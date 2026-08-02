"""
tune_rank_metric_selection.py – Punkt 8 i uppföljningslistan (2026-07-27,
KORRIGERAD + OMTOLKAD 2026-07-29).

URSPRUNGLIG PREMISS (felaktig mot nuvarande kod): "tränings-EARLY STOPPING
styrs idag av AUC på valideringsfönstret". Det stämmer INTE mot den
(oincheckade) LambdaRank-koden i models/lgbm_model.py::fit_walk_forward -
den tränar OCH early-stoppar redan mot NDCG (LightGBM:s inbyggda "ndcg"-
mått, ndcg_eval_at=[10, 20]) på KVINTIL-relevans (qcut(5) av target_return
INOM varje datum, samma etiketter används som träningsmål OCH som
early-stopping-facit).

KORRIGERING (samma binär-vs-lambdarank-confound som Test 5/7): de två
"förbättrings"-varianterna tränades ursprungligen med objective="binary" +
config.LGBM_PARAMS - en helt annan modellfamilj än produktionens
LambdaRank-baseline. Omskriven att träna BÅDA sidor identiskt (samma
LambdaRank-objective, hyperparametrar, kvintil-TRÄNINGSlabels, group=,
equal-date-weight - via tune_lambdarank_common.py) och bara variera VILKEN
METRIK som styr early stopping/best_iteration.

DEN SMALARE, FORTFARANDE ÖPPNA FRÅGAN: hjälper det att early-stoppa mot en
FINARE decil-baserad (10 nivåer, inte 5) NDCG@10 på den KONTINUERLIGA
target_return, i stället för produktionens grövre kvintil-NDCG@[10,20]
(som mäts på samma diskretiserade etiketter modellen tränas mot - riskerar
att belöna att bara memorera kvintilgränserna snarare än den finare
rangordningen)? Testar också rank-IC (Spearman mot kontinuerlig
target_return) som ett tredje alternativ, som i originalet.

Kräver att 'tune_abstention_gate.py fetch' redan körts (bara features/data
- alla tre varianter tränas om här, ingen gammal lgbm-modell återanvänds).

    /opt/momentum/venv/bin/python3 tune_rank_metric_selection.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

import numpy as np
import pandas as pd

from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from backtest.calibration_check import prob_resolution_stats
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_objective_comparison import (
    _rank_stability, _build_signals_for_backtest, _decile_labels, _ndcg_at_k,
)
from tune_lambdarank_common import _slice_sorted, train_lambdarank_split


def _make_ndcg10_feval(dates_val: np.ndarray, decile_val: np.ndarray):
    def feval(preds, _dataset):
        df = pd.DataFrame({"pred": preds, "decile": decile_val, "date": dates_val})
        ndcgs = []
        for _, g in df.groupby("date"):
            if len(g) < 10 or g["decile"].notna().sum() < 10:
                continue
            ndcgs.append(_ndcg_at_k(g["decile"].fillna(0).values, g["pred"].values, k=10))
        val = float(np.mean(ndcgs)) if ndcgs else 0.0
        return "ndcg10", val, True
    return feval


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
        return "rank_ic", val, True
    return feval


def _eval_on_test(test_sub: pd.DataFrame, raw_score: np.ndarray) -> dict:
    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))
    tmp = test_sub.copy()
    tmp["_raw"] = raw_score
    edges = []
    ndcgs10 = []
    for date, g in tmp.groupby(level=0):
        if len(g) < 10:
            continue
        cutoff = g["_raw"].quantile(0.9)
        edges.append(g.loc[g["_raw"] >= cutoff, "target_return"].mean() - g["target_return"].mean())
        dec = _decile_labels(g).fillna(0).values
        ndcgs10.append(_ndcg_at_k(dec, g["_raw"].values, k=10))
    res = prob_resolution_stats(raw_score)
    return {
        "test_ic": ic,
        "test_top_decile_edge": float(np.mean(edges)) if edges else None,
        "ndcg_at_10": float(np.mean(ndcgs10)) if ndcgs10 else None,
        "score_n_unique": res["n_unique"],
        "score_largest_plateau_frac": res["largest_plateau_frac"],
    }


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    print(f"[rank_metric_selection] KORRIGERAD: alla varianter tränas som LambdaRank, "
          f"identiskt med produktionen förutom early-stopping-feval. {len(splits)} splits.\n")

    per_split_rows = []
    full_scores = {"baseline": [], "rank_ic_selection": [], "ndcg10_selection": []}
    last_models = {}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 100:
            continue
        X_te = test_sub[FEATURE_COLS].values

        model_base = train_lambdarank_split(train_sub, val_d, dev_df)

        dates_val = val_sub.index.values
        decile_val = _decile_labels(val_sub).values
        feval_ndcg10 = _make_ndcg10_feval(dates_val, decile_val)
        model_ndcg10 = train_lambdarank_split(
            train_sub, val_d, dev_df, feval=feval_ndcg10, disable_builtin_metric=True)

        feval_rankic = _make_rank_ic_feval(dates_val, val_sub["target_return"].values)
        model_rankic = train_lambdarank_split(
            train_sub, val_d, dev_df, feval=feval_rankic, disable_builtin_metric=True)

        last_models = {"baseline": model_base, "ndcg10_selection": model_ndcg10, "rank_ic_selection": model_rankic}

        results = {
            "baseline": model_base.predict(X_te),
            "rank_ic_selection": model_rankic.predict(X_te),
            "ndcg10_selection": model_ndcg10.predict(X_te),
        }
        for name, raw in results.items():
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"baseline IC={per_split_rows[-3]['test_ic']:+.3f} | "
              f"rank_ic_sel IC={per_split_rows[-2]['test_ic']:+.3f} | "
              f"ndcg10_sel IC={per_split_rows[-1]['test_ic']:+.3f}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[rank_metric_selection] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].values
        for name, model in last_models.items():
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = model.predict(X_ho)
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
