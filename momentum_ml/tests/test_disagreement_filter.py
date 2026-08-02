import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from tune_disagreement_filter import cross_sectional_model_disagreement  # noqa: E402


def test_identical_model_rankings_have_zero_disagreement():
    preds = np.array([
        [1.0, 10.0, -2.0],
        [2.0, 20.0, -1.0],
        [3.0, 30.0,  0.0],
    ])
    # Samma tvärsnittsrankning trots olika nivå/skala.
    np.testing.assert_allclose(
        cross_sectional_model_disagreement(preds),
        np.zeros(3),
        atol=1e-12,
    )


def test_rank_reversal_creates_nonconstant_disagreement():
    preds = np.array([
        [1.0, 3.0, 1.0],
        [2.0, 2.0, 2.0],
        [3.0, 1.0, 3.0],
    ])
    out = cross_sectional_model_disagreement(preds)
    assert out[0] > out[1]
    assert out[2] > out[1]
    assert np.ptp(out) > 0
