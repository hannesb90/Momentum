import pandas as pd

from pit_model_audit import audit


def test_reused_ticker_is_not_applied_as_historical_identity():
    signals = pd.DataFrame({
        "Date": ["2020-01-01"], "ticker": ["REUSE.ST"], "pred_signal": [1]})
    intervals = pd.DataFrame({
        "ticker": ["REUSE.ST"], "valid_from": ["2000-01-01"],
        "valid_to": ["2010-01-01"]})
    coverage = pd.DataFrame({
        "ticker": ["REUSE.ST"], "status": ["avnoterad"],
        "ticker_reuse_conflict": [True], "has_cached_price": [True],
        "price_overlaps_lifecycle": [False]})
    result = audit(signals, intervals, coverage)
    assert result["ticker_reuse_conflicts"] == ["REUSE.ST"]
    assert result["selected_rows_outside_valid_window"] == 0


def test_safe_delisted_selection_enables_partial_retest():
    signals = pd.DataFrame({
        "Date": ["2020-01-01"], "ticker": ["OLD.ST"], "pred_signal": [1]})
    intervals = pd.DataFrame({
        "ticker": ["OLD.ST"], "valid_from": ["2018-01-01"],
        "valid_to": ["2021-01-01"]})
    coverage = pd.DataFrame({
        "ticker": ["OLD.ST"], "status": ["avnoterad"],
        "ticker_reuse_conflict": [False], "has_cached_price": [True],
        "price_overlaps_lifecycle": [True]})
    result = audit(signals, intervals, coverage)
    assert result["performance_retest_possible"] is True
