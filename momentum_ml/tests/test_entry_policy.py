import numpy as np
import pandas as pd

from models.entry_policy import decide_entry
from portfolio import _new_entry_allowed


def frame(**overrides):
    values = {
        "roc_8w": 0.0, "roc_13w": 0.0, "roc_26w": 0.0, "mom_12_1": 0.0,
        "report_reaction_abn": np.nan, "rev_growth_yoy": np.nan,
        "eps_growth_yoy": np.nan,
    }
    values.update(overrides)
    return pd.DataFrame([values])


def test_small_overextension_is_blocked_when_fundamentals_are_missing():
    decision = decide_entry("small", frame(roc_13w=1.01), True)
    assert not decision.eligible
    assert decision.action == "blocked_overextended"


def test_small_override_requires_report_and_verified_growth():
    incomplete = decide_entry(
        "small", frame(roc_13w=1.2, report_reaction_abn=0.1), True)
    confirmed = decide_entry(
        "small",
        frame(roc_13w=1.2, report_reaction_abn=0.1, rev_growth_yoy=0.2),
        True,
    )
    assert not incomplete.eligible
    assert confirmed.eligible
    assert confirmed.action == "fundamental_override"


def test_large_overextension_is_annotation_only():
    decision = decide_entry("large", frame(roc_13w=1.5), True)
    assert decision.eligible
    assert decision.overextended


def test_policy_never_makes_ineligible_candidate_eligible():
    decision = decide_entry(
        "small",
        frame(roc_13w=1.2, report_reaction_abn=0.1, eps_growth_yoy=0.2),
        False,
    )
    assert not decision.eligible


def test_cooldown_uses_only_trailing_history():
    history = pd.concat(
        [frame(roc_13w=1.2), frame(roc_13w=0.2)], ignore_index=True)
    decision = decide_entry("small", history, True)
    assert decision.eligible
    assert decision.action == "cooldown_review"


def test_new_entry_veto_does_not_block_existing_holding_refill():
    assert not _new_entry_allowed(False, is_owned=False)
    assert _new_entry_allowed(False, is_owned=True)
    assert _new_entry_allowed(None, is_owned=False)
