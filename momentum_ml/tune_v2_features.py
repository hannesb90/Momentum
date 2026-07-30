"""
tune_v2_features.py – Utvärderar volatilitetsjusterad momentum och trend-konsistens
(v2-features) under den nya LambdaRank-rankingarkitekturen med tidsutjämning.
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


def _date_weights(sub: pd.DataFrame) -> np.ndarray:
    """Tidsutjämning (1/n per datum) för förlustfunktionen."""
    sizes = sub.groupby(level=0).size()
    return (1.0 / sizes.reindex(sub.index)).values


def _add_v2_features(df: pd.DataFrame) -> pd.DataFrame:
    """Beräknar och lägger till v2-features (volatilitetsjustering och konsistens) på rullande basis."""
    df = df.copy().sort_index()
    
    # 1. Volatilitetsjusterad momentum (Sharpe-liknande momentum)
    df["mom_vol_scaled_13w"] = df["roc_13w"] / (df["rvol_13w"] + 1e-6)
    df["mom_vol_scaled_26w"] = df["roc_26w"] / (df["rvol_26w"] + 1e-6)
    
    # 2. Momentum-konsistens (rullande Sharpe av veckoavkastningar)
    df["mom_consistency_13w"] = df.groupby("ticker")["ret_1w"].transform(
        lambda x: x.rolling(13).mean() / (x.rolling(13).std() + 1e-6)
    ).fillna(0)
    df["mom_consistency_26w"] = df.groupby("ticker")["ret_1w"].transform(
        lambda x: x.rolling(26).mean() / (x.rolling(26).std() + 1e-6)
    ).fillna(0)
    
    return df


def _train_lambdarank_v2(
    train_sub: pd.DataFrame,
    val_sub: pd.DataFrame,
    feature_cols: list
) -> lgb.Booster:
    """Tränar en LambdaRank-modell med de utökade v2-featuresen."""
    X_tr = train_sub[feature_cols].fillna(0).values
    X_va = val_sub[feature_cols].fillna(0).values

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    # Relevanslabels (0-4)
    y_tr_rel = train_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values
    y_va_rel = val_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values

    w_tr = _date_weights(train_sub)

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
    
    # Beräkna v2-features
    print("[v2_features] Beräknar volatilitetsjusterade och konsistensbaserade features...")
    model_df = _add_v2_features(model_df)
    
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]

    splits = walk_forward_splits(dev_df.index)
    print(f"[v2_features] {len(splits)} splits, topp-10. Varianter: baseline (59 feats), v2_features (63 feats)\n")

    v2_feature_cols = FEATURE_COLS + [
        "mom_vol_scaled_13w", "mom_vol_scaled_26w", "mom_consistency_13w", "mom_consistency_26w"
    ]

    per_split_rows = []
    full_scores = {"baseline": [], "v2_features": []}
    last_model = None

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)

        if len(test_sub) < 10:
            continue

        X_te_base = test_sub[FEATURE_COLS].fillna(0).values
        X_te_v2 = test_sub[v2_feature_cols].fillna(0).values

        # Baseline predictions (från rankingmodell)
        raw_base = lgbm.cls_models[i].predict(X_te_base)
        per_split_rows.append({"split": i + 1, "objective": "baseline", **_eval_on_test(test_sub, raw_base)})
        sdf_base = test_sub[["ticker"]].copy()
        sdf_base["_raw"] = raw_base
        full_scores["baseline"].append(sdf_base)

        # V2 features training
        model = _train_lambdarank_v2(train_sub, val_sub, v2_feature_cols)
        last_model = model
        raw_v2 = model.predict(X_te_v2)
        
        per_split_rows.append({"split": i + 1, "objective": "v2_features", **_eval_on_test(test_sub, raw_v2)})
        sdf_v2 = test_sub[["ticker"]].copy()
        sdf_v2["_raw"] = raw_v2
        full_scores["v2_features"].append(sdf_v2)

        print(f"  Split {i+1}/{len(splits)}: baseline IC={per_split_rows[-2]['test_ic']:+.3f} | v2_features IC={per_split_rows[-1]['test_ic']:+.3f}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[v2_features] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        last_i = len(lgbm.cls_models) - 1

        X_ho_base = holdout_sub[FEATURE_COLS].fillna(0).values
        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho_base)
        sdf_base_ho = holdout_sub[["ticker"]].copy()
        sdf_base_ho["_raw"] = raw_base_ho
        full_scores["baseline"].append(sdf_base_ho)

        X_ho_v2 = holdout_sub[v2_feature_cols].fillna(0).values
        raw_v2_ho = last_model.predict(X_ho_v2)
        sdf_v2_ho = holdout_sub[["ticker"]].copy()
        sdf_v2_ho["_raw"] = raw_v2_ho
        full_scores["v2_features"].append(sdf_v2_ho)

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

    print("\n[v2_features] Klart.")


if __name__ == "__main__":
    main()
