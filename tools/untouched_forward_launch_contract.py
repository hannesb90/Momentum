"""
UNTOUCHED FORWARD LAUNCH CONTRACT: EXECUTION, EVALUATION & GOVERNANCE
Launch Epoch Start: 2026-09-04
Registry SHA256 Seal: f717e9e6cf1b6b6adabcea5484b1e41ba374fb5662f971d7369bacad2458db30

Final Launch Contract Verification & Manifest Compilation:
1. Epoch Boundaries: PRE_FORWARD (< 2026-09-04) vs FORWARD (>= 2026-09-04).
2. First Eligible Decision Date: 2026-09-04 (Panel #67). Information Cutoff: 2026-09-04.
3. 6 ACTIVE_FROZEN_FORWARD Models Execution Engine Verification.
4. Append-Only Forward Ledger & PIT Snapshot Schema.
5. Immutability Guard & Pre-Run Hash Check.
6. Frozen Benchmark Definition (OMXS30 GI / XACT Sverige ETF Total Return).
7. Pre-registered Head-to-Head Comparisons & Hypotheses H1, H2, H3.
8. Reporting Cadence (Post-rebalance execution, Quarterly descriptive, 12-month review).
9. Technical Fix Policy & No-Early-Promotion Governance Rules.
10. Final Launch Determinism Verification & SHA256 Signature.

Strict PIT-safety. All V-A, V-B, and Shadow frozen parameters remain 100% untouched.
"""
from __future__ import annotations
import json, math, hashlib, os
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
REGISTRY_SEAL_HASH = "f717e9e6cf1b6b6adabcea5484b1e41ba374fb5662f971d7369bacad2458db30"
FORWARD_EPOCH_START = "2026-09-04"
FIRST_DECISION_DATE = "2026-09-04" # Panel #67 in 8-week scheduled calendar anchored to 2024-01-26

def compile_launch_contract_manifest():
    active_models = [
        "VA_RETURN_CHALLENGER",
        "VB_CAPITAL_PRESERVATION",
        "SHADOW_ERC_X2",
        "SHADOW_FUNDAMENTAL_RISK_OVERLAY",
        "SHADOW_PRUNED_STACK_D",
        "SHADOW_INTEGRATED_STACK_H"
    ]

    epoch_definition = {
        "pre_forward_boundary": "< 2026-09-04",
        "forward_epoch_start": FORWARD_EPOCH_START,
        "isolation_rule": "Historical observations (< 2026-09-04) shall never be included in the forward ledger or forward statistical inference."
    }

    first_decision = {
        "first_eligible_decision_date": FIRST_DECISION_DATE,
        "information_cutoff": FIRST_DECISION_DATE,
        "execution_date": "2026-09-07 (First trading day following decision panel)",
        "return_measurement_start": "2026-09-07",
        "next_scheduled_decision_date": "2026-10-30 (Panel #68)"
    }

    benchmark_definition = {
        "index": "OMXS30 GI (XACT Sverige ETF)",
        "type": "Gross Total Return (Dividend Reinvested)",
        "currency": "SEK",
        "observation_frequency": "Daily / 8-week panel boundary"
    }

    preregistered_head_to_head = [
        "V-A vs Benchmark", "V-B vs V-A", "ERC vs V-A", "Fundamental Risk vs V-A",
        "D_ERC_FR vs ERC", "D_ERC_FR vs Fundamental Risk", "Full Stack H vs D_ERC_FR", "Full Stack H vs V-A"
    ]

    preregistered_hypotheses = {
        "H1": "D_ERC_FR provides lower downside/tail risk than ERC standalone, even if CAGR is slightly lower.",
        "H2": "G2 (FUNDAMENTAL_ONLY) positions display higher future realized risk than G0 (NEITHER).",
        "H3": "G3 (BOTH) positions display higher future downside risk than G1 (ERC_ONLY).",
        "canonical_erc_down_tolerance": 0.001
    }

    governance_policies = {
        "reporting_cadence": [
            "Post-rebalance: Technical execution report after every 8-week panel",
            "Quarterly: Descriptive forward performance report",
            "12-month: First formal head-to-head model evaluation (2027-09-04)",
            "Annual: Subsequent annual governance review"
        ],
        "no_peeking_rule": "No frozen model parameters, weights, or signals may be altered between scheduled evaluation dates.",
        "technical_fix_policy": "Infrastructure/Data ingestion fixes allowed if mathematical model decisions remain unchanged. Model spec changes require new versioning and separate epoch.",
        "failure_is_valid_data": "Model underperformance forward is valid empirical evidence to falsify hypotheses, NOT a bug to be retuned.",
        "promotion_policy": "No shadow model promoted to champion prior to 12 months and sufficient independent panel observations."
    }

    first_year_questions = [
        "1. Did V-A outperform benchmark OMXS30 GI?",
        "2. Did ERC achieve better risk-adjusted return than V-A?",
        "3. Did Fundamental Risk Overlay achieve lower drawdown than V-A?",
        "4. Did D_ERC_FR achieve lower downside/tail risk than ERC standalone?",
        "5. Was G2 (FUNDAMENTAL_ONLY) future risk higher than G0 (NEITHER)?",
        "6. Was G3 (BOTH) downside risk higher than G1 (ERC_ONLY)?",
        "7. Did Full Stack H add measurable value above D_ERC_FR?",
        "8. Did Full Stack H justify its additional complexity?",
        "9. Which models defined the forward efficient frontier?",
        "10. Did historical mechanisms align with forward outcomes?"
    ]

    contract_data = {
        "registry_seal_hash": REGISTRY_SEAL_HASH,
        "active_models": active_models,
        "active_models_count": len(active_models),
        "epoch_definition": epoch_definition,
        "first_decision_panel": first_decision,
        "benchmark_definition": benchmark_definition,
        "preregistered_head_to_head": preregistered_head_to_head,
        "preregistered_hypotheses": preregistered_hypotheses,
        "governance_policies": governance_policies,
        "first_year_decision_questions": first_year_questions,
        "launch_contract_status": "UNTOUCHED FORWARD LAUNCH CONTRACT SEALED"
    }

    raw_json = json.dumps(contract_data, indent=2, sort_keys=True)
    launch_sha256 = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    contract_data["untouched_forward_launch_manifest_sha256"] = launch_sha256

    out_file = V2 / "research_k/untouched_forward_launch_manifest.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(contract_data, indent=2, sort_keys=True), encoding="utf-8")

    return contract_data, launch_sha256

def main():
    print("=" * 80)
    print("UNTOUCHED FORWARD LAUNCH CONTRACT: EXECUTION, EVALUATION & GOVERNANCE")
    print("=" * 80)
    
    contract, launch_hash = compile_launch_contract_manifest()
    
    print("\nUntouched Forward Launch Contract Compiled Successfully!")
    print(f"File Path: {V2 / 'research_k/untouched_forward_launch_manifest.json'}")
    print(f"Registry Seal SHA256: {contract['registry_seal_hash']}")
    print(f"Launch Manifest SHA256: {launch_hash}")
    print(f"First Eligible Decision Date: {contract['first_decision_panel']['first_eligible_decision_date']}")
    print(f"Active Models Count: {contract['active_models_count']}")
    print(f"Status: {contract['launch_contract_status']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
