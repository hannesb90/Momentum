"""
tune_sector_theme_gap.py – Sektorn har redan flyttat sig, den enskilda
aktien har inte hunnit ikapp.

Skiljer sig från de övriga gap-skripten (earnings/insider/sentiment/
dividend): triggern är inte ett rapport-PM utan ett kontinuerligt,
rent prisbaserat mått, veckovis över hela panelen (samma stil som
tune_report_crowding.py/tune_attention_gap.py, inte event-baserat som
tune_earnings_reaction_gap.py).

Mått (per vecka, per aktie):
  · sector_mom  = sektorns (config-oberoende - backtest.sector_momentum
    använder redan load_sweden_universe()s riktiga per-ticker sector_map,
    INTE config.SECTOR_MAP som bara har 8 amerikanska exempel-tickers)
    likaviktade kumulativa avkastning senaste LOOKBACK_WEEKS veckorna.
  · stock_mom   = aktiens EGEN kumulativa avkastning samma fönster.
  · gap         = sector_mom - stock_mom (positivt = sektorn har rusat,
    aktien har INTE hunnit ikapp - "laggard i en het sektor").

Testar gap mot TVÅ baselines för att isolera om just kombinationen tillför
något:
  · sector_mom ensam (ren sektorrotation, redan görbart via
    backtest/sector_momentum.py - "köp den heta sektorn" utan
    laggard-filter).
  · -stock_mom ensam (ren tvärsnitts-reversal, ingen sektorkoppling alls).

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_sector_theme_gap.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe

LOOKBACK_WEEKS = 13   # samma storleksordning som dollar_vol_13w/rvol_13w
HORIZONS = [8, 26]


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]
    tickers, sector_map, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()

    sectors = {t: sector_map.get(t) for t in px.columns if sector_map.get(t)}
    if not sectors:
        print("Ingen sector_map-täckning för universumet - kan inte bygga sektor-grupper.")
        return
    by_sector: dict = {}
    for t, s in sectors.items():
        by_sector.setdefault(s, []).append(t)
    print(f"{len(px.columns)} bolag, {len(by_sector)} sektorer "
          f"(median {int(np.median([len(v) for v in by_sector.values()]))} bolag/sektor).")

    stock_mom = px.pct_change(LOOKBACK_WEEKS)
    # Sektorns likaviktade momentum = medel av MEDLEMMARNAS stock_mom (aktien
    # själv ingår - samma "inkludera sig själv"-förenkling som
    # equal_weight_index() i backtest/benchmark.py använder för hela
    # universumet; med typiskt >=10 bolag/sektor är snedvridningen liten).
    sector_mom = pd.DataFrame(index=px.index, columns=px.columns, dtype=float)
    for s, members in by_sector.items():
        cols = [m for m in members if m in stock_mom.columns]
        if len(cols) < 3:
            continue
        avg = stock_mom[cols].mean(axis=1)
        for c in cols:
            sector_mom[c] = avg

    gap = sector_mom - stock_mom
    fwd = {h: px.shift(-h) / px - 1 for h in HORIZONS}

    weeks = px.index
    holdout_start = weeks[-config.HOLDOUT_WEEKS] if len(weeks) > config.HOLDOUT_WEEKS else weeks[0]

    def ic_and_spread(signal_panel, mask_dates, h):
        r = fwd[h]
        ics, spreads = [], []
        for d in mask_dates:
            if d not in signal_panel.index or d not in r.index:
                continue
            s = signal_panel.loc[d].dropna()
            rr = r.loc[d]
            act = s[s.index.isin(rr.dropna().index)]
            if len(act) < 10:
                continue
            rrr = rr[act.index]
            ic = act.rank().corr(rrr.rank())
            if pd.notna(ic):
                ics.append(ic)
            hi = rrr[act >= act.quantile(0.8)].mean()
            lo = rrr[act <= act.quantile(0.2)].mean()
            if pd.notna(hi) and pd.notna(lo):
                spreads.append(hi - lo)
        return (np.mean(ics) if ics else float("nan"),
                np.mean(spreads) if spreads else float("nan"),
                len(ics))

    print("\n" + "=" * 78)
    print(f"  SEKTOR-GAP (sektorn flyttat sig, aktien inte) · segment {seg}")
    print("=" * 78)
    for label, panel in (("gap (sector_mom - stock_mom)", gap),
                          ("sector_mom (ren sektorrotation, ingen laggard-filter)", sector_mom),
                          ("-stock_mom (ren tvärsnitts-reversal, ingen sektorkoppling)", -stock_mom)):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n veckor':>10}")
        print("  " + "-" * 50)
        for h in HORIZONS:
            full = ic_and_spread(panel, weeks, h)
            ho = ic_and_spread(panel, weeks[weeks >= holdout_start], h)
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>10}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>10}")

    print("""
  Dom: gap bör slå BÅDE sector_mom-ensam och ren reversal-ensam, OCH ha
  |IC| >= 0.03-0.05 med positiv Q5-Q1 på holdouten, för att laggard-i-het-
  sektor vara en egen, värdefull axel. Slår gap inte båda baseline -> en av
  komponenterna (sektorrotation ELLER ren reversal) gör redan jobbet på
  egen hand, ingen anledning att kombinera dem.""")


if __name__ == "__main__":
    main()
