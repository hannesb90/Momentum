#!/usr/bin/env python3
"""Fail-fast byte/path/count verification for immutable J2B/J3 artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def lines(path: Path) -> int:
    with path.open("rb") as fh: return sum(1 for _ in fh)


def raw_manifest(run: Path) -> dict:
    rows = [json.loads(x) for x in (run / "manifest.jsonl").read_text().splitlines()]
    checked = 0
    for row in rows:
        path = ROOT / row["path"]
        if not path.is_file(): raise RuntimeError(f"missing RAW: {path}")
        if path.stat().st_size != row["response_bytes"]: raise RuntimeError(f"size mismatch: {path}")
        if sha(path) != row["response_sha256"]: raise RuntimeError(f"hash mismatch: {path}")
        checked += 1
    return {"manifest": str((run / "manifest.jsonl").relative_to(ROOT)), "entries": checked,
            "manifest_sha256": sha(run / "manifest.jsonl")}


def validated_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text()); checked = 0
    for row in manifest["files"]:
        target = ROOT / row["path"]
        if not target.is_file(): raise RuntimeError(f"missing validated file: {target}")
        if sha(target) != row["sha256"]: raise RuntimeError(f"validated hash mismatch: {target}")
        if row.get("rows") is not None and lines(target) != row["rows"]:
            raise RuntimeError(f"validated row mismatch: {target}")
        checked += 1
    return {"manifest": str(path.relative_to(ROOT)), "files": checked, "manifest_sha256": sha(path)}


def main() -> None:
    result = {
        "mfn_discovery_raw": raw_manifest(ROOT / "trackj/mfn/MFN_V2_20260809T130000Z"),
        "mfn_author_raw": raw_manifest(ROOT / "trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z"),
        "mfn_validated": validated_manifest(ROOT / "trackj/validated_mfn_events_v1/manifest.json"),
        "fi_raw": raw_manifest(ROOT / "trackj/fi/FI_OFFICIAL_V2_20260809T150000Z"),
        "fi_validated": validated_manifest(ROOT / "trackj/validated_fi_insider_v1/manifest.json"),
        "status": "PASS",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
