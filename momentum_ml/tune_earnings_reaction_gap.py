"""
tune_earnings_reaction_gap.py – Datadriven rapportförbättring UTAN prisreaktion:
tillfälligt förbisedd, väntar på fördröjd fundamental uppvärdering?

Skiljer sig från befintlig PEAD (altdata/pead.py): PEAD använder prisreaktionen
SJÄLV som surprise-mått (positiv reaktion → förvänta fortsatt drift). Här är
måtten frikopplade:
  · "Surprise" = genuin fundamental förbättring (marginal-/EPS-förändring mot
    FÖREGÅENDE rapport för samma bolag), rakt ur siffrorna – oberoende av kurs.
  · "Reaktion" = samma token-fria abnormal-avkastning-proxy som PEAD använder
    (Chan–Jegadeesh–Lakonishok 1996), rapportveckan.
Hypotesen: bolag med positiv fundamental förbättring men DÄMPAD prisreaktion
(marknaden har inte hunnit ikapp) borde ge en fördröjd uppvärdering över
kommande månader – matchar strategins långsiktsram (8–26v), inte rapportveckan
själv.

Testar detta som en EGEN axel (gap_score) och jämför mot en ren
fundamental-förbättring-baseline UTAN reaktionsfiltret, för att isolera om
"marknaden missade det" faktiskt tillför något utöver "förbättringen var
verklig" (som tune_fundamentals.py redan delvis mäter).

Datakällor (redan cachade på Pi:n, inget nätverksanrop):
  · results*/fundamentals_from_mfn.csv, fundamentals_from_pdf.csv,
    fundamentals_from_avanza.csv – samma källor som
    altdata/value_screener._load_fundamentals(), men här läses VARJE
    rapportrad (inte bara senaste snapshotten).
  · data/data_loader.fetch_weekly_data – veckopris, cachad.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_earnings_reaction_gap.py [large|small]
"""
import sys
from pathlib import Path
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.fund_merge import fill_from_avanza
from altdata.value_screener import (
    _seg_market_cap_and_dir, _num, _to_msek, _effective_annualization_factor,
)

HORIZONS = [8, 26]   # veckor framåt – matchar strategins långsiktsram, inte rapportveckan


def _load_report_events(seg_name: str) -> pd.DataFrame:
    """
    Samma råkällor + sammanslagningslogik som value_screener._load_fundamentals,
    men returnerar EN RAD PER RAPPORT (inte bara senaste snapshotten) med
    marginal/EPS + delta mot FÖREGÅENDE rapport för samma ticker.
    """
    _, results_dir = _seg_market_cap_and_dir(seg_name)

    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = results_dir / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:
                pass
    text_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not text_df.empty and "pm_id" in text_df.columns:
        has_id = text_df["pm_id"].notna()
        merged = text_df[has_id].groupby("pm_id", as_index=False, sort=False).first()
        text_df = pd.concat([merged, text_df[~has_id]], ignore_index=True)

    avanza_p = results_dir / "fundamentals_from_avanza.csv"
    avanza_df = pd.read_csv(avanza_p) if avanza_p.exists() else pd.DataFrame()

    df = fill_from_avanza(text_df, avanza_df)
    if df.empty or "ticker" not in df.columns or "published" not in df.columns:
        return pd.DataFrame()

    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["ticker", "published"]).sort_values(["ticker", "published"])

    rows = []
    for t, g in df.groupby("ticker"):
        g = g.sort_values("published")
        prev_margin = prev_eps = None
        for _, r in g.iterrows():
            ebit_i = _to_msek(r.get("ebit"), r.get("ebit_unit"))
            rev_i = _to_msek(r.get("revenue"), r.get("revenue_unit"))
            margin_i = ebit_i / rev_i if (ebit_i is not None and rev_i not in (None, 0.0)) else None
            eps_i = _num(r.get("eps"))
            if eps_i is None:
                eps_i = _num(r.get("eps_basic"))

            if margin_i is not None and prev_margin is not None and eps_i is not None and prev_eps is not None:
                rows.append({
                    "ticker": t,
                    "published": r["published"],
                    "margin_delta": margin_i - prev_margin,
                    "eps_delta": eps_i - prev_eps,
                })
            if margin_i is not None:
                prev_margin = margin_i
            if eps_i is not None:
                prev_eps = eps_i
    return pd.DataFrame(rows)


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]

    events = _load_report_events(seg)
    if events.empty:
        print(f"Inga rapporthändelser med jämförbar föregående rapport för segment '{seg}' – "
              "kör mfn_pdf.py backfill / altdata/avanza.py fundamentals build först.")
        return
    print(f"{len(events)} rapporthändelser med marginal+EPS-delta mot föregående rapport, "
          f"{events['ticker'].nunique()} bolag.")

    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    rets = px.pct_change()
    market = rets.mean(axis=1)          # likaviktad marknadsproxy, samma som pead.py
    abn = rets.sub(market, axis=0)      # abnormal avkastning per vecka

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

    # ── Poolade percentilrankningar: fundamental förbättring + reaktionens magnitud ──
    events["fund_rank"] = events["margin_delta"].rank(pct=True) * 0.5 + events["eps_delta"].rank(pct=True) * 0.5
    events["reaction_mag_rank"] = events["reaction"].abs().rank(pct=True)
    # Hög = stark fundamental förbättring OCH dämpad reaktion (marknaden missade det).
    events["gap_score"] = events["fund_rank"] - events["reaction_mag_rank"]
    # Baseline: ren fundamental-förbättring, reaktionen ignorerad helt.
    events["fund_only_score"] = events["fund_rank"]

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
    print(f"  RAPPORT-GAP (fundamental förbättring UTAN prisreaktion) · segment {seg}")
    print("=" * 78)
    for label, score_col in (("gap_score (förbättring − |reaktion|)", "gap_score"),
                              ("fund_only (ren förbättring, ingen reaktionsfilter)", "fund_only_score")):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        for h in HORIZONS:
            full = ic_and_spread(events, score_col, f"x_{h}")
            ho = ic_and_spread(events[events["published"] >= holdout_start], score_col, f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: gap_score bör slå fund_only_score (visar att reaktionsfiltret TILLFÖR
  något utöver "förbättringen var verklig") OCH ha |IC| ≥ 0.03-0.05 med
  positiv Q5-Q1 på 8v/26v-horisonten för att vara värd att bygga in som en
  egen feature/screener-signal. Slår gap_score inte fund_only_score → idén om
  "marknaden missade det" håller inte, bara "förbättringen var verklig" gör
  jobbet (redan delvis fångat av tune_fundamentals.py).""")


if __name__ == "__main__":
    main()
