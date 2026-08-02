"""
Verifierar de nya diagnostik-attributen i MomentumLGBM.fit_walk_forward
(kodgranskning 2026-07-23): feature_importance_history_ (per-split, inte
bara medelvärdet) och fold_diagnostics_ (per-fold hit rate/pseudo-Sharpe).

Kör en RIKTIG (men liten) LightGBM-träning på syntetisk data – snabbt
tack vare fit_walk_forward:s nya train_weeks/val_weeks/step_weeks/
embargo_weeks-överstyrning och en liten n_estimators/early_stopping-
konfiguration, inte en mockad modell. Detta är den enda pålitliga
verifieringen att attributen faktiskt fylls med rätt form under en
skarp träningsloop, inte bara att koden kompilerar.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from features.feature_engineering import FEATURE_COLS  # noqa: E402
from models.lgbm_model import MomentumLGBM  # noqa: E402

_SMALL_PARAMS = {
    "objective": "binary",
    "metric": ["binary_logloss"],
    "learning_rate": 0.2,
    "num_leaves": 7,
    "min_child_samples": 5,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0.0,
    "reg_lambda": 0.0,
    "n_estimators": 15,
    "early_stopping_rounds": 5,
    "verbose": -1,
    "num_threads": 1,
    "seed": 42,
    "bagging_seed": 42,
    "feature_fraction_seed": 42,
    "data_random_seed": 42,
    "deterministic": True,
    "force_row_wise": True,
}


def _synthetic_df(n_weeks=60, n_tickers=8, seed=7):
    """Syntetisk multi-ticker df i samma form fit_walk_forward förväntar:
    DatetimeIndex + FEATURE_COLS + target_signal/target_return. Värdena är
    slumpmässiga (inget riktigt momentum-mönster) – testet bryr sig bara om
    att pipelinen KÖR och lagrar rätt saker, inte om modellen tränar bra."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-04", periods=n_weeks, freq="W")
    rows = []
    for d in dates:
        for t in range(n_tickers):
            row = {c: rng.normal() for c in FEATURE_COLS}
            row["target_signal"] = int(rng.random() > 0.5)
            row["target_return"] = float(rng.normal(0, 0.05))
            rows.append(row)
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(np.repeat(dates, n_tickers)))
    return df


@pytest.fixture(scope="module")
def trained_model():
    df = _synthetic_df()
    model = MomentumLGBM(params=_SMALL_PARAMS)
    model.fit_walk_forward(df, train_weeks=20, val_weeks=6, step_weeks=6, embargo_weeks=2)
    return model


def test_fit_walk_forward_runs_multiple_splits(trained_model):
    assert len(trained_model.cls_models) >= 2
    assert len(trained_model.split_starts) == len(trained_model.cls_models)


# ── feature_importance_history_ ─────────────────────────────────────────────

def test_feature_importance_history_has_one_row_per_split(trained_model):
    hist = trained_model.feature_importance_history_
    assert hist is not None
    assert len(hist) == len(trained_model.cls_models)


def test_feature_importance_history_columns_match_feature_cols(trained_model):
    hist = trained_model.feature_importance_history_
    assert list(hist.columns) == FEATURE_COLS


def test_feature_importance_history_indexed_by_split_start_dates(trained_model):
    hist = trained_model.feature_importance_history_
    assert list(hist.index) == trained_model.split_starts


def test_feature_importance_history_values_are_finite_and_nonnegative(trained_model):
    """LightGBM gain-importance är alltid >= 0."""
    hist = trained_model.feature_importance_history_
    assert np.isfinite(hist.values).all()
    assert (hist.values >= 0).all()


def test_feature_importance_mean_matches_history_mean(trained_model):
    """Det gamla, aggregerade feature_importance_ ska fortfarande vara
    EXAKT medelvärdet av den nya per-split-historiken – historiken lägger
    till detaljinformation, den ersätter inte/motsäger inte det gamla
    kontraktet andra anropare (main.py: print_feature_importance) litar på."""
    hist = trained_model.feature_importance_history_
    agg = trained_model.feature_importance_
    recomputed_mean = hist.mean(axis=0)
    for _, row in agg.iterrows():
        assert row["cls_importance"] == pytest.approx(recomputed_mean[row["feature"]], abs=1e-6)


def test_print_feature_importance_by_period_does_not_crash(trained_model, capsys):
    trained_model.print_feature_importance_by_period(n_periods=2, top_n=5)
    out = capsys.readouterr().out
    assert "Feature importance per period" in out


# ── fold_diagnostics_ ────────────────────────────────────────────────────────

def test_fold_diagnostics_has_one_entry_per_split(trained_model):
    assert len(trained_model.fold_diagnostics_) == len(trained_model.cls_models)


def test_fold_diagnostics_hit_rate_in_valid_range(trained_model):
    for d in trained_model.fold_diagnostics_:
        assert d["hit_rate"] is None or 0.0 <= d["hit_rate"] <= 1.0


def test_fold_diagnostics_split_numbers_are_sequential(trained_model):
    splits = [d["split"] for d in trained_model.fold_diagnostics_]
    assert splits == list(range(1, len(splits) + 1))
    assert all(d["n_splits"] == len(splits) for d in trained_model.fold_diagnostics_)


def test_fold_diagnostics_test_window_is_chronological(trained_model):
    for d in trained_model.fold_diagnostics_:
        assert d["test_start"] <= d["test_end"]


def test_print_fold_diagnostics_does_not_crash(trained_model, capsys):
    trained_model.print_fold_diagnostics()
    out = capsys.readouterr().out
    assert "Per-fold diagnostik" in out
    assert str(len(trained_model.fold_diagnostics_)) in out


def test_fold_diagnostics_empty_before_training():
    model = MomentumLGBM(params=_SMALL_PARAMS)
    assert model.fold_diagnostics_ == []
    assert model.feature_importance_history_ is None


# ── Featureordnings-guard (#6 i pipeline-granskningslistan) ──────────────────
# predict() jämför redan self.feature_cols_ (satt vid träning) mot den LIVE
# FEATURE_COLS och kastar ValueError vid avvikelse (models/lgbm_model.py,
# se docstringen för strict=). Detta var den enda av de 10 granskade
# kontrollerna som redan var löst i produktionskoden - men aldrig testad.

def test_predict_raises_when_feature_cols_changed_since_training(trained_model):
    df = _synthetic_df(n_weeks=10, n_tickers=4, seed=99)
    original = trained_model.feature_cols_
    try:
        trained_model.feature_cols_ = original[:-1] + ["some_other_feature"]
        with pytest.raises(ValueError, match="FEATURE_COLS har ändrats"):
            trained_model.predict(df)
    finally:
        trained_model.feature_cols_ = original


def test_predict_succeeds_when_feature_cols_unchanged(trained_model):
    df = _synthetic_df(n_weeks=10, n_tickers=4, seed=99)
    result = trained_model.predict(df)
    assert len(result) == len(df)
