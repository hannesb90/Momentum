"""N3 stage 20: semantically deduplicate historical scripts and SR1-SR44.

This is a preregistration/queue construction stage.  It does not execute an
economic experiment or mutate production.  One row means one mechanism, never
one filename.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from niva3_stage_control import freeze_stage, verify_manifest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/19_historical_research_inventory.json"
AUDIT = ROOT / "results/research_method_audit_2026_08_01.csv"
MAP_OUT = ROOT / "results/research_semantic_mapping_2026_08_01.csv"
QUEUE_OUT = ROOT / "results/research_master_queue_2026_08_01.csv"
SUMMARY = ROOT / "results/research_master_queue_summary_2026_08_01.json"

# Ordered, explicit semantic rules.  Earlier rules win.  SR references point to
# the full second-review catalogue; several legacy scripts can support one SR.
RULES = [
    ("helper_not_experiment", "HELPER", ("lambdarank_common",)),
    ("conditional_52_13", "SR1", ("conditional_13_overlay", "horizon_ensemble")),
    ("ranker_uncertainty_switch", "SR2,SR20", ("disagreement", "abstention")),
    ("regime_cross_section_interaction", "SR3,SR38", ("regime_feature", "resid_mom", "riskadj_momentum")),
    ("cause_specific_reentry", "SR4,SR36", ("reentry", "refill_discount", "entry_policy")),
    ("drawdown_rank_confirmed_exit", "SR5,SR37", ("individual_drawdown",)),
    ("armed_takeprofit_state_machine", "SR6", ("takeprofit", "anchor_exit")),
    ("newly_qualified_sleeve", "SR7,SR40", ("newly_qualified",)),
    ("conditional_risk_adjusted_momentum", "SR8", ("riskadj_momentum_ablation",)),
    ("baseline_pipeline_parity", "SR9", ("combined_validation", "integrated_backtest")),
    ("rank_calibration", "SR11", ("rank_calibration", "precision_recall", "rank_metric")),
    ("concentration_active_share", "SR12,SR39", ("concentration_cap", "correlation_filter", "sizing")),
    ("dynamic_n_exposure_separation", "SR13", ("dynamic_positions",)),
    ("capacity_execution_cost", "SR14,SR41,SR42", ("slippage", "liquidity")),
    ("adaptive_sample_age", "SR15", ("age_weight",)),
    ("nested_hyperparameter_plateau", "SR16", ("hyperparams", "lambdarank_robustness")),
    ("ranker_objective_comparison", "SR16,SR22,SR24", ("catboost", "lambdarank_vs_baseline")),
    ("pit_missingness_state", "SR17", ("nan_handling", "feature_sanity")),
    ("selective_monotonicity", "SR18", ("monotonic",)),
    ("equal_date_capped_mass", "SR19", ("equal_date",)),
    ("feature_redundancy_group_dropout", "SR21", ("multicollinearity", "ablation", "v2_features", "interaction")),
    ("competing_risk_meta_target", "SR23", ("triple_barrier", "downside_veto", "metalabel")),
    ("fundamental_accrual_quality", "SR25", ("accrual",)),
    ("cashflow_inflection_persistence", "SR26", ("cashflow",)),
    ("fundamental_residual_to_roa", "SR27,SR28", ("borsdata_fundamental", "fundamentals")),
    ("attention_expected_volume", "SR29,SR34", ("attention", "report_crowding")),
    ("dividend_sustainability", "SR30,SR34", ("dividend",)),
    ("informative_insider_intensity", "SR31,SR34", ("insider",)),
    ("conditional_valuation", "SR32", ("otto", "global_relative_value", "qualified_holder")),
    ("quality_momentum_neutralized", "SR33", ("quality_momentum", "quality_score", "hold_forever_fundamentals")),
    ("joint_report_event_model", "SR34", ("pead", "earnings_reaction", "report_dip", "sentiment", "case_tracker")),
    ("staggered_52_cohorts", "SR35", ("staggered_52", "horizon", "hold_forever")),
    ("cash_alternative_after_exit", "SR37", ("atr_stop", "cash_drag", "asymmetric_exit", "combined_exits")),
    ("continuous_regime_hedge", "SR38", ("regime_exposure", "breadth", "dispersion", "voltarget")),
    ("benchmark_factor_attribution", "SR39", ("sector_categorical", "sector_theme", "universe")),
    ("generic_model_gate", "SR9,SR43", ("tune_gate",)),
    ("statistical_reality_check", "SR44", ("statistical_power",)),
    ("legacy_horizon_target", "SR1,SR16,SR35", ("horizon",)),
    ("legacy_portfolio_diagnostic", "REVIEW", ("hold_forever", "kelly_win_loss")),
]

PRIORITY = {
    "baseline_pipeline_parity": 0,
    "conditional_52_13": 1,
    "regime_cross_section_interaction": 2,
    "newly_qualified_sleeve": 3,
    "conditional_risk_adjusted_momentum": 4,
    "ranker_uncertainty_switch": 5,
    "cause_specific_reentry": 6,
    "drawdown_rank_confirmed_exit": 7,
    "armed_takeprofit_state_machine": 8,
    "rank_calibration": 9,
    "capacity_execution_cost": 10,
    "statistical_reality_check": 99,
}


def mechanism(script: str) -> tuple[str, str]:
    stem = Path(script).stem.lower()
    for key, sr, needles in RULES:
        if any(n in stem for n in needles):
            return key, sr
    return "manual_semantic_review", "REVIEW"


def main():
    parent = verify_manifest(PARENT)
    audit = pd.read_csv(AUDIT).fillna("")
    rows = []
    for row in audit.itertuples(index=False):
        key, sr = mechanism(row.script)
        if row.status == "frozen_current_chain": disposition = "CURRENT_FROZEN_NO_RERUN"
        elif row.status == "current_or_gate": disposition = "CURRENT_GATE_NO_RERUN"
        elif row.status == "separate_mandate": disposition = "OUTSIDE_LARGE_ALPHA_QUEUE"
        elif key == "helper_not_experiment": disposition = "HELPER_NO_TEST"
        elif row.status == "data_review_required": disposition = "BLOCKED_DATA_GATE"
        else: disposition = "STALE_REVALIDATE_OR_REWRITE"
        rows.append({**row._asdict(), "mechanism_key": key, "sr_links": sr,
                     "disposition": disposition})
    mapping = pd.DataFrame(rows)
    mapping.to_csv(MAP_OUT, index=False)

    actionable = mapping[mapping.disposition.isin(["STALE_REVALIDATE_OR_REWRITE", "BLOCKED_DATA_GATE"])]
    queue = []
    for key, group in actionable.groupby("mechanism_key", sort=False):
        scripts = sorted(group.script.tolist())
        sr = sorted({x for cell in group.sr_links for x in str(cell).split(",")})
        blocked = bool((group.disposition == "BLOCKED_DATA_GATE").any())
        manual = key == "manual_semantic_review"
        queue.append({
            "mechanism_key": key,
            "sr_links": ",".join(sr),
            "priority": PRIORITY.get(key, 50 if not blocked else 80),
            "status": "MANUAL_REVIEW_REQUIRED" if manual else ("BLOCKED_DATA_GATE" if blocked else "READY_FOR_METHOD_REWRITE"),
            "historical_scripts": ";".join(scripts),
            "script_count": len(scripts),
            "has_any_old_result": bool(group.has_saved_result.astype(bool).any()),
            "adoption_allowed_from_old_result": False,
            "next_action": "inspect and assign unique mechanism" if manual else ("satisfy PIT/event data gate" if blocked else "preregister current-baseline implementation"),
        })
    q = pd.DataFrame(queue).sort_values(["priority", "mechanism_key"]).reset_index(drop=True)
    q.insert(0, "queue_order", range(1, len(q)+1))
    q.to_csv(QUEUE_OUT, index=False)
    report = {
        "status": "PASS", "test": "N3-20-semantic-deduplication",
        "parent_stage": parent["manifest_sha256"],
        "source_scripts": int(len(mapping)),
        "historical_large_candidates": int(len(actionable)),
        "unique_actionable_mechanisms": int(len(q)),
        "ready_for_method_rewrite": int((q.status == "READY_FOR_METHOD_REWRITE").sum()),
        "blocked_data_gate": int((q.status == "BLOCKED_DATA_GATE").sum()),
        "manual_review_mechanisms": int((q.status == "MANUAL_REVIEW_REQUIRED").sum()),
        "old_result_adoption_allowed": False,
        "first_economic_test": "conditional_52_13 / SR1",
        "production": False,
    }
    SUMMARY.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage("20_semantic_research_queue", [MAP_OUT, QUEUE_OUT, SUMMARY, Path(__file__).resolve()],
                         {"test": "N3-20-semantic-deduplication",
                          "unique_actionable_mechanisms": len(q), "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False)); print(q.to_string(index=False)); print(stage)


if __name__ == "__main__":
    main()
