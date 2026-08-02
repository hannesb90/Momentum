"""
tune_nan_handling.py – Utvärderar selektiv native NaN-hantering i LightGBM
jämfört med global fillna(0) (baseline) och global native NaN (tidigare #46).
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

# De fundamentala features där NaN har stort informationsvärde (t.ex. innan första rapporten publicerats)
FUNDAMENTAL_COLS = [
    "f_score", "rev_growth", "rev_accel", "margin_delta", "ni_growth", 
    "fcf_margin", "roa", "rev_growth_yoy", "eps_growth_yoy", 
    "report_reaction_abn", "div_growth_yoy"
]


def _prepare_features(df: pd.DataFrame, mode: str) -> np.ndarray:
    """Förbereder features baserat på vald NaN-hantering."""
    if mode == "baseline":
        # Global fyllning med 0
        return df[FEATURE_COLS].fillna(0).values
    elif mode == "selective_nan":
        # Fyll med 0 på alla utom de fundamentala kolumnerna (de lämnas som NaN)
        tmp = df[FEATURE_COLS].copy()
        fill_cols = [c for c in FEATURE_COLS if c not in FUNDAMENTAL_COLS]
        tmp[fill_cols] = tmp[fill_cols].fillna(0)
        return tmp.values
    elif mode == "global_nan":
        # Ingen fyllning alls (nativ NaN-hantering för alla)
        return df[FEATURE_COLS].values
    else:
        raise ValueError(f"Okänt läge: {mode}")


def _train_lambdarank_nan_mode(
    train_sub: pd.DataFrame,
    val_sub: pd.DataFrame,
    mode: str
) -> lgb.Booster:
    """Tränar en LambdaRank-modell med vald NaN-hantering."""
    X_tr = _prepare_features(train_sub, mode)
    X_va = _prepare_features(val_sub, mode)

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    y_tr_rel = train_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values
    y_va_rel = val_sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
    ).values

    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups)
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
    print(f"[nan_tune] {len(splits)} splits, topp-10. Varianter: selective_nan, global_nan\n")

    modes = ["selective_nan", "global_nan"]

    per_split_rows = []
    full_scores = {"baseline": []}
    for mode in modes:
        full_scores[mode] = []

    last_models = {}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)

        if len(test_sub) < 10:
            continue

        X_te_base = _prepare_features(test_sub, "baseline")

        # Baseline predictions (från rankingmodell)
        raw_base = lgbm.cls_models[i].predict(X_te_base)
        per_split_rows.append({"split": i + 1, "objective": "baseline", **_eval_on_test(test_sub, raw_base)})
        sdf_base = test_sub[["ticker"]].copy()
        sdf_base["_raw"] = raw_base
        full_scores["baseline"].append(sdf_base)

        print(f"  Split {i+1}/{len(splits)}: baseline IC={per_split_rows[-1]['test_ic']:+.3f}", end="")

        for mode in modes:
            model = _train_lambdarank_nan_mode(train_sub, val_sub, mode)
            last_models[mode] = model
            
            X_te_mode = _prepare_features(test_sub, mode)
            raw_mode = model.predict(X_te_mode)
            
            per_split_rows.append({"split": i + 1, "objective": mode, **_eval_on_test(test_sub, raw_mode)})
            sdf_mode = test_sub[["ticker"]].copy()
            sdf_mode["_raw"] = raw_mode
            full_scores[mode].append(sdf_mode)
            print(f" | {mode} IC={per_split_rows[-1]['test_ic']:+.3f}", end="")
        print()

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[nan_tune] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        last_i = len(lgbm.cls_models) - 1

        X_ho_base = _prepare_features(holdout_sub, "baseline")
        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho_base)
        sdf_base_ho = holdout_sub[["ticker"]].copy()
        sdf_base_ho["_raw"] = raw_base_ho
        full_scores["baseline"].append(sdf_base_ho)

        for mode in modes:
            model = last_models[mode]
            X_ho_mode = _prepare_features(holdout_sub, mode)
            raw_ho = model.predict(X_ho_mode)
            sdf_ho = holdout_sub[["ticker"]].copy()
            sdf_ho["_raw"] = raw_ho
            full_scores[mode].append(sdf_ho)

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

    print("\n[nan_tune] Klart.")


if __name__ == "__main__":
    main()
