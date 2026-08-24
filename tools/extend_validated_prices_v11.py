"""dataset_v1.1 — förlänger prislagret från 2026-07-24 till idag.

dataset_v1.0 (sha256 e3ed38b8…) LÄMNAS ORÖRT. Detta skriver en ny fil,
validated/prices/prices_validated_v1_1.json, plus eget manifest.

Samma R-regler som build_validated_prices.py:
  R1  adjusted_close för avkastning, close bevaras
  R3  ogiltiga värden UTESLUTS (golv 0.0001, platshållare 1e6)
  R6  ingen clipping, winsorisering eller imputering

TILLÄGG: överlappskontroll. Hämtningen börjar 60 dagar före v1.0:s sista datum
och de överlappande adjusted_close jämförs mot v1.0. Avviker de har en
kapitalhändelse omskalat hela serien bakåt — instrumentet flaggas då och
utesluts ur v1.1 i stället för att tyst förorena lagret.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

V2 = Path("/home/hannesb/momentum_v2")
SRC = V2 / "validated/prices/prices_validated.json"
OUT = V2 / "validated/prices/prices_validated_v1_1.json"
MAN = V2 / "validated/manifest_sparA_v1_1.json"
BASE = "https://eodhd.com/api/eod"
FLOOR, PLACEHOLDER = 0.0001, 1000000.0
OVERLAP_DAYS = 60
TOL = 0.005          # 0,5 % tolerans på överlappande adjusted_close


def token() -> str:
    txt = Path.home().joinpath(".momentum.env").read_text()
    m = re.search(r"^\s*(?:export\s+)?EODHD_API_TOKEN\s*=\s*(.+)$", txt, re.M)
    if not m:
        raise SystemExit("EODHD_API_TOKEN saknas i ~/.momentum.env")
    return m.group(1).strip().strip('"').strip("'")


KEY = token()


def hamta(kod: str, fran: str, till: str):
    for f in range(4):
        r = requests.get(f"{BASE}/{kod}.ST",
                         params={"api_token": KEY, "fmt": "json", "from": fran, "to": till},
                         timeout=45)
        if r.status_code == 200:
            try:
                return r.json(), 200
            except Exception:  # noqa: BLE001
                return [], r.status_code
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** f)
            continue
        return [], r.status_code
    return [], r.status_code


def giltig(rad: dict) -> bool:
    a = rad.get("adjusted_close")
    c = rad.get("close")
    if a is None or c is None:
        return False
    if not (FLOOR < float(a) < PLACEHOLDER):
        return False
    if not (FLOOR < float(c) < PLACEHOLDER):
        return False
    return True


def main() -> None:
    v10 = json.loads(SRC.read_text(encoding="utf-8"))
    sista = max(r["d"] for rs in v10.values() for r in rs)
    idag = date.today().isoformat()
    fran = (date.fromisoformat(sista) - __import__("datetime").timedelta(days=OVERLAP_DAYS)).isoformat()
    print(f"v1.0 slutar {sista}   hämtar {fran} → {idag}   {len(v10)} instrument\n")

    ny, flaggade, tomma, fel = {}, [], [], []
    n_nya_rader = 0
    for i, (kod, rs) in enumerate(sorted(v10.items()), 1):
        rows, status = hamta(kod, fran, idag)
        time.sleep(0.12)
        if status != 200:
            fel.append((kod, status)); ny[kod] = rs; continue
        rows = [r for r in rows if giltig(r)]
        if not rows:
            tomma.append(kod); ny[kod] = rs; continue

        # överlappskontroll mot v1.0
        gamla = {r["d"]: r["adj"] for r in rs}
        avvik = 0; jamf = 0
        for r in rows:
            d = r["date"][:10]
            if d in gamla:
                jamf += 1
                g = gamla[d]
                if g and abs(float(r["adjusted_close"]) / g - 1) > TOL:
                    avvik += 1
        if jamf >= 5 and avvik / jamf > 0.2:
            flaggade.append((kod, jamf, avvik)); ny[kod] = rs; continue

        nya = [{"d": r["date"][:10], "adj": float(r["adjusted_close"]),
                "close": float(r["close"]), "v": int(r.get("volume") or 0)}
               for r in rows if r["date"][:10] > sista]
        ny[kod] = rs + sorted(nya, key=lambda x: x["d"])
        n_nya_rader += len(nya)
        if i % 60 == 0:
            print(f"  [{i}/{len(v10)}] nya rader {n_nya_rader}  flaggade {len(flaggade)}  "
                  f"tomma {len(tomma)}  fel {len(fel)}", flush=True)

    kanon = json.dumps(ny, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    OUT.write_text(kanon, encoding="utf-8")
    sha = hashlib.sha256(kanon.encode()).hexdigest()
    nytt_sista = max(r["d"] for rs in ny.values() for r in rs)

    man = {"dataset": "dataset_v1.1 / spår A — förlängning av v1.0",
           "bygger_pa": {"fil": SRC.name,
                         "sha256": hashlib.sha256(SRC.read_bytes()).hexdigest()},
           "byggd_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "kalla": "EODHD /api/eod, hämtat direkt (ej legacy-arkivet)",
           "dataset_sha256": sha,
           "innehall": {"n_instrument": len(ny),
                        "n_rader": sum(len(v) for v in ny.values()),
                        "nya_rader": n_nya_rader,
                        "forsta_datum": min(r["d"] for rs in ny.values() for r in rs),
                        "sista_datum": nytt_sista},
           "overlappskontroll": {"dagar": OVERLAP_DAYS, "tolerans": TOL,
                                 "flaggade_instrument": [f[0] for f in flaggade],
                                 "detalj": flaggade},
           "utan_ny_data": tomma, "hamtningsfel": fel,
           "regler": "R1/R3/R6 som build_validated_prices.py; ingen imputering",
           "v1_0_orort": True}
    MAN.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'='*72}")
    print(f"  nya rader        {n_nya_rader:,}")
    print(f"  sista datum      {sista} → {nytt_sista}")
    print(f"  flaggade (kapitalhändelse) {len(flaggade)}  → behåller v1.0-serien")
    print(f"  utan ny data     {len(tomma)}   (avnoterade)")
    print(f"  hämtningsfel     {len(fel)}")
    print(f"  v1.1 sha256      {sha}")
    if flaggade[:5]:
        print(f"  flaggade ex: {[f[0] for f in flaggade[:5]]}")


if __name__ == "__main__":
    main()
