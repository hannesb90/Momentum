#!/usr/bin/env python3
"""Fail fast unless every declared repaired D/F freeze artifact matches bytes/path/counts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(path: Path) -> dict:
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


def check_file(item: dict, failures: list) -> None:
    path = ROOT / item["path"]
    if not path.is_file():
        failures.append({"path": item["path"], "error": "MISSING"})
        return
    actual = {"bytes": path.stat().st_size, "sha256": sha(path), **counts(path)}
    for key, expected in item.items():
        if key == "path":
            continue
        if key in {"bytes", "sha256", "json_type", "row_count", "top_level_count", "nested_row_count"} and actual.get(key) != expected:
            failures.append({"path": item["path"], "field": key, "expected": expected, "actual": actual.get(key)})
            return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="repair_df/FREEZE_MANIFEST.json")
    args = ap.parse_args()
    manifest_path = ROOT / args.manifest
    if not manifest_path.is_file():
        raise SystemExit(f"FAIL: manifest missing: {args.manifest}")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for item in [m["generator"], *m["inputs"], *m["controls"]]:
        check_file(item, failures)
    for result in m["outputs"].values():
        current = []
        for item in result["files"]:
            check_file(item, failures)
            current.append(item)
        actual_aggregate = hashlib.sha256(
            json.dumps(current, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if actual_aggregate != result["freeze_aggregate_sha256"]:
            failures.append({"path": result["path"], "field": "freeze_aggregate_sha256", "expected": result["freeze_aggregate_sha256"], "actual": actual_aggregate})
    if failures:
        print(json.dumps({"status": "FAIL", "manifest_sha256": sha(manifest_path), "failures": failures}, indent=2))
        raise SystemExit(1)
    print(json.dumps({"status": "PASS", "manifest_sha256": sha(manifest_path), "files_checked": 1 + len(m["inputs"]) + len(m["controls"]) + sum(len(x["files"]) for x in m["outputs"].values())}, indent=2))


if __name__ == "__main__":
    main()
