"""
RESEARCH AH-FREEZE: CANONICAL INTERPRETATION, GOVERNANCE & FORWARD MANIFEST
Period: 2021-07-16 to 2026-07-10

Compiles the Master Governance JSON Manifest & SHA256 Hash for Untouched Forward Tracking (2026-09-04):
1. Canonical Terminology & Definitions (PREDICTIVELY COMPLEMENTARY BUT IMPLEMENTATIONALLY HIGH-OVERLAP).
2. Canonical Overlap Tolerance (0.10 pp = 0.001) & Canonical 2x2 Matrix (G0=428, G1=76, G2=345, G3=1131, N=1980).
3. Empirical Evidence Summary (G2 vs G0: +4.80 pp vol, p=0.0006; G3 vs G1 descriptive tail risk).
4. Model Freeze Directives (V-A, V-B, ERC, D_ERC_FR, Full Stack).
5. Superseded Historical Statements & Artifacts List.
6. Pre-registered Forward Hypotheses starting 2026-09-04.
7. SHA256 Governance Manifest Signature.

Strict PIT-safety. All V-A, V-B, and Shadow frozen parameters remain 100% untouched.
"""
from __future__ import annotations
import json, math, hashlib, os
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")

def compile_master_governance_manifest():
    canonical_terminology = {
        "term": "PREDICTIVELY COMPLEMENTARY BUT IMPLEMENTATIONALLY HIGH-OVERLAP",
        "predictive_complementarity": "Fundamental Confirmation provides forward risk information not captured by ERC (G2 vs G0 matched vol diff +4.80 pp, p = 0.0006).",
        "implementation_overlap": "ERC and Fundamental Overlay affect a high proportion of the same stock positions (93.70% of ERC-downweighted stocks are also Fundamental-unconfirmed)."
    }

    canonical_overlap = {
        "tolerance": 0.001,
        "tolerance_unit": "0.10 percentage points relative weight deviation",
        "n_total": 1980,
        "matrix_2x2": {
            "G0_NEITHER": 428,
            "G1_ERC_ONLY": 76,
            "G2_FUNDAMENTAL_ONLY": 345,
            "G3_BOTH": 1131
        },
        "jaccard_overlap": 0.7287371134020618,
        "p_fr_given_erc": 0.9370339685169843
    }

    evidence_summary = {
        "G2_vs_G0_matched_test": {
            "comparison": "FUNDAMENTAL_ONLY (G2) vs NEITHER (G0)",
            "mean_vol_diff": 0.04798569104969164,
            "ci_95": [0.01818974082270378, 0.07586189063180936],
            "p_value": 0.0006,
            "interpretation": "Fundamental Confirmation identifies a statistically significant material future-risk subset that ERC does not downweight."
        },
        "G3_vs_G1_descriptive_tail": {
            "comparison": "BOTH (G3) vs ERC_ONLY (G1)",
            "g3_realized_vol": 0.5185985124870639,
            "g1_realized_vol": 0.370678357465397,
            "g3_prob_loss_gt_10pct": 0.20424403183023873,
            "g1_prob_loss_gt_10pct": 0.11842105263157894,
            "g3_cvar95": -0.2104728494666952,
            "g1_cvar95": -0.13879176198573742,
            "interpretation": "G3/BOTH displays substantially worse future downside characteristics than G1/ERC_ONLY in the observed sample, supporting second-layer risk discrimination."
        }
    }

    model_governance = {
        "VA_RETURN_CHALLENGER": "IMMUTABLE FROZEN CHAMPION (CAGR 12.87%, Vol 18.39%, MaxDD -24.93%)",
        "VB_CAPITAL_PRESERVATION": "IMMUTABLE FROZEN CHAMPION (CAGR 9.84%, Vol 15.18%, MaxDD -17.14% under true portfolio covariance sqrt(w' Sigma w))",
        "SHADOW_ERC_X2": "IMMUTABLE SHADOW FORWARD (CAGR 13.60%, Vol 18.19%, MaxDD -24.41%)",
        "SHADOW_PRUNED_STACK_D": "IMMUTABLE SHADOW FORWARD (ERC + Fundamental Risk Overlay 0.75x, CAGR 13.47%, Vol 17.96%, MaxDD -23.70%)",
        "SHADOW_INTEGRATED_STACK_H": "IMMUTABLE SHADOW FORWARD (ERC + FR + Hysteresis + NTZ, CAGR 13.56%, Vol 17.02%, MaxDD -24.32%)"
    }

    superseded_list = [
        "ERC and Fundamental are fully orthogonal.",
        "Overlap < 8%.",
        "Jaccard 66.62% as canonical (superseded by 72.87% under strict 0.10 pp tolerance).",
        "ERC count 1 070 as canonical (superseded by 1 207).",
        "BOTH count 1 018 as canonical (superseded by 1 131).",
        "V-B 7.38% vol as canonical (superseded by 15.18% true portfolio covariance; 7.38% marked INVALID TEST ARTIFACT)."
    ]

    forward_hypotheses_2026_09_04 = [
        "H1: D_ERC_FR provides lower downside/tail risk than ERC standalone, even if CAGR is slightly lower.",
        "H2: G2 (FUNDAMENTAL_ONLY) positions retain higher future realized volatility than G0 (NEITHER) in forward data.",
        "H3: G3 (BOTH) positions retain higher future downside risk than G1 (ERC_ONLY) in forward data."
    ]

    manifest_data = {
        "canonical_terminology": canonical_terminology,
        "canonical_overlap": canonical_overlap,
        "evidence_summary": evidence_summary,
        "model_governance": model_governance,
        "superseded_statements": superseded_list,
        "forward_hypotheses_2026_09_04": forward_hypotheses_2026_09_04,
        "final_classification": "AH-FREEZE COMPLETE — PREDICTIVELY COMPLEMENTARY, IMPLEMENTATIONALLY HIGH-OVERLAP"
    }

    raw_json = json.dumps(manifest_data, indent=2, sort_keys=True)
    sha256_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    
    manifest_data["sha256_manifest_hash"] = sha256_hash

    out_file = V2 / "research_k/research_ah_freeze_governance_manifest.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest_data, indent=2, sort_keys=True), encoding="utf-8")

    return manifest_data, sha256_hash

def main():
    print("=" * 80)
    print("RESEARCH AH-FREEZE: CANONICAL INTERPRETATION, GOVERNANCE & FORWARD MANIFEST")
    print("=" * 80)
    
    manifest, sha256_hash = compile_master_governance_manifest()
    
    print("\nMaster Governance Manifest Compiled Successfully!")
    print(f"File Path: {V2 / 'research_k/research_ah_freeze_governance_manifest.json'}")
    print(f"SHA256 Manifest Hash: {sha256_hash}")
    print(f"Final Classification: {manifest['final_classification']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
