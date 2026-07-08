"""
altdata/mfn_fetch.py – Hämtar regulatoriska pressmeddelanden från MFN.se och
cachar dem point-in-time (med publiceringstidsstämpel) för en ärlig backtest.

MFN exponerar en ren JSON Feed (jsonfeed.org-stil):
    https://mfn.se/all/s?query=<q>&lang=sv&limit=500   (content-type application/json)
paginerad via "next_url". Varje item:
    news_id, url, author{slug,name,tickers,isins}, properties{lang,type,tags},
    content{publish_date, title, preamble, html, text}        ← fälten NÄSTLADE i content
Vi plockar id/datum/rubrik/ren-text och bolags-tickers, och filtrerar bort
fri-text-brus (PM som bara NÄMNER bolaget) genom att matcha author mot ticker/namn.

VIKTIGT – körs på Pi:n (molncontainern når varken mfn.se eller Yahoo).

    python altdata/mfn_fetch.py probe "Saab"     # rök-test mot feeden (gratis)
    python altdata/mfn_fetch.py one  "Saab" SAAB-B.ST   # ett bolag, filtrerat på ticker
    python altdata/mfn_fetch.py fetch large      # hela segmentet (cachas per ticker)
    python altdata/mfn_fetch.py stats            # PM/dag mätt på redan hämtad cache (inget nätanrop)
    python altdata/mfn_fetch.py types             # PM eller även rapporter? typ-fördelning + exempel
    python altdata/mfn_fetch.py raw "AAK"         # rå feed-dump: finns en PDF-länk vi missar?
"""
import sys
import re
import json
import time
import html as _html
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:
    requests = None

_UA = "Mozilla/5.0 (Momentum research) python-requests"


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _http_get(url: str, params: Optional[dict] = None, retries: int = 4):
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": _UA,
                             "Accept": "application/json"}, timeout=30)
            if r.status_code == 200:
                return r
            # Kroppen med (inte bara statuskoden) – annars är ett 500 för en
            # specifik query-sträng ogenomskinligt: vi såg ~20-30 bolag 500:a i
            # produktion (t.ex. "Re:NewCell", "Better Collective A/S") utan att
            # veta VARFÖR förrän vi faktiskt läste svarskroppen.
            last = RuntimeError(f"HTTP {r.status_code} för {r.url}: {r.text[:200]}")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 ** i)
    raise last or RuntimeError(f"GET misslyckades: {url}")


# ── Parser (MFN JSON Feed) ────────────────────────────────────────────────────
def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def _coerce(item: dict) -> Optional[dict]:
    """Normaliserar ETT MFN-feed-item → vårt schema (fälten ligger i content)."""
    c = item.get("content") or {}
    author = item.get("author") or {}
    props = item.get("properties") or {}
    pid = item.get("news_id") or item.get("group_id")
    date = c.get("publish_date")
    if not (pid and date):
        return None
    text = c.get("text") or c.get("preamble") or _strip_html(c.get("html", ""))
    # PDF-bilagor (t.ex. hela årsredovisningen när PM:et bara är en kort
    # announcement) – verifierat fältnamn via 'raw'-kommandot mot skarp MFN-
    # data: content.attachments = [{file_title, content_type, url, tags}].
    # Filtrerar på content_type så vi inte plockar upp t.ex. en bifogad bild.
    attachments = [
        {"url": str(a.get("url") or ""), "title": str(a.get("file_title") or ""),
         "tags": a.get("tags") or []}
        for a in (c.get("attachments") or [])
        if a.get("content_type") == "application/pdf" and a.get("url")
    ]
    return {
        "id": str(pid),
        "published": str(date),
        "title": str(c.get("title") or ""),
        "text": (text or "")[: config.MFN_MAX_BODY_CHARS],
        "type": str(props.get("type") or ""),
        "tags": props.get("tags") or [],
        "lang": str(props.get("lang") or config.MFN_LANG),
        "url": str(item.get("url") or ""),
        "author_slug": str(author.get("slug") or ""),
        "author_name": str(author.get("name") or ""),
        "tickers": author.get("tickers") or [],
        "isins": author.get("isins") or [],
        "attachments": attachments,
    }


def _feed_page(url: str, params: Optional[dict]) -> Tuple[List[dict], Optional[str]]:
    r = _http_get(url, params)
    try:
        data = r.json()
    except Exception:
        data = json.loads(r.text)
    return (data.get("items") or []), data.get("next_url")


def _fetch_feed(query: str) -> List[dict]:
    """Följer next_url-pagineringen tills vi nått historik-golvet eller slut."""
    base = config.MFN_BASE_URL.rstrip("/")
    max_pages = int(getattr(config, "MFN_MAX_PAGES", 20))
    hstart = config.START_DATE  # sluta paginera när posterna är äldre än så
    url, params = f"{base}/all/s", {"query": query, "lang": config.MFN_LANG, "limit": 500}
    raw: List[dict] = []
    for _ in range(max_pages):
        items, nxt = _feed_page(url, params)
        if not items:
            break
        raw.extend(items)
        oldest = min(((it.get("content") or {}).get("publish_date") or "9999" for it in items),
                     default="9999")
        if oldest[:10] < hstart:
            break
        if not nxt:
            break
        url, params = (nxt if nxt.startswith("http") else base + nxt), None
        time.sleep(config.MFN_REQUEST_PAUSE_S)
    return raw


# ── Author-matchning (filtrera bort fri-text-brus) ────────────────────────────
def _norm(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _author_match(c: dict, query: str, ticker: Optional[str]) -> bool:
    """Behåll bara PM som faktiskt är BOLAGETS egna (inte sådana som nämner det)."""
    qn = _norm(query)
    sn, nn = _norm(c["author_slug"]), _norm(c["author_name"])
    if sn and (sn in qn or qn in sn):
        return True
    if nn and (nn in qn or qn in nn):
        return True
    if ticker:
        tn = _norm(ticker.split(".")[0])          # "SAAB-B.ST" -> "SAABB"
        for t in c["tickers"]:
            if _norm(t.split(":")[-1]) == tn:     # "XSTO:SAAB B" -> "SAABB"
                return True
    return False


# ── Hämtning + cache ──────────────────────────────────────────────────────────
def fetch_company(query: str, ticker: Optional[str] = None) -> List[dict]:
    raw = _fetch_feed(query)
    out, seen = [], set()
    for it in raw:
        c = _coerce(it)
        if not c or c["id"] in seen:
            continue
        if not _author_match(c, query, ticker):
            continue
        seen.add(c["id"])
        out.append(c)
    return out


def probe(query: str) -> None:
    """Rök-test mot feeden: visar att vi når MFN och att parsern träffar rätt."""
    Path(config.MFN_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    base = config.MFN_BASE_URL.rstrip("/")
    print(f"[probe] frågar MFN-feeden om '{query}'")
    items, nxt = _feed_page(f"{base}/all/s", {"query": query, "lang": config.MFN_LANG, "limit": 500})
    coerced = [c for c in (_coerce(it) for it in items) if c]
    print(f"  {len(items)} feed-items, {len(coerced)} tolkade, next_url={'ja' if nxt else 'nej'}")
    for c in coerced[:3]:
        print(f"   • {c['published'][:10]}  [{c['author_slug']:<18}] {c['tickers']}  {c['title'][:60]}")
    out = Path(config.MFN_CACHE_DIR) / "_probe_feed.json"
    out.write_text(json.dumps(coerced[:5], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  (5 tolkade PM sparade i {out} för granskning)")
    print("  Ser fälten rätt ut (datum/rubrik/author/tickers)? Kör 'fetch'.")


def raw(query: str) -> None:
    """RÅ dump av ETT feed-item – ingen _coerce()-stripning. Svarar på om det
    finns en attachments/files-nyckel med en PDF-länk NÅGONSTANS i strukturen
    (_coerce() plockar i dag bara id/published/title/text/type/tags/lang/url/
    author/tickers/isins – aldrig kollat om mer finns), och om content.html
    innehåller en '<a href="...pdf">'-länk som _strip_html() annars kastar
    bort utan spår. Kör INNAN en fetch-PDF-pipeline byggs – annars gissar vi
    på ett fältnamn. Ett litet, billigt nätanrop (samma som probe())."""
    base = config.MFN_BASE_URL.rstrip("/")
    items, _ = _feed_page(f"{base}/all/s", {"query": query, "lang": config.MFN_LANG, "limit": 5})
    if not items:
        print(f"[raw] inga träffar för '{query}'")
        return
    it = items[0]
    c = it.get("content") or {}
    print(f"[raw] toppnivå-nycklar: {list(it.keys())}")
    print(f"[raw] content-nycklar:  {list(c.keys())}")
    print(f"[raw] author-nycklar:   {list((it.get('author') or {}).keys())}")
    print(f"[raw] properties-nycklar: {list((it.get('properties') or {}).keys())}")

    def _hunt(obj, path=""):
        hits = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if any(kw in k.lower() for kw in ("pdf", "attach", "file", "document", "asset")):
                    hits.append((p, v))
                hits.extend(_hunt(v, p))
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:3]):
                hits.extend(_hunt(v, f"{path}[{i}]"))
        return hits

    hits = _hunt(it)
    if hits:
        print("\n[raw] Fält som LUKTAR pdf/attachment/fil (troligen svaret vi letar efter):")
        for p, v in hits:
            print(f"  {p} = {json.dumps(v, ensure_ascii=False)[:200]}")
    else:
        print("\n[raw] Inget fältnamn innehåller pdf/attachment/fil/document/asset "
              "i det rå feed-itemet.")

    html = c.get("html") or ""
    pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', html, re.I)
    if pdf_links:
        print(f"\n[raw] PDF-länk(ar) hittade INUTI content.html (som _strip_html() idag kastar "
              f"bort helt): {pdf_links}")
    else:
        print("\n[raw] Ingen '.pdf'-länk hittad i content.html.")

    print(f"\n[raw] Fullständigt item för '{it.get('url', '')}':")
    print(json.dumps(it, indent=2, ensure_ascii=False)[:3000])


def _load_map() -> Dict[str, str]:
    """Valfri ticker→MFN-fråga (altdata/mfn_map.csv)."""
    p = Path(__file__).parent / "mfn_map.csv"
    out: Dict[str, str] = {}
    if p.exists():
        import csv
        with open(p, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["ticker"]] = row.get("mfn_query") or row.get("query") or ""
    return out


def _clean_name(name: str) -> str:
    """Kort, sökbart bolagsnamn. MFN:s /all/s ger HTTP 500 för vissa queries –
    särskilt med 'Class A/B'-suffix, '&' och vissa utländska bolagsformer.

    En full-universum-körning (900+ bolag) avslöjade EFTER den första fixen
    (suffix/kolon) ett andra, tydligt mönster i de kvarvarande ~19 felen: MFN:s
    sök kraschar på en ISOLERAD ETT-TECKENS-TOKEN i queryn – bokstav ELLER
    siffra. Alla dessa 500:ade tills tokenet togs bort:
      "...i Norden/Sverige/Skandinavien/Dalarna" (fristående "i", 7 bolag)
      "H M Hennes Mauritz", "L E Lundbergforetagen", "PetroNor E P"
      "Enad Global 7", "Subsea 7" (fristående siffra sist)
      "C-Rad", "I-Tech", "K-Fast Holding" (bindestreck → isolerad bokstav
       efter att bindestrecket blir mellanslag)
    18 av 19 kvarvarande fel förklarades av detta EN mönster (verifierat mot
    hela listan innan denna kod skrevs – se konversationen/committen). Kvar
    okänt: "Case Group", "Wall to Wall Group", "SJR in Scandinavia" – inget
    uppenbart mönster, INTE gissat vidare (_http_get visar nu svarskropp om
    de ska felsökas senare)."""
    n = name
    n = re.sub(r"\bclass\s+[a-d]\b", " ", n, flags=re.I)          # "Class B"
    n = re.sub(r"\bser(ie|ies|\.)?\s*[a-d]\b", " ", n, flags=re.I)  # "Ser./Series B"
    n = re.sub(r"\(publ\.?\)|\bAB\b|\bASA\b|\bOyj\b|\bplc\b|\bInc\b", " ", n, flags=re.I)
    n = n.replace("&", " ").replace(":", " ")                     # bryter MFN-queryn
    n = re.sub(r"\s+", " ", n).strip(" ,.-")
    # Utländska bolagsformer bara i SLUTET av namnet – "AG"/"SE" mitt i en fras
    # kan annars råka klippa ett riktigt ord av misstag.
    n = re.sub(r"\s+(A/S|AG|SE|S\.A\.?)$", "", n, flags=re.I)
    n = n.replace("/", " ")                                        # ev. kvarvarande "/"
    n = n.replace("-", " ")                                        # C-Rad, I-Tech, K-Fast
    # Akronymer typ "M.O.B.A." -> "MOBA" (INTE "Checkin.com" – den matchar inte
    # detta mönster eftersom "com" inte är en enskild bokstav).
    n = re.sub(r"\b(?:[A-Z]\.){2,}", lambda m: m.group(0).replace(".", ""), n)
    # Isolerad ett-tecken-token (bokstav/siffra) som eget "ord" – huvudfixen ovan.
    n = re.sub(r"(?<!\S)\w(?!\S)", "", n)
    return re.sub(r"\s+", " ", n).strip(" ,.-")


# Höjs varje gång _coerce()'s schema växer med ett fält vi vill backfilla
# (senast: 'attachments' för PDF-länkar). fetch_universe() jämför mot detta
# i stället för att bara kolla "finns filen" – annars skulle en cachad fil
# från INNAN attachments-fältet fanns aldrig hämtas om, och köraren skulle
# behöva radera hela cachen manuellt (riskabelt, lätt att göra fel på).
_SCHEMA_VERSION = 2


def _needs_refetch(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 – trasig fil → hämta om
        return True
    return cached.get("schema") != _SCHEMA_VERSION


def fetch_universe(target: str) -> None:
    """target = segmentnamn (large/small) ELLER 'quality' (Small/Micro/Nano för
    fundamental-screenern). Inkrementellt – bolag redan cachade på AKTUELLT
    schema hoppas över; en schema-höjning (se _SCHEMA_VERSION) hämtar om
    automatiskt utan att köraren behöver radera cachen manuellt."""
    from data.data_loader import load_sweden_universe
    if target == "quality":
        market_cap, label = config.QUALITY_MARKET_CAP, "quality (Small/Micro/Nano)"
    else:
        seg = config.SEGMENTS.get(target) or config.SEGMENTS[config.DEFAULT_SEGMENT]
        market_cap, label = seg["market_cap"], seg["label"]
    tickers, sector_map, cap_tier_map, name_map = load_sweden_universe(min_market_cap=market_cap)
    qmap = _load_map()
    cache_dir = Path(config.MFN_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch] {target} ({label}) – {len(tickers)} bolag")
    total = 0
    for i, t in enumerate(tickers, 1):
        # Hoppa fonder/ETF:er – de har inga egna MFN-pressmeddelanden.
        if cap_tier_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        out = cache_dir / f"{t}.json"
        if not _needs_refetch(out):
            continue  # redan cachad på aktuellt schema
        query = qmap.get(t) or _clean_name(name_map.get(t, t))
        try:
            items = fetch_company(query, ticker=t)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>4}/{len(tickers)}] {t:<12} FEL: {e}")
            continue
        out.write_text(json.dumps({"ticker": t, "query": query, "schema": _SCHEMA_VERSION,
                                   "items": items}, ensure_ascii=False), encoding="utf-8")
        total += len(items)
        print(f"  [{i:>4}/{len(tickers)}] {t:<12} '{query[:28]:<28}' → {len(items)} PM")
        time.sleep(config.MFN_REQUEST_PAUSE_S)
    print(f"[fetch] klart – {total} PM cachade i {cache_dir}/")


def stats() -> None:
    """Statistik ur REDAN HÄMTAD cache (inget nätanrop) – ärligt svar, mätt på
    vårt eget universum, på 'hur många PM kommer det ut per dag från MFN'.
    Kör efter (eller mitt under, för en tidig fingervisning) 'fetch'."""
    from datetime import date, timedelta
    from collections import Counter
    cache_dir = Path(config.MFN_CACHE_DIR)
    files = [f for f in cache_dir.glob("*.json") if not f.name.startswith("_")]
    if not files:
        print(f"Ingen cache i {cache_dir}/ än – kör 'fetch' först.")
        return

    dates: List[date] = []
    lengths: List[int] = []
    per_ticker: Counter = Counter()
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items = d.get("items", [])
        per_ticker[d.get("ticker", f.stem)] = len(items)
        for it in items:
            pub = str(it.get("published") or "")[:10]
            try:
                dates.append(date.fromisoformat(pub))
            except ValueError:
                continue
            lengths.append(len(it.get("text") or ""))

    if not dates:
        print(f"{len(files)} bolag cachade, men inga tolkningsbara PM hittades.")
        return

    dates.sort()
    span_days = max((dates[-1] - dates[0]).days, 1)
    n = len(dates)
    print(f"[mfn stats] {len(files)} bolag cachade, {n:,} PM totalt (id-dubbletter redan borttagna)"
          .replace(",", " "))
    print(f"  Period: {dates[0]} → {dates[-1]} ({span_days:,} dagar)".replace(",", " "))
    print(f"  Snitt hela perioden: {n / span_days:.1f} PM/dag  (~{n / (span_days / 7):.0f} PM/vecka)")

    cutoff = dates[-1] - timedelta(days=90)
    recent = [d for d in dates if d >= cutoff]
    recent_span = max((dates[-1] - cutoff).days, 1)
    print(f"  Senaste 90 dagarna: {len(recent)} PM → {len(recent) / recent_span:.1f} PM/dag "
          f"(färskare bild – historiken kan innehålla luckor från borttagna/avnoterade bolag)")

    by_month = Counter(d.strftime("%Y-%m") for d in dates)
    print("  Mest aktiva månader (rapportsäsong-toppar):")
    for m, c in by_month.most_common(5):
        print(f"    {m}: {c} PM")

    avg_len = sum(lengths) / len(lengths)
    print(f"  Snittlängd PM-text: {avg_len:.0f} tecken (klippt vid MFN_MAX_BODY_CHARS={config.MFN_MAX_BODY_CHARS})")

    print("  Flest PM (bolag):")
    for tk, c in per_ticker.most_common(10):
        print(f"    {tk:<14} {c}")


def types() -> None:
    """Svarar EMPIRISKT på 'har vi bara PM eller även rapporter': vi hämtar bara
    feed-itemets EGEN text (content.text/preamble/html – se _coerce()), aldrig
    en PDF-bilaga. Kvartals-/årsrapporter publiceras ofta på MFN som en KORT
    announcement + separat PDF-länk – då har vi bara annonsen, inte rapportens
    fulltext/siffror (det är Börsdata-spårets jobb, inte MFN:s). Vissa bolag
    klistrar dock in hela rapportnarrativet i själva PM:et. Denna funktion
    grupperar cachen på MFN:s 'type'-fält och visar textlängd + ett konkret
    exempel per rapport-liknande typ, så vi SER vilket det är i stället för
    att anta. Läser bara redan hämtad cache – inget nätanrop."""
    from collections import Counter
    cache_dir = Path(config.MFN_CACHE_DIR)
    files = [f for f in cache_dir.glob("*.json") if not f.name.startswith("_")]
    if not files:
        print(f"Ingen cache i {cache_dir}/ än – kör 'fetch' först.")
        return

    by_type: Counter = Counter()
    lens_by_type: Dict[str, List[int]] = {}
    example_by_type: Dict[str, dict] = {}
    tag_counts: Counter = Counter()
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in d.get("items", []):
            t = it.get("type") or "(okänd)"
            by_type[t] += 1
            L = len(it.get("text") or "")
            lens_by_type.setdefault(t, []).append(L)
            if t not in example_by_type or L > len(example_by_type[t].get("text") or ""):
                example_by_type[t] = it
            for tag in (it.get("tags") or []):
                tag_counts[tag] += 1

    if not by_type:
        print(f"{len(files)} bolag cachade, men ingen typ-information hittades.")
        return

    total = sum(by_type.values())
    print(f"[mfn types] {total:,} PM, {len(by_type)} olika 'type'-värden".replace(",", " "))
    print(f"\n{'typ':<32}{'antal':>8}{'snitt-tecken':>14}{'max-tecken':>12}")
    for t, c in by_type.most_common():
        lens = lens_by_type[t]
        print(f"{t:<32}{c:>8}{sum(lens) / len(lens):>14.0f}{max(lens):>12}")

    report_kw = ("report", "rapport", "interim", "annual", "year-end", "bokslut", "kvartal")
    report_like = [t for t in by_type if any(kw in t.lower() for kw in report_kw)]
    if report_like:
        print("\nExempel på rapport-liknande 'type' (avgör om det är fulltext eller bara en kort annons):")
        for t in sorted(report_like, key=lambda x: -by_type[x]):
            ex = example_by_type[t]
            txt = ex.get("text") or ""
            print(f"\n  type={t!r} ({by_type[t]} st, snitt {sum(lens_by_type[t]) / len(lens_by_type[t]):.0f} tecken)")
            print(f"  '{ex.get('title', '')[:70]}'")
            print(f"  {txt[:300]}{'...' if len(txt) > 300 else ''}")
    else:
        print("\nInget 'type'-värde ser rapport-relaterat ut vid namnet. Vanligaste tags "
              "(rapport-klassningen kan ligga där i stället):")
        for tag, c in tag_counts.most_common(15):
            print(f"    {tag:<28}{c:>6}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else "Saab")
    elif cmd == "one":
        q = sys.argv[2]
        tk = sys.argv[3] if len(sys.argv) > 3 else None
        items = fetch_company(q, ticker=tk)
        print(json.dumps(items[:3], ensure_ascii=False, indent=2))
        print(f"... totalt {len(items)} PM för '{q}'"
              f"{f' (ticker {tk})' if tk else ''}")
    elif cmd == "fetch":
        fetch_universe(sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_SEGMENT)
    elif cmd == "stats":
        stats()
    elif cmd == "types":
        types()
    elif cmd == "raw":
        raw(sys.argv[2] if len(sys.argv) > 2 else "AAK")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
