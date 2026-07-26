import purchase_review as pr


def test_unsourced_claims_and_updates_are_discarded():
    result = pr.validate_review({
        "verdict": "review",
        "confidence": 1.2,
        "summary": "Kontrollera.",
        "positive_signals": [
            {"claim": "med källa", "source_url": "https://example.com/a",
             "source_date": "2026-07-26"},
            {"claim": "utan källa", "source_date": "2026-07-26"},
        ],
        "negative_signals": [],
        "proposed_universe_updates": [
            {"field": "rev_growth_yoy", "new_value": 0.2, "as_of": "2026-06-30",
             "source_url": "https://example.com/report"},
            {"field": "eps_growth_yoy", "new_value": 0.3, "as_of": "2026-06-30"},
        ],
    })
    assert result["confidence"] == 1.0
    assert len(result["positive_signals"]) == 1
    assert len(result["proposed_universe_updates"]) == 1


def test_invalid_verdict_fails_closed():
    assert "error" in pr.validate_review({"verdict": "buy"})
