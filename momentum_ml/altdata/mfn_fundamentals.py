"""
altdata/mfn_fundamentals.py – Regex-extraherar HÅRDA finansiella siffror
direkt ur MFN-pressmeddelandenas text: nettoomsättning, EBIT, EBITDA,
resultat efter skatt, resultat per aktie, rörelsemarginal. Ingen AI, inget
nätanrop – bara mönstermatchning mot vanliga svenska rapporteringsfraser
("Nettoomsättningen uppgick till 125,3 (110,2) Mkr").

SYFTE: undersöka om vi kan täcka hela eller delar av Börsdata Pro+ GRATIS
genom att plocka siffrorna som redan finns i MFN-texten, i stället för att
betala för/sätta upp Börsdata-API:et. Resten (det regex missar) kan fyllas
manuellt.

ÄRLIGT (inte gissat): täckningen beror HELT på om bolaget klistrar in sin
fulla rapportnarrativ i själva MFN-PM:et eller bara publicerar en kort
announcement + PDF-länk (se mfn_fetch.py:s 'types'-kommando). Denna modul
kan ALDRIG läsa en PDF-bilaga. Regelmönstren är byggda på kända svenska
IR-rapporteringskonventioner, INTE verifierade mot ett stort urval riktiga
MFN-texter – kör själv:

    python -m altdata.mfn_fundamentals selftest large   # TRÄFFGRAD mot din cache
    python -m altdata.mfn_fundamentals extract large    # bygg fundamentals_from_mfn.csv

Låg träffgrad (selftest) = detta duger bara som gap-filler eller inte alls,
kör Börsdata/manuell inmatning i stället. Hög träffgrad = kan bära en stor
del av hård-datan gratis.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# ── Nummer/enhet-mönster (svensk notation: komma decimal, ev. mellanslag som
# tusentalsavgränsare, ev. minustecken) ────────────────────────────────────
# OBS: [  ] (mellanslag/hårt mellanslag) – INTE \s. \s matchar även \n/\t,
# vilket i skarp körning fångade en rad-brytning MITT I ett tal (HTML-tabell
# stripad till text) och kraschade _parse_num ("2\n271", "-8\n.8"). Ett riktigt
# tal spänner aldrig en radbrytning.
_NUM = r"-?\d[\d  ]*(?:,\d+)?"
_UNIT = r"Mkr|MSEK|mkr|msek|tkr|TSEK|kkr|miljoner kronor"
# "ökade/minskade/steg/föll" tar ofta en "med X%"-klausul FÖRE "till" ("ökade
# med 12,4% till 125,3 Mkr") – vanligare i verklig text än verbet + "till"
# direkt (upptäckt genom selftest mot skarp cache: revenue hade en misstänkt
# LÄGRE träffgrad än net_profit/ebit trots att omsättning nästan alltid nämns
# – detta var orsaken, inte att siffran saknades).
_CONNECT = (
    r"uppgick till"
    rf"|(?:ökade|minskade|steg|föll)(?:\s+med\s+{_NUM}\s*%)?\s+till"
    r"|blev|var|på"
)
# Etiketten följs ibland av en parentetisk förkortning ("Rörelseresultatet
# (EBIT) uppgick till...") och/eller en periods-kvalificerare ("...för
# perioden/kvartalet uppgick till...") innan konnektorn.
_LABEL_TAIL = r"(?:\s*\([^)]{1,15}\))?(?:\s+för\s+(?:perioden|kvartalet|räkenskapsåret|helåret))?\s+"


def _num_pattern(label_alts: str) -> re.Pattern:
    """'<etikett> uppgick till 125,3 (110,2) Mkr' – svensk IR-konvention: enheten
    kommer EFTER både aktuell siffra och jämförelseperioden i parentes, inte
    direkt efter den första siffran. Jämförelseperioden är valfri."""
    return re.compile(
        rf"\b(?:{label_alts}){_LABEL_TAIL}(?:{_CONNECT})\s+"
        rf"(?P<val>{_NUM})"
        rf"(?:\s*\(\s*(?P<cmp>{_NUM})\s*\))?"
        rf"\s*(?P<unit>{_UNIT})",
        re.I,
    )


_FIELD_PATTERNS: Dict[str, re.Pattern] = {
    "revenue":     _num_pattern(r"nettoomsättning(?:en)?|omsättning(?:en)?"),
    "ebit":        _num_pattern(r"rörelseresultat(?:et)?|EBIT(?!DA)"),
    "ebitda":      _num_pattern(r"EBITDA"),
    "net_profit":  _num_pattern(r"resultat(?:et)? efter skatt|periodens resultat|nettoresultat(?:et)?"),
}
_EPS_RE = re.compile(
    rf"resultat per aktie{_LABEL_TAIL}(?:{_CONNECT})\s+(?P<val>{_NUM})\s*(?:kr|kronor)", re.I)
_MARGIN_RE = re.compile(
    rf"(?:rörelsemarginal(?:en)?|EBIT-marginal(?:en)?){_LABEL_TAIL}(?:{_CONNECT})\s+(?P<val>{_NUM})\s*%", re.I)

# ── Period-detektering ur titeln (svenska IR-titlar är starkt standardiserade) ─
_Q_RE = re.compile(r"\bQ([1-4])\b", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MONTHRANGE_RE = re.compile(r"\b(januari|april|juli|oktober)[\s\-–]+(mars|juni|september|december)\b", re.I)
_FULLYEAR_KW = re.compile(r"bokslutskommuniké|helår(?:et|srapport)?", re.I)
_MONTH_TO_Q = {"januari": "Q1", "april": "Q2", "juli": "Q3", "oktober": "Q4"}

# Rapport-liknande PM (för att inte slösa regex-sökningar på ordernyheter etc.
# och för att selftest ska mäta rätt nämnare). Titlar, inte MFN:s 'type'-fält
# (det senare är inte verifierat – se mfn_fetch.py 'types').
_REPORT_TITLE_RE = re.compile(
    r"delårsrapport|kvartalsrapport|bokslutskommuniké|årsrapport|årsredovisning"
    r"|niomånadersrapport|halvårsrapport|halvårsrapport", re.I)
# En rapport-TITEL fångar även INBJUDNINGAR till presentationen av rapporten
# ("AAK bjuder in till presentation av delårsrapporten...") – dessa nämner
# rapportordet men innehåller per definition ALDRIG siffrorna (upptäckt via
# ett skarpt miss-exempel i selftest, inte en regex-lucka att laga). Utesluts
# explicit så nämnaren mäter faktiska rapport-PM, inte inbjudningar till dem.
_INVITATION_TITLE_RE = re.compile(
    r"bjuder in till|inbjuder till|inbjudan till|kallar till\s+(?:telefon|press)", re.I)


def _parse_num(s: str) -> float:
    return float(s.replace(" ", "").replace("\xa0", "").replace(",", "."))


def is_report_pm(item: dict) -> bool:
    title = str(item.get("title") or "")
    return bool(_REPORT_TITLE_RE.search(title)) and not _INVITATION_TITLE_RE.search(title)


def detect_period(title: str) -> Optional[str]:
    year_m = _YEAR_RE.search(title)
    year = year_m.group(1) if year_m else None
    q_m = _Q_RE.search(title)
    if q_m:
        return f"Q{q_m.group(1)} {year}" if year else f"Q{q_m.group(1)}"
    mr = _MONTHRANGE_RE.search(title)
    if mr:
        q = _MONTH_TO_Q.get(mr.group(1).lower())
        if q:
            return f"{q} {year}" if year else q
    if _FULLYEAR_KW.search(title):
        return f"Helår {year}" if year else "Helår"
    return None


def extract_hard_facts(text: str) -> Dict[str, dict]:
    """{"revenue": {"value": 125.3, "unit": "Mkr", "prior_period": 110.2}, ...}
    Tomt dict om inget matchar (vanligast för PM som bara länkar en PDF)."""
    if not text:
        return {}
    out: Dict[str, dict] = {}
    for field, pat in _FIELD_PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        # Defensivt: en regex-träff garanterar inte ett parsbart tal (t.ex. ett
        # okänt HTML-strippnings-artefakt vi inte förutsett) – ett fält som inte
        # går att tolka ska hoppas över, aldrig krascha hela extraktionen.
        try:
            val = _parse_num(m.group("val"))
        except ValueError:
            continue
        d = {"value": val, "unit": m.group("unit")}
        if m.group("cmp"):
            try:
                d["prior_period"] = _parse_num(m.group("cmp"))
            except ValueError:
                pass
        out[field] = d
    m = _EPS_RE.search(text)
    if m:
        try:
            out["eps"] = {"value": _parse_num(m.group("val")), "unit": "kr"}
        except ValueError:
            pass
    m = _MARGIN_RE.search(text)
    if m:
        try:
            out["ebit_margin_pct"] = {"value": _parse_num(m.group("val"))}
        except ValueError:
            pass
    return out


def _report_items(segment: Optional[str]) -> List[dict]:
    """Alla rapport-liknande PM i cachen (oavsett OOS-fönster – detta är inte
    en backtest-signal, bara datainsamling)."""
    from data.data_loader import load_sweden_universe
    seg = config.SEGMENTS.get(segment) if segment else None
    seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    cache_dir = Path(config.MFN_CACHE_DIR)
    out, seen = [], set()
    for t in tickers:
        p = cache_dir / f"{t}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in d.get("items", []):
            if it.get("id") in seen or not is_report_pm(it):
                continue
            seen.add(it.get("id"))
            it = dict(it)
            it["ticker"] = t
            out.append(it)
    return out


def selftest(segment: Optional[str] = None) -> None:
    """Mäter FAKTISK träffgrad mot redan hämtad cache. Inget nätanrop."""
    items = _report_items(segment)
    if not items:
        print("Inga rapport-liknande PM i cachen – kör mfn_fetch.py fetch <segment> först.")
        return
    hit, miss = 0, 0
    field_hits: Counter = Counter()
    miss_example = None
    hit_example = None
    for it in items:
        facts = extract_hard_facts(it.get("text") or "")
        if facts:
            hit += 1
            for f in facts:
                field_hits[f] += 1
            if hit_example is None:
                hit_example = (it, facts)
        else:
            miss += 1
            if miss_example is None:
                miss_example = it

    n = len(items)
    print(f"[mfn_fundamentals selftest] {n:,} rapport-liknande PM".replace(",", " "))
    print(f"  Minst 1 fält extraherat: {hit:,} ({hit / n:.0%})".replace(",", " "))
    print(f"  Inget extraherat (troligen bara 'se bifogad PDF'): {miss:,} ({miss / n:.0%})"
          .replace(",", " "))
    print("\n  Träffar per fält:")
    for f, c in field_hits.most_common():
        print(f"    {f:<16}{c:>6}  ({c / n:.0%})")

    if hit_example:
        it, facts = hit_example
        print(f"\n  Exempel PÅ TRÄFF ({it.get('ticker')}, {it.get('published', '')[:10]}): "
              f"'{it.get('title', '')[:60]}'")
        for f, d in facts.items():
            extra = f" (fg. period {d['prior_period']})" if "prior_period" in d else ""
            print(f"    {f}: {d['value']} {d.get('unit', '')}{extra}")
    if miss_example:
        print(f"\n  Exempel PÅ MISS ({miss_example.get('ticker')}, "
              f"{miss_example.get('published', '')[:10]}): '{miss_example.get('title', '')[:60]}'")
        txt = miss_example.get("text") or ""
        print(f"    text ({len(txt)} tecken): {txt[:200]}")

    print("\n  Dom: hög träffgrad (>60-70%) -> bär en stor del av hård-datan gratis, fyll")
    print("  resten manuellt. Låg träffgrad -> de flesta bolag länkar bara en PDF här;")
    print("  Börsdata (eller manuell inmatning för ett litet urval nyckelbolag) behövs.")


def extract(segment: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Bygger <segmentets results_dir>/fundamentals_from_mfn.csv av alla lyckade
    extraktioner. VIKTIGT: skriver till segmentets EGEN results_dir (samma
    mönster som resten av pipelinen: results/ för large, results/small/ för
    small) – en tidigare version skrev alltid till samma fil oavsett segment,
    så 'extract small' körd efter 'extract large' skrev tyst över den."""
    items = _report_items(segment)
    rows = []
    for it in items:
        facts = extract_hard_facts(it.get("text") or "")
        if not facts:
            continue
        row = {"ticker": it.get("ticker"), "published": it.get("published"),
               "period": detect_period(it.get("title") or ""), "pm_id": it.get("id"),
               "title": it.get("title")}
        for field, d in facts.items():
            row[field] = d.get("value")
            row[f"{field}_unit"] = d.get("unit", "")
            if "prior_period" in d:
                row[f"{field}_prior"] = d["prior_period"]
        rows.append(row)

    if not rows:
        print("Inga extraherade rader – kör 'selftest' först för att se varför.")
        return

    cols = ["ticker", "published", "period", "pm_id", "title"]
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)

    if out_path:
        out = Path(out_path)
    else:
        seg = config.SEGMENTS.get(segment) if segment else None
        seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
        out = Path(config.anchor(seg["results_dir"])) / "fundamentals_from_mfn.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[extract] {len(rows)} rader ({len(items)} rapport-PM genomsökta, "
          f"{len(rows) / max(len(items), 1):.0%} träffgrad) -> {out}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "selftest":
        selftest(seg)
    elif cmd == "extract":
        extract(seg)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
