"""Refresh Large/Mid 13-week features and run the isolated rank6 shadow."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import joblib

import config
from data.data_loader import (
    fetch_weekly_data,
    filter_active_universe,
    filter_liquid_universe,
    load_sweden_universe,
)
from features.feature_engineering import (
    attach_categorical_features,
    attach_fundamentals_features,
    build_all_features,
)
import shadow_challenger
import conditional_shadow


HOME = Path("/opt/momentum/momentum_ml")


def atomic_joblib(value, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, tmp)
    os.replace(tmp, path)


def refresh(snapshot: Path, out_dir: Path) -> None:
    segment = config.SEGMENTS["large"]
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
    features = attach_fundamentals_features(
        features, segment="large", prices=data)
    # The conditional shadow needs causal price history for its already
    # validated holder trend rule.  Production feature consumers ignore it.
    for ticker, frame in features.items():
        frame["Close"] = data[ticker]["Close"].reindex(frame.index)
    gaps = {
        len(frame.loc[frame.target_return.last_valid_index():]) - 1
        for frame in features.values()
        if frame.target_return.last_valid_index() is not None
    }
    if gaps != {13}:
        raise ValueError(f"Vägrar skriva snapshot: targetgap={sorted(gaps)}")
    atomic_joblib(features, snapshot)
    os.environ["MOMENTUM_LARGE13_CACHE"] = str(snapshot)
    panel, _ = shadow_challenger.load_panel()
    model, model_meta = shadow_challenger.train(panel)
    signals = shadow_challenger.current_signals(panel, model)
    shadow_challenger.atomic_csv(signals, out_dir / "signals_challenger.csv")
    joblib.dump({"model": model, "meta": model_meta},
                out_dir / "challenger_model.pkl")
    ledger = shadow_challenger.update_ledger(
        signals, panel, out_dir / "challenger_ledger.csv")
    shadow_challenger.atomic_csv(
        ledger, out_dir / "challenger_ledger.csv")
    card = shadow_challenger.scorecard(ledger, model_meta, snapshot)
    shadow_challenger.atomic_json(
        card, out_dir / "challenger_scorecard.json")
    conditional_shadow.run(out_dir, panel, model, signals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot", type=Path,
        default=HOME / "results/challenger/features_latest.pkl")
    parser.add_argument(
        "--out-dir", type=Path, default=HOME / "results/challenger")
    args = parser.parse_args()
    refresh(args.snapshot, args.out_dir)
