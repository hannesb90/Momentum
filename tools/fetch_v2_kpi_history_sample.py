"""Spar B: sample-hamtning av Borsdata KPI-historik (EBITDA/Capex/aterkop).

Verifierad endpoint (se docs/SPAR_B_KPI_HISTORIK_SAMPLE.md):
  /v1/instruments/{insId}/kpis/{kpiId}/{reportType}/{priceType}/history

Endast ETT litet, representativt sample hamtas har - inte hela universumet.
RAW sparas VERBATIM (r.content), sha256 av exakt mottagna bytes, samma
metodik som fetch_v2_raw_borsdata.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "raw/borsdata/kpi_history_sample"
MANIFEST = OUT / "_manifest.jsonl"
BASE = "https://apiservice.borsdata.se/v1"

KPI_IDS = {54: "EBITDA", 64: "Capex", 213: "Aterkop_1man", 214: "Aterkop_3man", 215: "Aterkop_1ar"}
REPORT_TYPES = ("year", "quarter", "r12")
PRICE_TYPE = "mean"

SAMPLE = {
    "stort_aktivt": (3, "ABB Ltd"),
    "litet_aktivt": (108, "Image Systems AB"),
    "avnoterat": (147, "Ledstiernan AB (EMPIR-B)"),
    "brutet_rakenskapsar": (124, "Lagercrantz"),
}


def _key() -> str:
    m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$",
                  Path.home().joinpath(".momentum.env").read_text(), re.M)
    return m.group(1).strip().strip('"').strip("'")


KEY = _key()


def hamta(endpoint: str, params: dict, slug: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    q = dict(params, authKey=KEY)
    r = None
    for försök in range(5):
        r = requests.get(BASE + endpoint, params=q, timeout=30)
        if r.status_code == 200:
            break
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** försök)
            continue
        break
    ts = datetime.now(timezone.utc)
    rec = {"fetch_utc": ts.isoformat(timespec="seconds"), "endpoint": endpoint,
           "params": {k: v for k, v in params.items()}, "http_status": r.status_code,
           "slug": slug}
    if r.status_code == 200:
        fn = OUT / f"{slug}__{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
        fn.write_bytes(r.content)
        rec.update({"ok": True, "sha256": hashlib.sha256(r.content).hexdigest(),
                   "n_bytes": len(r.content), "file": fn.name, "body": r.text[:500]})
    else:
        rec.update({"ok": False, "sha256": None, "n_bytes": 0, "file": None,
                   "body": r.text[:500] if r is not None else None})
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    time.sleep(0.15)
    return rec


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ok = fel = 0
    for kategori, (insid, namn) in SAMPLE.items():
        for kpi_id, kpi_namn in KPI_IDS.items():
            for rt in REPORT_TYPES:
                slug = f"{kategori}_{insid}_{kpi_namn}_{rt}"
                rec = hamta(f"/instruments/{insid}/kpis/{kpi_id}/{rt}/{PRICE_TYPE}/history",
                            {"maxCount": 60}, slug)
                status = "OK" if rec["ok"] else f"FEL({rec['http_status']})"
                print(f"{kategori:20s} insId={insid:5d} {kpi_namn:14s} {rt:8s} -> {status}")
                if rec["ok"]:
                    ok += 1
                else:
                    fel += 1

    # extra: testa ett GENUINT avnoterat bolag UTAN Borsdata-livematchning
    # (dokumenterar forvantad "ingen data"-respons for ren avnoterings-koll)
    print("\n-- extra: helt onoterat/avnoterat insId-test --")
    for insid, namn in ((-1, "ogiltigt insId, forvantat fel"),):
        rec = hamta(f"/instruments/{insid}/kpis/54/year/{PRICE_TYPE}/history",
                    {"maxCount": 10}, f"ogiltig_{insid}")
        print(f"  insId={insid} -> status={rec['http_status']} body={rec['body']}")

    print(f"\nklart: {ok} ok, {fel} fel")
    print(f"artefakter: {OUT}")


if __name__ == "__main__":
    main()
