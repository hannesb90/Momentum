import numpy as np
import pandas as pd

from tune_seed_consensus_niva3_stage6 import _consensus_scores


def test_consensus_is_equal_weight_rank_not_raw_magnitude():
    panel = pd.DataFrame({
        "Date": pd.to_datetime(["2020-01-06"] * 3),
        "ticker": ["A", "B", "C"],
        "raw_7": [1000.0, 2.0, 1.0],
        "raw_42": [1.0, 2.0, 3.0],
    })
    score = _consensus_scores(panel, (7, 42))
    assert np.isclose(score.iloc[0], (1.0 + 1 / 3) / 2)
    assert np.isclose(score.iloc[2], (1 / 3 + 1.0) / 2)
    assert np.isclose(score.iloc[0], score.iloc[2])
