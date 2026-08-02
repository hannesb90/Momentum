import pandas as pd
from validate_binary_shadow_pipeline import resolution, preds_from_panel

def test_raw_scores_do_not_become_constant_half():
    d=pd.Timestamp("2020-01-06")
    p=pd.DataFrame({"ticker":["A","B","C"],"raw":[.2,.5,.8]},index=[d]*3)
    preds=preds_from_panel(p)
    joined=pd.concat(preds.values())
    assert joined.prob_up.nunique()==3
    assert resolution(p,"raw")["median_largest_plateau"]==1/3
