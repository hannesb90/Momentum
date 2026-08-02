"""Leakage-safe report-improvement gap audit using fresh feature caches."""
from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from tune_earnings_reaction_gap import _load_report_events


def expanding_percentile(values: pd.Series, min_history: int = 30) -> pd.Series:
    """Rank each observation against strictly earlier observations."""
    seen: list[float] = []
    result = []
    for value in values:
        if pd.isna(value) or len(seen) < min_history:
            result.append(np.nan)
        else:
            result.append(bisect.bisect_right(seen, float(value)) / len(seen))
        if pd.notna(value):
            bisect.insort(seen, float(value))
    return pd.Series(result, index=values.index)


def feature_events(cache_path: Path, segment: str) -> pd.DataFrame:
    cache = joblib.load(cache_path)
    fundamentals = _load_report_events(segment).sort_values("published")
    rows = []
    for event in fundamentals.itertuples(index=False):
        frame = cache.get(event.ticker)
        if frame is None:
            continue
        pos = frame.index.searchsorted(pd.Timestamp(event.published), side="left")
        if pos >= len(frame):
            continue
        row = frame.iloc[pos]
        rows.append({
            "ticker": event.ticker, "published": event.published,
            "Date": frame.index[pos], "margin_delta": event.margin_delta,
            "eps_delta": event.eps_delta,
            "reaction": row.get("report_reaction_abn"),
            "target_return": row.get("target_return"),
        })
    out = pd.DataFrame(rows).sort_values(["published", "ticker"]).reset_index(drop=True)
    for col in ("margin_delta", "eps_delta"):
        out[f"{col}_rank"] = expanding_percentile(out[col])
    out["reaction_mag_rank"] = expanding_percentile(out.reaction.abs())
    out["fund_score"] = out[[
        "margin_delta_rank", "eps_delta_rank"]].mean(axis=1)
    out["gap_score"] = out.fund_score - out.reaction_mag_rank
    return out


def metrics(frame: pd.DataFrame, score: str, start: str, end: str | None) -> dict:
    x = frame[frame.published >= start]
    if end:
        x = x[x.published <= end]
    x = x.dropna(subset=[score, "target_return"])
    if len(x) < 20:
        return {"n": len(x), "ic": None, "spread": None}
    q20, q80 = x[score].quantile([.2, .8])
    return {
        "n": len(x),
        "ic": float(spearmanr(x[score], x.target_return).statistic),
        "spread": float(
            x.loc[x[score] >= q80, "target_return"].mean()
            - x.loc[x[score] <= q20, "target_return"].mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--segment", choices=["large", "small"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    events = feature_events(args.cache, args.segment)
    result = {"segment": args.segment}
    for score in ("fund_score", "gap_score"):
        result[score] = {
            "pre2024": metrics(events, score, "2010-01-01", "2023-12-31"),
            "modern": metrics(events, score, "2024-01-01", None),
        }
    result["gap_promotable"] = bool(
        result["gap_score"]["pre2024"]["ic"] is not None
        and result["gap_score"]["pre2024"]["ic"] > 0
        and result["gap_score"]["pre2024"]["spread"] > 0
        and result["gap_score"]["modern"]["ic"] >= .03
        and result["gap_score"]["modern"]["spread"] > 0
        and result["gap_score"]["modern"]["ic"]
        > result["fund_score"]["modern"]["ic"])
    events.to_csv(args.out / f"{args.segment}_events.csv", index=False)
    (args.out / f"{args.segment}_summary.json").write_text(
        json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
