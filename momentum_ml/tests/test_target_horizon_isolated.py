import pandas as pd
from tune_target_horizon_isolated import targets_from_prices

def test_forward_target_uses_exact_requested_horizon():
    idx=pd.date_range("2020-01-06",periods=60,freq="W-MON")
    base=pd.DataFrame({"ticker":"A"},index=idx);prices={"A":pd.DataFrame({"Close":range(1,61)},index=idx)}
    t=targets_from_prices(base,prices,13)
    assert abs(t.target_return.iloc[0]-(14/1-1))<1e-12
    assert pd.isna(t.target_return.iloc[-1])
