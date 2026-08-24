#!/usr/bin/env python3
"""Create or verify the final immutable freeze for locked event-alpha tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_k/EVENT_ALPHA_FINAL_FREEZE.json"
HASH = ROOT / "research_k/EVENT_ALPHA_FINAL_FREEZE.sha256"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paths() -> list[Path]:
    fixed = [
        ROOT / "trackj/validated_mfn_report_events_v1/manifest.json",
        ROOT / "trackj/validated_fi_insider_v4/FINAL_FREEZE_MANIFEST.json",
        ROOT / "research_k/REPORT_PEAD_PREREGISTRATION_BEFORE_ALPHA.json",
        ROOT / "research_k/INSIDER_CONDITIONAL_H0_PREREGISTRATION_BEFORE_ALPHA.json",
        ROOT / "research_k/EVENT_ALPHA_OPERATIONAL_LOCK_BEFORE_RESULTS.json",
        ROOT / "research_k/EVENT_ALPHA_FINAL_DECISION.json",
        ROOT / "docs/SPARJK_LOCKED_EVENT_ALPHA_RESULTS.md",
        ROOT / "tools/sparjk_locked_event_alpha.py",
    ]
    results = []
    for directory in (ROOT / "research_k/results/REPORT_PEAD_LOCKED_V1",
                      ROOT / "research_k/results/INSIDER_CONDITIONAL_H0_LOCKED_V1"):
        results.extend(sorted(p for p in directory.iterdir() if p.is_file()))
    return fixed + results


def verify() -> dict:
    expected = HASH.read_text().split()[0]
    if sha(OUT) != expected:
        raise RuntimeError("final freeze manifest hash mismatch")
    data = json.loads(OUT.read_text())
    for row in data["files"]:
        path = ROOT / row["path"]
        if not path.is_file() or sha(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"frozen path mismatch: {path}")
    return {"status": "PASS", "version": data["version_id"], "files": len(data["files"]),
            "manifest_sha256": expected}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--verify", action="store_true"); args = ap.parse_args()
    if args.verify:
        print(json.dumps(verify(), indent=2)); return
    if OUT.exists() or HASH.exists():
        raise RuntimeError("immutable final freeze already exists")
    files = paths()
    data = {"version_id": "SPARJK_LOCKED_EVENT_ALPHA_V1_IMMUTABLE_2026-08-09",
            "H0_changed": False, "report_insider_combined": False, "parameters_searched": 0,
            "files": [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]}
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    HASH.write_text(sha(OUT) + "  EVENT_ALPHA_FINAL_FREEZE.json\n")
    print(json.dumps(verify(), indent=2))


if __name__ == "__main__":
    main()
