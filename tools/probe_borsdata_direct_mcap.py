#!/usr/bin/env python3
"""Narrow data-source probe for Börsdata KPI 50 (Market Cap).

No alpha, market-cap bucket, return, P&L, or strategy calculation is made.
The purpose is solely to establish what the locally cached Börsdata API
actually returns and whether its time semantics support frozen H0 panels.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_k" / "borsdata_direct_mcap_probe"
META = ROOT / "raw/borsdata/metadata/kpis_metadata__20260808T042524Z.json"
MANIFEST = ROOT / "raw/borsdata/kpi_valuation/_manifest.jsonl"
UNIVERSE = ROOT / "docs/probes/kpi_history_universum.json"
SWAGGER = ROOT / "docs/probes/swagger_v1.json"
PATHS = {
    "W1": ROOT / "research_k/h0_v3_state_machine_and_path_ledger/PATH_LEDGER_W1.csv",
    "W2": ROOT / "research_k/h0_v3_state_machine_and_path_ledger/PATH_LEDGER_W2.csv",
}
IMPORTANT = ["SAGA-B", "NET-B", "BALD-B", "IAR-B", "EOLU-B", "VOLO", "VBG-B", "CLAS-B", "RAY-B", "HTRO", "IPCO"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META.read_text())
    mcap = next(x for x in meta["kpiHistoryMetadatas"] if x["kpiId"] == 50)
    ev = next(x for x in meta["kpiHistoryMetadatas"] if x["kpiId"] == 49)
    shares = next(x for x in meta["kpiHistoryMetadatas"] if x["kpiId"] == 61)
    dump(OUT / "BORSDATA_MCAP_KPI_INVENTORY.json", {
        "source_metadata": {"path": str(META.relative_to(ROOT)), "sha256": sha(META)},
        "identified_fields": [
            {**mcap, "endpoint_template": "/v1/instruments/{insId}/kpis/50/{reporttype}/{pricetype}/history"},
            {**ev, "role": "separate control; not market cap"},
            {**shares, "role": "separate field; not used to reconstruct market cap in this probe"},
        ],
        "field_identification": "KPI 50 is explicitly named Börsvärde / Market Cap; no KPI-ID was inferred.",
    })

    records = [json.loads(x) for x in MANIFEST.read_text().splitlines() if x.strip()]
    mcap_records = [r for r in records if "/kpis/50/" in r.get("endpoint", "")]
    api_by_type = []
    responses = []
    for r in mcap_records:
        report_type = r["endpoint"].split("/")[4]
        file = ROOT / "raw/borsdata" / r["file"] if r.get("file") else None
        exists = bool(file and file.exists())
        api_by_type.append({"report_type": report_type, "http_status": r["http_status"], "ok": r["ok"],
                            "raw_file_exists": exists, "endpoint": r["endpoint"], "price_type": "mean"})
        if exists:
            payload = json.loads(file.read_text())
            responses.append((r, file, payload))

    # Merge raw values strictly for availability inspection, not PIT assignment.
    values = defaultdict(list)
    for rec, file, payload in responses:
        for inst in payload.get("kpisList", []):
            for value in inst.get("values", []):
                values[str(inst["instrument"])].append({
                    "report_type": payload.get("reportTime"), "price_type": payload.get("priceValue"),
                    "year": value.get("y"), "period_token": value.get("p"), "value": value.get("v"),
                    "raw_file": str(file.relative_to(ROOT)), "raw_sha256": sha(file),
                })
    for x in values.values():
        x.sort(key=lambda q: (q["report_type"], q["year"] or 0, q["period_token"] or 0))

    raw_sample = {
        "purpose": "verbatim source excerpts and file hashes; no interpretation as PIT dates",
        "response_schema_observed": {"top_level": ["kpiId", "reportTime", "priceValue", "kpisList"],
                                     "value_fields": ["y", "p", "v"]},
        "examples": [{"source_file": str(f.relative_to(ROOT)), "sha256": sha(f),
                       "payload": p} for _, f, p in responses[:1]],
    }
    dump(OUT / "BORSDATA_MCAP_SAMPLE_RAW.json", raw_sample)

    swagger_text = SWAGGER.read_text()
    semantics = {
        "KPI_50": {"name_sv": mcap["nameSv"], "name_en": mcap["nameEn"], "format": mcap["format"]},
        "documented_endpoint": "/v1/instruments/kpis/{kpiId}/{reporttype}/{pricetype}/history",
        "documented_report_types": ["year", "r12", "quarter"],
        "documented_price_type_parameter": "priceType; cached KPI 50 requests use mean",
        "cached_api_execution": {
            "year": {"successes": sum(x["ok"] for x in api_by_type if x["report_type"] == "year"),
                     "failures": sum(not x["ok"] for x in api_by_type if x["report_type"] == "year")},
            "r12": {"successes": sum(x["ok"] for x in api_by_type if x["report_type"] == "r12"),
                    "failures": sum(not x["ok"] for x in api_by_type if x["report_type"] == "r12")},
            "quarter": {"successes": sum(x["ok"] for x in api_by_type if x["report_type"] == "quarter"),
                        "failures": sum(not x["ok"] for x in api_by_type if x["report_type"] == "quarter")},
        },
        "observed_value_schema": "{y, p, v}; no observation_date, period_end, report_date, publication_date, available_at or effective timestamp",
        "daily_or_date_specific_mcap_available": False,
        "historical_direct_value_available": bool(values),
        "pit_semantics_verified": False,
        "why_blocked": [
            "KPI history values identify year and a period token only, not a calendar observation date.",
            "Neither API schema nor cached payload documents when historical market-cap values became available.",
            "The cached values use priceValue=mean, so they are not date-specific market-cap observations.",
            "KPI 50 quarterly endpoint returned HTTP 400 in all eight cached batches.",
            "A period-end value without availability semantics cannot be mapped to frozen H0 decision dates without potential future leakage.",
        ],
        "scope": "UNKNOWN: API returns values keyed to instrument id, but local metadata/payload does not state whether KPI 50 is company total or share-class market value.",
        "swagger_source_contains_endpoint": "/v1/instruments/kpis/{kpiId}/{reporttype}/{pricetype}/history" in swagger_text,
    }
    dump(OUT / "BORSDATA_MCAP_SEMANTICS_REPORT.json", semantics)

    uni = json.loads(UNIVERSE.read_text())
    t2id = {x["kod"]: str(x["insId"]) for x in uni["instrument"]}
    # Potential API availability is shown separately from PIT availability.
    coverage = []
    important_counts = defaultdict(lambda: {"all": 0, "selected": 0})
    for window, path in PATHS.items():
        per_year = defaultdict(lambda: Counter())
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("eligible") != "True":
                    continue
                yr = row["date"][:4]
                t = row["ticker"]; selected = row.get("selected") == "True"
                c = per_year[yr]; c["eligible"] += 1; c["selected"] += int(selected)
                iid = t2id.get(t)
                has_nonpit = any(v["year"] == int(yr) and (v["value"] or 0) > 0 for v in values.get(iid, []))
                c["api_calendar_year_value"] += int(has_nonpit)
                if t in IMPORTANT:
                    important_counts[(window, t)]["all"] += 1
                    important_counts[(window, t)]["selected"] += int(selected)
        for yr, c in sorted(per_year.items()):
            coverage.append({
                "window": window, "year": yr, "population": "PIT_ELIGIBLE_UNIVERSE",
                "total_security_panel_observations": c["eligible"], "direct_mcap_pit_available": 0,
                "direct_mcap_pit_unavailable": c["eligible"], "direct_mcap_pit_coverage_pct": 0.0,
                "api_same_calendar_year_nonpit_value_exists": c["api_calendar_year_value"],
                "api_same_calendar_year_nonpit_coverage_pct": 100*c["api_calendar_year_value"]/c["eligible"] if c["eligible"] else None,
                "median_staleness_days": "NOT_DEFINABLE_NO_AVAILABLE_AT", "p90_staleness_days": "NOT_DEFINABLE_NO_AVAILABLE_AT",
            })
            coverage.append({
                "window": window, "year": yr, "population": "SELECTED_PRE_SMA",
                "total_security_panel_observations": c["selected"], "direct_mcap_pit_available": 0,
                "direct_mcap_pit_unavailable": c["selected"], "direct_mcap_pit_coverage_pct": 0.0,
                "api_same_calendar_year_nonpit_value_exists": "NOT_COMPUTED_TO_AVOID_PIT_IMPLICATION",
                "api_same_calendar_year_nonpit_coverage_pct": "NOT_COMPUTED_TO_AVOID_PIT_IMPLICATION",
                "median_staleness_days": "NOT_DEFINABLE_NO_AVAILABLE_AT", "p90_staleness_days": "NOT_DEFINABLE_NO_AVAILABLE_AT",
            })
    fields = list(coverage[0]); write_csv(OUT / "BORSDATA_DIRECT_MCAP_COVERAGE.csv", coverage, fields)

    important_qa = []
    for ticker in IMPORTANT:
        iid = t2id.get(ticker); vs = values.get(iid, [])
        ys = sorted({v["year"] for v in vs if (v["value"] or 0) > 0})
        important_qa.append({"ticker": ticker, "instrument_id": iid, "first_available_history_year": min(ys) if ys else None,
                             "last_available_history_year": max(ys) if ys else None, "number_of_value_observations": len(vs),
                             "frequencies": ";".join(sorted({v["report_type"] for v in vs})),
                             "missing_periods": "NOT_ASSESSABLE_WITHOUT_DATE_SEMANTICS", "MCAP_SCOPE": "UNKNOWN",
                             "PIT_confidence": "BLOCKED_NO_OBSERVATION_OR_AVAILABLE_DATE"})
    write_csv(OUT / "BORSDATA_MCAP_IMPORTANT_SECURITY_QA.csv", important_qa, list(important_qa[0]))

    # Event names are taken only from existing local corporate-action QA; a
    # month/day sanity check is impossible with KPI 50's year/period-token output.
    qa_rows = []
    for ticker, event in [("SAGA-B", "2019 split candidate"), ("CLAS-B", "share-class/ticker history QA"),
                          ("RAY-B", "2008 split candidate"), ("NET-B", "corporate-action QA requested")]:
        qa_rows.append({"ticker": ticker, "event": event, "before": "NOT_AVAILABLE_DATE_SPECIFIC",
                        "after": "NOT_AVAILABLE_DATE_SPECIFIC", "market_cap_ratio": "NOT_COMPUTABLE",
                        "assessment": "BLOCKED: KPI 50 cache has no daily observation/effective date; cannot test corporate-action continuity."})
    write_csv(OUT / "BORSDATA_MCAP_CORPORATE_ACTION_QA.csv", qa_rows, list(qa_rows[0]))

    readiness = {
        "study": "BORSDATA_DIRECT_HISTORICAL_MCAP_DATA_SOURCE_PROBE",
        "classification": "BORSDATA_DIRECT_MCAP_SEMANTICS_BLOCKED",
        "direct_field_found": True,
        "direct_field": "KPI 50 Börsvärde / Market Cap",
        "direct_daily_historical_field_found": False,
        "historical_frequency_observed": ["year", "r12"],
        "quarter_endpoint_status": "HTTP_400_FOR_ALL_8_CACHED_BATCHES",
        "pit_date_semantics": "NOT_DOCUMENTED_OR_RETURNED",
        "mcap_scope": "UNKNOWN",
        "corporate_action_sanity": "NOT_TESTABLE_WITH_NON_DATE_SPECIFIC_VALUES",
        "w1_w2_pit_coverage": "0% by definition; no value can be honestly assigned an available_at timestamp",
        "missingness_structure": "cannot be assessed as PIT missingness; endpoint-history availability exists but mapping would be future-contaminated",
        "next_data_action": "Obtain Börsdata documentation/API route that returns date-specific historical market cap with observation/effective/availability timestamps and documented company-vs-share-class scope. Do not use KPI 50 history as PIT until then.",
        "alpha_analysis_run": False,
    }
    dump(OUT / "BORSDATA_MCAP_READINESS_REPORT.json", readiness)
    (OUT / "SUMMARY.md").write_text(
        "# Börsdata direct Market Cap probe\n\n"
        "KPI 50 (`Börsvärde` / `Market Cap`) exists and cached history responds for `year` and `r12` with `priceValue=mean`. It is not usable for frozen H0 PIT panel mapping: payload values contain only `{y,p,v}`, while observation date, publication/availability time, and company-versus-share-class scope are undocumented. Quarterly KPI 50 requests returned HTTP 400. No alpha analysis was run.\n",
        encoding="utf-8")
    hashes = {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "HASHES.json"}
    dump(OUT / "HASHES.json", hashes)


if __name__ == "__main__":
    main()
