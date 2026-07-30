"""
tune_sector_categorical.py – Punkt 6 i uppföljningslistan (2026-07-27,
KORRIGERAD 2026-07-29): sector_code kodas idag ORDINALT
(features/feature_engineering.py::_category_code, index i
config.SECTOR_CATEGORIES-listan) - LightGBM behandlar den då som en vanlig
numerisk feature med en RIKTNING (sektor 5 antas ligga "mellan" sektor 2 och
sektor 8 i något meningsfullt avseende), trots att listans ordning är helt
godtycklig (bara den ordning sektorerna råkade läggas till i config.py,
ingen verklig gradient från t.ex. "cyklisk" till "defensiv").

LightGBM har NATIV kategorisk hantering (categorical_feature=[...] till
lgb.Dataset) som vid varje split hittar den bästa GRUPPERINGEN av
kategorier (optimal partition-sökning på trän-target), utan att anta någon
ordning alls. (cap_tier_code testas INTE här - den listan har en genuin
ordning, Mega->Nano Cap, så ordinal kodning är rimlig för den.)

KORRIGERING 2026-07-29: den ursprungliga körningen tränade
"categorical_sector"-varianten med objective="binary" + config.LGBM_PARAMS
(num_leaves=63, subsample=0.8, n_estimators=1000) medan "baseline" var
lgbm.cls_models[i] - den RIKTIGA produktionsmodellen (objective="lambdarank",
num_leaves=31, 500 boost rounds). En jämförelse mellan två olika
modellfamiljer, inte en isolerad test av bara categorical_feature. Nu tränas
BÅDA varianterna om från grunden med IDENTISK LambdaRank-uppsättning
(tune_lambdarank_common.py, samma hyperparametrar som produktionen hämtade
direkt från en riktig MomentumLGBM()-instans) - enda skillnaden är
categorical_feature=[sector_code] eller inte. Ingen isotonic-kalibrering
längre (produktionens LambdaRank-scores kalibreras inte heller, se Test 8).

Kräver att 'tune_abstention_gate.py fetch' redan körts (bara features/data,
inte den gamla lgbm-modellen - båda varianter tränas om här).

    /opt/momentum/venv/bin/python3 tune_sector_categorical.py
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
from tune_objective_comparison import _rank_stability, _build_signals_for_backtest
from tune_lambdarank_common import _slice_sorted, train_lambdarank_split

_SECTOR_IDX = FEATURE_COLS.index("sector_code")


def _eval_on_test(test_sub: pd.DataFrame, raw_score: np.ndarray) -> dict:
    tmp = test_sub.copy()
    tmp["_raw"] = raw_score
    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))
    edges = []
    for date, g in tmp.groupby(level=0):
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


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    n_top = int(config.MAX_POSITIONS)
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    n_sectors = dev_df["sector_code"].nunique()
    print(f"[sector_categorical] KORRIGERAD: båda varianter tränas som LambdaRank, "
          f"identiskt med produktionen förutom categorical_feature. "
          f"{n_sectors} distinkta sector_code-värden (feature-index {_SECTOR_IDX}), "
          f"{len(splits)} splits.\n")

    per_split_rows = []
    full_scores = {"baseline": [], "categorical_sector": []}
    last_models = {}

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 100:
            continue
        X_te = test_sub[FEATURE_COLS].values

        model_base = train_lambdarank_split(train_sub, val_d, dev_df)
        model_cat = train_lambdarank_split(train_sub, val_d, dev_df, categorical_feature=[_SECTOR_IDX])
        last_models["baseline"] = model_base
        last_models["categorical_sector"] = model_cat

        raw_base = model_base.predict(X_te)
        raw_cat = model_cat.predict(X_te)

        for name, raw in (("baseline", raw_base), ("categorical_sector", raw_cat)):
            metrics = _eval_on_test(test_sub, raw)
            per_split_rows.append({"split": i + 1, "objective": name, **metrics})
            sdf = test_sub[["ticker"]].copy()
            sdf["_raw"] = raw
            full_scores[name].append(sdf)

        print(f"  split {i+1}/{len(splits)}: "
              f"baseline IC={per_split_rows[-2]['test_ic']:+.3f} | "
              f"categorical_sector IC={per_split_rows[-1]['test_ic']:+.3f}")

    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print(f"\n[sector_categorical] Extrapolerar sista splittens modeller till holdout...")
        holdout_sub = _slice_sorted(model_df, holdout_dates)
        X_ho = holdout_sub[FEATURE_COLS].values
        for name, model in last_models.items():
            sdf = holdout_sub[["ticker"]].copy()
            sdf["_raw"] = model.predict(X_ho)
            full_scores[name].append(sdf)

    per_split_df = pd.DataFrame(per_split_rows)
    per_split_df.to_csv("results/sector_categorical_per_split.csv", index=False)

    print(f"\n{'='*100}\nMedian över {len(splits)} splits, per variant (innan portföljfilter)\n{'='*100}")
    summary = per_split_df.groupby("objective")[
        ["test_ic", "test_top_decile_edge", "score_n_unique", "score_largest_plateau_frac"]
    ].median()
    print(summary.to_string())
    summary.to_csv("results/sector_categorical_summary.csv")

    print(f"\n{'='*100}\nRankstabilitet (andel av topp-{n_top} utbytt per rebalansering)\n{'='*100}")
    stability_rows = []
    for name, frames in full_scores.items():
        scores_df = pd.concat(frames)
        stab = _rank_stability(scores_df, n_top, rebalance_weeks)
        stability_rows.append({"objective": name, "mean_topn_turnover": stab})
        print(f"  {name:22s}: {stab:.1%}")
    pd.DataFrame(stability_rows).to_csv("results/sector_categorical_stability.csv", index=False)

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
    pd.DataFrame(backtest_rows).to_csv("results/sector_categorical_backtest.csv", index=False)
    print(f"\n[sector_categorical] Klart.")


if __name__ == "__main__":
    main()
