#!/usr/bin/env python3
"""Seed a clean one-writer FI run from previously received verbatim bytes.

The source request journals remain immutable.  A response is admitted only when
its currently stored bytes match the response SHA recorded for that exact
request key.  Duplicate source journal rows are therefore neither copied nor
silently resolved by ordering.  Missing windows must subsequently be fetched by
the normal locked fetcher, whose global-count equality remains the final gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-run", action="append", required=True)
    ap.add_argument("--dest-run", required=True)
    args = ap.parse_args()
    dest = ROOT / "trackj/fi" / args.dest_run
    if dest.exists():
        raise RuntimeError(f"destination already exists: {dest}")
    raw_dest = dest / "raw"
    raw_dest.mkdir(parents=True)

    admitted: dict[tuple[str, str, str], dict] = {}
    conflicts: set[tuple[str, str, str]] = set()
    for run_id in args.source_run:
        source = ROOT / "trackj/fi" / run_id
        journal = source / "_request_journal.jsonl"
        for line in journal.read_text().splitlines():
            row = json.loads(line)
            key = (row["window_from"], row["window_to"], row["kind"])
            source_path = ROOT / row["path"]
            if not source_path.exists() or sha(source_path) != row["response_sha256"]:
                continue
            prior = admitted.get(key)
            if prior and prior["response_sha256"] != row["response_sha256"]:
                conflicts.add(key)
                admitted.pop(key, None)
                continue
            if key not in conflicts:
                copied = dict(row)
                copied["recovered_from_run"] = run_id
                copied["recovery_rule"] = "stored verbatim bytes match recorded response_sha256"
                target = raw_dest / source_path.name
                shutil.copyfile(source_path, target)
                copied["path"] = str(target.relative_to(ROOT))
                admitted[key] = copied

    rows = [admitted[key] for key in sorted(admitted)]
    journal_dest = dest / "_request_journal.jsonl"
    journal_dest.write_bytes(b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in rows))
    evidence = {
        "version": "FI_VERBATIM_RECOVERY_SEED_V1",
        "source_runs": args.source_run,
        "destination_run": args.dest_run,
        "admitted_unique_request_keys": len(rows),
        "admitted_export_windows": sum(r["kind"] == "utf16le_export" for r in rows),
        "conflicting_request_keys_excluded": [list(x) for x in sorted(conflicts)],
        "final_acceptance": "NOT COMPLETE: normal locked fetcher plus official global-count equality required",
    }
    (dest / "RECOVERY_EVIDENCE.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
