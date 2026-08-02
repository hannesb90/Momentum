import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
import main  # noqa: E402


def test_model_contract_rejects_wrong_horizon(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORWARD_WEEKS", 13)
    model = SimpleNamespace(training_contract_={
        "forward_weeks": 52,
        "feature_cols": list(main.FEATURE_COLS),
    })
    with pytest.raises(RuntimeError, match="matchar inte"):
        main._assert_model_contract(model, str(tmp_path))


def test_legacy_model_contract_uses_stats_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORWARD_WEEKS", 13)
    (tmp_path / "stats.json").write_text(json.dumps({"horizon_weeks": 52}))
    with pytest.raises(RuntimeError, match="Full omträning"):
        main._assert_model_contract(SimpleNamespace(), str(tmp_path))
