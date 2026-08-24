#!/usr/bin/env python3
"""Normalize immutable MFN RAW with exact entity routing; no targets/features."""

from __future__ import annotations

import glob
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z"
OUT = ROOT / "trackj/validated_mfn_events_v1"
START = "2020-01-01"
REPORT_RE = re.compile(r"\b(q[1-4]|kvartalsrapport|delårsrapport|interim report|bokslutskommunik|year[- ]end report|årsredovisning|annual report|trading update)\b", re.I)
DIV_RE = re.compile(r"\b(utdelning|vinstutdelning|extrautdelning|dividend|distribution to shareholders)\b", re.I)
BUYBACK_RE = re.compile(r"\b(återköp|återköpsprogram|egna aktier|share buy-?back|repurchase|treasury shares)\b", re.I)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report_subtype(tags: list[str], title: str) -> str | None:
    joined = " ".join(tags).lower()
    for q in ("q1", "q2", "q3", "q4"):
        if f"sub:report:interim:{q}" in joined or re.search(rf"\b{q}\b", title, re.I):
            return q.upper()
    if "sub:report:annual" in tags or re.search(r"årsredovisning|annual report", title, re.I):
        return "ANNUAL_REPORT"
    if re.search(r"bokslutskommunik|year[- ]end report", title, re.I):
        return "YEAR_END"
    if re.search(r"trading update", title, re.I):
        return "TRADING_UPDATE"
    if "sub:report:interim" in tags or re.search(r"kvartalsrapport|delårsrapport|interim report", title, re.I):
        return "INTERIM_UNRESOLVED_PERIOD"
    return None


def dividend_subtype(text: str) -> str:
    if re.search(r"indragen|withdrawn|slopad|ingen utdelning", text, re.I): return "WITHDRAWN_OR_ZERO"
    if re.search(r"ändrat förslag|reviderat förslag|revised proposal", text, re.I): return "CHANGED_PROPOSAL"
    if re.search(r"extrautdelning|extraordinary dividend|special dividend", text, re.I): return "SPECIAL_DIVIDEND"
    if re.search(r"styrelsen föreslår|föreslår.*utdelning|board proposes|proposed dividend", text, re.I): return "BOARD_PROPOSAL"
    if re.search(r"stämman beslut|årsstämman beslut|agm resolved|general meeting resolved", text, re.I): return "AGM_DECISION"
    if re.search(r"x-dag|ex[- ]date|avstämningsdag", text, re.I): return "EX_DATE_INFORMATION"
    return "UNRESOLVED_DIVIDEND_SEMANTICS"


def buyback_subtype(text: str) -> str:
    if re.search(r"försäljning av egna aktier|sale of treasury shares", text, re.I): return "TREASURY_SHARE_SALE"
    if re.search(r"avslut|slutfört|completed|terminated", text, re.I): return "PROGRAM_ENDED"
    if re.search(r"mandat|bemyndigande|authori[sz]ation", text, re.I): return "MANDATE"
    if re.search(r"under perioden|vecka\s+\d+|weekly|during the period", text, re.I): return "EXECUTED_PERIODIC"
    if re.search(r"inleder|beslutat.*återköpsprogram|launch|initiates|program", text, re.I): return "PROGRAM_ANNOUNCED"
    return "UNRESOLVED_BUYBACK_SEMANTICS"


def main():
    if OUT.exists():
        raise RuntimeError("validated output exists; immutable build refuses overwrite")
    OUT.mkdir(parents=True)
    routing = json.loads((RUN / "identity_routing.json").read_text())
    entity_map = defaultdict(dict)
    for route in routing["routes"]:
        for identity in route["v2_identities"]:
            entity_map[route["entity_id"]][identity["instrument_id"]] = identity
    terminal = set(json.loads((ROOT / "validated/terminal_events.json").read_text()))
    manifest_rows = {r["path"]: r for r in map(json.loads, (RUN / "manifest.jsonl").read_text().splitlines())}
    seen = set()
    unique_event_ids = set()
    validated_rows = 0
    cov = {family: {"events": 0, "instruments": set(), "active": set(), "terminal": set(),
                    "year_events": Counter(), "year_instruments": defaultdict(set)}
           for family in ("ANY", "REPORT", "DIVIDEND_ANNOUNCEMENT_CANDIDATE", "BUYBACK_ANNOUNCEMENT")}
    exclusion = Counter()
    duplicate_pairs = 0
    raw_items = 0
    tmp = tempfile.NamedTemporaryFile(prefix="mfn_validated_", suffix=".jsonl", delete=False)
    tmp_path = Path(tmp.name)
    try:
      for filename in sorted(glob.glob(str(RUN / "raw/*/*/*.json"))):
        path = Path(filename); rel = str(path.relative_to(ROOT)); raw_meta = manifest_rows[rel]
        expected_entity = path.parts[-3]; data = json.loads(path.read_bytes())
        for item in data.get("items") or []:
            raw_items += 1
            author = item.get("author") or {}
            content = item.get("content") or {}
            event_id = item.get("news_id") or item.get("group_id")
            published = content.get("publish_date")
            if author.get("entity_id") != expected_entity:
                exclusion["AUTHOR_ENTITY_MISMATCH"] += 1; continue
            if not event_id or not published:
                exclusion["MISSING_EVENT_ID_OR_TIMESTAMP"] += 1; continue
            if published[:10] < START:
                exclusion["BEFORE_2020"] += 1; continue
            if not published.endswith("Z"):
                exclusion["TIMESTAMP_NOT_EXPLICIT_UTC"] += 1; continue
            try: datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                exclusion["INVALID_TIMESTAMP"] += 1; continue
            tags = list((item.get("properties") or {}).get("tags") or [])
            title = str(content.get("title") or "")
            body = " ".join((title, str(content.get("preamble") or ""), str(content.get("text") or "")[:4000]))
            provider_report = any(t == "sub:report" or t.startswith("sub:report:") for t in tags)
            families = []
            if provider_report or REPORT_RE.search(title): families.append("REPORT")
            if DIV_RE.search(body): families.append("DIVIDEND_ANNOUNCEMENT_CANDIDATE")
            if "sub:ca:shares:repurchase" in tags or BUYBACK_RE.search(body): families.append("BUYBACK_ANNOUNCEMENT")
            for instrument_id, identity in entity_map[expected_entity].items():
                key = (str(event_id), instrument_id)
                if key in seen:
                    duplicate_pairs += 1; continue
                seen.add(key)
                row = {
                    "instrument_id": instrument_id, "isin": identity["isin"],
                    "event_id": str(event_id), "group_id": item.get("group_id"),
                    "published_at": published, "market_known_time": published,
                    "market_known_time_basis": "MFN_CONTENT_PUBLISH_DATE_EXPLICIT_UTC",
                    "provider_event_type": (item.get("properties") or {}).get("type"),
                    "provider_tags": tags, "derived_event_families": families,
                    "report_subtype": report_subtype(tags, title) if "REPORT" in families else None,
                    "report_classification_basis": "MFN_PROVIDER_TAG" if provider_report else ("TITLE_RULE_CANDIDATE" if "REPORT" in families else None),
                    "dividend_subtype": dividend_subtype(body) if "DIVIDEND_ANNOUNCEMENT_CANDIDATE" in families else None,
                    "dividend_semantics_validated": False,
                    "buyback_subtype": buyback_subtype(body) if "BUYBACK_ANNOUNCEMENT" in families else None,
                    "headline": title, "source": "MFN", "source_reference": item.get("url"),
                    "retrieved_at": raw_meta["retrieved_at_utc"],
                    "mapping_status": "VERIFIED_EXACT_ISIN_TO_MFN_ENTITY",
                    "inclusion_reason": "exact entity route and explicit UTC publish timestamp",
                    "raw_path": rel, "raw_sha256": raw_meta["response_sha256"],
                    "is_terminal_instrument": instrument_id in terminal,
                }
                tmp.write((json.dumps(row, sort_keys=True) + "\n").encode())
                validated_rows += 1; unique_event_ids.add(row["event_id"])
                year = int(row["published_at"][:4])
                for family in ["ANY", *families]:
                    c = cov[family]; c["events"] += 1; c["instruments"].add(instrument_id)
                    c["terminal" if row["is_terminal_instrument"] else "active"].add(instrument_id)
                    if 2020 <= year <= 2026:
                        c["year_events"][year] += 1; c["year_instruments"][year].add(instrument_id)
      tmp.flush(); tmp.close()
      out_path = OUT / "validated_mfn_events.jsonl"
      tmp_path.replace(out_path)
    except Exception:
      tmp.close(); tmp_path.unlink(missing_ok=True); raise
    jsonl_sha = hashlib.sha256()
    with (OUT / "validated_mfn_events.jsonl").open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): jsonl_sha.update(chunk)
    coverage = {}
    for family in ("ANY", "REPORT", "DIVIDEND_ANNOUNCEMENT_CANDIDATE", "BUYBACK_ANNOUNCEMENT"):
        c = cov[family]
        coverage[family] = {
            "events": c["events"], "instruments": len(c["instruments"]),
            "active_instruments": len(c["active"]), "terminal_instruments": len(c["terminal"]),
            "per_year": {str(y): {"events": c["year_events"][y], "instruments": len(c["year_instruments"][y])}
                         for y in range(2020, 2027)},
        }
    summary = {
        "version": "VALIDATED_MFN_EVENTS_V1", "created_at_utc": datetime.now().astimezone().isoformat(),
        "raw_manifest_sha256": sha((RUN / "manifest.jsonl").read_bytes()),
        "routing_sha256": sha((RUN / "identity_routing.json").read_bytes()),
        "raw_items_scanned": raw_items, "validated_instrument_event_rows": validated_rows,
        "unique_event_ids": len(unique_event_ids),
        "duplicate_instrument_event_pairs_removed": duplicate_pairs,
        "exclusions": dict(exclusion), "coverage": coverage,
        "validated_sha256": jsonl_sha.hexdigest(), "target_feature_model_data_read": False,
        "important_scope": "Dividend rows are candidates, not semantically validated announcements.",
    }
    summary_bytes = (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode()
    (OUT / "qa_summary.json").write_bytes(summary_bytes)
    manifest = {"files": [
        {"path": str((OUT / "validated_mfn_events.jsonl").relative_to(ROOT)), "sha256": jsonl_sha.hexdigest(), "rows": validated_rows},
        {"path": str((OUT / "qa_summary.json").relative_to(ROOT)), "sha256": sha(summary_bytes)},
    ]}
    mb = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (OUT / "manifest.json").write_bytes(mb)
    print(json.dumps({**summary, "manifest_sha256": sha(mb)}, indent=2, sort_keys=True))


if __name__ == "__main__": main()
