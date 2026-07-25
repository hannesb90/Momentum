"""Forward-only promotion readiness for Large, Small13 and ETF research."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


HOME = Path("/opt/momentum/momentum_ml")


def challenger_gate(path: Path, min_matured: int = 13) -> dict:
    if not path.exists():
        return {"ready": False, "reason": "scorecard_missing"}
    card = json.loads(path.read_text())
    matured = int(card.get("matured_prediction_dates", 0))
    metrics = card.get("forward_metrics") or {}
    ic = metrics.get("mean_ic")
    positive_ic_share = metrics.get("positive_ic_share")
    spread = (
        metrics.get("mean_top10_spread")
        if "mean_top10_spread" in metrics
        else metrics.get("mean_top20_spread"))
    checks = {
        "matured_dates": matured >= min_matured,
        "positive_ic": ic is not None and ic > 0,
        "ic_consistency_55pct": (
            positive_ic_share is not None and positive_ic_share >= .55),
        "positive_top_spread": spread is not None and spread > 0,
        "spread_consistency_55pct": (
            metrics.get("positive_top_spread_share") is not None
            and metrics["positive_top_spread_share"] >= .55),
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "matured_prediction_dates": matured,
        "required_matured_dates": min_matured,
        "mean_ic": ic, "positive_ic_share": positive_ic_share,
        "mean_top_spread": spread,
        "positive_top_spread_share": metrics.get(
            "positive_top_spread_share"),
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
        "at_least_13_weeks": weeks >= 13,
        "at_least_40_snapshots": len(dates) >= 40,
        "owner_change_coverage_70pct": owner_coverage >= .70,
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "calendar_weeks": weeks, "snapshot_dates": len(dates),
        "latest_instruments": len(latest),
        "owner_change_coverage": owner_coverage,
        "note": "Ready means enough data to test an ETF-flow model, not promotion.",
    }


def forward_signal_gate(path: Path, min_matured: int = 13) -> dict:
    if not path.exists():
        return {"ready": False, "reason": "scorecard_missing"}
    card = json.loads(path.read_text())
    matured = int(card.get("matured_dates", 0))
    metrics = card.get("forward_metrics") or {}
    spread = metrics.get("mean_spread")
    consistency = metrics.get("positive_spread_share")
    checks = {
        "matured_dates": matured >= min_matured,
        "positive_spread": spread is not None and spread > 0,
        "spread_consistency_55pct": (
            consistency is not None and consistency >= .55),
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "matured_dates": matured, "required_matured_dates": min_matured,
        "mean_spread": spread, "positive_spread_share": consistency,
    }


def conditional_shadow_gate(path: Path, min_matured: int = 13) -> dict:
    if not path.exists():
        return {"ready": False, "reason": "scorecard_missing"}
    card = json.loads(path.read_text())
    matured = int(card.get("matured_dates", 0))
    metrics = card.get("forward_metrics") or {}
    checks = {
        "matured_dates": matured >= min_matured,
        "positive_alpha_vs_base": metrics.get("mean_alpha_vs_base", 0) > 0,
        "base_consistency_55pct": (
            metrics.get("positive_alpha_vs_base_share", 0) >= .55),
        "positive_alpha_vs_production": (
            metrics.get("mean_alpha_vs_production", 0) > 0),
        "production_consistency_55pct": (
            metrics.get("positive_alpha_vs_production_share", 0) >= .55),
        "positive_alpha_vs_index": metrics.get("mean_alpha_vs_index", 0) > 0,
        "index_consistency_55pct": (
            metrics.get("positive_alpha_vs_index_share", 0) >= .55),
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "matured_dates": matured, "required_matured_dates": min_matured,
        "production_change_authorized": False,
    }
def regime_gate(path: Path) -> dict:
    if not path.exists():
        return {"forecast_approved": False, "reason": "audit_missing"}
    audit = json.loads(path.read_text())
    current = audit.get("current") or {}
    checks = {
        "accuracy_4w_55pct": current.get("modern_accuracy_4w", 0) >= .55,
        "accuracy_13w_55pct": current.get("modern_accuracy_13w", 0) >= .55,
        "positive_4w_separation": (
            current.get("modern_separation_4w", 0) > 0),
        "positive_13w_separation": (
            current.get("modern_separation_13w", 0) > 0),
    }
    return {
        "forecast_approved": all(checks.values()),
        "checks": checks,
        "modern_accuracy_4w": current.get("modern_accuracy_4w"),
        "modern_accuracy_13w": current.get("modern_accuracy_13w"),
        "modern_separation_4w": current.get("modern_separation_4w"),
        "modern_separation_13w": current.get("modern_separation_13w"),
        "note": (
            "Regime labels remain descriptive unless every predictive "
            "accuracy check passes."),
    }


def build() -> dict:
    large = challenger_gate(
        HOME / "results/challenger/challenger_scorecard.json")
    small = challenger_gate(
        HOME / "results/small13_challenger/challenger_scorecard.json")
    etf = etf_gate(
        HOME / "results/etf_flow/etf_flow_snapshots.csv")
    etf_alpha = forward_signal_gate(
        HOME / "results/etf_flow/challenger_scorecard.json")
    target_revisions = forward_signal_gate(
        HOME / "results/target_revision_scorecard.json")
    regime = regime_gate(
        HOME / "results/regime_accuracy/summary.json")
    conditional = conditional_shadow_gate(
        HOME / "results/challenger/conditional_shadow_scorecard.json")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "large13": large, "small13": small, "etf_flow": etf,
        "etf_flow_alpha": etf_alpha,
        "target_revision_alpha": target_revisions,
        "market_regime": regime,
        "large_conditional_shadow": conditional,
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
