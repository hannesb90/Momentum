#!/usr/bin/env python3
"""Fetch MFN author feeds routed only by exact ISIN/entity evidence from discovery RAW."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "trackj/mfn/MFN_V2_20260809T130000Z"
UA = "Mozilla/5.0 (Momentum V2 immutable data foundation; research)"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def routing() -> tuple[list[dict], list[dict]]:
    universe = {r["isin"]: r for r in json.loads((DISCOVERY / "universe.json").read_text())}
    routes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for filename in glob.glob(str(DISCOVERY / "raw/*/*.json")):
        query_isin = Path(filename).parent.name
        data = json.loads(Path(filename).read_bytes())
        for item in data.get("items") or []:
            entities = [item.get("author") or {}, *(item.get("subjects") or [])]
            for entity in entities:
                if query_isin in (entity.get("isins") or []) and entity.get("entity_id") and entity.get("slug"):
                    routes[(entity["entity_id"], entity["slug"])].add(query_isin)
    route_rows = [{
        "entity_id": entity_id,
        "slug": slug,
        "v2_identities": [universe[i] for i in sorted(isins)],
        "mapping_status": "VERIFIED_EXACT_ISIN_IN_MFN_ENTITY",
    } for (entity_id, slug), isins in sorted(routes.items())]
    resolved = {identity["isin"] for route in route_rows for identity in route["v2_identities"]}
    unresolved = [{**identity, "mapping_status": "UNRESOLVED_NO_EXACT_MFN_ENTITY"}
                  for isin, identity in sorted(universe.items()) if isin not in resolved]
    return route_rows, unresolved


def get(session, url, params):
    last = None
    for attempt in range(5):
        started = datetime.now(timezone.utc)
        try:
            response = session.get(url, params=params, timeout=90)
            finished = datetime.now(timezone.utc)
            response.raise_for_status()
            payload = response.content
            parsed = json.loads(payload)
            return payload, parsed, {
                "request_url": url, "request_params": params or {},
                "retrieved_at_utc": finished.isoformat(), "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "elapsed_seconds": (finished - started).total_seconds(),
                "response_bytes": len(payload), "response_sha256": sha(payload),
                "schema_version": parsed.get("version"),
            }
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed {url}: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--start-date", default="2020-01-01")
    args = ap.parse_args()
    run = ROOT / "trackj/mfn" / args.run_id
    if run.exists():
        raise RuntimeError("append-only run-id exists")
    raw = run / "raw"
    raw.mkdir(parents=True)
    routes, unresolved = routing()
    routing_bytes = (json.dumps({"routes": routes, "unresolved": unresolved}, indent=2, sort_keys=True) + "\n").encode()
    (run / "identity_routing.json").write_bytes(routing_bytes)
    manifest = []
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    for idx, route in enumerate(routes):
        entity_id, slug = route["entity_id"], route["slug"]
        url, params = f"https://mfn.se/all/a/{slug}", {"lang": "sv", "limit": "500"}
        seen = set()
        for page_no in range(100):
            key = url + json.dumps(params or {}, sort_keys=True)
            if key in seen:
                raise RuntimeError(f"pagination loop {slug}")
            seen.add(key)
            payload, parsed, meta = get(session, url, params)
            path = raw / entity_id / slug / f"page_{page_no:03d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            items = parsed.get("items") or []
            dates = [((x.get("content") or {}).get("publish_date") or "") for x in items]
            dates = [d for d in dates if d]
            row = {**meta, "entity_id": entity_id, "slug": slug, "page": page_no,
                   "item_count": len(items), "oldest_published_at": min(dates) if dates else None,
                   "newest_published_at": max(dates) if dates else None,
                   "next_url_present": bool(parsed.get("next_url")),
                   "path": str(path.relative_to(ROOT))}
            manifest.append(row)
            if not items or not parsed.get("next_url") or (dates and min(dates)[:10] < args.start_date):
                break
            nxt = urlparse(parsed["next_url"])
            url = f"{nxt.scheme}://{nxt.netloc}{nxt.path}"
            params = dict(parse_qsl(nxt.query, keep_blank_values=True))
            time.sleep(0.12)
        if (idx + 1) % 25 == 0:
            print(f"MFN author routes {idx + 1}/{len(routes)}, pages={len(manifest)}", flush=True)
    manifest_bytes = ("\n".join(json.dumps(r, sort_keys=True) for r in manifest) + "\n").encode()
    (run / "manifest.jsonl").write_bytes(manifest_bytes)
    terminal = set(json.loads((ROOT / "validated/terminal_events.json").read_text()))
    resolved_codes = {x["instrument_id"] for r in routes for x in r["v2_identities"]}
    summary = {
        "run_id": args.run_id, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "MFN author JSON feeds", "discovery_manifest_sha256": sha((DISCOVERY / "manifest.jsonl").read_bytes()),
        "routes": len(routes), "pages": len(manifest), "raw_bytes": sum(r["response_bytes"] for r in manifest),
        "resolved_instruments": len(resolved_codes), "resolved_terminal": len(resolved_codes & terminal),
        "unresolved_instruments": len(unresolved), "unresolved_terminal": len(terminal - resolved_codes),
        "routing_sha256": sha(routing_bytes), "manifest_sha256": sha(manifest_bytes),
        "target_feature_model_data_read": False,
    }
    (run / "summary.json").write_bytes((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
