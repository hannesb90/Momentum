"""Nasdaq monthly statistics — nedladdare, verifierare och coverage-rapport.

STDLIB ONLY (urllib). Inga beroenden. Kors dar natverk finns.

Kedja:
    notis-URL  ->  bilage-URL  ->  RAW-fil  ->  sha256  ->  parser  ->  coverage

Anvandning
----------
1) Ge notis-URL:er (fran discovery, en per rad, '#' = kommentar):

     python3 hamta_manadsfiler.py --notiser notiser.txt --ut raw/nasdaq_segment/monthly

2) Eller ge bilage-URL:er direkt om du redan har dem:

     python3 hamta_manadsfiler.py --bilagor bilagor.txt --ut raw/nasdaq_segment/monthly

3) Coverage-rapport over det som finns pa disk (kraver inget natverk):

     python3 hamta_manadsfiler.py --coverage raw/nasdaq_segment/monthly --fran 2011-01 --till 2026-07

Ingen manad antas tyst. Saknade manader listas explicit som MISSING.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys, time, urllib.request
from datetime import date

UA = {"User-Agent": "Mozilla/5.0 (compatible; momentum-v2 research data collector)"}
# OBS: bilage-hasharna ar 33 hex-tecken, inte 32. {32} ger en TRUNKERAD URL.
RE_BILAGA = re.compile(r"https://attachment\.news\.eu\.nasdaq\.com/[0-9a-f]{30,40}")
# Tva observerade filnamnskonventioner. Bada maste stodjas:
#   Equity_Trading_by_Company_and_Instrument_2511.xlsx              (YYMM)
#   Equity_Trading_by_Company_and_Instrument_2303_Updated.xls       (YYMM + suffix)
#   Main Market - Equity Trading by Company and Instrument_2025-06.xlsx  (ISO YYYY-MM)
RE_FILNAMN_YYMM = re.compile(
    r"Equity[_ ]Trading[_ ]by[_ ]Company[_ ]and[_ ]Instrument[_ ](\d{2})(\d{2})(_[A-Za-z]+)?\.(xlsx?)", re.I)
RE_FILNAMN_ISO = re.compile(
    r"Equity[_ ]Trading[_ ]by[_ ]Company[_ ]and[_ ]Instrument[_ ](\d{4})-(\d{2})(_[A-Za-z]+)?\.(xlsx?)", re.I)


def matcha_filnamn(text):
    """Returnerar (manad, ext, traffstrang) eller None. ISO provas forst eftersom
    YYMM-monstret annars matchar de fyra sista siffrorna i ett ISO-datum."""
    m = RE_FILNAMN_ISO.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}", m.group(4).lower(), m.group(0)
    m = RE_FILNAMN_YYMM.search(text)
    if m:
        return f"20{m.group(1)}-{m.group(2)}", m.group(4).lower(), m.group(0)
    return None


def hamta(url, forsok=3, paus=2.0) -> bytes:
    sista = None
    for i in range(forsok):
        try:
            r = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(r, timeout=60) as f:
                return f.read()
        except Exception as e:                       # noqa: BLE001
            sista = e; time.sleep(paus * (i + 1))
    raise RuntimeError(f"kunde inte hamta {url}: {sista}")


def bilaga_ur_notis(url: str) -> dict:
    html = hamta(url).decode("utf-8", "ignore")
    urls = RE_BILAGA.findall(html)
    tr = matcha_filnamn(html)
    if not urls:
        return {"notis": url, "status": "INGEN_BILAGA_HITTAD"}
    if not tr:
        return {"notis": url, "status": "FILNAMN_MATCHAR_INTE_MONSTRET",
                "bilagor": sorted(set(urls))}
    manad, ext, traff = tr
    return {"notis": url, "status": "OK", "bilaga": urls[0],
            "filnamn": traff.replace(" ", "_"), "manad": manad, "ext": ext}


def spara(bilaga_url: str, manad: str, ext: str, utdir: pathlib.Path) -> dict:
    d = utdir / manad[:4]
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{manad}.{ext}"
    if p.exists():
        b = p.read_bytes()
        return {"manad": manad, "fil": str(p), "sha256": hashlib.sha256(b).hexdigest(),
                "bytes": len(b), "status": "REDAN_PA_DISK"}
    b = hamta(bilaga_url)
    if b[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and b[:4] != b"PK\x03\x04":
        return {"manad": manad, "status": "EJ_EXCEL", "bytes": len(b),
                "signatur": b[:8].hex()}
    p.write_bytes(b)
    return {"manad": manad, "fil": str(p), "sha256": hashlib.sha256(b).hexdigest(),
            "bytes": len(b), "status": "HAMTAD", "kalla": bilaga_url}


def manadslista(fran: str, till: str):
    y, m = int(fran[:4]), int(fran[5:7])
    ye, me = int(till[:4]), int(till[5:7])
    ut = []
    while (y, m) <= (ye, me):
        ut.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return ut


def coverage(utdir: pathlib.Path, fran: str, till: str, parsa=True) -> dict:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    rader = []
    for man in manadslista(fran, till):
        tr = list((utdir / man[:4]).glob(f"{man}.xls*")) if (utdir / man[:4]).is_dir() else []
        if not tr:
            rader.append({"manad": man, "status": "MISSING"}); continue
        p = tr[0]
        r = {"manad": man, "status": "FOUND", "fil": str(p),
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
             "bytes": p.stat().st_size}
        if parsa:
            try:
                from parse_monthly import parse, sto_stock
                pr = parse(p); s = sto_stock(pr["rows"])
                from collections import Counter
                r.update({"parse": "OK", "schema_epoch": pr["schema_epoch"],
                          "header_row": pr["header_row"], "sto_stock_cap": len(s),
                          "per_segment": dict(Counter(x["segment"] for x in s)),
                          "isin_tackning": f"{sum(1 for x in s if x['isin'])}/{len(s)}",
                          "avnoterade": sum(1 for x in s if x["delisted"])})
            except Exception as e:                    # noqa: BLE001
                r.update({"parse": "FEL", "fel": f"{type(e).__name__}: {e}"})
        rader.append(r)
    n_found = sum(1 for x in rader if x["status"] == "FOUND")
    return {"fran": fran, "till": till, "manader": len(rader), "found": n_found,
            "missing": len(rader) - n_found,
            "parse_fel": sum(1 for x in rader if x.get("parse") == "FEL"),
            "rader": rader}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notiser"); ap.add_argument("--bilagor")
    ap.add_argument("--ut", default="raw/nasdaq_segment/monthly")
    ap.add_argument("--coverage"); ap.add_argument("--fran", default="2011-01")
    ap.add_argument("--till", default="2026-07")
    ap.add_argument("--rapport", default="research_k/nasdaq_segment_foundation/coverage.json")
    a = ap.parse_args()
    utdir = pathlib.Path(a.ut)

    if a.coverage:
        rap = coverage(pathlib.Path(a.coverage), a.fran, a.till)
        pathlib.Path(a.rapport).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.rapport).write_text(json.dumps(rap, ensure_ascii=False, indent=1))
        print(f"COVERAGE {a.fran}..{a.till}: {rap['found']} FOUND, {rap['missing']} MISSING, "
              f"{rap['parse_fel']} parse-fel")
        for r in rap["rader"]:
            if r["status"] == "MISSING":
                print(f"  {r['manad']}  MISSING")
            elif r.get("parse") == "FEL":
                print(f"  {r['manad']}  FOUND men PARSE-FEL: {r['fel']}")
        print(f"skrivet: {a.rapport}")
        return

    jobb = []
    if a.notiser:
        for rad in pathlib.Path(a.notiser).read_text().splitlines():
            rad = rad.strip()
            if rad and not rad.startswith("#"):
                jobb.append(("notis", rad))
    if a.bilagor:
        for rad in pathlib.Path(a.bilagor).read_text().splitlines():
            rad = rad.strip()
            if rad and not rad.startswith("#"):
                jobb.append(("bilaga", rad))
    if not jobb:
        ap.error("ange --notiser, --bilagor eller --coverage")

    logg = []
    for typ, url in jobb:
        if typ == "notis":
            info = bilaga_ur_notis(url)
            print(f"  notis {url[-20:]}: {info['status']}")
            if info["status"] != "OK":
                logg.append(info); continue
            res = spara(info["bilaga"], info["manad"], info["ext"], utdir)
            res["notis"] = url
        else:
            b = hamta(url)
            tr = matcha_filnamn(url)
            if not tr:
                logg.append({"bilaga": url, "status": "MANAD_OKAND_FRAN_URL"}); continue
            manad, ext, _ = tr
            res = spara(url, manad, ext, utdir)
        print(f"    {res.get('manad')}: {res['status']} {res.get('bytes','')}")
        logg.append(res)
    pathlib.Path(a.rapport).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.rapport).with_name("hamtningslogg.json").write_text(
        json.dumps(logg, ensure_ascii=False, indent=1))
    print(f"logg: {pathlib.Path(a.rapport).with_name('hamtningslogg.json')}")


if __name__ == "__main__":
    main()
