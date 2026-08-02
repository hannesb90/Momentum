"""
tune_riskadj_momentum_ablation.py – ALFA_TESTER_2026-07-30.md #1: full
LambdaRank-ablation av riskjusterad momentum. Uppföljning på #123
(tune_riskadj_momentum_ic.py), som bara mätte SOLO-IC för
mom_12_1/rvol_26w och roc_13w/rvol_13w isolerat - inget bevis för att de
förbättrar HELA modellen. Detta kör den riktiga ablationen: baslinje,
+12-1-riskjusterad, +13v-riskjusterad, båda - identisk LambdaRank-träning
i övrigt (samma disciplin som Test 5/tune_regime_feature.py ikväll).

FÖRREGISTRERAT (låst innan körning, ändras INTE efter att resultatet setts):
  - Nämnare: rvol_26w för mom_12_1, rvol_13w för roc_13w (samma fönster
    #123 redan validerade solo-IC för - inget nytt sök efter bättre fönster).
  - 25 walk-forward-splits, samma kostnader/segment (large) som alla
    kvällens tester.
  - Beslutsmått: median split-IC/NDCG@10 (dev-splits) + extrapolering till
    den BEFINTLIGA holdouten. OBS holdouten räknas som redan
    forskningsexponerad (många tidigare tester ikväll har tittat på den) -
    behandlas här ENDAST som diagnostik, inte som bevis, per
    ALFA_TESTER_2026-07-30.md:s egen disciplin (punkt 4) - det finns ingen
    genuint orörd senare period ännu (data slutar vid dagens datum).

    /opt/momentum/venv/bin/python3 tune_riskadj_momentum_ablation.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg = config.SEGMENTS[segment]

import numpy as np
import pandas as pd
import lightgbm as lgb

from features.feature_engineering import to_model_df, FEATURE_COLS
if "drop_features" in seg:
    dropped_set = set(seg["drop_features"])
    filtered = [c for c in FEATURE_COLS if c not in dropped_set]
    FEATURE_COLS.clear()
    FEATURE_COLS.extend(filtered)
from models.lgbm_model import walk_forward_splits
from backtest.calibration_check import prob_resolution_stats
from tune_abstention_gate import _load_state, _run_backtest, _pct
from tune_lambdarank_common import _slice_sorted, _relevance_labels, _date_weights, production_params

VARIANTS = {
    "baseline": [],
    "mom_riskadj": ["mom_12_1_riskadj"],
    "roc13_riskadj": ["roc13_riskadj"],
    "both": ["mom_12_1_riskadj", "roc13_riskadj"],
}


def _add_riskadj_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mom_12_1_riskadj"] = df["mom_12_1"] / df["rvol_26w"].clip(lower=0.02)
    df["roc13_riskadj"] = df["roc_13w"] / df["rvol_13w"].clip(lower=0.02)
    return df


def _train(train_sub, val_d, dev_df, feature_cols):
    X_tr = train_sub[feature_cols].values
    y_tr_rel = _relevance_labels(train_sub)
    train_groups = train_sub.groupby(level=0).size().values
    w_tr = _date_weights(train_sub)

    val_sub = _slice_sorted(dev_df, val_d)
    X_va = val_sub[feature_cols].values
    y_va_rel = _relevance_labels(val_sub)
    val_groups = val_sub.groupby(level=0).size().values

    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)
    return lgb.train(
        production_params(), ds_tr, num_boost_round=500, valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )


def _eval_on_test(test_sub, raw_score):
    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))
    res = prob_resolution_stats(raw_score)
    edges = []
    tmp = test_sub.copy()
    tmp["_raw"] = raw_score
    for date, g in tmp.groupby(level=0):
        if len(g) < 10:
            continue
        cutoff = g["_raw"].quantile(0.9)
        edges.append(g.loc[g["_raw"] >= cutoff, "target_return"].mean() - g["target_return"].mean())
    return {"test_ic": ic, "top_decile_edge": float(np.mean(edges)) if edges else None, "n_unique": res["n_unique"]}


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    model_df = _add_riskadj_cols(model_df)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    print(f"[riskadj_ablation] {len(splits)} splits, {len(VARIANTS)} varianter (förregistrerat, ej ändrat efteråt).\n")

    base_cols = list(FEATURE_COLS)
    variant_cols = {name: base_cols + extra for name, extra in VARIANTS.items()}
    last_models = {}

    rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 100:
            continue
        line = f"  split {i+1}/{len(splits)}:"
        for name, cols in variant_cols.items():
            model = _train(train_sub, val_d, dev_df, cols)
            last_models[name] = model
            raw = model.predict(test_sub[cols].values)
            m = _eval_on_test(test_sub, raw)
            rows.append({"split": i + 1, "variant": name, **m})
            line += f" {name}={m['test_ic']:+.3f}"
        print(line)

    df = pd.DataFrame(rows)
    print("\n" + "=" * 90)
    print("Median test-IC/top-decile-edge per variant (dev-splits)")
    print("=" * 90)
    med = df.groupby("variant")[["test_ic", "top_decile_edge"]].median()
    print(med.reindex(VARIANTS.keys()).to_string(float_format=lambda x: f"{x:+.4f}"))

    # Extrapolering till BEFINTLIG holdout (diagnostik, ej bevis - se moduldocstring)
    holdout_dates = all_dates[all_dates >= holdout_start]
    if len(holdout_dates):
        print("\n" + "=" * 90)
        print("Extrapolering till befintlig holdout (DIAGNOSTIK, redan forskningsexponerad - ej bevis)")
        print("=" * 90)
        holdout_sub = model_df[model_df.index.isin(holdout_dates)]
        for name, cols in variant_cols.items():
            model = last_models[name]
            raw = model.predict(holdout_sub[cols].values)
            m = _eval_on_test(holdout_sub, raw)
            print(f"  {name:<16}: IC={m['test_ic']:+.4f}  top_decile_edge={m['top_decile_edge']:+.4f}")

    print("\n[riskadj_ablation] Klart.")


if __name__ == "__main__":
    main()
