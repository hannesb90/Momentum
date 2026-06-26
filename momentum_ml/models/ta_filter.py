"""
models/ta_filter.py – Valbart teknisk-analys-filter ovanpå modellsignalerna.

Bekräftelselager: modellen (LGBM+LSTM-ensemble) avgör VAD som ska köpas, och
det här filtret kräver att den klassiska tekniska analysen håller med innan en
köpsignal får full vikt. Alla villkor läses från TA-features som redan
beräknats per ticker i feature_engineering.py – inget nytt hämtas eller räknas
om.

Två appliceringslägen (se ensemble.build_full_output):
  gate  – köpsignalen nollas helt om de krävda villkoren inte uppfylls
  score – position_size skalas med andelen uppfyllda villkor (0..1)

Stränghet styr vilka villkor som krävs (config.TA_FILTER_STRICTNESS):
  loose    – pris > SMA52
  moderate – trend (ADX) + riktning upp + pris > SMA52
  strict   – alla ovan + nära 52v-högsta + ej överköpt
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Callable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


# ── Enskilda villkor (returnerar True om TA bekräftar) ───────────────────────
# Varje villkor läser en feature-rad (pd.Series) för en ticker vid ett datum.
# NaN-värden ger False (konservativt: saknad bekräftelse räknas som icke-bekräftad).

def _cond_trend_strength(row: pd.Series) -> bool:
    """ADX över tröskeln = en riktig trend, inte bara brus."""
    return bool(row.get("adx", np.nan) >= config.TA_FILTER_ADX_MIN)


def _cond_uptrend(row: pd.Series) -> bool:
    """Riktningen är upp (+DI > -DI)."""
    return bool(row.get("adx_trend", 0) == 1 and row.get("di_diff", 0) > 0)


def _cond_above_sma52(row: pd.Series) -> bool:
    """Priset ligger över sitt 52-veckors glidande medel."""
    return bool(row.get("price_vs_sma52", np.nan) > 0)


def _cond_near_high(row: pd.Series) -> bool:
    """Priset är nära sin 52-veckors högsta (momentum-bekräftelse)."""
    return bool(row.get("high52_ratio", np.nan) >= config.TA_FILTER_HIGH52_MIN)


def _cond_not_overbought(row: pd.Series) -> bool:
    """Inte kraftigt överköpt enligt Bollinger-position."""
    return bool(row.get("bb_position", np.nan) <= config.TA_FILTER_BB_MAX)


STRICTNESS_CONDITIONS: dict[str, List[Callable[[pd.Series], bool]]] = {
    "loose":    [_cond_above_sma52],
    "moderate": [_cond_trend_strength, _cond_uptrend, _cond_above_sma52],
    "strict":   [_cond_trend_strength, _cond_uptrend, _cond_above_sma52,
                 _cond_near_high, _cond_not_overbought],
}


def ta_confirmation(
    row: pd.Series,
    strictness: str = None,
) -> Tuple[bool, float]:
    """
    Utvärderar TA-villkoren för en feature-rad.

    Returnerar (passed_all, score):
      passed_all – True om ALLA krävda villkor uppfylls (för gate-läget)
      score      – andel uppfyllda villkor, 0..1 (för score-läget)
    """
    strictness = strictness or config.TA_FILTER_STRICTNESS
    conds = STRICTNESS_CONDITIONS.get(strictness)
    if conds is None:
        raise ValueError(
            f"Okänd TA-stränghet: {strictness!r}. "
            f"Välj en av {list(STRICTNESS_CONDITIONS)}."
        )

    results = [c(row) for c in conds]
    score = sum(results) / len(results)
    return all(results), float(score)
