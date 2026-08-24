#!/usr/bin/env python3
"""Read-only fail-fast verifier for frozen MFN and FI event foundations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check(path: Path, expected: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing frozen path: {path}")
    actual = sha(path)
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch: {path}: {actual} != {expected}")


def main() -> None:
    mfn_path = ROOT / "trackj/validated_mfn_report_events_v1/manifest.json"
    mfn = json.loads(mfn_path.read_text())
    for row in [*mfn["inputs"], *mfn["outputs"]]:
        check(ROOT / row["path"], row["sha256"])

    fi_dir = ROOT / "trackj/validated_fi_insider_v4"
    fi_path = fi_dir / "FINAL_FREEZE_MANIFEST.json"
    expected_line = (fi_dir / "FINAL_FREEZE_MANIFEST.sha256").read_text().split()[0]
    check(fi_path, expected_line)
    fi = json.loads(fi_path.read_text())
    for row in fi["files"]:
        path = ROOT / row["path"]
        check(path, row["sha256"])
        if path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"byte-count mismatch: {path}")
    print(json.dumps({
        "status": "PASS",
        "mfn_version": mfn["version_id"],
        "mfn_manifest_sha256": sha(mfn_path),
        "fi_version": fi["version_id"],
        "fi_manifest_sha256": sha(fi_path),
        "fi_files": len(fi["files"])
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
