"""
tune_nonoverlapping_labels.py – Punkt 4 i uppföljningslistan (2026-07-27):
13-veckors framtidsavkastning beräknas varje vecka, så två intilliggande
träningsrader för SAMMA ticker delar 12 av 13 veckors framtidsdata. Det
är inte forward leakage (embargot vid train/val/test-gränsen är korrekt),
men den EFFEKTIVA oberoende stickprovsstorleken är mycket mindre än
antalet rader antyder - vilket kan göra early stopping känsligare för
brus än det ser ut (modellen "ser" i praktiken bara ~1/13 så många
oberoende observationer som radantalet visar).

Kontrolltest: träna på var FORWARD_WEEKS:e (13:e) datum i stället för
varje vecka - varje kvarvarande tränings-rad har då ett HELT
icke-överlappande 13-veckorsfönster. Valideringen (early stopping +
kalibrering) och testfönstret hålls OFÖRÄNDRADE (full veckovis
upplösning) - annars blandas "mindre överlapp" ihop med "mindre
valideringsdata att mäta på".

VIKTIG METODOLOGISK RESERVATION: detta minskar tränings-radantalet ~13x
(inte bara "avlägsnar korrelation") - ett genuint isolerat test hade
behövt MER kalenderhistorik för att kompensera, vilket inte är görbart
inom samma dev-fönster. Resultatet ska alltså tolkas som "påverkar
drastiskt färre, icke-överlappande observationer generaliseringen" -
inte en ren isolering av "överlapp" oberoende av datamängd.

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_nonoverlapping_labels.py
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
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_objective_comparison import (
    _slice_sorted, _eval_on_test, _rank_stability, _build_signals_for_backtest,
)


def _non_overlapping_dates(dates, step: int) -> pd.DatetimeIndex:
    uniq = pd.DatetimeIndex(sorted(set(dates)))
    return uniq[::step]


def _train_cls_nonoverlap(train_sub_full: pd.DataFrame, val_d: pd.DatetimeIndex, dev_df: pd.DataFrame,
                           step: int):
    non_overlap_dates = _non_overlapping_dates(train_sub_full.index, step)
    train_sub = train_sub_full[train_sub_full.index.isin(non_overlap_dates)]

    X_tr = train_sub[FEATURE_COLS].fillna(0).values
    y_tr = train_sub["target_signal"].values

    val_dates_sorted = pd.DatetimeIndex(val_d).sort_values().unique()
    split_i = int(len(val_dates_sorted) * (1 - CALIBRATION_VAL_FRACTION))
    val_d_stop, val_d_calib = val_dates_sorted[:split_i], val_dates_sorted[split_i:]

    stop_sub = _slice_sorted(dev_df, val_d_stop) if len(val_d_stop) else _slice_sorted(dev_df, val_d)
    calib_sub = _slice_sorted(dev_df, val_d_calib) if len(val_d_calib) >= 1 else _slice_sorted(dev_df, val_d)
    if len(calib_sub) < 30:
        stop_sub = calib_sub = _slice_sorted(dev_df, val_d)

    X_va_stop = stop_sub[FEATURE_COLS].fillna(0).values
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

    X_va_calib = calib_sub[FEATURE_COLS].fillna(0).values
    y_va_calib = calib_sub["target_signal"].values
    raw_calib = model.predict(X_va_calib)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_calib, y_va_calib)
    return model, calibrator, len(train_sub), len(train_sub_full)


def main():
    step = int(config.FORWARD_WEEKS)
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))
    print(f"[nonoverlap] step={step} (var {step}:e vecka i träningen), {len(splits)} splits.\n")

    per_split_rows = []
    full_scores = {"baseline": [], "non_overlapping": []}
    last_model, last_calibrator = None, None
    row_reduction = []

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 10:
            continue
        X_te = test_sub[FEATURE_COLS].fillna(0).values

        raw_base = lgbm.cls_models[i].predict(X_te)
        cal_base = lgbm.calibrators[i].transform(raw_base) if i < len(lgbm.calibrators) else raw_base

        model, calibrator, n_kept, n_full = _train_cls_nonoverlap(train_sub, val_d, dev_df, step)
        row_reduction.append((n_kept, n_full))
        last_model, last_calibrator = model, calibrator
        raw_no = model.predict(X_te)
        cal_no = calibrator.transform(raw_no)

        for name, raw in (("baseline", cal_base), ("non_overlapping", cal_no)):
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)} (tränings-rader {n_kept}/{n_full}): "
              f"baseline IC={per_split_rows[-2]['test_ic']:+.3f} | "
              f"non_overlapping IC={per_split_rows[-1]['test_ic']:+.3f}")

    total_kept = sum(k for k, _ in row_reduction)
    total_full = sum(f for _, f in row_reduction)
    print(f"\n[nonoverlap] Totalt tränings-rader: {total_kept}/{total_full} "
          f"({total_kept/total_full:.1%} kvar efter icke-överlappande urval).")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[nonoverlap] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].fillna(0).values
        last_i = len(lgbm.cls_models) - 1
        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho)
        cal_base_ho = (lgbm.calibrators[last_i].transform(raw_base_ho)
                       if last_i < len(lgbm.calibrators) else raw_base_ho)
        raw_no_ho = last_model.predict(X_ho)
        cal_no_ho = last_calibrator.transform(raw_no_ho)
        for name, raw in (("baseline", cal_base_ho), ("non_overlapping", cal_no_ho)):
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/nonoverlap_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per variant (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "ndcg_at_10", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/nonoverlap_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} utbytt per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/nonoverlap_stability.csv", index=False)

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
    pd.DataFrame(backtest_rows).to_csv("results/nonoverlap_backtest.csv", index=False)
    print(f"\n[nonoverlap] Klart.")


if __name__ == "__main__":
    main()
