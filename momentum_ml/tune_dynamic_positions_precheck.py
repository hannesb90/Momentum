"""
tune_dynamic_positions_precheck.py – [EDGE-8] Dynamiskt MAX_POSITIONS,
steg 1 (billig förkontroll innan en full dynamisk-N-backtest byggs).
EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #16.

Frågan en full backtest skulle kosta mycket att svara på: "skulle ett
bredd-/dispersionsstyrt antal positioner hjälpa?". Den här förkontrollen
svarar på en billigare, nödvändig FÖRUTSÄTTNING först: varierar
`avg_pairwise_corr` (#83:s redan validerade dispersionsmått,
tune_dispersion_proxy.py::_pairwise_corr, kausalt beräknad) ens
TILLRÄCKLIGT mycket mellan large-segmentets ~15 historiska årliga
ombalanseringstillfällen (REBALANCE_WEEKS=52) för att en dynamisk regel
skulle ha något att styra på? Om spridningen är liten är en dynamisk-N-
backtest sannolikt bortkastad tid.

    /opt/momentum/venv/bin/python3 tune_dynamic_positions_precheck.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe


def pairwise_corr(data, tickers, as_of, weeks=26):
    closes = pd.DataFrame({t: data[t].loc[:as_of, "Close"] for t in tickers if t in data})
    closes = closes.tail(weeks + 1)
    rets = closes.pct_change().dropna(how="all")
    if rets.shape[1] < 5:
        return float("nan")
    corr = rets.corr()
    iu = np.triu_indices_from(corr.values, k=1)
    vals = corr.values[iu]
    vals = vals[~np.isnan(vals)]
    return float(np.mean(vals)) if len(vals) else float("nan")


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"])
    rebalance_dates = sorted(sig["Date"].unique())
    # Endast VAR 52:E ombalanseringsdatum (matchar produktionens faktiska takt) -
    # signals.csv har en rad per VECKA, inte bara rebalanseringsveckor.
    all_weeks = sorted(sig["Date"].unique())
    rw = int(seg.get("rebalance_weeks", 52))
    rebalance_dates = all_weeks[::rw]

    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    rows = []
    for d in rebalance_dates:
        c = pairwise_corr(data, tickers, d)
        if pd.notna(c):
            rows.append({"date": d, "avg_pairwise_corr": c})

    out = pd.DataFrame(rows)
    print(f"[dynamic_n_precheck] {len(out)} årliga ombalanseringstillfällen med mätbar korrelation.\n")
    print(out.to_string(index=False, formatters={"avg_pairwise_corr": lambda x: f"{x:.3f}"}))
    print(f"\n  min={out['avg_pairwise_corr'].min():.3f}  max={out['avg_pairwise_corr'].max():.3f}  "
          f"spann={out['avg_pairwise_corr'].max()-out['avg_pairwise_corr'].min():.3f}  "
          f"std={out['avg_pairwise_corr'].std():.3f}")
    print("\n[dynamic_n_precheck] Tolkning: ett stort spann/hög std betyder att en dynamisk regel "
          "HAR något att styra på (värt att bygga steg 2, en full backtest). Ett litet spann "
          "betyder att korrelationen är strukturellt stabil år för år i detta universum - en "
          "dynamisk-N-regel skulle sällan avvika från dagens fasta MAX_POSITIONS ändå.")
    print("[dynamic_n_precheck] Klart.")


if __name__ == "__main__":
    main()
