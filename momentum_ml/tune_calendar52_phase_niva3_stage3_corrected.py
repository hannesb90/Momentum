"""Corrected N3-SR45 rerun with the frozen Large backtest environment.

N3-01 and N3-02 omitted the universe-derived sector/cap/name maps.  That made
their backtest environment differ from N2 Stage 06.  This remediation first
requires exact rounded parity with the frozen Stage-06 statistics, then reruns
all 52 phases without selecting one.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large

apply_large()

from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/02_phase_robust_rotation_remediation.json"
SOURCE = ROOT / "results/niva2_stage6_winner_signals.csv"
N2_REPORT = ROOT / "results/retraining_staleness_niva2.json"
OUT = ROOT / "results/niva3_calendar52_phase_corrected.json"
CSV = ROOT / "results/niva3_calendar52_phase_corrected_arms.csv"


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _metrics(values: pd.Series) -> dict:
    values = values.dropna().astype(float)
    ret = values.pct_change().dropna()
    years = (values.index[-1] - values.index[0]).days / 365.25
    return {
        "cagr": float((values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1),
        "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(52)),
        "max_drawdown": float((values / values.cummax() - 1).min()),
    }


def _load_frozen_environment():
    signals = pd.read_csv(SOURCE, parse_dates=["Date"]).set_index("Date").sort_index()
    _, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"]
    )
    if not sectors or not caps:
        raise RuntimeError("Large sector/cap maps are empty")
    config.SECTOR_MAP.update(sectors)
    config.CAP_TIER_MAP.update(caps)
    config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS = 52
    return signals, prices, {"sectors": len(sectors), "caps": len(caps), "names": len(names)}


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("architecture_gate") != "FAIL":
        raise RuntimeError("Corrected phase rerun expected failed N3-02 parent")
    signals, prices, map_counts = _load_frozen_environment()

    # Fail closed unless the exact Stage-06 signal reproduces the frozen rounded
    # metrics in the same environment.  This catches missing overlays/maps.
    parity_bt = NoCorrelationBacktester(signals, prices)
    parity_bt.run()
    actual_parity = parity_bt.statistics()
    expected_parity = json.loads(N2_REPORT.read_text())["retrain_13w_parity"]
    keys = ("CAGR", "Sharpe", "Max Drawdown")
    mismatches = {k: {"actual": actual_parity[k], "expected": expected_parity[k]}
                  for k in keys if actual_parity[k] != expected_parity[k]}
    if mismatches:
        raise RuntimeError(f"N2 Stage-06 baseline parity failed: {mismatches}")

    dates = signals.index.unique().sort_values()
    common_start = dates[51]
    common_dates = dates[51:]
    close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(common_dates).ffill().dropna()
    benchmark = _metrics(close / close.iloc[0])
    rows = []
    for phase in range(52):
        arm = signals[signals.index >= dates[phase]]
        bt = NoCorrelationBacktester(arm, prices)
        result = bt.run()
        met = _metrics(result.loc[result.index >= common_start, "portfolio_value"])
        rows.append({"phase": phase, "first_rebalance": str(dates[phase].date()), **met,
                     "benchmark_cagr": benchmark["cagr"],
                     "alpha_cagr": met["cagr"] - benchmark["cagr"]})
        print(f"phase {phase:02d}/51 CAGR={met['cagr']:.2%} alpha={met['cagr']-benchmark['cagr']:+.2%}",
              flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(CSV, index=False)
    alpha = table.alpha_cagr
    share = float((alpha > 0).mean())
    median = float(alpha.median())
    robust = median > 0 and share >= 0.75
    report = {
        "status": "PASS", "parent_stage": parent["manifest_sha256"],
        "test": "N3-SR45-corrected-environment", "invalidates_conclusions_from": ["N3-01", "N3-02"],
        "root_cause": "N3-01/N3-02 omitted universe sector/cap/name maps before backtest",
        "n2_stage06_parity": {"status": "PASS", "actual": {k: actual_parity[k] for k in keys},
                              "expected": expected_parity, "map_counts": map_counts},
        "common_window": {"start": str(common_start.date()), "end": str(common_dates[-1].date()),
                          "weeks": len(common_dates)},
        "benchmark_metrics": benchmark,
        "alpha_distribution": {"median": median, "p10": float(alpha.quantile(.10)),
            "worst": float(alpha.min()), "best": float(alpha.max()),
            "share_phases_beating_index": share},
        "robustness_gate": "PASS" if robust else "FAIL", "phase_selection_allowed": False,
        "holdout_used": False, "production": False, "multiple_testing_arms": 52,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("03_calendar52_phase_corrected", [OUT, CSV, Path(__file__).resolve()],
        {"test": "N3-SR45-corrected", "robustness_gate": report["robustness_gate"],
         "prior_n3_01_n3_02_conclusions": "INVALID_ENVIRONMENT", "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False)); print(stage)


if __name__ == "__main__":
    main()
