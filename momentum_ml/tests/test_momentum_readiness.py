import json
from pathlib import Path

from momentum_readiness import challenger_gate


def test_challenger_gate_requires_maturity_and_positive_metrics(tmp_path: Path):
    path = tmp_path / "card.json"
    path.write_text(json.dumps({
        "matured_prediction_dates": 8,
        "forward_metrics": {"mean_ic": .05, "mean_top20_spread": .02},
    }))
    assert challenger_gate(path)["ready"] is True


def test_challenger_gate_rejects_negative_spread(tmp_path: Path):
    path = tmp_path / "card.json"
    path.write_text(json.dumps({
        "matured_prediction_dates": 8,
        "forward_metrics": {"mean_ic": .05, "mean_top10_spread": -.01},
    }))
    assert challenger_gate(path)["ready"] is False
