"""Freeze the Large Level-3 scope without touching the Stage-07 challenger."""
from __future__ import annotations
import json
from pathlib import Path
from niva2_stage_control import verify_manifest as verify_n2
from niva3_stage_control import freeze_stage

ROOT = Path(__file__).resolve().parents[1]
N2 = ROOT / "results/niva2_stages/06_retraining_staleness.json"
OUT = ROOT / "results/niva3_large_scope.json"

def main():
    n2 = verify_n2(N2)
    scope = {"status": "PASS", "segment": "large", "production_change": False,
      "stage07_must_remain_unchanged": True, "parent_niva2": n2["manifest_sha256"],
      "locked_input": "LambdaRank + 13w target + calendar52 + eligibility + inverse-vol75; no correlation filter; refit at rotation",
      "old_holdout_voting_weight": 0,
      "ordered_gates": [
        "calendar52_phase_robustness",
        "eligibility_gate_decomposition_and_plateau",
        "seed_and_fit_date_stability",
        "pit_universe_delisting_and_vendor_sensitivity",
        "feature_family_ablation",
        "pit_fundamentals_and_economic_interactions",
        "risk_and_exposure_layers",
        "entry_exit_between_annual_rotations",
        "execution_delay_liquidity_capacity",
        "integrated_parity_attribution_multiple_testing",
        "live_100k_order_rounding_and_tracking_error"],
      "newly_added_after_gap_review": [
        "N3-SR45 all 52 calendar rebalance phases; phase is not a tunable parameter",
        "N3-SR46 decompose eligibility into expected-return, fund exclusion and momentum gate",
        "N3-SR47 at least three deterministic seeds and fit-date offsets",
        "N3-SR48 PIT listing/delisting coverage with lower-bound alpha",
        "N3-SR49 Borsdata/Yahoo fallback and corporate-action sensitivity",
        "N3-SR50 100k SEK whole-share/minimum-order tracking error",
        "N3-SR51 annual refit cutoff lag around the rotation date",
        "N3-SR52 temporal/factor attribution and worst-era robustness",
        "N3-SR53 feature-publication lag and missingness-selection audit",
        "N3-SR54 total-return benchmark/dividend parity"],
      "excluded_from_large_n3": ["Small model/allocation", "LSTM until separately trained",
                                  "monthly contributions as alpha", "retroactive Stage07 tuning"],
      "decision_policy": "DEV/OOF only; each accepted change creates a new challenger with its own forward clock"}
    OUT.write_text(json.dumps(scope, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage("00_large_scope_baseline",
        [OUT, ROOT/"results/niva2_stage6_winner_signals.csv",
         ROOT/"docs/NIVA3_LARGE_METHOD_2026-08-01.md", Path(__file__).resolve()],
        {"segment": "large", "gates": len(scope["ordered_gates"]),
         "stage07_unchanged": True, "production": False})
    print(json.dumps(scope, indent=2, ensure_ascii=False)); print(stage)

if __name__ == "__main__": main()
