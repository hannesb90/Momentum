"""
tune_drop_tidig_entry.py – Punkt 2 i användarens omprioriterade
uppföljningslista (2026-07-26/27): config.py:s egen kommentar dokumenterar
att en tidigare ablation (tune_ablation.py, LOGO) visade att
"tidig_entry"-featuregruppen (donchian_pos, breakout_nw, roc_accel_4w,
pullback) var AKTIVT SKADLIG på holdouten (-5,1% -> +1,5% vid borttag),
men config.DROP_FEATURES är fortfarande tom - fyndet blev aldrig
adopterat. Det här kör ett rent, uppdaterat A/B-test med FULL pipeline
(inte bara LGBM-ablationen som ursprungligen upptäckte det) på samma
full-universum-data som resten av sessionens forskning.

FEATURE_COLS beräknas en gång vid import av features.feature_engineering
utifrån config.DROP_FEATURES - att sätta config.DROP_FEATURES efter
import uppdaterar INTE listan. Skriptet filtrerar därför en egen kopia av
FEATURE_COLS lokalt (utan att röra config/modulen) och tränar en HELT NY
modell (inte en återanvänd - färre kolumner kräver ny träning genom hela
walk-forward-kedjan, kan inte återanvändas från de befintliga cls_models).

Två varianter, båda binär klassificering (samma objective, samma
kalibreringsmetodik):

  baseline        – återanvänder redan tränade cls_models/calibrators
                    (alla features, inkl. tidig_entry-gruppen).
  no_tidig_entry  – ny träning, FEATURE_COLS minus donchian_pos/
                    breakout_nw/roc_accel_4w/pullback.

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_drop_tidig_entry.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS as ALL_FEATURE_COLS
from models.lgbm_model import walk_forward_splits, CALIBRATION_VAL_FRACTION
from sklearn.isotonic import IsotonicRegression
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_objective_comparison import (
    _slice_sorted as _slice_sorted_all, _rank_stability, _build_signals_for_backtest,
)
from backtest.calibration_check import prob_resolution_stats

TIDIG_ENTRY = ["donchian_pos", "breakout_nw", "roc_accel_4w", "pullback"]
REDUCED_FEATURE_COLS = [c for c in ALL_FEATURE_COLS if c not in TIDIG_ENTRY]


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


def _train_cls_reduced(train_sub: pd.DataFrame, val_d: pd.DatetimeIndex, dev_df: pd.DataFrame):
    X_tr = train_sub[REDUCED_FEATURE_COLS].fillna(0).values
    y_tr = train_sub["target_signal"].values

    val_dates_sorted = pd.DatetimeIndex(val_d).sort_values().unique()
    split_i = int(len(val_dates_sorted) * (1 - CALIBRATION_VAL_FRACTION))
    val_d_stop, val_d_calib = val_dates_sorted[:split_i], val_dates_sorted[split_i:]

    stop_sub = _slice_sorted_all(dev_df, val_d_stop) if len(val_d_stop) else _slice_sorted_all(dev_df, val_d)
    calib_sub = _slice_sorted_all(dev_df, val_d_calib) if len(val_d_calib) >= 1 else _slice_sorted_all(dev_df, val_d)
    if len(calib_sub) < 30:
        stop_sub = calib_sub = _slice_sorted_all(dev_df, val_d)

    X_va_stop = stop_sub[REDUCED_FEATURE_COLS].fillna(0).values
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

    X_va_calib = calib_sub[REDUCED_FEATURE_COLS].fillna(0).values
    y_va_calib = calib_sub["target_signal"].values
    raw_calib = model.predict(X_va_calib)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_calib, y_va_calib)
    return model, calibrator


def main():
    print(f"[drop_tidig_entry] Uteslutna features: {TIDIG_ENTRY}")
    print(f"[drop_tidig_entry] {len(ALL_FEATURE_COLS)} -> {len(REDUCED_FEATURE_COLS)} features.\n")

    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    per_split_rows = []
    full_scores = {"baseline": [], "no_tidig_entry": []}
    last_model, last_calibrator = None, None

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted_all(dev_df, train_d)
        test_sub = _slice_sorted_all(dev_df, test_d)
        if len(test_sub) < 10:
            continue

        X_te_full = test_sub[ALL_FEATURE_COLS].fillna(0).values
        raw_base = lgbm.cls_models[i].predict(X_te_full)
        cal_base = lgbm.calibrators[i].transform(raw_base) if i < len(lgbm.calibrators) else raw_base

        model, calibrator = _train_cls_reduced(train_sub, val_d, dev_df)
        last_model, last_calibrator = model, calibrator
        X_te_reduced = test_sub[REDUCED_FEATURE_COLS].fillna(0).values
        raw_reduced = model.predict(X_te_reduced)
        cal_reduced = calibrator.transform(raw_reduced)

        for name, raw in (("baseline", cal_base), ("no_tidig_entry", cal_reduced)):
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"baseline IC={per_split_rows[-2]['test_ic']:+.3f} edge={per_split_rows[-2]['test_top_decile_edge']} | "
              f"no_tidig_entry IC={per_split_rows[-1]['test_ic']:+.3f} edge={per_split_rows[-1]['test_top_decile_edge']}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[drop_tidig_entry] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted_all(model_df, holdout_dates)
        last_i = len(lgbm.cls_models) - 1
        X_ho_full = holdout_sub[ALL_FEATURE_COLS].fillna(0).values
        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho_full)
        cal_base_ho = (lgbm.calibrators[last_i].transform(raw_base_ho)
                       if last_i < len(lgbm.calibrators) else raw_base_ho)
        X_ho_reduced = holdout_sub[REDUCED_FEATURE_COLS].fillna(0).values
        raw_reduced_ho = last_model.predict(X_ho_reduced)
        cal_reduced_ho = last_calibrator.transform(raw_reduced_ho)
        for name, raw in (("baseline", cal_base_ho), ("no_tidig_entry", cal_reduced_ho)):
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/drop_tidig_entry_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per variant (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/drop_tidig_entry_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} utbytt per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/drop_tidig_entry_stability.csv", index=False)

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
    pd.DataFrame(backtest_rows).to_csv("results/drop_tidig_entry_backtest.csv", index=False)
    print(f"\n[drop_tidig_entry] Klart.")


if __name__ == "__main__":
    main()
