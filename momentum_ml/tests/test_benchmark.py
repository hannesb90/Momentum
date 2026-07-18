import numpy as np
import pandas as pd
import pytest

from backtest.benchmark import equal_weight_index

def test_equal_weight_index_normal():
    # Test equal weight return calculation with normal prices
    dates = pd.date_range("2020-01-01", periods=3, freq="W")

    # Stock A grows 10% each week
    # Stock B drops 10% each week
    prices = {
        "A": pd.DataFrame({"Close": [100.0, 110.0, 121.0]}, index=dates),
        "B": pd.DataFrame({"Close": [100.0, 90.0, 81.0]}, index=dates),
    }

    result = equal_weight_index(prices, dates, initial_capital=100000.0)

    # Week 1 return: (0.1 - 0.1) / 2 = 0.0
    # Week 2 return: (0.1 - 0.1) / 2 = 0.0
    # The cumulative return should stay at 100000.0

    assert len(result) == 3
    assert result.index.equals(dates)
    assert np.isclose(result.iloc[0], 100000.0)
    assert np.isclose(result.iloc[1], 100000.0)
    assert np.isclose(result.iloc[2], 100000.0)


def test_equal_weight_index_missing_prices():
    # Test equal weight return with missing prices / dropouts
    dates = pd.date_range("2020-01-01", periods=3, freq="W")

    # A: full history
    # B: drops out after week 2
    # C: starts in week 2
    prices = {
        "A": pd.DataFrame({"Close": [100.0, 110.0, 121.0]}, index=dates), # 10% each week
        "B": pd.DataFrame({"Close": [100.0, 90.0, np.nan]}, index=dates), # -10% in week 1, no return week 2
        "C": pd.DataFrame({"Close": [np.nan, 100.0, 120.0]}, index=dates), # no return week 1, 20% in week 2
    }

    result = equal_weight_index(prices, dates, initial_capital=100000.0)

    # Week 0: 100000.0
    # Week 1 returns: A=0.1, B=-0.1, C=NaN. Mean = 0.0
    # Value week 1: 100000.0

    # Week 2 returns: A=0.1, B=NaN, C=0.2. Mean = 0.15
    # Value week 2: 100000.0 * 1.15 = 115000.0

    assert np.isclose(result.iloc[0], 100000.0)
    assert np.isclose(result.iloc[1], 100000.0)
    assert np.isclose(result.iloc[2], 115000.0)


def test_equal_weight_index_extreme_jump(monkeypatch):
    # Test clipping of suspicious jumps
    import config
    monkeypatch.setattr(config, "SUSPICIOUS_JUMP_THRESHOLD", 0.50, raising=False)

    dates = pd.date_range("2020-01-01", periods=2, freq="W")

    # Stock A jumps by 100% (should be clipped to 50%)
    prices = {
        "A": pd.DataFrame({"Close": [100.0, 200.0]}, index=dates),
    }

    result = equal_weight_index(prices, dates, initial_capital=100000.0)

    # Week 0: 100000.0
    # Week 1 return is 1.0, clipped to 0.50. Mean = 0.50
    # Value week 1: 150000.0

    assert np.isclose(result.iloc[0], 100000.0)
    assert np.isclose(result.iloc[1], 150000.0)


def test_equal_weight_index_empty_inputs():
    # Test with empty dates
    prices = {"A": pd.DataFrame({"Close": [100.0, 110.0]})}
    dates = pd.DatetimeIndex([])
    result = equal_weight_index(prices, dates)
    assert len(result) == 0
    assert isinstance(result, pd.Series)

    # Test with empty prices
    dates2 = pd.date_range("2020-01-01", periods=2)
    result2 = equal_weight_index({}, dates2)
    assert len(result2) == 2
    assert result2.isna().all()

    # Test with prices having no "Close" column or all NA
    prices_no_close = {"A": pd.DataFrame({"Open": [100.0, 110.0]}, index=dates2)}
    result3 = equal_weight_index(prices_no_close, dates2)
    assert result3.isna().all()
