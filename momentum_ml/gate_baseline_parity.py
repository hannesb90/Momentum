"""SR-9: canonical backtest determinism and saved-NAV parity gate."""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtest.backtester import MomentumBacktester
from research_gates_common import ROOT, apply_large, fingerprint, write_report
from data.data_loader import (fetch_weekly_data, filter_active_universe,
                              filter_liquid_universe, load_sweden_universe)
import config

TOL_BPS = 1.0


def main() -> int:
    apply_large()
    signals = pd.read_csv(ROOT / "results/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    seg = config.SEGMENTS["large"]
    tickers, sectors, caps, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps)
    cached = ROOT / "results/abstention_price_data.pkl"
    if cached.exists():
        prices = pd.read_pickle(cached)
    else:
        prices = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
        prices = filter_liquid_universe(filter_active_universe(prices),
                                        config.UNIVERSE_MIN_AVG_TURNOVER)
    runs = []
    for _ in range(2):
        bt = MomentumBacktester(signals, prices)
        runs.append(bt.run())
    cols = ["portfolio_value", "cash", "n_positions", "drawdown_guard", "market_exposure", "vol_exposure"]
    deterministic = fingerprint(runs[0], cols) == fingerprint(runs[1], cols)
    saved = pd.read_csv(ROOT / "results/portfolio.csv", parse_dates=["Date"]).set_index("Date")
    common = runs[0].index.intersection(saved.index)
    # Senaste veckobaren kan ha uppdaterats efter att portfolio.csv skrevs.
    # Paritetskontraktet gäller finaliserad historik; livebaren rapporteras separat.
    finalized = common[:-1]
    ret_new = runs[0].loc[finalized, "portfolio_value"].pct_change()
    ret_old = saved.loc[finalized, "portfolio_value"].pct_change()
    diff_bps = ((ret_new - ret_old).abs() * 1e4).dropna()
    max_bps = float(diff_bps.max()) if len(diff_bps) else float("inf")
    n_mismatch = int((diff_bps > TOL_BPS).sum())
    worst_date = str(diff_bps.idxmax().date()) if len(diff_bps) else None
    worst_new = float(runs[0].loc[diff_bps.idxmax(), "portfolio_value"]) if len(diff_bps) else None
    worst_saved = float(saved.loc[diff_bps.idxmax(), "portfolio_value"]) if len(diff_bps) else None
    latest_nav_diff_bps = float(abs(runs[0].loc[common[-1], "portfolio_value"] /
                                    saved.loc[common[-1], "portfolio_value"] - 1) * 1e4)
    pass_gate = deterministic and len(common) == len(runs[0]) and max_bps <= TOL_BPS
    report = {"gate": "SR-9", "status": "PASS" if pass_gate else "FAIL",
              "deterministic": deterministic, "weeks_rerun": len(runs[0]),
              "weeks_common_saved": len(common), "max_weekly_return_diff_bps": max_bps,
              "finalized_through": str(finalized[-1].date()),
              "latest_unfinalized_nav_diff_bps": latest_nav_diff_bps,
              "weeks_over_tolerance": n_mismatch, "tolerance_bps": TOL_BPS,
              "worst_date": worst_date, "worst_rerun_nav": worst_new,
              "worst_saved_nav": worst_saved,
              "fingerprint": fingerprint(runs[0], cols)}
    path = write_report("sr9_baseline_parity", report)
    print(report); print(path)
    return 0 if pass_gate else 1


if __name__ == "__main__": raise SystemExit(main())
