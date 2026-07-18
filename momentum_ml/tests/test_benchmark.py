import pytest
import pandas as pd
import numpy as np
import math

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.benchmark import alpha_beta, equal_weight_index

def test_alpha_beta_standard():
    # Construct series with known returns
    # b_rets has variance. s_rets = 2 * b_rets.
    # Therefore beta should be 2.
    # Mean of s_rets is 0. Mean of b_rets is 0.
    # alpha_week = 0 - 2 * 0 = 0.
    # alpha_annual = 0 * 52 = 0.
    b_rets = [0.01, -0.01, 0.02, -0.02, 0.03, -0.03, 0.04, -0.04, 0.05, -0.05]
    s_rets = [0.02, -0.02, 0.04, -0.04, 0.06, -0.06, 0.08, -0.08, 0.10, -0.10]

    b_values = pd.Series([100] + (100 * (1 + pd.Series(b_rets)).cumprod()).tolist())
    s_values = pd.Series([100] + (100 * (1 + pd.Series(s_rets)).cumprod()).tolist())

    res = alpha_beta(s_values, b_values)

    assert not math.isnan(res["beta"])
    assert not math.isnan(res["alpha_annual"])
    assert isinstance(res["beta"], float)
    assert isinstance(res["alpha_annual"], float)
    assert abs(res["beta"] - 2.0) < 1e-6
    assert abs(res["alpha_annual"] - 0.0) < 1e-6

def test_alpha_beta_too_short():
    # 8 data points -> 7 pct_change data points, < 8
    strategy = pd.Series([100, 101, 102, 103, 104, 105, 106, 107])
    benchmark = pd.Series([100, 102, 104, 106, 108, 110, 112, 114])

    res = alpha_beta(strategy, benchmark)

    assert math.isnan(res["beta"])
    assert math.isnan(res["alpha_annual"])

def test_alpha_beta_zero_variance():
    # 10 data points -> 9 pct_change data points, but benchmark has 0 variance
    strategy = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
    benchmark = pd.Series([100, 100, 100, 100, 100, 100, 100, 100, 100, 100])

    res = alpha_beta(strategy, benchmark)

    assert math.isnan(res["beta"])
    assert math.isnan(res["alpha_annual"])


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
        "A": pd.DataFrame({"Close": [100.0, 110.0, 121.0]}, index=dates),  # 10% each week
        "B": pd.DataFrame({"Close": [100.0, 90.0, np.nan]}, index=dates),  # -10% in week 1, no return week 2
        "C": pd.DataFrame({"Close": [np.nan, 100.0, 120.0]}, index=dates),  # no return week 1, 20% in week 2
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
