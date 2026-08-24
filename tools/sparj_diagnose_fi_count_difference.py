#!/usr/bin/env python3
"""Diagnose FI export-row versus official result-count differences."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    run = ROOT / "trackj/fi" / args.run_id
    fingerprints = Counter()
    examples = defaultdict(list)
    rows = 0
    schemas = Counter()
    for path in sorted((run / "raw").glob("*.export.csv")):
        payload = path.read_bytes()
        text = payload.decode("utf-16") if payload.startswith(b"\xff\xfe") else payload.decode("utf-16le")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        schemas[tuple(reader.fieldnames or [])] += 1
        for line_number, row in enumerate(reader, 2):
            rows += 1
            canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fp = hashlib.sha256(canonical.encode()).hexdigest()
            fingerprints[fp] += 1
            if len(examples[fp]) < 4:
                examples[fp].append({"path": str(path.relative_to(ROOT)), "line": line_number, "row": row})
    dupes = {fp: count for fp, count in fingerprints.items() if count > 1}
    result = {
        "run_id": args.run_id,
        "export_files": sum(schemas.values()),
        "raw_rows": rows,
        "unique_exact_rows": len(fingerprints),
        "duplicate_excess_rows": sum(n - 1 for n in dupes.values()),
        "duplicate_groups": len(dupes),
        "schema_variants": [{"fields": list(k), "files": v} for k, v in schemas.items()],
        "duplicates": [{"fingerprint": fp, "count": n, "examples": examples[fp]} for fp, n in dupes.items()],
    }
    out = run / "COUNT_DIAGNOSTIC.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "duplicates"}, ensure_ascii=False, indent=2))
    print(json.dumps(result["duplicates"], ensure_ascii=False, indent=2)[:12000])


if __name__ == "__main__":
    main()
