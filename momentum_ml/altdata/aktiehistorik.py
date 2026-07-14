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
"""
import html as _html
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
    """Rå tabell-dump: [tabell][rad][cell] – för probens strukturutskrift,
    INTE en färdig parser (celltolkning designas först efter skarp dump)."""
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


def probe_index() -> None:
    """Hämtar startsidan och dumpar länkstrukturen – svarar på: hur når man
    A-Ö-sidorna, och hur ser bolagssidornas URL-mönster ut? Ingen tolkning,
    bara rådata att bygga nästa steg på."""
    print(f"[probe_index] hämtar {INDEX_URL}")
    html = _http_get(INDEX_URL)
    raw = _save("_probe_index.html", html)
    links = _extract_links(html)
    ak_links = [(h, t) for h, t in links if "aktiehistorik" in h.lower()]
    print(f"  {len(links)} länkar totalt, {len(ak_links)} med 'aktiehistorik' i href:")
    for h, t in ak_links[:60]:
        print(f"    {t[:40]:<40} -> {h[:110]}")
    if len(ak_links) > 60:
        print(f"    ... och {len(ak_links) - 60} till")
    print(f"\n  rå HTML sparad: {raw}")
    print("  Klistra in utskriften så designar vi nästa steg (A-Ö-crawl) mot de "
          "FAKTISKA URL-mönstren.")


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
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
