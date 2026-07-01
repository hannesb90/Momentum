"""
altdata/tradingview.py – Fundamentals från TradingViews publika scanner (GRATIS, utan
nyckel): börsvärde + EBITDA + omsättning + aktieantal per bolag, i BATCH (en POST för
~100 tickers). Kompletterande källa som fyller luckor där Yahoo saknar data för svenska
små-/First North-bolag. Skriver samma cache-format som EODHD → report() kan väga in den.

Prioritet i quality_screener.report():  EODHD → TradingView → Yahoo → Claude-textutvinning.

Endpoint (inofficiell, JSON):
    POST https://scanner.tradingview.com/sweden/scan
    body: {"symbols":{"tickers":["OMXSTO:VOLV_B", ...],"query":{"types":[]}},
           "columns":["market_cap_basic","ebitda","total_revenue",
                      "total_shares_outstanding_fundamental","fundamental_currency_code"]}
    svar: {"data":[{"s":"OMXSTO:VOLV_B","d":[mcap, ebitda, rev, shares, "SEK"]}, ...]}

Ticker-mappning: våra tickers har '.ST' (Yahoo/EODHD-format). TradingView vill ha
'BÖRS:SYMBOL' med '_' istället för '-':  VOLV-B.ST → OMXSTO:VOLV_B,  SDS.ST → OMXSTO:SDS.
Bolag som inte hittas utelämnas tyst av scannern → vi rapporterar antalet missar; EODHD/
Yahoo täcker resten.

VIKTIGT – körs på Pi:n (molncontainern saknar nät till TradingView). Inget token behövs.
Inofficiellt API → kan sluta funka utan förvarning; behandla som best effort.

    python altdata/tradingview.py probe VOLV-B.ST SAAB-B.ST   # några bolag – verifiera fält
    python altdata/tradingview.py fill                        # alla poängsatta → _tradingview.json
    python altdata/tradingview.py universe                    # dry-run: visa bolag som SAKNAS i universumet
    python altdata/tradingview.py universe write              # addera dem till sweden_universe.csv
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:
    requests = None

# Kolumner i svarets 'd'-lista, i ordning (måste matcha _COLUMNS nedan).
_COLUMNS = ["market_cap_basic", "ebitda", "total_revenue",
            "total_shares_outstanding_fundamental", "fundamental_currency_code"]
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def tv_symbol(ticker: str) -> str:
    """'VOLV-B.ST' → 'OMXSTO:VOLV_B'. Endast Stockholm-tickers (.ST) mappas."""
    base = ticker.strip().upper()
    if base.endswith(".ST"):
        base = base[:-3]
    base = base.replace("-", "_").replace(".", "_")
    return f"{config.TRADINGVIEW_EXCHANGE}:{base}"


def _to_msek(v):
    return round(float(v) / 1e6, 1) if isinstance(v, (int, float)) else None


def _fetch_batch(symbols) -> dict:
    """POST:ar en batch TV-symboler och returnerar {tv_symbol: [d-värden]}."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    body = {"symbols": {"tickers": list(symbols), "query": {"types": []}},
            "columns": _COLUMNS}
    r = requests.post(config.TRADINGVIEW_SCAN_URL, json=body,
                      headers={"User-Agent": _UA, "Content-Type": "application/json"},
                      timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or []
    return {row.get("s"): (row.get("d") or []) for row in data if row.get("s")}


def _extract(vals) -> dict:
    """d-lista → samma struktur som EODHD-cachen (currency/mcap_msek/ebitda_msek/shares)."""
    def at(i):
        return vals[i] if i < len(vals) else None
    cur = at(4)
    return {
        "currency": (str(cur).upper() if cur else "SEK"),   # OMXSTO noterar i SEK
        "mcap_msek": _to_msek(at(0)),
        "ebitda_msek": _to_msek(at(1)),
        "revenue_msek": _to_msek(at(2)),
        "shares_million": (lambda s: round(float(s) / 1e6, 2)
                           if isinstance(s, (int, float)) else None)(at(3)),
    }


def _fetch_many(tickers) -> dict:
    """Hämtar fundamentals för en lista av VÅRA tickers (.ST) i batchar. Returnerar
    {vår_ticker: extrakt}. Missar (ej hittade i TV) utelämnas."""
    rev = {tv_symbol(t): t for t in tickers}          # TV-symbol → vår ticker
    syms = list(rev.keys())
    out = {}
    n = config.TRADINGVIEW_BATCH
    for i in range(0, len(syms), n):
        chunk = syms[i:i + n]
        try:
            got = _fetch_batch(chunk)
        except Exception as e:  # noqa: BLE001
            print(f"  [batch {i // n + 1}] FEL: {e}")
            continue
        for tvs, vals in got.items():
            out[rev.get(tvs, tvs)] = _extract(vals)
        if i + n < len(syms):
            time.sleep(config.TRADINGVIEW_REQUEST_PAUSE_S)
    return out


def probe(tickers) -> None:
    """Hämtar några bolag och visar de extraherade fälten – verifierar att den
    inofficiella endpointen svarar och att svenska bolag faktiskt har data."""
    res = _fetch_many(tickers)
    if not res:
        print("[probe] inga träffar – endpointen kan ha ändrats, eller fel symboler.")
        print(f"  (testade: {', '.join(tv_symbol(t) for t in tickers)})")
        return
    for t in tickers:
        ex = res.get(t)
        if not ex:
            print(f"  {t:<12} ({tv_symbol(t)})  – ingen träff i TradingView")
            continue
        print(f"  {t:<12} ({tv_symbol(t)})  valuta={ex['currency']}  "
              f"börsvärde={ex['mcap_msek']} MSEK  EBITDA={ex['ebitda_msek']} MSEK  "
              f"omsättning={ex['revenue_msek']} MSEK  aktier={ex['shares_million']} milj")
    print("  Ser rätt ut? Kör 'fill' för hela urvalet.")


def _scored_tickers():
    d = Path(config.QUALITY_CACHE_DIR)
    return [p.stem for p in d.glob("*.json") if not p.stem.startswith("_")]


def fill() -> None:
    """Hämtar fundamentals för alla poängsatta bolag → cache/quality/_tradingview.json.
    Inkrementellt: redan cachade tickers hoppas över (billigt/snällt mot endpointen)."""
    cache = Path(config.QUALITY_CACHE_DIR) / "_tradingview.json"
    out = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [t for t in _scored_tickers() if t not in out]
    print(f"[fill] {len(out)} redan cachade, {len(todo)} kvar att hämta")
    if not todo:
        print("[fill] inget nytt att hämta.")
        return
    got = _fetch_many(todo)
    out.update(got)
    misses = [t for t in todo if t not in got]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    mc = sum(1 for v in out.values() if v.get("mcap_msek") is not None)
    eb = sum(1 for v in out.values() if v.get("ebitda_msek") is not None)
    print(f"[fill] klart – {len(out)} bolag: {mc} med börsvärde, {eb} med EBITDA.")
    if misses:
        print(f"[fill] {len(misses)} bolag saknades i TradingView (EODHD/Yahoo täcker dem): "
              f"{', '.join(misses[:12])}{' …' if len(misses) > 12 else ''}")
    print("Kör nu 'quality_screener.py report' – TradingView vägs in efter EODHD, före Yahoo.")


# ── Universum-uppdatering: hämta HELA svenska aktielistan (inkl. First North) ──
# TradingViews 'sweden'-scan enumererar alla svenska aktier. Vi ADDERAR bara de
# som saknas i data/sweden_universe.csv (rör aldrig de 633 kurerade raderna) → löser
# den stela main-market-snapshoten utan att förstöra befintlig sektor-kurering.
_TV_SECTOR_GICS = {
    "technology services": "Information Technology", "electronic technology": "Information Technology",
    "health technology": "Health Care", "health services": "Health Care",
    "finance": "Financials",
    "energy minerals": "Energy",
    "non-energy minerals": "Materials", "process industries": "Materials",
    "producer manufacturing": "Industrials", "industrial services": "Industrials",
    "commercial services": "Industrials", "distribution services": "Industrials",
    "transportation": "Industrials", "miscellaneous": "Industrials",
    "consumer non-durables": "Consumer Staples",
    "consumer durables": "Consumer Discretionary", "consumer services": "Consumer Discretionary",
    "retail trade": "Consumer Discretionary",
    "communications": "Communication Services",
    "utilities": "Utilities",
}


def _gics(tv_sector) -> str:
    return _TV_SECTOR_GICS.get(str(tv_sector or "").strip().lower(), "Unknown")


def _cap_tier(mcap_sek) -> str:
    if not isinstance(mcap_sek, (int, float)):
        return "Nano Cap"
    m = mcap_sek / 1e6                                  # MSEK
    if m >= 10000:
        return "Large Cap"
    if m >= 2000:
        return "Mid Cap"
    if m >= 500:
        return "Small Cap"
    if m >= 100:
        return "Micro Cap"
    return "Nano Cap"


def _fetch_all_swedish() -> list:
    """Scanner-filter: alla svenska aktier (type=stock). Returnerar rå data-lista."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "columns": ["description", "market_cap_basic", "sector", "type", "subtype"],
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 4000], "options": {"lang": "en"}}
    r = requests.post(config.TRADINGVIEW_SCAN_URL, json=body,
                      headers={"User-Agent": _UA, "Content-Type": "application/json"}, timeout=45)
    r.raise_for_status()
    return r.json().get("data") or []


def universe(write=False) -> None:
    """Hämtar hela svenska aktielistan och ADDERAR de som saknas i universumet.
    Dry-run som default: kör 'universe write' för att faktiskt skriva filen."""
    import csv
    from collections import Counter
    uni_path = Path(__file__).parent.parent / "data" / "sweden_universe.csv"
    rows = list(csv.reader(open(uni_path, encoding="utf-8")))
    header, body = rows[0], rows[1:]
    existing = {r[0] for r in body}
    try:
        data = _fetch_all_swedish()
    except Exception as e:  # noqa: BLE001
        print(f"[universe] kunde inte hämta: {e}  (körs på Pi:n – molnet saknar nät)")
        return
    exch = Counter(row.get("s", "").split(":")[0] for row in data if row.get("s"))
    print(f"[universe] TradingView: {len(data)} aktier · börser: {dict(exch)}")
    new, skipped = [], Counter()
    for row in data:
        s, d = row.get("s", ""), (row.get("d") or [])
        if ":" not in s:
            continue
        ex, base = s.split(":", 1)
        if ex != config.TRADINGVIEW_EXCHANGE:          # bara Nasdaq Stockholm → .ST-format
            skipped[ex] += 1
            continue
        subtype = (str(d[4]).lower() if len(d) > 4 else "")
        if subtype and subtype not in ("common", "preferred"):   # skippa etf/fond/dr
            continue
        ticker = base.replace("_", "-") + ".ST"
        if ticker in existing:
            continue
        name = str(d[0]) if d else base
        sector = _gics(d[2] if len(d) > 2 else "")
        tier = _cap_tier(d[1] if len(d) > 1 else None)
        new.append((ticker, name, sector, tier))
    new.sort()
    on_sthlm = sum(1 for r in data if r.get("s", "").startswith(config.TRADINGVIEW_EXCHANGE + ":"))
    print(f"[universe] {on_sthlm} på {config.TRADINGVIEW_EXCHANGE}, varav {len(new)} SAKNAS i universumet:")
    for t in new[:50]:
        print(f"    + {t[0]:<13}{str(t[1])[:30]:<31}{t[2]:<24}{t[3]}")
    if len(new) > 50:
        print(f"    … och {len(new) - 50} till")
    if skipped:
        print(f"  (hoppade börser som ej mappar till .ST: {dict(skipped)})")
    unknown = sum(1 for t in new if t[2] == "Unknown")
    if unknown:
        print(f"  OBS: {unknown} nya bolag fick sektor 'Unknown' (TV-sektor saknade GICS-mappning).")
    if not write:
        print("  DRY-RUN – inget skrivet. Kör 'python altdata/tradingview.py universe write' för att lägga till.")
        return
    allrows = body + [list(t) for t in new]
    allrows.sort(key=lambda r: r[0])
    with open(uni_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(allrows)
    print(f"[universe] skrev {len(allrows)} bolag (+{len(new)} nya) → {uni_path}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        args = sys.argv[2:] or ["VOLV-B.ST", "SAAB-B.ST", "SDS.ST"]
        probe(args)
    elif cmd == "fill":
        fill()
    elif cmd == "universe":
        universe(write=(len(sys.argv) > 2 and sys.argv[2] == "write"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
