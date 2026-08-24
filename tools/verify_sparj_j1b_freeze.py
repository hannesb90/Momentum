#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "trackj/FREEZE_MANIFEST_J1B.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    freeze = json.loads(FREEZE.read_text())
    actual = []
    for row in freeze["files"]:
        path = ROOT / row["path"]
        assert path.is_file(), path
        assert path.stat().st_size == row["bytes"], path
        assert sha(path) == row["sha256"], path
        actual.append(row)
    aggregate = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert aggregate == freeze["aggregate_sha256"]
    assert sha(FREEZE) == (ROOT / "trackj/FREEZE_MANIFEST_J1B.sha256").read_text().split()[0]
    scope = json.loads((ROOT / "trackj/results/SPARJ_J1B_ATR_ADX_V1/protected_scope_audit.json").read_text())
    assert scope["status"] == "PASS" and not scope["changed"]
    assert freeze["new_challenger"] is None
    print(json.dumps({"status": "PASS", "files": len(actual), "manifest_sha256": sha(FREEZE), "aggregate_sha256": aggregate}, sort_keys=True))


if __name__ == "__main__":
    main()
