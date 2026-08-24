"""Spar B, Track A: hamta Borsdata-rapporter LIVE for universumets instrument.

Skillnad mot legacyns rawstore.py/borsdata.py (som skrev om till json.dumps):
har sparas r.content VERBATIM, och sha256 beraknas pa EXAKT de mottagna
bytesen. Det ar den defekt som underkande legacyns radatalager - den
upprepas inte har.

Tre endpoints per instrument (samma parametrar som verifierats tidigare):
  /v1/instruments/{id}/reports                 maxYearCount=20 (arsdata)
  /v1/instruments/{id}/reports/quarter          maxCount=40 (kvartal, API-tak)
  /v1/instruments/{id}/reports/r12              maxCount=40 (rullande 12 man)

Endast instrument som Borsdata FAKTISKT serverar idag hamtas - dvs. de i
universumet vars ISIN matchar nagot i dagens /instruments-lista. For
avnoterade bolag som Borsdata redan tagit bort (bekraftat i UNIVERSUM_OCH_
KALLBESLUT.md) ger detta 0 rader, vilket registreras, inte gissas bort.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "raw/borsdata"
MANIFEST = OUT / "_manifest.jsonl"
BASE = "https://apiservice.borsdata.se/v1"
SLEEP = 0.15


def _key() -> str:
    m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$",
                  Path.home().joinpath(".momentum.env").read_text(), re.M)
    return m.group(1).strip().strip('"').strip("'")


KEY = _key()


def hamta(endpoint: str, params: dict, slug: str) -> dict:
    d = OUT / slug.split("/")[0]
    d.mkdir(parents=True, exist_ok=True)
    q = dict(params, authKey=KEY)
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
        fn.parent.mkdir(parents=True, exist_ok=True)
        fn.write_bytes(r.content)                      # VERBATIM
        rec.update({"ok": True, "sha256": hashlib.sha256(r.content).hexdigest(),
                   "n_bytes": len(r.content), "file": str(fn.relative_to(OUT))})
    else:
        rec.update({"ok": False, "sha256": None, "n_bytes": 0, "file": None})
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    time.sleep(SLEEP)
    return rec


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text(encoding="utf-8"))
    live = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    inst_live = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    ns_live_by_isin = {(i.get("isin") or "").upper(): i for i in inst_live
                       if i.get("marketId") in (1, 2, 3)}

    # universum (samma definition som i build_validated_prices.py)
    ns_isin = {(i.get("isin") or "").upper() for i in live if i.get("marketId") in (1, 2, 3)}
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

    # matcha mot Börsdatas LIVE insId via ISIN
    par, ingen_traff = [], []
    for kod, r in kod2post.items():
        z = ((r.get("eodhd") or {}).get("isin") or "").upper()
        post = ns_live_by_isin.get(z)
        if post:
            par.append((kod, post["insId"], r["namn"], z))
        else:
            ingen_traff.append((kod, r["namn"], z))
    print(f"universum: {len(kod2post)} instrument")
    print(f"  matchar dagens live Börsdata-instrument (hämtningsbara): {len(par)}")
    print(f"  matchar INTE (Börsdata serverar inte längre, förväntat för avnoterade): "
          f"{len(ingen_traff)}")

    ok = fel = 0
    for i, (kod, insid, namn, isin) in enumerate(par, 1):
        for ep, params, tag in (
            (f"/instruments/{insid}/reports",
             {"maxYearCount": 20, "maxR12Count": 20, "maxQuarterCount": 40}, "year"),
            (f"/instruments/{insid}/reports/quarter", {"maxCount": 40}, "quarter"),
            (f"/instruments/{insid}/reports/r12", {"maxCount": 40}, "r12"),
        ):
            rec = hamta(ep, params, f"{tag}/{insid}_{tag}")
            if rec["ok"]:
                ok += 1
            else:
                fel += 1
        if i % 50 == 0:
            print(f"  [{i}/{len(par)}] ok={ok} fel={fel}", flush=True)

    (OUT / "_matchning.json").write_text(json.dumps({
        "n_universum": len(kod2post), "n_matchade": len(par),
        "n_ej_matchade": len(ingen_traff),
        "matchade": [{"kod": k, "insid": i, "namn": n, "isin": z} for k, i, n, z in par],
        "ej_matchade": [{"kod": k, "namn": n, "isin": z} for k, n, z in ingen_traff]},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nklart: {ok} lyckade anrop, {fel} fel, över {len(par)} instrument")
    print(f"artefakt: {OUT}/_matchning.json, {MANIFEST}")


if __name__ == "__main__":
    main()
