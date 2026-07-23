import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from models.ensemble import MomentumEnsemble, kelly_position_size  # noqa: E402


# ── kelly_position_size ────────────────────────────────────────────────────

def test_kelly_position_size_bounds_normal():
    """Normala indata ska ge ett resultat inom [0, MAX_POSITION]."""
    for prob_up in (0.3, 0.5, 0.6, 0.75, 0.9):
        v = kelly_position_size(prob_up, pred_return=0.05, volatility=0.15)
        assert 0.0 <= v <= config.MAX_POSITION


def test_kelly_position_size_never_negative():
    """Long-only: prob_up under break-even ska ge 0.0, aldrig negativt."""
    v = kelly_position_size(prob_up=0.1, pred_return=-0.05, volatility=0.15)
    assert v == 0.0


def test_kelly_position_size_extreme_probability_is_capped():
    """prob_up=1.0 (perfekt säkerhet) ska klippas internt (0.99) och aldrig
    ge en orimlig exponering utöver MAX_POSITION."""
    v = kelly_position_size(prob_up=1.0, pred_return=0.10, volatility=0.15)
    assert v == pytest.approx(config.MAX_POSITION)
    assert v <= config.MAX_POSITION


def test_kelly_position_size_zero_probability():
    v = kelly_position_size(prob_up=0.0, pred_return=0.05, volatility=0.15)
    assert v == 0.0


@pytest.mark.parametrize("prob_up", [np.nan, np.inf, -np.inf])
def test_kelly_position_size_nan_inf_probability_returns_zero(prob_up):
    """BUGG (fixad, se models/ensemble.py): np.clip saniterar inte NaN – ett
    NaN prob_up flödade tidigare oförändrat till slutresultatet i stället för
    att ge en säker, tydlig 0.0."""
    v = kelly_position_size(prob_up, pred_return=0.05, volatility=0.15)
    assert v == 0.0
    assert np.isfinite(v)


def test_kelly_position_size_nan_volatility_falls_back_gracefully():
    """NaN volatilitet ska INTE krascha eller ge NaN – vol-skalningen hoppas
    bara över (volatility > 0 är False för NaN)."""
    v = kelly_position_size(prob_up=0.6, pred_return=0.05, volatility=np.nan)
    assert np.isfinite(v)
    assert 0.0 <= v <= config.MAX_POSITION


def test_kelly_position_size_infinite_volatility_gives_zero():
    """Extrem volatilitet ska skala ner mot noll, inte krascha eller explodera."""
    v = kelly_position_size(prob_up=0.6, pred_return=0.05, volatility=np.inf)
    assert v == 0.0


def test_kelly_position_size_zero_volatility_does_not_divide_by_zero():
    """volatility=0 tar INTE vol-skalningsgrenen (villkoret är `> 0`),
    så resultatet ska vara den obeskalade Kelly-storleken, inte en krasch."""
    v = kelly_position_size(prob_up=0.6, pred_return=0.05, volatility=0.0)
    assert np.isfinite(v)
    assert 0.0 <= v <= config.MAX_POSITION


# ── MomentumEnsemble.combine() ─────────────────────────────────────────────

def _preds(prob_up_values, dates=None):
    dates = dates if dates is not None else pd.date_range("2024-01-05", periods=len(prob_up_values), freq="W")
    return pd.DataFrame(
        {"prob_up": prob_up_values, "pred_return": [0.02] * len(prob_up_values)},
        index=dates,
    )


def test_ensemble_probability_bounds_lgbm_only():
    """Utan LSTM returneras LGBM-benet oförändrat – redan garanterat kalibrerat
    till [0,1] av IsotonicRegression(y_min=0, y_max=1), men verifiera ändå
    kontraktet explicit så en framtida ändring inte tyst bryter det."""
    ens = MomentumEnsemble()
    lgbm = _preds([0.1, 0.5, 0.9])
    out = ens.combine(lgbm, None)
    assert ((out["prob_up"] >= 0.0) & (out["prob_up"] <= 1.0)).all()


def test_ensemble_probability_bounds_combined():
    """Ett viktat medel av två sannolikheter som VAR OCH EN redan ligger i
    [0,1] måste matematiskt också ligga i [0,1] (konvex kombination,
    vikterna summerar till 1) – verifierar att combine() inte introducerar
    ett fel som bryter den garantin."""
    ens = MomentumEnsemble()
    dates = pd.date_range("2024-01-05", periods=5, freq="W")
    lgbm = _preds([0.0, 0.25, 0.5, 0.75, 1.0], dates)
    lstm = _preds([1.0, 0.75, 0.5, 0.25, 0.0], dates)
    out = ens.combine(lgbm, lstm)
    assert ((out["prob_up"] >= 0.0) & (out["prob_up"] <= 1.0)).all()
    # 60/40-vikt (config.ENSEMBLE_LGBM_WEIGHT/_LSTM_WEIGHT) på de yttersta
    # punkterna ger ett känt, exakt värde – bra regressionsskydd.
    w_lg = config.ENSEMBLE_LGBM_WEIGHT / (config.ENSEMBLE_LGBM_WEIGHT + config.ENSEMBLE_LSTM_WEIGHT)
    w_ls = 1 - w_lg
    expected_first = w_lg * 0.0 + w_ls * 1.0
    assert out["prob_up"].iloc[0] == pytest.approx(expected_first)


def test_ensemble_combine_pred_signal_matches_threshold():
    ens = MomentumEnsemble()
    dates = pd.date_range("2024-01-05", periods=2, freq="W")
    lgbm = _preds([0.9, 0.1], dates)
    lstm = _preds([0.9, 0.1], dates)
    out = ens.combine(lgbm, lstm)
    assert out["pred_signal"].iloc[0] == 1
    assert out["pred_signal"].iloc[1] == 0


def test_ensemble_combine_empty_lstm_falls_back_to_lgbm():
    ens = MomentumEnsemble()
    lgbm = _preds([0.3, 0.7])
    out = ens.combine(lgbm, pd.DataFrame())
    pd.testing.assert_frame_equal(out, lgbm)
