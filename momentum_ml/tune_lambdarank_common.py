"""
tune_lambdarank_common.py – delad tränings-helper för Test 5/6/7-omkörningarna
(2026-07-29, korrigering efter upptäckt confound).

Test 5 (tune_sector_categorical.py), 6 (tune_rank_metric_selection.py) och 7
(tune_equal_date_weight.py) tränade ursprungligen sina "förbättrings"-
varianter med `objective="binary"` + config.LGBM_PARAMS (num_leaves=63,
subsample=0.8, n_estimators=1000, ...) medan "baseline" var
lgbm.cls_models[i] - den RIKTIGA produktionsmodellen (objective="lambdarank",
num_leaves=31, ingen subsampling, 500 boost rounds, se
models/lgbm_model.py::fit_walk_forward). En jämförelse mellan två olika
modellfamiljer, inte en isolerad enskild-variabel-test.

Den här modulen replikerar fit_walk_forward:s per-split träningslogik EXAKT
(samma relevanslabels via qcut(5), samma group=, samma equal-date-weight,
samma hyperparametrar hämtade direkt från en riktig MomentumLGBM()-instans
- inte kopierade för hand, för att inte råka drifta isär igen) och exponerar
bara de enskilda knapparna varje test faktiskt undersöker:
categorical_feature (Test 5), weight på/av (Test 7), feval/metric (Test 6).

Ingen isotonic-kalibrering - produktionens LambdaRank-scores kalibreras inte
heller (se Test 8/project_momentum_lambdarank_migration.md), så raden ska
inte finnas här bara för att den fanns i de gamla (förorenade) skripten.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

from features.feature_engineering import FEATURE_COLS
from models.lgbm_model import MomentumLGBM


def _slice_sorted(df: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    return df[df.index.isin(dates)].sort_index()


def _relevance_labels(sub: pd.DataFrame) -> np.ndarray:
    return sub.groupby(level=0)["target_return"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop") if len(x) >= 5 else 0
    ).values


def _date_weights(sub: pd.DataFrame) -> np.ndarray:
    sizes = sub.groupby(level=0).size()
    return (1.0 / sizes.reindex(sub.index)).values.astype(np.float32)


def production_params() -> dict:
    """Hämtar EXAKT samma hyperparametrar som produktionen använder just nu,
    direkt från en riktig MomentumLGBM()-instans - aldrig hårdkodade separat,
    så de två aldrig kan glida isär igen som med config.LGBM_PARAMS-buggen."""
    return dict(MomentumLGBM().params)


def train_lambdarank_split(
    train_sub: pd.DataFrame,
    val_d: pd.DatetimeIndex,
    dev_df: pd.DataFrame,
    categorical_feature: list = None,
    use_date_weight: bool = True,
    feval=None,
    disable_builtin_metric: bool = False,
    num_boost_round: int = 500,
    early_stopping_rounds: int = 50,
) -> lgb.Booster:
    """Replikerar models/lgbm_model.py::fit_walk_forward per split, med de tre
    variablerna Test 5/6/7 faktiskt undersöker som parametrar. Allt annat
    (objective, num_leaves, min_child_samples, reg_alpha/lambda,
    learning_rate, seed, relevanslabels, group=, num_boost_round,
    early_stopping) är identiskt med produktionen."""
    X_tr = train_sub[FEATURE_COLS].values
    y_tr_rel = _relevance_labels(train_sub)
    train_groups = train_sub.groupby(level=0).size().values

    val_sub = _slice_sorted(dev_df, val_d)
    X_va = val_sub[FEATURE_COLS].values
    y_va_rel = _relevance_labels(val_sub)
    val_groups = val_sub.groupby(level=0).size().values

    w_tr = _date_weights(train_sub) if use_date_weight else None

    ds_kwargs = {}
    if categorical_feature is not None:
        ds_kwargs["categorical_feature"] = categorical_feature
    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr, **ds_kwargs)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

    params = production_params()
    if disable_builtin_metric:
        params = {**params, "metric": "None"}

    model = lgb.train(
        params, ds_tr, num_boost_round=num_boost_round, valid_sets=[ds_va],
        feval=feval,
        callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False),
                   lgb.log_evaluation(period=-1)],
    )
    return model
