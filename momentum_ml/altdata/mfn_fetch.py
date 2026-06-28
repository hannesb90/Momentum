"""
altdata/mfn_fetch.py – Hämtar regulatoriska pressmeddelanden från MFN.se och
cachar dem point-in-time (med publiceringstidsstämpel) för en ärlig backtest.

Varför MFN: Modular Finance distribuerar nordiska regulatoriska PM och har ett
ARKIV. Varje post har en publiceringstidsstämpel, så vi kan rekonstruera exakt
vad som var känt vid varje historisk tidpunkt – ingen look-ahead. Det är
förutsättningen för att över huvud taget kunna backtesta en text-/nyhetssignal
ärligt.

VIKTIGT – körs på Pi:n. Molncontainern som koden utvecklas i når varken mfn.se
eller Yahoo (egress-spärr). Kör allt detta på Raspberry Pi:n.

MFN:s exakta endpoint/JSON-form är inte hårdkodad på tro. Kör FÖRST:

    /opt/momentum/venv/bin/python altdata/mfn_fetch.py probe "Saab"

Det sparar MFN:s råsvar till cache/mfn/_probe_*.txt. Titta på filen (eller
klistra tillbaka den) så låser vi parsern mot den faktiska formen. Därefter:

    /opt/momentum/venv/bin/python altdata/mfn_fetch.py fetch large   # hela segmentet
    /opt/momentum/venv/bin/python altdata/mfn_fetch.py one  "Saab"   # ett bolag

Cachen (cache/mfn/<ticker>.json) gör att hämtningen är inkrementell och att
sentiment-steget aldrig behöver röra nätet igen.
"""
import sys
import os
import re
import json
import time
import html as _html
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:  # requests följer med yfinance, men var defensiv
    requests = None

_UA = "Mozilla/5.0 (Momentum research; contact via app owner) python-requests"


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _http_get(url: str, params: Optional[dict] = None, retries: int = 4) -> "requests.Response":
    """GET med exponentiell backoff. Respekterar HTTPS_PROXY/CA-bundle via miljön."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": _UA,
                             "Accept": "application/json, text/html;q=0.9"}, timeout=30)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} för {r.url}")
        except Exception as e:  # noqa: BLE001 – nätfel ska retrias
            last = e
        time.sleep(2 ** i)
    raise last or RuntimeError(f"GET misslyckades: {url}")


# ── Parser (verifieras mot probe-utdata) ──────────────────────────────────────
def _strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _coerce_item(raw: dict) -> Optional[dict]:
    """Normaliserar ETT MFN-objekt till vårt schema. Robust mot fältnamns-
    variation eftersom MFN:s exakta nycklar bekräftas med `probe`."""
    def pick(*keys):
        for k in keys:
            v = raw.get(k)
            if v:
                return v
        return None

    pid = pick("news_id", "content_id", "id", "guid", "slug")
    date = pick("publish_date", "published", "date", "created", "pubDate", "datetime")
    title = pick("title", "subject", "headline")
    body = pick("content", "body", "html", "text", "description", "summary")
    lang = pick("lang", "language") or config.MFN_LANG
    url = pick("url", "link", "permalink")
    typ = pick("type", "category", "subtype")

    if not (pid and date and (title or body)):
        return None
    text = _strip_html(str(body or ""))[: config.MFN_MAX_BODY_CHARS]
    return {
        "id": str(pid),
        "published": str(date),
        "title": _strip_html(str(title or "")),
        "type": str(typ or ""),
        "lang": str(lang),
        "url": str(url or ""),
        "text": text,
    }


def parse_mfn_payload(payload) -> List[dict]:
    """Plockar ut PM-listan ur MFN:s svar oavsett om det är ren JSON eller en
    HTML-sida med en inbäddad JSON-blob (vanligt på MFN:s Next.js-sajt)."""
    items: List[dict] = []

    # 1) Redan en lista/dict (JSON-endpoint)
    def harvest(obj):
        if isinstance(obj, list):
            for x in obj:
                harvest(x)
        elif isinstance(obj, dict):
            it = _coerce_item(obj)
            if it:
                items.append(it)
            # gå även ner i kända container-nycklar
            for k in ("items", "results", "news", "data", "hits", "feed", "entries"):
                if k in obj:
                    harvest(obj[k])

    if isinstance(payload, (list, dict)):
        harvest(payload)
        return _dedup(items)

    # 2) Text: prova JSON, annars leta inbäddad JSON i HTML
    text = str(payload)
    try:
        harvest(json.loads(text))
        if items:
            return _dedup(items)
    except Exception:
        pass
    for m in re.finditer(r'(\{.*?"publish[_-]?date".*?\})', text, flags=re.S):
        try:
            harvest(json.loads(m.group(1)))
        except Exception:
            continue
    return _dedup(items)


def _dedup(items: List[dict]) -> List[dict]:
    seen, out = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────────
def _endpoint_candidates(query: str) -> List[tuple]:
    """(beskrivning, url, params) – probas i tur och ordning. Verifieras på Pi:n."""
    base = config.MFN_BASE_URL.rstrip("/")
    lang = config.MFN_LANG
    return [
        ("all-json",   f"{base}/all",     {"query": query, "lang": lang, "json": "1", "limit": 500}),
        ("search",     f"{base}/all/s",   {"query": query, "lang": lang, "limit": 500}),
        ("author",     f"{base}/a/{_slug(query)}", {"lang": lang}),
        ("filter",     f"{base}/all",     {"query": query, "lang": lang}),
    ]


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = (s.replace("å", "a").replace("ä", "a").replace("ö", "o"))
    s = re.sub(r"\b(ab|publ|asa|oyj|plc|the)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def probe(query: str) -> None:
    """Hämtar varje endpoint-kandidat och dumpar råsvaret för granskning."""
    Path(config.MFN_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    print(f"[probe] frågar MFN om '{query}' – sparar råsvar i {config.MFN_CACHE_DIR}/")
    for name, url, params in _endpoint_candidates(query):
        out = Path(config.MFN_CACHE_DIR) / f"_probe_{name}.txt"
        try:
            r = _http_get(url, params)
            body = r.text
            out.write_text(f"URL: {r.url}\nCT: {r.headers.get('content-type')}\n"
                           f"LEN: {len(body)}\n{'='*60}\n{body[:20000]}", encoding="utf-8")
            parsed = parse_mfn_payload(body)
            print(f"  [{name:8}] {r.status_code}  {len(body):>7} tecken  "
                  f"→ {len(parsed)} PM tolkade  ({out.name})")
        except Exception as e:  # noqa: BLE001
            print(f"  [{name:8}] FEL: {e}")
    print("\nTitta på filen med flest tolkade PM. Stämmer fälten (id/published/"
          "title/text)? Då är parsern rätt – kör 'fetch'. Annars klistra in en "
          "_probe_*.txt så låser jag parsern mot den faktiska formen.")


# ── Hämtning + cache ──────────────────────────────────────────────────────────
def fetch_company(query: str) -> List[dict]:
    """Returnerar alla tolkade PM för ett bolag (första endpoint som ger träff)."""
    for name, url, params in _endpoint_candidates(query):
        try:
            r = _http_get(url, params)
            items = parse_mfn_payload(r.text)
            if items:
                return items
        except Exception:
            continue
        finally:
            time.sleep(config.MFN_REQUEST_PAUSE_S)
    return []


def _load_map() -> Dict[str, str]:
    """Valfri ticker→MFN-fråga-mappning (altdata/mfn_map.csv). Saknas den
    härleds frågan ur bolagsnamnet."""
    p = Path(__file__).parent / "mfn_map.csv"
    out: Dict[str, str] = {}
    if p.exists():
        import csv
        with open(p, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["ticker"]] = row.get("mfn_query") or row.get("query") or ""
    return out


def fetch_universe(segment: str) -> None:
    """Hämtar + cachar PM för alla tickers i ett segment."""
    from data.data_loader import load_sweden_universe
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, _, _, name_map = load_sweden_universe(min_market_cap=seg["market_cap"])
    qmap = _load_map()
    cache_dir = Path(config.MFN_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch] segment={segment} ({seg['label']}) – {len(tickers)} bolag")
    total = 0
    for i, t in enumerate(tickers, 1):
        out = cache_dir / f"{t}.json"
        if out.exists():
            continue  # inkrementellt – ta bort filen för att hämta om
        query = qmap.get(t) or _clean_name(name_map.get(t, t))
        items = fetch_company(query)
        out.write_text(json.dumps({"ticker": t, "query": query, "items": items},
                                  ensure_ascii=False, indent=0), encoding="utf-8")
        total += len(items)
        print(f"  [{i:>4}/{len(tickers)}] {t:<12} '{query[:30]:<30}' → {len(items)} PM")
    print(f"[fetch] klart – {total} PM cachade i {cache_dir}/")


def _clean_name(name: str) -> str:
    """Kort, sökbart bolagsnamn (släpp 'AB (publ)' m.m.)."""
    n = re.sub(r"\(publ\)|\bAB\b|\bASA\b|\bOyj\b|\bplc\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" ,.-")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else "Saab")
    elif cmd == "one":
        q = sys.argv[2]
        items = fetch_company(q)
        print(json.dumps(items[:5], ensure_ascii=False, indent=2))
        print(f"... totalt {len(items)} PM för '{q}'")
    elif cmd == "fetch":
        fetch_universe(sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_SEGMENT)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
