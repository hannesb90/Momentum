"""Write an immutable snapshot plus mutable index of research challengers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/challenger_registry"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: str) -> dict:
    p = ROOT / path
    return {"path": path, "exists": p.exists(),
            "sha256": sha(p) if p.exists() else None, "bytes": p.stat().st_size if p.exists() else None}


def main():
    n3_latest = json.loads((ROOT / "results/niva3_stages/latest_healthy.json").read_text())
    stage5 = pd.read_csv(ROOT / "results/niva3_seed_fitdate_stability_arms.csv")
    stage6 = pd.read_csv(ROOT / "results/niva3_seed_consensus_arms.csv")
    entries = [{
        "id": "n2_stage07_forward_challenger", "family": "niva2_forward",
        "status": "ACTIVE_FORWARD_NOT_PRODUCTION", "production": False,
        "metrics": None,
        "artifacts": [artifact("results/niva2_forward/challenger.joblib"),
                      artifact("results/niva2_forward/initial_candidate_signal.csv"),
                      artifact("results/niva2_stages/07_forward_preregistration.json")],
    }, {
        "id": "n3_approved_architecture_seed42", "family": "large_lambdarank",
        "status": "HISTORICAL_ARCHITECTURE_BASELINE_NOT_PRODUCTION", "production": False,
        "metrics": {"CAGR": "27.1%", "Sharpe": "1.97", "Max Drawdown": "-19.8%"},
        "artifacts": [artifact("results/niva2_stage6_winner_signals.csv"),
                      artifact("results/niva2_stages/06_retraining_staleness.json")],
    }]
    for row in stage5.to_dict("records"):
        entries.append({
            "id": "n3_" + row["arm"], "family": "large_lambdarank_fit_stability",
            "status": "DIAGNOSTIC_CHALLENGER_REPRODUCIBLE_FROM_FROZEN_SCRIPT", "production": False,
            "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown", "alpha_cagr")},
            "artifacts": [artifact("results/niva3_seed_fitdate_stability_arms.csv"),
                          artifact("results/niva3_stages/05_seed_fitdate_stability.json")],
        })
    for row in stage6.to_dict("records"):
        full = row["arm"] == "consensus_all_3"
        entries.append({
            "id": "n3_" + row["arm"], "family": "large_lambdarank_seed_consensus",
            "status": "SAVED_CHALLENGER_GATE_FAIL_MEMBERSHIP" if full else "DIAGNOSTIC_LEAVE_ONE_OUT",
            "production": False,
            "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown", "alpha_cagr")},
            "artifacts": ([artifact("results/niva3_seed_consensus_signals.csv")] if full else []) +
                         [artifact("results/niva3_seed_consensus_raw_scores.csv"),
                          artifact("results/niva3_seed_consensus_arms.csv"),
                          artifact("results/niva3_stages/06_seed_consensus_remediation.json")],
        })
    partial_path = ROOT / "results/niva3_partial_delisted_inclusion.json"
    if partial_path.exists():
        partial = json.loads(partial_path.read_text())
        entries.append({
            "id": "n3_partial_survivorship_ica_coll", "family": "large_lambdarank_pit_universe",
            "status": "PARTIAL_DIAGNOSTIC_CHALLENGER_SURVIVORSHIP_GATE_FAIL", "production": False,
            "metrics": partial["partial_augmented_metrics"],
            "artifacts": [artifact("results/niva3_partial_delisted_signals.csv"),
                          artifact("results/niva3_partial_delisted_selections.csv"),
                          artifact("results/niva3_partial_delisted_inclusion.json"),
                          artifact("results/niva3_stages/08_partial_delisted_inclusion.json")],
        })
    vendor_path = ROOT / "results/niva3_vendor_corporate_action_arms.csv"
    if vendor_path.exists():
        for row in pd.read_csv(vendor_path).to_dict("records"):
            if row["arm"] == "frozen_baseline":
                continue
            entries.append({
                "id": "n3_sr49_" + row["arm"], "family": "large_price_source_sensitivity",
                "status": "DIAGNOSTIC_EXCLUSION_ARM_NOT_PRODUCTION", "production": False,
                "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown", "alpha_cagr",
                                                  "cagr_change_vs_baseline")},
                "artifacts": [artifact("results/niva3_vendor_corporate_action_arms.csv"),
                              artifact("results/niva3_vendor_corporate_action_exclusions.csv"),
                              artifact("results/niva3_stages/09_vendor_corporate_action_sensitivity.json")],
            })
    reconstructed_path = ROOT / "results/niva3_reconstructed_price_retrain_corrected.json"
    if reconstructed_path.exists():
        reconstructed = json.loads(reconstructed_path.read_text())
        entries.append({
            "id": "n3_reconstructed_price_seed42", "family": "large_price_source_reconstruction",
            "status": "SAVED_CHALLENGER_SENSITIVITY_GATE_FAIL", "production": False,
            "metrics": {**reconstructed["reconstructed_metrics"],
                        "alpha_cagr": reconstructed["alpha_cagr"],
                        "cagr_change_vs_baseline": reconstructed["cagr_change_vs_baseline"]},
            "artifacts": [artifact("results/niva3_reconstructed_price_signals_corrected.csv"),
                          artifact("results/niva3_reconstructed_price_patches_corrected.csv"),
                          artifact("results/niva3_reconstructed_price_retrain_corrected.json"),
                          artifact("results/niva3_stages/12_reconstructed_price_retrain_corrected.json")],
        })
    implement_path = ROOT / "results/niva3_100k_implementability_arms.csv"
    if implement_path.exists():
        for row in pd.read_csv(implement_path).to_dict("records"):
            entries.append({
                "id": "n3_sr50_" + row["arm"], "family": "large_100k_implementation",
                "status": "DIAGNOSTIC_IMPLEMENTATION_ARM_NOT_PRODUCTION", "production": False,
                "metrics": {k: row[k] for k in ("cagr", "sharpe", "max_drawdown",
                                                  "tracking_error_annual", "terminal_wealth_gap")},
                "artifacts": [artifact("results/niva3_100k_implementability_arms.csv"),
                              artifact("results/niva3_100k_implementability.json"),
                              artifact("results/niva3_stages/13_100k_implementability.json")],
            })
    cutoff_path = ROOT / "results/niva3_operational_cutoff_lag_arms.csv"
    if cutoff_path.exists():
        for row in pd.read_csv(cutoff_path).to_dict("records"):
            entries.append({
                "id": f"n3_sr51_operational_lag_{int(row['lag_weeks'])}w",
                "family": "large_operational_cutoff_lag",
                "status": "DIAGNOSTIC_LAG_ARM_NO_SELECTION", "production": False,
                "metrics": {k: row[k] for k in ("cagr", "sharpe", "max_drawdown",
                                                  "alpha_cagr", "median_rotation_jaccard_vs_lag0")},
                "artifacts": [artifact("results/niva3_operational_cutoff_lag_arms.csv"),
                              artifact("results/niva3_operational_cutoff_lag_members.csv"),
                              artifact("results/niva3_stages/14_operational_cutoff_lag.json")],
            })
    sr53_path = ROOT / "results/niva3_publication_missingness_arms.csv"
    if sr53_path.exists():
        for row in pd.read_csv(sr53_path).to_dict("records"):
            if row["arm"] == "baseline":
                continue
            entries.append({
                "id": "n3_sr53_" + row["arm"], "family": "large_publication_missingness",
                "status": "SAVED_CHALLENGER_SELECTION_STABILITY_FAIL", "production": False,
                "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown",
                                                  "alpha_cagr", "median_top15_jaccard")},
                "artifacts": [artifact(f"results/niva3_sr53_{row['arm']}_signals.csv"),
                              artifact("results/niva3_publication_missingness_arms.csv"),
                              artifact("results/niva3_stages/17_publication_missingness_selection.json")],
            })
    sr1_path = ROOT / "results/niva3_sr1_corrected_overlay_arms.csv"
    if sr1_path.exists():
        sr1_report = json.loads((ROOT / "results/niva3_sr1_corrected_overlay.json").read_text())
        eligible = set(sr1_report.get("eligible_challengers", []))
        robust_path = ROOT / "results/niva3_sr1_robustness.json"
        robust = set(json.loads(robust_path.read_text()).get("passed_challengers", [])) if robust_path.exists() else None
        for row in pd.read_csv(sr1_path).to_dict("records"):
            if row["arm"] == "baseline_13_target":
                continue
            entries.append({
                "id": "n3_sr1_corrected_" + row["arm"], "family": "large_conditional_13_52_target",
                "status": ("ROBUST_CHALLENGER_AWAITING_FURTHER_GATES" if robust is not None and row["arm"] in robust
                           else "REJECTED_AT_ROBUSTNESS_GATE" if robust is not None and row["arm"] in eligible
                           else "ELIGIBLE_CHALLENGER_AWAITING_ROBUSTNESS" if row["arm"] in eligible
                           else "REJECTED_DIAGNOSTIC_ARM"),
                "production": False,
                "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown",
                                                  "alpha_cagr", "median_top15_jaccard")},
                "artifacts": [artifact("results/niva3_sr1_corrected_overlay_arms.csv"),
                              artifact("results/niva3_sr1_corrected_overlay_members.csv"),
                              artifact("results/niva3_sr1_corrected_overlay.json"),
                              artifact("results/niva3_stages/23_sr1_corrected_overlay.json"),
                              artifact("results/niva3_sr1_robustness.json"),
                              artifact("results/niva3_stages/24_sr1_robustness.json")],
            })
    sr3_path = ROOT / "results/niva3_sr3_regime_rvol_arms.csv"
    if sr3_path.exists():
        for row in pd.read_csv(sr3_path).to_dict("records"):
            if row["arm"] == "baseline":
                continue
            entries.append({
                "id": "n3_sr3_" + row["arm"], "family": "large_regime_cross_section_interaction",
                "status": "REJECTED_FULLMODEL_GATE" if row["arm"] == "bear_rvol_interaction" else "PLACEBO_CONTROL",
                "production": False,
                "metrics": {k: row[k] for k in ("CAGR", "Sharpe", "Max Drawdown",
                                                  "median_top15_jaccard", "median_split_ic", "positive_split_ic_share")},
                "artifacts": [artifact("results/niva3_sr3_regime_rvol_arms.csv"),
                              artifact(f"results/niva3_sr3_{row['arm']}_signals.csv"),
                              artifact("results/niva3_sr3_regime_rvol.json"),
                              artifact("results/niva3_stages/26_sr3_regime_rvol_fullmodel.json")],
            })
    registry = {
        "schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "n3_latest_manifest_sha256": n3_latest["manifest_sha256"],
        "policy": "Entries are never production unless production=true; immutable snapshots preserve history.",
        "challengers": entries,
    }
    encoded = json.dumps(registry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    registry["registry_sha256"] = hashlib.sha256(encoded).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = OUT / f"registry_{n3_latest['manifest_sha256'][:12]}.json"
    if snapshot.exists() and json.loads(snapshot.read_text()).get("registry_sha256") != registry["registry_sha256"]:
        raise RuntimeError(f"Immutable challenger snapshot already differs: {snapshot}")
    snapshot.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    print(snapshot); print(registry["registry_sha256"]); print(len(entries))


if __name__ == "__main__":
    main()
