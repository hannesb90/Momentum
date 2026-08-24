#!/usr/bin/env python3
"""Registrerar H1 (Drawdown Resilience) och H2 (Trend Strength) i observationsjournalen.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL_DIR = ROOT / "journals_observation"

ts = datetime.now(timezone.utc).isoformat()

h1_entry = {
    "journal_init_timestamp": ts,
    "model_key": "OBS_H1_DRAW_RESILIENCE",
    "journal_class": "OBSERVATION_ONLY — NOT PART OF THE SEALED FORWARD SET",
    "promotion_rights": "NONE on historical data. Forward evidence only.",
    "contamination_note": "Formellt registrerad i observationsjournalen för framåtutvärdering fr.o.m. 2026-09-04. Ingen befordran på historiska tal.",
    "model_spec": {
        "selector": "0.5*rank(H0 score) + 0.5*rank(drawdown_resilience)",
        "factor": "drawdown_resilience = -abs(trailing 52-calendar-week maximum drawdown from PIT adjusted closes)",
        "n_top": 30,
        "weighting": "equal_weight",
        "rebalance_freq_weeks": 8,
        "execution": "T+1 PIT",
        "cost_oneway_bp": 20,
        "role": "CHALLENGER H1 — Drawdown Resilience"
    },
    "historical_background_not_forward": {
        "cagr_20panel": 0.2385,
        "cagr_66panel": 0.1106,
        "maxdd_20panel": -0.0454,
        "maxdd_66panel": -0.2253,
        "vinnare_fangst_median": 0.1001,
        "forlorare_fangst_median": 0.1112,
        "top30_ic": 0.1217
    },
    "forward_epoch_start": "2026-09-04",
    "source_lock": "research_i/forward_challengers/H1_DRAW_RESILIENCE/LOCK.json"
}

h2_entry = {
    "journal_init_timestamp": ts,
    "model_key": "OBS_H2_TREND_STRENGTH",
    "journal_class": "OBSERVATION_ONLY — NOT PART OF THE SEALED FORWARD SET",
    "promotion_rights": "NONE on historical data. Forward evidence only.",
    "contamination_note": "Formellt registrerad i observationsjournalen för framåtutvärdering fr.o.m. 2026-09-04. Ingen befordran på historiska tal.",
    "model_spec": {
        "selector": "0.5*rank(H0 score) + 0.5*rank(trend_strength)",
        "factor": "trend_strength = OLS t-stat of log adjusted close on daily observation index over trailing 52 calendar weeks (min 200 obs)",
        "n_top": 30,
        "weighting": "equal_weight",
        "rebalance_freq_weeks": 8,
        "execution": "T+1 PIT",
        "cost_oneway_bp": 20,
        "role": "CHALLENGER H2 — Trend Strength"
    },
    "historical_background_not_forward": {
        "cagr_20panel": 0.2698,
        "cagr_66panel": 0.0818,
        "maxdd_20panel": -0.0268,
        "maxdd_66panel": -0.3384,
        "vinnare_fangst_median": 0.0562,
        "forlorare_fangst_median": 0.1391,
        "top30_ic": 0.0096
    },
    "forward_epoch_start": "2026-09-04",
    "source_lock": "research_i/forward_challengers/H2_TREND_STRENGTH/LOCK.json"
}

# Write observation files
p_h1 = JOURNAL_DIR / "OBS_H1_DRAW_RESILIENCE_FORWARD.jsonl"
p_h1.write_text(json.dumps(h1_entry, ensure_ascii=False) + "\n")

p_h2 = JOURNAL_DIR / "OBS_H2_TREND_STRENGTH_FORWARD.jsonl"
p_h2.write_text(json.dumps(h2_entry, ensure_ascii=False) + "\n")

# Update manifest
manifest_path = JOURNAL_DIR / "_MANIFEST.json"
manifest = json.loads(manifest_path.read_text())

arms = manifest.get("arms", [])
for arm in ["OBS_H1_DRAW_RESILIENCE", "OBS_H2_TREND_STRENGTH"]:
    if arm not in arms:
        arms.append(arm)
manifest["arms"] = arms
manifest["last_updated_utc"] = ts

manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print("Registered OBS_H1_DRAW_RESILIENCE and OBS_H2_TREND_STRENGTH successfully in journals_observation.")
