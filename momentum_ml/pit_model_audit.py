"""Measure how much existing model history can be retested with the PIT layer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


HOME = Path("/opt/momentum/momentum_ml")


def audit(signals: pd.DataFrame, intervals: pd.DataFrame,
          coverage: pd.DataFrame) -> dict:
    signals = signals.copy()
    signals["Date"] = pd.to_datetime(signals.Date)
    intervals = intervals.copy()
    intervals["valid_from"] = pd.to_datetime(intervals.valid_from)
    intervals["valid_to"] = pd.to_datetime(intervals.valid_to)
    conflicts = set(coverage.loc[
        coverage.ticker_reuse_conflict.astype(str).str.lower().isin(
            ["true", "1"]), "ticker"])
    safe = intervals[~intervals.ticker.isin(conflicts)]
    merged = signals.merge(
        safe[["ticker", "valid_from", "valid_to"]], on="ticker", how="left")
    in_window = (
        merged.valid_from.notna()
        & (merged.Date >= merged.valid_from)
        & (merged.valid_to.isna() | (merged.Date <= merged.valid_to)))
    matched = merged.valid_from.notna()
    selected = pd.to_numeric(merged.pred_signal, errors="coerce").eq(1)
    dead = set(coverage.loc[coverage.status.eq("avnoterad"), "ticker"])
    priced = set(coverage.loc[
        coverage.has_cached_price.astype(str).str.lower().isin(["true", "1"])
        & coverage.price_overlaps_lifecycle.astype(str).str.lower().isin(
            ["true", "1"]), "ticker"])
    safe_dead = (dead - conflicts) & priced
    dead_selected = merged[
        selected & in_window & merged.ticker.isin(safe_dead)]
    return {
        "signal_rows": len(signals),
        "signal_tickers": int(signals.ticker.nunique()),
        "pit_matched_rows": int(matched.sum()),
        "pit_matched_tickers": int(merged.loc[matched, "ticker"].nunique()),
        "rows_outside_valid_window": int((matched & ~in_window).sum()),
        "selected_rows_outside_valid_window": int(
            (matched & ~in_window & selected).sum()),
        "safe_delisted_selected_rows": len(dead_selected),
        "safe_delisted_selected_tickers": int(dead_selected.ticker.nunique()),
        "ticker_reuse_conflicts": sorted(conflicts & set(signals.ticker)),
        "performance_retest_possible": bool(len(dead_selected)),
        "interpretation": (
            "No model selections exist for safely matched delisted price series."
            if dead_selected.empty else
            "A partial delisted-series performance retest is possible."),
    }


def run(out: Path) -> dict:
    intervals = pd.read_csv(
        HOME / "results/point_in_time/historical_universe_intervals.csv")
    coverage = pd.read_csv(HOME / "results/point_in_time/pit_coverage.csv")
    result = {}
    for segment, path in {
        "large": HOME / "results/signals.csv",
        "small": HOME / "results/small/signals.csv",
    }.items():
        result[segment] = audit(pd.read_csv(path), intervals, coverage)
    result["conclusion"] = (
        "PIT filters can audit eligibility now, but cannot estimate corrected "
        "alpha until missing delisted price series are supplied.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path,
        default=HOME / "results/point_in_time/model_pit_audit.json")
    args = parser.parse_args()
    print(json.dumps(run(args.out), ensure_ascii=False, indent=2))
