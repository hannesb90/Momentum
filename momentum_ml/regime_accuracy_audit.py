"""Causal OOS audit of Momentum's bull/sideways/bear classifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def market_data(cache_path: Path) -> tuple[pd.Series, pd.DataFrame]:
    cache = joblib.load(cache_path)
    return_series = {
        ticker: pd.to_numeric(frame["ret_1w"], errors="coerce")
        for ticker, frame in cache.items()
        if "ret_1w" in frame and ticker.endswith(".ST")
    }
    if return_series:
        returns = pd.DataFrame(return_series).sort_index()
    else:
        closes = pd.DataFrame({
            ticker: frame["Close"] for ticker, frame in cache.items()
            if "Close" in frame and ticker.endswith(".ST")
        }).sort_index()
        returns = closes.pct_change(fill_method=None)
    if returns.empty:
        raise ValueError("Cachen saknar både ret_1w och Close för svenska aktier.")
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod()
    breadth = (returns > 0).mean(axis=1)
    return proxy, breadth


def classify(proxy: pd.Series, breadth: pd.Series, sma_weeks: int,
             slope_weeks: int, buffer: float, breadth_gate: float) -> pd.Series:
    sma = proxy.rolling(sma_weeks).mean()
    slope = sma.pct_change(slope_weeks)
    distance = proxy / sma - 1
    breadth_smooth = breadth.rolling(4).mean()
    regime = pd.Series("sideways", index=proxy.index, dtype=object)
    regime[(distance > buffer) & (slope > 0) &
           (breadth_smooth >= breadth_gate)] = "bull"
    regime[(distance < -buffer) & (slope < 0) &
           (breadth_smooth <= 1 - breadth_gate)] = "bear"
    regime[sma.isna() | slope.isna()] = np.nan
    return regime


def metrics(proxy: pd.Series, regime: pd.Series, start: str, end: str | None) -> dict:
    frame = pd.DataFrame({"regime": regime})
    for horizon in (4, 13):
        frame[f"fwd_{horizon}w"] = proxy.shift(-horizon) / proxy - 1
    frame = frame.loc[start:end].dropna()
    active = frame[frame.regime.isin(["bull", "bear"])]
    result = {"weeks": len(frame), "active_share": len(active) / len(frame)}
    for horizon in (4, 13):
        fwd = active[f"fwd_{horizon}w"]
        predicted_up = active.regime.eq("bull")
        actual_up = fwd.gt(0)
        result[f"accuracy_{horizon}w"] = float((predicted_up == actual_up).mean())
        result[f"bull_mean_{horizon}w"] = float(
            active.loc[predicted_up, f"fwd_{horizon}w"].mean())
        result[f"bear_mean_{horizon}w"] = float(
            active.loc[~predicted_up, f"fwd_{horizon}w"].mean())
        result[f"separation_{horizon}w"] = (
            result[f"bull_mean_{horizon}w"] - result[f"bear_mean_{horizon}w"])
    changes = frame.regime.ne(frame.regime.shift()).sum()
    result["changes_per_year"] = float(changes / len(frame) * 52)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/challenger/features_latest.pkl"))
    parser.add_argument(
        "--out", type=Path,
        default=Path("/opt/momentum/momentum_ml/results/regime_accuracy"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    proxy, breadth = market_data(args.cache)
    rows = []
    for sma in (8, 13, 17, 26):
        for slope in (1, 2, 4):
            for buffer in (0.0, 0.01, 0.02):
                for breadth_gate in (0.0, 0.50, 0.55):
                    reg = classify(proxy, breadth, sma, slope, buffer, breadth_gate)
                    pre = metrics(proxy, reg, "2010-01-01", "2023-12-31")
                    modern = metrics(proxy, reg, "2024-01-01", None)
                    rows.append({
                        "sma": sma, "slope": slope, "buffer": buffer,
                        "breadth_gate": breadth_gate,
                        **{f"pre_{k}": v for k, v in pre.items()},
                        **{f"modern_{k}": v for k, v in modern.items()},
                    })
    grid = pd.DataFrame(rows)
    # Select only on pre-2024. Reward both horizons and useful separation,
    # penalise excessive flipping; the modern period remains untouched.
    grid["pre_score"] = (
        grid.pre_accuracy_4w + grid.pre_accuracy_13w
        + 2 * grid.pre_separation_13w
        - 0.002 * grid.pre_changes_per_year
    )
    selected = grid.sort_values("pre_score", ascending=False).iloc[0]
    current = grid[
        (grid.sma == 13) & (grid.slope == 1) &
        (grid.buffer == 0) & (grid.breadth_gate == 0)
    ].iloc[0]
    grid.to_csv(args.out / "grid.csv", index=False)
    summary = {
        "selection_rule": "pre-2024 only",
        "current": current.to_dict(),
        "selected": selected.to_dict(),
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
