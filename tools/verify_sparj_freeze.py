#!/usr/bin/env python3
"""Fail-fast verifier for the Track J J0/J1 freeze; reads no targets or models."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OHLC = ROOT / "trackj/ohlc_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = OHLC / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "IMMUTABLE_FROZEN"
    assert manifest["target_read"] is False
    assert manifest["model_imports"] is False
    assert manifest["feature_engineering"] is False

    actual = []
    for row in manifest["files"]:
        path = OHLC / row["path"]
        assert path.is_file(), f"missing: {path}"
        assert path.stat().st_size == row["bytes"], f"byte mismatch: {path}"
        assert sha256(path) == row["sha256"], f"hash mismatch: {path}"
        actual.append(row)

    aggregate = hashlib.sha256(
        json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert aggregate == manifest["aggregate_sha256"]
    expected_manifest_hash = (OHLC / "manifest.sha256").read_text().split()[0]
    assert sha256(manifest_path) == expected_manifest_hash

    qa = json.loads((OHLC / "qa/ohlc_qa.json").read_text())
    assert qa["status"] == "PASS"
    assert qa["counts"]["expected_A_rows"] == qa["counts"]["validated_rows"]
    assert qa["instruments"] == 420
    assert qa["terminal_instruments"] == 68
    assert qa["terminal_instrument_coverage"] == 1.0

    j0 = json.loads((ROOT / "trackj/J0_DATA_GAP_ANALYSIS.json").read_text())
    assert j0["target_read"] is False
    assert j0["model_code_imported"] is False
    assert j0["stop_before_external_fetch"] is True
    closure = json.loads((ROOT / "research_i/RESEARCH_I_COMPLETE.json").read_text())
    assert closure["status"] == "SLUTFÖRT"
    assert closure["remaining_after_batch3"] == 0
    assert closure["batch4_allowed"] is False

    print(json.dumps({
        "status": "PASS",
        "ohlc_manifest_sha256": sha256(manifest_path),
        "ohlc_aggregate_sha256": aggregate,
        "files": len(actual),
        "rows": qa["counts"]["validated_rows"],
        "instruments": qa["instruments"],
        "terminal_instruments": qa["terminal_instruments"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
