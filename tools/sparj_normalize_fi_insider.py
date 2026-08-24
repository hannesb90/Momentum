#!/usr/bin/env python3
"""Normalize official immutable FI exports using exact ISIN identity only."""

from __future__ import annotations

import csv
import argparse
import hashlib
import io
import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from sparj_fetch_mfn_immutable import frozen_universe


ROOT = Path(__file__).resolve().parents[1]
STOCKHOLM = ZoneInfo("Europe/Stockholm")
UTC = ZoneInfo("UTC")
def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def number(value: str) -> str | None:
    value = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not value:
        return None
    try:
        return format(Decimal(value), "f")
    except InvalidOperation:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", default="trackj/validated_fi_insider_v1")
    args = ap.parse_args()
    run = ROOT / "trackj/fi" / args.run_id
    out_dir = ROOT / args.out
    if out_dir.exists():
        raise RuntimeError("validated FI output exists; immutable build refuses overwrite")
    if not (run / "summary.json").exists():
        raise RuntimeError("FI RAW run is not complete")
    out_dir.mkdir(parents=True)
    identities = {row["isin"]: row for row in frozen_universe()}
    terminal_events = json.loads((ROOT / "validated/terminal_events.json").read_text())
    terminal = set(terminal_events)
    manifest = [json.loads(x) for x in (run / "manifest.jsonl").read_text().splitlines()]
    raw_meta = {row["path"]: row for row in manifest if row["kind"] == "utf16le_export"}
    output = out_dir / "validated_fi_insider.jsonl"
    exclusions = Counter(); coverage = defaultdict(lambda: {"events": 0, "instruments": set(), "active": set(), "terminal": set()})
    seen = set(); duplicates = 0; included = 0; scanned = 0; status = Counter(); character = Counter()
    with output.open("wb") as dst:
        for rel, meta in sorted(raw_meta.items()):
            payload = (ROOT / rel).read_bytes()
            if sha(payload) != meta["response_sha256"]:
                raise RuntimeError(f"RAW hash mismatch: {rel}")
            text = payload.decode("utf-16") if payload.startswith(b"\xff\xfe") else payload.decode("utf-16le")
            for source_row_number, row in enumerate(csv.DictReader(io.StringIO(text), delimiter=";"), 2):
                scanned += 1
                isin = (row.get("ISIN") or "").strip().upper()
                if isin not in identities:
                    exclusions["ISIN_NOT_IN_FROZEN_V2_IDENTITY_SET"] += 1; continue
                published = (row.get("Publiceringsdatum") or "").strip()
                try:
                    published_local = datetime.strptime(published, "%Y-%m-%d %H:%M:%S").replace(tzinfo=STOCKHOLM)
                except ValueError:
                    exclusions["MISSING_OR_INVALID_SECOND_RESOLUTION_PUBLICATION_TIME"] += 1; continue
                identity = identities[isin]
                code = identity["instrument_id"]
                terminal_date = terminal_events.get(code, {}).get("event_date")
                if terminal_date and published[:10] > terminal_date:
                    exclusions["MARKET_KNOWN_AFTER_VERIFIED_TERMINAL_DATE"] += 1
                    continue
                canonical = {key: (value or "").strip() for key, value in row.items() if key is not None}
                fingerprint = sha(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode())
                if fingerprint in seen:
                    duplicates += 1; continue
                seen.add(fingerprint)
                record = {
                    "instrument_id": code, "isin": isin,
                    "source_id": "fi_export_sha256:" + fingerprint,
                    "fi_source_record_id": None,
                    "source_record_fingerprint_sha256": fingerprint,
                    "source_id_status": "OFFICIAL_EXPORT_DOES_NOT_EXPOSE_REPORT_ID",
                    "issuer": canonical.get("Emittent"), "issuer_lei": canonical.get("LEI-kod"),
                    "reporting_person": canonical.get("Anmälningsskyldig"),
                    "person_in_leading_position": canonical.get("Person i ledande ställning"),
                    "role": canonical.get("Befattning"), "related_party": canonical.get("Närstående"),
                    "transaction_character": canonical.get("Karaktär"),
                    "instrument_type": canonical.get("Instrumenttyp"), "instrument_name": canonical.get("Instrumentnamn"),
                    "transaction_date": (canonical.get("Transaktionsdatum") or "")[:10] or None,
                    "quantity": number(canonical.get("Volym", "")), "quantity_unit": canonical.get("Volymsenhet"),
                    "price": number(canonical.get("Pris", "")), "currency": canonical.get("Valuta"),
                    "trading_venue": canonical.get("Handelsplats"),
                    "published_at_source_local": published,
                    "published_at_source_timezone": "Europe/Stockholm",
                    "market_known_time": published_local.astimezone(UTC).isoformat(),
                    "market_known_time_basis": "FI_OFFICIAL_PUBLICATION_TIMESTAMP_SECOND_RESOLUTION_INTERPRETED_EUROPE_STOCKHOLM_AND_NORMALIZED_UTC",
                    "correction_flag": canonical.get("Korrigering"),
                    "correction_description": canonical.get("Beskrivning av korrigering"),
                    "first_reporting_flag": canonical.get("Är förstagångsrapportering"),
                    "equity_program_flag": canonical.get("Är kopplad till aktieprogram"),
                    "source_status": canonical.get("Status"),
                    "mapping_status": "VERIFIED_EXACT_ISIN",
                    "inclusion_reason": "exact V2 ISIN and explicit official publication timestamp",
                    "raw_path": rel, "raw_sha256": meta["response_sha256"], "raw_row_number": source_row_number,
                    "is_terminal_instrument": code in terminal,
                    "terminal_event_date": terminal_date,
                    "pre_terminal_event": terminal_date is None or published[:10] <= terminal_date,
                }
                dst.write((json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode())
                included += 1; status[record["source_status"]] += 1; character[record["transaction_character"]] += 1
                year = published[:4]; c = coverage[year]; c["events"] += 1; c["instruments"].add(code)
                c["terminal" if code in terminal else "active"].add(code)
    out_bytes = output.read_bytes()
    annual = {str(year): {"events": coverage[str(year)]["events"],
                          "instruments": len(coverage[str(year)]["instruments"]),
                          "active_instruments": len(coverage[str(year)]["active"]),
                          "terminal_instruments": len(coverage[str(year)]["terminal"])}
              for year in range(2020, 2027)}
    all_instruments = set().union(*(coverage[str(y)]["instruments"] for y in range(2020, 2027)))
    all_terminal = set().union(*(coverage[str(y)]["terminal"] for y in range(2020, 2027)))
    summary = {
        "version": "VALIDATED_FI_INSIDER_V2_TIMEZONE_SAFE", "created_at": datetime.now().astimezone().isoformat(),
        "raw_run_id": args.run_id,
        "raw_manifest_sha256": sha((run / "manifest.jsonl").read_bytes()),
        "raw_records_scanned": scanned, "validated_rows": included, "duplicates_removed": duplicates,
        "exclusions": dict(exclusions), "source_status": dict(status),
        "transaction_character_counts": dict(character), "coverage_per_year": annual,
        "coverage": {"instruments": len(all_instruments),
                     "active_instruments": len(all_instruments - terminal),
                     "terminal_instruments": len(all_terminal),
                     "terminal_universe": 68},
        "identity_rule": "exact ISIN only; no ticker or fuzzy-name mapping",
        "market_known_time_rule": "official FI Publiceringsdatum at second resolution in Europe/Stockholm, normalized to UTC; no transaction-date substitution",
        "validated_sha256": sha(out_bytes), "target_feature_model_data_read": False,
    }
    sb = (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    (out_dir / "qa_summary.json").write_bytes(sb)
    mf = {"version": summary["version"], "files": [
        {"path": str(output.relative_to(ROOT)), "sha256": sha(out_bytes), "rows": included},
        {"path": str((out_dir / "qa_summary.json").relative_to(ROOT)), "sha256": sha(sb)},
    ]}
    mb = (json.dumps(mf, indent=2, sort_keys=True) + "\n").encode()
    (out_dir / "manifest.json").write_bytes(mb)
    print(json.dumps({**summary, "manifest_sha256": sha(mb)}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
