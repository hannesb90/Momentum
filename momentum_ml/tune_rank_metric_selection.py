"""
tune_rank_metric_selection.py – Punkt 8 i uppföljningslistan (2026-07-27):
tränings-EARLY STOPPING (och därmed valet av "bästa" iteration/modell)
styrs idag av AUC på valideringsfönstret (config.LGBM_PARAMS["metric"]).
AUC mäter binär klassificeringskvalitet mot target_signal - men det som
faktiskt avgör portföljresultatet är RANGORDNINGSKVALITET mot den
KONTINUERLIGA framtida avkastningen (target_return), vilket är ett annat
mått. Spearman-korrelation mellan predicerad sannolikhet och en BINÄR
label är dessutom matematiskt bara en omskalad AUC (Mann-Whitney U) - att
byta till "Rank IC mot target_signal" hade alltså INTE varit ett giltigt
test av något nytt. Det som testas här är i stället Rank IC/NDCG@10 mot
target_return (den kontinuerliga framtida avkastningen) - det faktiska
målet för portföljkonstruktionen.

Objectivet (binär klassificering, samma loss/gradienter som produktionen)
ändras INTE - bara VILKEN METRIK som avgör var early stopping stannar och
vilken iteration som väljs som "bäst". Två varianter:

  rank_ic_selection – custom feval: medel-Spearman (pred vs target_return)
                      PER VALIDERINGSDATUM (tvärsnittsmått, inte poolat
                      över alla datum - annars mäts kalendertid-drift
                      snarare än rangordning inom en vecka).
  ndcg10_selection  – custom feval: medel-NDCG@10 PER VALIDERINGSDATUM,
                      relevans = ordinal decil (0-9) av target_return
                      inom datumet (samma decil-konstruktion som
                      tune_objective_comparison.py använder för LambdaRank-
                      utvärderingen).

params["metric"]="None" stänger av LightGBM:s inbyggda AUC-spårning helt,
så early stopping/best_iteration styrs uteslutande av feval-måttet - annars
hade båda metrikerna spårats parallellt och det hade varit tvetydigt vilken
som faktiskt avgjorde stoppunkten.

Kalibreringen (isotonic mot target_signal) är OFÖRÄNDRAD i alla varianter -
den kalibrerar bara den redan färdigtränade modellens rå output till en
sannolikhet, den påverkar inte vilken iteration som valdes.

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_rank_metric_selection.py
"""
import sys

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
    _slice_sorted, _eval_on_test, _decile_labels, _ndcg_at_k,
    _rank_stability, _build_signals_for_backtest,
)


def _make_rank_ic_feval(dates_val: np.ndarray, ret_val: np.ndarray):
    def feval(preds, _dataset):
        df = pd.DataFrame({"pred": preds, "ret": ret_val, "date": dates_val})
        ics = []
        for _, g in df.groupby("date"):
            if len(g) < 10 or g["pred"].nunique() < 2:
                continue
            ic = pd.Series(g["pred"].values).corr(pd.Series(g["ret"].values), method="spearman")
            if pd.notna(ic):
                ics.append(ic)
        val = float(np.mean(ics)) if ics else 0.0
        return "rank_ic", val, True  # higher is better
    return feval


def _make_ndcg10_feval(dates_val: np.ndarray, decile_val: np.ndarray):
    def feval(preds, _dataset):
        df = pd.DataFrame({"pred": preds, "decile": decile_val, "date": dates_val})
        ndcgs = []
        for _, g in df.groupby("date"):
            if len(g) < 10 or g["decile"].notna().sum() < 10:
                continue
            ndcgs.append(_ndcg_at_k(g["decile"].fillna(0).values, g["pred"].values, k=10))
        val = float(np.mean(ndcgs)) if ndcgs else 0.0
        return "ndcg10", val, True  # higher is better
    return feval


def _train_cls_custom_selection(train_sub: pd.DataFrame, val_d: pd.DatetimeIndex,
                                 dev_df: pd.DataFrame, metric_name: str):
    """IDENTISKT objective/features/data som produktionens _fit_cls - enda
    skillnaden är VILKEN METRIK early stopping/best_iteration styrs av."""
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
    dates_val = stop_sub.index.values

    if metric_name == "rank_ic":
        custom_feval = _make_rank_ic_feval(dates_val, stop_sub["target_return"].values)
    else:
        custom_feval = _make_ndcg10_feval(dates_val, _decile_labels(stop_sub).values)

    params = {**config.LGBM_PARAMS, "objective": "binary", "metric": "None"}
    p = {k: v for k, v in params.items() if k not in ("n_estimators", "early_stopping_rounds")}
    ds_tr = lgb.Dataset(X_tr, label=y_tr)
    ds_va = lgb.Dataset(X_va_stop, label=y_va_stop, reference=ds_tr)
    model = lgb.train(
        p, ds_tr, num_boost_round=params["n_estimators"], valid_sets=[ds_va],
        feval=custom_feval,
        callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False),
                   lgb.log_evaluation(period=-1)],
    )

    X_va_calib = calib_sub[FEATURE_COLS].fillna(0).values
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
    variants = ["rank_ic", "ndcg10"]
    print(f"[rank_metric_selection] {len(splits)} splits, varianter: baseline (AUC), {variants}\n")

    per_split_rows = []
    full_scores = {"baseline": [], "rank_ic_selection": [], "ndcg10_selection": []}
    last_models = {}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 10:
            continue
        X_te = test_sub[FEATURE_COLS].fillna(0).values

        raw_base = lgbm.cls_models[i].predict(X_te)
        cal_base = lgbm.calibrators[i].transform(raw_base) if i < len(lgbm.calibrators) else raw_base
        results = {"baseline": cal_base}

        for metric_name, key in (("rank_ic", "rank_ic_selection"), ("ndcg10", "ndcg10_selection")):
            model, calibrator = _train_cls_custom_selection(train_sub, val_d, dev_df, metric_name)
            last_models[key] = (model, calibrator)
            raw = model.predict(X_te)
            results[key] = calibrator.transform(raw)

        for name, raw in results.items():
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"baseline IC={per_split_rows[-3]['test_ic']:+.3f} | "
              f"rank_ic_sel IC={per_split_rows[-2]['test_ic']:+.3f} ndcg10={per_split_rows[-2]['ndcg_at_10']} | "
              f"ndcg10_sel IC={per_split_rows[-1]['test_ic']:+.3f} ndcg10={per_split_rows[-1]['ndcg_at_10']}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[rank_metric_selection] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].fillna(0).values
        last_i = len(lgbm.cls_models) - 1
        raw_base_ho = lgbm.cls_models[last_i].predict(X_ho)
        cal_base_ho = (lgbm.calibrators[last_i].transform(raw_base_ho)
                       if last_i < len(lgbm.calibrators) else raw_base_ho)
        ho_results = {"baseline": cal_base_ho}
        for key, (model, calibrator) in last_models.items():
            raw_ho = model.predict(X_ho)
            ho_results[key] = calibrator.transform(raw_ho)
        for name, raw in ho_results.items():
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/rank_metric_selection_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per variant (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "ndcg_at_10", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/rank_metric_selection_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} utbytt per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/rank_metric_selection_stability.csv", index=False)

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
    pd.DataFrame(backtest_rows).to_csv("results/rank_metric_selection_backtest.csv", index=False)
    print(f"\n[rank_metric_selection] Klart.")


if __name__ == "__main__":
    main()
