#!/usr/bin/env python3
"""Read-only Börsdata J2A API probes; no targets, features, or models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://apiservice.borsdata.se"
SWAGGER = "https://apidoc.borsdata.se/swagger/v1/swagger.json"
OUT = ROOT / "trackj" / "j2a_borsdata_api_probe"
RAW = OUT / "raw"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_key() -> str:
    for env_path in (Path.home() / ".momentum.env", ROOT / ".env"):
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("BORSDATA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    for name in ("BORSDATA_API_KEY", "BORSDATA_AUTH_KEY", "BORSDATA_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError("Börsdata API key missing")


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"append-only collision: {path}")
        return
    path.write_bytes(data)


def request_bytes(url: str, params: dict[str, str] | None = None) -> tuple[bytes, dict]:
    started = datetime.now(timezone.utc)
    response = requests.get(url, params=params, timeout=90)
    finished = datetime.now(timezone.utc)
    payload = response.content
    response.raise_for_status()
    safe_params = {k: v for k, v in (params or {}).items() if k != "authKey"}
    return payload, {
        "url": url,
        "params": safe_params,
        "retrieved_at_utc": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "bytes": len(payload),
        "sha256": sha256(payload),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    key = load_key()
    match = json.loads((ROOT / "raw/borsdata/_matchning.json").read_text())
    insids = sorted({int(row["insid"]) for row in match["matchade"]})
    run_dir = RAW / args.run_id
    if run_dir.exists():
        raise RuntimeError(f"run-id already exists: {args.run_id}")
    run_dir.mkdir(parents=True)
    manifest: list[dict] = []

    swagger, meta = request_bytes(SWAGGER)
    path = run_dir / "swagger_v1.json"
    write_once(path, swagger)
    manifest.append({**meta, "logical_name": "swagger", "path": str(path.relative_to(ROOT))})

    instruments, meta = request_bytes(f"{BASE}/v1/instruments", {"authKey": key})
    path = run_dir / "instruments.json"
    write_once(path, instruments)
    manifest.append({**meta, "logical_name": "instruments", "path": str(path.relative_to(ROOT))})

    endpoints = {
        "report_calendar": "/v1/instruments/report/calendar",
        "dividend_calendar": "/v1/instruments/dividend/calendar",
        "insider": "/v1/holdings/insider",
        "buyback": "/v1/holdings/buyback",
    }
    for logical_name, endpoint in endpoints.items():
        for offset in range(0, len(insids), 50):
            batch = insids[offset : offset + 50]
            params = {"authKey": key, "instList": ",".join(map(str, batch))}
            payload, meta = request_bytes(f"{BASE}{endpoint}", params)
            path = run_dir / logical_name / f"batch_{offset:04d}.json"
            write_once(path, payload)
            manifest.append({
                **meta,
                "logical_name": logical_name,
                "endpoint": endpoint,
                "batch_offset": offset,
                "insids": batch,
                "path": str(path.relative_to(ROOT)),
                "pagination": "client-side instList batches, max 50 per Swagger",
            })
            time.sleep(0.11)

    splits, meta = request_bytes(
        f"{BASE}/v1/instruments/StockSplits",
        {"authKey": key, "from": "2020-01-01"},
    )
    path = run_dir / "stock_splits_2020.json"
    write_once(path, splits)
    manifest.append({
        **meta,
        "logical_name": "stock_splits",
        "endpoint": "/v1/instruments/StockSplits",
        "path": str(path.relative_to(ROOT)),
        "pagination": "none documented",
    })

    manifest_bytes = ("\n".join(json.dumps(x, sort_keys=True) for x in manifest) + "\n").encode()
    write_once(run_dir / "manifest.jsonl", manifest_bytes)
    summary = {
        "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "J2A data-gap audit probes only",
        "target_or_model_data_read": False,
        "verified_v2_insid_count": len(insids),
        "requests": len(manifest),
        "manifest_sha256": sha256(manifest_bytes),
        "manifest_path": str((run_dir / "manifest.jsonl").relative_to(ROOT)),
    }
    write_once(run_dir / "summary.json", (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
