"""Causal, segment-specific entry policy for live serving signals."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EntryDecision:
    eligible: bool
    action: str
    overextended: bool
    fundamental_override: bool
    peak_roc13_13w: float


def _finite(value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return np.nan
    return value if np.isfinite(value) else np.nan


def decide_entry(segment: str, history: pd.DataFrame,
                 base_eligible: bool) -> EntryDecision:
    """Decide from data available at the signal date; missing is not evidence."""
    if history.empty:
        return EntryDecision(bool(base_eligible), "normal", False, False, np.nan)

    row = history.iloc[-1]
    roc13 = _finite(row.get("roc_13w"))
    roc8 = _finite(row.get("roc_8w"))
    roc26 = _finite(row.get("roc_26w"))
    mom121 = _finite(row.get("mom_12_1"))
    report = _finite(row.get("report_reaction_abn"))
    revenue = _finite(row.get("rev_growth_yoy"))
    eps = _finite(row.get("eps_growth_yoy"))
    peaks = pd.to_numeric(history.get("roc_13w", pd.Series(dtype=float)),
                          errors="coerce").tail(13)
    peak13 = _finite(peaks.max()) if len(peaks) else np.nan

    confirmed = bool(
        np.isfinite(report) and report > 0
        and ((np.isfinite(revenue) and revenue > 0)
             or (np.isfinite(eps) and eps > 0))
    )
    overextended = bool(np.isfinite(roc13) and roc13 >= 1.0)
    cooldown = bool(np.isfinite(peak13) and peak13 >= 1.0 and not overextended)
    long_runup = bool(
        (np.isfinite(roc26) and roc26 >= 1.0)
        or (np.isfinite(mom121) and mom121 >= 1.0)
    )

    eligible = bool(base_eligible)
    if segment == "small" and overextended and not confirmed:
        eligible = False
        action = "blocked_overextended"
    elif segment == "small" and overextended:
        action = "fundamental_override"
    elif cooldown:
        action = "cooldown_review"
    elif long_runup:
        action = "long_runup_review"
    elif segment == "small" and np.isfinite(roc8) and roc8 >= 0.35 and confirmed:
        action = "early_second_opinion"
    elif segment == "large" and np.isfinite(roc13) and roc13 >= 0.40 and confirmed:
        action = "early_second_opinion"
    else:
        action = "normal"

    return EntryDecision(eligible, action, overextended, confirmed, peak13)
