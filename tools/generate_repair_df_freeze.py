#!/usr/bin/env python3
"""Generate the repaired D/F freeze from actual paths and bytes only."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "repair_df/FREEZE_MANIFEST.json"
INPUTS = [
    "panels/core_panel.json",
    "panels/core_fundamenta_panel.json",
    "panels/target_table.json",
    "docs/probes/feature_registry.json",
    "validated/prices/prices_validated.json",
    "validated/terminal_events.json",
]
CONTROLS = [
    "spard/core_race_preregistration.json",
    "sparf/preregistration.json",
    "repair_df/repair_preregistration.json",
    "repair_df/regression_results.json",
    "repair_df/static_scope_audit.json",
    "tools/decision_portfolio_v2.py",
    "tools/decision_portfolio_v3_execution.py",
    "tools/test_decision_portfolio_v2.py",
    "tools/test_execution_timing_v3.py",
    "tools/rebuild_spard_pit.py",
    "tools/rebuild_sparf_pit.py",
    "tools/verify_repair_df_freeze.py",
    "repair_df/execution_timing_preregistration.json",
]
RESULTS = {
    "SPARD_CORE_NEUTRAL_RACE_V3_EXECUTION_PIT": "repair_df/results/SPARD_CORE_NEUTRAL_RACE_V3_EXECUTION_PIT",
    "SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT": "repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_counts(path: Path) -> dict:
    if path.suffix != ".json":
        return {}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return {"json_type": "list", "row_count": len(obj)}
    if isinstance(obj, dict):
        nested = sum(len(v) for v in obj.values() if isinstance(v, list))
        out = {"json_type": "object", "top_level_count": len(obj)}
        if nested:
            out["nested_row_count"] = nested
        return out
    return {"json_type": type(obj).__name__}


def describe(rel: str) -> dict:
    path = ROOT / rel
    if not path.is_file():
        raise FileNotFoundError(rel)
    return {
        "path": rel,
        "bytes": path.stat().st_size,
        "sha256": sha(path),
        **json_counts(path),
    }


def result_description(rel: str) -> dict:
    root = ROOT / rel
    if not root.is_dir():
        raise FileNotFoundError(rel)
    files = [describe(p.relative_to(ROOT).as_posix()) for p in sorted(root.iterdir()) if p.is_file()]
    aggregate = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"path": rel, "files": files, "freeze_aggregate_sha256": aggregate}


def build(version: str) -> dict:
    return {
        "freeze_id": version,
        "created": date.today().isoformat(),
        "status": "IMMUTABLE_VERIFIED_DF_EXECUTION_FREEZE",
        "track_g_status": "STOPPED_PENDING_G0_RESTART",
        "generator": describe("tools/generate_repair_df_freeze.py"),
        "verifier_path": "tools/verify_repair_df_freeze.py",
        "inputs": [describe(p) for p in INPUTS],
        "controls": [describe(p) for p in CONTROLS],
        "outputs": {name: result_description(rel) for name, rel in RESULTS.items()},
        "champion": {
            "signal": "0.5*rank(mom_12m)+0.5*rank(mom_18m)",
            "missing_tie_rule": "per-date median fill, deterministic score-desc/kod-desc tie break",
            "portfolio_size": 30,
            "weighting": "equal_weight",
            "rebalance": "8w_on_frozen_4w_panel_phase_0",
            "execution": "first observed trading close strictly after decision panel date",
            "one_way_cost_bps": 20,
            "gate": None,
            "entry_exit": None,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--output", default=str(FREEZE))
    args = ap.parse_args()
    out = Path(args.output)
    data = build(args.version)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "GENERATED", "path": str(out), "sha256": sha(out)}, indent=2))


if __name__ == "__main__":
    main()
