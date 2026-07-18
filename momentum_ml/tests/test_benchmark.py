import pytest
import pandas as pd
import numpy as np
import math

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.benchmark import alpha_beta

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
