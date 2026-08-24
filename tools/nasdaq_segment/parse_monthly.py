"""Nasdaq 'Equity Trading by Company and Instrument' — enhetlig parser, stdlib only.

Verifierat mot tva argangar 14 ar isar: 2012-03 (.xls, OLE2/BIFF8) och
2025-11 (.xlsx, OOXML). BADA anvander SAMMA instrumentlayout:

    Instrument | Company Code | Orderbook Code | ISIN | Instrument Type |
    Segment | Industry | Supersector | ... | Currency | Location | Delisted

Endast headerradens position skiljer (5 mot 6) och en stavrattning
("Indsutry" -> "Industry"). Segment ar ett FALT i bada. Delisted ar ett
avnoteringsDATUM (Excel-serial), inte en flagga.

VARNING OM BLADVAL: arbetsboken innehaller ett ANNAT blad ("Main Market
Trading Details") vars TITELRAD ocksa lyder "Instrument Trading Details".
Det bladet ar bolagsnivat, saknar ISIN och har Segment som BANDRAD. Blad
maste darfor kopplas via r:id mot workbook.xml.rels — positionsbaserad
mappning valjer tyst fel blad. BAND_LAYOUT-grenen finns kvar enbart som
skyddsnat om nagon argang skulle sakna instrumentbladet.

Kastar SchemaOkand om ingen epok kan faststallas. Gissar aldrig.

Kor: /opt/momentum/venv/bin/python tools/nasdaq_segment/parse_monthly.py <fil> [...]
"""
from __future__ import annotations
import hashlib, json, pathlib, re, sys, zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ole2 import OLE2
import biff8

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
SEGMENT = ("Large Cap", "Mid Cap", "Small Cap")
ARKNAMN = "Instrument Trading Details"


class SchemaOkand(Exception):
    pass


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _excel_datum(v):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return (date(1899, 12, 30) + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- inlasning
def _las_xlsx(p: pathlib.Path):
    z = zipfile.ZipFile(p)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{NS}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    # Bladnamn maste kopplas via r:id -> workbook.xml.rels. Positionsbaserad
    # mappning (sheet1.xml, sheet2.xml, ...) ar INTE tillforlitlig: i Nasdaqs
    # filer har flera blad samma titelrad, sa fel blad kan valjas tyst.
    RELNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    ark = {}
    for s in wb.iter(f"{NS}sheet"):
        nm = s.get("name")
        mal = rels.get(s.get(RELNS + "id"))
        if not mal:
            continue
        path = mal if mal.startswith("xl/") else "xl/" + mal.lstrip("/")
        if path not in z.namelist():
            continue
        rader = []
        for row in ET.fromstring(z.read(path)).iter(f"{NS}row"):
            c = []
            for cell in row.iter(f"{NS}c"):
                v = cell.find(f"{NS}v"); t = cell.get("t")
                c.append(ss[int(v.text)] if (t == "s" and v is not None)
                         else (v.text if v is not None else ""))
            rader.append(c)
        ark[nm] = rader
    return ark


def _las_xls(p: pathlib.Path):
    blad = biff8.parse(OLE2(p.read_bytes()).read("Workbook"))
    ark = {}
    for b in blad:
        c = b["cells"]
        if not c:
            ark[b["name"]] = []; continue
        maxr = max(r for r, _ in c); maxc = max(x for _, x in c)
        ark[b["name"]] = [[c.get((r, k), "") for k in range(maxc + 1)] for r in range(maxr + 1)]
    return ark


# ---------------------------------------------------------------- epokdetektor
def detektera_epok(rader):
    for i, r in enumerate(rader[:40]):
        n = [_norm(x) for x in r]
        if "isin" in n and "segment" in n:
            return "ISIN_SEGMENT_COLUMNS", i
    for i, r in enumerate(rader[:40]):
        n = [_norm(x) for x in r]
        if any("issuer" in x for x in n) and any("orderbook" in x for x in n):
            return "BAND_LAYOUT", i
    raise SchemaOkand("varken ISIN_SEGMENT_COLUMNS- eller BAND_LAYOUT-header hittad i de forsta 40 raderna")


# ---------------------------------------------------------------- parsers
def _legacy(rader, hrad):
    kol = {}
    for i, h in enumerate(rader[hrad]):
        n = _norm(h)
        for nyckel, mons in (("instrument", "instrument"), ("company_code", "company code"),
                             ("orderbook_code", "orderbook code"), ("isin", "isin"),
                             ("instrument_type", "instrument type"), ("segment", "segment"),
                             ("location", "loca- tion"), ("delisted", "delisted")):
            if n == mons or n.replace("- ", "").replace("-", "") == mons.replace("- ", "").replace("-", ""):
                kol.setdefault(nyckel, i)
    saknas = {"instrument", "isin", "segment", "location", "instrument_type"} - set(kol)
    if saknas:
        raise SchemaOkand(f"ISIN_SEGMENT_COLUMNS saknar kolumner: {sorted(saknas)}")
    ut = []
    for r in rader[hrad + 1:]:
        g = lambda k: (str(r[kol[k]]).strip() if k in kol and kol[k] < len(r) else "")
        if not g("instrument"):
            continue
        ut.append({"instrument": g("instrument"), "company_code": g("company_code"),
                   "orderbook_code": g("orderbook_code"), "isin": g("isin"),
                   "instrument_type": g("instrument_type"), "segment": g("segment"),
                   "location": g("location"), "delisted": _excel_datum(g("delisted"))})
    return ut


def _modern(rader, hrad):
    kol = {}
    for i, h in enumerate(rader[hrad]):
        n = _norm(h)
        if "issuer" in n: kol["company_code"] = i
        elif "orderbook" in n: kol["orderbook_code"] = i
        elif n.replace("- ", "").replace("-", "") == "location": kol["location"] = i
    if "location" not in kol or "orderbook_code" not in kol:
        raise SchemaOkand("BAND_LAYOUT saknar location/orderbook")
    namnkol = min(kol.values()) - 1
    ut, segment = [], None
    for r in rader[hrad + 1:]:
        c0 = str(r[0]).strip() if r else ""
        if c0 in SEGMENT:
            segment = c0; continue
        g = lambda k: (str(r[kol[k]]).strip() if k in kol and kol[k] < len(r) else "")
        namn = str(r[namnkol]).strip() if namnkol < len(r) else ""
        if not namn or not g("location") or segment is None:
            continue
        ut.append({"instrument": namn, "company_code": g("company_code"),
                   "orderbook_code": g("orderbook_code"), "isin": None,
                   "instrument_type": None, "segment": segment,
                   "location": g("location"), "delisted": None})
    return ut


# ---------------------------------------------------------------- publikt API
def parse(path) -> dict:
    p = pathlib.Path(path)
    m = re.search(r"_(\d{2})(\d{2})\.(xls|xlsx)$", p.name, re.I)
    manad = f"20{m.group(1)}-{m.group(2)}" if m else None
    ark = _las_xlsx(p) if p.suffix.lower() == ".xlsx" else _las_xls(p)
    rader = ark.get(ARKNAMN)
    if rader is None:
        tr = [k for k in ark if _norm(ARKNAMN) in _norm(k)]
        if not tr:
            raise SchemaOkand(f"arket '{ARKNAMN}' saknas (finns: {list(ark)})")
        rader = ark[tr[0]]
    epok, hrad = detektera_epok(rader)
    poster = _legacy(rader, hrad) if epok == "ISIN_SEGMENT_COLUMNS" else _modern(rader, hrad)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    for x in poster:
        x.update({"snapshot_month": manad, "schema_epoch": epok,
                  "source_filename": p.name, "sha256": sha})
    return {"file": str(p), "snapshot_month": manad, "schema_epoch": epok,
            "header_row": hrad, "sha256": sha, "n_rows": len(poster), "rows": poster}


def sto_stock(poster):
    """Kanoniskt filter: Stockholm, aktie, cap-segment.
    I MODERN-epoken saknas instrument_type; arket innehaller enligt Nasdaqs egen
    not endast Shares, sa villkoret utelamnas da i stallet for att gissa."""
    ut = []
    for x in poster:
        if x["location"] != "STO":
            continue
        if x["segment"] not in SEGMENT:
            continue
        if x["schema_epoch"] == "ISIN_SEGMENT_COLUMNS" and x["instrument_type"] != "Stock":
            continue
        ut.append(x)
    return ut


if __name__ == "__main__":
    for f in sys.argv[1:]:
        try:
            r = parse(f)
        except SchemaOkand as e:
            print(f"SCHEMA_OKAND {f}: {e}"); continue
        s = sto_stock(r["rows"])
        from collections import Counter
        print(f"{r['snapshot_month']}  epok {r['schema_epoch']:6s} headerrad {r['header_row']:>2}  "
              f"rader {r['n_rows']:>4}  STO+aktie+cap {len(s):>3}  "
              f"{dict(Counter(x['segment'] for x in s))}")
        d = [x for x in s if x["delisted"]]
        if d:
            print(f"     avnoterade under manaden: {len(d)} — "
                  f"{[(x['orderbook_code'], x['delisted']) for x in d[:5]]}")
        print(f"     isin-tackning: {sum(1 for x in s if x['isin'])}/{len(s)}")
