import pandas as pd
from tune_conditional_13_overlay import make_variant


def test_variants_select_exactly_top_n_when_panel_is_large():
    date=pd.Timestamp("2020-01-06")
    n=20
    frame=pd.DataFrame({"ticker":[f"T{i}" for i in range(n)],
        "selection_rank":range(n),"selection_eligible":1,
        "roc_13w":range(n-1,-1,-1),"roc_accel_4w":range(n)},index=[date]*n)
    for variant in ("baseline_52","agreement","positive_acceleration","top_quintile_tiebreak"):
        out=make_variant(frame,variant)
        assert out.pred_signal.sum()==15
        assert abs(out.position_size.sum()-1)<1e-12
