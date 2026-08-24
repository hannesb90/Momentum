#!/usr/bin/env python3
"""Analyze the immutable J2A Börsdata probes without reading targets/models."""

from __future__ import annotations

import glob
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "trackj/j2a_borsdata_api_probe/raw/J2A_PROBE_2026-08-09T120000Z"
OUT = ROOT / "trackj/j2a_borsdata_api_probe/J2A_AUDIT_RESULTS.json"
YEARS = range(2020, 2027)
DATE_FIELD = {
    "report_calendar": "releaseDate",
    "dividend_calendar": "excludingDate",
    "insider": "verificationDate",
    "buyback": "date",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except (ValueError, TypeError):
        return None


def load_endpoint(name: str) -> list[dict]:
    rows: list[dict] = []
    for filename in sorted(glob.glob(str(RUN / name / "*.json"))):
        rows.extend(json.loads(Path(filename).read_text()).get("list") or [])
    return rows


def main() -> None:
    match = json.loads((ROOT / "raw/borsdata/_matchning.json").read_text())
    terminals = json.loads((ROOT / "validated/terminal_events.json").read_text())
    matched = match["matchade"]
    unmatched = match["ej_matchade"]
    matched_codes = {r["kod"] for r in matched}
    terminal_codes = set(terminals)
    terminal_matched = terminal_codes & matched_codes
    endpoint_stats = {}
    schemas = {}

    for name, date_field in DATE_FIELD.items():
        rows = load_endpoint(name)
        events_by_insid = {int(r["insId"]): (r.get("values") or []) for r in rows}
        all_events = [event for values in events_by_insid.values() for event in values]
        schemas[name] = sorted({field for event in all_events for field in event})
        per_year = {}
        for y in YEARS:
            relevant = [(insid, event) for insid, values in events_by_insid.items()
                        for event in values if year(event.get(date_field)) == y]
            per_year[str(y)] = {
                "events": len(relevant),
                "instruments": len({insid for insid, _ in relevant}),
            }
        endpoint_stats[name] = {
            "queried_instruments": len(rows),
            "instruments_with_any_event": sum(bool(v) for v in events_by_insid.values()),
            "events_all_dates": len(all_events),
            "events_2020_2026": sum(v["events"] for v in per_year.values()),
            "instruments_with_event_2020_2026": len({
                insid for insid, values in events_by_insid.items()
                if any(year(e.get(date_field)) in YEARS for e in values)
            }),
            "per_year": per_year,
            "all_timestamps_midnight": all(
                not e.get(date_field) or e[date_field][11:19] == "00:00:00" for e in all_events
            ),
            "null_counts": {
                field: sum(event.get(field) is None for event in all_events)
                for field in schemas[name]
            },
        }

    insider_rows = load_endpoint("insider")
    insider = [e for r in insider_rows for e in (r.get("values") or [])]
    lags = []
    for e in insider:
        if e.get("transactionDate") and e.get("verificationDate"):
            t = datetime.fromisoformat(e["transactionDate"])
            v = datetime.fromisoformat(e["verificationDate"])
            lags.append((v - t).days)
    endpoint_stats["insider"]["transaction_type_counts"] = dict(sorted(Counter(
        str(e.get("transactionType")) for e in insider
    ).items()))
    endpoint_stats["insider"]["verification_lag_days"] = {
        "n": len(lags),
        "min": min(lags),
        "median": sorted(lags)[len(lags) // 2],
        "max": max(lags),
        "negative": sum(x < 0 for x in lags),
        "zero": sum(x == 0 for x in lags),
    }

    buyback = [e for r in load_endpoint("buyback") for e in (r.get("values") or [])]
    endpoint_stats["buyback"]["quality_flags"] = {
        "price_zero": sum(e.get("price") == 0 for e in buyback),
        "change_negative": sum((e.get("change") or 0) < 0 for e in buyback),
        "change_zero": sum((e.get("change") or 0) == 0 for e in buyback),
        "missing_market_known_time_field": len(buyback),
    }

    reports = endpoint_stats["report_calendar"]
    reports["future_or_scheduled_after_retrieval_2026"] = sum(
        1 for r in load_endpoint("report_calendar") for e in (r.get("values") or [])
        if (e.get("releaseDate") or "")[:10] > "2026-08-09"
    )

    splits = json.loads((RUN / "stock_splits_2020.json").read_text()).get("stockSplitList") or []
    split_insids = {int(e["instrumentId"]) for e in splits}
    verified_insids = {int(r["insid"]) for r in matched}

    swagger = json.loads((RUN / "swagger_v1.json").read_text())
    paths = sorted(swagger["paths"])
    report_schema = swagger["components"]["schemas"]["ReportV1"]["properties"]
    result = {
        "audit": "J2A_FULL_BORSDATA_API_DATA_GAP_AUDIT",
        "generated_from_probe": str(RUN.relative_to(ROOT)),
        "probe_manifest_sha256": sha(RUN / "manifest.jsonl"),
        "target_feature_model_data_read": False,
        "v2_identity_scope": {
            "borsdata_match_file_universe": match["n_universum"],
            "verified_isin_to_insid": match["n_matchade"],
            "unmatched": match["n_ej_matchade"],
            "verified_terminal_instruments": len(terminals),
            "terminal_with_verified_current_insid_bridge": len(terminal_matched),
            "terminal_without_current_insid_bridge": len(terminal_codes - matched_codes),
            "unmatched_codes": [r["kod"] for r in unmatched],
        },
        "official_openapi": {
            "title": swagger["info"]["title"],
            "version": swagger["info"]["version"],
            "paths": paths,
            "relevant_schemas": schemas,
            "report_fields": sorted(report_schema),
            "has_estimates_or_consensus_endpoint": any(
                "estimate" in p.lower() or "consensus" in p.lower() for p in paths
            ),
            "has_general_corporate_actions_endpoint": any(
                "corporate" in p.lower() or "action" in p.lower() for p in paths
            ),
        },
        "endpoint_coverage_for_352_verified_current_insids": endpoint_stats,
        "terminal_coverage": {
            "report_calendar": {"addressable": 0, "events": None},
            "dividend_calendar": {"addressable": 0, "events": None},
            "insider": {"addressable": 0, "events": None},
            "buyback": {"addressable": 0, "events": None},
            "interpretation": "Current /v1/instruments did not expose a verified insId bridge for any of the 68 terminal V2 instruments; absence of events cannot be inferred.",
        },
        "stock_splits": {
            "events_since_2020": len(splits),
            "events_on_verified_current_v2_insids": sum(int(e["instrumentId"]) in verified_insids for e in splits),
            "verified_current_v2_instruments_with_split": len(split_insids & verified_insids),
            "schema": sorted({k for e in splits for k in e}),
        },
        "family_classification": {
            "report_attention_pead": {
                "classification": "KRÄVER BÖRSDATA + MFN",
                "reason": "Börsdata has date-only calendar/type but no publication timestamp, actual/estimated flag, or terminal insId coverage.",
            },
            "dividend_gap": {
                "classification": "DATA FORTSATT OTILLRÄCKLIG",
                "reason": "Only ex-date is exposed; no announcement/decision/AGM/record/payment market-known timestamp.",
            },
            "insider_gap": {
                "classification": "KRÄVER BÖRSDATA + FI",
                "reason": "Verification time is promising for active instruments, but terminal addressability is 0/68 and official revision semantics require FI.",
            },
            "buyback_shareholder_yield": {
                "classification": "DATA FORTSATT OTILLRÄCKLIG",
                "reason": "No market-known timestamp or explicit issuance endpoint; signed changes and zero prices need semantic QA.",
            },
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    OUT.write_bytes(payload)
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": hashlib.sha256(payload).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
