#!/usr/bin/env python3
"""Build an append-only, verbatim MFN JSON-feed snapshot for frozen V2 ISINs."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://mfn.se/all/s"
UA = "Mozilla/5.0 (Momentum V2 immutable data foundation; research)"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen_universe() -> list[dict]:
    prices = json.loads((ROOT / "validated/prices/prices_validated.json").read_text())
    match = json.loads((ROOT / "raw/borsdata/_matchning.json").read_text())
    rows = {row["kod"]: row for key in ("matchade", "ej_matchade") for row in match[key]}
    # Two terminal SDBs lack ISIN in the Börsdata match artifact. Both values
    # are explicitly evidenced in immutable Skatteverket material / issuer
    # history, not inferred from ticker or fuzzy name.
    evidenced_terminal_isin = {
        "MIC-SDB": "SE0001174970",
        "SMF": "CA8169221089",
    }
    out = []
    for code in sorted(prices):
        row = rows.get(code)
        if row and not row.get("isin") and code in evidenced_terminal_isin:
            row = {**row, "isin": evidenced_terminal_isin[code]}
        if not row or not row.get("isin"):
            raise RuntimeError(f"missing ISIN routing identity: {code}")
        out.append({"instrument_id": code, "isin": row["isin"], "name": row.get("namn")})
    if len(out) != 420 or len({r["isin"] for r in out}) != 420:
        raise RuntimeError("expected 420 unique frozen V2 ISINs")
    return out


def request(session: requests.Session, url: str, params: dict | None) -> tuple[bytes, dict, dict]:
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
                "request_url": url,
                "request_params": params or {},
                "retrieved_at_utc": finished.isoformat(),
                "elapsed_seconds": (finished - started).total_seconds(),
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "response_bytes": len(payload),
                "response_sha256": digest(payload),
                "schema_version": parsed.get("version"),
            }
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"MFN request failed: {url}: {last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--start-date", default="2020-01-01")
    ap.add_argument("--pause", type=float, default=0.12)
    args = ap.parse_args()
    run = ROOT / "trackj/mfn" / args.run_id
    raw = run / "raw"
    if (run / "summary.json").exists():
        raise RuntimeError(f"completed run-id exists (append-only): {run}")
    raw.mkdir(parents=True, exist_ok=True)
    universe = frozen_universe()
    universe_bytes = (json.dumps(universe, indent=2, sort_keys=True) + "\n").encode()
    universe_path = run / "universe.json"
    if universe_path.exists() and universe_path.read_bytes() != universe_bytes:
        raise RuntimeError("resume universe mismatch")
    if not universe_path.exists():
        universe_path.write_bytes(universe_bytes)
    journal_path = run / "_request_journal.jsonl"
    manifest = [json.loads(line) for line in journal_path.read_text().splitlines()] if journal_path.exists() else []
    by_isin: dict[str, list[dict]] = {}
    for row in manifest:
        by_isin.setdefault(row["isin"], []).append(row)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    for index, identity in enumerate(universe):
        isin = identity["isin"]
        url, params = BASE, {"query": isin, "lang": "sv", "limit": "500"}
        seen_urls = set()
        prior = sorted(by_isin.get(isin, []), key=lambda r: r["page"])
        if prior:
            last = prior[-1]
            prior_payload = json.loads((ROOT / last["path"]).read_bytes())
            if not last["item_count"] or not prior_payload.get("next_url") or (
                last["oldest_published_at"] and last["oldest_published_at"][:10] < args.start_date
            ):
                continue
            next_url = prior_payload["next_url"]
            parsed_url = urlparse(next_url)
            url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
        for page_no in range(len(prior), 100):
            request_key = url + "?" + json.dumps(params or {}, sort_keys=True)
            if request_key in seen_urls:
                raise RuntimeError(f"pagination loop: {isin}")
            seen_urls.add(request_key)
            payload, parsed, meta = request(session, url, params)
            path = raw / isin / f"page_{page_no:03d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            items = parsed.get("items") or []
            dates = [((item.get("content") or {}).get("publish_date") or "") for item in items]
            valid_dates = [d for d in dates if d]
            row = {
                **meta,
                **identity,
                "page": page_no,
                "item_count": len(items),
                "newest_published_at": max(valid_dates) if valid_dates else None,
                "oldest_published_at": min(valid_dates) if valid_dates else None,
                "next_url_present": bool(parsed.get("next_url")),
                "path": str(path.relative_to(ROOT)),
            }
            manifest.append(row)
            with journal_path.open("ab") as journal:
                journal.write((json.dumps(row, sort_keys=True) + "\n").encode())
            if not items or not parsed.get("next_url"):
                break
            if valid_dates and min(valid_dates)[:10] < args.start_date:
                break
            next_url = parsed["next_url"]
            parsed_url = urlparse(next_url)
            url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
            time.sleep(args.pause)
        else:
            raise RuntimeError(f"pagination safety limit: {isin}")
        if (index + 1) % 25 == 0:
            print(f"MFN {index + 1}/420 instruments, {len(manifest)} pages", flush=True)

    manifest_bytes = journal_path.read_bytes()
    (run / "manifest.jsonl").write_bytes(manifest_bytes)
    summary = {
        "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "MFN JSON Feed",
        "start_date": args.start_date,
        "instruments": len(universe),
        "pages": len(manifest),
        "raw_bytes": sum(r["response_bytes"] for r in manifest),
        "universe_sha256": digest(universe_bytes),
        "manifest_sha256": digest(manifest_bytes),
        "target_feature_model_data_read": False,
    }
    (run / "summary.json").write_bytes((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
