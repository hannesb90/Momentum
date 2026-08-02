"""Fail-closed production-readiness audit against the Level-2 second review."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/niva2_method_compliance.json"

def status(path,validator=lambda x:x.get("status")=="PASS"):
    if not path.exists():return "MISSING"
    try:return "PASS" if validator(json.loads(path.read_text())) else "FAIL"
    except Exception:return "FAIL"

def main():
    gates=[
      {"order":0,"gate":"baseline_contract","status":status(ROOT/"results/research_gates/sr9_baseline_parity.json")},
      {"order":1,"gate":"target_isolation","status":status(ROOT/"results/target_horizon_isolated.json"),"winner":"binary_13_target"},
      {"order":2,"gate":"rotation_and_staggered_isolation","status":status(ROOT/"results/rotation_isolated.json")},
      {"order":3,"gate":"objective_tournament_on_winning_target_rotation",
       "status":status(ROOT/"results/objective_niva2_stage3.json",
         lambda x:x.get("status")=="PASS" and x.get("target_weeks")==13
         and x.get("rotation_weeks")==52 and x.get("holdout_used") is False),
       "winner":"lambdarank"},
      {"order":4,"gate":"score_and_sizing_isolation",
       "status":status(ROOT/"results/sizing_isolated_niva2.json",
         lambda x:x.get("status")=="PASS" and x.get("holdout_used") is False
         and x.get("winner")=="inverse_vol_b075"),
       "winner":"inverse_vol_b075"},
      {"order":5,"gate":"pipeline_ablation_on_locked_winner",
       "status":status(ROOT/"results/pipeline_ablation_niva2.json",
         lambda x:x.get("status")=="PASS" and x.get("holdout_used") is False
         and x.get("retraining") is False and x.get("winner")=="plus_inverse_vol75"),
       "winner":"eligibility_gate_plus_inverse_vol75_without_correlation_filter"},
      {"order":6,"gate":"retraining_and_staleness",
       "status":status(ROOT/"results/retraining_staleness_niva2.json",
         lambda x:x.get("status")=="PASS" and x.get("holdout_used") is False
         and x.get("same_splits")==21),
       "decision":"refit_at_every_52_week_rotation; denser cadence added no portfolio alpha"},
      {"order":7,"gate":"independent_forward","status":"ACTIVE_FORWARD",
       "reason":"preregistered 2026-07-27; one start observation; require 52 observed weeks through at least 2027-07-26 and one scheduled annual rotation"},
      {"order":8,"gate":"small_replication","status":"BLOCKED_DATA",
       "reason":"Small PIT fundamentals coverage not yet decision-grade; does not block Large-only paper shadow"},
    ]
    blocking={"MISSING","FAIL","STALE_ORDER","PARTIAL","INSUFFICIENT","ACTIVE_FORWARD"}
    ready=not any(g["status"] in blocking for g in gates[:8])
    report={"status":"PRODUCTION_READY" if ready else "NOT_PRODUCTION_READY",
      "large_production_change_authorized":ready,"gates":gates,
      "required_next_order":[
       "collect_weekly_stage07_forward_until_2027-07-26_and_execute_one_rotation"],
      "policy":"No skipping or parallel winner selection; old holdout has zero voting weight."}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False));print(OUT)

if __name__=="__main__":main()
