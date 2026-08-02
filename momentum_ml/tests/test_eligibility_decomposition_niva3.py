import numpy as np
import pandas as pd

from tune_eligibility_decomposition_niva3_stage3 import _build_arm, _random_matched_mask


def test_random_control_matches_eligible_count_per_date_and_is_deterministic():
    dates = pd.to_datetime(["2020-01-06"] * 5 + ["2020-01-13"] * 4)
    frame = pd.DataFrame({"selection_eligible": [1, 0, 1, 0, 0, 0, 1, 1, 1]}, index=dates)
    a = _random_matched_mask(frame, 29)
    b = _random_matched_mask(frame, 29)
    assert np.array_equal(a, b)
    for date, pos in frame.groupby(level=0).indices.items():
        assert int(a.iloc[np.asarray(pos)].sum()) == int(frame.iloc[np.asarray(pos)].selection_eligible.sum())


def test_cash_mode_scales_exposure_when_fewer_than_max_positions(monkeypatch):
    import config
    monkeypatch.setattr(config, "MAX_POSITIONS", 4)
    monkeypatch.setattr(config, "MAX_POSITION", 1.0)
    date = pd.Timestamp("2020-01-06")
    frame = pd.DataFrame({
        "ticker": ["A", "B", "C"], "selection_rank": [3.0, 2.0, 1.0],
        "prob_up": [0.7, 0.6, 0.5], "prob_raw": [0.3, 0.2, 0.1],
        "position_size": 0.0, "pred_signal": 0,
    }, index=[date] * 3)
    vol = pd.Series([0.2, 0.2, 0.2], index=pd.MultiIndex.from_tuples(
        [(date, "A"), (date, "B"), (date, "C")]))
    arm = _build_arm(frame, np.array([True, True, False]), vol)
    assert np.isclose(arm.position_size.sum(), 2 / 4)
