"""
tune_dynamic_positions_backtest.py – [EDGE-8] steg 2: full backtest av
dispersionsstyrt (dynamiskt) MAX_POSITIONS (EDGE_RISK_SCENARIO_TESTKO.md
Tier 3 #16). Uppföljning på #151 (steg 1), som bekräftade att
`avg_pairwise_corr` varierar genuint (0,13-0,60) mellan large-segmentets 17
historiska ombalanseringsår - förutsättningen för att en dynamisk regel ska
kunna göra skillnad.

Metod: bygger OM signals.csv:s `position_size`/`pred_signal` bara på de 17
ombalanseringsdatumen (produktionens övriga logik - korrelationsfilter,
sektorspärr, marknadsfilter, vol-target - rörs INTE, de körs redan i
MomentumBacktester oförändrat). Dynamisk regel (kausal, `avg_pairwise_corr`
mätt FÖRE varje ombalansering, aldrig framåtblickande):

    corr < 0.25  -> N=20 (låg korrelation, genuin dispersion att utnyttja)
    corr > 0.45  -> N=8  (hög korrelation, marknaden rör sig som ett block -
                          koncentrera i de starkaste namnen i stället)
    annars       -> N=15 (dagens fasta default, oförändrat)

Kandidaturval: samma `selection_eligible`/`selection_rank`-kolumner
signals.csv redan har (produktionens riktiga rangordning), bara
ANTALET som väljs och likaviktningen (matchar `qualified_holder_
portfolio_audit.py`:s redan etablerade likaviktnings-konvention) ändras.

Jämför: baslinje (dagens fasta N=15, signals.csv oförändrat) vs dynamisk N.

    /opt/momentum/venv/bin/python3 tune_dynamic_positions_backtest.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

LOW_CORR, HIGH_CORR = 0.25, 0.45
N_LOW_CORR, N_HIGH_CORR, N_DEFAULT = 20, 8, 15


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


def dynamic_n(corr):
    if pd.isna(corr):
        return N_DEFAULT
    if corr < LOW_CORR:
        return N_LOW_CORR
    if corr > HIGH_CORR:
        return N_HIGH_CORR
    return N_DEFAULT


def rebuild_signals_dynamic(sig: pd.DataFrame, rebalance_dates: list, n_by_date: dict) -> pd.DataFrame:
    out = sig.copy()
    for d in rebalance_dates:
        mask = out["Date"] == d
        day = out.loc[mask]
        n = n_by_date[d]
        cand = day[day["selection_eligible"] == 1].sort_values("selection_rank", ascending=False)
        top = set(cand["ticker"].head(n))
        w = 1.0 / len(top) if top else 0.0
        out.loc[mask, "position_size"] = out.loc[mask, "ticker"].map(lambda t: w if t in top else 0.0)
        out.loc[mask, "pred_signal"] = out.loc[mask, "ticker"].isin(top).astype(int)
    return out


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"])
    all_weeks = sorted(sig["Date"].unique())
    rw = int(seg.get("rebalance_weeks", 52))
    rebalance_dates = all_weeks[::rw]

    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    n_by_date = {}
    print("[dynamic_n] Ombalanseringsdatum -> korrelation -> dynamiskt N:")
    for d in rebalance_dates:
        c = pairwise_corr(data, tickers, d)
        n = dynamic_n(c)
        n_by_date[d] = n
        print(f"    {d.date()}: corr={c:.3f} -> N={n}")

    # Baslinje: dagens FASTA N=15 på ALLA ombalanseringsdatum (replikerar
    # signals.csv:s redan bakade urval - ingen ombyggnad behövs för den).
    sig_dynamic = rebuild_signals_dynamic(sig, rebalance_dates, n_by_date)
    sig_baseline_fixed15 = rebuild_signals_dynamic(sig, rebalance_dates, {d: N_DEFAULT for d in rebalance_dates})

    holdout_start = sig["Date"].unique()
    holdout_start = sorted(holdout_start)[-config.HOLDOUT_WEEKS] if len(holdout_start) > config.HOLDOUT_WEEKS else None

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("\n[dynamic_n] Kör baslinje (fast N=15, samma urvalslogik/likaviktning som dynamisk-varianten)...")
    bt_base = MomentumBacktester(sig_baseline_fixed15.set_index("Date"), data)
    bt_base.run()

    print("[dynamic_n] Kör dynamisk N (korrelationsstyrd)...")
    bt_dyn = MomentumBacktester(sig_dynamic.set_index("Date"), data)
    bt_dyn.run()

    print("\n" + "=" * 90)
    print("Full backtest (large) – fast N=15 vs dispersionsstyrt dynamiskt N")
    print("=" * 90)
    for name, bt in (("fast N=15 (kontroll)", bt_base), ("dynamiskt N", bt_dyn)):
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  {name:<22}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}")

    print("\n[dynamic_n] Klart.")


if __name__ == "__main__":
    main()
