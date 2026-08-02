"""Large N3-SR45: all 52 calendar rebalance phases, no phase selection."""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large
apply_large()

from backtest.backtester import MomentumBacktester
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/00_large_scope_baseline.json"
SOURCE = ROOT / "results/niva2_stage6_winner_signals.csv"
OUT = ROOT / "results/niva3_calendar52_phase.json"
CSV = ROOT / "results/niva3_calendar52_phase_arms.csv"


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _metrics(values):
    values = values.dropna().astype(float); r = values.pct_change().dropna()
    years = (values.index[-1] - values.index[0]).days / 365.25
    cagr = (values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(52) if len(r) > 1 and r.std(ddof=1) else np.nan
    dd = (values / values.cummax() - 1).min()
    return {"cagr": float(cagr), "sharpe": float(sharpe), "max_drawdown": float(dd)}


def _benchmark(prices, dates):
    close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().dropna()
    nav = close / close.iloc[0]
    return _metrics(nav)


def main():
    parent = verify_manifest(PARENT)
    signals = pd.read_csv(SOURCE, parse_dates=["Date"]).set_index("Date").sort_index()
    _, prices, _, _ = _load_state()
    dates = signals.index.unique().sort_values()
    if len(dates) < 52 * 3:
        raise RuntimeError("Need at least three annual cycles for phase test")
    common_start = dates[51]; common_dates = dates[51:]
    benchmark = _benchmark(prices, common_dates)
    rows = []
    for phase in range(52):
        arm = signals[signals.index >= dates[phase]]
        bt = NoCorrelationBacktester(arm, prices); result = bt.run()
        stats = _metrics(result.loc[result.index >= common_start, "portfolio_value"])
        rows.append({"phase": phase, "first_rebalance": str(dates[phase].date()),
                     "common_start": str(common_start.date()), **stats,
                     "benchmark_cagr": benchmark["cagr"],
                     "alpha_cagr": stats["cagr"] - benchmark["cagr"]})
        print(f"phase {phase:02d}/51 CAGR={stats['cagr']:.2%} alpha={stats['cagr']-benchmark['cagr']:+.2%}", flush=True)
    table = pd.DataFrame(rows); table.to_csv(CSV, index=False)
    alpha = table.alpha_cagr
    share = float((alpha > 0).mean()); median = float(alpha.median())
    # Predeclared robustness classification; never used to select a phase.
    robust = median > 0 and share >= 0.75
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
      "test": "N3-SR45", "phases_tested": 52, "phase_selection_allowed": False,
      "holdout_used": False, "common_window": {"start": str(common_start.date()),
        "end": str(common_dates[-1].date()), "weeks": len(common_dates)},
      "benchmark": config.INDEX_BENCHMARK_TICKER, "benchmark_metrics": benchmark,
      "alpha_distribution": {"median": median, "p10": float(alpha.quantile(.10)),
        "worst": float(alpha.min()), "best": float(alpha.max()),
        "share_phases_beating_index": share, "range": float(alpha.max()-alpha.min())},
      "robustness_gate": "PASS" if robust else "FAIL",
      "decision": "keep calendar52 architecture without choosing phase" if robust else
                  "calendar52 phase-sensitive; do not advance architecture unchanged",
      "actual_frozen_phase0": table.iloc[0].to_dict(),
      "multiple_testing_arms": 52}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("01_calendar52_phase_robustness", [OUT, CSV, Path(__file__).resolve()],
        {"test": "N3-SR45", "phases": 52, "robustness_gate": report["robustness_gate"],
         "phase_selection": False, "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)

if __name__ == "__main__": main()
