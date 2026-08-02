import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pandas as pd
import pytest

from conditional_shadow import scorecard, update_holders


def test_core_is_always_bought_and_all_qualified_exits_are_extra():
    holders = update_holders(
        {"OLD": 3}, {"A", "B", "C"}, {"B", "C", "D"},
        {"A": True, "OLD": True}, {"A": False, "OLD": False})
    assert holders == {"OLD": 2, "A": 4}
    assert not (set(holders) & {"B", "C", "D"})


def test_otto_high_blocks_new_and_existing_holder():
    holders = update_holders(
        {"OLD": 3}, {"A", "B"}, {"B", "C"},
        {"A": True, "OLD": True}, {"A": True, "OLD": True})
    assert holders == {}


def test_broken_trend_removes_holder_before_expiry():
    holders = update_holders(
        {"OLD": 4}, set(), set(), {"OLD": False}, {"OLD": False})
    assert holders == {}


def test_scorecard_attributes_alpha_against_base_production_and_index():
    date = pd.Timestamp("2025-01-06")
    ledger = pd.DataFrame({
        "Date": [date] * 4, "ticker": ["C", "B", "P", "X"],
        "version": ["conditional_meta20_holder4_otto_v1"] * 4,
        "realized_13w_return": [.20, .10, .05, .00],
        "selected": [True, False, False, False],
        "challenger_top10": [False, True, False, False],
        "pred_signal": [0, 0, 1, 0],
    })
    metrics = scorecard(ledger, {}, pd.Series({date: .08}))["forward_metrics"]
    assert metrics["mean_alpha_vs_base"] == pytest.approx(.10)
    assert metrics["mean_alpha_vs_production"] == pytest.approx(.15)
    assert metrics["mean_alpha_vs_index"] == pytest.approx(.12)
