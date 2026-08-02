"""Mechanical first-pass inventory after methodology reset.

This does not certify economic validity. It identifies scripts that can prove
the current full Large contract in source, separates known data blockers, and
forces everything else into revalidation rather than inheriting old conclusions.
"""
from __future__ import annotations
import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/research_method_audit_2026_08_01.csv"
SUMMARY=ROOT/"results/research_method_audit_summary_2026_08_01.json"
PARENT=ROOT/"results/niva3_stages/18_benchmark_total_return_parity.json"
DATA_BLOCKED=("sentiment","case_tracker","pead","report_crowding","report_dip",
              "earnings_reaction","dividend_gap","insider_gap","attention_gap")
CURRENT={"tune_objective_comparison.py","tune_idx_mix.py","tune_monthly_contributions.py",
         "gate_baseline_parity.py","gate_corporate_actions.py","gate_placebo_leakage.py",
         "gate_multiple_testing.py","run_research_gates.py"}
SEPARATE_MANDATE=("core_","theme_satellite","etf_rotation","large_small_allocation",
                  "leverage_holding","bear_hedge","bull_hedge","isk_","monthly_contributions")
FAMILIES={
    "model_training": ("objective","lambdarank","catboost","hyperparam","age_weight","equal_date","monotonic","nan_handling","checkpoint","rank_metric","rank_calibration","precision_recall"),
    "target_horizon": ("horizon","target_","triple_barrier","metalabel","downside"),
    "fundamental_event": ("fundamental","borsdata","accrual","cashflow","quality","pead","attention","report_","earnings","dividend","insider","sentiment","case_tracker","otto","valuation"),
    "portfolio_exit_risk": ("sizing","position","concentration","correlation","reentry","refill","entry_policy","atr","drawdown","takeprofit","anchor_exit","breadth","dispersion","voltarget","regime_exposure","slippage","liquidity","kelly"),
    "universe_benchmark": ("universe","idx_mix","sector_","eligibility","delisted","vendor_corporate","benchmark","100k"),
    "validation": ("ablation","sanity","statistical_power","integrated","combined_validation","publication_missingness","seed_","calendar52","phase_robust","operational_cutoff","reconstructed"),
}


def frozen_scripts()->set[str]:
    out=set()
    for folder in (ROOT/"results/niva2_stages", ROOT/"results/niva3_stages"):
        for manifest in folder.glob("*.json"):
            if manifest.name=="latest_healthy.json": continue
            try:
                data=json.loads(manifest.read_text())
                for item in data.get("artifacts",[]):
                    p=item.get("path","")
                    if p.startswith("momentum_ml/") and p.endswith(".py"): out.add(Path(p).name)
            except Exception:
                pass
    return out


def family(name:str)->str:
    low=name.lower()
    hits=[label for label,keys in FAMILIES.items() if any(k in low for k in keys)]
    return "+".join(hits) if hits else "other"


def saved_results(path:Path)->list[Path]:
    key=path.stem
    aliases={key, key.removeprefix("tune_"), key.removeprefix("backtest_"), key.removeprefix("gate_")}
    found=[]
    for p in (ROOT/"results").rglob("*"):
        if p.is_file() and any(a and a in p.name for a in aliases): found.append(p)
    return sorted(found,key=lambda p:p.stat().st_mtime,reverse=True)


def classify(path:Path,frozen:set[str])->tuple[str,str]:
    text=path.read_text(errors="replace")
    name=path.name
    if name in frozen:
        return "frozen_current_chain","artifact in verified N2/N3 hash chain"
    if any(x in name for x in SEPARATE_MANDATE):
        return "separate_mandate","allocation, tax, savings or ETF/risk subsystem"
    if any(x in name for x in DATA_BLOCKED):
        return "data_review_required","requires verified PIT/event-time coverage"
    if name in CURRENT:
        return "current_or_gate","explicitly reviewed in methodology reset"
    if "apply_large(" in text and "validate_large_contract(" in text:
        return "contract_validated","full fail-closed Large contract in source"
    missing=[]
    for token,label in (("REBALANCE_WEEKS","rebalance"),("MAX_POSITIONS","N"),
                        ("MARKET_FILTER_EXPOSURE","market exposure"),("SECTOR_MAP","sector map")):
        if token not in text: missing.append(label)
    reason="no full fail-closed contract"
    if missing: reason += "; source does not mention " + ", ".join(missing)
    return "revalidation_required",reason


def main():
    from niva3_stage_control import freeze_stage, verify_manifest
    parent=verify_manifest(PARENT)
    files=sorted(list((ROOT/"momentum_ml").glob("tune_*.py"))+
                 list((ROOT/"momentum_ml").glob("gate_*.py"))+
                 list((ROOT/"momentum_ml").glob("backtest_*.py")))
    frozen=frozen_scripts(); rows=[]
    for path in files:
        status,reason=classify(path,frozen); saved=saved_results(path)
        if status=="revalidation_required" and "apply_large(" in path.read_text(errors="replace"):
            status="contract_review_then_run"; reason="Large config helper present; semantic parity and frozen baseline still required"
        rows.append({"script":path.name,"status":status,"reason":reason,
                     "mechanism_family":family(path.name),
                     "has_saved_result":bool(saved),
                     "latest_saved_result":str(saved[0].relative_to(ROOT)) if saved else "",
                     "latest_result_utc":datetime.fromtimestamp(saved[0].stat().st_mtime,timezone.utc).isoformat() if saved else ""})
    with OUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    counts={}
    for row in rows: counts[row["status"]]=counts.get(row["status"],0)+1
    families={}
    for row in rows:
        for fam in row["mechanism_family"].split("+"): families[fam]=families.get(fam,0)+1
    actionable=[r for r in rows if r["status"] in ("revalidation_required","contract_review_then_run")]
    report={"status":"PASS","test":"historical-research-master-inventory",
            "parent_stage":parent["manifest_sha256"],"scripts":len(rows),"counts":counts,"families":families,
            "large_revalidation_candidates_before_semantic_dedup":len(actionable),
            "with_any_saved_result":sum(bool(r["has_saved_result"]) for r in rows),
            "without_saved_result":sum(not bool(r["has_saved_result"]) for r in rows),
            "policy":"Frozen-chain tests carry their scoped conclusions. Historical scripts require semantic dedup and current-baseline parity before rerun or reuse.",
            "note":"Source/artifact audit; rows are scripts, not yet unique economic hypotheses."}
    SUMMARY.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    stage=freeze_stage("19_historical_research_inventory",[OUT,SUMMARY,Path(__file__).resolve()],
                       {"test":"historical-research-master-inventory",
                        "large_revalidation_candidates_before_semantic_dedup":len(actionable),
                        "production":False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False)); print(OUT); print(stage)

if __name__=="__main__": main()
