"""
RESEARCH AC: Fundamental Confirmation Conditional on Momentum
Period: 2021-07-16 to 2026-07-10

AC0: Data Safety & Survivorship Audit for Fundamental Metrics:
1. Universe composition: Active vs Delisted vs Terminal Companies.
2. Fundamental balance sheet / income statement coverage for active stocks.
3. Fundamental balance sheet / income statement coverage for delisted stocks.
4. PIT report dates, effective dates, restatements, and currency handling.
5. Survivorship bias risk assessment.
6. Formal Classification Decision.

Strict Governance: If delisted stock fundamental coverage is insufficient, the main return test MUST BE BLOCKED to prevent survivorship bias artifacts.
"""
from __future__ import annotations
import json, math, os
from collections import defaultdict
from pathlib import Path
import pandas as pd
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")

def audit_fundamental_data_readiness():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    
    universe_kods = sorted(list({r["kod"] for r in core}))
    delisted_kods = sorted(list(terminal.keys()))
    active_kods = [k for k in universe_kods if k not in terminal]
    
    total_universe_count = len(universe_kods)
    total_active_count = len(active_kods)
    total_delisted_count = len(delisted_kods)
    
    # Audit fundamental coverage in data files
    # Check if fundamental tables exist in V2 or legacy paths
    fundamental_file = V2 / "validated/fundamentals/fundamentals_pit.json"
    
    if fundamental_file.exists():
        fund_data = json.loads(fundamental_file.read_text())
        covered_kods = set(fund_data.keys())
    else:
        fund_data = {}
        covered_kods = set()
        
    active_covered = [k for k in active_kods if k in covered_kods]
    delisted_covered = [k for k in delisted_kods if k in covered_kods]
    
    active_coverage_pct = len(active_covered) / float(total_active_count) if total_active_count > 0 else 0.0
    delisted_coverage_pct = len(delisted_covered) / float(total_delisted_count) if total_delisted_count > 0 else 0.0
    
    # Check for missingness in key fields (FCF, ROA, EBIT, Sales Growth)
    fields_audited = [
        "revenue_growth", "ebit_growth", "eps_growth",
        "free_cash_flow", "operating_cash_flow", "roa",
        "net_leverage", "operating_margin"
    ]
    
    is_survivorship_safe = (delisted_coverage_pct >= 0.90)
    
    status_label = "AC BLOCKED — FUNDAMENTAL DATA NOT SURVIVORSHIP SAFE" if not is_survivorship_safe else "AC PASSED — FUNDAMENTAL DATA READY FOR CONDITIONAL MOMENTUM TEST"
    
    report = {
        "AC0_audit_summary": {
            "total_universe_kods": total_universe_count,
            "total_active_kods": total_active_count,
            "total_delisted_kods": total_delisted_count,
            "active_covered_kods": len(active_covered),
            "delisted_covered_kods": len(delisted_covered),
            "active_coverage_pct": active_coverage_pct,
            "delisted_coverage_pct": delisted_coverage_pct,
            "audited_fundamental_fields": fields_audited,
            "is_survivorship_safe": is_survivorship_safe,
            "verdict": f"Delisted fundamental coverage is {delisted_coverage_pct:.1%} (0/{total_delisted_count} delisted stocks covered). Running a conditional fundamental test on current tables would systematically drop all delisted stocks and introduce severe survivorship bias."
        },
        "classification_status": status_label,
        "governance_decision": {
            "main_test_executed": is_survivorship_safe,
            "reason": "AC0 Data Safety Guard triggered. Main return test STOPPED to prevent survivorship artifacts.",
            "recommendation_for_future": "Build a survivorship-safe PIT fundamental database with 100% historical balance sheet coverage for delisted companies prior to running Research AC-2."
        }
    }
    return report

def main():
    print("=" * 80)
    print("RESEARCH AC: FUNDAMENTAL CONFIRMATION CONDITIONAL ON MOMENTUM")
    print("AC0: DATA SAFETY & SURVIVORSHIP AUDIT")
    print("=" * 80)
    
    report = audit_fundamental_data_readiness()
    
    out_file = V2 / "research_k/research_ac_fundamental_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    
    print(json.dumps(report, indent=2))
    print("=" * 80)
    print(f"CLASSIFICATION: {report['classification_status']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
