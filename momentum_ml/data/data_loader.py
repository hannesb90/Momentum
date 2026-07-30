"""
data/data_loader.py – Hämtar och cachar veckodata via yfinance.

OBS: yfinance ger bara historik för tickers som finns/går att slå upp
idag. Aktier som avnoterats, gått i konkurs eller blivit uppköpta
saknas helt, vilket ger survivorship bias i backtester – CAGR/Sharpe
tenderar att överskattas eftersom universumet implicit bara innehåller
"vinnare". För kapital i den storleksordning som motiverar den här
strategin bör en datakälla med korrekt point-in-time-universum (t.ex.
Polygon.io eller Norgate Data, båda betaltjänster) användas innan
resultat tas på allvar. Att byta källa innebär att skriva en ny
funktion med samma retur-kontrakt som fetch_weekly_data (Dict[ticker,
DataFrame] med kolumnerna Open/High/Low/Close/Volume).
"""

import os
import pickle
import hashlib
import datetime as dt
import pandas as pd
import yfinance as yf
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from backtest import pipeline_diagnostics as _diag


def _cache_path(key: str) -> Path:
    Path(config.CACHE_DIR).mkdir(exist_ok=True)
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return Path(config.CACHE_DIR) / f"{h}.pkl"


def _prune_stale_cache(max_age_days: Optional[int] = None) -> None:
    """Rensar gamla kursdata-pkl:er. Cache-nyckeln innehåller DAGENS datum
    (medvetet – annars serverades frusen kursdata dag efter dag, se
    fetch_weekly_data), men det betyder också att varje dag skapar en NY
    pkl och gårdagens aldrig mer träffas. Utan städning växer cache/ med
    en full universum-pickle (tiotals MB) per dag och segment – gigabyte
    på några månader på Pi:ns SD-kort. Rensar ENBART *.pkl direkt i
    CACHE_DIR (aldrig underkataloger som mfn/, aldrig andra filtyper som
    portfolio_holdings.csv)."""
    if max_age_days is None:
        max_age_days = int(getattr(config, "PRICE_CACHE_MAX_AGE_DAYS", 10))
    if max_age_days <= 0:
        return
    import time
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        for p in Path(config.CACHE_DIR).glob("*.pkl"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        return
    if removed:
        print(f"[DataLoader] Rensade {removed} kursdata-cachefiler äldre än {max_age_days} dagar.")


# '.NGM'-suffix (data/sweden_universe_ngm.csv, byggd av
# altdata/tradingview.py:s universe_ngm()) -> hämtas via Avanza istället för
# Yahoo. Grund: NGM/Spotlight (sedan NGM:s köp av Spotlight 2023 samma
# börskod hos TradingView) saknar en pålitlig Yahoo-mappning (verifierat via
# gaps()-kommandot: 0/8 träff på '.NGM'-suffixet, och '.ST' gav träff för en
# del men med en KÄND risk för symbolkrock mot Nasdaq Stockholm-instrument
# med samma kortnamn). Avanza handlar däremot HELA svenska marknaden.
_AVANZA_SUFFIX = ".NGM"


def _fetch_avanza_weekly(tickers: List[str]) -> Dict[str, "pd.DataFrame"]:
    """Hämtar veckovis OHLCV via Avanzas prisdiagram för '.NGM'-tickers.
    Läser orderBookId ur cache/avanza_map.json (byggd av
    'python -m altdata.avanza match ngm') – BARA confirmed:true-poster
    används, samma regel som resten av Avanza-integrationen (en osäker
    matchning ska aldrig tyst användas som om den vore bekräftad).

    VERIFIERAT (chart_probe mot Plejd/Kopparbergs Bryggeri): timePeriod=
    'five_years' ger redan VECKOUPPLÖST data, ingen resampling behövs. INTE
    kontrollerat: om detta håller för ALLA NGM/Spotlight-bolag eller om
    vissa har kortare/glesare historik – _clean()s MIN_HISTORY_WEEKS-filter
    sorterar bort dem som inte räcker, snarare än att anta att de gör det."""
    if not tickers:
        return {}
    from altdata import avanza
    map_path = Path(config.anchor("cache")) / "avanza_map.json"
    if not map_path.exists():
        print(f"  [WARN] {map_path} saknas – kör 'python -m altdata.avanza match ngm' "
              f"först. Hoppar över {len(tickers)} NGM-tickers.")
        return {}
    import json as _json
    mapping = _json.loads(map_path.read_text(encoding="utf-8"))

    result: Dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        entry = mapping.get(ticker)
        if not entry or not entry.get("confirmed") or not entry.get("orderBookId"):
            print(f"  [WARN] {ticker}: ingen bekräftad Avanza-matchning, hoppar över.")
            continue
        try:
            df = avanza.fetch_chart_ohlcv(entry["orderBookId"], period="five_years")
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] {ticker}: Avanza-hämtning misslyckades ({e}), hoppar över.")
            continue
        df = _clean(df, ticker) if df is not None else None
        if df is not None:
            result[ticker] = df
        import time as _time
        _time.sleep(getattr(avanza, "_PAUSE_S", 0.5))
    return result


def fetch_weekly_data(
    tickers: List[str],
    start: str = config.START_DATE,
    end: Optional[str] = config.END_DATE,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Hämtar OHLCV-veckodata för en lista tickers.
    Returnerar dict {ticker: DataFrame med kolumner Open/High/Low/Close/Volume}.

    Tickers med '.NGM'-suffix hämtas via Avanza (se _fetch_avanza_weekly/
    _AVANZA_SUFFIX ovan) istället för Yahoo Finance.
    """
    # BUGG (fixad): end=None ("idag", se config.END_DATE) blev tidigare
    # BOKSTAVLIGEN strängen "None" i cache-nyckeln f-strängen – identisk
    # nyckel varje dag, så en gång cachad returnerades samma frusna
    # kursdata dag efter dag i stället för att hämtas på nytt "idag",
    # trots kommentaren "None = idag". Löst genom att slå upp dagens datum
    # EN gång och använda det UPPLÖSTA värdet (inte den råa None) både i
    # cache-nyckeln och i själva yf.download-anropet, så nyckeln faktiskt
    # ändras dag för dag och en ny hämtning triggas.
    _diag.record_universe_stage("fetch_requested", tickers)

    resolved_end = end or dt.date.today().isoformat()
    # min_history ingår i nyckeln: cachen lagrar data EFTER historikfiltret, så
    # en ändrad tröskel måste ge en ny cache (annars returneras gamla survivors).
    cache_key = f"{','.join(sorted(tickers))}_{start}_{resolved_end}_h{config.MIN_HISTORY_WEEKS}"
    cp = _cache_path(cache_key)

    if use_cache and cp.exists():
        print(f"[DataLoader] Laddar cache: {cp}")
        with open(cp, "rb") as f:
            cached = pickle.load(f)
        _diag.record_universe_stage("fetch_cleaned", list(cached.keys()))
        return cached

    yahoo_tickers = [t for t in tickers if not t.endswith(_AVANZA_SUFFIX)]
    ngm_tickers = [t for t in tickers if t.endswith(_AVANZA_SUFFIX)]

    result: Dict[str, pd.DataFrame] = {}

    if yahoo_tickers:
        print(f"[DataLoader] Hämtar {len(yahoo_tickers)} tickers från Yahoo Finance...")
        raw = yf.download(
            yahoo_tickers,
            start=start,
            end=resolved_end,
            interval="1wk",
            auto_adjust=True,
            progress=True,
            threads=True,
        )

        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in yahoo_tickers:
                try:
                    df = raw.xs(ticker, axis=1, level=1).copy()
                    df = _clean(df, ticker)
                    if df is not None:
                        result[ticker] = df
                except KeyError:
                    print(f"  [WARN] {ticker}: ingen data, hoppar över.")
        else:
            # Enstaka ticker
            df = _clean(raw, yahoo_tickers[0])
            if df is not None:
                result[yahoo_tickers[0]] = df

    if ngm_tickers:
        print(f"[DataLoader] Hämtar {len(ngm_tickers)} NGM/Spotlight-tickers från Avanza...")
        result.update(_fetch_avanza_weekly(ngm_tickers))

    if not result:
        raise RuntimeError(
            "Ingen ticker gav tillräcklig data. Kontrollera nätverksåtkomst "
            "till Yahoo Finance/Avanza och att tickrarna/perioden är giltiga."
        )

    print(f"[DataLoader] Laddade {len(result)} tickers, "
          f"{min(len(v) for v in result.values())}–"
          f"{max(len(v) for v in result.values())} veckor vardera.")
    _diag.record_universe_stage("fetch_cleaned", list(result.keys()))

    with open(cp, "wb") as f:
        pickle.dump(result, f)
    _prune_stale_cache()   # dagliga nycklar → gårdagens pkl:er träffas aldrig mer

    return result


_SUSPICIOUS_JUMPS: List[Tuple[str, str, float]] = []   # (ticker, date_iso, ret) - se get_suspicious_jumps()


def get_suspicious_jumps(clear: bool = True) -> List[Tuple[str, str, float]]:
    """Hämtar alla misstänkta hopp flaggade av _check_suspicious_jumps sedan
    senaste rensning. Görs tillgänglig som en lista (inte bara konsol-print)
    så en anropare (main.py) kan korsreferera mot faktiska köp/sälj-signaler
    och avgöra vilka varningar som faktiskt påverkat en handel – se
    results/suspicious_jumps_held.csv."""
    jumps = list(_SUSPICIOUS_JUMPS)
    if clear:
        _SUSPICIOUS_JUMPS.clear()
    return jumps


def _check_suspicious_jumps(df: pd.DataFrame, ticker: str) -> None:
    """
    Flaggar (men korrigerar inte) veckoavkastningar över
    SUSPICIOUS_JUMP_THRESHOLD i magnitud. Sådana hopp kan vara legitima
    (vinstvarningar, biotech-resultat) eller artefakter av ojusterade
    corporate actions (splits/utdelningar som yfinance missat). Att
    auto-korrigera riskerar att introducera nya fel, så det här är bara
    en varning för manuell granskning.
    """
    weekly_ret = df["Close"].pct_change().dropna()
    jumps = weekly_ret[weekly_ret.abs() > config.SUSPICIOUS_JUMP_THRESHOLD]
    for date, ret in jumps.items():
        print(f"  [WARN] {ticker} {date.date()}: misstänkt hopp {ret:+.1%} "
              f"– kontrollera ev. ojusterad corporate action.")
        _SUSPICIOUS_JUMPS.append((ticker, date.date().isoformat(), float(ret)))


def _clean(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """Droppar NaN-rader, kontrollerar minimilängd."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [WARN] {ticker}: saknar kolumner {missing}.")
        return None

    df = df[required].copy()
    df.dropna(subset=["Close"], inplace=True)
    df["Volume"] = df["Volume"].fillna(0)
    df.sort_index(inplace=True)

    # Normalisera till en GEMENSAM måndags-ankrad veckokalender (BUGG, upptäckt
    # 2026-07-23 medan en användarfråga om "slår modellen index" granskades).
    # yfinance kan ankra en enskild tickers '1wk'-staplar på en ANNAN veckodag
    # än resten av universumet - verkligt fall: INCOAX.ST konsekvent
    # tisdags-ankrad sedan 2019-12-31 (343 rader), alla andra small/micro-
    # tickers måndags-ankrade. Utan normalisering blir "tisdagen" en HELT EGEN
    # rad i det kombinerade backtest-datumindexet (backtest/backtester.py:
    # dates = signals.index.unique()) - en extra "spökvecka" varje sådan
    # vecka. Small/Micro-segmentets holdout-stats visade 233 rapporterade
    # "veckor" mot en verklig kalenderlängd på ~116 (2024-04-29 -> idag) -
    # nästan exakt dubblat - vilket i sin tur gör _compute_stats CAGR/Sharpe/
    # Sortino fel (hårdkodat ann=52, weeks=len(rets): fel exponent på
    # annualiseringen när "veckorna" inte är riktiga kalenderveckor). Samma
    # mönster som redan flaggades och fixades i
    # backtest/accumulation.py:normalize_weekly_panel() - men den fixen
    # gällde bara ETT fristående forskningsskript, inte huvudpipelinen
    # (träning/features/backtest) som använder just den här funktionen. .last()
    # är en förenkling (ingen riktig OHLC-aggregering av High/Low/Open för de
    # sällsynta sammanslagna veckorna) men berör bara en handfull rader per
    # ticker, inte datan i stort.
    df = df.resample("W-MON").last().dropna(subset=["Close"])

    min_rows = config.MIN_HISTORY_WEEKS
    if len(df) < min_rows:
        print(f"  [WARN] {ticker}: för kort historik ({len(df)} veckor), "
              f"behöver minst {min_rows}.")
        return None

    _check_suspicious_jumps(df, ticker)

    return df


def load_sweden_universe(
    min_market_cap: Optional[List[str]] = None,
    include_funds: bool = True,
    include_sector_etfs: bool = True,
) -> "tuple[List[str], Dict[str, str], Dict[str, str]]":
    """
    Läser det förbyggda universumet av svenska börsbolag
    (data/sweden_universe.csv, källa: JerBouma/FinanceDatabase STO.csv,
    filtrerat till icke-avnoterade aktier med country=Sweden).

    min_market_cap: t.ex. ["Large Cap", "Mid Cap"] för att bara ta med
    de kategorierna. None = alla (inklusive Nano/Micro Cap). Gäller bara
    aktier - fonder/ETF:er (se nedan) tas alltid med oavsett.

    include_funds: lägger till data/sweden_funds.csv – breda svenska
    index-/stilfonder som handlas på börsen (XACT Sverige, OMXS30, Norden,
    Småbolag, High Dividend). Hävstångsprodukter (XACT Bear/Bull) och
    obligationsfonder är medvetet exkluderade: bear/bull har daglig
    ombalansering som ger decay över tid och är olämpliga för
    medelfristig momentum, och obligationsfonder är en annan
    tillgångsklass än aktiemomentum-strategin är byggd för.

    include_sector_etfs: lägger till data/sector_etfs.csv – riktiga
    GICS-sektor-ETF:er finns inte på den svenska börsen (bara breda
    index-/stilfonder, se ovan), så dessa är amerikanska SPDR-sektorfonder
    (XLK/XLF/XLE m.fl.) som ger sektor-momentum-signaler trots att
    aktieuniverset i övrigt är begränsat till Sverige.

    Returnerar (tickers, sector_map, cap_tier_map, name_map) – sector_map kan
    slås ihop med config.SECTOR_MAP för att sektorexponeringsspärren ska
    fungera även för dessa tickers. cap_tier_map ger market_cap_category
    per ticker, t.ex. för att mata in cap-tier som modell-feature
    (features/feature_engineering.py). name_map ger bolagsnamn per ticker
    (visas i frontend och möjliggör sök på namn).
    """
    import csv

    tickers: List[str] = []
    sector_map: Dict[str, str] = {}
    cap_tier_map: Dict[str, str] = {}
    name_map: Dict[str, str] = {}

    stocks_path = Path(__file__).parent / "sweden_universe.csv"
    with open(stocks_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if min_market_cap is not None and row["market_cap_category"] not in min_market_cap:
                continue
            tickers.append(row["ticker"])
            sector_map[row["ticker"]] = row["sector"]
            cap_tier_map[row["ticker"]] = row["market_cap_category"]
            name_map[row["ticker"]] = row["name"]

    if include_funds:
        funds_path = Path(__file__).parent / "sweden_funds.csv"
        with open(funds_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tickers.append(row["ticker"])
                sector_map[row["ticker"]] = row["sector"]
                cap_tier_map[row["ticker"]] = row["market_cap_category"]
                name_map[row["ticker"]] = row["name"]

    if include_sector_etfs:
        etf_path = Path(__file__).parent / "sector_etfs.csv"
        with open(etf_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tickers.append(row["ticker"])
                sector_map[row["ticker"]] = row["sector"]
                cap_tier_map[row["ticker"]] = row["market_cap_category"]
                name_map[row["ticker"]] = row["name"]

    return tickers, sector_map, cap_tier_map, name_map


def load_ngm_universe() -> "tuple[List[str], Dict[str, str], Dict[str, str], Dict[str, str]]":
    """Läser data/sweden_universe_ngm.csv (byggd av
    altdata/tradingview.py:s universe_ngm() – svenska aktier UTANFÖR
    Nasdaq Stockholm/First North, dvs NGM Main Regulated/Nordic SME +
    Spotlight, som TradingView sedan NGM:s köp av Spotlight 2023 redovisar
    under samma börskod). Tickers har '.NGM'-suffix (inte '.ST') – det är
    signalen fetch_weekly_data() använder för att hämta prisdata via
    Avanza istället för Yahoo (Yahoo saknar en pålitlig mappning för
    dessa börser, verifierat via tradingview.py:s gaps()-kommando).

    Filen är valfri (skapas bara efter ett explicit 'universe_ngm write')
    – saknas den returneras tomma listor, ingen krasch. Samma
    (tickers, sector_map, cap_tier_map, name_map)-kontrakt som
    load_sweden_universe() för att kunna slås ihop rakt av."""
    import csv

    tickers: List[str] = []
    sector_map: Dict[str, str] = {}
    cap_tier_map: Dict[str, str] = {}
    name_map: Dict[str, str] = {}

    ngm_path = Path(__file__).parent / "sweden_universe_ngm.csv"
    if not ngm_path.exists():
        return tickers, sector_map, cap_tier_map, name_map

    with open(ngm_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tickers.append(row["ticker"])
            sector_map[row["ticker"]] = row["sector"]
            cap_tier_map[row["ticker"]] = row["market_cap_category"]
            name_map[row["ticker"]] = row["name"]

    return tickers, sector_map, cap_tier_map, name_map


def filter_liquid_universe(
    data: Dict[str, pd.DataFrame],
    min_avg_turnover: float = config.UNIVERSE_MIN_AVG_TURNOVER,
    lookback_weeks: int = config.UNIVERSE_LIQUIDITY_LOOKBACK_WEEKS,
) -> Dict[str, pd.DataFrame]:
    """
    Filtrerar bort tickers med för låg genomsnittlig omsättning
    (Close * Volume) de senaste `lookback_weeks` veckorna. Tänkt att köras
    innan feature engineering/träning vid stora universum (hundratals/
    tusentals tickers), så att tunt handlade bolag inte drar ner
    datakvalitet och beräkningstid i resten av pipelinen.
    """
    filtered: Dict[str, pd.DataFrame] = {}
    dropped = []

    for ticker, df in data.items():
        recent = df.tail(lookback_weeks)
        avg_turnover = (recent["Close"] * recent["Volume"]).mean()
        if avg_turnover >= min_avg_turnover:
            filtered[ticker] = df
        else:
            dropped.append((ticker, avg_turnover))

    if dropped:
        print(f"[DataLoader] Likviditetsfilter: {len(dropped)} tickers under "
              f"tröskeln ({min_avg_turnover:,.0f}/vecka, {lookback_weeks}v snitt):")
        for ticker, turnover in sorted(dropped, key=lambda x: x[1]):
            print(f"  [LIQ] {ticker}: {turnover:,.0f}/vecka")

    print(f"[DataLoader] Kvar efter likviditetsfilter: "
          f"{len(filtered)}/{len(data)} tickers.")
    _diag.record_universe_stage("liquidity_filter", list(filtered.keys()))
    return filtered


def filter_active_universe(
    data: Dict[str, pd.DataFrame],
    max_stale_weeks: int = config.STALE_MAX_WEEKS,
) -> Dict[str, pd.DataFrame]:
    """
    Tar bort avnoterade/döda bolag: om en tickers SENASTE datapunkt är äldre än
    `max_stale_weeks` veckor före universumets senaste datum (referens = "nu")
    har bolaget ingen ny kurs och tolkas som avnoterat – det ska varken visas
    som en aktuell signal eller störa beräkningarna.

    OBS: detta tar även bort bolagets historik ur träningen. Det är ett pragmatiskt
    "städa bort döda namn"-filter; en SURVIVORSHIP-korrekt lösning (behåll döda
    bolags historik från en riktig avnoterings-datakälla) är ett separat, större
    steg.
    """
    if not data:
        return data
    last_dates = {t: df.index.max() for t, df in data.items() if len(df)}
    if not last_dates:
        return data
    ref = max(last_dates.values())
    cutoff = ref - pd.Timedelta(weeks=max_stale_weeks)

    active: Dict[str, pd.DataFrame] = {}
    dropped = []
    for ticker, df in data.items():
        last = last_dates.get(ticker)
        if last is not None and last >= cutoff:
            active[ticker] = df
        else:
            dropped.append((ticker, last))

    if dropped:
        print(f"[DataLoader] Avnoterade/inaktiva (ingen kurs sedan >{max_stale_weeks}v "
              f"före {ref.date()}): {len(dropped)} st")
        for ticker, last in sorted(dropped, key=lambda x: str(x[1])):
            stamp = last.date() if last is not None else "—"
            print(f"  [DELISTED] {ticker}: senaste kurs {stamp}")

    print(f"[DataLoader] Aktiva kvar efter delisting-filter: "
          f"{len(active)}/{len(data)} tickers.")
    _diag.record_universe_stage("delisting_filter", list(active.keys()))
    return active


def build_universe_df(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Sätter ihop alla tickers till ett long-format DataFrame.
    Kolumner: ticker, Open, High, Low, Close, Volume  (index = Date)
    """
    frames = []
    for ticker, df in data.items():
        tmp = df.copy()
        tmp["ticker"] = ticker
        frames.append(tmp)
    universe = pd.concat(frames).sort_index()
    universe.index.name = "Date"
    return universe
