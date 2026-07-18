import pytest
import pandas as pd
import numpy as np

from momentum_ml.backtest.regime import classify_regimes

def test_classify_regimes():
    """
    Test that classify_regimes correctly identifies bull, bear, and sideways
    regimes based on an equal-weighted proxy and its SMA.
    """
    # Create artificial price data to trigger specific regimes based on an SMA of 2 weeks.
    # We will use 6 weeks of data to get a sequence of regimes.

    dates = pd.date_range("2020-01-01", periods=6, freq="W")

    # Let's walk through the expected proxy and SMA with these prices:
    # We'll use a single ticker for simplicity, so the proxy exactly mirrors the scaled prices.
    # W1: Price 100.0 => Proxy 1.0. SMA(2) = NaN, SMA_slope = NaN, Regime: sideways (if not NaN, but first is dropped because sma is NaN, though proxy > sma is False)
    # W2: Price 110.0 => Proxy 1.1. SMA(2) = 1.05. SMA_slope = NaN. Regime: sideways
    # W3: Price 120.0 => Proxy 1.2. SMA(2) = 1.15. SMA_slope = 0.10. Proxy (1.2) > SMA (1.15) and SMA_slope > 0 => 'bull'
    # W4: Price 100.0 => Proxy 1.0. SMA(2) = 1.10. SMA_slope = -0.05. Proxy (1.0) < SMA (1.10) and SMA_slope < 0 => 'bear'
    # W5: Price 80.0  => Proxy 0.8. SMA(2) = 0.90. SMA_slope = -0.20. Proxy (0.8) < SMA (0.90) and SMA_slope < 0 => 'bear'
    # W6: Price 90.0  => Proxy 0.9. SMA(2) = 0.85. SMA_slope = -0.05. Proxy (0.9) > SMA (0.85) but SMA_slope (-0.05) < 0 => 'sideways'

    prices = [100.0, 110.0, 120.0, 100.0, 80.0, 90.0]

    df = pd.DataFrame({"Close": prices}, index=dates)
    price_data = {"TICK": df}

    # Calculate regimes with SMA of 2 weeks
    regimes = classify_regimes(price_data, sma_weeks=2)

    # W1 (2020-01-05) has NaN SMA, so it should be dropped.
    # The output series should have length 5.
    assert len(regimes) == 5

    # Expected regimes
    expected_labels = ["sideways", "bull", "bear", "bear", "sideways"]

    # Compare with our calculated regimes
    for i, expected in enumerate(expected_labels):
        assert regimes.iloc[i] == expected
