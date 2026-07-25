"""Forward-only alpha scorecard for analyst target-price revisions."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def evaluate(frame: pd.DataFrame, horizon_obs: int = 13) -> dict:
    frame = (frame.sort_values(["ticker", "date"])
             .drop_duplicates(["ticker", "date"], keep="last").copy())
    frame["target_revision"] = frame.groupby("ticker").target_mean.pct_change(
        fill_method=None)
    frame["forward_return"] = (
        frame.groupby("ticker").price_now.shift(-horizon_obs)
        / frame.price_now - 1)
    matured = frame.dropna(subset=["target_revision", "forward_return"])
    rows = []
    for date, group in matured.groupby("date"):
        if len(group) < 20:
            continue
        cut = group.target_revision.quantile(.75)
        top = group[group.target_revision >= cut].forward_return.mean()
        benchmark = group.forward_return.mean()
        rows.append({"date": date, "spread": top - benchmark})
    dates = pd.DataFrame(rows)
    card = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if dates.empty else "measuring",
        "horizon_observations": horizon_obs,
        "snapshot_dates": int(frame.date.nunique()),
        "matured_dates": int(len(dates)),
    }
    if not dates.empty:
        card["forward_metrics"] = {
            "mean_spread": float(dates.spread.mean()),
            "positive_spread_share": float((dates.spread > 0).mean()),
        }
    return card


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--large", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/public_target_price.csv"))
    ap.add_argument(
        "--small", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/small/public_target_price.csv"))
    ap.add_argument(
        "--out", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/target_revision_scorecard.json"))
    args = ap.parse_args()
    frame = pd.concat([
        pd.read_csv(args.large, parse_dates=["date"]),
        pd.read_csv(args.small, parse_dates=["date"]),
    ], ignore_index=True)
    card = evaluate(frame)
    tmp = args.out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    tmp.replace(args.out)
    print(json.dumps(card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
