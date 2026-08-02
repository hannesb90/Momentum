import pandas as pd

from altdata.borsdata import (
    adjust_ohlc_for_dividends, normalize_dividends_for_splits,
    split_events_map, stockprices_ohlcv,
)


def test_stockprices_schema_is_normalized(monkeypatch):
    monkeypatch.setattr(
        "altdata.borsdata._find_stockprice_endpoint_data",
        lambda ins_id, use_cache=True: {"stockPricesList": [{
            "d": "2025-01-02", "o": 10, "h": 12, "l": 9, "c": 11, "v": 100,
        }]},
    )
    frame = stockprices_ohlcv(1)
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.loc[pd.Timestamp("2025-01-02"), "Close"] == 11


def test_dividend_adjustment_removes_ex_date_price_drop():
    idx = pd.to_datetime(["2025-04-01", "2025-04-02"])
    frame = pd.DataFrame({
        "Open": [100.0, 95.0], "High": [101.0, 96.0],
        "Low": [99.0, 94.0], "Close": [100.0, 95.0],
        "Volume": [10, 20],
    }, index=idx)
    events = pd.DataFrame({"ex_date": [pd.Timestamp("2025-04-02")], "amount": [5.0]})
    adjusted = adjust_ohlc_for_dividends(frame, events)
    assert adjusted.loc["2025-04-01", "Close"] == 95.0
    assert adjusted.loc["2025-04-02", "Close"] == 95.0
    assert adjusted["Volume"].tolist() == [10, 20]


def test_future_dividend_is_not_applied():
    frame = pd.DataFrame({
        "Open": [100.0], "High": [100.0], "Low": [100.0],
        "Close": [100.0], "Volume": [10],
    }, index=pd.to_datetime(["2025-04-01"]))
    events = pd.DataFrame({"ex_date": [pd.Timestamp("2025-05-01")], "amount": [5.0]})
    assert adjust_ohlc_for_dividends(frame, events).equals(frame)


def test_old_dividend_is_normalized_for_later_split():
    events = pd.DataFrame({
        "ex_date": [pd.Timestamp("2019-04-01")], "amount": [4.0]
    })
    normalized = normalize_dividends_for_splits(
        events, [(pd.Timestamp("2020-09-15"), 4.0)]
    )
    assert normalized.iloc[0]["amount"] == 1.0


def test_split_schema_uses_instrument_id_and_ratio_string():
    parsed = split_events_map({"stockSplitList": [{
        "instrumentId": 8, "ratio": "4:1", "splitDate": "2020-09-15T00:00:00"
    }]})
    assert parsed[8][0][1] == 4.0
