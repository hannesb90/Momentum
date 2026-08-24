"""instrument_master: historiskt instrumentregister for samtliga Skatteverket-bolag.

Fristaende v2-kod. Legacy lases READ-ONLY. Skriver bara under momentum_v2/.

Steg:
  1. Full tolkning av Skatteverkets bolagssidor: namn, ORGANISATIONSNUMMER,
     status, notering, avnotering + orsak, namnbyten, corporate actions och
     BYTESTABELLEN (uppkop/fusion -> efterfoljande bolag).
  2. Identifierarindex ur legacy: borsapi (namn/isin/ticker), MFN (isins/tickers),
     Borsdata (namn/isin/ticker), EODHD (Code/Name/Isin, aktiva + avnoterade).
  3. Upplosningskedja per bolag, med metod och sakerhet registrerad per rad:
        ISIN via namn -> EODHD via ISIN   (starkast)
        historiskt namn / efterfoljarnamn -> samma kedja
        direkt namnmatch mot EODHD (exakt, darefter fuzzy)
  4. missing_price_history: avnoterade bolag utan prisserie nagonstans.
"""
from __future__ import annotations

import difflib
import glob
import gzip
import html as H
import json
import re
import sys
from collections import Counter
from pathlib import Path

LEGACY = Path("/home/hannesb/momentum_prod_work/momentum_ml")
LC = LEGACY / "cache"
EOD = LC / "eodhd_archive/ST"
V2 = Path("/home/hannesb/momentum_v2")
PAGES = V2 / "raw/skatteverket/pages"
LEG_PAGES = LC / "aktiehistorik"
MASTER = V2 / "docs/probes/instrument_master.json"
SAKNAS = V2 / "docs/probes/missing_price_history.json"

_MAN = {"januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
        "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11,
        "december": 12}
_DATUM = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MAN) + r")(?:\s+(\d{4}))?\b", re.I)
_AVNOT = re.compile(r"avnoterad|avnotering|avregistrerad", re.I)
_NYNOT = re.compile(r"ny\s+notering|nynotering", re.I)
_NAMN = re.compile(r"namnändring\s+från\s+(.+?)\s+till\s+(.+?)(?:\s+\d|\.|$)", re.I)
_ORG = re.compile(r"[Oo]rganisationsnummer[^0-9]{0,60}(\d{6})-?(\d{4})")


def _txt(h: str) -> str:
    return H.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\xa0", " ")


def _tabeller(h: str) -> list:
    ut = []
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", h, re.S | re.I):
        rader = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S | re.I):
            c = [_txt(x).strip() for x in
                 re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(1), re.S | re.I)]
            if c:
                rader.append(c)
        if rader:
            ut.append(rader)
    return ut


def _sv_datum(text: str, ar: int):
    m = _DATUM.search(text)
    if not m:
        return None
    import datetime
    try:
        return datetime.date(int(m.group(3)) if m.group(3) else ar,
                             _MAN[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def tolka_sida(h: str) -> dict | None:
    t = _tabeller(h)
    hs = next((tb for tb in t if [x.strip().lower() for x in tb[0]][:2] == ["år", "kommentarer"]),
              None)
    if hs is None or len(hs) < 2:
        return None
    txt = _txt(h)
    mo = _ORG.search(txt)
    orgnr = f"{mo.group(1)}-{mo.group(2)}" if mo else None

    statustext = hs[1][1] if len(hs[1]) > 1 else ""
    if re.search(r"\bavnoterad\b", statustext, re.I):
        status = "avnoterad"
    elif re.search(r"\bnoterad\b", statustext, re.I):
        status = "noterad"
    else:
        status = "okänd"

    handelser, namnbyten = [], []
    for r in hs[2:]:
        if len(r) < 2 or not r[0].strip():
            continue
        try:
            ar = int(r[0].strip())
        except ValueError:
            continue
        s = r[1].strip()
        d = _sv_datum(s, ar)
        nm = _NAMN.search(s)
        if nm:
            namnbyten.append({"fran": nm.group(1).strip(), "till": nm.group(2).strip(), "ar": ar})
            typ = "namnändring"
        elif _AVNOT.search(s):
            typ = "avnotering"
        elif _NYNOT.search(s):
            typ = "notering"
        else:
            typ = "övrigt"
        handelser.append({"ar": ar, "datum": d, "typ": typ, "text": s})
    avn = next((e for e in handelser if e["typ"] == "avnotering"), None)
    if status == "noterad":
        avn = None
    nots = [e for e in handelser if e["typ"] == "notering"]
    forsta = min(nots, key=lambda e: (e["ar"], e["datum"] or "")) if nots else None

    # bytestabell: "Aktie | Anledning | Nummer", rader "X - Y | Byte | SKV M ..."
    byten = []
    bt = next((tb for tb in t if [x.strip().lower() for x in tb[0]][:2] == ["aktie", "anledning"]),
              None)
    if bt:
        for r in bt[1:]:
            if len(r) < 2 or not r[0].strip():
                continue
            par = re.split(r"\s+-\s+", r[0])
            byten.append({"fran": par[0].strip(), "till": par[1].strip() if len(par) > 1 else None,
                          "anledning": r[1].strip()})
    return {"orgnr": orgnr, "status": status,
            "avnoterad_datum": avn["datum"] if avn else None,
            "avnoterad_ar": avn["ar"] if avn else None,
            "avnoterad_orsak": (avn["text"][:300] if avn else None),
            "forsta_notering": forsta["datum"] if forsta else None,
            "forsta_notering_ar": forsta["ar"] if forsta else None,
            "forsta_ar": min((e["ar"] for e in handelser), default=None),
            "sista_ar": max((e["ar"] for e in handelser), default=None),
            "namnbyten": namnbyten, "byten": byten, "n_handelser": len(handelser)}


# ------------------------------------------------------------------ namn ---
def norm(s) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(publ\.?\)|\bpubl\b", " ", s)
    s = re.sub(r"\b(ab|abp|asa|a/s|plc|inc|oyj|holding|group|series|serie|the|of|och)\b", " ", s)
    s = re.sub(r"\bser(ie)?\.?\s*[a-d]\b", " ", s)
    s = re.sub(r"[^a-z0-9åäöéü ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def isin_ok(x) -> str | None:
    s = (x or "").strip().upper()
    return s if len(s) == 12 and s[:2].isalpha() else None


def bygg_index() -> dict:
    """namn -> ISIN (flera källor), ISIN -> EODHD-post, namn -> EODHD-post."""
    namn2isin: dict = {}
    isin2eod: dict = {}
    namn2eod: dict = {}
    kallor = Counter()

    for p in sorted(glob.glob(str(LC / "borsapi/companies_all_*.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        for x in (d.get("data") or []):
            z = isin_ok(x.get("isin"))
            n = norm(x.get("name"))
            if z and n:
                namn2isin.setdefault(n, set()).add(z)
                kallor["borsapi"] += 1

    bd = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    for x in bd:
        z = isin_ok(x.get("isin"))
        n = norm(x.get("name"))
        if z and n:
            namn2isin.setdefault(n, set()).add(z)
            kallor["borsdata"] += 1

    for p in glob.glob(str(LC / "mfn/*.json")):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        poster = d.get("items") if isinstance(d, dict) else (d if isinstance(d, list) else [])
        for it in (poster or [])[:6]:
            if not isinstance(it, dict):
                continue
            zs = [isin_ok(z) for z in (it.get("isins") or [])]
            nm = norm(it.get("author_name"))
            for z in zs:
                if z and nm:
                    namn2isin.setdefault(nm, set()).add(z)
                    kallor["mfn"] += 1

    for grupp, fil in (("active", "active_catalogue.json"), ("delisted", "delisted_catalogue.json")):
        for x in json.loads((EOD / fil).read_text(encoding="utf-8")):
            post = {"code": x.get("Code"), "namn": x.get("Name"), "typ": x.get("Type"),
                    "grupp": grupp, "isin": isin_ok(x.get("Isin"))}
            if post["isin"]:
                isin2eod.setdefault(post["isin"], []).append(post)
            n = norm(x.get("Name"))
            if n:
                namn2eod.setdefault(n, []).append(post)
    return {"namn2isin": namn2isin, "isin2eod": isin2eod, "namn2eod": namn2eod,
            "kallor": dict(kallor)}


def los_upp(namn_varianter: list, idx: dict) -> tuple:
    """Returnerar (eod-post, metod). Starkaste kedjan forst."""
    n2i, i2e, n2e = idx["namn2isin"], idx["isin2eod"], idx["namn2eod"]
    for i, nv in enumerate(namn_varianter):
        n = norm(nv)
        if not n:
            continue
        etikett = "eget namn" if i == 0 else "alt. namn"
        for z in n2i.get(n, ()):
            if z in i2e:
                return i2e[z][0], f"ISIN via {etikett}"
        if n in n2e:
            return n2e[n][0], f"exakt namn ({etikett})"
    nycklar = list(n2e)
    for i, nv in enumerate(namn_varianter):
        n = norm(nv)
        if len(n) < 6:
            continue
        nara = difflib.get_close_matches(n, nycklar, n=1, cutoff=0.90)
        if nara:
            return n2e[nara[0]][0], "fuzzy namn"
    return None, None


def har_serie(post: dict) -> dict | None:
    if not post:
        return None
    sub = "delisted" if post["grupp"] == "delisted" else "active"
    p = EOD / sub / "eod" / f"{post['code']}.json.gz"
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if not d:
        return None
    return {"forsta": d[0]["date"], "sista": d[-1]["date"], "n": len(d)}


def alla_sidor() -> dict:
    ut = {}
    for f in PAGES.glob("*.html"):
        ut.setdefault(f.stem.split("__")[0], f)
    for f in LEG_PAGES.glob("_probe_*_html.html"):
        m = re.match(r"_probe_(.+?)_4_", f.name)
        if m:
            ut.setdefault(m.group(1), f)
    return ut


def main() -> None:
    idx_bolag = json.loads((LEG_PAGES / "_company_index.json").read_text(encoding="utf-8"))
    bolag = []
    for x in idx_bolag:
        u = x.get("url", "")
        if "/aktiehistorik/" not in u or "beskrivning" in u:
            continue
        m = re.search(r"/([^/]+)\.4\.[0-9a-f]+\.html$", u)
        if m:
            bolag.append({"namn": x.get("name"), "slug": m.group(1), "url": u})
    sidor = alla_sidor()
    print(f"index {len(bolag)} bolag | sidor tillgängliga {len(sidor)}")

    idx = bygg_index()
    print(f"identifierarindex: namn→ISIN {len(idx['namn2isin'])} namn "
          f"(källor {idx['kallor']}), ISIN→EODHD {len(idx['isin2eod'])}, "
          f"namn→EODHD {len(idx['namn2eod'])}")

    master, metoder = [], Counter()
    for b in bolag:
        p = sidor.get(b["slug"])
        f = tolka_sida(p.read_text(encoding="utf-8", errors="replace")) if p else None
        rad = {"slug": b["slug"], "namn": b["namn"], "url": b["url"]}
        if f is None:
            rad["status"] = "ej tolkbar"
            master.append(rad)
            metoder["ej tolkbar sida"] += 1
            continue
        rad.update(f)
        varianter = [b["namn"]]
        for nb in f["namnbyten"]:
            varianter += [nb.get("fran"), nb.get("till")]
        for by in f["byten"]:
            varianter += [by.get("fran")]
        efterfoljare = [by.get("till") for by in f["byten"] if by.get("till")]
        post, metod = los_upp([v for v in varianter if v], idx)
        if post is None and efterfoljare:
            post, metod = los_upp(efterfoljare, idx)
            if post:
                metod = f"efterföljare ({metod})"
        rad["eodhd"] = post
        rad["metod"] = metod
        rad["serie"] = har_serie(post)
        metoder[metod or "INGEN TRÄFF"] += 1
        master.append(rad)

    MASTER.write_text(json.dumps(master, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nUPPLÖSNINGSMETOD ({len(master)} bolag):")
    for k, v in metoder.most_common():
        print(f"  {str(k):34s} {v:>5d}")

    avn = [r for r in master if r.get("status") == "avnoterad"]
    utan = [r for r in avn if not r.get("serie")]
    print(f"\navnoterade: {len(avn)} | utan prisserie i EODHD: {len(utan)}")
    print(f"{'år':>5} {'avnot.':>7} {'m. serie':>9} {'utan serie':>11} {'täckn':>7}")
    per_ar = {}
    for ar in range(2010, 2027):
        g = [r for r in avn if r.get("avnoterad_ar") == ar]
        med = [r for r in g if r.get("serie")]
        print(f"{ar:>5} {len(g):>7} {len(med):>9} {len(g)-len(med):>11} "
              f"{(100*len(med)/len(g) if g else 0):>6.0f}%")
        per_ar[ar] = {"avnoterade": len(g), "med_serie": len(med),
                      "utan_serie": len(g) - len(med)}
    SAKNAS.write_text(json.dumps(
        {"per_ar": per_ar,
         "bolag": [{"slug": r["slug"], "namn": r["namn"], "orgnr": r.get("orgnr"),
                    "avnoterad_datum": r.get("avnoterad_datum"),
                    "avnoterad_ar": r.get("avnoterad_ar"),
                    "avnoterad_orsak": (r.get("avnoterad_orsak") or "")[:160],
                    "metod": r.get("metod")} for r in utan]},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefakter: {MASTER}\n            {SAKNAS}")


if __name__ == "__main__":
    sys.exit(main())
