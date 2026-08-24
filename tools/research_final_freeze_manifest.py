"""
FINAL SYSTEM FREEZE MANIFEST & FORWARD JOURNAL INITIALIZER
Period Anchor: 2026-08-10
First Untouched Forward Decision Panel: 2026-09-04 (Panel #67)

Frozen Models (6 Total):
1. T0_A_CONTROL_H0 (Baseline 50/50 12m+18m Momentum Top-30)
2. CONTROL_C_SMA200 (H0 + SMA200 SKIP Entry Gate)
3. VA_RETURN_CHALLENGER (Control C + Inverse Vol 60d, Caps/Floors 1-6%)
4. VB_CAPITAL_PRESERVATION_CHALLENGER (V-A + Target Vol 15%)
5. SHADOW_ERC_X2 (Equal Risk Contribution Shadow Model)
6. SHADOW_FUNDAMENTAL_RISK_OVERLAY (V-A-FR 0.75x Unconfirmed Risk Overlay)

Generates immutable SHA256 signatures and locks all model parameters permanently.
"""
from __future__ import annotations
import json, hashlib, os
from datetime import datetime
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")

def main():
    print("=" * 80)
    print("FINAL SYSTEM FREEZE MANIFEST GENERATION")
    print("Timestamp: 2026-08-10T17:46:37+02:00")
    print("=" * 80)

    models = {
        "T0_A_CONTROL_H0": {
            "role": "CONTROL",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": None,
            "weighting": "equal_weight",
            "target_vol": None,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — CONTROL"
        },
        "CONTROL_C_SMA200": {
            "role": "CONTROL",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": "SMA200 SKIP on T close",
            "weighting": "equal_weight",
            "target_vol": None,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — CONTROL"
        },
        "VA_RETURN_CHALLENGER": {
            "role": "CHALLENGER (RETURN OPTIMIZED)",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": "SMA200 SKIP on T close",
            "weighting": "inverse_vol_60d",
            "caps_floors": [0.01, 0.06],
            "target_vol": None,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — V-A CHALLENGER"
        },
        "VB_CAPITAL_PRESERVATION_CHALLENGER": {
            "role": "CHALLENGER (CAPITAL PRESERVATION)",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": "SMA200 SKIP on T close",
            "weighting": "inverse_vol_60d",
            "caps_floors": [0.01, 0.06],
            "target_vol": 0.15,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — V-B CHALLENGER"
        },
        "SHADOW_ERC_X2": {
            "role": "SHADOW EXPERIMENTAL",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": "SMA200 SKIP on T close",
            "weighting": "equal_risk_contribution_60d",
            "caps_floors": [0.01, 0.06],
            "target_vol": None,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — SHADOW EXPERIMENTAL"
        },
        "SHADOW_FUNDAMENTAL_RISK_OVERLAY": {
            "role": "SHADOW EXPERIMENTAL",
            "selector": "50/50 12m + 18m momentum",
            "n_top": 30,
            "rebalance_freq_weeks": 8,
            "entry_gate": "SMA200 SKIP on T close",
            "weighting": "inverse_vol_60d_with_0.75x_unconfirmed_risk_overlay",
            "caps_floors": [0.01, 0.06],
            "target_vol": None,
            "execution": "T+1 PIT",
            "status": "FROZEN FOR FORWARD — SHADOW EXPERIMENTAL"
        }
    }

    manifest_content = {
        "freeze_timestamp": "2026-08-10T17:46:37+02:00",
        "first_untouched_forward_panel_date": "2026-09-04",
        "n_frozen_models": len(models),
        "models": models,
        "governance_rules": [
            "TOUCHLESS FORWARD VALIDATION — NO TUNING",
            "NO PARAMETER MODIFICATION ON FORWARD DATA",
            "IMMUTABLE APPEND-ONLY JOURNALING",
            "FORWARD GOALPOSTS PERMANENTLY LOCKED"
        ]
    }

    bytes_data = json.dumps(manifest_content, indent=2, sort_keys=True).encode("utf-8")
    sha256_hash = hashlib.sha256(bytes_data).hexdigest()
    manifest_content["sha256_system_manifest_hash"] = sha256_hash

    manifest_file = V2 / "research_k/final_system_freeze_manifest.json"
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest_content, indent=2, sort_keys=True), encoding="utf-8")

    # Ensure forward journals directory exists
    journals_dir = V2 / "journals"
    journals_dir.mkdir(parents=True, exist_ok=True)

    journal_files = {
        "T0_A_CONTROL_H0": journals_dir / "T0_A_CONTROL_H0_FORWARD.jsonl",
        "CONTROL_C_SMA200": journals_dir / "CONTROL_C_SMA200_FORWARD.jsonl",
        "VA_RETURN_CHALLENGER": journals_dir / "VA_RETURN_CHALLENGER_FORWARD.jsonl",
        "VB_CAPITAL_PRESERVATION_CHALLENGER": journals_dir / "VB_CAPITAL_PRESERVATION_CHALLENGER_FORWARD.jsonl",
        "SHADOW_ERC_X2": journals_dir / "SHADOW_ERC_X2_FORWARD.jsonl",
        "SHADOW_FUNDAMENTAL_RISK_OVERLAY": journals_dir / "SHADOW_FUNDAMENTAL_RISK_OVERLAY_FORWARD.jsonl"
    }

    for model_key, j_path in journal_files.items():
        if not j_path.exists():
            header = {
                "journal_init_timestamp": "2026-08-10T17:46:37+02:00",
                "model_key": model_key,
                "model_spec": models[model_key],
                "sha256_system_manifest_hash": sha256_hash,
                "first_untouched_panel_date": "2026-09-04"
            }
            j_path.write_text(json.dumps(header) + "\n", encoding="utf-8")

    print(f"Manifest written to: {manifest_file}")
    print(f"SHA256 Manifest Hash: {sha256_hash}")
    print("=" * 80)
    print("SYSTEM FREEZE COMPLETE — 6 MODELS PERMANENTLY LOCKED")
    print("=" * 80)

if __name__ == "__main__":
    main()
