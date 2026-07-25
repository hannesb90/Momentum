import pandas as pd

from eodhd_delisted_import import normalize_prices, warning


def test_subscription_warning_is_not_price_data():
    payload = [{"warning": "Data is limited by one year"}]
    assert warning(payload)
    assert normalize_prices(payload).empty


def test_normalizes_valid_daily_ohlcv():
    payload = [{
        "date": "2025-01-02", "open": 1, "high": 2, "low": .5,
        "close": 1.5, "adjusted_close": 1.4, "volume": 100,
    }]
    result = normalize_prices(payload)
    assert list(result.Date) == [pd.Timestamp("2025-01-02")]
    assert result.iloc[0].AdjustedClose == 1.4
