"""Refresh Small/Micro 13-week features and run the isolated shadow model."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import joblib
import numpy as np

import config
from data.data_loader import (
    fetch_weekly_data,
    filter_active_universe,
    filter_liquid_universe,
    load_sweden_universe,
)
from features.feature_engineering import (
    attach_categorical_features,
    build_all_features,
)
import small13_shadow_challenger


HOME = Path("/opt/momentum/momentum_ml")


def atomic_joblib(value, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, tmp)
    os.replace(tmp, path)


def refresh(snapshot: Path, out_dir: Path) -> None:
    segment = config.SEGMENTS["small"]
    config.FORWARD_WEEKS = 13
    config.REBALANCE_WEEKS = 13
    config.EMBARGO_WEEKS = 13
    config.RESULTS_DIR = str(out_dir)

    tickers, sector_map, cap_map, name_map = load_sweden_universe(
        min_market_cap=segment["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_map)
    config.NAME_MAP.update(name_map)

    data = fetch_weekly_data(
        tickers, start=config.START_DATE, end=config.END_DATE, use_cache=True)
    data = filter_active_universe(data, max_stale_weeks=4)
    data = filter_liquid_universe(
        data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    features = build_all_features(data)
    features = attach_categorical_features(
        features, sector_map=config.SECTOR_MAP, cap_tier_map=cap_map)

    # Small/Micro saknar ännu point-in-time-rapporttäckning. Shadowmodellen
    # behandlar den femte signalen neutralt; skapa kolumnen explicit så
    # snapshotens schema är stabilt tills täckningen finns.
    for frame in features.values():
        if "report_reaction_abn" not in frame:
            frame["report_reaction_abn"] = np.nan

    gaps = {
        len(frame.loc[frame.target_return.last_valid_index():]) - 1
        for frame in features.values()
        if frame.target_return.last_valid_index() is not None
    }
    if gaps != {13}:
        raise ValueError(f"Vägrar skriva snapshot: targetgap={sorted(gaps)}")

    atomic_joblib(features, snapshot)
    os.environ["MOMENTUM_SMALL13_CACHE"] = str(snapshot)
    small13_shadow_challenger.run(out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot", type=Path,
        default=HOME / "results/small13_challenger/features_latest.pkl")
    parser.add_argument(
        "--out-dir", type=Path,
        default=HOME / "results/small13_challenger")
    args = parser.parse_args()
    refresh(args.snapshot, args.out_dir)
