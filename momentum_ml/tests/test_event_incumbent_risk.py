import numpy as np
import pandas as pd
import pytest

import config
from backtest.backtester import MomentumBacktester


DATE = pd.Timestamp("2026-01-12")


def _prices(correlated=True):
    dates = pd.date_range("2025-09-01", periods=20, freq="W-MON")
    a = np.linspace(100, 120, len(dates))
    b = a * 2 if correlated else np.linspace(120, 100, len(dates))
    return {
        "A.ST": pd.DataFrame(
            {"Close": a, "Volume": 1_000_000}, index=dates),
        "B.ST": pd.DataFrame(
            {"Close": b, "Volume": 1_000_000}, index=dates),
    }


def _backtester():
    signals = pd.DataFrame([{
        "Date": DATE, "ticker": "A.ST", "pred_signal": 1,
        "position_size": .1,
    }]).set_index("Date")
    return MomentumBacktester(
        signals, _prices(), initial_capital=1_000, market_filter=False)


def test_correlation_filter_drops_new_candidate_before_incumbent(monkeypatch):
    monkeypatch.setattr(config, "CORRELATION_LOOKBACK_WEEKS", 13)
    monkeypatch.setattr(config, "MAX_PAIRWISE_CORRELATION", .8)
    bt = _backtester()
    result = bt._correlation_filter(
        {"A.ST": .1, "B.ST": .1}, DATE,
        protected_tickers={"A.ST"})
    assert "A.ST" in result
    assert "B.ST" not in result
    assert result["A.ST"] == .2


def test_sector_filter_uses_newcomer_budget_first(monkeypatch):
    monkeypatch.setattr(config, "SECTOR_MAP", {
        "A.ST": "Industrials", "B.ST": "Industrials"})
    monkeypatch.setattr(config, "MAX_SECTOR_EXPOSURE", .15)
    bt = _backtester()
    result = bt._sector_exposure_filter(
        {"A.ST": .1, "B.ST": .1},
        protected_tickers={"A.ST"})
    assert result["A.ST"] == .1
    assert result["B.ST"] == pytest.approx(.05)


def test_sector_filter_excludes_newcomer_if_incumbents_fill_cap(monkeypatch):
    monkeypatch.setattr(config, "SECTOR_MAP", {
        "A.ST": "Industrials", "B.ST": "Industrials"})
    monkeypatch.setattr(config, "MAX_SECTOR_EXPOSURE", .10)
    bt = _backtester()
    result = bt._sector_exposure_filter(
        {"A.ST": .1, "B.ST": .1},
        protected_tickers={"A.ST"})
    assert result == {"A.ST": .1}
