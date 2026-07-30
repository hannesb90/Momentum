"""
tune_age_weight.py – Utvärderar åldersviktade sample-vikter (time decay)
kombinerat med equal date weighting under LambdaRank-rankingarkitekturen.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
import joblib

sys.path.insert(0, ".")
import config
# tune_abstention_gate sätter config.DROP_FEATURES (buggmönster 1) - måste
# importeras FÖRE vårt eget FEATURE_COLS-import, annars 61-vs-48-mismatch.
from tune_abstention_gate import _load_state, _run_backtest, _pct
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from tune_objective_comparison import (
    _slice_sorted, _eval_on_test, _rank_stability, _build_signals_for_backtest,
)
from tune_lambdarank_common import production_params


def _combined_weights(sub: pd.DataFrame, half_life_weeks: float) -> np.ndarray:
    """Kombinerar tidsutjämning (1/n per datum) med åldersviktning (exponential decay)."""
    # 1. Date weights
    sizes = sub.groupby(level=0).size()
    w_date = (1.0 / sizes.reindex(sub.index)).values

    # 2. Age weights
    unique_dates = sub.index.unique().sort_values()
    max_date = unique_dates[-1]
    dates = sub.index
    age_weeks = (max_date - dates).days / 7.0
    w_age = np.exp(-np.log(2.0) * age_weeks / half_life_weeks)

    return np.asarray(w_date * w_age, dtype=np.float32)


def _train_lambdarank_age_weighted(
    train_sub: pd.DataFrame,
    val_sub: pd.DataFrame,
    half_life_weeks: float
) -> lgb.Booster:
    """Tränar en LambdaRank-modell med ålders- och datumviktade samples."""
    X_tr = train_sub[FEATURE_COLS].fillna(0).values
    X_va = val_sub[FEATURE_COLS].fillna(0).values

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    # Relevanslabels (0-4)
    y_tr_rel = train_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values
    y_va_rel = val_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values

    w_tr = _combined_weights(train_sub, half_life_weeks)

    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

    model = lgb.train(
        production_params(),
        ds_tr,
        num_boost_round=500,
        valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)]
    )
    return model


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]

    splits = walk_forward_splits(dev_df.index)
    print(f"[ageweight] {len(splits)} splits, topp-10. Varianter: decay_52w, decay_104w, decay_208w\n")

    half_lives = {
        "decay_52w": 52.0,
        "decay_104w": 104.0,
        "decay_208w": 208.0,
    }

    per_split_rows = []
    full_scores = {"baseline": []}
    for key in half_lives:
        full_scores[key] = []

    last_models = {}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)

        if len(test_sub) < 10:
            continue

        X_te = test_sub[FEATURE_COLS].fillna(0).values

        # Baseline predictions (från rankingmodell)
        raw_base = lgbm.cls_models[i].predict(X_te)
        per_split_rows.append({"split": i + 1, "objective": "baseline", **_eval_on_test(test_sub, raw_base)})
        sdf_base = test_sub[["ticker"]].copy()
        sdf_base["_raw"] = raw_base
        full_scores["baseline"].append(sdf_base)

        print(f"  Split {i+1}/{len(splits)}: baseline IC={per_split_rows[-1]['test_ic']:+.3f}", end="")

        for key, hl in half_lives.items():
            model = _train_lambdarank_age_weighted(train_sub, val_sub, hl)
            last_models[key] = model
            raw_decay = model.predict(X_te)
            
            per_split_rows.append({"split": i + 1, "objective": key, **_eval_on_test(test_sub, raw_decay)})
            sdf_decay = test_sub[["ticker"]].copy()
            sdf_decay["_raw"] = raw_decay
            full_scores[key].append(sdf_decay)
            print(f" | {key} IC={per_split_rows[-1]['test_ic']:+.3f}", end="")
        print()

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[ageweight] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].fillna(0).values
        last_i = len(lgbm.cls_models) - 1

        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho)
        sdf_base_ho = holdout_sub[["ticker"]].copy()
        sdf_base_ho["_raw"] = raw_base_ho
        full_scores["baseline"].append(sdf_base_ho)

        for key in half_lives:
            model = last_models[key]
            raw_ho = model.predict(X_ho)
            sdf_ho = holdout_sub[["ticker"]].copy()
            sdf_ho["_raw"] = raw_ho
            full_scores[key].append(sdf_ho)

    # Sammanställ
    df_results = pd.DataFrame(per_split_rows)
    print("\n" + "=" * 100)
    print("Median över 31 splits, per variant (innan portföljfilter)")
    print("=" * 100)
    medians = df_results.groupby("objective")[["test_ic", "ndcg_at_10"]].median()
    print(medians)

    print("\n" + "=" * 100)
    print("Rankstabilitet (andel av topp-10 utbytt per rebalansering)")
    print("=" * 100)
    for key in full_scores:
        stab = _rank_stability(pd.concat(full_scores[key]), 10, 13)
        print(f"  {key:<18}: {stab:.1%}")

    print("\n" + "=" * 100)
    print("Fullständigt backtest (topp-10 likaviktat, dev+holdout)")
    print("=" * 100)
    for key in full_scores:
        signals = _build_signals_for_backtest(pd.concat(full_scores[key]), 10)
        stats = _run_backtest(signals, data, holdout_start)
        dev_res = stats["dev"]
        ho_res = stats["holdout"]
        print(f"  {key:<18}: dev CAGR={_pct(dev_res, 'CAGR'):+.2%} Sharpe={float(dev_res['Sharpe']):.2f} MaxDD={_pct(dev_res, 'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(ho_res, 'CAGR'):+.2%} Sharpe={float(ho_res['Sharpe']) if ho_res else 0.0:.2f}")

    print("\n[ageweight] Klart.")


if __name__ == "__main__":
    main()
