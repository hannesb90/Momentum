"""Skatteverkets aktiehistorik -> historiskt universum, ar for ar.

Skatteverket anvands ENBART for att faststalla VILKA noterade bolag som funnits
och nar de noterades/avnoterades. Aldrig som kalla for fundamenta.

Fristaende: ingen legacy-import. Legacy lases READ-ONLY (cachad HTML + index).
Nytt radata skrivs till momentum_v2/raw/skatteverket/ VERBATIM med sha256 pa
exakt de bytes som togs emot - det legacy-lagret inte gjorde.

Delkommandon:
    parse    tolka all tillganglig HTML (legacy-cache + v2-raw) -> facts.json
    fetch    hamta bolagssidor som saknas, artigt, till v2-raw
    build    bygg ar-for-ar-universum och jamfor mot EODHD-arkivet
"""
from __future__ import annotations

import datetime
import hashlib
import html as htmllib
import json
import re
import sys
import time
from pathlib import Path

# --- sokvagar (explicita; legacy ar READ-ONLY) -----------------------------
LEGACY_CACHE = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/aktiehistorik")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/skatteverket"
PAGES = RAW / "pages"
MANIFEST = RAW / "_manifest.jsonl"
FACTS = V2 / "docs/probes/skatteverket_facts.json"
UT = V2 / "docs/probes/universum_ar_for_ar.json"

BAS = "https://www.skatteverket.se"
PAUS = 1.2          # artig paus mot en publik myndighetssajt

_MANADER = {"januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
            "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11,
            "december": 12}
_DATUM = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MANADER) + r")(?:\s+(\d{4}))?\b", re.I)
_AVNOT = re.compile(r"avnoterad|avnotering|avregistrerad", re.I)
_NYNOT = re.compile(r"ny\s+notering|nynotering", re.I)
_NAMN = re.compile(r"namnändring\s+från\s+(.+?)\s+till\s+(.+?)(?:\s+\d|\.|$)", re.I)


def _tagbort(s: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", s))


def tabeller(h: str) -> list:
    ut = []
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", h, re.S | re.I):
        rader = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S | re.I):
            celler = [_tagbort(c).strip() for c in
                      re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(1), re.S | re.I)]
            if celler:
                rader.append(celler)
        if rader:
            ut.append(rader)
    return ut


def sv_datum(text: str, fallback_ar: int):
    m = _DATUM.search(text)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)) if m.group(3) else fallback_ar,
                             _MANADER[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def tolka(h: str):
    """Bolagssidans HTML -> overlevnadsfakta. None om strukturen inte matchar."""
    t = tabeller(h)
    if not t or not t[0]:
        return None
    rubrik = [x.strip().lower() for x in t[0][0]]
    if rubrik[:2] != ["år", "kommentarer"]:
        return None
    rader = t[0][1:]
    if not rader:
        return None
    statustext = rader[0][1] if len(rader[0]) > 1 else ""
    # ORDNING KRITISK: 'avnoterad' innehåller 'noterad' som delsträng
    if re.search(r"\bavnoterad\b", statustext, re.I):
        status = "avnoterad"
    elif re.search(r"\bnoterad\b", statustext, re.I):
        status = "noterad"
    else:
        status = "okänd"
    handelser, namnbyten = [], []
    for r in rader[1:]:
        if len(r) < 2 or not r[0].strip():
            continue
        try:
            ar = int(r[0].strip())
        except ValueError:
            continue
        txt = r[1].strip()
        d = sv_datum(txt, ar)
        nm = _NAMN.search(txt)
        if nm:
            namnbyten.append({"fran": nm.group(1).strip(), "till": nm.group(2).strip(),
                              "datum": d, "ar": ar})
            typ = "namnändring"
        elif _AVNOT.search(txt):
            typ = "avnotering"
        elif _NYNOT.search(txt):
            typ = "notering"
        else:
            typ = "övrigt"
        handelser.append({"ar": ar, "datum": d, "typ": typ, "text": txt})
    avn = next((e for e in handelser if e["typ"] == "avnotering"), None)
    if status == "noterad":
        avn = None                      # statusraden är facit
    not_ = [e for e in handelser if e["typ"] == "notering"]
    forsta = min(not_, key=lambda e: (e["ar"], e["datum"] or "")) if not_ else None
    sista_ar = max((e["ar"] for e in handelser), default=None)
    forsta_ar = min((e["ar"] for e in handelser), default=None)
    return {"status": status,
            "avnoterad_datum": avn["datum"] if avn else None,
            "avnoterad_ar": avn["ar"] if avn else None,
            "avnoterad_orsak": avn["text"] if avn else None,
            "forsta_notering": forsta["datum"] if forsta else None,
            "forsta_notering_ar": forsta["ar"] if forsta else None,
            "forsta_ar_i_historiken": forsta_ar, "sista_ar_i_historiken": sista_ar,
            "namnbyten": namnbyten, "n_handelser": len(handelser)}


def index_bolag() -> list:
    idx = json.loads((LEGACY_CACHE / "_company_index.json").read_text(encoding="utf-8"))
    ut = []
    for x in idx:
        u = x.get("url", "")
        if "/aktiehistorik/" not in u or "beskrivning" in u:
            continue
        m = re.search(r"/([^/]+)\.4\.[0-9a-f]+\.html$", u)
        if m:
            ut.append({"namn": x.get("name"), "url": u, "slug": m.group(1)})
    return ut


def _cachade() -> dict:
    """slug -> sokvag, fran legacyns cache och v2:s eget radalager."""
    ut = {}
    for f in LEGACY_CACHE.glob("_probe_*_html.html"):
        m = re.match(r"_probe_(.+?)_4_", f.name)
        if m:
            ut.setdefault(m.group(1), f)
    for f in PAGES.glob("*.html"):
        ut.setdefault(f.stem.split("__")[0], f)
    return ut


def cmd_parse() -> None:
    bolag = index_bolag()
    cache = _cachade()
    fakta, utan_html, oparsbara = {}, [], []
    for b in bolag:
        p = cache.get(b["slug"])
        if p is None:
            utan_html.append(b)
            continue
        f = tolka(p.read_text(encoding="utf-8", errors="replace"))
        if f is None:
            oparsbara.append(b["slug"])
            continue
        fakta[b["slug"]] = dict(f, namn=b["namn"], url=b["url"])
    FACTS.parent.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(fakta, indent=1, ensure_ascii=False), encoding="utf-8")
    n_avn = sum(1 for v in fakta.values() if v["status"] == "avnoterad")
    print(f"index: {len(bolag)} bolag")
    print(f"tolkade: {len(fakta)}  (varav avnoterade {n_avn}, noterade "
          f"{sum(1 for v in fakta.values() if v['status']=='noterad')}, "
          f"okänd {sum(1 for v in fakta.values() if v['status']=='okänd')})")
    print(f"saknar HTML: {len(utan_html)}   ej tolkbar struktur: {len(oparsbara)}")
    print(f"artefakt: {FACTS}")


def cmd_fetch(gräns: int = 0) -> None:
    import requests
    bolag = index_bolag()
    cache = _cachade()
    saknas = [b for b in bolag if b["slug"] not in cache]
    if gräns:
        saknas = saknas[:gräns]
    PAGES.mkdir(parents=True, exist_ok=True)
    print(f"hämtar {len(saknas)} bolagssidor, {PAUS}s paus → ~{len(saknas)*PAUS/60:.0f} min")
    ok = fel = 0
    for i, b in enumerate(saknas, 1):
        url = BAS + b["url"] if b["url"].startswith("/") else b["url"]
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": "momentum-v2-research/1.0"})
        except Exception as e:  # noqa: BLE001
            fel += 1
            print(f"  [{i}/{len(saknas)}] {b['slug']}: FEL {type(e).__name__}")
            time.sleep(PAUS)
            continue
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rec = {"hamtad_utc": ts, "url": url, "slug": b["slug"], "namn": b["namn"],
               "http_status": r.status_code, "sha256": None, "n_bytes": len(r.content),
               "fil": None, "ok": r.status_code == 200}
        if r.status_code == 200:
            # VERBATIM: exakt de bytes som togs emot, hashade på samma bytes
            fn = PAGES / f"{b['slug']}__{ts}.html"
            fn.write_bytes(r.content)
            rec["sha256"] = hashlib.sha256(r.content).hexdigest()
            rec["fil"] = fn.name
            ok += 1
        else:
            fel += 1
        with MANIFEST.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if i % 100 == 0:
            print(f"  [{i}/{len(saknas)}] ok={ok} fel={fel}", flush=True)
        time.sleep(PAUS)
    print(f"klart: {ok} hämtade, {fel} fel")


# ---------------------------------------------------------------- build ----
def _normnamn(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(publ\.?\)|\bpubl\b", " ", s)
    s = re.sub(r"\b(ab|abp|asa|a/s|plc|inc|oyj|holding|group|series|serie)\b", " ", s)
    s = re.sub(r"\bser(ie)?\.?\s*[a-d]\b", " ", s)
    s = re.sub(r"[^a-z0-9åäöéü ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cmd_build() -> None:
    fakta = json.loads(FACTS.read_text(encoding="utf-8"))
    akt = json.loads((EOD / "active_catalogue.json").read_text(encoding="utf-8"))
    avn = json.loads((EOD / "delisted_catalogue.json").read_text(encoding="utf-8"))
    print(f"Skatteverket-fakta: {len(fakta)} bolag | EODHD aktiva {len(akt)}, "
          f"avnoterade {len(avn)}")

    eod_idx = {}
    for grupp, lst in (("active", akt), ("delisted", avn)):
        for x in lst:
            n = _normnamn(x.get("Name"))
            if n:
                eod_idx.setdefault(n, []).append(dict(x, _grupp=grupp))

    def eod_traff(namn: str):
        return eod_idx.get(_normnamn(namn), [])

    # sista handelsdag per EODHD-kod (avnoterade)
    import gzip
    sista = {}
    for x in avn:
        p = EOD / "delisted/eod" / f"{x['Code']}.json.gz"
        if not p.exists():
            continue
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if d:
            sista[x["Code"]] = {"forsta": d[0]["date"], "sista": d[-1]["date"], "n": len(d)}

    rep = {"skatteverket_bolag": len(fakta), "eodhd_aktiva": len(akt),
           "eodhd_avnoterade": len(avn), "ar": {}}
    print("\n" + "=" * 104)
    print("AVNOTERINGAR PER ÅR ENLIGT SKATTEVERKET, MOT EODHD-ARKIVET")
    print("=" * 104)
    print(f"{'år':>5} {'SKV avnot.':>11} {'i EODHD':>9} {'saknas':>8} {'täckn':>7} "
          f"{'m. prisserie':>13} {'serie täcker avnot.dag':>23}")
    for ar in range(2010, 2027):
        skv = [v for v in fakta.values() if v["status"] == "avnoterad"
               and v["avnoterad_ar"] == ar]
        traff, med_serie, tacker = 0, 0, 0
        saknade = []
        for b in skv:
            t = eod_traff(b["namn"])
            if not t:
                saknade.append(b["namn"])
                continue
            traff += 1
            koder = [x["Code"] for x in t if x["_grupp"] == "delisted" and x["Code"] in sista]
            if koder:
                med_serie += 1
                d = sista[koder[0]]
                if b["avnoterad_datum"] and d["sista"] >= (b["avnoterad_datum"][:10]
                                                           if b["avnoterad_datum"] else ""):
                    tacker += 1
                elif not b["avnoterad_datum"]:
                    tacker += 1
        n = len(skv)
        print(f"{ar:>5} {n:>11} {traff:>9} {n-traff:>8} "
              f"{(100*traff/n if n else 0):>6.0f}% {med_serie:>13} {tacker:>23}")
        rep["ar"][str(ar)] = {"skv_avnoteringar": n, "i_eodhd": traff, "saknas": n - traff,
                              "med_prisserie": med_serie, "serie_tacker_avnoteringsdag": tacker,
                              "exempel_saknade": saknade[:8]}

    print("\n" + "=" * 104)
    print("UNIVERSUMSTORLEK PER ÅR (noterade vid årets slut enligt Skatteverket)")
    print("=" * 104)
    print(f"{'år':>5} {'SKV noterade':>13} {'varav i EODHD':>15} {'täckning':>10}")
    for ar in range(2010, 2027):
        lev = []
        for v in fakta.values():
            fn = v["forsta_notering_ar"] or v["forsta_ar_i_historiken"]
            if fn is None or fn > ar:
                continue
            if v["status"] == "avnoterad" and v["avnoterad_ar"] and v["avnoterad_ar"] < ar:
                continue
            lev.append(v)
        t = sum(1 for v in lev if eod_traff(v["namn"]))
        print(f"{ar:>5} {len(lev):>13} {t:>15} {(100*t/len(lev) if lev else 0):>9.0f}%")
        rep["ar"][str(ar)].update({"skv_noterade": len(lev), "noterade_i_eodhd": t})

    UT.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    kmd = sys.argv[1] if len(sys.argv) > 1 else "parse"
    if kmd == "parse":
        cmd_parse()
    elif kmd == "fetch":
        cmd_fetch(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    elif kmd == "build":
        cmd_build()
    else:
        print(__doc__)
