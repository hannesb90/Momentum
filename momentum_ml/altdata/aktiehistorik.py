"""
altdata/aktiehistorik.py – Skatteverkets aktiehistorik som källa för HISTORISK
överlevnad: notering-/avnoteringsdatum + orsak (uppköp/konkurs/fusion) BAKÅT i
tiden – den lucka den framåtbyggande liggaren (avanza.audit ->
results/universe_survival.csv) per definition inte kan fylla.

KÄLLVAL (av fyra föreslagna: FI börsinformation, Nasdaqs börsmeddelanden,
Bolagsverket, Skatteverkets aktiehistorik) – Skatteverket FÖRST:
  1. Täcker enligt sin egen beskrivning SAMTLIGA aktier på Nasdaq Stockholm,
     NGM Main Regulated, First North, Spotlight och NGM Nordic SME –
     INKLUSIVE redan avnoterade bolag (SAS, HQ och Corem Kelly verifierades
     ha egna sidor via webbsökning).
  2. Innehåller enligt samma beskrivning noterings-/avnoteringshändelser med
     orsakskommentarer – exakt fälten ett survivorship-facit behöver.
  3. Publikt, ingen inloggning.
FI (rapporthistorik), Nasdaq (exakta sista handelsdagar/observationsstatus)
och Bolagsverket (juridiska händelser) är KOMPLEMENT – byggs efter att denna
källa visat sig bära. En källa i taget, verifierad hela vägen.

VERIFIERAT från molnmiljön: bara att sidorna EXISTERAR (webbsökning).
INTE VERIFIERAT: sidornas HTML-struktur – molnsandlådans proxy blockerar
skatteverket.se (CONNECT 403), så kommandona nedan är SCHEMA-UPPTÄCKANDE
och körs på Pi:n. Samma disciplin som avanza.probe/borsdata.py: ingen
parser skrivs mot ett format ingen har sett. Extraktionssteget (bygga
data/historical_survival.csv) läggs till FÖRST efter en skarp probe-dump.

Alla hämtade sidor sparas permanent i cache/aktiehistorik/ – historiska
händelser ändras inte, och Skatteverket ska inte behöva serva om samma sida
(artig paus mellan anrop av samma skäl).

    python -m altdata.aktiehistorik probe_index           # A-Ö-sidornas länkstruktur
    python -m altdata.aktiehistorik probe <url>            # EN bolagssidas struktur (t.ex. SAS)
    python -m altdata.aktiehistorik dump_table sas [i]     # EN tabell fullständigt, otrunkerat
    python -m altdata.aktiehistorik facts sas              # extract_survival_facts(), läsvänligt
    python -m altdata.aktiehistorik build_index            # huvudsida+9 undersidor -> _company_index.json
    python -m altdata.aktiehistorik match_survival [seg]    # namnmatcha vårt universum mot indexet (LOKALT, 0 nätanrop)
"""
import html as _html
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Startsida (verifierad EXISTERA via webbsökning – en kort och en lång
# URL-variant förekommer; den korta är den stabila kanoniska ingången).
INDEX_URL = "https://www.skatteverket.se/privat/skatter/vardepapper/aktiehistorik.html"
# Känd bolagssida att röktesta mot (verifierad existera via webbsökning;
# SAS är dessutom en av våra kända döda tickers – perfekt facit-kandidat).
EXAMPLE_URL = ("https://www.skatteverket.se/privat/skatter/vardepapper/"
               "aktiehistorik/s/sas.4.dfe345a107ebcc9baf80009498.html")

# VERIFIERAT PROBLEM (skarp körning på Pi:n): en identifierande, icke-
# webbläsarlik User-Agent ("Mozilla/5.0 (Momentum research; ...)") gav
# ConnectionResetError från skatteverket.se – samma Pi når Avanza/Yahoo/
# GitHub problemfritt, så det är riktat mot just den här klienten (en WAF/
# brandvägg som stänger anslutningen på icke-webbläsarsignaler), inte ett
# nätverksfel. Sidorna är offentlig, oautentiserad myndighetsinformation
# (ingen inloggning, inget kringgås) – en vanlig webbläsar-UA + fullständiga
# standardheaders (det en riktig webbläsare alltid skickar) är rimligt för
# att alls kunna läsa dem, inte ett försök att dölja vad vi gör.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
_PAUSE_S = 1.0   # artigare än Avanza-pausen – myndighetssajt, ingen brådska

_EVENT_KW_RE = re.compile(
    r"avnoter|noter(?:a[dt]|ing)|nynoter|börsintroduk|uppköp|budet|bud på|"
    r"konkurs|likvidation|fusion|tvångsinlösen|inlösen|sista dag|"
    r"avregistrer|upplös",
    re.I,
)

# Session (inte engångs-requests.get): en del WAF:er kräver en cookie satt
# vid FÖRSTA träffen innan de släpper igenom efterföljande sidor – en
# session bär den cookien automatiskt mellan anrop, engångsanrop gjorde inte det.
_session = requests.Session()
_session.headers.update(_HEADERS)


def _cache_dir() -> Path:
    return Path(config.anchor("cache")) / "aktiehistorik"


def _http_get(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"kunde inte hämta {url}: {last}")


def _strip_tags(markup: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    # stdlib-unescape hanterar ALLA entiteter (&Aring;/&aring;/&#229;/...) –
    # manuell ersättningslista missade versalvarianterna
    s = _html.unescape(s).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s)


def _extract_tables(html: str) -> List[List[List[str]]]:
    """Rå tabell-dump: [tabell][rad][cell]. Används både av probens
    strukturutskrift och (sedan tre skarpa exempel – SAS/HQ/AAK – verifierat
    ett konsekvent mönster) av extract_survival_facts() nedan."""
    tables = []
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S | re.I):
            cells = [_strip_tags(c).strip()
                     for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(1), re.S | re.I)]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _extract_links(html: str) -> List[Tuple[str, str]]:
    """(href, länktext) för alla a-taggar – för att kartlägga A-Ö-indexet."""
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = _strip_tags(m.group(2)).strip()
        if text:
            out.append((m.group(1), text))
    return out


# ── Extraktion (VERIFIERAT mot tre skarpa exempel: SAS, HQ, AAK) ─────────────
# Tabell 0 ("Namnändringar och notering på lista") har ALLTID en statusrad
# UTAN årtal överst ('Aktien är avnoterad' / 'Aktien är noterad på ...') –
# den enda signal som behövs för levande/avnoterad, ingen datumtolkning
# krävs för STATUS. Följande rader (MED årtal) beskriver historiska
# händelser; dag+månad står ofta i kommentar-cellen UTAN årtal (året tas då
# från 'År'-kolumnen) – verifierat exakt: SAS '13 augusti' + År=2024 ->
# 2024-08-13 (riktig avnotering); HQ 'den 22 december. ... den 14 december
# 2017 ...' -> regexen tar FÖRSTA datumträffen ('22 december', utan eget
# årtal, får 2017 från kolumnen) = 2017-12-22 (den RIKTIGA avnoteringen),
# INTE det andra datumet i samma cell (handelsstoppets startdag).
_MONTHS_SV = {"januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
             "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11,
             "december": 12}
_DATE_RE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_SV) + r")(?:\s+(\d{4}))?\b", re.I)
_DELIST_RE = re.compile(r"avnoterad|avnotering|avregistrerad", re.I)
_RELIST_RE = re.compile(r"ny\s+notering|nynotering", re.I)
_NAMECHANGE_RE = re.compile(r"namnändring\s+från\s+(.+?)\s+till\s+(.+?)(?:\s+\d|\.|$)", re.I)


def _parse_sv_date(text: str, fallback_year: int) -> Optional[str]:
    """'13 augusti' + fallback_year 2024 -> '2024-08-13'. Ogiltiga datum
    (t.ex. felräknad skottdag) returnerar None – gissar aldrig ett datum."""
    import datetime
    m = _DATE_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS_SV[m.group(2).lower()]
    year = int(m.group(3)) if m.group(3) else fallback_year
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_survival_facts(html: str) -> Optional[dict]:
    """En bolagssidas HTML -> {status, delisted_date, delisted_reason,
    first_listed_date, name_changes, events}. Returnerar None om sidans
    struktur INTE matchar det verifierade mönstret (tabell 0:s rubrikrad
    != ['År','Kommentarer']) – flaggas då för manuell granskning i stället
    för att tyst läsa fel tabell som om den vore notering/avnotering."""
    tables = _extract_tables(html)
    if not tables or not tables[0]:
        return None
    header = [h.strip().lower() for h in tables[0][0]]
    if header[:2] != ["år", "kommentarer"]:
        return None
    rows = tables[0][1:]
    if not rows:
        return None

    status_text = rows[0][1] if len(rows[0]) > 1 else ""
    # ORDNING KRITISK: 'avnoterad' innehåller självt delsträngen 'noterad',
    # så 'avnoterad' måste kollas FÖRST – annars läses varje avnoterat
    # bolag felaktigt som 'noterad'.
    if re.search(r"\bavnoterad\b", status_text, re.I):
        status = "avnoterad"
    elif re.search(r"\bnoterad\b", status_text, re.I):
        status = "noterad"
    else:
        status = "okänd"

    events, name_changes = [], []
    for r in rows[1:]:
        if len(r) < 2 or not r[0].strip():
            continue
        try:
            year = int(r[0].strip())
        except ValueError:
            continue
        comment = r[1].strip()
        date = _parse_sv_date(comment, year)
        nm = _NAMECHANGE_RE.search(comment)
        if nm:
            name_changes.append({"from": nm.group(1).strip(), "to": nm.group(2).strip(),
                                 "date": date, "year": year})
            etype = "namnändring"
        elif _DELIST_RE.search(comment):
            etype = "avnotering"
        elif _RELIST_RE.search(comment):
            etype = "notering"
        else:
            etype = "övrigt"
        events.append({"year": year, "date": date, "type": etype, "text": comment})

    # Rad-ordningen på sidan är NYAST FÖRST (verifierat i alla tre exempel)
    # -> första 'avnotering'-träffen i listordning är den SENASTE/RIKTIGA
    # avnoteringen, inte en äldre (t.ex. en tidigare avnoterad preferensaktie).
    delisting = next((e for e in events if e["type"] == "avnotering"), None)
    listings = [e for e in events if e["type"] == "notering"]
    first_listing = min(listings, key=lambda e: (e["year"], e["date"] or "")) if listings else None

    return {
        "status": status,
        "delisted_date": delisting["date"] if delisting else None,
        "delisted_reason": delisting["text"] if delisting else None,
        "first_listed_date": first_listing["date"] if first_listing else None,
        "name_changes": name_changes,
        "events": events,
    }


def _save(name: str, content: str) -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(content, encoding="utf-8")
    return p


def _slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", url.rsplit("/", 1)[-1].lower())[:60]


def dump_table(name_or_url: str, table_index: int = 0) -> None:
    """Skriver ut EN tabell FULLSTÄNDIGT, otrunkerat (probe() klipper celler
    vid 28 tecken – bara för kompakt översikt, inte för att designa
    datumextraktion mot). Läser ur cache/aktiehistorik/ om bolaget redan
    probats (INGET nytt nätanrop) – annars hämtas och sparas det på nytt.
    name_or_url: antingen en full URL (som probe()), eller bara ett
    igenkännbart fragment av ett redan cachat filnamn (t.ex. 'sas' eller
    'hq') – då används den cachade filen direkt.

        python -m altdata.aktiehistorik dump_table sas       # tabell 0 (notering)
        python -m altdata.aktiehistorik dump_table sas 2      # tabell 2 (övrigt)
    """
    cached = None
    if not name_or_url.startswith("http"):
        matches = sorted(_cache_dir().glob(f"_probe_*{name_or_url.lower()}*.html"))
        if matches:
            cached = matches[0]
    if cached:
        print(f"[dump_table] läser cachad {cached} (inget nätanrop)")
        html = cached.read_text(encoding="utf-8")
    else:
        url = name_or_url if name_or_url.startswith("http") else None
        if url is None:
            print(f"Ingen cachad sida matchar '{name_or_url}' i {_cache_dir()} – ange en full URL.")
            return
        print(f"[dump_table] hämtar {url}")
        html = _http_get(url)
        _save(f"_probe_{_slug(url)}.html", html)

    tables = _extract_tables(html)
    if table_index >= len(tables):
        print(f"Bara {len(tables)} tabell(er) hittades (index 0-{len(tables) - 1}).")
        return
    rows = tables[table_index]
    print(f"[dump_table] tabell {table_index}: {len(rows)} rader, FULLSTÄNDIG text:\n")
    for i, r in enumerate(rows):
        marker = "RUBRIK" if i == 0 else f"rad {i}"
        print(f"  [{marker}]")
        for cell in r:
            print(f"    {cell!r}")
        print()


def facts(name_or_url: str) -> None:
    """Kör extract_survival_facts() mot en bolagssida och skriver ut resultatet
    läsvänligt – samma cache-först-princip som dump_table (inget nytt
    nätanrop om sidan redan probats).

        python -m altdata.aktiehistorik facts sas
        python -m altdata.aktiehistorik facts hq
    """
    cached = None
    if not name_or_url.startswith("http"):
        matches = sorted(_cache_dir().glob(f"_probe_*{name_or_url.lower()}*.html"))
        if matches:
            cached = matches[0]
    if cached:
        print(f"[facts] läser cachad {cached} (inget nätanrop)")
        html = cached.read_text(encoding="utf-8")
    elif name_or_url.startswith("http"):
        print(f"[facts] hämtar {name_or_url}")
        html = _http_get(name_or_url)
        _save(f"_probe_{_slug(name_or_url)}.html", html)
    else:
        print(f"Ingen cachad sida matchar '{name_or_url}' i {_cache_dir()} – ange en full URL.")
        return

    f = extract_survival_facts(html)
    if f is None:
        print("  KUNDE INTE TOLKAS – tabell 0:s rubrikrad matchade inte "
              "['År','Kommentarer']. Flaggas för manuell granskning, ingen gissning.")
        return
    print(f"  status:            {f['status']}")
    print(f"  avnoterad:         {f['delisted_date'] or '–'}")
    if f["delisted_reason"]:
        print(f"    orsak: {f['delisted_reason']}")
    print(f"  första notering:   {f['first_listed_date'] or '–'}")
    if f["name_changes"]:
        print("  namnbyten:")
        for nc in f["name_changes"]:
            print(f"    {nc['date'] or nc['year']}: '{nc['from']}' -> '{nc['to']}'")
    print(f"\n  alla {len(f['events'])} händelser:")
    for e in f["events"]:
        print(f"    {e['date'] or e['year']:<12} [{e['type']:<12}] {e['text'][:90]}")


# Kända A-Ö-undersidor – VERIFIERADE ORDAGRANT ur skarp probe_index-körning
# (hrefs, inte gissade/konstruerade). Ligger under en 'aktiehistorik/'-KATALOG,
# skild från FILEN 'aktiehistorik.html' som INDEX_URL pekar mot – därför
# hårdkodade hela vägen i stället för att härleda ur INDEX_URL.
_SUBPAGE_BASE = "https://www.skatteverket.se/privat/skatter/vardepapper/aktiehistorik/"
SUBPAGE_URLS = [_SUBPAGE_BASE + suffix for suffix in (
    "df.4.6fdde64a12cc4eee23080001707.html", "gi.4.6fdde64a12cc4eee23080001567.html",
    "jl.4.6fdde64a12cc4eee23080001646.html", "mo.4.6fdde64a12cc4eee23080001845.html",
    "pr.4.6fdde64a12cc4eee23080001932.html", "su.4.6fdde64a12cc4eee23080001938.html",
    "vy.4.6fdde64a12cc4eee23080002417.html", "zo.4.6fdde64a12cc4eee23080002494.html",
    "09.4.6fdde64a12cc4eee23080002541.html",
)]

# Länkar som INTE är bolagssidor (navigations-/metalänkar, verifierade texter
# ur skarp körning) – filtreras bort innan bokstavsanalysen nedan.
_NAV_LINK_TEXTS = {"aktiehistorik", "beskrivning av aktiehistoriken",
                   "mer information om aktiehistoriken och v",
                   "d–f", "g–i", "j–l", "m–o", "p–r", "s–u", "v–y", "z–ö", "0–9"}


def probe_index() -> None:
    """Hämtar startsidan (cache-först, som dump_table/facts) och dumpar
    länkstrukturen – svarar DEFINITIVT (bokstavsfördelning över ALLA
    extraherade länkar, inte bara de första 60 som skrevs ut förra
    körningen) på: täcker huvudsidan hela alfabetet, eller krävs
    SUBPAGE_URLS för B/C-Ö? Ingen tolkning av enskilda bolag än."""
    cached = _cache_dir() / "_probe_index.html"
    if cached.exists():
        print(f"[probe_index] läser cachad {cached} (inget nätanrop)")
        html = cached.read_text(encoding="utf-8")
    else:
        print(f"[probe_index] hämtar {INDEX_URL}")
        html = _http_get(INDEX_URL)
        _save("_probe_index.html", html)

    links = _extract_links(html)
    ak_links = [(h, t) for h, t in links if "aktiehistorik" in h.lower()
               and t.strip().lower() not in _NAV_LINK_TEXTS]
    print(f"  {len(links)} länkar totalt, {len(ak_links)} bolagslänkar "
          f"(navigations-/metalänkar borträknade)")

    from collections import Counter
    first_letters = Counter(t.strip()[0].upper() for h, t in ak_links if t.strip())
    print(f"\n  Bokstavsfördelning (VISAR om huvudsidan täcker hela alfabetet "
          f"eller om SUBPAGE_URLS krävs):")
    for letter in sorted(first_letters):
        print(f"    {letter}: {first_letters[letter]} bolag")
    missing = sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ") - set(first_letters))
    if missing:
        print(f"\n  INGA bolag på huvudsidan för: {', '.join(missing)} – dessa MÅSTE "
              f"hämtas via SUBPAGE_URLS.")
    else:
        print(f"\n  Huvudsidan täcker HELA alfabetet – SUBPAGE_URLS kan vara redundanta "
              f"(verifiera ändå: dubbletter är ofarliga, en krävd bokstav som saknas är inte det).")
    print(f"\n  rå HTML: {cached if cached.exists() else _cache_dir() / '_probe_index.html'}")


def _company_links_from(html: str) -> List[Tuple[str, str]]:
    """(bolagsnamn, href) ur en index-/undersidas HTML – nav-/metalänkar och
    tomma länktexter (verifierat: en enstaka nolledd-blankstegslänk finns på
    huvudsidan, brus) filtreras bort."""
    out = []
    for h, t in _extract_links(html):
        if "aktiehistorik" not in h.lower():
            continue
        name = t.strip()
        if not name or name.lower() in _NAV_LINK_TEXTS:
            continue
        out.append((name, h))
    return out


def crawl_index() -> List[Tuple[str, str]]:
    """Kombinerar huvudsidan (A-C, VERIFIERAT i skarp körning) + de 9
    SUBPAGE_URLS (D-Ö+0-9, VERIFIERAT nödvändiga – huvudsidan saknar dem
    helt) till EN fullständig (bolagsnamn, href)-lista, deduplicerad på
    href. Cache-först per sida (samma princip som övriga kommandon) – en
    redan hämtad sida hämtas ALDRIG om, ingen paus behövs då."""
    seen, all_links = set(), []

    idx_cache = _cache_dir() / "_probe_index.html"
    if idx_cache.exists():
        html = idx_cache.read_text(encoding="utf-8")
    else:
        html = _http_get(INDEX_URL)
        _save("_probe_index.html", html)
    for name, href in _company_links_from(html):
        if href not in seen:
            seen.add(href)
            all_links.append((name, href))

    for url in SUBPAGE_URLS:
        cache_file = _cache_dir() / f"_sub_{_slug(url)}.html"
        if cache_file.exists():
            sub_html = cache_file.read_text(encoding="utf-8")
        else:
            sub_html = _http_get(url)
            _save(f"_sub_{_slug(url)}.html", sub_html)
            time.sleep(_PAUSE_S)
        for name, href in _company_links_from(sub_html):
            if href not in seen:
                seen.add(href)
                all_links.append((name, href))

    return all_links


def build_index() -> None:
    """Kör crawl_index() och sparar HELA bolagslistan till cache/
    aktiehistorik/_company_index.json – grunden för nästa steg
    (namnmatchning mot vårt ticker-universum). Visar bokstavsfördelningen
    igen som en SLUTGILTIG sanity-check – ska nu vara hela A-Ö, inga
    saknade bokstäver (annars är täckningen ofullständig och något är fel)."""
    links = crawl_index()
    print(f"[build_index] {len(links)} bolag totalt (huvudsida + {len(SUBPAGE_URLS)} undersidor)")

    from collections import Counter
    first_letters = Counter(n[0].upper() for n, _ in links if n)
    missing = sorted(set("ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ") - set(first_letters))
    print()
    for letter in sorted(first_letters):
        print(f"    {letter}: {first_letters[letter]}")
    if missing:
        print(f"\n  VARNING: fortfarande saknade bokstäver: {', '.join(missing)} – "
              f"täckningen är INTE komplett, undersök innan nästa steg.")
    else:
        print(f"\n  Full A-Ö-täckning bekräftad.")

    out = _cache_dir() / "_company_index.json"
    out.write_text(json.dumps([{"name": n, "url": h} for n, h in links],
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  sparad: {out}")


# ── Namnmatchning (vårt universum -> Skatteverkets index) ────────────────────
# HELT LOKAL (0 nätanrop) – matchar mot den redan hämtade _company_index.json.
# Skatteverket verkar indexera varje bolag under dess NUVARANDE namn (AAK:s
# sida nås via 'aak.html' trots att bolaget historiskt hetat 'BNS Industri
# AB' – namnbytet ligger inbäddat som HISTORIK på sidan, inte som en egen
# indexpost). Juridiska suffix (AB/(publ)/Ltd/ASA/A-S/Inc/Corp/Holding/...)
# och aktieklasser ('Class B') skiljer sig ofta mellan vår universum-CSV
# (FinanceDatabase) och Skatteverkets skrivsätt – normaliseras bort innan
# jämförelse. Verifierat manuellt att Å/Ä-luckan i build_index() är ett
# äkta nollresultat (inga sådana bolag), inte ett filtreringsfel.
_SUFFIX_WORDS = {"ab", "publ", "asa", "as", "ltd", "limited", "inc", "corp",
                 "corporation", "holding", "holdings", "group", "plc", "se",
                 "nv", "ag", "oyj", "aktiebolag", "aktiebolaget", "spa", "sa",
                 # instrumentbeskrivande ord (ej bolagsidentitet) - samma
                 # PREF/BTA-mönster som avanza.py:s _INSTRUMENT_SEG_RE redan
                 # känner igen på tickernivå, verifierat mot skarpa exempel
                 # ('ALM Equity AB Pref.shs', 'AlzeCure Pharma AB TEMP',
                 # 'Autoliv Inc. SDB') där dessa ord blockerade en annars
                 # exakt matchning
                 "pref", "temp", "sdb", "shs"}


def _normalize_name(name: str) -> str:
    """Bolagsnamn -> jämförbar kärna: gemener, danska 'A/S' hopslaget till
    ett ord, aktieklass ('Class B') och juridiska suffix upprepat strippade
    från BÅDA ändarna tills inget mer går bort ('X AB (publ)' kräver två
    pass: strippa 'publ', sedan 'ab'; 'AB Electrolux (publ)' och
    'Aktiebolaget Fastator (publ)' är verkliga fall där suffixet står
    FÖRST istället – verifierat mot skarp match_survival-körning där dessa
    annars bara blev osäkra delsträngsträffar istället för bekräftade)."""
    n = (name or "").strip().lower()
    n = re.sub(r"\ba/s\b", " as ", n)
    n = re.sub(r"[().,]", " ", n)
    n = re.sub(r"\bclass\s+[a-zåäö]\b", " ", n)
    tokens = n.split()
    while tokens and tokens[-1] in _SUFFIX_WORDS:
        tokens.pop()
    while tokens and tokens[0] in _SUFFIX_WORDS:
        tokens.pop(0)
    return " ".join(tokens)


def _match_index(name: str, index_by_norm: dict) -> Tuple[Optional[dict], Optional[dict]]:
    """(bekräftad_träff, bästa_osäkra) mot ett {normaliserat_namn: [poster]}-
    uppslag. Bekräftad = EXAKT normaliserad likhet. Osäker fallback = det
    KORTARE namnets ORD (hela tokens, inte tecken) förekommer som en
    SAMMANHÄNGANDE svit i det längre namnet – FLAGGAS osäker, används
    aldrig tyst som om den vore bekräftad (samma lärdom som avanza.py:s
    Eagle Football Group-fall: gissa aldrig tyst).

    Ordbaserad matchning istället för teckendelsträng: en skarp
    match_survival-körning visade att 'DNO ASA Class A' (normaliserat
    'dno') annars char-delsträngsmatchade mot 'AddNode Group AB'
    (normaliserat 'addnode', som råkar innehålla bokstäverna d-n-o i rad)
    – två helt orelaterade bolag. Ordgränser tar bort den brusfällan utan
    att offra legitima fall som 'Bygghemma Group' vs 'Bygghemma Group
    First'."""
    key = _normalize_name(name)
    if not key:
        return None, None
    exact = index_by_norm.get(key)
    if exact:
        return exact[0], None
    key_tokens = key.split()
    for other_key, entries in index_by_norm.items():
        other_tokens = other_key.split()
        if not key_tokens or not other_tokens:
            continue
        shorter, longer = (key_tokens, other_tokens) if len(key_tokens) <= len(other_tokens) else (other_tokens, key_tokens)
        if shorter == longer or sum(len(w) for w in shorter) < 3:
            continue
        n = len(shorter)
        for i in range(len(longer) - n + 1):
            if longer[i:i + n] == shorter:
                return None, entries[0]
    return None, None


def match_survival(segment: Optional[str] = None) -> None:
    """Matchar VÅRT ticker-universum mot Skatteverkets redan hämtade
    bolagsindex (cache/aktiehistorik/_company_index.json, byggd av
    build_index()) – HELT LOKAL strängmatchning, INGET nätanrop, snabbt
    även mot 1650 bolag.

    segment: 'large'/'small'/'quality' ELLER None (default – HELA
    universumet oavsett handelssegment, eftersom döda/avnoterade tickers
    per definition inte hör hemma i något aktuellt marknadsvärde-segment).

    Sparar cache/aktiehistorik/ticker_match.json: {ticker: {name, url,
    confirmed}}. Extraktionssteget (hämta varje bekräftad matchnings sida
    + extract_survival_facts(), det NÄTVERKSTUNGA steget) byggs separat och
    läser BARA confirmed:true-poster – samma regel som avanza.extract()
    lärde sig dyrt att inte hoppa över (osäkra träffar extraherades
    tidigare tyst, tills en riktig felmatchning upptäcktes).

        python -m altdata.aktiehistorik match_survival
        python -m altdata.aktiehistorik match_survival large
    """
    idx_path = _cache_dir() / "_company_index.json"
    if not idx_path.exists():
        print(f"Ingen {idx_path} – kör 'build_index' först.")
        return
    index = json.loads(idx_path.read_text(encoding="utf-8"))
    index_by_norm: dict = {}
    for e in index:
        k = _normalize_name(e["name"])
        if k:
            index_by_norm.setdefault(k, []).append(e)

    from data.data_loader import load_sweden_universe
    market_cap = None
    if segment:
        seg_cfg = config.SEGMENTS.get(segment)
        market_cap = seg_cfg["market_cap"] if seg_cfg else config.QUALITY_MARKET_CAP
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=market_cap)

    result = {}
    confirmed = uncertain = none = 0
    for t in tickers:
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        name = name_map.get(t, t)
        hit, fallback = _match_index(name, index_by_norm)
        if hit:
            result[t] = {"name": hit["name"], "url": hit["url"], "confirmed": True}
            confirmed += 1
        elif fallback:
            result[t] = {"name": fallback["name"], "url": fallback["url"], "confirmed": False}
            uncertain += 1
        else:
            none += 1

    out = _cache_dir() / "ticker_match.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[match_survival] {confirmed} bekräftade, {uncertain} osäkra, {none} utan träff "
          f"(av {len(tickers)} tickers, segment={segment or 'hela universumet'}) -> {out}")
    if uncertain:
        print(f"\n  {min(uncertain, 20)} exempel på osäkra (granska/förbättra normaliseringen vid behov):")
        n = 0
        for t, v in result.items():
            if not v["confirmed"]:
                print(f"    {t:<16} vårt namn={name_map.get(t, t)!r:<40} "
                      f"Skatteverket={v['name']!r}")
                n += 1
                if n >= 20:
                    break


def probe(url: Optional[str] = None) -> None:
    """Hämtar EN bolagssida och dumpar strukturen: titel, tabeller (rubriker +
    första rader) och alla textrader som matchar händelse-nyckelord
    (avnoter/konkurs/uppköp/...). Default: SAS – känd avnoterad ticker i vårt
    universum, dvs. ett facit vi kan korsverifiera liggaren mot."""
    url = url or EXAMPLE_URL
    print(f"[probe] hämtar {url}")
    html = _http_get(url)
    slug = re.sub(r"[^a-z0-9]+", "_", url.rsplit("/", 1)[-1].lower())[:60]
    raw = _save(f"_probe_{slug}.html", html)

    tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    print(f"  titel: {_strip_tags(tm.group(1)).strip() if tm else '(saknas)'}")

    tables = _extract_tables(html)
    print(f"  {len(tables)} tabell(er):")
    for i, rows in enumerate(tables, 1):
        print(f"\n  --- tabell {i}: {len(rows)} rader, "
              f"{max(len(r) for r in rows)} kolumner som mest ---")
        for r in rows[:6]:
            print(f"    | {' | '.join(c[:28] for c in r)}")
        if len(rows) > 6:
            print(f"    ... och {len(rows) - 6} rader till")

    text = _strip_tags(html)
    hits = [ln.strip() for ln in text.splitlines()
            if ln.strip() and _EVENT_KW_RE.search(ln)]
    print(f"\n  {len(hits)} textrad(er) med händelse-nyckelord "
          f"(avnoter/konkurs/uppköp/fusion/notera/...):")
    for ln in hits[:25]:
        print(f"    • {ln[:160]}")
    if len(hits) > 25:
        print(f"    ... och {len(hits) - 25} till")

    print(f"\n  rå HTML sparad: {raw}")
    print("  Klistra in utskriften – extraktionssteget (historical_survival.csv) "
          "byggs FÖRST mot den faktiska strukturen, inte gissad.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "probe_index":
        probe_index()
    elif cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "dump_table":
        if len(sys.argv) < 3:
            print("Ange bolag/URL: python -m altdata.aktiehistorik dump_table sas [tabell-index]")
            return
        idx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        dump_table(sys.argv[2], idx)
    elif cmd == "facts":
        if len(sys.argv) < 3:
            print("Ange bolag/URL: python -m altdata.aktiehistorik facts sas")
            return
        facts(sys.argv[2])
    elif cmd == "build_index":
        build_index()
    elif cmd == "match_survival":
        match_survival(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
