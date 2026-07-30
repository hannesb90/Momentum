"""
tune_newly_qualified_vs_established.py – [SCN-KÖP-3] Nykvalificerade bolag
(precis passerat MIN_HISTORY_WEEKS=78) i köpsignalerna – presterar de
sämre/mer volatilt än etablerade namn, trots samma konviktion i sizingen?
(EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #24, skärpning av LCA-41/RISK-6.)

Ren mätning mot redan sparade results/signals.csv + cachead prisdata, ingen
omträning. För varje köpsignal (pred_signal==1): räkna hur många veckors
egen prishistorik tickern hade FRAM TILL just det datumet (från sin första
kända notering i den redan hämtade panelen), inte totalt-idag som
data_loader.py:s MIN_HISTORY_WEEKS-filter gör vid hämtningstillfället.
Buckets: nykvalificerad (78-130v, dvs inom ~1 år efter att ha passerat
tröskeln) vs etablerad (>=260v, 5+ år). Mäter forward-avkastning (13/26/52v)
och volatilitet (std av veckoavkastning under hållperioden) per grupp.

    /opt/momentum/venv/bin/python3 tune_newly_qualified_vs_established.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

HORIZONS = (13, 26, 52)
NEW_LO, NEW_HI = config.MIN_HISTORY_WEEKS, config.MIN_HISTORY_WEEKS + 52
EST_LO = 260


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).sort_values(["ticker", "Date"])
    buys = sig[sig["pred_signal"] == 1].copy()
    print(f"[newly_qualified] {len(buys)} köpsignal-observationer i signals.csv.")

    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    first_date = {t: px[t].dropna().index.min() for t in px.columns}

    rows = []
    for r in buys.itertuples(index=False):
        t = r.ticker
        if t not in px.columns or pd.isna(first_date.get(t)):
            continue
        weeks_hist = (r.Date - first_date[t]).days / 7.0
        if NEW_LO <= weeks_hist < NEW_HI:
            group = "nykvalificerad"
        elif weeks_hist >= EST_LO:
            group = "etablerad"
        else:
            continue
        pos = px.index.searchsorted(r.Date)
        if pos >= len(px) or px.index[pos] != r.Date:
            # närmaste handelsdatum om exakt match saknas
            pos = px.index.get_indexer([r.Date], method="nearest")[0]
        p0 = px[t].iloc[pos]
        row = {"Date": r.Date, "ticker": t, "group": group, "weeks_hist": weeks_hist}
        for h in HORIZONS:
            if pos + h < len(px) and pd.notna(px[t].iloc[pos + h]) and pd.notna(p0) and p0:
                row[f"ret_{h}"] = px[t].iloc[pos + h] / p0 - 1
            else:
                row[f"ret_{h}"] = np.nan
        # veckovis volatilitet under hållperioden (52v, eller kortare om data tar slut)
        seg_prices = px[t].iloc[pos:pos + 53]
        wk_rets = seg_prices.pct_change().dropna()
        row["weekly_vol"] = wk_rets.std() if len(wk_rets) >= 8 else np.nan
        rows.append(row)

    out = pd.DataFrame(rows)
    print(f"[newly_qualified] {len(out)} klassificerbara observationer "
          f"({(out['group']=='nykvalificerad').sum()} nykvalificerade, "
          f"{(out['group']=='etablerad').sum()} etablerade).\n")

    print("=" * 90)
    print("Forward-avkastning + volatilitet per grupp")
    print("=" * 90)
    for group, g in out.groupby("group"):
        print(f"\n  {group} (n={len(g)}):")
        for h in HORIZONS:
            x = g[f"ret_{h}"].dropna()
            if len(x):
                print(f"    {h:>3}v: n={len(x):<5} medel={x.mean():+.2%} median={x.median():+.2%} "
                      f"std={x.std():.2%} positiv={100*(x>0).mean():.0f}%")
        vol = g["weekly_vol"].dropna()
        if len(vol):
            print(f"    veckovolatilitet (annualiserad): medel={vol.mean()*np.sqrt(52):.1%} "
                  f"median={vol.median()*np.sqrt(52):.1%}")

    print("\n[newly_qualified] Klart.")


if __name__ == "__main__":
    main()
