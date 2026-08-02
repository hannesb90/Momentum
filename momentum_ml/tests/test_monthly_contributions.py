import pandas as pd
from tune_monthly_contributions import stats

def test_twr_removes_external_cash_flow():
    frame=pd.DataFrame({"portfolio_value":[100000.,100010.,100020.],"external_flow":[0.,10.,10.],
                        "cash":[100000.,100010.,100020.],"n_positions":[0,0,0]},
                       index=pd.to_datetime(["2020-01-01","2020-02-01","2020-03-01"]))
    result=stats(frame)
    assert abs(result["TWR_CAGR"]) < 1e-12
    assert result["contributed"] == 100020.
