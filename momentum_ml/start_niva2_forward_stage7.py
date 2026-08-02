"""Start/update the preregistered independent Stage-07 paper-forward test."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import joblib
import pandas as pd

import config
from research_gates_common import apply_large, validate_large_contract

apply_large()

from data.data_loader import (fetch_weekly_data, filter_active_universe,
                              filter_liquid_universe, load_sweden_universe)
from features.feature_engineering import (FEATURE_COLS, attach_categorical_features,
    attach_fundamentals_features, build_all_features, to_model_df)
from models.ensemble import MomentumEnsemble, build_full_output
from niva2_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_lambdarank
from tune_target_horizon_isolated import raw_preds, targets_from_prices


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva2_stages/06_retraining_staleness.json"
STAGE = ROOT / "results/niva2_stages/07_forward_preregistration.json"
DIR = ROOT / "results/niva2_forward"
PROTOCOL = DIR / "protocol.json"
MODEL = DIR / "challenger.joblib"
INITIAL = DIR / "initial_candidate_signal.csv"
PRODUCTION = DIR / "initial_production_signal.csv"
LEDGER = DIR / "weekly_ledger.jsonl"


def _panel(features, prices):
    # Serving must retain the unlabeled right edge. to_model_df() deliberately
    # drops it according to the legacy 52w production target and is research-only.
    frames = []
    for ticker, frame in features.items():
        piece = frame.copy(); piece["ticker"] = ticker; frames.append(piece)
    base = pd.concat(frames).sort_index(); base.index.name = "Date"
    target = targets_from_prices(base, prices, 13)
    clean = base.drop(columns=[c for c in base if c.startswith("target_")], errors="ignore")
    labeled = (clean.reset_index().merge(target.reset_index(), on=["Date", "ticker"])
               .dropna(subset=["target_return", "target_signal"]).set_index("Date").sort_index())
    return base, labeled


def _current_state(tickers, sectors, caps):
    """Build from the current price cache; research pickle ends in 2025."""
    prices = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    prices = filter_active_universe(prices)
    prices = filter_liquid_universe(prices, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    all_features = build_all_features(prices)
    all_features = attach_categorical_features(all_features, sector_map=sectors, cap_tier_map=caps)
    all_features = attach_fundamentals_features(all_features, segment="large", prices=prices)
    features = {ticker: frame for ticker, frame in all_features.items()
                if config.CAP_TIER_MAP.get(ticker, caps.get(ticker, "")) != "Fond"}
    return features, prices


def _train_and_freeze(parent, features, prices, state):
    DIR.mkdir(parents=True, exist_ok=True)
    cols = list(getattr(state, "feature_cols_", []) or FEATURE_COLS)
    validate_large_contract(cols)
    base, labeled = _panel(features, prices)
    all_dates = base.index.unique().sort_values(); start_date = all_dates[-1]
    # Reproduce the conservative Stage-01..06 split geometry immediately before
    # forward start: nominal 260w train/52w validation, both purged by 52w.
    start_i = len(all_dates) - 1 - config.TRAIN_WINDOW_WEEKS - config.VAL_WINDOW_WEEKS
    if start_i < 0:
        raise RuntimeError("Insufficient history for frozen serving split")
    train_nominal = all_dates[start_i:start_i + config.TRAIN_WINDOW_WEEKS]
    train_dates = train_nominal[:-52]
    val_start = start_i + config.TRAIN_WINDOW_WEEKS
    val_dates = all_dates[val_start:val_start + 1]
    train = labeled[labeled.index.isin(train_dates)].sort_index()
    val = labeled[labeled.index.isin(val_dates)].sort_index()
    if train.empty or val.empty:
        raise RuntimeError("Frozen serving train/validation window is empty")
    model = _train_lambdarank(train, val, cols)
    joblib.dump({"model": model, "feature_cols": cols, "start_date": start_date,
                 "train_dates": [train_dates.min(), train_dates.max()],
                 "val_dates": [val_dates.min(), val_dates.max()],
                 "production": False, "tuning_locked": True}, MODEL)

    recent_dates = all_dates[-52:]
    recent = base[base.index.isin(recent_dates)]
    raw = recent[["ticker"]].copy(); raw["raw"] = model.predict(recent[cols].fillna(0).values)
    preds = raw_preds(raw)
    config.REBALANCE_WEEKS = 52; config.SIZING_MODE = "inverse_vol"; config.CONVICTION_BLEND = 0.75
    feature_dfs = {ticker: frame.assign(ticker=ticker) for ticker, frame in features.items()}
    full = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), record_diagnostics=False)
    initial = full.loc[[start_date]].copy(); initial.to_csv(INITIAL)
    prod = pd.read_csv(ROOT / "results/signals.csv", parse_dates=["Date"])
    prod = prod[prod.Date.eq(start_date)]; prod.to_csv(PRODUCTION, index=False)
    end_min = start_date + timedelta(weeks=52)
    protocol = {
        "status": "PREREGISTERED_ACTIVE", "production": False,
        "parent_stage": parent["manifest_sha256"], "start_date": str(start_date.date()),
        "minimum_end_date": str(end_min.date()), "minimum_observed_weeks": 52,
        "required_scheduled_rotations": 1, "initial_capital_sek": 100000,
        "monthly_contributions": "tracked separately; excluded from TWR/alpha endpoint",
        "candidate": "LambdaRank + 13w target + calendar52 + eligibility + inverse-vol75; no correlation filter",
        "refit_policy": "once immediately before each 52-week rotation",
        "comparators": ["production_signal_frozen_at_each_observation", "XACT-SVERIGE.ST"],
        "primary_endpoint": "net time-weighted CAGR alpha versus XACT Sverige",
        "secondary": ["Sharpe", "MaxDD", "turnover", "alpha versus production"],
        "pass_policy": "cannot PASS before both minimum weeks and one scheduled rotation; no retroactive tuning",
        "old_holdout_voting_weight": 0,
    }
    PROTOCOL.write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8")
    return freeze_stage("07_forward_preregistration",
        [PROTOCOL, MODEL, INITIAL, PRODUCTION, Path(__file__).resolve()],
        {"gate": "protocol_frozen_not_validation_pass", "start_date": str(start_date.date()),
         "minimum_weeks": 52, "production": False}, parent=PARENT)


def _append_initial_observation(prices):
    protocol = json.loads(PROTOCOL.read_text()); date = protocol["start_date"]
    existing = []
    if LEDGER.exists():
        existing = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    if any(row.get("date") == date for row in existing):
        return False
    candidate = pd.read_csv(INITIAL)
    candidate = candidate[candidate.pred_signal.eq(1)]
    production = pd.read_csv(PRODUCTION)
    production = production[production.pred_signal.eq(1)]
    idx = config.INDEX_BENCHMARK_TICKER
    record = {"date": date, "observation": 1, "status": "ACTIVE_INSUFFICIENT_FORWARD",
              "candidate_tickers": candidate.ticker.tolist(),
              "candidate_weights": candidate.position_size.astype(float).tolist(),
              "production_tickers": production.ticker.tolist(),
              "production_weights": production.position_size.astype(float).tolist(),
              "benchmark": idx, "benchmark_close": float(prices[idx].Close.asof(pd.Timestamp(date))),
              "candidate_nav": 100000.0, "production_nav": 100000.0, "benchmark_nav": 100000.0,
              "note": "start observation; no performance inference"}
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def main():
    parent = verify_manifest(PARENT)
    _, _, state, _ = _load_state()  # locked feature-column contract only
    tickers, sectors, caps, names = load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    features, prices = _current_state(tickers, sectors, caps)
    stage = verify_manifest(STAGE) if STAGE.exists() else verify_manifest(
        _train_and_freeze(parent, features, prices, state))
    added = _append_initial_observation(prices)
    print(json.dumps({"stage_status": stage["status"], "protocol_status": "PREREGISTERED_ACTIVE",
                      "initial_observation_added": added, "ledger": str(LEDGER),
                      "production_changed": False}, indent=2))


if __name__ == "__main__":
    main()
