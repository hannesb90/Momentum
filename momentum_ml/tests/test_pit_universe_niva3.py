import pandas as pd

from audit_pit_universe_niva3_stage7 import _validity


def test_validity_accepts_any_matching_lifecycle_interval():
    signals = pd.DataFrame({
        "Date": pd.to_datetime(["2010-01-01", "2015-01-01", "2020-01-01"]),
        "ticker": ["A", "A", "A"], "pred_signal": [1, 1, 1], "position_size": [1, 1, 1],
    }).set_index("Date")
    intervals = pd.DataFrame({
        "ticker": ["A", "A"], "valid_from": ["2009-01-01", "2019-01-01"],
        "valid_to": ["2011-01-01", None],
    })
    result = _validity(signals, intervals)
    assert result.pit_matched.tolist() == [True, True, True]
    assert result.pit_valid.tolist() == [True, False, True]
