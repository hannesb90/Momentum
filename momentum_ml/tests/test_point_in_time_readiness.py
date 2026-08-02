import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
try:
    from momentum_readiness import point_in_time_gate
except ImportError:
    from momentum_readiness_pit import point_in_time_gate


def test_pit_gate_blocks_when_delisted_prices_are_missing(tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({
        "intervals": 700, "corporate_actions": 5000,
        "delisted_missing_price": 84,
        "blocking_reason": "delisted_price_history_missing",
    }))
    result = point_in_time_gate(path)
    assert result["historical_backtest_ready"] is False
    assert result["checks"]["all_delisted_have_prices"] is False


def test_pit_gate_passes_complete_registry(tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({
        "intervals": 700, "corporate_actions": 5000,
        "delisted_missing_price": 0,
    }))
    assert point_in_time_gate(path)["historical_backtest_ready"] is True
