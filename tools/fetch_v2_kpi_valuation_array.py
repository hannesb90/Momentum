"""Spår K2-förberedelse: hämtar Börsdatas VÄRDERINGS-KPI:er via ARRAY-endpointen.

Verifierad endpoint (swagger, docs/probes/swagger_v1.json):
  /v1/instruments/kpis/{kpiId}/{reporttype}/{pricetype}/history
    instList  (comma separated, batchas om 50)
    maxCount  ("10 default. year=20 max, r12&quarter=40 max")

Skälet till array: den befintliga fetch_v2_kpi_history_full.py hämtar ett
instrument i taget. För 20 KPI:er × 3 rapporttyper × 352 instrument blir det
21 120 anrop. Med instList blir det 20 × 3 × 8 = 480.

DATAINSAMLING ENDAST. Ingen modell, inget target, ingen backtest, inget
features-bygge. RAW sparas VERBATIM (r.content) med sha256 av exakt mottagna
bytes och append-only-manifest — samma metodik som fetch_v2_raw_borsdata.py.

Kör:  /opt/momentum/venv/bin/python tools/fetch_v2_kpi_valuation_array.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "raw/borsdata/kpi_valuation"
MANIFEST = OUT / "_manifest.jsonl"
BASE = "https://apiservice.borsdata.se/v1"
SLEEP = 0.15
BATCH = 50
PRICE_TYPE = "mean"
REPORT_TYPES = ("year", "quarter", "r12")
MAXCOUNT = {"year": 20, "quarter": 40, "r12": 40}   # API-taket, se swagger

# Upplösta ur raw/borsdata/metadata/kpis_metadata__20260808T042524Z.json
KPI_IDS = {
    2: "PE", 3: "PS", 4: "PB", 18: "PB_tang", 9: "PEx",
    10: "EV_EBIT", 11: "EV_EBITDA", 12: "EV_E", 13: "EV_FCF", 15: "EV_S",
    16: "E_EV", 17: "EBIT_EV", 19: "PEG", 76: "P_FCF",
    1: "Direktavkastning", 20: "Utdelningsandel", 308: "NCAV_aktie",
    50: "Borsvarde", 49: "EnterpriseValue", 61: "AntalAktier",
}


def _key() -> str:
    m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$",
                  Path.home().joinpath(".momentum.env").read_text(), re.M)
    if not m:
        sys.exit("BORSDATA_API_KEY saknas i ~/.momentum.env")
    return m.group(1).strip().strip('"').strip("'")


KEY = _key()


def hamta(endpoint: str, params: dict, slug: str) -> dict:
    """Ett anrop. Sparar RAW verbatim + manifestrad. Returnerar manifestposten."""
    OUT.mkdir(parents=True, exist_ok=True)
    q = dict(params, authKey=KEY)
    r = None
    for forsok in range(5):
        r = requests.get(BASE + endpoint, params=q, timeout=60)
        if r.status_code == 200:
            break
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** forsok)
            continue
        break
    ts = datetime.now(timezone.utc)
    loggade_params = {k: v for k, v in params.items()}
    if "instList" in loggade_params:                      # logga listan, inte 50 id på rad
        loggade_params["n_instrument"] = len(loggade_params["instList"].split(","))
    rec = {"fetch_utc": ts.isoformat(timespec="seconds"), "endpoint": endpoint,
           "params": loggade_params, "http_status": r.status_code, "slug": slug}
    if r.status_code == 200:
        fn = OUT / f"{slug}__{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
        fn.write_bytes(r.content)
        rec.update({"ok": True, "sha256": hashlib.sha256(r.content).hexdigest(),
                    "n_bytes": len(r.content),
                    "file": str(fn.relative_to(V2 / "raw/borsdata"))})
    else:
        rec.update({"ok": False, "sha256": None, "n_bytes": 0, "file": None,
                    "body_head": r.text[:200] if r is not None else None})
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    time.sleep(SLEEP)
    return rec


def universum() -> list:
    """Återanvänder EXAKT samma universumdefinition som fetch_v2_kpi_history_full."""
    src = V2 / "tools/fetch_v2_kpi_history_full.py"
    spec = importlib.util.spec_from_file_location("kpifull", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.bygg_universum()


def main() -> None:
    par = universum()
    ids = [str(insid) for _, insid, _, _ in par]
    batchar = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    total = len(KPI_IDS) * len(REPORT_TYPES) * len(batchar)
    print(f"universum       : {len(ids)} instrument som matchar Börsdata")
    print(f"KPI:er          : {len(KPI_IDS)}")
    print(f"rapporttyper    : {len(REPORT_TYPES)}")
    print(f"batchar (à {BATCH})  : {len(batchar)}")
    print(f"planerade anrop : {total}   (per instrument hade varit "
          f"{len(KPI_IDS) * len(REPORT_TYPES) * len(ids)})")
    print()

    ok = fel = 0
    felrader = []
    for kpi_id, kpi_namn in KPI_IDS.items():
        for rt in REPORT_TYPES:
            for bi, batch in enumerate(batchar):
                rec = hamta(
                    f"/instruments/kpis/{kpi_id}/{rt}/{PRICE_TYPE}/history",
                    {"instList": ",".join(batch), "maxCount": MAXCOUNT[rt]},
                    f"{kpi_id}_{kpi_namn}_{rt}_b{bi:02d}")
                ok += rec["ok"]
                if not rec["ok"]:
                    fel += 1
                    felrader.append((kpi_namn, rt, bi, rec["http_status"]))
        print(f"  {kpi_namn:16s} klar   ok={ok} fel={fel}", flush=True)

    print(f"\nklart: {ok} ok, {fel} fel av {total}")
    if felrader:
        print("fel:")
        for f in felrader[:20]:
            print("   ", f)


if __name__ == "__main__":
    main()
