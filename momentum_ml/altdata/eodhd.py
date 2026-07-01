"""
altdata/eodhd.py – Fundamentals från EODHD (börsvärde + EBITDA + aktieantal i ETT
anrop). Bättre datakälla än Yahoo/textutvinning: en pålitlig källa ger både
börsvärde OCH EBITDA per bolag → report() prioriterar den, med Yahoo/Claude som
fallback. Löser BÅDA halvorna av screenerns "okänd"-hink.

Endpoint (JSON):
    https://eodhd.com/api/fundamentals/<TICKER>?api_token=<KEY>&fmt=json
Fält vi använder:
    General.CurrencyCode, Highlights.MarketCapitalization, Highlights.EBITDA,
    SharesStats.SharesOutstanding
Våra tickers har redan '.ST' (EODHD:s Stockholm-format) → skickas som de är.

Kräver EN betald fundamentals-plan. Nyckeln läses från miljövariabeln
EODHD_API_TOKEN (lägg i ~/.momentum.env, chmod 600 – ALDRIG i repot). En gratis
demo-token ("demo") fungerar bara för några få US-tickers (AAPL.US m.fl.) och är
bra för att röktesta kod-vägen, inte för svenska bolag.

VIKTIGT – körs på Pi:n (molncontainern saknar nyckel/nät till Yahoo/EODHD).

    export EODHD_API_TOKEN=...      # eller lägg i ~/.momentum.env
    python altdata/eodhd.py probe SDS.ST     # ett bolag – verifiera nyckel + fält
    python altdata/eodhd.py probe AAPL.US demo   # röktest utan egen nyckel
    python altdata/eodhd.py fill              # alla poängsatta → cache/quality/_eodhd.json
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:
    requests = None

_FILTER = ("General::CurrencyCode,Highlights::MarketCapitalization,"
           "Highlights::EBITDA,SharesStats::SharesOutstanding")


def _token(explicit: Optional[str] = None) -> str:
    t = explicit or os.environ.get("EODHD_API_TOKEN")
    if not t:
        raise RuntimeError(
            "EODHD_API_TOKEN saknas – lägg nyckeln i ~/.momentum.env (chmod 600) "
            "och 'export EODHD_API_TOKEN=...', eller ange den som andra argument.")
    return t


def _dig(data: dict, section: str, field: str):
    """Läser ett fält robust oavsett om EODHD:s filter-svar är nästlat
    ({'Highlights': {'EBITDA': ...}}) eller platt ({'Highlights::EBITDA': ...})."""
    if not isinstance(data, dict):
        return None
    sec = data.get(section)
    if isinstance(sec, dict) and field in sec:
        return sec[field]
    return data.get(f"{section}::{field}")


def _fetch(ticker: str, token: str) -> dict:
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    url = f"{config.EODHD_BASE_URL}/fundamentals/{ticker}"
    r = requests.get(url, params={"api_token": token, "fmt": "json", "filter": _FILTER},
                     timeout=30)
    r.raise_for_status()
    return r.json()


def _to_msek(v):
    return round(float(v) / 1e6, 1) if isinstance(v, (int, float)) else None


def _extract(d: dict) -> dict:
    return {
        "currency": _dig(d, "General", "CurrencyCode"),
        "mcap_msek": _to_msek(_dig(d, "Highlights", "MarketCapitalization")),
        "ebitda_msek": _to_msek(_dig(d, "Highlights", "EBITDA")),
        "shares_million": (lambda s: round(float(s) / 1e6, 2)
                           if isinstance(s, (int, float)) else None)(
            _dig(d, "SharesStats", "SharesOutstanding")),
    }


def probe(ticker: str, token: Optional[str] = None) -> None:
    """Hämtar ETT bolag och visar råsvar + de extraherade fälten – verifierar att
    nyckeln funkar och att börsvärde/EBITDA faktiskt finns för svenska bolag."""
    tok = _token(token)
    try:
        d = _fetch(ticker, tok)
    except Exception as e:  # noqa: BLE001
        print(f"[probe] FEL för {ticker}: {e}")
        print("  (401/403 = fel nyckel eller plan utan fundamentals; 404 = okänd ticker)")
        return
    print(f"[probe] {ticker} råsvar: {json.dumps(d, ensure_ascii=False)[:400]}")
    ex = _extract(d)
    print(f"  → valuta={ex['currency']}  börsvärde={ex['mcap_msek']} MSEK  "
          f"EBITDA={ex['ebitda_msek']} MSEK  aktier={ex['shares_million']} milj")
    if ex["currency"] and ex["currency"] != "SEK":
        print(f"  OBS: valutan är {ex['currency']}, inte SEK – siffrorna är i den valutan.")
    if ex["mcap_msek"] or ex["ebitda_msek"]:
        print("  Ser rätt ut? Kör 'fill' för hela urvalet.")


def _scored_tickers():
    d = Path(config.QUALITY_CACHE_DIR)
    return [p.stem for p in d.glob("*.json") if not p.stem.startswith("_")]


def fill() -> None:
    """Hämtar fundamentals för alla poängsatta bolag → cache/quality/_eodhd.json
    (börsvärde + EBITDA + aktier). Inkrementellt: cachade tickers hoppas över, så
    en avbruten körning kan återupptas utan att betala om för samma anrop."""
    tok = _token()
    cache = Path(config.QUALITY_CACHE_DIR) / "_eodhd.json"
    out = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [t for t in _scored_tickers() if t not in out]
    print(f"[fill] {len(out)} redan cachade, {len(todo)} kvar att hämta")
    nonsek = 0
    for i, t in enumerate(todo, 1):
        try:
            ex = _extract(_fetch(t, tok))
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>4}/{len(todo)}] {t:<12} FEL: {e}")
            continue
        out[t] = ex
        if ex.get("currency") and ex["currency"] != "SEK":
            nonsek += 1
        if i % 25 == 0:
            cache.write_text(json.dumps(out))     # checkpoint mot avbrott
            print(f"  ...{i}/{len(todo)}")
        time.sleep(config.EODHD_REQUEST_PAUSE_S)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    mc = sum(1 for v in out.values() if v.get("mcap_msek") is not None)
    eb = sum(1 for v in out.values() if v.get("ebitda_msek") is not None)
    print(f"[fill] klart – {len(out)} bolag: {mc} med börsvärde, {eb} med EBITDA.")
    if nonsek:
        print(f"[fill] OBS: {nonsek} bolag rapporterar i annan valuta än SEK – "
              "report() flaggar dem så multipeln inte blir vilseledande.")
    print("Kör nu 'quality_screener.py report' – EODHD prioriteras före Yahoo/text.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        if len(sys.argv) < 3:
            print("Ange ticker, t.ex.: python altdata/eodhd.py probe SDS.ST")
            return
        probe(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "fill":
        fill()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
