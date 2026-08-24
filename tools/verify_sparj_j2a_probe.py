#!/usr/bin/env python3
"""Fail-fast byte verification for the J2A Börsdata probe snapshot."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "trackj/j2a_borsdata_api_probe/raw/J2A_PROBE_2026-08-09T120000Z"


def main() -> None:
    manifest = RUN / "manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text().splitlines() if line]
    for row in rows:
        path = ROOT / row["path"]
        if not path.is_file():
            raise SystemExit(f"MISSING {path}")
        data = path.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != row["sha256"] or len(data) != row["bytes"]:
            raise SystemExit(f"MISMATCH {path}")
    expected = json.loads((RUN / "summary.json").read_text())["manifest_sha256"]
    got_manifest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if got_manifest != expected:
        raise SystemExit("MANIFEST MISMATCH")
    print(f"PASS {len(rows)}/{len(rows)} files; manifest_sha256={got_manifest}")


if __name__ == "__main__":
    main()
