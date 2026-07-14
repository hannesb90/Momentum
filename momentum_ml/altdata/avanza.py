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

SKARPT VERIFIERAT (riktig probe-körning mot Wallenstam, WALL-B.ST):
  companyFinancialsByYear/Quarter = DICT (INTE lista) med nycklarna
    sales, netProfit, profitMargin, totalAssets, totalLiabilities,
    debtToEquityRatio – var och en en LISTA av {date, reportType,
    financialYear, value}. RÅA belopp i HELA SEK (inte Mkr/tkr – Wallenstams
    sales 2025 = 3 256 000 000, dvs 3,256 miljarder, verifierat mot deras
    riktiga omsättning). totalAssets − totalLiabilities ger EGET KAPITAL
    direkt – ingen egen tkr/Mkr-skalning eller koncern/moderbolag-gissning
    behövs, till skillnad från vår PDF-tabellextraktion.
  companyKeyRatiosByYear/Quarter = samma form, nycklar earningsPerShare/
    turnoverPerShare/equityPerShare/netDebtEbitdaRatio/returnOnEquityRatio
    – FÄRDIGRÄKNAD ROE/D-E från Avanza själva (returnOnEquityRatio för
    Wallenstam 2025 var rimlig, jämför vår egen extraktions 656%-bugg).
  date-fältet saknas för de äldsta åren (2016/2017 i Wallenstam-exemplet)
    men finns för alla senare år/kvartal – tillräckligt för growth-
    consistency/ROE-consistency som bara tittar 4 rapporter bakåt.

Körs på Pi:n (nät):
    python -m altdata.avanza search "Volvo"        # hitta instrument-id
    python -m altdata.avanza probe SAAB-B.ST        # full schema-dump för ETT bolag
    python -m altdata.avanza match large            # bygg ticker -> orderBookId (cachas)
    python -m altdata.avanza extract large          # bygg fundamentals_from_avanza.csv
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


# ── Matchning (ticker -> Avanza orderBookId) ──────────────────────────────────
def _norm_ticker(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _map_path() -> Path:
    return Path(config.anchor("cache")) / "avanza_map.json"


def match(segment: Optional[str] = None) -> None:
    """Bygger ticker -> Avanza orderBookId genom att söka på VÅR ticker-
    sträng (inte bolagsnamnet – Avanzas titelformat "Bolag (TICKER)" gör
    tickersökning träffsäker, verifierat: 'WALL B' -> 'Wallenstam B (WALL B)').
    Sparar mappningen permanent i cache/avanza_map.json (ändras sällan – körs
    inte om för redan matchade tickers).

    SÄKERHET (samma lärdom som mfn_fetch._author_match kostade dyrt att
    sakna): kräver att VÅR tickers bokstav/siffror finns som delsträng i
    träffens titel innan den godtas. En STOCK-träff utan den bekräftelsen
    accepteras ändå (bästa gissning) men FLAGGAS som osäker i utskriften –
    granska de raderna manuellt innan extract() litar på dem."""
    from data.data_loader import load_sweden_universe

    seg_cfg = config.SEGMENTS.get(segment) if segment else None
    seg_cfg = seg_cfg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, sector_map, cap_map, _name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    mp = _map_path()
    mapping = json.loads(mp.read_text()) if mp.exists() else {}

    matched = already = skipped = uncertain = 0
    for i, t in enumerate(tickers, 1):
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        if t in mapping:
            already += 1
            continue
        base = t.split(".")[0]
        try:
            hits = search(base.replace("-", " "))
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} FEL: {e}")
            continue
        stock_hits = [h for h in (hits.get("hits") or []) if h.get("type") == "STOCK"]
        tn = _norm_ticker(base)
        confirmed = next((h for h in stock_hits if tn in _norm_ticker(str(h.get("title") or ""))), None)
        hit = confirmed or (stock_hits[0] if stock_hits else None)
        if hit is None:
            skipped += 1
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} ingen STOCK-träff")
            continue
        if confirmed is None:
            uncertain += 1
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} OSÄKER: '{hit.get('title')}' "
                  f"(tickern syns inte i titeln – granska manuellt)")
        mapping[t] = {"orderBookId": str(hit.get("orderBookId") or ""),
                      "title": hit.get("title"), "confirmed": confirmed is not None}
        matched += 1
        time.sleep(_PAUSE_S)

    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[match] {matched} nya ({uncertain} osäkra), {already} redan cachade, "
          f"{skipped} utan träff -> {mp}")


# ── Extraktion (analysis -> fundamentals_from_avanza.csv) ────────────────────
# Fältmappning: vänster = vårt kanoniska namn, höger = Avanzas nyckel i
# companyFinancialsByYear/Quarter respektive companyKeyRatiosByYear/Quarter
# (se modulens docstring – verifierat via skarp probe, inte gissat).
_FIN_FIELDS = {"revenue": "sales", "net_profit": "netProfit",
              "_total_assets": "totalAssets", "liabilities": "totalLiabilities",
              "debt_equity_avanza": "debtToEquityRatio"}
_RATIO_FIELDS = {"eps": "earningsPerShare", "roe_avanza": "returnOnEquityRatio"}


def _rows_from_section(section: dict, fields: dict) -> dict:
    """Avanzas dict-av-listor-form -> {(financialYear, reportType): {vårt
    fältnamn: värde, "date": ...}}. section kan vara None/tom utan att krascha."""
    out: dict = {}
    for our_field, avanza_key in fields.items():
        for entry in ((section or {}).get(avanza_key) or []):
            key = (entry.get("financialYear"), entry.get("reportType"))
            if key[0] is None or key[1] is None:
                continue
            row = out.setdefault(key, {})
            row[our_field] = entry.get("value")
            if entry.get("date"):
                row["date"] = entry["date"]
    return out


def _period_label(report_type: str, year: int) -> Optional[str]:
    """Avanzas reportType -> vår periodsträng (samma konvention som
    mfn_fundamentals.detect_period/annualization_factor läser: 'Helår 2025',
    'Q2 2026')."""
    if report_type == "FULL_YEAR":
        return f"Helår {year}"
    if report_type in ("Q1", "Q2", "Q3", "Q4"):
        return f"{report_type} {year}"
    return None   # okänd reportType (t.ex. en framtida Avanza-kategori) – hoppa hellre än gissa


def company_financials(order_book_id: str) -> dict:
    return _get(f"/_api/market-guide/stock/{order_book_id}/analysis")


def _build_rows(ticker: str, analysis: dict) -> list:
    """Slår ihop companyFinancials* + companyKeyRatios* per (år, period) och
    formaterar till våra kanoniska fundamentals-kolumner. RÅA SEK-belopp
    (verifierat i probe: Wallenstams sales 2025 = 3 256 000 000, inte
    3256 eller 3.256) konverteras till Mkr HÄR – value_screener._to_msek
    tolkar en tom/okänd enhet som 'redan Mkr', så vi MÅSTE skala om innan
    skrivning, annars blir det ett 1 000 000x-fel i andra riktningen."""
    rows = []
    for by_key, granularity in (("companyFinancialsByYear", "year"), ("companyFinancialsByQuarter", "quarter")):
        fin = _rows_from_section(analysis.get(by_key), _FIN_FIELDS)
        ratio_key = by_key.replace("Financials", "KeyRatios")
        ratios = _rows_from_section(analysis.get(ratio_key), _RATIO_FIELDS)
        all_keys = set(fin) | set(ratios)
        for (year, rtype) in all_keys:
            period = _period_label(rtype, year)
            if period is None:
                continue
            f = fin.get((year, rtype), {})
            r = ratios.get((year, rtype), {})
            date = f.get("date") or r.get("date")
            if not date:
                continue   # utan datum: ingen point-in-time-plats i pipelinen (dropna nedströms ändå)
            revenue = f.get("revenue")
            equity = None
            if f.get("_total_assets") is not None and f.get("liabilities") is not None:
                equity = (f["_total_assets"] - f["liabilities"]) / 1e6
            # revenue_prior: SAMMA reportType, föregående år, ur SAMMA serie.
            prior = fin.get((year - 1, rtype), {}).get("revenue")
            row = {
                "ticker": ticker, "published": f"{date}T08:00:00Z", "period": period,
                "pm_id": f"avanza-{ticker}-{year}-{rtype}",
                "title": f"Avanza {rtype} {year} ({granularity})",
                "revenue": (revenue / 1e6) if revenue is not None else None, "revenue_unit": "Mkr",
                "revenue_prior": (prior / 1e6) if prior is not None else None,
                "net_profit": (f["net_profit"] / 1e6) if f.get("net_profit") is not None else None,
                "net_profit_unit": "Mkr",
                "equity": equity, "equity_unit": "Mkr",
                "liabilities": (f["liabilities"] / 1e6) if f.get("liabilities") is not None else None,
                "liabilities_unit": "Mkr",
                "eps": r.get("eps"),
                "debt_equity_avanza": f.get("debt_equity_avanza"),
                "roe_avanza": r.get("roe_avanza"),
            }
            rows.append(row)
    return rows


def extract(segment: Optional[str] = None) -> None:
    """Kör match() FÖRST. Hämtar analysis för alla matchade tickers, bygger
    <results_dir>/fundamentals_from_avanza.csv – samma kolumnkonvention som
    fundamentals_from_mfn.csv (ticker/published/period/pm_id/revenue/
    net_profit/equity/liabilities/...) så value_screener._load_fundamentals
    kan läsa den rakt av. debt_equity_avanza/roe_avanza/eps följer med som
    EXTRA kolumner (Avanzas egna färdiga nyckeltal) – oanvända av dagens
    pipeline tills value_screener explicit kopplas in att föredra dem."""
    mp = _map_path()
    if not mp.exists():
        print(f"Ingen {mp} – kör 'match' först.")
        return
    mapping = json.loads(mp.read_text())

    seg_cfg = config.SEGMENTS.get(segment) if segment else None
    seg_cfg = seg_cfg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    from data.data_loader import load_sweden_universe
    tickers, sector_map, cap_map, _name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    wanted = {t for t in tickers if cap_map.get(t) != "Fond" and sector_map.get(t) != "Fond"}

    all_rows, ok, fail = [], 0, 0
    for i, t in enumerate(sorted(wanted & mapping.keys()), 1):
        oid = mapping[t].get("orderBookId")
        if not oid:
            continue
        try:
            analysis = company_financials(oid)
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  [{i}] {t:<14} FEL: {e}")
            continue
        rows = _build_rows(t, analysis)
        all_rows.extend(rows)
        ok += 1
        if i % 20 == 0:
            print(f"  ...{i}/{len(wanted & mapping.keys())} ({len(all_rows)} rader hittills)")
        time.sleep(_PAUSE_S)

    if not all_rows:
        print("Inga rader extraherade.")
        return
    cols = ["ticker", "published", "period", "pm_id", "title", "revenue", "revenue_unit",
           "revenue_prior", "net_profit", "net_profit_unit", "equity", "equity_unit",
           "liabilities", "liabilities_unit", "eps", "debt_equity_avanza", "roe_avanza"]
    out = Path(config.anchor(seg_cfg["results_dir"])) / "fundamentals_from_avanza.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[extract] {ok} bolag ({fail} fel), {len(all_rows)} rader -> {out}")


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
    elif cmd == "match":
        match(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "extract":
        extract(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
