"""
tune_nan_native.py – Punkt 5 i uppföljningslistan (2026-07-27): koden
kör genomgående `df[FEATURE_COLS].fillna(0)` (i _slice, predict(),
MomentumDataset) innan data går in i LightGBM. Det gör "saknad data" och
"verkligt värde noll" identiska för modellen - t.ex. rev_growth_yoy=0
(ingen tillväxt) och rev_growth_yoy=NaN (okänd tillväxt, bolaget saknar
ännu rapportdata) blir omöjliga att skilja åt.

LightGBM hanterar NaN NATIVT (use_missing=True som default) - den lär sig
per split-nod åt vilket håll saknade värden ska gå, i stället för att
tvingas tolka dem som en godtycklig konstant. Testat här: samma binära
klassificeringsobjective, samma features/splits/kalibrering, enda
skillnaden är att fillna(0) helt utelämnas (rå NaN skickas till LightGBM).

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_nan_native.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits, CALIBRATION_VAL_FRACTION
from sklearn.isotonic import IsotonicRegression
from backtest.calibration_check import prob_resolution_stats
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_objective_comparison import (
    _slice_sorted, _rank_stability, _build_signals_for_backtest,
)


def _eval_on_test(test_sub: pd.DataFrame, raw_score: np.ndarray) -> dict:
    test_sub = test_sub.copy()
    test_sub["_raw"] = raw_score
    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))
    edges = []
    for date, g in test_sub.groupby(level=0):
        if len(g) < 10:
            continue
        cutoff = g["_raw"].quantile(0.9)
        edges.append(g.loc[g["_raw"] >= cutoff, "target_return"].mean() - g["target_return"].mean())
    res = prob_resolution_stats(raw_score)
    return {
        "test_ic": ic,
        "test_top_decile_edge": float(np.mean(edges)) if edges else None,
        "score_n_unique": res["n_unique"],
        "score_largest_plateau_frac": res["largest_plateau_frac"],
    }


def _train_cls_nan_native(train_sub: pd.DataFrame, val_d: pd.DatetimeIndex, dev_df: pd.DataFrame):
    """IDENTISK metodik med produktionens _fit_cls/_fit_calibrator, enda
    skillnaden: .values i stället för .fillna(0).values - rå NaN skickas
    till LightGBM, som hanterar det nativt (use_missing=True, default)."""
    X_tr = train_sub[FEATURE_COLS].values
    y_tr = train_sub["target_signal"].values

    val_dates_sorted = pd.DatetimeIndex(val_d).sort_values().unique()
    split_i = int(len(val_dates_sorted) * (1 - CALIBRATION_VAL_FRACTION))
    val_d_stop, val_d_calib = val_dates_sorted[:split_i], val_dates_sorted[split_i:]

    stop_sub = _slice_sorted(dev_df, val_d_stop) if len(val_d_stop) else _slice_sorted(dev_df, val_d)
    calib_sub = _slice_sorted(dev_df, val_d_calib) if len(val_d_calib) >= 1 else _slice_sorted(dev_df, val_d)
    if len(calib_sub) < 30:
        stop_sub = calib_sub = _slice_sorted(dev_df, val_d)

    X_va_stop = stop_sub[FEATURE_COLS].values
    y_va_stop = stop_sub["target_signal"].values

    params = {**config.LGBM_PARAMS, "objective": "binary"}
    p = {k: v for k, v in params.items() if k not in ("n_estimators", "early_stopping_rounds")}
    ds_tr = lgb.Dataset(X_tr, label=y_tr)
    ds_va = lgb.Dataset(X_va_stop, label=y_va_stop, reference=ds_tr)
    model = lgb.train(
        p, ds_tr, num_boost_round=params["n_estimators"], valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False),
                   lgb.log_evaluation(period=-1)],
    )

    X_va_calib = calib_sub[FEATURE_COLS].values
    y_va_calib = calib_sub["target_signal"].values
    raw_calib = model.predict(X_va_calib)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_calib, y_va_calib)
    return model, calibrator


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    nan_rate = dev_df[FEATURE_COLS].isna().mean().sort_values(ascending=False)
    print(f"[nan_native] Features med störst NaN-andel:\n{nan_rate.head(8).to_string()}\n")

    per_split_rows = []
    full_scores = {"baseline": [], "nan_native": []}
    last_model, last_calibrator = None, None

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 10:
            continue

        X_te_filled = test_sub[FEATURE_COLS].fillna(0).values
        raw_base = lgbm.cls_models[i].predict(X_te_filled)
        cal_base = lgbm.calibrators[i].transform(raw_base) if i < len(lgbm.calibrators) else raw_base

        model, calibrator = _train_cls_nan_native(train_sub, val_d, dev_df)
        last_model, last_calibrator = model, calibrator
        X_te_nan = test_sub[FEATURE_COLS].values
        raw_nan = model.predict(X_te_nan)
        cal_nan = calibrator.transform(raw_nan)

        for name, raw in (("baseline", cal_base), ("nan_native", cal_nan)):
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"baseline IC={per_split_rows[-2]['test_ic']:+.3f} | "
              f"nan_native IC={per_split_rows[-1]['test_ic']:+.3f}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[nan_native] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        last_i = len(lgbm.cls_models) - 1
        raw_base_ho = lgbm.cls_models[last_i].predict(holdout_sub[FEATURE_COLS].fillna(0).values)
        cal_base_ho = (lgbm.calibrators[last_i].transform(raw_base_ho)
                       if last_i < len(lgbm.calibrators) else raw_base_ho)
        raw_nan_ho = last_model.predict(holdout_sub[FEATURE_COLS].values)
        cal_nan_ho = last_calibrator.transform(raw_nan_ho)
        for name, raw in (("baseline", cal_base_ho), ("nan_native", cal_nan_ho)):
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/nan_native_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per variant (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/nan_native_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} utbytt per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/nan_native_stability.csv", index=False)

    print(f"\n{'='*100}\nFullständigt backtest (topp-{n_top} likaviktat, dev+holdout)\n{'='*100}")
    backtest_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        signals = _build_signals_for_backtest(scores_df, n_top)
        stats = _run_backtest(signals, data, holdout_start)
        row = {
            "objective": name,
            "dev_CAGR": _pct(stats["dev"], "CAGR"), "dev_Sharpe": float(stats["dev"]["Sharpe"]),
            "dev_MaxDD": _pct(stats["dev"], "Max Drawdown"),
            "holdout_CAGR": _pct(stats["holdout"], "CAGR") if stats["holdout"] else None,
            "holdout_Sharpe": float(stats["holdout"]["Sharpe"]) if stats["holdout"] else None,
            "holdout_MaxDD": _pct(stats["holdout"], "Max Drawdown") if stats["holdout"] else None,
        }
        backtest_rows.append(row)
        print(f"  {name:22s}: dev CAGR={row['dev_CAGR']:+.2%} Sharpe={row['dev_Sharpe']:.2f} "
              f"MaxDD={row['dev_MaxDD']:.1%} | holdout CAGR={row['holdout_CAGR']:+.2%} "
              f"Sharpe={row['holdout_Sharpe']}")
    pd.DataFrame(backtest_rows).to_csv("results/nan_native_backtest.csv", index=False)
    print(f"\n[nan_native] Klart.")


if __name__ == "__main__":
    main()
