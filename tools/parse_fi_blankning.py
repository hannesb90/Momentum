"""PARSAR FI:S BLANKNINGSREGISTER (ODS) TILL VALIDERAT LAGER

Finansinspektionens blankningsregister är den enda nya datakällan som har
HISTORIK. Börsdatas /v1/holdings/shorts är en ögonblicksbild utan tidsserie;
FI:s historiska fil innehåller varje rapporterad betydande nettoposition sedan
registret startade.

Varje rad: innehavare, emittent, ISIN, position i procent, datum.
"<0,5" betyder att positionen sjunkit under publiceringströskeln 0,5 procent.

Skriptet parsar ODS-filen, normaliserar, kopplar ISIN till våra tickers och
rapporterar täckning per år och per fönster.

Kör: /opt/momentum/venv/bin/python tools/parse_fi_blankning.py
"""
from __future__ import annotations
import glob, hashlib, json, re, sys, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/fi_blankning"
UT = V2 / "validated/fi_blankning"
NS = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
      "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
      "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0"}


def celltext(c):
    return "".join(p.itertext()).strip() if (p := c) is not None else ""


def rader_ur_ods(p: Path):
    z = zipfile.ZipFile(p)
    root = ET.fromstring(z.read("content.xml"))
    ut = []
    for tabell in root.iter(f"{{{NS['table']}}}table"):
        for rad in tabell.iter(f"{{{NS['table']}}}table-row"):
            celler = []
            for c in rad.findall(f"{{{NS['table']}}}table-cell"):
                rep = int(c.get(f"{{{NS['table']}}}number-columns-repeated", "1"))
                v = "".join(c.itertext()).strip()
                celler.extend([v] * min(rep, 20))
            if celler:
                ut.append(celler)
    return ut


def normalisera(rader):
    dat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    isin = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
    ut = []
    for r in rader:
        i_isin = next((i for i, v in enumerate(r) if isin.match(v or "")), None)
        i_dat = next((i for i, v in enumerate(r) if dat.match(v or "")), None)
        if i_isin is None or i_dat is None or i_isin < 2:
            continue
        pos = r[i_isin + 1] if i_isin + 1 < len(r) else ""
        p = None
        if pos.startswith("<"):
            p = 0.0
        else:
            m = re.match(r"^([\d,\.]+)$", pos.replace(" ", ""))
            if m:
                try:
                    p = float(m.group(1).replace(",", "."))
                except ValueError:
                    p = None
        ut.append({"innehavare": r[i_isin - 2], "emittent": r[i_isin - 1], "isin": r[i_isin],
                   "position_pct": p, "under_troskel": pos.startswith("<"), "datum": r[i_dat]})
    return ut


def main():
    UT.mkdir(parents=True, exist_ok=True)
    filer = {n: sorted(glob.glob(str(RAW / f"fi_blankning_{n}_*.ods")))[-1] for n in ("Hist", "Aktuell")}
    allt, meta = [], {}
    for namn, f in filer.items():
        p = Path(f)
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        rader = normalisera(rader_ur_ods(p))
        meta[namn] = {"fil": p.name, "sha256": sha, "bytes": p.stat().st_size, "rader": len(rader)}
        for r in rader:
            r["kalla"] = namn
        allt.extend(rader)
        print(f"  {namn:<8} {len(rader):>7} rader   sha {sha[:16]}…")

    sett, unika = set(), []
    for r in allt:
        n = (r["innehavare"], r["isin"], r["datum"], r["position_pct"])
        if n in sett:
            continue
        sett.add(n); unika.append(r)
    d = sorted(r["datum"] for r in unika)
    print(f"\n  unika poster: {len(unika)}   datum {d[0]} → {d[-1]}")
    per_ar = Counter(r["datum"][:4] for r in unika)
    print(f"  per år: {dict(sorted(per_ar.items()))}")

    # koppla ISIN -> ticker via Börsdatas instrumentlista i proben
    inst = json.loads((V2 / "trackj/j2a_borsdata_api_probe/raw/"
                       "J2A_PROBE_2026-08-09T120000Z/instruments.json").read_text())
    rows = inst.get("instruments", inst)
    i2t = {(i.get("isin") or "").upper(): i.get("ticker") for i in rows if i.get("isin")}
    prod = set(json.loads((V2 / "validated/prices/prices_validated.json").read_text()))
    for r in unika:
        r["ticker"] = i2t.get(r["isin"].upper())
    med_t = [r for r in unika if r["ticker"]]
    i_prod = [r for r in med_t if r["ticker"] in prod]
    print(f"\n  med ticker: {len(med_t)}   varav i produktionsuniversumet: {len(i_prod)}")
    print(f"  unika ISIN totalt: {len({r['isin'] for r in unika})}, "
          f"unika tickers i universumet: {len({r['ticker'] for r in i_prod})}")
    for lo, hi, namn in (("2014-01-01", "2019-12-31", "fönster 2014-2019"),
                         ("2020-01-01", "2026-12-31", "fönster 2020-2026")):
        v = [r for r in i_prod if lo <= r["datum"] <= hi]
        print(f"  {namn}: {len(v)} poster, {len({r['ticker'] for r in v})} bolag, "
              f"{len({r['datum'] for r in v})} datum")

    fil = UT / "fi_blankning_normaliserad.jsonl"
    with open(fil, "w") as f:
        for r in sorted(unika, key=lambda x: (x["datum"], x["isin"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (UT / "manifest.json").write_text(json.dumps({
        "version": "FI_BLANKNING_NORMALISERAD_V1",
        "skapad_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "kalla": "Finansinspektionen blankningsregistret, fi.se",
        "url": "https://www.fi.se/sv/vara-register/blankningsregistret/Get{Hist,Aktuell}File",
        "raa_filer": meta, "unika_poster": len(unika),
        "datumspann": [d[0], d[-1]], "per_ar": dict(sorted(per_ar.items())),
        "poster_i_produktionsuniversum": len(i_prod),
        "notering": "Publiceringströskel 0,5 %. '<0,5' tolkas som position_pct=0 och "
                    "under_troskel=True, alltså en nedgång under tröskeln."},
        ensure_ascii=False, indent=1))
    print(f"\n  skrivet: {fil}")


if __name__ == "__main__":
    main()
