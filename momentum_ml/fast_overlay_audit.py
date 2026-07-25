"""Point-in-time screen for fast entry overlays on the rank challengers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

RAW = ["mom_12_1", "mom_tstat_26w", "resid_mom", "atr_norm",
       "report_reaction_abn"]
DIRECTION = [1, 1, 1, -1, 1]
FAST = ["roc_accel_4w", "roc_4w", "price_vs_sma52", "ema_cross_8_21",
        "vol_ratio_4w"]


def panel(cache_path: Path, universe_path: Path, segment: str) -> pd.DataFrame:
    cache = joblib.load(cache_path)
    universe = pd.read_csv(universe_path)
    caps = (["Large Cap", "Mid Cap"] if segment == "large"
            else ["Small Cap", "Micro Cap"])
    allowed = set(universe.loc[
        universe.market_cap_category.isin(caps), "ticker"])
    frames = []
    needed = RAW + FAST + ["target_return"]
    for ticker, frame in cache.items():
        if ticker not in allowed or any(c not in frame for c in needed):
            continue
        x = frame[needed].copy()
        x["Date"] = pd.to_datetime(x.index)
        x["ticker"] = ticker
        frames.append(x.reset_index(drop=True))
    out = pd.concat(frames, ignore_index=True)
    for col, direction in zip(RAW, DIRECTION):
        rank = out[col].groupby(out.Date).rank(pct=True)
        out[f"r_{col}"] = ((1 - rank) if direction < 0 else rank).fillna(.5)
    for col in FAST:
        out[f"r_{col}"] = out[col].groupby(out.Date).rank(pct=True).fillna(.5)
    out["base"] = out[[f"r_{c}" for c in RAW]].mean(axis=1)
    return out


def evaluate(frame: pd.DataFrame, score: pd.Series, top_n: int,
             start: str, end: str | None) -> dict:
    x = frame.assign(score=score)
    x = x[(x.Date >= start) & (x.Date <= end if end else True)]
    x = x.dropna(subset=["target_return"])
    selected = x[x.groupby("Date").score.rank(ascending=False, method="first")
                 <= top_n]
    weekly = selected.groupby("Date").target_return.mean()
    ics = x.groupby("Date").apply(
        lambda g: spearmanr(g.score, g.target_return).statistic,
        include_groups=False)
    return {
        "dates": int(weekly.size),
        "mean_top_return": float(weekly.mean()),
        "mean_ic": float(ics.mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--universe", type=Path, required=True)
    ap.add_argument("--segment", choices=["large", "small"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    data = panel(args.cache, args.universe, args.segment)
    top_n = 10 if args.segment == "large" else 20
    rows = []
    candidates = [("base", None, 0.0)]
    for feature in FAST:
        for weight in (-.20, -.10, .10, .20):
            candidates.append((f"{feature}_{weight:+.2f}", feature, weight))
    for name, feature, weight in candidates:
        score = data.base if feature is None else (
            data.base + weight * (data[f"r_{feature}"] - .5))
        pre = evaluate(data, score, top_n, "2016-01-01", "2023-12-31")
        modern = evaluate(data, score, top_n, "2024-01-01", None)
        rows.append({"candidate": name, "feature": feature, "weight": weight,
                     **{f"pre_{k}": v for k, v in pre.items()},
                     **{f"modern_{k}": v for k, v in modern.items()}})
    grid = pd.DataFrame(rows)
    base = grid.iloc[0]
    # Candidate must improve both pre-period top return and IC. Select on pre only.
    eligible = grid[
        (grid.pre_mean_top_return > base.pre_mean_top_return) &
        (grid.pre_mean_ic > base.pre_mean_ic)]
    chosen = (eligible.sort_values(
        ["pre_mean_top_return", "pre_mean_ic"], ascending=False).iloc[0]
        if not eligible.empty else base)
    grid.to_csv(args.out / f"{args.segment}_grid.csv", index=False)
    summary = {"segment": args.segment, "base": base.to_dict(),
               "selected_pre2024": chosen.to_dict()}
    (args.out / f"{args.segment}_summary.json").write_text(
        json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
