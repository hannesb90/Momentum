import pandas as pd

from tune_seed_fitdate_stability_niva3_stage5 import _jaccard_summary, _trim_cutoff


def test_fit_cutoff_only_removes_recent_dates():
    dates = pd.date_range("2020-01-06", periods=8, freq="W-MON")
    assert _trim_cutoff(dates, 0).equals(dates)
    assert _trim_cutoff(dates, 2).equals(dates[:-2])


def test_jaccard_summary_uses_same_dates():
    d = pd.Timestamp("2020-01-06")
    result = _jaccard_summary({d: {"A", "B"}}, {d: {"B", "C"}})
    assert result["median"] == 1 / 3
    assert result["dates"] == 1
