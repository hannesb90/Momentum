"""
altdata/nasdaq_nordic.py – Auktoritativt börsvärde/aktieantal från Nasdaq Nordics
egen datafeed (gratis), som KOMPLETTERAR Yahoo. Yahoo saknar aktieantal för många
svenska microcaps → screenerns "okänd"-hink. Nasdaq har det. Vi sveper hela
Stockholmsbörsen i några anrop och fyller BARA de börsvärden Yahoo missade
(Yahoo har företräde – vi skriver bara tickers som saknas i cachen).

Reverse-engineerad XML-datafeed (samma endpoint publika klienter använder):
    GET .../DataFeedProxy.aspx?Exchange=NMF&SubSystem=Prices&Action=GetMarket
        &Market=<id>&instrumentType=S&inst__a=<fältkoder>
Svaret är XML med <inst>-element; varje har namngivna attribut (nm, isin, ...).
VILKET attribut som bär aktieantal/börsvärde är inte dokumenterat → kör `probe`
FÖRST (dumpar de råa attributen från Pi:n) och sätt NASDAQ_ATTR_* i config därefter.

VIKTIGT – körs på Pi:n (molncontainern når inte nasdaqomxnordic.com).

    python altdata/nasdaq_nordic.py probe            # dumpa råa attribut → identifiera fälten
    python altdata/nasdaq_nordic.py probe L:10214    # en specifik marknad
    python altdata/nasdaq_nordic.py fill             # fyll cache/quality/_marketcaps.json
"""
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:
    requests = None

_UA = "Mozilla/5.0 (Momentum research) python-requests"


def _norm(s: str) -> str:
    """Ticker/symbol → jämförbar nyckel: 'SAAB-B.ST' och 'SAAB B' → 'SAABB'."""
    s = (s or "").split(".")[0]                      # strippa '.ST'
    return "".join(ch for ch in s.upper() if ch.isalnum())


def _get_market(market: str) -> List[dict]:
    """Hämtar alla aktie-instrument på EN marknad → lista av attribut-dictar."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    params = {
        "Exchange": config.NASDAQ_EXCHANGE,
        "SubSystem": "Prices",
        "Action": "GetMarket",
        "Market": market,
        "instrumentType": "S",
        "inst__a": config.NASDAQ_INST_FIELDS,
    }
    r = requests.get(config.NASDAQ_ENDPOINT, params=params,
                     headers={"User-Agent": _UA}, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    # <inst>-element kan ligga nästlade; ta alla oavsett djup.
    return [dict(el.attrib) for el in root.iter() if el.tag.lower().endswith("inst")]


def _raw_response(market: str) -> "tuple[str, bytes]":
    params = {
        "Exchange": config.NASDAQ_EXCHANGE,
        "SubSystem": "Prices",
        "Action": "GetMarket",
        "Market": market,
        "instrumentType": "S",
        "inst__a": config.NASDAQ_INST_FIELDS,
    }
    r = requests.get(config.NASDAQ_ENDPOINT, params=params,
                     headers={"User-Agent": _UA}, timeout=30)
    r.raise_for_status()
    return r.headers.get("Content-Type", "?"), r.content


def raw(market: Optional[str] = None) -> None:
    """Skriver ut content-type + råsvarets första rader – för att bygga rätt parser."""
    m = market or config.NASDAQ_MARKETS[0]
    ctype, body = _raw_response(m)
    print(f"[raw] {m}  content-type={ctype}  {len(body)} bytes")
    txt = body.decode("utf-8", errors="replace")
    print(txt[:1800])


def _fetch_all() -> List[dict]:
    out: List[dict] = []
    for m in config.NASDAQ_MARKETS:
        try:
            insts = _get_market(m)
        except Exception as e:  # noqa: BLE001
            print(f"  [{m}] FEL: {e}")
            continue
        print(f"  [{m}] {len(insts)} instrument")
        out.extend(insts)
        time.sleep(config.NASDAQ_REQUEST_PAUSE_S)
    return out


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _market_cap_msek(inst: dict) -> Optional[float]:
    """Börsvärde i MSEK ur ett instrument. Direkt mcap-attribut om satt, annars
    aktieantal × kurs. Returnerar None om fälten inte går att läsa."""
    mc_attr, sh_attr, px_attr = (config.NASDAQ_ATTR_MCAP, config.NASDAQ_ATTR_SHARES,
                                 config.NASDAQ_ATTR_PRICE)
    if mc_attr:
        mc = _to_float(inst.get(mc_attr))
        if mc:
            return round(mc / 1e6, 1)                 # SEK → MSEK
    if sh_attr and px_attr:
        sh, px = _to_float(inst.get(sh_attr)), _to_float(inst.get(px_attr))
        if sh and px:
            return round(sh * px / 1e6, 1)
    return None


def probe(market: Optional[str] = None) -> None:
    """Dumpar de RÅA attributen så vi kan identifiera aktieantal/börsvärde/kurs.
    Sätt sedan NASDAQ_ATTR_MCAP / _SHARES / _PRICE i config utifrån detta."""
    markets = [market] if market else config.NASDAQ_MARKETS
    for m in markets:
        print(f"\n[probe] marknad {m}")
        try:
            insts = _get_market(m)
        except Exception as e:  # noqa: BLE001
            print(f"  FEL: {e}")
            continue
        print(f"  {len(insts)} instrument")
        if not insts:
            continue
        keys = sorted({k for it in insts for k in it})
        print(f"  attribut: {keys}")
        # Numeriska attribut (kandidater för aktieantal/börsvärde/kurs):
        numeric = [k for k in keys if sum(1 for it in insts[:50] if _to_float(it.get(k)) is not None) > 25]
        print(f"  numeriska attribut: {numeric}")
        for it in insts[:3]:
            print(f"   • {json.dumps(it, ensure_ascii=False)}")
    print("\n  Identifiera fälten och sätt NASDAQ_ATTR_MCAP/_SHARES/_PRICE i config, "
          "kör sedan 'fill'.")


def _scored_tickers() -> List[str]:
    d = Path(config.QUALITY_CACHE_DIR)
    return [p.stem for p in d.glob("*.json") if not p.stem.startswith("_")]


def fill() -> None:
    """Fyller cache/quality/_marketcaps.json med Nasdaq-börsvärde för de poängsatta
    bolag Yahoo missade. Yahoo har företräde: befintliga nycklar rörs inte."""
    if not (config.NASDAQ_ATTR_MCAP or (config.NASDAQ_ATTR_SHARES and config.NASDAQ_ATTR_PRICE)):
        print("[fill] NASDAQ_ATTR_* ej satta i config – kör 'probe' först och sätt fälten.")
        return
    insts = _fetch_all()
    if not insts:
        print("[fill] inga instrument hämtade – kontrollera NASDAQ_MARKETS/nätet.")
        return
    # Bygg uppslag: normaliserad symbol/isin → börsvärde (MSEK).
    by_sym: Dict[str, float] = {}
    for it in insts:
        mc = _market_cap_msek(it)
        if mc is None:
            continue
        sym = _norm(it.get(config.NASDAQ_ATTR_SYMBOL, ""))
        isin = (it.get(config.NASDAQ_ATTR_ISIN) or "").upper()
        if sym:
            by_sym[sym] = mc
        if isin:
            by_sym[isin] = mc
    print(f"[fill] {len(insts)} instrument, {len(by_sym)} med börsvärde")

    cache = Path(config.QUALITY_CACHE_DIR) / "_marketcaps.json"
    caps = json.loads(cache.read_text()) if cache.exists() else {}
    added = 0
    for t in _scored_tickers():
        if t in caps:                       # Yahoo har redan detta – rör inte
            continue
        mc = by_sym.get(_norm(t))
        if mc is not None:
            caps[t] = mc
            added += 1
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(caps))
    print(f"[fill] +{added} börsvärden från Nasdaq (totalt {len(caps)} i cachen). "
          "Kör nu 'quality_screener.py report' igen.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "raw":
        raw(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "fill":
        fill()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
