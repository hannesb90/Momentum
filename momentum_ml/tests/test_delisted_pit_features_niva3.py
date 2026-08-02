import numpy as np
import pandas as pd

from build_delisted_pit_features_niva3 import match_score


def test_match_score_identifies_same_return_path_despite_price_scale():
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    close = 100 * np.cumprod(1 + np.sin(np.arange(100)) / 100)
    eod = pd.DataFrame({"Date": dates, "Close": close})
    bors = pd.DataFrame({"d": dates, "c": close * 7})
    result = match_score(eod, bors)
    assert result["overlap"] >= 90
    assert result["correlation"] > .999999
    assert result["median_abs_return_diff"] < 1e-12
