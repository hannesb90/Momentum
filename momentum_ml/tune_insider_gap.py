"""
tune_insider_gap.py – Insynsköp-kluster UTAN prisreaktion: har marknaden
missat att insiders köper?

Samma gap-mönster som tune_earnings_reaction_gap.py, men med insynsköp som
trigger i stället för fundamental förbättring:
  · "Surprise" = nettoinsynsköp (köp-PM minus sälj-PM, PDMR-transaktioner)
    de senaste 90 dagarna före händelsen, räknat historiskt (inte bara
    dagens rullande snapshot som altdata/mfn_events.scan() skriver).
    Insynsköp är enligt mfn_events.py:s egen docstring "en av de starkast
    belagda positiva signalerna i litteraturen" (insiders säljer av många
    skäl, köper bara av ett).
  · "Reaktion" = samma token-fria abnormal-avkastning-proxy (rets minus
    likaviktad marknadsproxy) som PEAD/earnings-gapet använder, veckan
    köp-PM:et publicerades.
Hypotesen: bolag med starkt nettoinsynsköp men DÄMPAD prisreaktion (marknaden
har inte hunnit reagera på att insiders köper) borde ge en fördröjd
uppvärdering över kommande månader.

Datakällor (redan cachade på Pi:n, inget nätverksanrop):
  · cache/mfn/<ticker>.json – altdata.mfn_events.load_insider_events() läser
    HELA cachen strömmande (en fil i taget, se den funktionens docstring för
    varför: samma minnesbugg som fällde tune_pead.py/tune_report_crowding.py
    2026-07-19 om man läser in alla filer i minnet samtidigt).
  · data/data_loader.fetch_weekly_data – veckopris, cachad.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_insider_gap.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.mfn_events import load_insider_events

HORIZONS = [8, 26]        # veckor framåt – matchar strategins långsiktsram
CLUSTER_WINDOW_DAYS = 90  # samma fönster som mfn_events.scan()


def _load_buy_events_with_net() -> pd.DataFrame:
    """Alla PDMR-transaktioner → en rad per KÖP-PM, med nettoköp
    (köp minus sälj, samma ticker) inom det föregående 90-dagarsfönstret."""
    rows = load_insider_events(config.MFN_CACHE_DIR)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["published"] = pd.to_datetime(df["published"])
    out = []
    for t, g in df.groupby("ticker"):
        g = g.sort_values("published").reset_index(drop=True)
        dates = g["published"].values
        sides = g["side"].values
        for i, row in g.iterrows():
            if row["side"] != "buy":
                continue
            win_start = row["published"] - pd.Timedelta(days=CLUSTER_WINDOW_DAYS)
            mask = (dates > np.datetime64(win_start)) & (dates <= np.datetime64(row["published"]))
            net = int((sides[mask] == "buy").sum() - (sides[mask] == "sell").sum())
            out.append({"ticker": t, "published": row["published"], "net_buys_90d": net})
    return pd.DataFrame(out)


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]

    events = _load_buy_events_with_net()
    if events.empty:
        print(f"Inga insynsköp hittade i {config.MFN_CACHE_DIR}. "
              "Kör mfn_fetch.fetch_universe(...) först.")
        return
    print(f"{len(events)} köp-PM med nettoköp-kontext, {events['ticker'].nunique()} bolag.")

    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    rets = px.pct_change()
    market = rets.mean(axis=1)          # likaviktad marknadsproxy, samma som pead.py
    abn = rets.sub(market, axis=0)

    events = events[events["ticker"].isin(px.columns)].copy()
    weeks = px.index

    def _week_of(ts):
        pos = weeks.searchsorted(ts, side="left")
        return weeks[pos] if pos < len(weeks) else None

    events["event_week"] = events["published"].apply(_week_of)
    events = events.dropna(subset=["event_week"])

    events["reaction"] = [
        abn.at[wk, tk] if (wk in abn.index and tk in abn.columns) else np.nan
        for wk, tk in zip(events["event_week"], events["ticker"])
    ]
    for h in HORIZONS:
        vals = []
        for wk, tk in zip(events["event_week"], events["ticker"]):
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

    # ── Poolade percentilrankningar: insynsköp-styrka + reaktionens magnitud ──
    events["buy_rank"] = events["net_buys_90d"].rank(pct=True)
    events["reaction_mag_rank"] = events["reaction"].abs().rank(pct=True)
    # Hög = starkt nettoinsynsköp OCH dämpad reaktion (marknaden missade det).
    events["gap_score"] = events["buy_rank"] - events["reaction_mag_rank"]
    # Baseline: rått insynsköp-signal, reaktionen ignorerad helt.
    events["buy_only_score"] = events["buy_rank"]

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
    print(f"  INSYNSKÖP-GAP (nettoköp UTAN prisreaktion) · segment {seg}")
    print("=" * 78)
    for label, score_col in (("gap_score (nettoköp − |reaktion|)", "gap_score"),
                              ("buy_only (rått nettoköp, ingen reaktionsfilter)", "buy_only_score")):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        for h in HORIZONS:
            full = ic_and_spread(events, score_col, f"x_{h}")
            ho = ic_and_spread(events[events["published"] >= holdout_start], score_col, f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: gap_score bör slå buy_only_score (visar att reaktionsfiltret TILLFÖR
  något utöver "insiders köpte") OCH ha |IC| ≥ 0.03-0.05 med positiv Q5-Q1 på
  8v/26v-horisonten för att vara värd att bygga in. Slår gap_score inte
  buy_only_score → idén om "marknaden missade insynsköpet" håller inte, bara
  själva insynsköpet gör jobbet (redan delvis fångat via insider_buys_90d i
  portfolio.py:s köp-vakt).""")


if __name__ == "__main__":
    main()
