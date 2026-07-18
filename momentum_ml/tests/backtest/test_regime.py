import pytest
import pandas as pd
import numpy as np

import sys
from pathlib import Path

# Add the momentum_ml directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtest.regime import classify_regimes, regime_breakdown

def test_classify_regimes():
    """
    Test classifying regimes based on simulated price data.
    Ensures that bull, bear, and sideways regimes are correctly identified
    based on the proxy price and its SMA crossing/slope.
    """
    closes = [10.0, 10.0, 10.0, 13.0, 16.0, 16.0, 10.0, 10.0, 13.0, 10.0, 7.0]
    dates = pd.date_range(start='2020-01-01', periods=len(closes), freq='W')

    df = pd.DataFrame({"Close": closes}, index=dates)
    price_data = {"TICKER": df}

    regimes = classify_regimes(price_data, sma_weeks=3)

    # SMA(3) gives NaN for first two, so dropped
    assert len(regimes) == len(closes) - 2

    expected_regimes = [
        "sideways", # idx 2
        "bull",     # idx 3
        "bull",     # idx 4
        "bull",     # idx 5
        "bear",     # idx 6
        "bear",     # idx 7
        "sideways", # idx 8
        "sideways", # idx 9
        "bear"      # idx 10
    ]

    for i, expected in enumerate(expected_regimes):
        assert regimes.iloc[i] == expected, f"Expected {expected} at index {i+2}, got {regimes.iloc[i]}"

def test_classify_regimes_multiple_tickers():
    """
    Test that the market proxy is correctly calculated as the equal-weighted
    cumulative product of mean weekly returns for multiple tickers.
    """
    closes_A = [10.0, 11.0, 12.1, 13.31, 14.641]
    closes_B = [10.0, 9.0, 8.1, 7.29, 6.561]
    dates = pd.date_range(start='2020-01-01', periods=5, freq='W')

    price_data = {
        "A": pd.DataFrame({"Close": closes_A}, index=dates),
        "B": pd.DataFrame({"Close": closes_B}, index=dates)
    }

    regimes = classify_regimes(price_data, sma_weeks=2)

    assert len(regimes) == 4
    for r in regimes:
        assert r == "sideways"

def test_classify_regimes_missing_prices():
    """
    Test behavior when one of the tickers has missing prices or empty series.
    """
    dates = pd.date_range(start='2020-01-01', periods=5, freq='W')
    price_data = {
        "A": pd.DataFrame({"Close": [10.0, 11.0, 12.1, 13.31, 14.641]}, index=dates),
        "EMPTY": pd.DataFrame()
    }

    regimes = classify_regimes(price_data, sma_weeks=2)

    assert len(regimes) == 4
    assert regimes.iloc[0] == "sideways"
    assert regimes.iloc[1] == "bull"
    assert regimes.iloc[2] == "bull"
    assert regimes.iloc[3] == "bull"

def test_classify_regimes_empty():
    """
    Test classifying regimes when no valid price data is available.
    """
    price_data = {
        "EMPTY1": pd.DataFrame(),
        "EMPTY2": pd.DataFrame()
    }
    with pytest.raises(ValueError, match="Ingen prisdata tillgänglig för marknadsproxyn."):
        classify_regimes(price_data, sma_weeks=2)

def test_regime_breakdown():
    """
    Test the regime breakdown function.
    """
    dates = pd.date_range(start='2020-01-01', periods=4, freq='W')
    # Portfolio returns
    returns = pd.Series([0.1, -0.05, 0.05, -0.1], index=dates)
    # Regimes
    regimes = pd.Series(["bull", "bull", "bear", "sideways"], index=dates)

    breakdown = regime_breakdown(returns, regimes)

    assert "bull" in breakdown.index
    assert "bear" in breakdown.index
    assert "sideways" in breakdown.index

    assert breakdown.loc["bull", "n_weeks"] == 2
    assert breakdown.loc["bull", "win_rate"] == 0.5
    assert breakdown.loc["bull", "avg_return"] == 0.025 # (0.1 - 0.05)/2

    assert breakdown.loc["bear", "n_weeks"] == 1
    assert breakdown.loc["bear", "win_rate"] == 1.0 # 0.05 > 0

    assert breakdown.loc["sideways", "n_weeks"] == 1
    assert breakdown.loc["sideways", "win_rate"] == 0.0 # -0.1 <= 0
