import pandas as pd

import config
from backtest.backtester import MomentumBacktester


DATE = pd.Timestamp("2026-01-12")


def _signals(a_eligible=1):
    return pd.DataFrame([
        {"Date": DATE, "ticker": "A.ST", "selection_eligible": a_eligible,
         "selection_rank": .99, "prob_up": .9, "prob_raw": .9,
         "pred_return": .2, "pred_signal": 1, "position_size": .1},
        {"Date": DATE, "ticker": "B.ST", "selection_eligible": 1,
         "selection_rank": .80, "prob_up": .8, "prob_raw": .8,
         "pred_return": .1, "pred_signal": 1, "position_size": .1},
    ]).set_index("Date")


def _prices(a_date=DATE):
    idx = pd.DatetimeIndex([a_date])
    return {
        "A.ST": pd.DataFrame(
            {"Close": [100.0], "High": [101.0], "Low": [99.0],
             "Volume": [1_000_000]}, index=idx),
        "B.ST": pd.DataFrame(
            {"Close": [50.0], "High": [51.0], "Low": [49.0],
             "Volume": [1_000_000]}, index=pd.DatetimeIndex([DATE])),
    }


def _backtester(signals=None, prices=None):
    bt = MomentumBacktester(
        signals if signals is not None else _signals(),
        prices if prices is not None else _prices(),
        initial_capital=1_000, market_filter=False)
    bt._portfolio = {"A.ST": 5.0}
    bt._close_panel = pd.DataFrame(
        {"A.ST": [100.0], "B.ST": [50.0]}, index=[DATE])
    bt._below_sma = pd.DataFrame(
        {"A.ST": [False], "B.ST": [False]}, index=[DATE])
    bt._atr_panel = pd.DataFrame(
        {"A.ST": [5.0], "B.ST": [5.0]}, index=[DATE])
    bt._correlation_filter = lambda weights, date: weights
    bt._sector_exposure_filter = lambda weights: weights
    return bt


def _run_event(bt):
    cash = bt._event_rebalance(
        DATE, portfolio_value=500.0, cash=0.0,
        market_exp=1.0, guard=1.0)
    return cash


def test_trend_break_cannot_reenter_same_event_cycle(monkeypatch):
    monkeypatch.setattr(config, "ATR_STOP_ENABLED", False)
    bt = _backtester()
    bt._below_sma.at[DATE, "A.ST"] = True
    _run_event(bt)
    assert "A.ST" not in bt._portfolio
    assert any(
        row["decision"] == "hard_exit"
        and row["ticker"] == "A.ST"
        and "trend_break" in row["reasons"]
        for row in bt._event_decisions)


def test_atr_stop_is_hard_exit_in_event_mode(monkeypatch):
    monkeypatch.setattr(config, "ATR_STOP_ENABLED", True)
    monkeypatch.setattr(config, "ATR_STOP_MULT", 2.5)
    bt = _backtester()
    bt._peak_price["A.ST"] = 120.0
    _run_event(bt)
    assert "A.ST" not in bt._portfolio
    assert any(
        row["ticker"] == "A.ST" and "atr_stop" in row["reasons"]
        for row in bt._event_decisions)


def test_ineligible_holding_is_hard_exit(monkeypatch):
    monkeypatch.setattr(config, "ATR_STOP_ENABLED", False)
    bt = _backtester(signals=_signals(a_eligible=0))
    _run_event(bt)
    assert "A.ST" not in bt._portfolio
    assert any(
        row["ticker"] == "A.ST" and "ineligible" in row["reasons"]
        for row in bt._event_decisions)


def test_stale_price_is_hard_exit(monkeypatch):
    monkeypatch.setattr(config, "ATR_STOP_ENABLED", False)
    monkeypatch.setattr(config, "MAX_PRICE_FFILL_WEEKS", 8)
    old = DATE - pd.Timedelta(weeks=9)
    bt = _backtester(prices=_prices(a_date=old))
    _run_event(bt)
    assert "A.ST" not in bt._portfolio
    assert any(
        row["ticker"] == "A.ST" and "stale_price" in row["reasons"]
        for row in bt._event_decisions)


def test_custom_hard_exit_hook_blocks_same_cycle_entry(monkeypatch):
    monkeypatch.setattr(config, "ATR_STOP_ENABLED", False)

    class DelistingBacktester(MomentumBacktester):
        def _additional_event_hard_exit_reasons(self, ticker, date):
            return ["delisting"] if ticker == "A.ST" else []

    base = _backtester()
    bt = DelistingBacktester(
        _signals(), _prices(), initial_capital=1_000, market_filter=False)
    bt._portfolio = dict(base._portfolio)
    bt._close_panel = base._close_panel
    bt._below_sma = base._below_sma
    bt._atr_panel = base._atr_panel
    bt._correlation_filter = lambda weights, date: weights
    bt._sector_exposure_filter = lambda weights: weights
    _run_event(bt)
    assert "A.ST" not in bt._portfolio
    assert any(
        row["ticker"] == "A.ST" and "delisting" in row["reasons"]
        for row in bt._event_decisions)
