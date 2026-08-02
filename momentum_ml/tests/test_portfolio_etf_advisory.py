import config
import portfolio


def test_etf_advisory_target_moves_theme_to_core(monkeypatch):
    monkeypatch.setattr(config, "ETF_ADVISORY_ONLY", True)
    target = {"broad": 0.65, "sweden": 0.15, "theme": 0.20, "leverage": 0.0}

    model = portfolio._allocation_target(target)

    assert model["theme"] == 0.0
    assert model["broad"] == 0.85
    assert model["sweden"] == 0.15
    # Den användarsparade/displayade kartan muteras aldrig.
    assert target["theme"] == 0.20


def test_etf_can_be_reenabled_without_changing_target(monkeypatch):
    monkeypatch.setattr(config, "ETF_ADVISORY_ONLY", False)
    target = {"broad": 0.65, "sweden": 0.15, "theme": 0.20, "leverage": 0.0}

    assert portfolio._allocation_target(target) == target
