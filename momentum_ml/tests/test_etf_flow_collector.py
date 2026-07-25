from datetime import datetime, timezone
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import etf_flow_collector as collector


def test_title_match_requires_exact_terminal_ticker():
    assert collector.title_has_ticker("Example UCITS ETF (EXV3)", "EXV3.DE")
    assert not collector.title_has_ticker("Example EXV3 leveraged", "EXV3.DE")


def test_fund_name_tokens_ignore_share_class_noise():
    wanted = collector.fund_name_tokens("iShares Automation & Robotics UCITS")
    title = collector.fund_name_tokens(
        "iShares Automation & Robotics UCITS ETF USD (Acc) (2B76)")
    assert wanted.issubset(title)


def test_enrich_calculates_owner_change_without_cross_ticker_leakage():
    frame = pd.DataFrame([
        {"snapshot_date": "2026-01-01", "collected_at": "a", "ticker": "A",
         "number_of_owners": 100, "last": 10, "vwap": 10},
        {"snapshot_date": "2026-01-02", "collected_at": "b", "ticker": "A",
         "number_of_owners": 110, "last": 11, "vwap": 10},
        {"snapshot_date": "2026-01-02", "collected_at": "b", "ticker": "B",
         "number_of_owners": 50, "last": 10, "vwap": 10},
    ])
    result = collector.enrich(frame)
    a2 = result[(result.ticker == "A") &
                (result.snapshot_date == "2026-01-02")].iloc[0]
    b2 = result[result.ticker == "B"].iloc[0]
    assert a2.owner_change_1d == 10
    assert round(a2.owner_change_pct_1d, 6) == 0.1
    assert pd.isna(b2.owner_change_1d)


def test_snapshot_marks_avanza_quote_as_delayed():
    meta = type("Meta", (), {
        "ticker": "EXV3.DE", "name": "ETF", "group": "Technology",
        "kind": "sector",
    })
    info = {
        "quote": {
            "last": 93.0, "volumeWeightedAveragePrice": 92.5,
            "totalVolumeTraded": 1000, "totalValueTraded": 92500,
            "timeOfLast": 1_700_000_000_000, "isRealTime": False,
        },
        "keyIndicators": {"numberOfOwners": 126},
        "listing": {"currency": "EUR"},
    }
    row = collector.snapshot_row(
        meta, {"orderBookId": "1"}, info,
        datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert row["is_real_time"] is False
    assert row["number_of_owners"] == 126


def test_enrich_builds_persistent_multi_observation_flow_score():
    rows = [
        {"snapshot_date": f"2026-01-0{i}", "collected_at": str(i),
         "ticker": "A", "kind": "sector", "number_of_owners": 100 + i,
         "last": 10, "vwap": 10}
        for i in range(1, 7)
    ]
    result = collector.enrich(pd.DataFrame(rows))
    latest = result.iloc[-1]
    assert latest.owner_change_5obs == 5
    assert latest.owner_flow_persistence_5obs == 1
    assert pd.notna(latest.flow_score)
