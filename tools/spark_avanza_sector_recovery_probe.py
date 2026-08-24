#!/usr/bin/env python3
"""Public Avanza sector recovery probe. Data/provenance only; no target reads."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

V2 = Path("/home/hannesb/momentum_v2")
BASE = "https://www.avanza.se"
RUN_ID = "AVANZA_SECTOR_RECOVERY_20260809_V2"
ROOT = V2 / "research_k/avanza_sector_recovery_probe"
RAW = ROOT / "raw" / RUN_ID
UA = "Momentum-V2-public-data-audit/1.0"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"immutable raw mismatch: {path}")
        return
    path.write_bytes(data)


def identities() -> dict:
    d = json.loads((V2 / "trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z/identity_routing.json").read_text())
    out = {}
    for route in d["routes"]:
        for x in route["v2_identities"]:
            out[x["instrument_id"]] = {"isin": x.get("isin"), "name": x.get("name")}
    for x in d["unresolved"]:
        out[x["instrument_id"]] = {"isin": x.get("isin"), "name": x.get("name")}
    return out


def request(session: requests.Session, method: str, path: str, *, payload=None):
    url = BASE + path
    r = session.request(method, url, json=payload, timeout=30)
    retrieved = datetime.now(timezone.utc).isoformat()
    return r, retrieved


def main() -> None:  # noqa: C901
    ids = identities()
    terminal = set(json.loads((V2 / "validated/terminal_events.json").read_text()))
    instruments = json.loads((V2 / "docs/probes/instruments_live.json").read_text())
    match = json.loads((V2 / "raw/borsdata/_matchning.json").read_text())["matchade"]
    bd = {x["kod"]: next((i for i in instruments if i["insId"] == x["insid"]), {}) for x in match}
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": UA,
                            "Content-Type": "application/json"})
    manifest, evidence = [], []
    for n, code in enumerate(sorted(ids), 1):
        ident = ids[code]
        queries = [("ISIN", ident.get("isin")), ("TICKER", code), ("EXACT_NAME", ident.get("name"))]
        chosen = None
        query_evidence = []
        for method_name, query in queries:
            if not query:
                continue
            payload = {"query": query, "limit": 10}
            r, retrieved = request(session, "POST", "/_api/search/filtered-search", payload=payload)
            body = r.content
            rel = Path("search") / code / f"{method_name.lower()}.json"
            write_once(RAW / rel, body)
            manifest.append({"code": code, "kind": "search", "identity_query": method_name,
                             "endpoint": "/_api/search/filtered-search", "params": payload,
                             "retrieved_at": retrieved, "http_status": r.status_code,
                             "content_type": r.headers.get("Content-Type"), "bytes": len(body),
                             "sha256": sha(body), "path": str(rel)})
            hits = []
            if r.status_code == 200:
                try:
                    hits = [h for h in r.json().get("hits", []) if h.get("type") == "STOCK"]
                except Exception:
                    hits = []
            query_evidence.append({"method": method_name, "query": query,
                                   "stock_hits": len(hits), "titles": [h.get("title") for h in hits]})
            # An ISIN query is only a candidate until stock-info independently returns same ISIN.
            for hit in hits:
                ob = hit.get("orderBookId")
                if not ob:
                    continue
                ir, irt = request(session, "GET", f"/_api/market-guide/stock/{ob}")
                ib = ir.content
                # Stock-info contains a live quote and can therefore differ bytewise
                # between two requests to the same orderbook. Preserve every response
                # under its request identity; never overwrite/deduplicate dynamic bytes.
                irel = Path("stock_info") / code / f"{method_name.lower()}_{ob}.json"
                write_once(RAW / irel, ib)
                manifest.append({"code": code, "kind": "stock_info", "orderBookId": str(ob),
                                 "endpoint": f"/_api/market-guide/stock/{ob}", "params": {},
                                 "retrieved_at": irt, "http_status": ir.status_code,
                                 "content_type": ir.headers.get("Content-Type"), "bytes": len(ib),
                                 "sha256": sha(ib), "path": str(irel)})
                try:
                    info = ir.json() if ir.status_code == 200 else {}
                except Exception:
                    info = {}
                if ident.get("isin") and info.get("isin") == ident["isin"]:
                    chosen = ("EXACT_ISIN_MATCH", hit, info, retrieved)
                    break
                ticker = (info.get("listing") or {}).get("tickerSymbol")
                if method_name == "TICKER" and ticker and ticker.replace(" ", "-") == code:
                    chosen = ("VERIFIED_HISTORICAL_TICKER", hit, info, retrieved)
                    break
                if method_name == "EXACT_NAME" and info.get("name") == ident.get("name"):
                    chosen = ("VERIFIED_EXACT_NAME", hit, info, retrieved)
                    break
            if chosen:
                break
            time.sleep(0.12)

        if chosen:
            identity_method, hit, info, retrieved = chosen
            sectors = info.get("sectors") or hit.get("stockSectors") or []
            listing = info.get("listing") or {}
            evidence.append({"instrument_id": code, "terminal": code in terminal,
                             "expected_isin": ident.get("isin"), "expected_name": ident.get("name"),
                             "identity_method": identity_method, "identity_confidence": "HIGH",
                             "avanza_orderbook_id": str(hit.get("orderBookId")),
                             "avanza_isin": info.get("isin"), "avanza_name": info.get("name") or hit.get("title"),
                             "avanza_ticker": listing.get("tickerSymbol"),
                             "market_place": listing.get("marketPlaceName") or hit.get("marketPlaceName"),
                             "market_list": listing.get("marketListName"),
                             "avanza_sector_path_raw": [s.get("sectorName") or s.get("name") for s in sectors],
                             "avanza_sector_objects_raw": sectors,
                             "source_url": BASE + f"/_api/market-guide/stock/{hit.get('orderBookId')}",
                             "retrieved_at": retrieved, "query_evidence": query_evidence,
                             "borsdata_sector_id_current": bd.get(code, {}).get("sectorId"),
                             "borsdata_branch_id_current": bd.get(code, {}).get("branchId")})
        else:
            evidence.append({"instrument_id": code, "terminal": code in terminal,
                             "expected_isin": ident.get("isin"), "expected_name": ident.get("name"),
                             "identity_method": "UNRESOLVED", "identity_confidence": "NONE",
                             "avanza_sector_path_raw": [], "query_evidence": query_evidence,
                             "borsdata_sector_id_current": bd.get(code, {}).get("sectorId"),
                             "borsdata_branch_id_current": bd.get(code, {}).get("branchId")})
        time.sleep(0.12)
        if n % 25 == 0:
            print(f"{n}/{len(ids)}", flush=True)

    write_once(RAW / "request_manifest.jsonl",
               ("\n".join(json.dumps(x, sort_keys=True) for x in manifest) + "\n").encode())
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "identity_sector_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "run_id": RUN_ID, "public_unauthenticated": True, "target_read": False,
        "instruments": len(evidence), "terminal_total": len(terminal),
        "exact_isin": sum(x["identity_method"] == "EXACT_ISIN_MATCH" for x in evidence),
        "terminal_exact_isin": sum(x["terminal"] and x["identity_method"] == "EXACT_ISIN_MATCH" for x in evidence),
        "terminal_resolved": sum(x["terminal"] and x["identity_method"] != "UNRESOLVED" for x in evidence),
        "terminal_with_sector": sum(x["terminal"] and bool(x["avanza_sector_path_raw"]) for x in evidence),
        "active_resolved": sum(not x["terminal"] and x["identity_method"] != "UNRESOLVED" for x in evidence),
        "active_with_sector": sum(not x["terminal"] and bool(x["avanza_sector_path_raw"]) for x in evidence),
        "raw_requests": len(manifest),
    }
    (ROOT / "probe_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    files = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files.append({"path": str(p.relative_to(V2)), "bytes": p.stat().st_size,
                          "sha256": sha(p.read_bytes())})
    aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (ROOT / "manifest.json").write_text(json.dumps({"files": files, "aggregate_sha256": aggregate}, indent=2), encoding="utf-8")
    print(json.dumps(summary | {"aggregate_sha256": aggregate}, indent=2))


if __name__ == "__main__":
    main()
