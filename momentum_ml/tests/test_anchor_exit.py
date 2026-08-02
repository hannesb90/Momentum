import numpy as np
import pandas as pd

from tune_anchor_exit import add_oof_anchors


def _signals(dates):
    return pd.DataFrame({
        "Date": dates, "ticker": "A.ST", "prob_rank": .8,
        "pred_return": .2, "sector": "Industrials",
        "selection_rank": 1.0, "selection_eligible": 1,
    }).set_index("Date")


def test_future_prices_do_not_change_earlier_anchor():
    dates = pd.date_range("2018-01-01", periods=180, freq="W-MON")
    close = pd.DataFrame({"A.ST": np.linspace(100, 220, len(dates))}, index=dates)
    signals = _signals(dates)
    base = add_oof_anchors(signals, close)
    changed = close.copy()
    changed.loc[dates[-20]:, "A.ST"] *= 10
    other = add_oof_anchors(signals, changed)
    cutoff = dates[-72]
    pd.testing.assert_series_equal(
        base.loc[:cutoff, "anchor_return"], other.loc[:cutoff, "anchor_return"])
