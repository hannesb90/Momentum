"""Nivå-2 stage 06: causal retraining cadence and model-staleness sweep."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large, validate_large_contract

apply_large()

from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS, to_model_df
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva2_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _eval_on_test, _train_lambdarank
from tune_target_horizon_isolated import raw_preds, targets_from_prices


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva2_stages/05_pipeline_ablation.json"
OUT = ROOT / "results/retraining_staleness_niva2.json"
ARMS_OUT = ROOT / "results/retraining_staleness_niva2_arms.csv"
AGE_OUT = ROOT / "results/retraining_staleness_niva2_age.csv"
WINNER_SIG = ROOT / "results/niva2_stage6_winner_signals.csv"
CADENCES = {"retrain_13w": 1, "retrain_26w": 2, "retrain_52w": 4,
            "retrain_104w": 8, "static_first_fit": 10_000}


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _number(stats, key):
    return float(str(stats[key]).replace("%", ""))


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("winner") != "plus_inverse_vol75":
        raise RuntimeError("Stage-05 winner mismatch")
    features, prices, state, _ = _load_state()
    cols = list(getattr(state, "feature_cols_", []) or FEATURE_COLS)
    validate_large_contract(cols)
    _, sectors, caps, names = load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)

    base = to_model_df(features).sort_index(); base.index.name = "Date"
    target13 = targets_from_prices(base, prices, 13)
    target52 = targets_from_prices(base, prices, 52)
    feature_base = base.drop(columns=[c for c in base.columns if c.startswith("target_")], errors="ignore")
    t13 = target13.reset_index().rename(columns={"target_return": "ret13", "target_signal": "sig13"})
    t52 = target52.reset_index().rename(columns={"target_return": "ret52", "target_signal": "sig52"})
    panel = (feature_base.reset_index().merge(t13, on=["Date", "ticker"])
             .merge(t52, on=["Date", "ticker"])
             .dropna(subset=["ret13", "sig13", "ret52", "sig52"])
             .set_index("Date").sort_index())
    panel["target_return"] = panel["ret13"]
    panel["target_signal"] = panel["sig13"]
    dates = panel.index.unique().sort_values(); purge = dates[-(config.HOLDOUT_WEEKS + 52)]
    dev = panel[panel.index < purge]
    expected = json.loads((ROOT / "results/target_horizon_isolated.json").read_text())["same_feature_hash"]
    actual = hashlib.sha256(pd.util.hash_pandas_object(dev[cols], index=True).values.tobytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("Stage-01 feature panel hash mismatch")
    splits = walk_forward_splits(dev.index, embargo_weeks=52)
    feature_dfs = {ticker: frame.assign(ticker=ticker) for ticker, frame in features.items()}
    config.REBALANCE_WEEKS = 52; config.SIZING_MODE = "inverse_vol"; config.CONVICTION_BLEND = 0.75

    all_stats = []; age_rows = []; signals = {}
    for arm, block_count in CADENCES.items():
        raw = []; model = None; fit_split = None
        for split_i, (train_dates, val_dates, test_dates) in enumerate(splits):
            if model is None or split_i % block_count == 0:
                train = dev[dev.index.isin(train_dates)].sort_index()
                val = dev[dev.index.isin(val_dates)].sort_index()
                model = _train_lambdarank(train, val, cols); fit_split = split_i
            test = dev[dev.index.isin(test_dates)].sort_index()
            score = model.predict(test[cols].fillna(0).values)
            piece = test[["ticker"]].copy(); piece["raw"] = score; raw.append(piece)
            age = (split_i - fit_split) * config.TEST_STEP_WEEKS
            age_rows.append({"arm": arm, "split": split_i + 1, "fit_split": fit_split + 1,
                             "model_age_weeks": age, **_eval_on_test(test, score)})
            print(f"{arm} split {split_i + 1}/{len(splits)} age={age}w", flush=True)
        sig = build_full_output(raw_preds(pd.concat(raw).sort_index()), None, feature_dfs,
                                MomentumEnsemble(), record_diagnostics=False)
        bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
        all_stats.append({"arm": arm, "cadence_weeks": None if block_count > 1000 else block_count * 13,
                          "fits": 1 if block_count > 1000 else int(np.ceil(len(splits) / block_count)), **stats})
        signals[arm] = sig
        print(arm, stats["CAGR"], stats["Sharpe"], stats["Max Drawdown"], flush=True)

    table = pd.DataFrame(all_stats); ages = pd.DataFrame(age_rows)
    winner = max(table.arm, key=lambda name: (
        _number(table.set_index("arm").loc[name], "CAGR"),
        float(table.set_index("arm").loc[name, "Sharpe"])))
    table.to_csv(ARMS_OUT, index=False); ages.to_csv(AGE_OUT, index=False); signals[winner].to_csv(WINNER_SIG)
    age_summary = (ages.groupby("model_age_weeks")[["test_ic", "test_top_decile_edge", "ndcg_at_10"]]
                   .median().reset_index().to_dict("records"))
    baseline = table.set_index("arm").loc["retrain_13w"]
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
              "locked_architecture": "lambdarank_13w_calendar52_eligibility_inversevol75_no_corr",
              "same_rows": len(dev), "same_splits": len(splits), "feature_hash": actual,
              "holdout_used": False, "cadences_preregistered": list(CADENCES),
              "winner": winner, "winner_metrics": table.set_index("arm").loc[winner].to_dict(),
              "retrain_13w_parity": {"CAGR": baseline["CAGR"], "Sharpe": baseline["Sharpe"],
                                      "Max Drawdown": baseline["Max Drawdown"]},
              "median_metrics_by_model_age": age_summary,
              "results_csv": str(ARMS_OUT.relative_to(ROOT)), "age_csv": str(AGE_OUT.relative_to(ROOT))}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("06_retraining_staleness",
        [OUT, ARMS_OUT, AGE_OUT, WINNER_SIG, Path(__file__).resolve()],
        {"winner": winner, "objective": "lambdarank", "target_weeks": 13,
         "rotation_weeks": 52, "holdout_used": False, "arms": len(CADENCES)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
