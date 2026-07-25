"""Forward-only promotion readiness for Large, Small13 and ETF research."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


HOME = Path("/opt/momentum/momentum_ml")


def challenger_gate(path: Path, min_matured: int = 8) -> dict:
    if not path.exists():
        return {"ready": False, "reason": "scorecard_missing"}
    card = json.loads(path.read_text())
    matured = int(card.get("matured_prediction_dates", 0))
    metrics = card.get("forward_metrics") or {}
    ic = metrics.get("mean_ic")
    spread = (
        metrics.get("mean_top10_spread")
        if "mean_top10_spread" in metrics
        else metrics.get("mean_top20_spread"))
    checks = {
        "matured_dates": matured >= min_matured,
        "positive_ic": ic is not None and ic > 0,
        "positive_top_spread": spread is not None and spread > 0,
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "matured_prediction_dates": matured,
        "required_matured_dates": min_matured,
        "mean_ic": ic, "mean_top_spread": spread,
    }


def etf_gate(path: Path) -> dict:
    if not path.exists():
        return {"ready": False, "reason": "snapshots_missing"}
    frame = pd.read_csv(path, parse_dates=["snapshot_date"])
    dates = sorted(frame.snapshot_date.dropna().unique())
    weeks = (
        (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 7
        if len(dates) >= 2 else 0.0)
    latest = frame[frame.snapshot_date == max(dates)] if dates else frame.iloc[0:0]
    owner_coverage = (
        float(latest.owner_change_1d.notna().mean())
        if not latest.empty and "owner_change_1d" in latest else 0.0)
    checks = {
        "at_least_8_weeks": weeks >= 8,
        "at_least_8_snapshots": len(dates) >= 8,
        "owner_change_coverage_70pct": owner_coverage >= .70,
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "calendar_weeks": weeks, "snapshot_dates": len(dates),
        "latest_instruments": len(latest),
        "owner_change_coverage": owner_coverage,
        "note": "Ready means enough data to test an ETF-flow model, not promotion.",
    }


def build() -> dict:
    large = challenger_gate(
        HOME / "results/challenger/challenger_scorecard.json")
    small = challenger_gate(
        HOME / "results/small13_challenger/challenger_scorecard.json")
    etf = etf_gate(
        HOME / "results/etf_flow/etf_flow_snapshots.csv")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "large13": large, "small13": small, "etf_flow": etf,
        "equity_candidates_ready": large["ready"] and small["ready"],
        # Deliberately never auto-promote money-affecting behavior.
        "production_change_authorized": False,
        "next_action": (
            "manual_production_review"
            if large["ready"] and small["ready"]
            else "continue_forward_collection"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path,
        default=HOME / "results/shadow_readiness.json")
    args = parser.parse_args()
    result = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    tmp.replace(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
