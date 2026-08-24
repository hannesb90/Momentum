#!/usr/bin/env python3
"""One-writer immutable FI snapshot with bounded concurrent HTTP retrieval.

Each task writes one disjoint seven-day response.  Only the parent process
creates the sorted manifest, after every response has passed schema/row checks.
The official full-period count remains the hard completeness oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from sparj_fetch_fi_immutable import COUNT_RE, URL, exported_rows, get


ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Momentum V2 immutable FI data foundation; research)"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_window(run: Path, start: date, end: date) -> dict:
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "*/*", "Connection": "close"})
    payload, meta = get(session, {
        "SearchFunctionType": "Insyn", "Publiceringsdatum.From": start.isoformat(),
        "Publiceringsdatum.To": end.isoformat(), "button": "export",
    })
    rows = exported_rows(payload)
    path = run / "raw" / f"{start}_{end}.export.csv"
    path.write_bytes(payload)
    row = {**meta, "kind": "utf16le_export", "window_from": start.isoformat(),
            "window_to": end.isoformat(), "record_count": rows,
            "path": str(path.relative_to(ROOT)),
            "schema_version": "FI_INSIDER_EXPORT_22_COLUMNS_2026-08-09"}
    # Sidecar provenance is written by the same worker immediately after the
    # verbatim response, so an interrupted attempt never relies on file mtime.
    path.with_suffix(path.suffix + ".request.json").write_text(
        json.dumps(row, indent=2, sort_keys=True) + "\n"
    )
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from-date", default="2020-01-01")
    ap.add_argument("--to-date", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    run = ROOT / "trackj/fi" / args.run_id
    if run.exists():
        raise RuntimeError(f"immutable destination exists: {run}")
    (run / "raw").mkdir(parents=True)

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "*/*", "Connection": "close"})
    params = {"SearchFunctionType": "Insyn", "Publiceringsdatum.From": args.from_date,
              "Publiceringsdatum.To": args.to_date, "button": "search"}
    count_payload, count_meta = get(session, params)
    match = COUNT_RE.search(count_payload)
    if not match:
        raise RuntimeError("official FI global count not found")
    global_count = int(match.group(1).replace(b" ", b""))
    count_path = run / "raw" / f"{args.from_date}_{args.to_date}.global.search.html"
    count_path.write_bytes(count_payload)
    count_row = {**count_meta, "kind": "global_search_count_html", "window_from": args.from_date,
                 "window_to": args.to_date, "record_count": global_count,
                 "path": str(count_path.relative_to(ROOT))}

    windows = []
    cursor, final = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    while cursor <= final:
        end = min(final, cursor + timedelta(days=6))
        windows.append((cursor, end)); cursor = end + timedelta(days=1)
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_window, run, a, b): (a, b) for a, b in windows}
        for n, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if n % 25 == 0 or n == len(windows):
                print(f"FI received {n}/{len(windows)} windows", flush=True)
    rows.sort(key=lambda r: (r["window_from"], r["window_to"]))
    total = sum(r["record_count"] for r in rows)
    if total != global_count:
        raise RuntimeError(f"FI global completeness mismatch: exports={total}, official_count={global_count}")
    manifest_rows = [count_row, *rows]
    manifest_bytes = b"".join((json.dumps(r, sort_keys=True) + "\n").encode() for r in manifest_rows)
    (run / "_request_journal.jsonl").write_bytes(manifest_bytes)
    (run / "manifest.jsonl").write_bytes(manifest_bytes)
    summary = {
        "version": "FI_OFFICIAL_IMMUTABLE_RAW_V2", "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Finansinspektionen public insider registry", "source_url": URL,
        "from_date": args.from_date, "to_date": args.to_date,
        "windows": len(windows), "requests": len(manifest_rows), "records": total,
        "official_global_record_count": global_count,
        "completeness_rule": "sum of disjoint 7-day official exports equals official full-period HTML count",
        "retrieval_architecture": f"one manifest writer; {args.workers} bounded HTTP workers; disjoint paths",
        "market_known_time_field": "Publiceringsdatum (second resolution in official export)",
        "manifest_sha256": sha(manifest_bytes), "target_feature_model_data_read": False,
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
