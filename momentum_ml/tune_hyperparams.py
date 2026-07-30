"""
tune_hyperparams.py – Genomför en systematisk koordinatsvep av hyperparametrar
mot den nya produktionsbaslinjen (LambdaRank + Equal Date Weight + native NaN).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
import joblib

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_objective_comparison import (
    _slice_sorted, _eval_on_test, _rank_stability, _build_signals_for_backtest,
)


def _date_weights(sub: pd.DataFrame) -> np.ndarray:
    """Tidsutjämning (1/n per datum) för förlustfunktionen."""
    sizes = sub.groupby(level=0).size()
    return (1.0 / sizes.reindex(sub.index)).values.astype(np.float32)


def _train_lambdarank_params(
    train_sub: pd.DataFrame,
    val_sub: pd.DataFrame,
    hyperparams: dict
) -> lgb.Booster:
    """Tränar en LambdaRank-modell med anpassade hyperparametrar."""
    X_tr = train_sub[FEATURE_COLS].values
    X_va = val_sub[FEATURE_COLS].values

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    # Relevanslabels (0-4)
    y_tr_rel = train_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values
    y_va_rel = val_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values

    # INGEN datumviktning – Test 7 (testplan_niva1_niva2.md, UTVECKLINGSLOGG #102/#117)
    # visade att equal-date-weighting SKADAR holdout-prestanda kraftigt (Sharpe
    # 0,64→1,73 vid borttagning); den kombinerade produktionsmodellen tränas UTAN den.
    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [10],
        "verbosity": -1,
        "n_jobs": -1,
        **hyperparams
    }

    model = lgb.train(
        params,
        ds_tr,
        num_boost_round=500,
        valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False)]
    )
    return model


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]

    splits = walk_forward_splits(dev_df.index)
    
    # Baslinjeparametrar – HÄMTADE DIREKT från MomentumLGBM().params (2026-07-30,
    # verifierat via `python3 -c "from models.lgbm_model import MomentumLGBM;
    # print(MomentumLGBM().params)"`), inte hårdkodade separat. Ursprungliga värden
    # (lr=0,01/min_data_in_leaf=100/inga reg-termer) var INAKTUELLA – matchade INTE
    # produktionens faktiska (lr=0,05/min_child_samples=30/reg_alpha=0,1/reg_lambda=1,0),
    # samma buggmönster 3-confound som redan hittats/fixats i tune_universe.py m.fl.
    baseline_params = {
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 30,      # LightGBM-alias för min_child_samples
        "feature_fraction": 1.0,
        "lambda_l2": 1.0,            # LightGBM-alias för reg_lambda
        "lambda_l1": 0.1,            # LightGBM-alias för reg_alpha
        "seed": 42,
    }

    # Definiera svepkonfigurationerna (koordinatbaserat sweep för att spara tid)
    candidates = {
        "baseline": baseline_params,
        
        # num_leaves
        "num_leaves_7": {**baseline_params, "num_leaves": 7},
        "num_leaves_15": {**baseline_params, "num_leaves": 15},
        "num_leaves_63": {**baseline_params, "num_leaves": 63},
        
        # learning_rate
        "lr_0.005": {**baseline_params, "learning_rate": 0.005},
        "lr_0.02": {**baseline_params, "learning_rate": 0.02},
        
        # min_data_in_leaf
        "min_leaf_50": {**baseline_params, "min_data_in_leaf": 50},
        "min_leaf_200": {**baseline_params, "min_data_in_leaf": 200},
        
        # feature_fraction
        "feat_frac_0.7": {**baseline_params, "feature_fraction": 0.7},
        "feat_frac_0.85": {**baseline_params, "feature_fraction": 0.85},
        
        # lambda_l2
        "l2_1.0": {**baseline_params, "lambda_l2": 1.0},
        "l2_5.0": {**baseline_params, "lambda_l2": 5.0},
    }

    print(f"[hyperparams] {len(splits)} splits, topp-10. Antal varianter att testa: {len(candidates)}\n")

    per_split_rows = []
    full_scores = {name: [] for name in candidates}
    last_models = {name: None for name in candidates}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)

        if len(test_sub) < 10:
            continue

        X_te = test_sub[FEATURE_COLS].values

        print(f"  Split {i+1}/{len(splits)}:", end="")
        for name, params in candidates.items():
            model = _train_lambdarank_params(train_sub, val_sub, params)
            last_models[name] = model
            
            raw_scores = model.predict(X_te)
            per_split_rows.append({"split": i + 1, "objective": name, **_eval_on_test(test_sub, raw_scores)})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw_scores
            full_scores[name].append(sdf)
            print(f" {name}={per_split_rows[-1]['test_ic']:+.2f}", end=" |")
        print()

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[hyperparams] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].values
        
        for name in candidates:
            model = last_models[name]
            raw_ho = model.predict(X_ho)
            sdf_ho = holdout_sub[["ticker"]].copy()
            sdf_ho["_raw"] = raw_ho
            full_scores[name].append(sdf_ho)

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
    backtest_summary = []
    for key in full_scores:
        signals = _build_signals_for_backtest(pd.concat(full_scores[key]), 10)
        stats = _run_backtest(signals, data, holdout_start)
        dev_res = stats["dev"]
        ho_res = stats["holdout"]
        print(f"  {key:<18}: dev CAGR={_pct(dev_res, 'CAGR'):+.2%} Sharpe={float(dev_res['Sharpe']):.2f} MaxDD={_pct(dev_res, 'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(ho_res, 'CAGR'):+.2%} Sharpe={float(ho_res['Sharpe']) if ho_res else 0.0:.2f}")

    print("\n[hyperparams] Klart.")


if __name__ == "__main__":
    main()
