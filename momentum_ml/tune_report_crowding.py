"""
tune_report_crowding.py – Rapportträngsel/distraktion (Hirshleifer, Lim & Teoh
2009): underreagerar marknaden MER på en rapport när många andra bolag
rapporterar samma vecka (delad uppmärksamhet), så PEAD-driften blir starkare
efteråt?

Skiljer sig från tune_pead.py och tune_earnings_reaction_gap.py: ingen ny
"surprise"-källa. Samma token-fria PEAD-reaktion (abnormal avkastning
rapportveckan) som redan finns, men datat SPLITTAT på hur många ANDRA bolag
i universumet som rapporterade samma kalendervecka ("trängsel"). Hypotesen:
PEAD-edgen (IC/kvintilspread mot framåtavkastning) ska vara STARKARE i
tränga veckor än i lugna veckor, eftersom en trång vecka dämpar den
OMEDELBARA reaktionen mer än den "borde" - mer kvar att hämta in efteråt.

Ingen ny datakälla: räknar bara om samma MFN-rapportdatum (extract_report_dates,
altdata/pead.py) som PEAD redan använder, över HELA universumet i stället för
en ticker i taget.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_report_crowding.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.pead import load_report_dates

HORIZONS = [8, 26]


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]
    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    rets = px.pct_change()
    market = rets.mean(axis=1)
    abn = rets.sub(market, axis=0)
    weeks = px.index

    report_dates = load_report_dates(config.MFN_CACHE_DIR)
    if not report_dates:
        print(f"Ingen MFN-cache i {config.MFN_CACHE_DIR}. Kör mfn_fetch.fetch_universe('{seg}') först.")
        return

    # ── Trängsel: mappa varje rapport till sin veckobar, räkna ANTAL BOLAG
    # (inte antal PM) som rapporterar samma veckobar, över HELA universumet
    # (även bolag utanför segmentet räknas med - trängseln är en marknadsbred
    # uppmärksamhetsresurs, inte segmentspecifik).
    week_of = {}
    for t, dates in report_dates.items():
        for d in dates:
            pos = weeks.searchsorted(pd.Timestamp(d).normalize(), side="left")
            if pos < len(weeks):
                week_of.setdefault((t, pd.Timestamp(d).normalize()), weeks[pos])
    crowd_count = pd.Series([wk for wk in week_of.values()]).value_counts()

    events = []
    for t, dates in report_dates.items():
        if t not in px.columns:
            continue
        for d in dates:
            wk = week_of.get((t, pd.Timestamp(d).normalize()))
            if wk is None or wk not in abn.index or t not in abn.columns:
                continue
            reaction = abn.at[wk, t]
            if pd.isna(reaction):
                continue
            events.append({"ticker": t, "published": pd.Timestamp(d), "report_week": wk,
                            "reaction": reaction, "crowding": int(crowd_count.get(wk, 1))})
    events = pd.DataFrame(events)
    if events.empty:
        print("Inga rapporthändelser med prisdata matchade.")
        return
    print(f"{len(events)} rapporthändelser, {events['ticker'].nunique()} bolag, "
          f"trängsel (bolag/vecka) median={events['crowding'].median():.0f}, "
          f"p90={events['crowding'].quantile(0.9):.0f}")

    for h in HORIZONS:
        vals = []
        for wk, t in zip(events["report_week"], events["ticker"]):
            s = px[t]
            pos = px.index.get_loc(wk)
            if pos + h < len(px.index) and pd.notna(s.iloc[pos]) and s.iloc[pos] != 0:
                vals.append(s.iloc[pos + h] / s.iloc[pos] - 1)
            else:
                vals.append(np.nan)
        events[f"fwd_{h}"] = vals

    events["year"] = events["published"].dt.year
    for h in HORIZONS:
        col = f"fwd_{h}"
        events[f"x_{h}"] = events[col] - events.groupby("year")[col].transform("mean")

    holdout_start = weeks[-1] - pd.DateOffset(weeks=config.HOLDOUT_WEEKS)
    crowd_hi = events["crowding"] >= events["crowding"].median()

    def ic_and_spread(df, x_col):
        sub = df.dropna(subset=["reaction", x_col])
        if len(sub) < 20:
            return float("nan"), float("nan"), len(sub)
        ic = sub["reaction"].rank().corr(sub[x_col].rank())
        q5 = sub[sub["reaction"] >= sub["reaction"].quantile(0.8)][x_col].mean()
        q1 = sub[sub["reaction"] <= sub["reaction"].quantile(0.2)][x_col].mean()
        return ic, (q5 - q1), len(sub)

    print("\n" + "=" * 78)
    print(f"  RAPPORTTRÄNGSEL · PEAD-edge (reaktion → framåtavkastning) trång vs lugn vecka · {seg}")
    print("=" * 78)
    for label, mask in (("TRÅNG vecka (≥ median bolag/vecka)", crowd_hi),
                         ("LUGN vecka (< median bolag/vecka)", ~crowd_hi)):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        sub_all = events[mask]
        for h in HORIZONS:
            full = ic_and_spread(sub_all, f"x_{h}")
            ho = ic_and_spread(sub_all[sub_all["published"] >= holdout_start], f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: PEAD-IC/Q5-Q1 bör vara TYDLIGT starkare i trånga veckor än lugna för
  att distraktionshypotesen ska hålla. Ingen skillnad (eller omvänd) → idén
  tillför inget utöver PEAD:et som redan finns.""")


if __name__ == "__main__":
    main()
