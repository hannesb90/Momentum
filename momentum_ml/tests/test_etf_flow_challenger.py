import pandas as pd

from etf_flow_challenger import evaluate


def test_forward_scorecard_is_causal_and_detects_positive_spread():
    rows = []
    for day in range(25):
        for ticker in range(12):
            rows.append({
                "snapshot_date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
                "ticker": f"T{ticker}", "flow_score": ticker / 11,
                "last": 100 + day * (1 + ticker / 11),
            })
    card = evaluate(pd.DataFrame(rows), horizon_obs=20)
    assert card["matured_dates"] == 5
    assert card["forward_metrics"]["mean_spread"] > 0
