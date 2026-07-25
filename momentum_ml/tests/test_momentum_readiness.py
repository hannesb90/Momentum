import json
from pathlib import Path

from momentum_readiness import challenger_gate, forward_signal_gate, regime_gate


def test_challenger_gate_requires_maturity_and_positive_metrics(tmp_path: Path):
    path = tmp_path / "card.json"
    path.write_text(json.dumps({
        "matured_prediction_dates": 13,
        "forward_metrics": {
            "mean_ic": .05, "positive_ic_share": .62,
            "mean_top20_spread": .02,
            "positive_top_spread_share": .62,
        },
    }))
    assert challenger_gate(path)["ready"] is True


def test_challenger_gate_rejects_negative_spread(tmp_path: Path):
    path = tmp_path / "card.json"
    path.write_text(json.dumps({
        "matured_prediction_dates": 13,
        "forward_metrics": {
            "mean_ic": .05, "positive_ic_share": .62,
            "mean_top10_spread": -.01,
            "positive_top_spread_share": .62,
        },
    }))
    assert challenger_gate(path)["ready"] is False


def test_regime_gate_rejects_wrong_direction_despite_raw_accuracy(tmp_path: Path):
    path = tmp_path / "regime.json"
    path.write_text(json.dumps({"current": {
        "modern_accuracy_4w": .60, "modern_accuracy_13w": .60,
        "modern_separation_4w": -.01, "modern_separation_13w": .02,
    }}))
    assert regime_gate(path)["forecast_approved"] is False


def test_forward_signal_gate_requires_consistent_positive_alpha(tmp_path: Path):
    path = tmp_path / "signal.json"
    path.write_text(json.dumps({
        "matured_dates": 13,
        "forward_metrics": {
            "mean_spread": .02, "positive_spread_share": .62,
        },
    }))
    assert forward_signal_gate(path)["ready"] is True
