"""
tune_objective_comparison.py – Samma features, samma walk-forward-splits,
tre olika LightGBM-objectives (session 2026-07-26, uppföljning på
abstention/breadth-gate-forskningen - en annan vinkel: kan modellen bli
bättre av att träna mot RANGORDNINGEN direkt i stället för att härleda
den från en binär klassificerare?):

  binary_classification – nuvarande produktionsobjective (baseline),
                           återanvänder redan tränade cls_models/
                           calibrators från abstention_lgbm.pkl.
  regression             – återanvänder redan tränade reg_models från
                           SAMMA träningskörning (fit_walk_forward
                           tränar redan båda per split).
  lambdarank             – NY träning per split: query-grupp = ETT
                           veckodatum (alla tickers samma vecka), relevans
                           = ordinal decil (0-9) av target_return INOM
                           det datumet. Utan korrekt datumgruppering vore
                           det inte ett giltigt test - LightGBM:s
                           lambdarank optimerar rangordning INOM en grupp,
                           och en grupp måste vara "alla kandidater som
                           faktiskt konkurrerar om samma portföljplatser
                           samma vecka", inte hela historiken på en gång.

Utvärdering (i den ordning användaren efterfrågade):
  1. Rank IC (Spearman, rå score vs target_return), NDCG@10 (rå
     score-ordning vs decil-relevans), topp-decil-edge - INNAN
     portföljfilter, på exakt samma 31 testfönster för alla tre.
  2. Rankstabilitet: hur ofta byter topp-N (=config.MAX_POSITIONS)
     identitet mellan rebalanseringar, per objective.
  3. Score-upplösning (n_unika, största platå) - samma mått som
     calibration_check.py använder för isotonic-platån.
  4. Fullständigt backtest (CAGR/Sharpe/MaxDD, dev+holdout) - topp-N
     LIKAVIKTAT för alla tre (isolerar rangordningskvaliteten, blandar
     inte in sizing-skillnader).

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_objective_comparison.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from models.ensemble import _topn_invested_weights
from backtest.calibration_check import prob_resolution_stats
from backtest.backtester import MomentumBacktester
from tune_abstention_gate import _load_state, _run_backtest, _pct


def _slice_sorted(df: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    return df[df.index.isin(dates)].sort_index()


def _decile_labels(sub: pd.DataFrame, target_col: str = "target_return") -> pd.Series:
    def _decile(s: pd.Series) -> pd.Series:
        if s.notna().sum() < 10:
            return pd.Series(np.nan, index=s.index)
        try:
            return pd.qcut(s, 10, labels=False, duplicates="drop").astype(float)
        except ValueError:
            return pd.Series(np.nan, index=s.index)
    return sub.groupby(level=0)[target_col].transform(_decile)


def _lambdarank_xyg(sub: pd.DataFrame):
    sub = sub.copy()
    sub["_decile"] = _decile_labels(sub)
    sub = sub.dropna(subset=["_decile"]).sort_index()
    X = sub[FEATURE_COLS].fillna(0).values
    y = sub["_decile"].values.astype(int)
    group = sub.groupby(level=0).size().values
    return X, y, group


def _train_lambdarank(train_sub: pd.DataFrame, val_sub: pd.DataFrame) -> lgb.Booster:
    """Tränar en LambdaRank-modell för EN split. Query-grupp = datum (alla
    tickers samma vecka), relevans = ordinal decil (0-9) av target_return
    INOM det datumet - rader utan giltig decil (för få bolag den veckan)
    exkluderas helt innan gruppstorlekarna räknas, annars stämmer inte
    group-arrayen mot raderna LightGBM faktiskt får. Early stopping mot
    NDCG@10 på valideringsfönstret, exakt samma disciplin (och samma
    tålamod/n_estimators-budget) som _fit_cls/_fit_reg använder för de
    andra två objectiven - annars är jämförelsen orättvis (fast antal
    rundor för det ena, tidigt-stoppat för de andra)."""
    X_tr, y_tr, group_tr = _lambdarank_xyg(train_sub)
    X_va, y_va, group_va = _lambdarank_xyg(val_sub)

    # label_gain sätts INTE explicit - LightGBM:s default för lambdarank
    # är exponentiell gain (2^rel - 1) för heltalsrelevans, samma
    # gain-funktion som _ndcg_at_k använder här i skriptet. Att sätta ett
    # eget (t.ex. linjärt) label_gain hade tyst bytt vad modellen
    # optimerar mot jämfört med vad utvärderingen mäter.
    params = {**config.LGBM_PARAMS, "objective": "lambdarank", "metric": ["ndcg"], "eval_at": [10]}
    p = {k: v for k, v in params.items() if k not in ("n_estimators", "early_stopping_rounds")}
    ds_tr = lgb.Dataset(X_tr, label=y_tr, group=group_tr)
    ds_va = lgb.Dataset(X_va, label=y_va, group=group_va, reference=ds_tr)
    model = lgb.train(
        p, ds_tr, num_boost_round=params["n_estimators"], valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False),
                   lgb.log_evaluation(period=-1)],
    )
    return model


def _ndcg_at_k(rel_true: np.ndarray, score_pred: np.ndarray, k: int = 10) -> float:
    if len(rel_true) == 0:
        return float("nan")
    k = min(k, len(rel_true))
    order = np.argsort(-score_pred)[:k]
    discounts = np.log2(np.arange(2, k + 2))
    dcg = float(np.sum((2.0 ** rel_true[order] - 1) / discounts))
    ideal_order = np.argsort(-rel_true)[:k]
    idcg = float(np.sum((2.0 ** rel_true[ideal_order] - 1) / discounts))
    return dcg / idcg if idcg > 0 else float("nan")


def _eval_on_test(test_sub: pd.DataFrame, raw_score: np.ndarray) -> dict:
    test_sub = test_sub.copy()
    test_sub["_raw"] = raw_score
    test_sub["_decile"] = _decile_labels(test_sub)

    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))

    edges, ndcgs = [], []
    for date, g in test_sub.groupby(level=0):
        if len(g) < 10:
            continue
        cutoff = g["_raw"].quantile(0.9)
        top_ret = g.loc[g["_raw"] >= cutoff, "target_return"].mean()
        edges.append(top_ret - g["target_return"].mean())
        if g["_decile"].notna().sum() >= 10:
            ndcgs.append(_ndcg_at_k(g["_decile"].fillna(0).values, g["_raw"].values, k=10))

    res = prob_resolution_stats(raw_score)
    return {
        "test_ic": ic,
        "test_top_decile_edge": float(np.mean(edges)) if edges else None,
        "ndcg_at_10": float(np.mean(ndcgs)) if ndcgs else None,
        "score_n_unique": res["n_unique"],
        "score_largest_plateau_frac": res["largest_plateau_frac"],
    }


def _topn_by_date(scores_df: pd.DataFrame, n: int) -> dict:
    """date -> set(topp-N tickers efter '_raw', bland de raderna som finns)."""
    out = {}
    for date, g in scores_df.groupby(level=0):
        top = g.sort_values("_raw", ascending=False).head(n)
        out[date] = set(top["ticker"])
    return out


def _rank_stability(scores_df: pd.DataFrame, n: int, rebalance_weeks: int) -> float:
    top_by_date = _topn_by_date(scores_df, n)
    dates = sorted(top_by_date)
    rebal_dates = dates[::max(rebalance_weeks, 1)]
    changes = []
    prev = None
    for d in rebal_dates:
        cur = top_by_date[d]
        if prev is not None and len(prev) > 0:
            changed = len(cur - prev) / len(prev)
            changes.append(changed)
        prev = cur
    return float(np.mean(changes)) if changes else float("nan")


def _build_signals_for_backtest(scores_df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Topp-N LIKAVIKTAT (inte konviktionsviktat) - isolerar rangordnings-
    kvaliteten, blandar inte in sizing-skillnader mellan objectiven. Helt
    vektoriserat (inte iterrows) - annars blir 3 objectiv x ~800 datum x
    ~170 tickers ohanterligt långsamt."""
    df = scores_df.copy()
    rank = df.groupby(level=0)["_raw"].rank(ascending=False, method="first")
    df["pred_signal"] = (rank <= n).astype(int)
    n_selected = df.groupby(level=0)["pred_signal"].transform("sum").replace(0, 1)
    df["position_size"] = df["pred_signal"] / n_selected
    df["prob_up"] = 0.5
    df["prob_raw"] = df["_raw"]
    df["pred_return"] = 0.0
    df["selection_eligible"] = 1
    return df[["ticker", "prob_up", "prob_raw", "pred_return",
               "selection_eligible", "pred_signal", "position_size"]]


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))
    print(f"[objective] {len(splits)} splits, topp-{n_top}, ombalansering var {rebalance_weeks}:e vecka.\n")

    per_split_rows = []
    full_scores = {"binary_classification": [], "regression": [], "lambdarank": []}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 10:
            continue
        X_te = test_sub[FEATURE_COLS].fillna(0).values

        # 1) Baseline - redan tränad binär klassificerare + kalibrator.
        raw_cls = lgbm.cls_models[i].predict(X_te)
        cal_cls = lgbm.calibrators[i].transform(raw_cls) if i < len(lgbm.calibrators) else raw_cls

        # 2) Regression - redan tränad regressor (SAMMA körning, samma split).
        raw_reg = lgbm.reg_models[i].predict(X_te)

        # 3) LambdaRank - ny träning för just denna split.
        rank_model = _train_lambdarank(train_sub, val_sub)
        raw_rank = rank_model.predict(X_te)
        last_rank_model = rank_model   # sista LYCKADE splitten - används för holdout-extrapolering nedan

        for name, raw in (("binary_classification", cal_cls), ("regression", raw_reg), ("lambdarank", raw_rank)):
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"cls IC={per_split_rows[-3]['test_ic']:+.3f} edge={per_split_rows[-3]['test_top_decile_edge']} | "
              f"reg IC={per_split_rows[-2]['test_ic']:+.3f} edge={per_split_rows[-2]['test_top_decile_edge']} | "
              f"rank IC={per_split_rows[-1]['test_ic']:+.3f} edge={per_split_rows[-1]['test_top_decile_edge']} "
              f"ndcg10={per_split_rows[-1]['ndcg_at_10']}")

    # Holdout-perioden (fryst, efter purge_start) täcks INTE av något av de
    # 31 testfönstren - utan detta skulle backtesten sakna holdout-data helt
    # (bekräftat: kraschade första körningen). Extrapolerar sista splittens
    # modeller till holdouten, exakt samma konvention som
    # MomentumLGBM.predict()/_select_model_idx redan använder för
    # live/serving-datum bortom sista testfönstret.
    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[objective] Extrapolerar sista splittens modeller till holdout "
              f"({holdout_dates.min().date()} -> {holdout_dates.max().date()}, {len(holdout_dates)} veckor)...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].fillna(0).values
        last_i = len(lgbm.cls_models) - 1

        raw_cls_ho = lgbm.cls_models[last_i].predict(X_ho)
        cal_cls_ho = (lgbm.calibrators[last_i].transform(raw_cls_ho)
                      if last_i < len(lgbm.calibrators) else raw_cls_ho)
        raw_reg_ho = lgbm.reg_models[last_i].predict(X_ho)
        raw_rank_ho = last_rank_model.predict(X_ho)

        for name, raw in (("binary_classification", cal_cls_ho), ("regression", raw_reg_ho),
                          ("lambdarank", raw_rank_ho)):
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/objective_comparison_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per objective (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "ndcg_at_10", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/objective_comparison_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} som byts ut per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/objective_comparison_stability.csv", index=False)

    print(f"\n{'='*100}\nFullständigt backtest (topp-{n_top} likaviktat, dev+holdout)\n{'='*100}")
    bench_ticker = None
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
    pd.DataFrame(backtest_rows).to_csv("results/objective_comparison_backtest.csv", index=False)
    print(f"\n[objective] Klart. Alla CSV:er sparade i results/objective_comparison_*.csv")


if __name__ == "__main__":
    main()
