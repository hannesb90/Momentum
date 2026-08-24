#!/usr/bin/env python3
"""Immutable, complete FI insider snapshot by publication-date windows.

The official UTF-16LE export contains second-resolution publication time and
correction/status fields.  A verbatim HTML count response is stored beside
every verbatim export and the two row counts must agree.  No V2 universe,
target, feature, or model data is sent to FI or used to shape the snapshot.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
URL = "https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search"
UA = "Mozilla/5.0 (Momentum V2 immutable FI data foundation; research)"
COUNT_RE = re.compile(rb'av\s*<span class="badge badge-info">\s*([0-9 ]+)\s*</span>')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(session: requests.Session, params: dict[str, str]) -> tuple[bytes, dict]:
    last = None
    for attempt in range(7):
        started = datetime.now(timezone.utc)
        try:
            response = session.get(URL, params=params, timeout=30)
            finished = datetime.now(timezone.utc)
            response.raise_for_status()
            payload = response.content
            return payload, {
                "endpoint": URL,
                "request_params": params,
                "retrieved_at_utc": finished.isoformat(),
                "elapsed_seconds": (finished - started).total_seconds(),
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "response_bytes": len(payload),
                "response_sha256": sha(payload),
            }
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"FI request failed: {params}: {last}")


def exported_rows(payload: bytes) -> int:
    if not payload.startswith((b"\xff\xfe", b"P\x00u\x00")):
        raise RuntimeError("FI export is not the expected UTF-16LE table")
    text = payload.decode("utf-16") if payload.startswith(b"\xff\xfe") else payload.decode("utf-16le")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames or reader.fieldnames[0] != "Publiceringsdatum":
        raise RuntimeError("unexpected FI export schema")
    # CSV fields may legally contain embedded newlines. Counting physical text
    # lines overstated the 2020--2026 snapshot by two; parsed records are the
    # only valid unit for the official result-count comparison.
    return sum(1 for _ in reader)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--from-date", default="2020-01-01")
    ap.add_argument("--to-date", default=date.today().isoformat())
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--pause", type=float, default=0.08)
    args = ap.parse_args()
    run = ROOT / "trackj/fi" / args.run_id
    raw = run / "raw"
    if (run / "summary.json").exists():
        raise RuntimeError(f"completed run exists (append-only): {run}")
    raw.mkdir(parents=True, exist_ok=True)
    # An advisory run lock makes concurrent resume attempts fail immediately.
    # This is deliberately held for the complete process lifetime.
    lock_fh = (run / ".fetch.lock").open("a+b")
    try:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"FI run already has an active writer: {run}") from exc
    journal_path = run / "_request_journal.jsonl"
    journal = [json.loads(x) for x in journal_path.read_text().splitlines()] if journal_path.exists() else []
    journal_keys = [(x["window_from"], x["window_to"], x["kind"]) for x in journal]
    if len(journal_keys) != len(set(journal_keys)):
        raise RuntimeError(f"duplicate request keys in append-only FI journal: {run}")
    completed = {(x["window_from"], x["window_to"], x["kind"]): x for x in journal}
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "*/*", "Connection": "close"})
    first, final = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    cursor = first
    windows = []
    while cursor <= final:
        end = min(final, cursor + timedelta(days=args.window_days - 1))
        windows.append((cursor, end)); cursor = end + timedelta(days=1)

    # One official count for the complete requested period is the completeness
    # oracle.  Comparing it with the sum of disjoint exports avoids doubling
    # the request load (FI resets connections under aggressive polling).
    global_key = (args.from_date, args.to_date, "global_search_count_html")
    global_row = completed.get(global_key)
    if global_row:
        global_count = global_row["record_count"]
    else:
        global_params = {"SearchFunctionType": "Insyn", "Publiceringsdatum.From": args.from_date,
                         "Publiceringsdatum.To": args.to_date, "button": "search"}
        payload, meta = get(session, global_params)
        match = COUNT_RE.search(payload)
        if not match:
            raise RuntimeError("official FI global count not found")
        global_count = int(match.group(1).replace(b" ", b""))
        path = raw / f"{args.from_date}_{args.to_date}.global.search.html"
        path.write_bytes(payload)
        global_row = {**meta, "kind": "global_search_count_html", "window_from": args.from_date,
                      "window_to": args.to_date, "record_count": global_count,
                      "path": str(path.relative_to(ROOT))}
        with journal_path.open("ab") as fh:
            fh.write((json.dumps(global_row, sort_keys=True) + "\n").encode())

    total = 0
    for number, (start, end) in enumerate(windows, 1):
        common = {
            "SearchFunctionType": "Insyn",
            "Publiceringsdatum.From": start.isoformat(),
            "Publiceringsdatum.To": end.isoformat(),
        }
        key = (start.isoformat(), end.isoformat())
        export_row = completed.get((*key, "utf16le_export"))
        if export_row:
            rows = export_row["record_count"]
        else:
            payload, meta = get(session, {**common, "button": "export"})
            rows = exported_rows(payload)
            path = raw / f"{start}_{end}.export.csv"
            path.write_bytes(payload)
            export_row = {**meta, "kind": "utf16le_export", "window_from": key[0],
                          "window_to": key[1], "record_count": rows,
                          "path": str(path.relative_to(ROOT)),
                          "schema_version": "FI_INSIDER_EXPORT_22_COLUMNS_2026-08-09"}
            with journal_path.open("ab") as fh:
                fh.write((json.dumps(export_row, sort_keys=True) + "\n").encode())
        # Weekly counts observed in the already stored count pages remain useful
        # local assertions, but are not required for every new week.
        search_row = completed.get((*key, "search_count_html"))
        if search_row and search_row["record_count"] != rows:
            raise RuntimeError(f"FI local completeness mismatch {key}: search={search_row['record_count']}, export={rows}")
        total += rows
        if number % 25 == 0 or number == len(windows):
            print(f"FI {number}/{len(windows)} windows; {total} records", flush=True)
        time.sleep(args.pause)

    if total != global_count:
        raise RuntimeError(f"FI global completeness mismatch: exports={total}, official_count={global_count}")
    manifest_bytes = journal_path.read_bytes()
    (run / "manifest.jsonl").write_bytes(manifest_bytes)
    summary = {
        "version": "FI_OFFICIAL_IMMUTABLE_RAW_V1",
        "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Finansinspektionen public insider registry",
        "source_url": URL,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "windows": len(windows),
        "requests": len((run / "_request_journal.jsonl").read_text().splitlines()),
        "records": total,
        "official_global_record_count": global_count,
        "completeness_rule": "sum of disjoint weekly official exports equals official HTML result count for full period",
        "market_known_time_field": "Publiceringsdatum (second resolution in official export)",
        "manifest_sha256": sha(manifest_bytes),
        "target_feature_model_data_read": False,
    }
    (run / "summary.json").write_bytes((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
