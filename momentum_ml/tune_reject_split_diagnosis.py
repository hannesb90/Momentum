"""
tune_reject_split_diagnosis.py – Varför blir score identiska? Del 2: är
degenererade (num_trees<=1) walk-forward-splits orsakade av för hård
LightGBM-regularisering, eller av att signalen genuint saknas i de
perioderna?

Bakgrund (session 2026-07-26): rank-gap-granskningen visade att flera olika
bolag fick bit-identisk rå LGBM-poäng. Spårat till att den AKTIVA splitten
(den som styr dagens signaler) hade num_trees()==best_iteration()==
current_iteration()==1 - LightGBM avbröt boostingen tidigt. En första
hypotes var LightGBM:s egna "no further splits with positive gain"-
terminering (skild från den vanliga 50-rundors tålamodsregeln), men en
uppföljande test-upptäckt visade att eval_history:s längd kan vara STÖRRE
än num_trees() - dvs vanlig tålamods-baserad early stopping (runda 1 var
bäst, ~50 rundor därefter förbättrade inte) är en fullt möjlig förklaring
också. Det här skriptet avgör vilket, empiriskt, i stället för att gissa.

Två faser:

  compare   – för varje walk-forward-split (BASELINE-parametrar): antal
              rader/datum/tickers, positiv targetandel, targetvarians per
              datum, NaN/fill-rate per feature, feature-drift train vs
              validering, initial-AUC + AUC-utveckling (från eval_history).
              Grupperar sedan degenererade mot friska splits.

  grid      – kör om ENDAST de splits som var degenererade under BASELINE
              (+ en kontrollgrupp friska splits) under tre parameteruppsättningar
              (baseline/A/B, minskande regularisering) och jämför
              out-of-sample AUC/rank-IC/score-upplösning på TEST-fönstret
              (aldrig sett av vare sig träning eller early stopping) - inte
              bara antal träd.

OBS om datakälla: main.py raderar sin feature-cache efter varje orkestrerad
körning (se main.py:s _rejected_splits_this_run.flag-undantag, tillagt i
samma session, som förhindrar just detta framöver). Den EXAKTA data som
orsakade produktionens 1-träds-splittar den natten kunde alltså inte
återskapas - det här skriptet använder i stället den nyaste TILLGÄNGLIGA
feature-cachen som en representativ (inte bit-identisk) approximation.
Resultaten ska läsas som "vad denna mekanism gör på likartad data", inte
som en exakt reproduktion av en specifik natts körning.

    /opt/momentum/venv/bin/python3 tune_reject_split_diagnosis.py compare
    /opt/momentum/venv/bin/python3 tune_reject_split_diagnosis.py grid
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from backtest.calibration_check import prob_resolution_stats

CACHE_CANDIDATES = sorted(
    Path("results").glob("_features_cache_*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)

BASELINE = {"reg_lambda": 1.0, "reg_alpha": 0.1, "min_child_samples": 50}
VARIANT_A = {"reg_lambda": 0.5, "reg_alpha": 0.05, "min_child_samples": 30}
VARIANT_B = {"reg_lambda": 0.0, "reg_alpha": 0.0, "min_child_samples": 20}
VARIANTS = {"baseline": BASELINE, "variant_A": VARIANT_A, "variant_B": VARIANT_B}


def _load_dev_df():
    if not CACHE_CANDIDATES:
        raise SystemExit("Ingen feature-cache i results/ - kör main.py minst en gång först.")
    cache = CACHE_CANDIDATES[0]
    print(f"[diagnosis] Laddar feature-cache: {cache} (senast ändrad {pd.Timestamp(cache.stat().st_mtime, unit='s')})")
    all_features = pd.read_pickle(cache)
    model_df = to_model_df(all_features)
    all_dates = model_df.index.unique().sort_values()
    if len(all_dates) > config.HOLDOUT_WEEKS + config.FORWARD_WEEKS:
        purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
        dev_df = model_df[model_df.index < purge_start]
    else:
        dev_df = model_df
    return dev_df


def _slice(df, dates):
    sub = df[df.index.isin(dates)]
    X = sub[FEATURE_COLS].fillna(0).values
    y_cls = sub["target_signal"].values
    y_reg = sub["target_return"].values
    return sub, X, y_cls, y_reg


def _cls_params(overrides: dict) -> dict:
    p = {**config.LGBM_PARAMS, "objective": "binary", **overrides}
    return p


def _train_one(X_tr, y_tr, X_va, y_va, overrides: dict):
    params = _cls_params(overrides)
    p = {k: v for k, v in params.items() if k not in ("n_estimators", "early_stopping_rounds")}
    ds_tr = lgb.Dataset(X_tr, label=y_tr)
    ds_va = lgb.Dataset(X_va, label=y_va, reference=ds_tr)
    evals_result = {}
    model = lgb.train(
        p, ds_tr, num_boost_round=params["n_estimators"], valid_sets=[ds_va],
        callbacks=[
            lgb.early_stopping(params["early_stopping_rounds"], verbose=False),
            lgb.log_evaluation(period=-1),
            lgb.record_evaluation(evals_result),
        ],
    )
    return model, evals_result.get("valid_0", {})


def _feature_nan_rates(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {}
    return {c: float(sub[c].isna().mean()) for c in FEATURE_COLS}


def _feature_drift(train_sub: pd.DataFrame, val_sub: pd.DataFrame) -> float:
    """Medel|z-score| mellan tränings- och valideringsmedelvärdet per
    feature (z mot träningens std) - en enda sammanfattande siffra per
    split för "hur mycket har fördelningen glidit mellan train och val"."""
    zs = []
    for c in FEATURE_COLS:
        tr = train_sub[c].dropna()
        va = val_sub[c].dropna()
        if tr.empty or va.empty:
            continue
        std = tr.std()
        if std and std > 0:
            zs.append(abs(va.mean() - tr.mean()) / std)
    return float(np.mean(zs)) if zs else float("nan")


def cmd_compare():
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)
    print(f"[diagnosis] {len(splits)} walk-forward-splits.\n")

    rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub, X_tr, y_cls_tr, y_reg_tr = _slice(dev_df, train_d)
        val_sub, X_va, y_cls_va, y_reg_va = _slice(dev_df, val_d)
        if len(X_tr) < 100:
            continue

        model, eval_hist = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, BASELINE)
        num_trees = model.num_trees()
        auc_hist = eval_hist.get("auc", [])
        raw_va = model.predict(X_va)
        res = prob_resolution_stats(raw_va)

        target_var_by_date = train_sub.groupby(train_sub.index)["target_return"].var()

        rows.append({
            "split": i + 1,
            "val_start": val_d.min().date().isoformat(),
            "degenerate": num_trees <= 1,
            "num_trees": num_trees,
            "eval_rounds_attempted": len(auc_hist),
            "n_train_rows": len(X_tr), "n_val_rows": len(X_va),
            "n_train_dates": train_sub.index.nunique(), "n_val_dates": val_sub.index.nunique(),
            "n_train_tickers": train_sub["ticker"].nunique() if "ticker" in train_sub else None,
            "n_val_tickers": val_sub["ticker"].nunique() if "ticker" in val_sub else None,
            "positive_share_train": float(y_cls_tr.mean()),
            "positive_share_val": float(y_cls_va.mean()),
            "target_var_median_by_date": float(target_var_by_date.median()),
            "nan_rate_mean": float(np.mean(list(_feature_nan_rates(train_sub).values()))),
            "feature_drift_mean_abs_z": _feature_drift(train_sub, val_sub),
            "val_auc_initial": float(auc_hist[0]) if auc_hist else None,
            "val_auc_best": float(max(auc_hist)) if auc_hist else None,
            "val_score_n_unique": res["n_unique"],
            "val_score_largest_plateau_frac": res["largest_plateau_frac"],
        })
        print(f"  split {i+1}/{len(splits)}: num_trees={num_trees} "
              f"eval_rounds_attempted={len(auc_hist)} auc_initial={rows[-1]['val_auc_initial']} "
              f"auc_best={rows[-1]['val_auc_best']}")

    df = pd.DataFrame(rows)
    out_csv = Path("results/reject_split_comparison.csv")
    df.to_csv(out_csv, index=False)
    print(f"\n[diagnosis] Sparat: {out_csv}\n")

    print(f"{'='*78}\nDegenererade ({df['degenerate'].sum()}) vs friska ({(~df['degenerate']).sum()}) splits\n{'='*78}")
    compare_cols = [
        "n_train_rows", "n_val_rows", "n_train_tickers", "n_val_tickers",
        "positive_share_train", "positive_share_val", "target_var_median_by_date",
        "nan_rate_mean", "feature_drift_mean_abs_z",
        "val_auc_initial", "val_auc_best", "val_score_n_unique", "val_score_largest_plateau_frac",
        "eval_rounds_attempted",
    ]
    summary = df.groupby("degenerate")[compare_cols].median()
    print(summary.T.to_string())
    summary.T.to_csv("results/reject_split_comparison_summary.csv")


def cmd_grid():
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)

    baseline_rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        _, X_tr, y_cls_tr, _ = _slice(dev_df, train_d)
        _, X_va, y_cls_va, _ = _slice(dev_df, val_d)
        if len(X_tr) < 100:
            continue
        model, _ = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, BASELINE)
        baseline_rows.append((i, model.num_trees()))

    degenerate_idx = [i for i, nt in baseline_rows if nt <= 1]
    healthy_idx = [i for i, nt in baseline_rows if nt > 1]
    control_idx = healthy_idx[:: max(len(healthy_idx) // 3, 1)][:3]
    target_splits = sorted(set(degenerate_idx + control_idx))
    print(f"[diagnosis] {len(degenerate_idx)} degenererade splits under BASELINE, "
          f"{len(control_idx)} friska kontrollsplits. Kör grid på {len(target_splits)} splits.\n")

    rows = []
    for i in target_splits:
        train_d, val_d, test_d = splits[i]
        _, X_tr, y_cls_tr, _ = _slice(dev_df, train_d)
        _, X_va, y_cls_va, _ = _slice(dev_df, val_d)
        test_sub, X_te, y_cls_te, y_reg_te = _slice(dev_df, test_d)
        if len(X_te) < 10:
            continue

        for variant_name, overrides in VARIANTS.items():
            model, eval_hist = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, overrides)
            raw_te = model.predict(X_te)
            res_te = prob_resolution_stats(raw_te)

            test_auc = None
            if len(set(y_cls_te)) > 1:
                from sklearn.metrics import roc_auc_score
                test_auc = float(roc_auc_score(y_cls_te, raw_te))
            rank_ic = float(pd.Series(raw_te).corr(pd.Series(y_reg_te), method="spearman"))

            rows.append({
                "split": i + 1, "variant": variant_name,
                "was_degenerate_baseline": i in degenerate_idx,
                "num_trees": model.num_trees(),
                "test_auc": test_auc, "test_rank_ic": rank_ic,
                "test_score_n_unique": res_te["n_unique"],
                "test_score_largest_plateau_frac": res_te["largest_plateau_frac"],
            })
            print(f"  split {i+1} [{variant_name}]: num_trees={model.num_trees()} "
                  f"test_auc={test_auc} rank_ic={rank_ic:.4f}")

    df = pd.DataFrame(rows)
    out_csv = Path("results/reject_split_grid.csv")
    df.to_csv(out_csv, index=False)
    print(f"\n[diagnosis] Sparat: {out_csv}\n")

    print(f"{'='*78}\nMedian per variant, ENDAST splits som var degenererade under BASELINE\n{'='*78}")
    deg = df[df["was_degenerate_baseline"]]
    print(deg.groupby("variant")[["num_trees", "test_auc", "test_rank_ic",
                                    "test_score_n_unique", "test_score_largest_plateau_frac"]].median().to_string())

    print(f"\n{'='*78}\nMedian per variant, kontrollsplits (redan friska under BASELINE)\n{'='*78}")
    ctrl = df[~df["was_degenerate_baseline"]]
    if len(ctrl):
        print(ctrl.groupby("variant")[["num_trees", "test_auc", "test_rank_ic",
                                        "test_score_n_unique", "test_score_largest_plateau_frac"]].median().to_string())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if cmd == "compare":
        cmd_compare()
    elif cmd == "grid":
        cmd_grid()
    else:
        raise SystemExit(f"Okänt kommando: {cmd!r}. Välj 'compare' eller 'grid'.")
