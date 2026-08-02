"""
tune_dividend_gap.py – Utdelningshöjning UTAN prisreaktion: har marknaden
missat ett förtroendesignal-PM?

Samma gap-mönster som tune_earnings_reaction_gap.py, med utdelning i stället
för marginal/EPS som fundamental-trigger:
  · "Surprise" = utdelningstillväxt YoY (dividend vs dividend_prior, båda
    finns direkt som kolumner i fundamentals_from_pdf.csv – PDF-extraktionen
    fångar dem redan, samma mönster som revenue/revenue_prior). En HÖJD
    utdelning är en välbelagd förtroendesignal (ledningen signalerar
    framtida kassaflöde) – starkare än bara dividend_any (boolean närvaro,
    som value_screener.py redan använder).
  · "Reaktion" = samma token-fria abnormal-avkastning-proxy som PEAD/
    earnings-gapet/insynsköp-gapet/sentiment-gapet använder, rapportveckan.
Hypotesen: bolag med höjd utdelning men DÄMPAD prisreaktion borde ge en
fördröjd uppvärdering.

OBS teckenkonvention: dividend/dividend_prior lagras som NEGATIVA tal
(kassautflöde, samma konvention som capex) i PDF-extraktionen – tillväxt
räknas därför på abs(), precis som value_screener._num-hanteringen av andra
utflödesfält gör på andra ställen.

Datakällor (redan cachade på Pi:n, inget nätverksanrop):
  · results*/fundamentals_from_mfn.csv, fundamentals_from_pdf.csv – samma
    källor som tune_earnings_reaction_gap.py, men bara PDF-extraktionen har
    dividend/dividend_prior i praktiken (MFN-textextraktionen har nästan
    ingen täckning för utdelning, 8/3769 rader).
  · data/data_loader.fetch_weekly_data – veckopris, cachad.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_dividend_gap.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.value_screener import _to_msek

HORIZONS = [8, 26]


def _load_dividend_events(seg_name: str) -> pd.DataFrame:
    """En rad per rapport med både dividend och dividend_prior ifyllda →
    utdelningstillväxt YoY (abs-baserad, se docstring ovan)."""
    from altdata.value_screener import _seg_market_cap_and_dir
    _, results_dir = _seg_market_cap_and_dir(seg_name)

    frames = []
    for fname in ("fundamentals_from_pdf.csv", "fundamentals_from_mfn.csv"):
        p = results_dir / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:
                pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if "pm_id" in df.columns:
        has_id = df["pm_id"].notna()
        merged = df[has_id].groupby("pm_id", as_index=False, sort=False).first()
        df = pd.concat([merged, df[~has_id]], ignore_index=True)
    needed = {"ticker", "published", "dividend", "dividend_prior"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()
    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["ticker", "published"])

    rows = []
    unit_col = df["dividend_unit"] if "dividend_unit" in df.columns else pd.Series([None] * len(df))
    for (_, r), unit in zip(df.iterrows(), unit_col):
        div_i = _to_msek(r.get("dividend"), unit)
        div_prior = _to_msek(r.get("dividend_prior"), unit)
        if div_i is None or div_prior is None or abs(div_prior) == 0:
            continue
        growth = (abs(div_i) - abs(div_prior)) / abs(div_prior)
        rows.append({"ticker": r["ticker"], "published": r["published"], "div_growth_yoy": growth})
    return pd.DataFrame(rows).drop_duplicates(subset=["ticker", "published"])


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]

    events = _load_dividend_events(seg)
    if events.empty:
        print(f"Ingen utdelningsdata (dividend+dividend_prior) för segment '{seg}' – "
              "kör altdata/mfn_pdf.py backfill först.")
        return
    print(f"{len(events)} rapporter med utdelningstillväxt YoY, {events['ticker'].nunique()} bolag.")

    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    rets = px.pct_change()
    market = rets.mean(axis=1)
    abn = rets.sub(market, axis=0)

    events = events[events["ticker"].isin(px.columns)].copy()
    weeks = px.index

    def _week_of(ts):
        pos = weeks.searchsorted(ts, side="left")
        return weeks[pos] if pos < len(weeks) else None

    events["report_week"] = events["published"].apply(_week_of)
    events = events.dropna(subset=["report_week"])

    events["reaction"] = [
        abn.at[wk, tk] if (wk in abn.index and tk in abn.columns) else np.nan
        for wk, tk in zip(events["report_week"], events["ticker"])
    ]
    for h in HORIZONS:
        vals = []
        for wk, tk in zip(events["report_week"], events["ticker"]):
            s = px[tk] if tk in px.columns else None
            if s is None or wk not in px.index:
                vals.append(np.nan)
                continue
            pos = px.index.get_loc(wk)
            if pos + h < len(px.index) and pd.notna(s.iloc[pos]) and s.iloc[pos] != 0:
                vals.append(s.iloc[pos + h] / s.iloc[pos] - 1)
            else:
                vals.append(np.nan)
        events[f"fwd_{h}"] = vals

    events = events.dropna(subset=["reaction"])
    events["year"] = events["published"].dt.year
    for h in HORIZONS:
        col = f"fwd_{h}"
        events[f"x_{h}"] = events[col] - events.groupby("year")[col].transform("mean")

    events["div_rank"] = events["div_growth_yoy"].rank(pct=True)
    events["reaction_mag_rank"] = events["reaction"].abs().rank(pct=True)
    events["gap_score"] = events["div_rank"] - events["reaction_mag_rank"]
    events["div_only_score"] = events["div_rank"]

    holdout_start = pd.Timestamp.now() - pd.DateOffset(weeks=config.HOLDOUT_WEEKS)

    def ic_and_spread(df, score_col, x_col):
        sub = df.dropna(subset=[score_col, x_col])
        if len(sub) < 20:
            return float("nan"), float("nan"), len(sub)
        ic = sub[score_col].rank().corr(sub[x_col].rank())
        q5 = sub[sub[score_col] >= sub[score_col].quantile(0.8)][x_col].mean()
        q1 = sub[sub[score_col] <= sub[score_col].quantile(0.2)][x_col].mean()
        return ic, (q5 - q1), len(sub)

    print("\n" + "=" * 78)
    print(f"  UTDELNINGS-GAP (höjning UTAN prisreaktion) · segment {seg}")
    print("=" * 78)
    for label, score_col in (("gap_score (utdelningstillväxt − |reaktion|)", "gap_score"),
                              ("div_only (rå utdelningstillväxt, ingen reaktionsfilter)", "div_only_score")):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        for h in HORIZONS:
            full = ic_and_spread(events, score_col, f"x_{h}")
            ho = ic_and_spread(events[events["published"] >= holdout_start], score_col, f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: gap_score bör slå div_only_score OCH ha |IC| ≥ 0.03-0.05 med positiv
  Q5-Q1 på 8v/26v-horisonten för att vara värd att bygga in. Slår gap_score
  inte div_only_score → idén om "marknaden missade utdelningshöjningen"
  håller inte.""")


if __name__ == "__main__":
    main()
