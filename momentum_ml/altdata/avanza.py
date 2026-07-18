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
    python -m altdata.avanza inspect                # riktat urval ur senast sparade probe-dump
    python -m altdata.avanza chart_probe "Bolag"    # prisdiagram-schema/djup (testa NGM/Spotlight-bolag)
    python -m altdata.avanza match large            # bygg ticker -> orderBookId (cachas)
    python -m altdata.avanza match quality          # ...även Small+Micro+NANO Cap
    python -m altdata.avanza match ngm              # ...NGM/Spotlight (data/sweden_universe_ngm.csv)
    python -m altdata.avanza extract large          # bygg fundamentals_from_avanza.csv
    python -m altdata.avanza extract quality        # ...till results/quality/ (rör ej large/small)
    python -m altdata.avanza audit                  # månatlig avnoterings-/uppköpsrevision + överlevnadsliggare
    python -m altdata.avanza calendar large          # rapportkalender (nextReport ur keyIndicators)
    python -m altdata.avanza revalidate              # engångsstädning: purga gamla felmatchningar
    python -m altdata.avanza check_marketplace       # Avanzas EGET listing.marketPlaceName/countryCode, ALLA matchade bolag
    python -m altdata.avanza check_marketplace suspects  # ...bara de ~109 ASA/A-S/Oyj/P-F-misstänkta (snabbare)
    python -m altdata.avanza list_probe              # proba börslist-/IPO-endpoints + chart-djup (Yahoo-ersättningsfrågan)
    python -m altdata.avanza list_probe2             # chart-djup+upplösning mot ÄLDRE bolag (Yahoo-ersättningsfrågan, avgjord: se kodkommentar ovan list_probe2)
    python -m altdata.avanza list_probe2 VOLV-B.ST   # ...annat chart-testbolag (default AAK.ST)
    python -m altdata.avanza universe_remove T1,T2   # dry-run: ta bort tickers ur sweden_universe.csv (lägg till 'write' för att faktiskt skriva)

Namnbytes-overrides (bolag ingen strängregel kan hitta, t.ex. Cellink -> BICO
Group): altdata/avanza_overrides.csv (ticker,query,comment) – valfri fil,
varje rad ska vara verifierad mot en skarp 'search'-körning innan den läggs
till, samma princip som mfn_fetch.py:s valfria mfn_map.csv.
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
    print("[probe] (kör 'inspect' för ett riktat urval ur den sparade dumpen: quote/totalAssets/"
          "totalLiabilities/netProfit/equityPerShare/marketCapital – utan att printa om allt.)")


# ── Prishistorik (chart) ───────────────────────────────────────────────────────
# Avanza handlar HELA svenska marknaden (Nasdaq Stockholm+First North, MEN
# ÄVEN NGM och Spotlight) - till skillnad från Yahoo, vars '.ST'-suffix bara
# mappar mot OMXSTO (se altdata/tradingview.py:s gaps()-kommando).
#
# VERIFIERAT (skarp chart_probe-körning mot Plejd/PLEJD och Kopparbergs
# Bryggeri/KOBR B, båda NGM-listade): svarets punktlista ligger under
# nyckeln 'ohlc', varje punkt har fälten timestamp (EPOCH MILLISEKUNDER),
# open, high, low, close, totalVolumeTraded. Upplösningen är ADAPTIV per
# timePeriod - kortare period ger TÄTARE punkter, INTE samma punkter
# trunkerade: one_month ≈ 189 punkter/29 dagar (intradag), one_year ≈ 251
# punkter/år (≈ dagsvis, matchar antal handelsdagar), three_years/
# five_years ≈ 157/261 punkter över perioden (≈ EN punkt/vecko) - alltså
# redan VECKOUPPLÖST för de långa perioderna, exakt vad
# MIN_HISTORY_WEEKS/fetch_weekly_data behöver, ingen resampling krävs.
# five_years gav fullständig 5-årsdjup för båda testbolagen (start ~5 år
# bakåt från körningsdatumet, inte begränsat av notering/BTA-episoder i de
# två testade fallen) - gott och väl över MIN_HISTORY_WEEKS=78.
_CHART_PERIODS = ("one_month", "three_months", "one_year", "three_years", "five_years")
_CHART_POINT_KEYS = ("ohlc", "dataPoints", "candles", "points", "series")


def fetch_chart_ohlcv(order_book_id: str, period: str = "five_years"):
    """Hämtar OCH tolkar prisdiagram-data för ETT bolag -> pandas DataFrame
    med kolumnerna Open/High/Low/Close/Volume (samma kontrakt som
    data_loader._clean() förväntar sig), indexerad på datum. Returnerar
    None om svaret saknar en igenkänd punktlista eller är tomt - GISSAR
    ALDRIG en tom/felaktig serie (samma disciplin som resten av modulen).

    period: en av _CHART_PERIODS, se modulkommentaren ovan för verifierad
    upplösning per period (five_years = veckovis, redan rätt för pipelinen)."""
    import pandas as pd
    data = _get(f"/_api/price-chart/stock/{order_book_id}", {"timePeriod": period})
    points = None
    for k in _CHART_POINT_KEYS:
        if isinstance(data.get(k), list):
            points = data[k]
            break
    if not points:
        return None
    rows = []
    for p in points:
        ts = p.get("timestamp")
        if ts is None:
            continue
        rows.append({
            "Date": pd.to_datetime(ts, unit="ms"),
            "Open": p.get("open"), "High": p.get("high"),
            "Low": p.get("low"), "Close": p.get("close"),
            "Volume": p.get("totalVolumeTraded"),
        })
    if not rows:
        return None
    df = pd.DataFrame(rows).set_index("Date").sort_index()
    return df


def chart_probe(ticker_or_name: str) -> None:
    """Söker upp ETT bolag (samma sök+orderBookId-mönster som probe()) och
    dumpar RÅ prisdiagram-JSON för varje kandidat-timePeriod – hur långt
    tillbaka går datan, vilken upplösning (antal punkter/period), och vilka
    fältnamn (open/high/low/close eller bara close?) svaret faktiskt har.
    Testa uttryckligen mot ett NGM- eller Spotlight-bolag (inte bara
    Nasdaq Stockholm) – det är just den täckningen frågan gäller.

        python -m altdata.avanza chart_probe "NGM Bolaget"
    """
    q = _clean_query(ticker_or_name)
    print(f"[chart_probe] söker '{q}' (från '{ticker_or_name}')")
    hits = search(q)
    stock_hits = [h for h in (hits.get("hits") or []) if h.get("type") == "STOCK"]
    if not stock_hits:
        print("[chart_probe] ingen STOCK-träff – kolla stavningen eller använd 'search' direkt.")
        print(json.dumps(hits, ensure_ascii=False, indent=2)[:2000])
        return
    hit = stock_hits[0]
    iid = str(hit.get("orderBookId") or "")
    print(f"[chart_probe] vald träff: {hit.get('title')!r} orderBookId={iid}\n")
    if not iid:
        print("[chart_probe] orderBookId saknades – kolla dumpen ovan.")
        return

    dump = {}
    for period in _CHART_PERIODS:
        time.sleep(_PAUSE_S)
        try:
            data = _get(f"/_api/price-chart/stock/{iid}", {"timePeriod": period})
        except Exception as e:  # noqa: BLE001
            print(f"  timePeriod={period:<14} FEL: {e}")
            continue
        dump[period] = data
        top_keys = list(data.keys())
        points = None
        for k in _CHART_POINT_KEYS:
            if isinstance(data.get(k), list):
                points = data[k]
                break
        if points:
            first, last = points[0], points[-1]
            print(f"  timePeriod={period:<14} {len(points)} punkter  "
                  f"[{first.get('timestamp') or first.get('date')} -> "
                  f"{last.get('timestamp') or last.get('date')}]")
            print(f"    fältnamn i EN punkt: {list(first.keys())}")
        else:
            print(f"  timePeriod={period:<14} toppnivå-nycklar: {top_keys} "
                  f"(ingen igenkänd punktlista - kolla den sparade dumpen)")

    out = Path(config.anchor("cache")) / "_avanza_chart_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[chart_probe] fullständiga svar sparade: {out}")
    print("[chart_probe] Klistra in utskriften – avgör om djup/upplösning räcker för att "
          "ersätta/komplettera Yahoo på NGM/Spotlight, INGET antas ännu.")


def inspect_probe() -> None:
    """Läser SENAST SPARADE probe()-dump (cache/_avanza_probe.json, kräver att
    probe() körts först för bolaget du vill inspektera) och visar ett RIKTAT
    urval i stället för hela dumpen:
      - info['quote']: livepris – ger ett TREDJE, mer universellt sätt att
        härleda aktieantal (marketCapital/price) för bolag där equityPerShare/
        eps saknas (nuvarande _build_rows-härledning behöver minst en av dem).
      - companyFinancialsByYear.totalAssets/totalLiabilities/netProfit (senaste
        4 år): verifierar att equity_raw/net_profit FAKTISKT har data att
        jobba med för bolagstyper där andra fält (t.ex. 'sales') legitimt är
        0.0 (investmentbolag har ingen omsättning, men har fortfarande
        tillgångar/skulder/resultat – 0.0 där är en äkta siffra, inte en lucka).
      - companyKeyRatiosByYear.equityPerShare + keyIndicators.marketCapital/
        equityPerShare: cross-check mellan de två endpointsen (historisk serie
        vs nu-ögonblicksbild) – ska stämma överens om båda är pålitliga."""
    p = Path(config.anchor("cache")) / "_avanza_probe.json"
    if not p.exists():
        print(f"Ingen {p} – kör 'probe <ticker>' först.")
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    info = data.get("info") or {}
    analysis = data.get("analysis") or {}

    print("=== info toppnivå-nycklar ===")
    print(list(info.keys()))

    print("\n=== info['quote'] (livepris) ===")
    print(json.dumps(info.get("quote"), ensure_ascii=False, indent=2))

    fin = analysis.get("companyFinancialsByYear") or {}
    for key in ("totalAssets", "totalLiabilities", "netProfit"):
        print(f"\n=== companyFinancialsByYear.{key} (senaste 4 år) ===")
        print(json.dumps((fin.get(key) or [])[-4:], ensure_ascii=False, indent=2))

    ratios = analysis.get("companyKeyRatiosByYear") or {}
    print("\n=== companyKeyRatiosByYear.equityPerShare (senaste 4 år) ===")
    print(json.dumps((ratios.get("equityPerShare") or [])[-4:], ensure_ascii=False, indent=2))

    ki = info.get("keyIndicators") or {}
    print("\n=== keyIndicators.marketCapital + equityPerShare (cross-check) ===")
    print(json.dumps({"marketCapital": ki.get("marketCapital"), "equityPerShare": ki.get("equityPerShare")},
                     ensure_ascii=False, indent=2))


def _resolve_universe(segment: Optional[str]):
    """segment = 'large'/'small' (config.SEGMENTS, tradade backtest-segment)
    ELLER 'quality' (Small+Micro+NANO Cap – SAMMA specialfall som
    mfn_fetch.fetch_universe/refresh_universe redan använder för sin PM-cache;
    Nano exkluderas MEDVETET ur 'small' i config.py – opålitlig klassning/
    likviditet för att TA POSITIONER, inte ett skäl att avstå datainsamling.
    'quality' skriver till en EGEN results/quality/-mapp, rör ALDRIG large/
    small:s filer). Returnerar (tickers, sector_map, cap_map, name_map,
    results_dir)."""
    if segment == "ngm":
        # NGM/Spotlight – ett eget universum (data/sweden_universe_ngm.csv),
        # inte cap-tier-segmenterat som large/small/quality: dessa bolag
        # matchas mot Avanza HELT för prisdata (data_loader.fetch_weekly_data
        # via '.NGM'-suffixet), inte för att gå igenom risksättning/handel
        # ännu – en egen results/ngm/-katalog håller isär det.
        from data.data_loader import load_ngm_universe
        tickers, sector_map, cap_map, name_map = load_ngm_universe()
        return tickers, sector_map, cap_map, name_map, config.anchor("results/ngm")

    from data.data_loader import load_sweden_universe
    if segment == "quality":
        market_cap = config.QUALITY_MARKET_CAP
        results_dir = config.anchor("results/quality")
    else:
        seg_cfg = config.SEGMENTS.get(segment) if segment else None
        seg_cfg = seg_cfg or config.SEGMENTS[config.DEFAULT_SEGMENT]
        market_cap = seg_cfg["market_cap"]
        results_dir = config.anchor(seg_cfg["results_dir"])
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=market_cap)
    return tickers, sector_map, cap_map, name_map, results_dir


# ── Matchning (ticker -> Avanza orderBookId) ──────────────────────────────────
def _norm_ticker(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _map_path() -> Path:
    return Path(config.anchor("cache")) / "avanza_map.json"


# Interimsinstrument-/aktieklass-segment som INTE finns i Avanzas ticker för
# STAMAKTIEN – BTA/TO/TR/UR (delårs-emissionsrätter/betalda tecknade aktier,
# samma mönster som tvingade fram _clean_name-fixen i mfn_fetch.py) samt PREF
# (preferensaktie – VERIFIERAT via coverage-körning: 6/17 no-data-bolag i
# small-segmentet hade '-PREF'-suffix, t.ex. KLOV-PREF.ST, medan KLOV-B.ST
# redan hade data – preferensaktien delar SAMMA bolagsfundamenta som stam-
# aktien, bara utdelningsvillkoren skiljer, så att stryka PREF och söka på
# stammen ger korrekt delad revenue/net_profit/equity). PREF[AB]?: även
# klassade preferensaktier – verifierat fall 'OP-PREFB.ST' (Oscar Properties
# pref B) som fick noll träff när bara exakt 'PREF' kändes igen.
_INSTRUMENT_SEG_RE = re.compile(r"^(BTA|TO|TR|UR|PREF[AB]?)\d*$", re.I)


def _ticker_variants(base: str) -> list:
    """Kandidat-söksträngar för en ticker, prövade i ordning tills en
    BEKRÄFTAD träff hittas:
      1. Bokstavlig ticker.
      2. Interimsinstrument-segment (BTA/TO/TR/UR, ev. numrerat) borttaget
         ur bindestrecks-delarna – "INTRUM-BTA" -> "INTRUM".
      3. En trailing "O" borttagen – VERIFIERAT mönster (en riktig match-
         körning missade 58+ bolag, nästan alla nordiska primärnoteringar
         på Oslo Børs som vårt lokala universum suffixar med "O" för den
         svenska sekundärnoteringen: 'EQNRO'->'EQNR' (Equinor), 'YARO'->
         'YAR' (Yara), 'ORKO'->'ORK' (Orkla) – Avanzas egen ticker saknar
         suffixet. Samma mekanism som AKERO/AKRBPO/BNORO/DOFGO/ORKO/PENO/
         SOFFO visade i MFN-matchningen tidigare, nu i ett annat system.
      4. TVÅ trailing "O" borttagna (inte rstrip-alla – ticker-stammen kan
         själv sluta på "O") – 'AUTOOO' (AutoStore: stammen "AUTO" slutar
         redan på O, plus sekundärnoteringssuffixet "O" ovanpå) kräver att
         BÅDA sista O:na strippas för att bli 'AUTO'; steg 3 ensam ger bara
         'AUTOO' som inte finns hos Avanza. Ett rakt rstrip("O") hade
         strippat även stammens egen O och felaktigt gett 'AUT'."""
    variants = [base]
    parts = base.split("-")
    stripped = [p for p in parts if not _INSTRUMENT_SEG_RE.match(p)]
    if stripped != parts and stripped:
        cand = "-".join(stripped)
        if cand not in variants:
            variants.append(cand)
    if base.endswith("O") and len(base) > 3:
        cand = base[:-1]
        if cand not in variants:
            variants.append(cand)
    if base.endswith("OO") and len(base) > 4:
        cand = base[:-2]
        if cand not in variants:
            variants.append(cand)
    return variants


# Avanzas titelformat är OFTAST "Bolagsnamn (TICKER)" – matcha EXAKT mot
# ticker-delen i parentesen, ALDRIG mot hela titeln som en fri delsträng.
# VERIFIERAT skarpt fel med den URSPRUNGLIGA (för lösa) regeln: 'FOOT-PREF.ST'
# (Footway) söktes som 'FOOT' och blev "bekräftad" mot 'Eagle Football Group
# (EFG)' – 'FOOT' råkade vara en delsträng av bolagsNAMNET 'FootBALL', inte
# av tickern.
#
# MEN: en skarp revalidate()-körning visade att Avanza för en del bolag helt
# UTELÄMNAR parentesen – titeln är bara 'AAK'/'SAAB B'/'SEB A'/'SSAB A' rakt
# av (troligen när bolagsnamnet redan ÄR/innehåller tickern, ingen redundant
# '(TICKER)' behövs). En regel som KRÄVER parentes kastade ut 32+ äkta
# bekräftade matchningar tillsammans med de riktiga buggarna. Fix: saknas
# parentes helt, jämförs HELA titeln normaliserad – FORTFARANDE EXAKT
# likhet, aldrig en fri delsträng (det var precis det som orsakade Eagle
# Football Group-felet, om än den titeln HADE parenteser).
_TITLE_TICKER_RE = re.compile(r"\(([A-Z0-9 .\-]+)\)\s*$")


def _title_ticker_matches(title: str, variant: str) -> bool:
    title = title or ""
    tn = _norm_ticker(variant)
    m = _TITLE_TICKER_RE.search(title)
    if m:
        return _norm_ticker(m.group(1)) == tn
    if "(" not in title and ")" not in title:
        return _norm_ticker(title) == tn   # ingen parentes -> hela titeln, EXAKT
    return False


def _search_variant(variant: str) -> tuple:
    """Ett sökförsök -> (bekräftad_träff_eller_None, bästa_ej_bekräftade_eller_None).
    Bekräftelse: variantens ticker matchar EXAKT ticker-delen i träffens
    titel – se _title_ticker_matches/_TITLE_TICKER_RE ovan för varför en fri
    delsträng mot hela titeln inte duger."""
    hits = search(variant.replace("-", " "))
    stock_hits = [h for h in (hits.get("hits") or []) if h.get("type") == "STOCK"]
    confirmed = next((h for h in stock_hits if _title_ticker_matches(str(h.get("title") or ""), variant)), None)
    return confirmed, (stock_hits[0] if stock_hits else None)


def _load_query_overrides() -> dict:
    """Valfri ticker -> KÄND aktuell sökfråga (altdata/avanza_overrides.csv,
    kolumner ticker,query,comment). För bolag som bytt namn/ticker på ett sätt
    ingen strängregel (_ticker_variants) kan räkna ut – t.ex. CLNK-B.ST
    (Cellink) heter numera BICO Group med EN enda aktieklass, ingen "-B" ens
    kvar. Varje rad ska vara VERIFIERAD mot en skarp search()-körning innan
    den läggs till (inte gissad – en extern, overifierad namnbyteslista
    ledde till detta, men bara BICO-fallet kontrollerades faktiskt mot en
    riktig sökning innan det lades till). Samma mönster som mfn_fetch.py:s
    valfria mfn_map.csv. Saknas filen -> tom dict, ingen krasch."""
    p = Path(__file__).parent / "avanza_overrides.csv"
    out: dict = {}
    if p.exists():
        import csv as _csv
        with open(p, encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                if row.get("ticker") and row.get("query"):
                    out[row["ticker"]] = row["query"]
    return out


def match(segment: Optional[str] = None) -> None:
    """Bygger ticker -> Avanza orderBookId genom att söka på VÅR ticker-
    sträng (inte bolagsnamnet – Avanzas titelformat "Bolag (TICKER)" gör
    tickersökning träffsäker, verifierat: 'WALL B' -> 'Wallenstam B (WALL B)').
    Sparar mappningen permanent i cache/avanza_map.json (ändras sällan – körs
    inte om för redan matchade tickers).

    Provar flera tickervarianter (se _ticker_variants) tills en BEKRÄFTAD
    träff hittas – annars sparas bästa ej bekräftade träff (om någon fanns)
    men FLAGGAS som osäker i utskriften, så den kan granskas manuellt innan
    extract() litar på den. Samma lärdom som mfn_fetch._author_match kostade
    dyrt att sakna: gissa aldrig tyst.

    segment: 'large'/'small'/'quality' (Small+Micro+Nano Cap) ELLER 'ngm' (se
    _resolve_universe). Provar en ev. VERIFIERAD override-sökfråga
    (avanza_overrides.csv) FÖRST, före de vanliga tickervarianterna – för
    bolag som bytt namn på ett sätt inga strängregler kan räkna ut."""
    tickers, sector_map, cap_map, _name_map, _results_dir = _resolve_universe(segment)
    overrides = _load_query_overrides()

    mp = _map_path()
    mapping = json.loads(mp.read_text()) if mp.exists() else {}

    matched = already = skipped = uncertain = 0
    for i, t in enumerate(tickers, 1):
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        if t in mapping:
            # En OSÄKER post får ETT nytt försök när en override finns för
            # tickern – annars blockerar den gamla fallback-träffen för evigt
            # (verifierat: BICO-overriden hade aldrig fått verka om inte
            # revalidate() råkat radera CLNK-B-posten först). Bekräftade
            # poster provas aldrig om (dyra nätanrop i onödan).
            if mapping[t].get("confirmed") or t not in overrides:
                already += 1
                continue
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} OSÄKER post + override finns – provar om")
        base = t.split(".")[0]
        confirmed = fallback = None
        variants = ([overrides[t]] if t in overrides else []) + _ticker_variants(base)
        for variant in variants:
            try:
                confirmed, hit = _search_variant(variant)
            except Exception as e:  # noqa: BLE001
                print(f"  [{i:>4}/{len(tickers)}] {t:<14} FEL ('{variant}'): {e}")
                continue
            finally:
                time.sleep(_PAUSE_S)
            if fallback is None:
                fallback = hit
            if confirmed is not None:
                break
        hit = confirmed or fallback
        if hit is None:
            skipped += 1
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} ingen STOCK-träff (provade {variants})")
            continue
        if confirmed is None:
            uncertain += 1
            print(f"  [{i:>4}/{len(tickers)}] {t:<14} OSÄKER: '{hit.get('title')}' "
                  f"(tickern syns inte i titeln – granska manuellt)")
        mapping[t] = {"orderBookId": str(hit.get("orderBookId") or ""),
                      "title": hit.get("title"), "confirmed": confirmed is not None}
        matched += 1

    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[match] {matched} nya ({uncertain} osäkra), {already} redan cachade, "
          f"{skipped} utan träff -> {mp}")


def revalidate() -> None:
    """ENGÅNGSSTÄDNING (körs vid behov, t.ex. efter en skärpning av
    bekräftelseregeln): läser om VARJE 'confirmed: true'-post i
    avanza_map.json mot dess SPARADE titel med DAGENS (strängare) regel –
    exakt ticker-i-parentes-matchning (_title_ticker_matches), inte den
    gamla 'ticker syns NÅGONSTANS i titeln'-regeln som gav en VERIFIERAD
    felmatchning (FOOT-PREF.ST/Footway -> 'Eagle Football Group (EFG)',
    eftersom 'FOOT' råkade vara en delsträng av bolagsNAMNET 'FootBALL').

    Poster som INTE längre klarar den strängare regeln mot NÅGON av sina
    _ticker_variants tas bort ur mappningen – en efterföljande 'match'-
    körning försöker då om dem på riktigt i stället för att permanent lita
    på en gammal felaktig träff. redan match():ade tickers som ALDRIG var
    'confirmed' (bara osäkra fallback-träffar) rörs inte – de var redan
    flaggade för manuell granskning.

        python -m altdata.avanza revalidate
    """
    mp = _map_path()
    if not mp.exists():
        print(f"Ingen {mp} – inget att validera om.")
        return
    mapping = json.loads(mp.read_text())
    n_confirmed = sum(1 for v in mapping.values() if v.get("confirmed"))
    bad = []
    for t, v in list(mapping.items()):
        if not v.get("confirmed"):
            continue
        base = t.split(".")[0]
        title = str(v.get("title") or "")
        if not any(_title_ticker_matches(title, cand) for cand in _ticker_variants(base)):
            bad.append((t, title))
            del mapping[t]
    if not bad:
        print(f"[revalidate] alla {n_confirmed} bekräftade mappningar klarar den strängare "
              f"regeln – inga ändringar.")
        return
    mp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[revalidate] {len(bad)} felmatchning(ar) av {n_confirmed} bekräftade hittades och "
          f"togs bort (kör 'match' igen för att försöka om dem):")
    for t, title in bad:
        print(f"  {t:<16} var felaktigt matchad mot: '{title}'")


# ── Extraktion (analysis -> fundamentals_from_avanza.csv) ────────────────────
# Fältmappning: vänster = vårt kanoniska namn, höger = Avanzas nyckel i
# companyFinancialsByYear/Quarter respektive companyKeyRatiosByYear/Quarter
# (se modulens docstring – verifierat via skarp probe, inte gissat).
_FIN_FIELDS = {"revenue": "sales", "net_profit": "netProfit",
              "_total_assets": "totalAssets", "liabilities": "totalLiabilities",
              "debt_equity_avanza": "debtToEquityRatio"}
# _equity_per_share (VERIFIERAT fältnamn ur skarp probe, companyKeyRatiosByYear)
# används BARA för att härleda aktieantal (se _build_rows) – Avanzas analysis-
# endpoint har inget eget "antal aktier"-fält, men equity/equityPerShare ger
# samma tal utan ett extra API-anrop.
_RATIO_FIELDS = {"eps": "earningsPerShare", "roe_avanza": "returnOnEquityRatio",
                 "_equity_per_share": "equityPerShare"}


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
    skrivning, annars blir det ett 1 000 000x-fel i andra riktningen.

    shares_outstanding HÄRLEDS (Avanza har inget eget aktieantal-fält):
    primärt equity_raw / equityPerShare (båda RÅA SEK, samma skala tar ut
    varandra), med net_profit_raw / eps som reserv för år där equityPerShare
    saknas men eps finns (t.ex. ett förlustår med negativt eget kapital gör
    equityPerShare meningslös men eps ändå brukbar). Utan detta saknade
    283/296 bolag P/E-underlaget helt (Avanza-extraktionen gav aldrig
    aktieantal) – 'komplett'-andelen i coverage() låg fast på 0% trots att
    revenue/net_profit/equity/liabilities redan täcktes.

    TOMMA FRAMTIDSPERIODER HOPPAS ÖVER: Avanza listar även INNEVARANDE/
    KOMMANDE kvartal med financialYear/reportType (och ofta ett nominellt
    'date' = periodens SLUTdatum, t.ex. '2026-06-30' för Q2 2026) INNAN
    rapporten faktiskt publicerats – alla värdefält saknas (None) då.
    VERIFIERAT med skarp coverage/diagnose-körning: en sådan tom rad blev
    konsekvent 'senaste raden' i value_screener._load_fundamentals (den har
    ju det SENASTE datumet) och gjorde ROE/D-E/aktieantal obedömbara trots
    att en fullt komplett Q1-rad låg direkt före den i samma historik –
    drabbade i praktiken NÄSTAN VARJE bolag identiskt (samma mönster i 8/8
    diagnostiserade bolag: 8TRA/AAK/ABB/ACAST/ACRO/AFGO/AFKO/AFRY). En rad
    utan NÅGOT faktiskt värdefält (bara datum/period/pm_id) är alltså inte
    en riktig rapport och hoppas över helt."""
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
            has_fin_value = any(f.get(k) is not None for k in
                                ("revenue", "net_profit", "_total_assets", "liabilities", "debt_equity_avanza"))
            has_ratio_value = any(r.get(k) is not None for k in ("eps", "roe_avanza", "_equity_per_share"))
            if not has_fin_value and not has_ratio_value:
                continue   # tom framtidsperiod (se docstring) - inte en riktig rapport
            revenue = f.get("revenue")
            equity_raw = None
            if f.get("_total_assets") is not None and f.get("liabilities") is not None:
                equity_raw = f["_total_assets"] - f["liabilities"]
            equity = (equity_raw / 1e6) if equity_raw is not None else None
            # revenue_prior: SAMMA reportType, föregående år, ur SAMMA serie.
            prior = fin.get((year - 1, rtype), {}).get("revenue")
            eqs = r.get("_equity_per_share")
            shares = (equity_raw / eqs) if (equity_raw is not None and eqs not in (None, 0)) else None
            if shares is None and f.get("net_profit") is not None and r.get("eps") not in (None, 0):
                shares = f["net_profit"] / r["eps"]
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
                "shares_outstanding": shares,
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
    pipeline tills value_screener explicit kopplas in att föredra dem.

    segment: 'large'/'small'/'quality' (Small+Micro+Nano Cap) ELLER 'ngm' (se
    _resolve_universe) – skriver till results/quality/ för det senare, rör
    ALDRIG large/small:s fundamentals_from_avanza.csv.

    HOPPAR ÖVER 'confirmed: false'-poster (osäkra fallback-träffar från
    match()) – VERIFIERAT skarpt varför det är nödvändigt: en tidigare
    version extraherade OAVSETT confirmed-status, vilket hade tystat in helt
    orelaterade bolags siffror (t.ex. amerikanska Roivant Sciences/Opendoor/
    Meta Platforms/ATHA Energy för svenska RO.ST/OP.ST/ME.ST/SAS.ST) i
    fundamentals_from_avanza.csv – exakt samma felklass som Eagle Football
    Group-buggen, bara inte längre tyst i match()-utskriften. Osäkra poster
    ligger KVAR i avanza_map.json (för manuell granskning/ev. framtida
    override i avanza_overrides.csv) men bidrar inga rader."""
    mp = _map_path()
    if not mp.exists():
        print(f"Ingen {mp} – kör 'match' först.")
        return
    mapping = json.loads(mp.read_text())

    tickers, sector_map, cap_map, _name_map, results_dir = _resolve_universe(segment)
    wanted = {t for t in tickers if cap_map.get(t) != "Fond" and sector_map.get(t) != "Fond"}

    candidates = sorted(wanted & mapping.keys())
    uncertain = [t for t in candidates if not mapping[t].get("confirmed")]
    candidates = [t for t in candidates if mapping[t].get("confirmed")]
    if uncertain:
        print(f"[extract] hoppar över {len(uncertain)} OSÄKRA mappningar (granska manuellt, "
              f"se avanza_map.json/avanza_overrides.csv):")
        for t in uncertain:
            print(f"    {t:<16} '{mapping[t].get('title')}'")

    all_rows, ok, fail = [], 0, 0
    for i, t in enumerate(candidates, 1):
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
            print(f"  ...{i}/{len(candidates)} ({len(all_rows)} rader hittills)")
        time.sleep(_PAUSE_S)

    if not all_rows:
        print("Inga rader extraherade.")
        return
    cols = ["ticker", "published", "period", "pm_id", "title", "revenue", "revenue_unit",
           "revenue_prior", "net_profit", "net_profit_unit", "equity", "equity_unit",
           "liabilities", "liabilities_unit", "eps", "shares_outstanding",
           "debt_equity_avanza", "roe_avanza"]
    out = Path(results_dir) / "fundamentals_from_avanza.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[extract] {ok} bolag ({fail} fel, {len(uncertain)} osäkra överhoppade), "
          f"{len(all_rows)} rader -> {out}")


# ── Överlevnadsrevision (avnotering/uppköp) ───────────────────────────────────
# Svenska nyckelord i PM-TITLAR som brukar signalera att ett bolag försvinner
# från börsen. Träff = LEDTRÅD för manuell granskning, INTE ett facit – en
# rubrik som nämner "budplikt" kan lika gärna handla om ett ANNAT bolags bud
# PÅ det här bolaget (ingen automatisk sanning, samma försiktighet som
# _search_variant()s 'confirmed vs uncertain'-flaggning).
_DELISTING_KEYWORDS = re.compile(
    r"avnoter|uppköp|budplikt|tvångsinlösen|offentligt (?:kontant)?bud|"
    r"budet\b|fusion(?:en)?\b|samgående|sammanslagning|delisting|"
    r"inlösen av aktier|likvidation|konkurs",
    re.I,
)


def _mfn_delisting_hint(ticker: str) -> Optional[dict]:
    """Söker REDAN CACHAD MFN-data (cache/mfn/{ticker}.json, byggd av
    mfn_fetch.py – INGET nytt nätanrop här) efter den SENASTE PM-titeln som
    matchar ett avnoterings-/uppköpsnyckelord. Returnerar None om cachen
    saknas eller inget PM matchar (ärligt 'okänd orsak', inte en gissning)."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        cached = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    items = sorted(cached.get("items") or [], key=lambda it: it.get("published") or "", reverse=True)
    for it in items:
        title = it.get("title") or ""
        m = _DELISTING_KEYWORDS.search(title)
        if m:
            return {"keyword": m.group(0), "title": title,
                    "date": (it.get("published") or "")[:10], "url": it.get("url")}
    return None


def audit() -> None:
    """MÅNATLIG ÖVERLEVNADSREVISION – re-verifierar VARJE redan BEKRÄFTAD
    avanza_map.json-mappning mot /_api/market-guide/stock/{orderBookId}
    (SAMMA verifierade endpoint som probe()/company_financials() redan
    använder – inget nytt, ogissat API). Sveper ALLA segment/tiers som någon
    gång match():ats (oavsett 'large'/'small'/'quality') – avnotering är en
    bolags-egenskap, inte en segment-egenskap.

    Ett fel (404/timeout/etc) på ett instrument som förut gick att slå upp är
    en stark avnoterings-/uppköpssignal – byggd på samma lärdom som avslöjade
    de 9 AUTOOO/EQNRO-liknande fallen i match(): en Avanza-sökning som SLUTAR
    ge träff är information, inte brus.

    Jämför mot cache/avanza_audit_snapshot.json (föregående körnings status
    per ticker) för att hitta NYA fel sedan senast – annars skulle varje
    körning återflagga samma redan kända/granskade bolag om och om igen.
    NYFLAGGADE tickers korsrefereras mot redan cachad MFN-data (ingen extra
    nätaccess) för att STYRKA (inte bevisa) en trolig orsak.

    Skriver ACKUMULERANDE results/avanza_delisting_audit.csv (en rad per
    nyflaggat bolag och körning – historik bevaras, filen skrivs ALDRIG över,
    till skillnad från övriga CSV:er i pipelinen). Tänkt körd en gång i
    månaden (deploy/momentum-avanza-audit.timer).

    ÖVERLEVNADSLIGGARE (survivorship framåt): varje snapshot-post bär
    first_seen (datum då tickern FÖRST observerades av audit – ärligt "vår
    bevakning började då", inte noteringsdatumet) och last_ok (senaste datum
    tickern kunde verifieras som levande). Tillsammans med delisting-CSV:ns
    daterade händelser ackumulerar det en point-in-time-universumhistorik:
    ett FRAMTIDA backtest kan veta exakt när varje ticker bevisligen levde
    och när den försvann – den survivorship-lucka som backtest/benchmark.py
    ärligt dokumenterar som "kan ej kodas bort" BAKÅT (Avanza kan inte
    återuppliva redan avnoterade bolags historik) stängs därmed FRAMÅT, och
    blir mer värd för varje månad liggaren växer. Projektionen exporteras
    till results/universe_survival.csv varje körning.

        python -m altdata.avanza audit
    """
    import csv as _csv
    from datetime import datetime, timezone

    mp = _map_path()
    if not mp.exists():
        print(f"Ingen {mp} – kör 'match' först.")
        return
    mapping = json.loads(mp.read_text())
    confirmed = {t: v for t, v in mapping.items() if v.get("confirmed") and v.get("orderBookId")}

    snap_path = Path(config.anchor("cache")) / "avanza_audit_snapshot.json"
    prev = json.loads(snap_path.read_text()) if snap_path.exists() else {}

    today = datetime.now(timezone.utc).date().isoformat()
    current = dict(prev)
    newly_flagged = []
    print(f"[audit] verifierar {len(confirmed)} bekräftade mappningar...")
    for i, (t, v) in enumerate(sorted(confirmed.items()), 1):
        oid = v["orderBookId"]
        try:
            info = _get(f"/_api/market-guide/stock/{oid}")
            ok = bool(info)
        except Exception:  # noqa: BLE001
            ok = False
        status = "ok" if ok else "error"
        was_ok = prev.get(t, {}).get("status") in (None, "ok")
        if was_ok and status == "error":
            newly_flagged.append(t)
            print(f"  [{i:>4}/{len(confirmed)}] {t:<14} NY FLAGGA – kunde inte verifieras längre")
        entry = dict(prev.get(t) or {})
        entry.update({"status": status, "checked": today, "orderBookId": oid, "title": v.get("title")})
        # first_seen sätts EN gång (befintliga poster utan fältet får dagens
        # datum – ärligt "bevakningen började nu", aldrig bakdaterat/gissat)
        entry.setdefault("first_seen", today)
        if ok:
            entry["last_ok"] = today
        current[t] = entry
        time.sleep(_PAUSE_S)

    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

    # Överlevnadsprojektion – skrivs om varje körning (liggaren i snapshoten
    # är sanningskällan; CSV:n är en läsvänlig export för backtest/manuell koll).
    surv = Path(config.anchor("results")) / "universe_survival.csv"
    surv.parent.mkdir(parents=True, exist_ok=True)
    with open(surv, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["ticker", "title", "status", "first_seen",
                                           "last_ok", "checked"], extrasaction="ignore")
        w.writeheader()
        for t in sorted(current):
            w.writerows([{"ticker": t, **current[t]}])
    print(f"[audit] överlevnadsliggare ({len(current)} tickers) -> {surv}")

    if not newly_flagged:
        n_error = sum(1 for s in current.values() if s.get("status") == "error")
        print(f"[audit] inga NYA avvikelser sedan förra körningen ({len(confirmed)} kontrollerade, "
              f"{n_error} sedan tidigare kända fel) -> {snap_path}")
        return

    print(f"\n[audit] {len(newly_flagged)} NYA avvikelser – korsrefererar mot cachad MFN-data...")
    rows = []
    for t in newly_flagged:
        hint = _mfn_delisting_hint(t)
        if hint:
            reason = f"PM nämner \"{hint['keyword']}\""
        else:
            reason = "okänd (ingen MFN-nyckelordsträff) – manuell koll"
        rows.append({
            "audit_date": today, "ticker": t, "orderBookId": confirmed[t]["orderBookId"],
            "avanza_titel": confirmed[t].get("title"), "trolig_orsak": reason,
            "styrkande_pm_titel": (hint or {}).get("title") or "",
            "styrkande_pm_datum": (hint or {}).get("date") or "",
            "styrkande_pm_url": (hint or {}).get("url") or "",
        })
        print(f"  {t:<14} {reason}")

    out = Path(config.anchor("results")) / "avanza_delisting_audit.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["audit_date", "ticker", "orderBookId", "avanza_titel", "trolig_orsak",
           "styrkande_pm_titel", "styrkande_pm_datum", "styrkande_pm_url"]
    file_exists = out.exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if not file_exists:
            w.writeheader()
        w.writerows(rows)
    print(f"\n[audit] {len(rows)} rader TILLAGDA (ackumulerande, historik bevaras) -> {out}")


def calendar(segment: Optional[str] = None) -> None:
    """RAPPORTKALENDER – hämtar keyIndicators.nextReport/previousReport
    (VERIFIERADE fält ur skarp INVE-B-probe: {"date": "2026-07-16",
    "reportType": "INTERIM", "isConfirmed": true}) för segmentets bekräftade
    mappningar och skriver <results_dir>/report_calendar.csv sorterad på
    nästa rapportdatum. Detta är en datalucka MFN aldrig kan fylla – feeden
    innehåller bara REDAN PUBLICERADE PM, aldrig kommande datum.

    Användning: PEAD-planering (veta NÄR rapporter kommer, inte bara reagera
    efteråt) och dashboarden ("dagar till rapport"). OBS point-in-time-
    ärlighet: detta är en NU-ögonblicksbild – kommande rapportdatum fanns
    inte att veta historiskt, så fältet får ALDRIG bli en ML-tränings-
    feature bakåt i tiden (lookahead per definition). Endast framåtblickande
    användning. Osäkra mappningar hoppas över (samma regel som extract()).

        python -m altdata.avanza calendar large
    """
    import csv as _csv

    mp = _map_path()
    if not mp.exists():
        print(f"Ingen {mp} – kör 'match' först.")
        return
    mapping = json.loads(mp.read_text())
    tickers, sector_map, cap_map, name_map, results_dir = _resolve_universe(segment)
    wanted = {t for t in tickers if cap_map.get(t) != "Fond" and sector_map.get(t) != "Fond"}
    candidates = sorted(t for t in wanted & mapping.keys()
                        if mapping[t].get("confirmed") and mapping[t].get("orderBookId"))

    rows, fail = [], 0
    print(f"[calendar] hämtar rapportdatum för {len(candidates)} bolag...")
    for i, t in enumerate(candidates, 1):
        try:
            info = _get(f"/_api/market-guide/stock/{mapping[t]['orderBookId']}")
        except Exception:  # noqa: BLE001
            fail += 1
            continue
        finally:
            time.sleep(_PAUSE_S)
        ki = info.get("keyIndicators") or {}
        nr = ki.get("nextReport") or {}
        pr = ki.get("previousReport") or {}
        if not nr.get("date") and not pr.get("date"):
            continue
        rows.append({
            "ticker": t, "name": name_map.get(t, t),
            "next_report_date": nr.get("date") or "",
            "next_report_type": nr.get("reportType") or "",
            "next_report_confirmed": nr.get("isConfirmed"),
            "previous_report_date": pr.get("date") or "",
        })
        if i % 50 == 0:
            print(f"  ...{i}/{len(candidates)}")

    rows.sort(key=lambda r: r["next_report_date"] or "9999")
    out = Path(results_dir) / "report_calendar.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["ticker", "name", "next_report_date",
                                           "next_report_type", "next_report_confirmed",
                                           "previous_report_date"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[calendar] {len(rows)} bolag med rapportdatum ({fail} fel) -> {out}")
    upcoming = [r for r in rows if r["next_report_date"]][:15]
    if upcoming:
        print("\n  NÄRMAST KOMMANDE RAPPORTER:")
        for r in upcoming:
            conf = "bekräftad" if r["next_report_confirmed"] else "prel."
            print(f"   {r['next_report_date']}  {r['ticker']:<14} {str(r['name'])[:28]:<28} "
                  f"{r['next_report_type']} ({conf})")


# Bolagsformer som otvetydigt INTE är svenska (ASA=norskt publikt bolag,
# A/S=danskt, Oyj=finskt, P/F=färöiskt) – VERIFIERAT bättre signal än att
# gissa på tickerformat: en naiv "tickern slutar på O"-regel fångar äkta
# svenska bolag som Ratos/Volati/Garo/Axfood (198 falska positiva mot 109
# äkta när vi provade, 2026-07-15).
_FOREIGN_FORM_RE = re.compile(r"\bASA\b|\bA/S\b|\bOyj\b|\bP/F\b", re.I)


def _foreign_form_candidates() -> list:
    """Alla tickers i sweden_universe.csv vars bolagsnamn har en otvetydigt
    utländsk juridisk bolagsform. Verkligt fynd (2026-07-15): 109 sådana
    bolag, bl.a. hela EQNRO/YARO/ORKO/AKERO/MEDIO-familjen som redan
    dokumenterats som nordiska "O"-suffix-tickers i _ticker_variants ovan."""
    import csv as _csv
    path = Path(__file__).parent.parent / "data" / "sweden_universe.csv"
    out = []
    with open(path, encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            if _FOREIGN_FORM_RE.search(row.get("name", "")):
                out.append(row["ticker"])
    return out


def check_marketplace(scope: str = "all", tickers: Optional[list] = None) -> None:
    """Kontrollerar Avanzas EGET listing.marketPlaceName/countryCode-fält
    (StockInfo.listing – samma /_api/market-guide/stock/{id}-svar som
    probe()/extract() redan hämtar, INGEN ny endpoint, fältnamnen
    VERIFIERADE mot avanza-mcp-projektets Listing/StockInfo-modeller) för
    att avgöra VILKEN BÖRS ett bolag faktiskt handlas på via Avanza – det
    verkliga facit, inte en gissning ur tickerformat eller tredjepartskällor.

    Verkligt fall som motiverade detta: Medistim ASA (MEDIO.ST) – Yahoo/
    StockAnalysis/MarketScreener kallar den "Nasdaq Stockholm"/"First
    North", men Avanzas EGEN app visar "Oslo Børs | Aktie", NOK. Tredje-
    partskällornas '.ST'-tickerformat är alltså INTE bevis på en äkta
    svensk notering – bara Avanzas egna listing-fält är det.

    Avanza saknar (verifierat mot tre oberoende community-projekt som
    reverse-engineerat deras API – avanza-mcp, fhqvst/avanza, Qluxzz/avanza,
    plus en olöst feature-request från 2021 i den sistnämnda) en dokumenterad
    endpoint för att LISTA alla aktier på en börs – ingen bulk-lösning
    byggs därför. Istället körs kontrollen BOLAG FÖR BOLAG mot de tickers
    vi redan matchat (samma princip, bara fler anrop):

    scope: 'all' (default – ALLA confirmed:true-poster i avanza_map.json,
    ~1000+ bolag, grundligast: fångar även felklassade bolag UTAN utländsk
    bolagsform i namnet) eller 'suspects' (bara _foreign_form_candidates –
    de ~109 bolagen med ASA/A-S/Oyj/P-F i namnet, snabbare).
    tickers: uttrycklig lista – åsidosätter scope helt (för test/enstaka bolag).

    Läser orderBookId ur cache/avanza_map.json (BARA confirmed:true – en
    osäker matchning får aldrig ligga till grund för att ta bort ett
    bolag). Skriver cache/avanza_marketplace_check.csv: ticker, namn,
    Avanzas marketPlaceName, countryCode, currency, recommend_remove
    (countryCode != 'SE'). Tar INTE bort något själv – det är ett separat,
    medvetet manuellt steg (universe_remove nedan) på verifierad data.

        python -m altdata.avanza check_marketplace           # alla ~1000+ matchade bolag
        python -m altdata.avanza check_marketplace suspects  # bara de 109 misstänkta
    """
    import csv as _csv

    mapping = json.loads(_map_path().read_text()) if _map_path().exists() else {}
    if tickers is not None:
        cand = tickers
    elif scope == "suspects":
        cand = _foreign_form_candidates()
    else:
        cand = sorted(t for t, e in mapping.items() if e.get("confirmed") and e.get("orderBookId"))

    rows, no_match = [], []
    for i, t in enumerate(cand, 1):
        entry = mapping.get(t)
        if not entry or not entry.get("confirmed") or not entry.get("orderBookId"):
            no_match.append(t)
            continue
        try:
            info = _get(f"/_api/market-guide/stock/{entry['orderBookId']}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>4}/{len(cand)}] {t:<14} FEL: {e}")
            continue
        finally:
            time.sleep(_PAUSE_S)
        listing = info.get("listing") or {}
        mp, cc = listing.get("marketPlaceName") or "", listing.get("countryCode")
        rows.append({"ticker": t, "name": entry.get("title") or t,
                     "market_place": mp, "country_code": cc or "",
                     "currency": listing.get("currency") or "",
                     "recommend_remove": cc != "SE"})
        if i % 20 == 0:
            print(f"  ...{i}/{len(cand)}")

    out = Path(config.anchor("cache")) / "avanza_marketplace_check.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["ticker", "name", "market_place",
                                           "country_code", "currency", "recommend_remove"])
        w.writeheader()
        w.writerows(rows)

    foreign = [r for r in rows if r["recommend_remove"]]
    swedish = [r for r in rows if not r["recommend_remove"]]
    print(f"\n[check_marketplace] {len(rows)} kontrollerade ({len(no_match)} utan "
          f"bekräftad Avanza-matchning, hoppade över) -> {out}")
    print(f"\n  UTLÄNDSK BÖRS ({len(foreign)} st – REKOMMENDERAS BORTTAGNA):")
    for r in sorted(foreign, key=lambda r: r["ticker"]):
        print(f"    {r['ticker']:<14} {str(r['name'])[:30]:<30} {r['market_place']:<32} "
              f"{r['country_code']:<3} {r['currency']}")
    print(f"\n  BEKRÄFTAT SVENSK BÖRS ({len(swedish)} st – behålls):")
    for r in sorted(swedish, key=lambda r: r["ticker"])[:10]:
        print(f"    {r['ticker']:<14} {str(r['name'])[:30]:<30} {r['market_place']}")
    if len(swedish) > 10:
        print(f"    ... och {len(swedish) - 10} till")
    if no_match:
        shown = ", ".join(no_match[:20])
        print(f"\n  UTAN BEKRÄFTAD MATCHNING ({len(no_match)} st, granskades INTE – "
              f"kör 'match' först om de ska kollas): {shown}"
              + (f" ... och {len(no_match) - 20} till" if len(no_match) > 20 else ""))


# ── Börslist-enumerering (SCHEMA-UPPTÄCKANDE PROBE, inget byggt på gissning) ──
# MÅL (uttryckligt önskemål): kunna LISTA alla aktier per svensk börslista hos
# Avanza → (1) avnoteringsbevakning genom att diffa listan över tid, (2)
# IPO-koll (nya bolag dyker upp), (3) på sikt ersätta Yahoo helt som referens.
# LÄGET: ingen av de tre community-projekt som reverse-engineerat Avanzas API
# (avanza-mcp, fhqvst/avanza, Qluxzz/avanza) dokumenterar en sådan endpoint –
# men Avanza HAR verifierade filter-endpoints för certifikat/warranter/ETF:er
# (/_api/market-certificate-filter/ m.fl., wire-format VERIFIERAT ur avanza-
# mcp:s modeller: POST {"filter":{},"offset":0,"limit":N,"sortBy":{"field",
# "order"}} → svar {"<typ>s":[...],"filterOptions":...}). En motsvarande
# aktie-variant är därför TROLIG men OVERIFIERAD – kandidaterna nedan är
# mönster-härledda gissningar som PROBAS mot skarpa svar på Pi:n innan någon
# parser byggs (samma disciplin som probe()/chart_probe()/aktiehistorik).
_LIST_CANDIDATES = [
    # (metod, path, payload) – payload=None => GET
    ("POST", "/_api/market-stock-filter/",
     {"filter": {}, "offset": 0, "limit": 5, "sortBy": {"field": "name", "order": "asc"}}),
    ("POST", "/_api/market-stock-filter/", {"offset": 0, "limit": 5}),
    ("GET", "/_api/market-stock-filter/filter-options", None),
    # Äldre mobil-API:t (fhqvst/avanza byggde mot /_mobile/-paths historiskt).
    # FÖRKASTAD (verifierad 2026-07-15): status=200 här är en FALSK POSITIV -
    # Content-Type text/html, kroppen är Avanzas SPA-index.html (routern faller
    # igenom till appskalet för alla okända paths istället för en riktig 404).
    # Ingen riktig API-endpoint. Se list_probe2()s docstring för fullständig
    # dödgångs-slutsats för hela börslist-enumereringsspåret.
    ("GET", "/_mobile/market/stocks?limit=5", None),
    # IPO-kandidater (Avanzas webbsida har en börsintroduktioner-vy)
    ("GET", "/_api/market-ipo/", None),
    ("GET", "/_api/market-guide/ipos", None),
]
# Chart-djup bortom five_years – avgör om Yahoo (15+ års historik, backtesten
# startar 2010) alls KAN ersättas för prisdatan eller bara kompletteras.
_CHART_DEPTH_CANDIDATES = ("ten_years", "fifteen_years", "twenty_years", "max", "infinity")


def list_probe() -> None:
    """Probar kandidat-endpoints för börslist-enumerering + IPO-listor +
    djupare prishistorik. Skriver ut status/toppnycklar per kandidat och
    sparar ALLA råa svar till cache/_avanza_list_probe.json – parsern byggs
    FÖRST mot ett skarpt verifierat schema, aldrig mot en gissning.

        python -m altdata.avanza list_probe
    """
    dump: dict = {}
    print("[list_probe] == A. Börslist-/IPO-kandidater ==")
    for method, path, payload in _LIST_CANDIDATES:
        key = f"{method} {path}"
        # Två kandidater kan dela metod+path (olika payload-varianter) – utan
        # unik nyckel skrev variant 2:s svar TYST över variant 1:s i dumpen
        # (upptäckt av testet: en 404 raderade 200-beviset).
        n = 2
        while key in dump:
            key = f"{method} {path} (variant {n})"
            n += 1
        try:
            r = requests.request(method, f"{BASE}{path}", json=payload,
                                 headers={"User-Agent": _UA, "Accept": "application/json"},
                                 timeout=30)
            body = r.json() if (r.content and "json" in (r.headers.get("Content-Type") or "")) else None
            dump[key] = {"status": r.status_code, "body": body}
            if r.status_code == 200 and isinstance(body, dict):
                lists = {k: len(v) for k, v in body.items() if isinstance(v, list)}
                print(f"  200  {key}")
                print(f"       toppnycklar: {list(body.keys())}")
                if lists:
                    print(f"       list-fält: {lists}")
                first_list = next((v for v in body.values() if isinstance(v, list) and v), None)
                if first_list and isinstance(first_list[0], dict):
                    print(f"       fältnamn i EN post: {list(first_list[0].keys())}")
            else:
                print(f"  {r.status_code:>3}  {key}")
        except Exception as e:  # noqa: BLE001
            dump[key] = {"status": None, "error": str(e)}
            print(f"  FEL  {key}: {e}")
        finally:
            time.sleep(_PAUSE_S)

    print("\n[list_probe] == B. Chart-djup bortom five_years (Yahoo-ersättningsfrågan) ==")
    mapping = json.loads(_map_path().read_text()) if _map_path().exists() else {}
    entry = next((e for e in mapping.values() if e.get("confirmed") and e.get("orderBookId")), None)
    if entry is None:
        print("  ingen bekräftad orderBookId i avanza_map.json – kör 'match' först, hoppar över B.")
    else:
        print(f"  testbolag: {entry.get('title')!r} (orderBookId={entry['orderBookId']})")
        for period in _CHART_DEPTH_CANDIDATES:
            try:
                data = _get(f"/_api/price-chart/stock/{entry['orderBookId']}",
                            {"timePeriod": period})
                points = next((data[k] for k in _CHART_POINT_KEYS
                               if isinstance(data.get(k), list)), None)
                dump[f"chart {period}"] = {"status": 200,
                                           "n_points": len(points) if points else 0,
                                           "first": (points[0] if points else None),
                                           "last": (points[-1] if points else None)}
                if points:
                    print(f"  timePeriod={period:<14} {len(points)} punkter  "
                          f"[{points[0].get('timestamp')} -> {points[-1].get('timestamp')}]")
                else:
                    print(f"  timePeriod={period:<14} 200 men ingen punktlista "
                          f"(nycklar: {list(data.keys())})")
            except Exception as e:  # noqa: BLE001
                dump[f"chart {period}"] = {"status": None, "error": str(e)}
                print(f"  timePeriod={period:<14} FEL: {e}")
            finally:
                time.sleep(_PAUSE_S)

    out = Path(config.anchor("cache")) / "_avanza_list_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[list_probe] fullständiga svar sparade: {out}")
    print("[list_probe] Klistra in utskriften – listsnapshot/IPO-liggare och ev. "
          "Yahoo-ersättning byggs FÖRST mot ett verifierat schema.")


# 2010-01-01 i ms sedan epoch – backtesten startar där, så chart-djupet måste
# nå MINST hit för att Avanza ens vara en KANDIDAT till Yahoo-ersättning.
_BACKTEST_START_MS = 1262304000000
# Veckodata (backtestens upplösning) kräver ~7 dagars punktavstånd. Grövre
# än så (t.ex. 'infinity'-periodens ~30 dagar/punkt, verifierat 2026-07-15
# mot AAK.ST: 250 punkter över 20,8 år) duger inte som PRIMÄRKÄLLA även om
# djupet räcker – bara som komplement/sanity-check.
_MAX_WEEKLY_GAP_DAYS = 10.0

# FÖRKASTAT SPÅR (verifierat 2026-07-15): /_mobile/market/stocks gav alltid
# status=200 i list_probe() steg A, men det var en FALSK POSITIV - riktig
# nyttolast (curl) visade Content-Type text/html och en kropp som ÄR
# Avanzas SPA-index.html (routern faller igenom till appskalet för alla
# okända paths). Ingen paginerings-/limit-probe kan rädda en endpoint som
# inte finns - togs därför bort härifrån istället för att lämnas som en
# probe som alltid rapporterar "200" men aldrig ett tolkningsbart svar.
# SLUTSATS för hela börslist-enumereringsspåret: tre oberoende community-
# projekt (avanza-mcp, fhqvst/avanza, Qluxzz/avanza) dokumenterar ingen
# bulk-börslista, och ingen av våra egna gissade kandidater (market-stock-
# filter, market-ipo, market-guide/ipos, mobile/market/stocks) höll. Avanza
# kan alltså INTE ersätta JerBouma/FinanceDatabase + manuell sök-matchning
# för universum-enumerering eller avnoterings-/IPO-bevakning.


def list_probe2(chart_ticker: str = "AAK.ST") -> None:
    """Chart-djup mot ett ÄLDRE, etablerat bolag (default AAK.ST) - avgör om
    Avanza kan ersätta/komplettera Yahoo för backtest-prishistorik. list_probe()s
    testbolag (TRATON SE, IPO 2019) kunde inte skilja "hela historiken" från
    "takad vid ~7 år" eftersom TRATON inte HAR äldre historik att sakna;
    AAK/Volvo/SEB gör. Flaggar både om perioden når 2010 OCH om punkttätheten
    räcker för veckodata (se _MAX_WEEKLY_GAP_DAYS) - ett djup som når 2010
    men bara ger månadsupplösning duger inte som primärkälla.

        python -m altdata.avanza list_probe2                # chart mot AAK.ST
        python -m altdata.avanza list_probe2 VOLV-B.ST       # annat bolag
    """
    dump: dict = {}
    print(f"[list_probe2] Chart-djup mot ÄLDRE bolag ({chart_ticker}) ==")
    mapping = json.loads(_map_path().read_text()) if _map_path().exists() else {}
    entry = mapping.get(chart_ticker)
    if not entry or not entry.get("confirmed") or not entry.get("orderBookId"):
        print(f"  {chart_ticker}: ingen bekräftad orderBookId i avanza_map.json – "
              f"kör 'match large' (eller motsvarande segment) först.")
    else:
        print(f"  testbolag: {entry.get('title')!r} (orderBookId={entry['orderBookId']})")
        for period in _CHART_DEPTH_CANDIDATES:
            try:
                data = _get(f"/_api/price-chart/stock/{entry['orderBookId']}",
                            {"timePeriod": period})
                points = next((data[k] for k in _CHART_POINT_KEYS
                               if isinstance(data.get(k), list)), None)
                first_ts = points[0].get("timestamp") if points else None
                last_ts = points[-1].get("timestamp") if points else None
                reaches_2010 = (first_ts is not None and first_ts <= _BACKTEST_START_MS)
                gap_days = None
                if points and len(points) > 1 and first_ts is not None and last_ts is not None:
                    gap_days = (last_ts - first_ts) / 1000 / 86400 / (len(points) - 1)
                weekly_ok = gap_days is not None and gap_days <= _MAX_WEEKLY_GAP_DAYS
                dump[f"chart {period}"] = {"status": 200,
                                           "n_points": len(points) if points else 0,
                                           "first": (points[0] if points else None),
                                           "last": (points[-1] if points else None),
                                           "reaches_2010": reaches_2010,
                                           "avg_gap_days": gap_days,
                                           "weekly_resolution_ok": weekly_ok}
                if points:
                    depth_flag = "NÅR 2010" if reaches_2010 else "täcker INTE 2010"
                    res_flag = (f"~{gap_days:.1f} dagar/punkt, "
                                + ("veckoduglig" if weekly_ok else "FÖR GLEST för veckodata")
                                if gap_days is not None else "")
                    print(f"  timePeriod={period:<14} {len(points)} punkter  "
                          f"[{first_ts} -> {last_ts}]  ({depth_flag}, {res_flag})")
                else:
                    print(f"  timePeriod={period:<14} 200 men ingen punktlista "
                          f"(nycklar: {list(data.keys())})")
            except Exception as e:  # noqa: BLE001
                dump[f"chart {period}"] = {"status": None, "error": str(e)}
                print(f"  timePeriod={period:<14} FEL: {e}")
            finally:
                time.sleep(_PAUSE_S)

    out = Path(config.anchor("cache")) / "_avanza_list_probe2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[list_probe2] fullständiga svar sparade: {out}")


# Båda universum-filerna – NGM/Spotlight-bolagen (data/sweden_universe_ngm.csv,
# '.NGM'-suffix) fångades i check_marketplace(scope='all') precis som
# huvudlistan, och behöver kunna rensas på samma sätt (verkligt fall:
# BTC.B.NGM/DIV.B.NGM m.fl. visade sig vara kanadensiska/amerikanska bolag).
_UNIVERSE_FILES = ("sweden_universe.csv", "sweden_universe_ngm.csv")


def universe_remove(tickers: list, dry_run: bool = True) -> None:
    """Tar bort angivna tickers HELT ur BÅDA universum-filerna (vardera
    tickern tas bort ur den fil den faktiskt finns i) – det avsiktliga,
    manuella steget EFTER check_marketplace() gett ett verifierat facit
    (Avanzas eget countryCode != 'SE'). Kör ALDRIG automatiskt på
    check_marketplace()s output – en människa ska se listan (samma
    disciplin som tradingview.py:s universe()/universe_ngm(): dry-run visar
    alltid vad som SKULLE hända innan write).

        python -m altdata.avanza universe_remove MEDIO.ST,EQNRO.ST      # dry-run
        python -m altdata.avanza universe_remove MEDIO.ST,EQNRO.ST write
    """
    import csv as _csv
    remove_set = {t.strip().upper() for t in tickers}
    found_total = set()

    for fname in _UNIVERSE_FILES:
        path = Path(__file__).parent.parent / "data" / fname
        if not path.exists():
            continue
        rows = list(_csv.DictReader(open(path, encoding="utf-8")))
        removed = [r for r in rows if r["ticker"].strip().upper() in remove_set]
        if not removed:
            continue
        kept = [r for r in rows if r["ticker"].strip().upper() not in remove_set]
        found_total |= {r["ticker"].strip().upper() for r in removed}
        print(f"[universe_remove] {len(removed)} tickers i {fname} ({len(rows)} rader totalt):")
        for r in removed:
            print(f"    - {r['ticker']:<14} {r['name']}")
        if not dry_run:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(kept)
            print(f"  skrev {len(kept)} kvarvarande rader -> {path}")

    missing = remove_set - found_total
    if missing:
        print(f"\n  VARNING: {len(missing)} ticker(s) fanns i INGEN av {_UNIVERSE_FILES}: "
              f"{', '.join(sorted(missing))}")
    if dry_run:
        print("\n  DRY-RUN – inget skrivet. Kör med 'write' som sista argument för att faktiskt ta bort.")
    else:
        print(f"\n[universe_remove] klart – {len(found_total)}/{len(remove_set)} tickers borttagna totalt.")


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
    elif cmd == "inspect":
        inspect_probe()
    elif cmd == "chart_probe":
        chart_probe(sys.argv[2] if len(sys.argv) > 2 else "SAAB-B.ST")
    elif cmd == "match":
        match(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "extract":
        extract(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "audit":
        audit()
    elif cmd == "calendar":
        calendar(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "revalidate":
        revalidate()
    elif cmd == "check_marketplace":
        check_marketplace(sys.argv[2] if len(sys.argv) > 2 else "all")
    elif cmd == "list_probe":
        list_probe()
    elif cmd == "list_probe2":
        list_probe2(sys.argv[2] if len(sys.argv) > 2 else "AAK.ST")
    elif cmd == "universe_remove":
        if len(sys.argv) < 3:
            print("Ange kommaseparerade tickers: python -m altdata.avanza universe_remove "
                  "MEDIO.ST,EQNRO.ST [write]")
            return
        tickers = [t.strip() for t in sys.argv[2].split(",") if t.strip()]
        universe_remove(tickers, dry_run=not (len(sys.argv) > 3 and sys.argv[3] == "write"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
