"""Forward-only alpha scorecard for the Avanza ETF-flow signal."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def evaluate(frame: pd.DataFrame, horizon_obs: int = 20) -> dict:
    frame = frame.sort_values(["ticker", "snapshot_date"]).copy()
    frame["forward_return"] = (
        frame.groupby("ticker")["last"].shift(-horizon_obs) / frame["last"] - 1)
    matured = frame.dropna(subset=["flow_score", "forward_return"])
    dates = []
    for date, group in matured.groupby("snapshot_date"):
        if len(group) < 12:
            continue
        top_cut = group.flow_score.quantile(.75)
        top = group[group.flow_score >= top_cut].forward_return.mean()
        benchmark = group.forward_return.mean()
        dates.append({"snapshot_date": date, "top_return": top,
                      "benchmark_return": benchmark, "spread": top - benchmark})
    weekly = pd.DataFrame(dates)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if weekly.empty else "measuring",
        "horizon_observations": horizon_obs,
        "snapshot_dates": int(frame.snapshot_date.nunique()),
        "matured_dates": int(len(weekly)),
    }
    if not weekly.empty:
        out["forward_metrics"] = {
            "mean_top_return": float(weekly.top_return.mean()),
            "mean_benchmark_return": float(weekly.benchmark_return.mean()),
            "mean_spread": float(weekly.spread.mean()),
            "positive_spread_share": float((weekly.spread > 0).mean()),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--snapshots", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/etf_flow/etf_flow_snapshots.csv"))
    ap.add_argument(
        "--out", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/etf_flow/challenger_scorecard.json"))
    args = ap.parse_args()
    frame = pd.read_csv(args.snapshots, parse_dates=["snapshot_date"])
    card = evaluate(frame)
    tmp = args.out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    tmp.replace(args.out)
    print(json.dumps(card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
