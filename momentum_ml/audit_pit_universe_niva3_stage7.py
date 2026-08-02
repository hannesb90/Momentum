"""N3 stage 07 / SR48: PIT listing, delisting and survivorship audit.

The tested portfolio is the last approved N3 architecture (frozen N2 Stage-06
signals), not the failed seed-consensus challenger.  Known lifecycle-window
violations are filtered and re-backtested.  Missing, never-scored delisted
securities are reported as non-identifiable rather than assigned invented
returns or ranks.
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
PARENT = ROOT / "results/niva3_stages/06_seed_consensus_remediation.json"
SIGNALS = ROOT / "results/niva2_stage6_winner_signals.csv"
INTERVALS = ROOT / "results/point_in_time/historical_universe_intervals.csv"
COVERAGE = ROOT / "results/point_in_time/pit_coverage.csv"
EODHD = ROOT / "results/point_in_time/eodhd_delisted_coverage.csv"
N2_REPORT = ROOT / "results/retraining_staleness_niva2.json"
OUT = ROOT / "results/niva3_pit_universe_audit.json"
VIOLATIONS = ROOT / "results/niva3_pit_selected_violations.csv"
TICKERS = ROOT / "results/niva3_pit_ticker_coverage.csv"


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _validity(signals: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    """One row per signal row; valid if any lifecycle interval contains Date."""
    x = signals.reset_index(drop=False).copy()
    x["_row"] = np.arange(len(x))
    iv = intervals[["ticker", "valid_from", "valid_to"]].copy()
    iv["valid_from"] = pd.to_datetime(iv.valid_from, errors="coerce")
    iv["valid_to"] = pd.to_datetime(iv.valid_to, errors="coerce")
    merged = x[["_row", "Date", "ticker"]].merge(iv, on="ticker", how="left")
    merged["matched"] = merged.valid_from.notna() | merged.valid_to.notna()
    merged["inside"] = merged.matched & (
        (merged.valid_from.isna() | merged.Date.ge(merged.valid_from))
        & (merged.valid_to.isna() | merged.Date.le(merged.valid_to)))
    agg = merged.groupby("_row").agg(pit_matched=("matched", "max"), pit_valid=("inside", "max"))
    return x.merge(agg, left_on="_row", right_index=True, how="left").sort_values("_row")


def _cagr(values: pd.Series) -> float:
    values = values.dropna().astype(float)
    years = (values.index[-1] - values.index[0]).days / 365.25
    return float((values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1)


def main():
    parent = verify_manifest(PARENT)
    signals = pd.read_csv(SIGNALS, parse_dates=["Date"]).set_index("Date").sort_index()
    intervals = pd.read_csv(INTERVALS)
    coverage = pd.read_csv(COVERAGE)
    eodhd = pd.read_csv(EODHD)
    _, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS = 52

    baseline_bt = NoCorrelationBacktester(signals, prices); baseline_bt.run()
    baseline_stats = baseline_bt.statistics()
    expected = json.loads(N2_REPORT.read_text())["retrain_13w_parity"]
    mismatch = {k: (baseline_stats[k], expected[k]) for k in expected if baseline_stats[k] != expected[k]}
    if mismatch:
        raise RuntimeError(f"Stage-06 baseline parity failed: {mismatch}")

    audit = _validity(signals, intervals)
    selected = audit.pred_signal.eq(1)
    known_invalid = audit.pit_matched & ~audit.pit_valid
    selected_invalid = selected & known_invalid
    violations = audit.loc[selected_invalid].drop(columns=["_row"])
    violations.to_csv(VIOLATIONS, index=False)

    corrected = signals.copy()
    invalid_rows = audit.loc[selected_invalid, "_row"].to_numpy(dtype=int)
    corrected.iloc[invalid_rows, corrected.columns.get_loc("pred_signal")] = 0
    corrected.iloc[invalid_rows, corrected.columns.get_loc("position_size")] = 0.0
    corrected_bt = NoCorrelationBacktester(corrected, prices); corrected_bt.run()
    corrected_stats = corrected_bt.statistics()

    dates = signals.index.unique().sort_values()
    benchmark_close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().dropna()
    benchmark_cagr = _cagr(benchmark_close)
    coverage["eodhd_status"] = coverage.ticker.map(eodhd.set_index("ticker").status)
    coverage["eodhd_complete"] = coverage.ticker.map(
        eodhd.set_index("ticker").complete_from_listing).fillna(False).astype(bool)
    in_model = set(signals.ticker)
    coverage["in_model_signal_panel"] = coverage.ticker.isin(in_model)
    coverage.to_csv(TICKERS, index=False)

    dead = coverage.status.eq("avnoterad")
    absent_dead = dead & ~coverage.in_model_signal_panel
    complete_dead = dead & coverage.eodhd_complete
    matched_rows = int(audit.pit_matched.sum())
    selected_rows = int(selected.sum())
    known_alpha = _pct(corrected_stats["CAGR"]) - benchmark_cagr
    full_identifiable = bool((~absent_dead).all())
    gate = bool(full_identifiable and selected_invalid.sum() == 0)
    report = {
        "status": "PASS", "parent_stage": parent["manifest_sha256"], "test": "N3-SR48",
        "tested_candidate": "n3_approved_architecture_seed42_not_consensus",
        "baseline_parity": {k: baseline_stats[k] for k in expected},
        "signal_rows": len(signals), "signal_tickers": int(signals.ticker.nunique()),
        "pit_matched_rows": matched_rows, "pit_matched_row_share": matched_rows / len(signals),
        "pit_matched_tickers": int(audit.loc[audit.pit_matched, "ticker"].nunique()),
        "selected_rows": selected_rows, "selected_known_outside_lifecycle": int(selected_invalid.sum()),
        "selected_violation_tickers": sorted(violations.ticker.unique().tolist()),
        "known_window_filter_backtest": {
            "baseline": {"CAGR": baseline_stats["CAGR"], "Sharpe": baseline_stats["Sharpe"],
                         "Max Drawdown": baseline_stats["Max Drawdown"]},
            "corrected": {"CAGR": corrected_stats["CAGR"], "Sharpe": corrected_stats["Sharpe"],
                          "Max Drawdown": corrected_stats["Max Drawdown"]},
            "benchmark_cagr": benchmark_cagr, "known_violation_adjusted_alpha": known_alpha,
        },
        "delisted_facts": int(dead.sum()), "delisted_absent_from_model_panel": int(absent_dead.sum()),
        "eodhd_complete_delisted_series": int(complete_dead.sum()),
        "historical_large_cap_eligibility_available": False,
        "full_survivorship_lower_bound_alpha": None,
        "full_lower_bound_identifiable": False,
        "non_identifiability_reason": "Absent delisted securities were never featured/scored and historical Large-cap eligibility is unavailable; assigning ranks or returns would fabricate alpha.",
        "survivorship_gate": "PASS" if gate else "FAIL",
        "production": False, "holdout_used": False,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("07_pit_universe_delisting_audit", [OUT, VIOLATIONS, TICKERS, Path(__file__).resolve()],
        {"test": "N3-SR48", "survivorship_gate": report["survivorship_gate"],
         "full_lower_bound_identifiable": False, "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


def _pct(value: str) -> float:
    return float(str(value).replace("%", "")) / 100.0


if __name__ == "__main__":
    main()
