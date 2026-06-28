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
            last = RuntimeError(f"HTTP {r.status_code} för {r.url}")
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
    n = re.sub(r"\(publ\)|\bAB\b|\bASA\b|\bOyj\b|\bplc\b", "", name, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" ,.-")


def fetch_universe(segment: str) -> None:
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
        try:
            items = fetch_company(query, ticker=t)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>4}/{len(tickers)}] {t:<12} FEL: {e}")
            continue
        out.write_text(json.dumps({"ticker": t, "query": query, "items": items},
                                  ensure_ascii=False), encoding="utf-8")
        total += len(items)
        print(f"  [{i:>4}/{len(tickers)}] {t:<12} '{query[:28]:<28}' → {len(items)} PM")
        time.sleep(config.MFN_REQUEST_PAUSE_S)
    print(f"[fetch] klart – {total} PM cachade i {cache_dir}/")


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
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
