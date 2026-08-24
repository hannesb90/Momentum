"""Fail-closed provenance audit for H0_V3_OTQ2_QUALITY_OVERLAY_BUILD_AND_TEST.

This tool intentionally performs no score construction and reads no future
returns.  It records whether the current fundamental foundation is licensed
and sufficient for a historical conditional-overlay test.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_k/h0_v3_otq2_quality_overlay_build_and_test"
LEGACY_ROOT = Path("/home/hannesb/momentum_prod_work")
CHECKPOINT = ROOT / "research_k/h0_v3_canonical_production_implementation/PRODUCTION_CHECKPOINT_FINALIZATION.json"
SPARB = ROOT / "validated/manifest_sparB.json"
RESTRICT = ROOT / "validated/fundamentals_gated/FUNDAMENTAL_RESTRICTION_REGISTRY.json"
GOVERNANCE = ROOT / "docs/DATA_GOVERNANCE_REGISTRY.md"
STATE = ROOT / "docs/CURRENT_RESEARCH_STATE.md"
FUNDS = ROOT / "validated/fundamentals"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def source(path: Path, logical_name: str, producer: str, use: str, pit: str) -> dict:
    return {"logical_name": logical_name, "exact_resolved_path": str(path),
            "producer_script": producer, "sha256": sha(path), "role": use,
            "pit_semantics": pit}


def table_coverage(path: Path, table: str) -> tuple[dict, list[dict]]:
    rows = json.loads(path.read_text())
    fields = sorted({k for r in rows for k in r})
    dates = sorted(r["report_date"] for r in rows if r.get("report_date"))
    codes = {r.get("kod") for r in rows if r.get("kod")}
    cov = {"table": table, "path": str(path), "rows": len(rows), "instruments_with_code": len(codes),
           "earliest_report_date": dates[0] if dates else None, "latest_report_date": dates[-1] if dates else None,
           "schema": fields, "primary_key": ["insid", "year", "period"],
           "publication_field": "report_date", "currency_fields": ["currency", "currency_ratio"]}
    field_rows = []
    for field in fields:
        n = sum(r.get(field) is not None and r.get(field) != "" for r in rows)
        field_rows.append({"table": table, "field": field, "n_nonmissing": n,
                           "coverage_fraction": n / len(rows) if rows else 0.0})
    return cov, field_rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checkpoint = json.loads(CHECKPOINT.read_text())
    restriction = json.loads(RESTRICT.read_text())
    sparb = json.loads(SPARB.read_text())
    tables, schema_rows = [], []
    for stem, label in (("fundamentals_year_validated.json", "annual"),
                        ("fundamentals_quarter_validated.json", "quarterly"),
                        ("fundamentals_r12_validated.json", "r12")):
        coverage, rows = table_coverage(FUNDS / stem, label)
        tables.append(coverage); schema_rows.extend(rows)
    with (OUT / "OTQ2_SCHEMA_COVERAGE.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "field", "n_nonmissing", "coverage_fraction"])
        w.writeheader(); w.writerows(schema_rows)

    sources = [
        source(CHECKPOINT, "production_canonical_checkpoint", "tools/run_h0_v3_canonical_production_implementation.py", "PRIMARY_CANONICAL", "production checkpoint"),
        source(SPARB, "spar_b_fundamental_manifest", "tools/build_validated_fundamentals_final.py", "SECONDARY_BLOCKED", "report_date rules R1-R5, but formal freeze absent"),
        source(RESTRICT, "fundamental_restriction_registry", "restriction registry", "PRIMARY_GOVERNANCE", "explicit restrictions"),
        source(GOVERNANCE, "data_governance_registry", "governance", "PRIMARY_GOVERNANCE", "fundamentals forbidden / market cap EV blocked"),
        source(STATE, "current_research_state", "governance", "PRIMARY_GOVERNANCE", "fundamentals forbidden in model tests"),
    ] + [source(FUNDS / x, x.removesuffix(".json"), "tools/build_validated_fundamentals_final.py", "SECONDARY_BLOCKED", "report_date <= decision date would be required") for x in ("fundamentals_year_validated.json", "fundamentals_quarter_validated.json", "fundamentals_r12_validated.json")]
    provenance = {
        "study": "H0_V3_OTQ2_QUALITY_OVERLAY_BUILD_AND_TEST", "audit_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "economic_analysis_performed": False, "sources": sources, "fundamental_tables": tables,
        "currency_conflict": {"build_comment": "build_validated_fundamentals_final.py says report monetary values are already SEK and must not be converted again.",
                              "later_restriction": "FUNDAMENTAL_RESTRICTION_REGISTRY says canonical layer is original currency and needs explicit conversion for USD/EUR/ISK/NOK/PLN.",
                              "result": "UNRESOLVED_CONTRADICTION_FAIL_CLOSED"},
        "coverage_block": restriction["sammanfattning"],
        "survivorship_block": "67 of 68 delisted 2020-2026 instruments lack any identified fundamental data.",
        "formal_status": sparb.get("status"),
        "conclusion": "Not an authorized, sufficiently complete historical PIT foundation for OTQ2 economic testing."
    }
    (OUT / "OTQ2_DATA_PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")

    legacy = """# OTQ2 legacy audit\n\n## Scope\n\nLegacy material was read from `/home/hannesb/momentum_prod_work`, not used as an OTQ2 input or implementation.\n\n## What the old implementations did\n\n- `quality_screener.py`: a discretionary LLM/report-text quality funnel. It selected a report from MFN material, cached one JSON response per ticker, and later combined qualitative scores with cached market cap and valuation data. It explicitly warned that historical backtesting would leak because a modern LLM may know outcomes.\n- `value_screener.py`: hard-data Buffett-style score from `fundamentals_from_mfn.csv`, PDF extraction and Avanza fallbacks, with cached currency and market-cap retrieval. These are legacy inputs and are not authoritative PIT sources.\n- `quant_screener.py`: TradingView/Avanza snapshot metrics and cache-based composite ranks; not a dated historical research input.\n- `tune_quality_score_validation.py`: explicitly used cache-file mtime as an approximate known date. This is not PIT and is invalid for OTQ2 historical alpha.\n- `tune_quality_momentum_interact.py`: legacy `f_score × momentum` diagnostic on cached feature panels. Its documented question is useful context only; it is not a current PIT proof. Its conclusion must not justify a hard quality eligibility filter.\n- `tune_borsdata_fundamental_lgbm.py` and `tune_fundamentals.py`: legacy fixed-date annual-report assumptions and `fundamentals.csv`; the former is ML and therefore prohibited by the OTQ2 design.\n\n## Required lessons adopted\n\n1. LLM text assessment must not extract numeric fundamentals already available structurally.\n2. mtime is never a PIT timestamp.\n3. OTQ2 cannot use a hard high-quality eligibility threshold in its first test.\n4. Transparent equal-weight dimensions are required; no LGBM/XGB/NN or performance-selected weights.\n\n## Current audit outcome\n\nThe replacement data path has a documented currency-semantics contradiction, lacks fundamentals for 67/68 known delistings, has 209 material share-count restrictions, and is not formally frozen. Therefore no legacy result is carried forward and no new OTQ2 historical score is built in this run.\n"""
    (OUT / "OTQ2_LEGACY_AUDIT.md").write_text(legacy)

    placement = {"pre_result_mechanistic_assessment": {"A_universe_filter": "REJECTED: contradicts legacy QMJ lesson and changes eligibility.", "B_mix_into_K1": "REJECTED: confounds primary momentum alpha.", "C_secondary_selection": "ONLY_CONCEPTUAL_CANDIDATE: bounded +0.05 rerank at selection boundary.", "D_weighting": "NOT_TESTED: downstream of selection.", "E_confirmation": "NOT_TESTED: needs separate preregistration.", "F_retain_exit": "NOT_TESTED: needs separate preregistration.", "G_execution": "REJECTED: execution must not carry alpha."}, "decision": "NO_JUSTIFIED_OVERLAY_DATA_FOUNDATION_BLOCKED"}
    (OUT / "OTQ2_PLACEMENT_DECISION.json").write_text(json.dumps(placement, indent=2) + "\n")
    (OUT / "OTQ2_INSERTION_POINT_TRACE.md").write_text("# OTQ2 insertion-point trace\n\nNo insertion was implemented. The only conceptual allowed location is the existing pre-Top-30/refill momentum ordering. The audit failed before code tracing or any mutation of that path.\n")
    (OUT / "OTQ2_CURRENT_CARDS.json").write_text(json.dumps({"status": "NOT_GENERATED", "reason": "hard-data currency and governance gates failed; no score may be represented as current OTQ2_HARD."}, indent=2) + "\n")
    for name in ("OTQ2_QUAL_SNAPSHOT_LOG.jsonl", "OTQ2_QUAL_SOURCE_MANIFEST.jsonl"):
        (OUT / name).write_text("")
    for name in ("OTQ2_HARD_PANEL_SCORES.parquet", "OTQ2_HARD_COMPONENT_SCORES.parquet"):
        (OUT / f"{name}.NOT_CREATED").write_text("NOT_CREATED: data foundation gate failed before score construction.\n")
    model_spec = {"status": "NOT_FROZEN", "reason": "metric selection cannot be finalized while authoritative currency semantics, share-count validity, delisted coverage and governance permission remain unresolved.", "economic_results_accessed": False}
    (OUT / "OTQ2_MODEL_SPEC.json").write_text(json.dumps(model_spec, indent=2) + "\n")
    (OUT / "OTQ2_MODEL_FREEZE.json").write_text(json.dumps({"status": "INVALID_NOT_FROZEN", "model_spec_sha256": sha(OUT / "OTQ2_MODEL_SPEC.json"), "reason": model_spec["reason"]}, indent=2) + "\n")
    prereg = {"status": "BLOCKED_BEFORE_PREREGISTRATION", "allowed_arms": ["BASE_CURRENT_CANONICAL", "OTQ2_BOUNDED_5PP"], "economic_run_performed": False, "reason": "Data foundation must be repaired and explicitly authorized before a valid immutable economic preregistration can be frozen."}
    (OUT / "OTQ2_PREREGISTRATION.json").write_text(json.dumps(prereg, indent=2) + "\n")
    governance_text = GOVERNANCE.read_text() + STATE.read_text()
    blocked_by_governance = ("FORBIDDEN_IN_MODEL_TEST" in governance_text or
                             "DATA_BLOCKED_GOVERNANCE" in governance_text)
    currency_pass = provenance["currency_conflict"]["result"] != "UNRESOLVED_CONTRADICTION_FAIL_CLOSED"
    shares_pass = restriction["sammanfattning"].get("SHARES_UNVERIFIED", 0) == 0
    delisted_pass = restriction["sammanfattning"].get("DELISTED_FUNDAMENTALS_MISSING", 0) == 0
    formal_freeze = "EJ ÄNNU" not in str(sparb.get("status", "")).upper()
    economic_analysis_performed = provenance["economic_analysis_performed"]
    gates = {
        "PRODUCTION_CANONICAL_IDENTITY": checkpoint.get("all_gates_pass", False),
        "OTQ2_DATA_PROVENANCE": bool(sources) and len(tables) == 3,
        "OTQ2_CURRENT_DATA_PATHS": all(Path(s["exact_resolved_path"]).exists() for s in sources),
        "OTQ2_CURRENCY_REPAIR_IDENTITY": currency_pass,
        "OTQ2_REPORT_PUBLICATION_PIT": formal_freeze and not blocked_by_governance,
        "OTQ2_FUTURE_MUTATION_INVARIANCE": economic_analysis_performed,
        "OTQ2_MARKET_CAP_PIT": not blocked_by_governance,
        "OTQ2_SHARE_COUNT_PIT": shares_pass,
        "OTQ2_MODEL_SPEC_FROZEN": model_spec["status"] == "FROZEN",
        "OTQ2_NO_PERFORMANCE_BASED_FEATURE_SELECTION": not economic_analysis_performed,
        "OTQ2_MISSINGNESS_SEMANTICS": delisted_pass,
        "OTQ2_BASELINE_CANONICAL_REPLAY": economic_analysis_performed,
        "OTQ2_INSERTION_ISOLATION": economic_analysis_performed,
        "K7_DISABLED": checkpoint.get("gates", {}).get("ACTIVE_PATH_K7_OFF", False),
        "EXEC100BP_IDENTITY": economic_analysis_performed,
        "SELF_FINANCING": economic_analysis_performed,
        "COST_B": economic_analysis_performed,
        "RETURN_TIMING": economic_analysis_performed,
        "STATE_ISOLATION": economic_analysis_performed,
        "OTQ2_DETERMINISM": economic_analysis_performed,
        "NON_COMPUTED_CLAIM_SCAN": not any(token in (ROOT / "tools/h0_v3_production.py").read_text().lower()
                                       for token in ("hardcoded result", "hardcoded winner", "quality helps")),
    }
    (OUT / "OTQ2_GATES.json").write_text(json.dumps(gates, indent=2) + "\n")
    report = """# OTQ2 final report — fail closed before score construction\n\n## Purpose\n\nAssess whether a new transparent OTQ2 hard-quality overlay can be built and tested without mutating the H0 V3 production canonical.\n\n## Finding\n\nThis run stops before economic analysis. The sole currently identified candidate foundation is not authorized or sufficiently reliable for a historical model test: governance still forbids fundamental KPI and market-cap/EV model inputs; the later restriction registry records a material survivorship gap (67/68 delistings missing), material share-count restrictions (209), and currency restrictions; and its currency statement contradicts the repaired-build statement. The Spår B manifest is not formally frozen.\n\nNo returns, scores, selection changes, portfolio arms, company cards or qualitative snapshots were generated. This is intentional: inventing a reduced historical score would violate the requested no-special-model and fail-closed rules.\n\n## Final classification\n\n`OTQ2_HISTORICAL_COVERAGE_INSUFFICIENT`\n\nOTQ2_BUILD: INVALID\nOTQ2_HISTORICAL_PIT: INVALID\nPLACEMENT: NO_JUSTIFIED_OVERLAY\nECONOMIC_RESULT: OTQ2_HISTORICAL_COVERAGE_INSUFFICIENT\nPRODUCTION_MUTATION_PERFORMED: FALSE\nNEXT_ACTION: REPAIR_OTQ2_DATA_FOUNDATION\n"""
    (OUT / "OTQ2_FINAL_REPORT.md").write_text(report)
    (OUT / "OTQ2_FINAL_REPORT.json").write_text(json.dumps({"classification": "OTQ2_HISTORICAL_COVERAGE_INSUFFICIENT", "production_mutation_performed": False, "next_action": "REPAIR_OTQ2_DATA_FOUNDATION", "economic_analysis_performed": False, "gates": gates}, indent=2) + "\n")
    print(json.dumps({"output": str(OUT), "classification": "OTQ2_HISTORICAL_COVERAGE_INSUFFICIENT", "failed_gates": [k for k, v in gates.items() if not v]}, indent=2))


if __name__ == "__main__":
    main()
