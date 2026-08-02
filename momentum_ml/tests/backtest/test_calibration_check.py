import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backtest.calibration_check import (  # noqa: E402
    brier_score, reliability_bins, expected_calibration_error, calibration_report,
)


# ── brier_score ──────────────────────────────────────────────────────────────

def test_brier_score_perfect_predictions_is_zero():
    probs = np.array([0.0, 1.0, 0.0, 1.0])
    outcomes = np.array([0, 1, 0, 1])
    assert brier_score(probs, outcomes) == pytest.approx(0.0)


def test_brier_score_always_wrong_is_one():
    probs = np.array([1.0, 0.0])
    outcomes = np.array([0, 1])
    assert brier_score(probs, outcomes) == pytest.approx(1.0)


def test_brier_score_always_half_matches_base_rate_case():
    probs = np.full(4, 0.5)
    outcomes = np.array([0, 1, 0, 1])
    assert brier_score(probs, outcomes) == pytest.approx(0.25)


def test_brier_score_matches_sklearn():
    sk = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(0)
    probs = rng.uniform(0, 1, 200)
    outcomes = rng.integers(0, 2, 200)
    ours = brier_score(probs, outcomes)
    theirs = sk.brier_score_loss(outcomes, probs)
    assert ours == pytest.approx(theirs)


def test_brier_score_ignores_nan_entries():
    probs = np.array([0.0, np.nan, 1.0])
    outcomes = np.array([0, 1, 1])
    # Bara index 0 och 2 räknas (index 1 saknar giltig prediktion) -> båda perfekta -> 0.0
    assert brier_score(probs, outcomes) == pytest.approx(0.0)


def test_brier_score_all_nan_returns_nan():
    assert np.isnan(brier_score(np.array([np.nan, np.nan]), np.array([0, 1])))


# ── reliability_bins / expected_calibration_error ───────────────────────────

def test_reliability_bins_perfect_calibration_lies_on_diagonal():
    rng = np.random.default_rng(1)
    n = 5000
    probs = rng.uniform(0, 1, n)
    outcomes = (rng.uniform(0, 1, n) < probs).astype(int)   # sant kalibrerat per konstruktion
    bins = reliability_bins(probs, outcomes, n_bins=10)
    populated = bins.dropna(subset=["mean_predicted", "actual_frequency"])
    assert len(populated) >= 8
    assert (populated["mean_predicted"] - populated["actual_frequency"]).abs().max() < 0.08


def test_reliability_bins_n_sums_to_total_observations():
    probs = np.array([0.05, 0.15, 0.55, 0.95, 0.99])
    outcomes = np.array([0, 0, 1, 1, 1])
    bins = reliability_bins(probs, outcomes, n_bins=10)
    assert bins["n"].sum() == len(probs)


def test_reliability_bins_probability_one_lands_in_last_bin():
    bins = reliability_bins(np.array([1.0]), np.array([1]), n_bins=10)
    assert bins.iloc[-1]["n"] == 1


def test_expected_calibration_error_zero_for_perfect_calibration():
    # Stora, jämnt fördelade hinkar med exakt matchande frekvens -> ECE ~ 0
    probs = np.repeat([0.1, 0.3, 0.5, 0.7, 0.9], 1000)
    outcomes = np.concatenate([
        np.random.default_rng(i).binomial(1, p, 1000) for i, p in enumerate([0.1, 0.3, 0.5, 0.7, 0.9])
    ])
    ece = expected_calibration_error(probs, outcomes, n_bins=5)
    assert ece < 0.03


def test_expected_calibration_error_high_for_systematically_overconfident_model():
    """Modell som alltid säger 0.95 men bara har rätt 50% av tiden -> hög ECE."""
    probs = np.full(1000, 0.95)
    outcomes = np.random.default_rng(2).binomial(1, 0.5, 1000)
    ece = expected_calibration_error(probs, outcomes, n_bins=10)
    assert ece > 0.3


def test_expected_calibration_error_empty_returns_nan():
    assert np.isnan(expected_calibration_error(np.array([]), np.array([])))


# ── calibration_report ──────────────────────────────────────────────────────

class _FakeModel:
    """Returnerar en FAST rå-sannolikhet per rad – ingen riktig LGBM behövs
    för att testa rapport-logiken (splitting/aggregering), bara kontraktet
    (.predict(X) -> array)."""
    def __init__(self, raw_value):
        self.raw_value = raw_value

    def predict(self, X):
        return np.full(len(X), self.raw_value)


class _FakeCalibrator:
    """Identitetstransform, isolerar testet till rapport-logiken."""
    def transform(self, raw):
        return np.asarray(raw)


def test_calibration_report_has_one_row_per_split_plus_total():
    from features.feature_engineering import FEATURE_COLS

    dates = pd.date_range("2020-01-05", periods=20, freq="W")
    df = pd.DataFrame(
        {c: np.random.default_rng(0).normal(size=len(dates)) for c in FEATURE_COLS},
        index=dates,
    )
    df["target_signal"] = (np.arange(len(dates)) % 2)

    split_a, split_b = dates[:10], dates[10:]
    cls_models = [_FakeModel(0.5), _FakeModel(0.5)]
    calibrators = [_FakeCalibrator(), _FakeCalibrator()]
    split_starts = [split_a[0], split_b[0]]
    val_windows = [split_a, split_b]

    report = calibration_report(cls_models, calibrators, split_starts, df, val_windows, n_bins=5)
    assert len(report) == 3   # 2 splits + TOTALT
    assert report.iloc[-1]["split_start"] == "TOTALT"
    assert report.iloc[-1]["n"] == len(dates)


def test_calibration_report_brier_matches_manual_calc_for_constant_prediction():
    from features.feature_engineering import FEATURE_COLS

    dates = pd.date_range("2020-01-05", periods=10, freq="W")
    df = pd.DataFrame({c: 0.0 for c in FEATURE_COLS}, index=dates)
    df["target_signal"] = [0] * 5 + [1] * 5   # 50% positiva

    cls_models = [_FakeModel(0.5)]
    calibrators = [_FakeCalibrator()]
    report = calibration_report(cls_models, calibrators, [dates[0]], df, [dates], n_bins=5)
    # Konstant prediktion 0.5 mot 50% bas-frekvens -> Brier = 0.25 (klassiska "gissa medel"-fallet)
    assert report.iloc[0]["brier_before"] == pytest.approx(0.25)
    assert report.iloc[0]["brier_after"] == pytest.approx(0.25)


def test_calibration_report_skips_empty_val_windows():
    from features.feature_engineering import FEATURE_COLS

    dates = pd.date_range("2020-01-05", periods=10, freq="W")
    df = pd.DataFrame({c: 0.0 for c in FEATURE_COLS}, index=dates)
    df["target_signal"] = [0] * 5 + [1] * 5

    empty_window = pd.date_range("2099-01-01", periods=3, freq="W")   # matchar inget i df
    cls_models = [_FakeModel(0.5)]
    calibrators = [_FakeCalibrator()]
    report = calibration_report(cls_models, calibrators, [dates[0]], df, [empty_window], n_bins=5)
    assert len(report) == 0   # inget att aggregera -> ingen TOTALT-rad heller
