#!/usr/bin/env python3
"""Fail-fast verification and final immutable manifests for MFN/FI foundations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from sparj_fetch_mfn_immutable import frozen_universe


ROOT = Path(__file__).resolve().parents[1]
MFN = ROOT / "trackj/validated_mfn_report_events_v1"
FI_RAW = ROOT / "trackj/fi/FI_OFFICIAL_V2_20260809T190500Z"
FI = ROOT / "trackj/validated_fi_insider_v4"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, expected: str) -> None:
    if not path.is_file() or sha(path) != expected:
        raise RuntimeError(f"hash/path verification failed: {path}")


def main() -> None:
    # MFN immutable layer and every declared input/output.
    mfn_manifest_path = MFN / "manifest.json"
    mfn_manifest = json.loads(mfn_manifest_path.read_text())
    for row in [*mfn_manifest["inputs"], *mfn_manifest["outputs"]]:
        verify(ROOT / row["path"], row["sha256"])

    # FI raw: unique disjoint requests and byte-for-byte raw verification.
    raw_summary = json.loads((FI_RAW / "summary.json").read_text())
    raw_manifest_path = FI_RAW / "manifest.jsonl"
    if sha(raw_manifest_path) != raw_summary["manifest_sha256"]:
        raise RuntimeError("FI raw manifest hash mismatch")
    raw_rows = [json.loads(x) for x in raw_manifest_path.read_text().splitlines()]
    keys = [(r["window_from"], r["window_to"], r["kind"]) for r in raw_rows]
    if len(keys) != len(set(keys)) or len(raw_rows) != 346:
        raise RuntimeError("FI request uniqueness/count mismatch")
    for row in raw_rows:
        verify(ROOT / row["path"], row["response_sha256"])
    if (raw_summary["records"] != raw_summary["official_global_record_count"]
            or raw_summary["official_global_record_count"] != 120446):
        raise RuntimeError("FI official completeness mismatch")

    validated_path = FI / "validated_fi_insider.jsonl"
    fi_summary_path = FI / "qa_summary.json"
    fi_summary = json.loads(fi_summary_path.read_text())
    if sha(validated_path) != fi_summary["validated_sha256"]:
        raise RuntimeError("FI validated bytes mismatch")
    rows = [json.loads(x) for x in validated_path.read_text().splitlines()]
    if len(rows) != fi_summary["validated_rows"]:
        raise RuntimeError("FI validated row count mismatch")
    if any(not r["market_known_time"].endswith("+00:00") for r in rows):
        raise RuntimeError("FI market_known_time is not explicit UTC")
    if any(not r["pre_terminal_event"] for r in rows):
        raise RuntimeError("post-terminal FI row entered validated layer")

    universe = frozen_universe()
    all_codes = {r["instrument_id"] for r in universe}
    terminal_events = json.loads((ROOT / "validated/terminal_events.json").read_text())
    terminal = set(terminal_events)
    covered = {r["instrument_id"] for r in rows}
    statuses = Counter(r["source_status"] for r in rows)
    correction_shapes = Counter(
        (r["source_status"], bool(r["correction_flag"]), bool(r["correction_description"])) for r in rows
    )
    extended = {
        "version": "FI_INSIDER_FOUNDATION_FINAL_QA_V1",
        "status": "PASS_MED_BEGRAENSNING",
        "raw_completeness": {
            "parsed_records": raw_summary["records"],
            "official_records": raw_summary["official_global_record_count"],
            "windows": raw_summary["windows"],
            "manifest_sha256": raw_summary["manifest_sha256"]
        },
        "coverage": {
            "universe": len(all_codes), "covered": len(covered),
            "current_universe": len(all_codes - terminal), "current_covered": len(covered - terminal),
            "terminal_universe": len(terminal), "terminal_pre_event_covered": len(covered & terminal),
            "missing_current": sorted((all_codes - terminal) - covered),
            "missing_terminal": sorted(terminal - covered)
        },
        "rows": len(rows),
        "source_status": dict(statuses),
        "correction_shapes": [
            {"status": k[0], "has_flag": k[1], "has_description": k[2], "rows": v}
            for k, v in sorted(correction_shapes.items())
        ],
        "correction_pit_decision": "source_status is retrieval-time state and is never allowed to filter historical availability; publications remain timestamped individually; stable FI report ID is unavailable",
        "identity": "exact ISIN only",
        "timezone": "FI Europe/Stockholm publication timestamp normalized to UTC",
        "target_feature_model_data_read": False
    }
    extended_path = FI / "qa_extended.json"
    extended_path.write_text(json.dumps(extended, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    prereg = ROOT / "research_k/INSIDER_CONDITIONAL_H0_PREREGISTRATION_BEFORE_ALPHA.json"
    crossval = FI / "fi_borsdata_crossvalidation.json"
    files = [
        raw_manifest_path, FI_RAW / "summary.json", validated_path, fi_summary_path,
        FI / "manifest.json", crossval, extended_path, prereg,
        ROOT / "tools/sparj_fetch_fi_parallel_immutable.py",
        ROOT / "tools/sparj_normalize_fi_insider.py",
        ROOT / "tools/sparj_crossvalidate_fi_borsdata.py"
    ]
    final_manifest = {
        "version_id": "FI_INSIDER_FOUNDATION_V1_IMMUTABLE_2026-08-09",
        "files": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p), "bytes": p.stat().st_size} for p in files]
    }
    final_path = FI / "FINAL_FREEZE_MANIFEST.json"
    final_path.write_text(json.dumps(final_manifest, indent=2, sort_keys=True) + "\n")
    (FI / "FINAL_FREEZE_MANIFEST.sha256").write_text(sha(final_path) + "  FINAL_FREEZE_MANIFEST.json\n")
    print(json.dumps({
        "mfn_status": "PASS_MED_BEGRAENSNING", "mfn_manifest_sha256": sha(mfn_manifest_path),
        "fi_status": extended["status"], "fi_coverage": extended["coverage"],
        "fi_final_manifest_sha256": sha(final_path)
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
