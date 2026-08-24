"""Spar B: fullskale-hamtning av Borsdata KPI-historik (EBITDA, Capex) +
transaktionsniva-atarkop, for hela Spar A-universumet.

Verifierat i sample-fasen (docs/SPAR_B_KPI_HISTORIK_SAMPLE.md) - inga
blockerande problem. RAW sparas OFORANDRAT/VERBATIM, ingen normalisering
eller PIT-mappning har - det gors i separata steg (build_validated_...).

Endpoints:
  /v1/instruments/{insId}/kpis/{kpiId}/{reportType}/{priceType}/history
      kpiId 54 (EBITDA), 64 (Capex); reportType year/quarter/r12; priceType mean
  /v1/holdings/buyback?instList=... (max 50 per anrop)
      transaktionsniva, explicit datum per rad
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
OUT_KPI = V2 / "raw/borsdata/kpi_history"
OUT_BUYBACK = V2 / "raw/borsdata/buyback"
MANIFEST = V2 / "raw/borsdata/_manifest.jsonl"
BASE = "https://apiservice.borsdata.se/v1"
SLEEP = 0.15

KPI_IDS = {54: "EBITDA", 64: "Capex"}
REPORT_TYPES = ("year", "quarter", "r12")
PRICE_TYPE = "mean"


def _key() -> str:
    m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$",
                  Path.home().joinpath(".momentum.env").read_text(), re.M)
    return m.group(1).strip().strip('"').strip("'")


KEY = _key()


def hamta(endpoint: str, params: dict, out_dir: Path, slug: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
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
        fn = out_dir / f"{slug}__{ts.strftime('%Y%m%dT%H%M%SZ')}.json"
        fn.write_bytes(r.content)
        rec.update({"ok": True, "sha256": hashlib.sha256(r.content).hexdigest(),
                   "n_bytes": len(r.content), "file": str(fn.relative_to(V2 / "raw/borsdata"))})
    else:
        rec.update({"ok": False, "sha256": None, "n_bytes": 0, "file": None})
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    time.sleep(SLEEP)
    return rec


def bygg_universum() -> list:
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text(encoding="utf-8"))
    live = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    ns_live_by_isin = {(i.get("isin") or "").upper(): i for i in live if i.get("marketId") in (1, 2, 3)}
    ns_isin = set(ns_live_by_isin.keys())
    kod2post = {}
    for r in master:
        e = r.get("eodhd") or {}
        kod = e.get("code")
        if not kod:
            continue
        t = (r.get("avnoterad_orsak") or "").lower()
        ar = r.get("avnoterad_ar") or 0
        i_ns = (e.get("isin") or "").upper() in ns_isin
        avn_ns = ar >= 2020 and any(k in t for k in ("nasdaq stockholm", "nordiska listan"))
        if i_ns or avn_ns:
            kod2post[kod] = r
    par = []
    for kod, r in kod2post.items():
        z = ((r.get("eodhd") or {}).get("isin") or "").upper()
        post = ns_live_by_isin.get(z)
        if post:
            par.append((kod, post["insId"], r["namn"], z))
    return par


def main() -> None:
    par = bygg_universum()
    print(f"universum: {len(par)} instrument matchar Börsdata idag")

    ok = fel = 0
    for i, (kod, insid, namn, isin) in enumerate(par, 1):
        for kpi_id, kpi_namn in KPI_IDS.items():
            for rt in REPORT_TYPES:
                rec = hamta(f"/instruments/{insid}/kpis/{kpi_id}/{rt}/{PRICE_TYPE}/history",
                            {"maxCount": 60}, OUT_KPI, f"{insid}_{kpi_namn}_{rt}")
                ok += rec["ok"]
                fel += not rec["ok"]
        if i % 50 == 0:
            print(f"  kpi-historik [{i}/{len(par)}] ok={ok} fel={fel}", flush=True)
    print(f"kpi-historik klart: {ok} ok, {fel} fel")

    ok_bb = fel_bb = 0
    ids = [str(insid) for _, insid, _, _ in par]
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        rec = hamta("/holdings/buyback", {"instList": ",".join(batch)},
                    OUT_BUYBACK, f"batch_{start:04d}")
        ok_bb += rec["ok"]
        fel_bb += not rec["ok"]
        print(f"  buyback-batch {start}-{start+len(batch)} -> {'OK' if rec['ok'] else 'FEL'}")
    print(f"buyback klart: {ok_bb} ok, {fel_bb} fel (batchar om 50)")

    (V2 / "docs/probes/kpi_history_universum.json").write_text(
        json.dumps({"n": len(par), "instrument": [
            {"kod": k, "insId": i, "namn": n, "isin": z} for k, i, n, z in par]},
            indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefakter: {OUT_KPI}, {OUT_BUYBACK}, {MANIFEST}")


if __name__ == "__main__":
    main()
