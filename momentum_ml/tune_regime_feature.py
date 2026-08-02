"""
tune_regime_feature.py – [EDGE-3] Steg 1: regimetikett som kategorisk
LambdaRank-feature (EDGE_RISK_SCENARIO_TESTKO.md Tier 2 #7).

Idag används backtest/regime.py::classify_regimes() BARA för att skala
MARKET_FILTER_EXPOSURE i backtestern - primärmodellen får aldrig se regimen
själv och kan alltså inte lära sig regimberoende feature-vikter. Motiverat
av #27d (docs/UTVECKLINGSLOGG.md): ema_cross_21_55/rs_26w tappade
feature-importance efter 2022 års regimbrytning - en modell som VET vilken
regim den är i skulle kunna kompensera.

Metod: EXAKT samma disciplin som Test 5 (tune_sector_categorical.py) - båda
varianter tränas som identisk LambdaRank (tune_lambdarank_common.py:s
production_params(), samma relevanslabels/group/weight), enda skillnaden är
om `regime_code` (0=bull/1=sideways/2=bear, kausalt - classify_regimes()
SMA:n ser bara bakåt) finns med som en NY kategorisk feature eller inte.
Till skillnad från Test 5 (som bara ändrade KODNINGEN av en REDAN
existerande feature) läggs regime_code till som en HELT NY kolumn - baseline
och variant tränas därför med olika FEATURE_COLS-listor (egen lokal
kopia per variant, rör INTE den globala listan andra script importerar).

Segmenterar resultatet explicit i FÖRE/EFTER 2022-07-01 (samma brytpunkt
#27d flaggade) för att direkt testa hypotesen "hjälper regimen mest i och
efter regimbrytningen", inte bara ett aggregerat medel över hela perioden.

Kräver att 'tune_abstention_gate.py fetch' redan körts (samma cache som
Test 5/6/7/#33-#35 redan återanvänt ikväll).

    /opt/momentum/venv/bin/python3 tune_regime_feature.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

import numpy as np
import pandas as pd
import lightgbm as lgb

from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from backtest.calibration_check import prob_resolution_stats
from backtest.regime import classify_regimes
from tune_abstention_gate import _load_state
from tune_lambdarank_common import _slice_sorted, _relevance_labels, _date_weights, production_params

REGIME_CODE = {"bull": 0, "sideways": 1, "bear": 2}
BREAK_DATE = pd.Timestamp("2022-07-01")


def _train(train_sub, val_d, dev_df, feature_cols, categorical_feature=None):
    X_tr = train_sub[feature_cols].values
    y_tr_rel = _relevance_labels(train_sub)
    train_groups = train_sub.groupby(level=0).size().values
    w_tr = _date_weights(train_sub)

    val_sub = _slice_sorted(dev_df, val_d)
    X_va = val_sub[feature_cols].values
    y_va_rel = _relevance_labels(val_sub)
    val_groups = val_sub.groupby(level=0).size().values

    ds_kwargs = {}
    if categorical_feature is not None:
        ds_kwargs["categorical_feature"] = categorical_feature
    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr, **ds_kwargs)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)
    return lgb.train(
        production_params(), ds_tr, num_boost_round=500, valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
    )


def _eval_on_test(test_sub, raw_score):
    ic = float(pd.Series(raw_score).corr(pd.Series(test_sub["target_return"].values), method="spearman"))
    res = prob_resolution_stats(raw_score)
    return {"test_ic": ic, "n_unique": res["n_unique"]}


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]

    print("[regime_feature] Klassificerar regimer (kausalt, samma metod som backtestern)...")
    regime = classify_regimes(data)
    n_bull, n_bear, n_side = (regime == "bull").sum(), (regime == "bear").sum(), (regime == "sideways").sum()
    print(f"[regime_feature] {len(regime)} veckor klassade: bull={n_bull} bear={n_bear} sideways={n_side}")

    regime_code_by_date = regime.reindex(dev_df.index.unique()).ffill().map(REGIME_CODE)
    dev_df = dev_df.copy()
    dev_df["regime_code"] = dev_df.index.map(regime_code_by_date).astype(float)
    missing = dev_df["regime_code"].isna().sum()
    if missing:
        print(f"[regime_feature] [VARNING] {missing} rader saknar regimetikett (tidigt i historiken), fylls med 1 (sideways).")
        dev_df["regime_code"] = dev_df["regime_code"].fillna(1)

    baseline_cols = list(FEATURE_COLS)
    regime_cols = baseline_cols + ["regime_code"]
    regime_idx = len(baseline_cols)   # positionellt index i regime_cols

    splits = walk_forward_splits(dev_df.index)
    print(f"[regime_feature] {len(splits)} splits.\n")

    rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 100:
            continue
        test_start = test_sub.index.min()

        model_base = _train(train_sub, val_d, dev_df, baseline_cols)
        model_regime = _train(train_sub, val_d, dev_df, regime_cols, categorical_feature=[regime_idx])

        raw_base = model_base.predict(test_sub[baseline_cols].values)
        raw_regime = model_regime.predict(test_sub[regime_cols].values)

        for name, raw in (("baseline", raw_base), ("regime_feature", raw_regime)):
            m = _eval_on_test(test_sub, raw)
            rows.append({"split": i + 1, "test_start": test_start, "period": "pre-2022" if test_start < BREAK_DATE else "post-2022",
                         "variant": name, **m})
        print(f"  split {i+1}/{len(splits)} ({test_start.date()}, {'pre' if test_start < BREAK_DATE else 'post'}-2022): "
              f"baseline IC={rows[-2]['test_ic']:+.3f} | regime_feature IC={rows[-1]['test_ic']:+.3f}")

    df = pd.DataFrame(rows)
    print("\n" + "=" * 90)
    print("Median test-IC per variant, hela perioden / pre-2022 / post-2022")
    print("=" * 90)
    for period_label, sub in (("Hela dev-perioden", df), ("Pre-2022-07-01", df[df["period"] == "pre-2022"]),
                               ("Post-2022-07-01", df[df["period"] == "post-2022"])):
        if sub.empty:
            print(f"\n  {period_label}: inga splits.")
            continue
        med = sub.groupby("variant")["test_ic"].median()
        n_splits = sub["split"].nunique()
        print(f"\n  {period_label} ({n_splits} splits):")
        print(med.to_string(float_format=lambda x: f"{x:+.4f}"))

    print("\n[regime_feature] Klart.")


if __name__ == "__main__":
    main()
