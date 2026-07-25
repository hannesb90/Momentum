import pandas as pd

from target_revision_challenger import evaluate


def test_revision_scorecard_detects_forward_spread():
    rows = []
    for week in range(16):
        for ticker in range(20):
            quality = ticker / 19
            rows.append({
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(weeks=week),
                "ticker": f"T{ticker}",
                "target_mean": 100 * (1 + week * quality * .01),
                "price_now": 100 * (1 + week * quality * .02),
            })
    card = evaluate(pd.DataFrame(rows), horizon_obs=13)
    assert card["matured_dates"] == 2
    assert card["forward_metrics"]["mean_spread"] > 0
