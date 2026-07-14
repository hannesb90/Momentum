"""
altdata/avanza.py – Avanza (www.avanza.se) publika _api-klient, ingen
autentisering krävs (verifierat: avanza-mcp-projektets endpoints.py säger
uttryckligen "All endpoints are public and require no authentication", och
client/base.py skickar bara User-Agent+Accept, ingen nyckel/cookie).

SYFTE: undersöka om Avanza kan täcka värderingsscreenerns balansräknings-
luckor (equity/liabilities/net_profit) HELT GRATIS – de har redan
färdigräknade nyckeltal (keyIndicators.returnOnEquity/equityRatio) vilket
skulle eliminera hela felklassen vi jagat i mfn_fundamentals/mfn_pdf
(koncern/moderbolag-förväxling, tkr/Mkr-skalning, annualisering): Avanza
äger beräkningen, inte vi.

VERIFIERAT (ur avanza-mcp-projektets källkod): bas-URL, endpoint-paths,
att ingen auth behövs, sök stödjer namn/ticker/ISIN.
INTE VERIFIERAT: exakt fältstruktur i companyFinancialsByYear/Quarter (bara
flödesmått – revenue/operatingProfit/netProfit – är dokumenterade i den
källan; om RÅA balansposter (equity/liabilities/totalAssets) finns där
också är okänt tills vi ser ett skarpt svar). probe() är därför SCHEMA-
UPPTÄCKANDE – dumpar riktiga fältnamn ur skarpa svar i stället för att anta
stavning som tyst kan vara fel (samma disciplin som altdata/borsdata.py).

Körs på Pi:n (nät):
    python -m altdata.avanza search "Volvo"        # hitta instrument-id
    python -m altdata.avanza probe SAAB-B.ST        # full schema-dump för ETT bolag
"""
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

BASE = "https://www.avanza.se"
_UA = "Mozilla/5.0 (Momentum research)"
_PAUSE_S = 0.5   # artig paus mellan anrop – ingen publicerad kvot, men slösa inte


def _get(path: str, params: Optional[dict] = None) -> dict:
    r = requests.get(f"{BASE}{path}", params=params,
                     headers={"User-Agent": _UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def _post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}{path}", json=payload,
                      headers={"User-Agent": _UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


def search(query: str, limit: int = 10) -> dict:
    """POST /_api/search/filtered-search – namn/ticker/ISIN. Rått svar
    (schema ej ännu verifierat mot skarp träff)."""
    return _post("/_api/search/filtered-search", {"query": query, "limit": limit})


def _clean_query(ticker_or_name: str) -> str:
    """Ticker med börs-suffix ("SAAB-B.ST") -> sökbar sträng ("SAAB B")."""
    q = ticker_or_name.split(".")[0]
    return q.replace("-", " ")


def probe(ticker_or_name: str) -> None:
    """Sök upp ETT bolag och dumpa RÅ JSON från de tre relevanta endpointsen
    (stock info/keyIndicators, analysis/companyFinancials) – inget antas,
    allt skrivs ut så de faktiska fältnamnen syns svart på vitt.

    VERIFIERAT sök-svarsschema (skarp körning): hits[] är en BLANDNING av
    typer (STOCK, CERTIFICATE/BULL/BEAR på samma underliggande, ...) – vi
    vill alltid den FÖRSTA träffen med type=='STOCK'. Fältet heter
    'orderBookId' (stort B) – INTE 'orderbookId'/'id', som råkar finnas
    (annan betydelse: sektorkoder) längre ner i strukturen och gav en
    falsk positiv (404) i en tidigare version av detta skript."""
    q = _clean_query(ticker_or_name)
    print(f"[probe] söker '{q}' (från '{ticker_or_name}')")
    hits = search(q)
    print(f"[probe] rått sök-svar (nycklar): {list(hits.keys())}")
    print(json.dumps(hits, ensure_ascii=False, indent=2)[:3000])

    stock_hits = [h for h in (hits.get("hits") or []) if h.get("type") == "STOCK"]
    if not stock_hits:
        print("[probe] ingen STOCK-träff i sök-svaret – kolla den råa dumpen ovan manuellt.")
        return
    hit = stock_hits[0]
    iid = str(hit.get("orderBookId") or "")
    print(f"\n[probe] vald träff: {hit.get('title')!r} orderBookId={iid}")
    if not iid:
        print("[probe] orderBookId saknades i den valda träffen – kolla dumpen ovan.")
        return
    time.sleep(_PAUSE_S)

    print(f"\n[probe] === STOCK INFO (id={iid}) ===")
    info = _get(f"/_api/market-guide/stock/{iid}")
    print(f"toppnivå-nycklar: {list(info.keys())}")
    if "keyIndicators" in info:
        print(f"keyIndicators: {json.dumps(info['keyIndicators'], ensure_ascii=False, indent=2)}")
    if "company" in info:
        print(f"company: {json.dumps(info['company'], ensure_ascii=False, indent=2)[:800]}")
    time.sleep(_PAUSE_S)

    print(f"\n[probe] === ANALYSIS (id={iid}) – companyFinancials ===")
    analysis = _get(f"/_api/market-guide/stock/{iid}/analysis")
    print(f"toppnivå-nycklar: {list(analysis.keys())}")
    # OVERIFIERAD form: kan vara lista ELLER dict (år/kvartal som nycklar) –
    # en tidigare version antog lista och kraschade (KeyError: 0) på en dict.
    # companyKeyRatiosByYear/stockKeyRatiosByYear är NYA, oväntade nycklar
    # (inte dokumenterade i avanza-mcp-källkoden) – kan innehålla RÅA
    # balansposter (equity/liabilities) som companyFinancials* saknar.
    for key in ("companyFinancialsByYear", "companyFinancialsByQuarter",
               "companyKeyRatiosByYear", "companyKeyRatiosByQuarter",
               "stockKeyRatiosByYear", "keyRatiosByYear"):
        section = analysis.get(key)
        if section is None:
            continue
        if isinstance(section, dict):
            print(f"\n{key}: DICT, {len(section)} nycklar: {list(section.keys())[:10]}")
            first_key = next(iter(section), None)
            if first_key is not None:
                first_val = section[first_key]
                print(f"  exempel [{first_key!r}]: {json.dumps(first_val, ensure_ascii=False, indent=2)[:1500]}")
        elif isinstance(section, list) and section:
            print(f"\n{key}: LISTA, {len(section)} rader")
            print(f"  fältnamn i EN rad: {list(section[0].keys())}")
            print(f"  exempel: {json.dumps(section[0], ensure_ascii=False, indent=2)[:1500]}")
        else:
            print(f"\n{key}: tom ({type(section).__name__})")

    out = Path(config.anchor("cache")) / "_avanza_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"search": hits, "info": info, "analysis": analysis},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[probe] fullständigt svar sparat: {out}")
    print("\n[probe] Klistra in denna utskrift så bygger vi mappningen mot våra kanoniska fält "
          "(revenue/net_profit/equity/liabilities/...) FÖRST efter att ha sett riktiga fältnamn.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "search":
        print(json.dumps(search(sys.argv[2] if len(sys.argv) > 2 else "Volvo"),
                         ensure_ascii=False, indent=2)[:3000])
    elif cmd == "probe":
        probe(sys.argv[2] if len(sys.argv) > 2 else "SAAB-B.ST")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
