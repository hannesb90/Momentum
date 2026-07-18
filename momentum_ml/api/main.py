"""
api/main.py – Lättviktig FastAPI-server som exponerar pipeline-resultaten
(results/*.csv + stats.json) som JSON för frontend-dashboarden.

Servern läser bara redan genererade filer från `python main.py` – den
kör inga modeller eller backtester själv. Kör pipelinen om
`results/`-filerna saknas eller är gamla.

Användning:
  uvicorn api.main:app --reload --port 8001
"""

import json
import math
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

app = FastAPI(title="Momentum ML API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """Skyddsnät: en oväntad läs-/parsefel (t.ex. en CSV mitt i en omskrivning från
    tränings-/sync-jobbet) ska ge ett vänligt 503 som frontend kan försöka om, inte
    en ogenomskinlig 500 som ser ut som att API:t är nere."""
    return JSONResponse(
        status_code=503,
        content={"detail": f"Resultat uppdateras just nu ({type(exc).__name__}). Försök igen strax."},
    )


def _clean(obj):
    """Ersätter NaN/±Inf med None rekursivt. FastAPI:s JSON-kodare kastar annars
    'ValueError: Out of range float values are not JSON compliant: nan' – vilket är
    den egentliga orsaken till de återkommande 500/503 (results/*.csv innehåller NaN,
    t.ex. limit_price på icke-köp-rader eller tomma feature-kolumner)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def _records(df: pd.DataFrame) -> list:
    """DataFrame → JSON-säkra records (NaN/Inf → null)."""
    return _clean(df.to_dict(orient="records"))


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    """Läser en CSV robust. Tränings-/sync-jobbet kan skriva om filen samtidigt →
    en läsning kan då träffa en halvskriven fil. Försök några gånger med kort paus
    (skrivningen är klar på millisekunder) innan vi ger upp."""
    last = None
    for i in range(4):
        try:
            return pd.read_csv(path, **kwargs)
        except Exception as e:  # noqa: BLE001 – pandas kastar olika fel på trasig fil
            last = e
            time.sleep(0.2 * (i + 1))
    raise HTTPException(status_code=503,
                        detail=f"Kunde inte läsa {path.name} (uppdateras?). Försök igen strax.") from last


RESULTS_DIR = Path(config.RESULTS_DIR)


def _seg_dir(segment: Optional[str]) -> Path:
    """Resultatkatalog för ett segment (storbolag/småbolag). Okänt/None faller
    tillbaka på default-segmentet, så befintliga anrop utan ?segment fungerar."""
    cfg = config.SEGMENTS.get(segment) if segment else None
    if cfg is None:
        cfg = config.SEGMENTS[config.DEFAULT_SEGMENT]
    return Path(cfg["results_dir"])


def _require(path: Path) -> Path:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{path.name} saknas – kör 'python main.py' först för att generera resultat.",
        )
    return path


@app.get("/api/segments")
def get_segments():
    """Tillgängliga segment för frontend-toggeln."""
    return {
        "default": config.DEFAULT_SEGMENT,
        "segments": [{"id": k, "label": v["label"]} for k, v in config.SEGMENTS.items()],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def get_stats(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "stats.json")
    with open(path) as f:
        data = json.load(f)
    # Rekommenderad exponering räknas om LIVE ur nuvarande config.MARKET_FILTER_EXPOSURE
    # (regimen är fastställd i stats.json men faktorn ska följa config utan att hela
    # pipelinen körs om). Så ändrad exponerings-config slår igenom direkt i appen.
    mkt = data.get("market")
    if isinstance(mkt, dict) and mkt.get("state"):
        mkt["exposure"] = float(config.MARKET_FILTER_EXPOSURE.get(mkt["state"], 1.0))
    return _clean(data)


# signals.csv är stor (alla tickers × alla veckor, ~100 MB på storsegmentet)
# och lästes tidigare I SIN HELHET vid VARJE anrop – samma flaskhals som
# portfolio._latest_signals fick svansläsning+mtime-cache för (Buffett-
# hängningen), men i API-lagret. /latest behöver bara SENASTE raden per
# ticker → läs bara filens sista _SIGNALS_TAIL_BYTES (kronologisk fil, ~1 år)
# och cacha resultatet på mtime. En ticker utan handel på ~1 år faller bort –
# korrekt (ingen aktuell signal). /history cachar färdiga svar per
# (fil, ticker, limit, mtime) så en återbesökt aktievy inte skannar om filen.
_SIGNALS_TAIL_BYTES = 8 * 1024 * 1024
_LATEST_CACHE: dict = {}
_HISTORY_CACHE: dict = {}


def _signals_tail_df(path: Path) -> pd.DataFrame:
    import io
    with open(path, "rb") as f:
        header = f.readline()
        if path.stat().st_size > _SIGNALS_TAIL_BYTES + len(header):
            f.seek(-_SIGNALS_TAIL_BYTES, 2)
            f.readline()   # kasta trolig halv rad
        chunk = f.read()
    return pd.read_csv(io.BytesIO(header + chunk), index_col=0, parse_dates=True)


@app.get("/api/signals/latest")
def get_latest_signals(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "signals.csv")
    mt = path.stat().st_mtime
    hit = _LATEST_CACHE.get(str(path))
    if hit is not None and hit[0] == mt:
        return hit[1]
    df = _signals_tail_df(path)
    latest = df.groupby("ticker").last().reset_index()
    latest = latest.sort_values("prob_up", ascending=False)
    out = _records(latest)
    _LATEST_CACHE[str(path)] = (mt, out)
    return out


@app.get("/api/signals/history")
def get_signal_history(ticker: Optional[str] = None, limit: int = 260, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "signals.csv")
    mt = path.stat().st_mtime
    key = (str(path), ticker or "", int(limit))
    hit = _HISTORY_CACHE.get(key)
    if hit is not None and hit[0] == mt:
        return hit[1]
    df = _read_csv(path, index_col=0, parse_dates=True)
    if ticker:
        df = df[df["ticker"] == ticker]
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Ingen data för ticker '{ticker}'.")
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    out = _records(df)
    if len(_HISTORY_CACHE) > 32:
        _HISTORY_CACHE.clear()
    _HISTORY_CACHE[key] = (mt, out)
    return out


@app.get("/api/portfolio")
def get_portfolio(limit: int = 1000, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "portfolio.csv")
    df = _read_csv(path, index_col=0, parse_dates=True)
    pv = df["portfolio_value"]
    df["drawdown"] = pv / pv.cummax() - 1
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return _records(df)


@app.get("/api/drift")
def get_drift(limit: int = 260, segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "drift_report.csv")
    df = _read_csv(path, index_col=0, parse_dates=True)
    df = df.sort_index().tail(limit).reset_index()
    df = df.rename(columns={df.columns[0]: "date"})
    return _records(df)


@app.get("/api/regime")
def get_regime_breakdown(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "regime_breakdown.csv")
    df = _read_csv(path, index_col=0).reset_index()
    return _records(df)


@app.get("/api/sector-momentum")
def get_sector_momentum(segment: Optional[str] = None):
    path = _require(_seg_dir(segment) / "sector_momentum.csv")
    df = _read_csv(path)
    return _records(df)


_PRICES_CACHE: dict = {}


@app.get("/api/prices")
def get_prices(ticker: str, limit: int = 260, segment: Optional[str] = None):
    """Per-ticker prishistorik (close) för aktiedetaljvyns kursgraf.
    Hela prices.csv (alla tickers × ~260v, ~340k rader) parsades tidigare om
    för VARJE aktievy-öppning (~3s på Pi:n) – nu cachas den parsade filen på
    mtime (liten: bara date/ticker/close) och filtreringen är vektoriserad."""
    path = _seg_dir(segment) / "prices.csv"
    if not path.exists():
        return []
    mt = path.stat().st_mtime
    hit = _PRICES_CACHE.get(str(path))
    if hit is not None and hit[0] == mt:
        df = hit[1]
    else:
        df = _read_csv(path)
        _PRICES_CACHE[str(path)] = (mt, df)
    df = df[df["ticker"] == ticker].sort_values("date").tail(limit)
    return _records(df[["date", "close"]])


@app.get("/api/quality")
def get_quality():
    """Fundamental microcap-kortlista (kvalitativ sållning + värdering). Global,
    inte segment-uppdelad. Tom lista om screenern ännu inte körts (i st. f. 404).

    TOKENFRI FALLBACK: LLM-screenern (quality_screener.py) täcker bara de bolag
    den faktiskt körts på – Kvalitet-fliken visade därför '–' för nästan hela
    universumet tills nattbatchen hunnit dit. soft_signals.py:s destillat
    (LightGBM/lexikon på samma PM-text, kalibrerat mot LLM-betygen på samma
    0–5-skala) fyller luckorna token-fritt – SAMMA precedens som portfolio.py:s
    kvalitets-fallback: LLM vinner ALLTID när den finns, och källan märks
    (quality_source 'llm'/'soft') så betygen aldrig kan förväxlas."""
    rows: list = []
    llm_tickers: set = set()
    path = RESULTS_DIR / "quality_shortlist.csv"
    if path.exists():
        rows = _records(_read_csv(path))
        for r in rows:
            r["quality_source"] = "llm"
        llm_tickers = {str(r.get("ticker") or "").upper() for r in rows}

    for seg in config.SEGMENTS.values():
        sp = Path(config.anchor(seg.get("results_dir", ""))) / "soft_signals.csv"
        if not sp.exists():
            continue
        try:
            soft = _read_csv(sp)
        except HTTPException:
            continue
        for r in _records(soft):
            tk = str(r.get("ticker") or "").upper()
            if not tk or tk in llm_tickers:
                continue
            llm_tickers.add(tk)   # dedupe även mellan segmentfilerna
            rows.append({
                "ticker": tk, "name": r.get("name"),
                "composite": r.get("soft_score"),
                "red_flags": r.get("red_flags") or "",
                "quality_source": "soft",
            })
    return rows


@app.get("/api/quant")
def get_quant():
    """Token-fri kvantitativ kortlista (hård data: kvalitet/tillväxt/trygghet/värde).
    Tom lista om quant_screener ännu inte körts. Anchor-medveten (MOMENTUM_HOME)."""
    path = Path(config.anchor(config.RESULTS_DIR)) / "quant_shortlist.csv"
    if not path.exists():
        return []
    return _records(_read_csv(path))


@app.get("/api/rotation")
def get_rotation():
    """ETF/sektor-rotation (D-spåret): regim + rankade ETF:er m. flöde. Global.
    Tom struktur om signalen ännu inte körts (etf_rotation.py signal)."""
    path = RESULTS_DIR / "etf_rotation.csv"
    meta_path = RESULTS_DIR / "etf_rotation_meta.json"
    if not path.exists():
        return {"meta": None, "rows": []}
    rows = _records(_read_csv(path))
    meta = None
    if meta_path.exists():
        with open(meta_path) as f:
            meta = _clean(json.load(f))
    return {"meta": meta, "rows": rows}


@app.get("/api/thesis")
def get_thesis():
    """Kausala 'nästa-trend'-idéer (D-spårets hypotes-lager). Global. Idéer, ej signaler."""
    path = RESULTS_DIR / "etf_thesis.csv"
    if not path.exists():
        return []
    return _records(_read_csv(path))


@app.get("/api/holdings")
def get_portfolio_holdings(amount: Optional[float] = None):
    """Manuellt inmatad portfölj + hink-analys + (om amount) nytt-kapital-plan.
    Egen väg (/api/holdings) – krockar annars med backtest-endpointen /api/portfolio."""
    import portfolio as pf
    return _clean(pf.compute(pf.load_holdings(), amount=amount))


@app.get("/api/next-buy")
def get_next_buy(amount: Optional[float] = None):
    """Coret: ETT rangordnat svar på 'var ska nästa krona in?' (hemvyns huvudkort).
    Kärna-först-hierarkin och gate-logiken ligger i portfolio.next_buy."""
    import portfolio as pf
    return _clean(pf.next_buy(pf.load_holdings(), amount=amount))


@app.get("/api/universe")
def get_universe():
    """Alla sökbara värdepapper appen känner (sök/filtrera vid innehav)."""
    import portfolio as pf
    return _clean(pf.universe())


@app.get("/api/portfolio-target")
def get_portfolio_target():
    """Användarens målfördelning (broad/sweden/theme, normaliserad)."""
    import portfolio as pf
    return _clean({"target": pf.load_target(), "default": config.PORTFOLIO_TARGET})


@app.post("/api/portfolio-target")
async def set_portfolio_target(request: Request):
    """Sparar användarens målfördelning. Body: {broad, sweden, theme} (normaliseras)."""
    import portfolio as pf
    body = await request.json()
    return _clean({"target": pf.save_target(body)})


@app.get("/api/portfolio-model")
def get_portfolio_model():
    """Vald rank-modell för 'nästa köp' (balanced/buffett/momentum) + valbara.
    Ren vy-inställning: ALL underliggande data laddas alltid, så växling kräver
    ingen omkörning."""
    import portfolio as pf
    return _clean({"model": pf.active_model(), "available": list(pf._MODEL_WEIGHTS.keys())})


@app.post("/api/portfolio-model")
def set_portfolio_model(body: dict):
    """Sätter vald rank-modell. Body: {model: 'balanced'|'buffett'|'momentum'}.
    Okänt namn ignoreras (behåller nuvarande)."""
    import portfolio as pf
    return _clean({"model": pf.set_active_model(str(body.get("model", "")))})


@app.get("/api/scanner/fields")
def get_scanner_fields():
    """Fältlista + hjälptext för scenario-skannerns formulär (frontend bygger
    formuläret ur denna, så en ny fält-typ i manual_scan.py syns automatiskt
    utan en frontend-ändring)."""
    from altdata import manual_scan as ms
    return _clean({
        "fields": [{"key": k, "help": v, "type": (
                        "bool" if k in ms._BOOL_FIELDS else
                        "number" if k in ms._FLOAT_FIELDS else "text")}
                   for k, v in ms._FIELD_HELP.items()],
    })


@app.post("/api/scanner/scan")
async def post_scanner_scan(request: Request):
    """Manuell scenario-skanning: {ticker, overrides: {fält: värde, ...}, segment?}.
    Görs ALDRIG mot nätet och sparas ALDRIG – ett engångs 'vad om'-svar (se
    altdata/manual_scan.py:s docstring). Ogiltig indata (t.ex. tom ticker) ger
    400, inte en opak 500."""
    from altdata import manual_scan as ms
    body = await request.json()
    ticker = str(body.get("ticker") or "").strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker saknas.")
    overrides = body.get("overrides") or {}
    segment = body.get("segment")
    try:
        result = ms.scan(ticker, overrides, segment=segment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _clean(result)


@app.post("/api/holdings")
async def save_portfolio_holdings(request: Request):
    """Sparar hela innehavslistan (skriver cache/portfolio_holdings.csv) och
    returnerar omräknad analys. Body: {holdings:[{name,value,bucket}], amount?}."""
    import portfolio as pf
    body = await request.json()
    holdings = body.get("holdings", [])
    rows = []
    def _f(x):
        try:
            return float(x) if x not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            return None
    for h in holdings:
        v = _f(h.get("value") if h.get("value") is not None else h.get("value_sek")) or 0.0
        name = str(h.get("name", "")).strip()
        shares = _f(h.get("shares"))
        # antal+ticker räcker (värdet räknas ur senaste kurs); annars krävs värde
        if not name or (v <= 0 and not shares):
            continue
        b = str(h.get("bucket", "theme"))
        rows.append({"name": name, "value": v, "bucket": b if b in pf.BUCKETS else "theme",
                     "ticker": str(h.get("ticker", "")).strip().upper(),
                     "cost": _f(h.get("cost")), "shares": shares,
                     "buy_price": _f(h.get("buy_price"))})
    pf.save_holdings(rows)
    # Läs tillbaka med refresh så svaret innehåller auto-beräknade värden.
    return _clean(pf.compute(pf.load_holdings(), amount=body.get("amount")))


@app.get("/api/portfolio-log")
def get_portfolio_log():
    """Framåt-logg av din portföljs totala värde (byggs upp från och med nu, en
    punkt per dag). Tom lista tills du sparat innehav minst en gång."""
    import portfolio as pf
    return _clean(pf.load_value_log())


@app.get("/api/exit-signals")
def get_exit_signals():
    """Exit-alarm ('end this now'): senaste skanningen (sektor+teknik) per innehav.
    Tom struktur om skanningen ännu inte körts (portfolio.py exitscan på Pi:n)."""
    path = Path(config.anchor(config.RESULTS_DIR)) / "exit_signals.json"
    if not path.exists():
        return {"generated": None, "holdings": []}
    with open(path, encoding="utf-8") as f:
        return _clean(json.load(f))


@app.get("/api/case-changes")
def get_case_changes():
    """Har investeringscaset förändrats? (altdata/case_tracker.py). Jämför
    senaste 90d PM-signaler mot föregående 90d per bolag. Tom lista om
    trackern ännu inte körts."""
    path = Path(config.anchor(config.RESULTS_DIR)) / "case_changes.csv"
    if not path.exists():
        return []
    return _records(_read_csv(path))


@app.get("/api/portfolio-backtest")
def get_portfolio_backtest():
    """'Nästa köp' (fyll-mot-mål) mot index – DCA-simulering på din bok
    (portfolio.py backtest). Läser bara redan genererad JSON (samma princip
    som resten av API:t – kör aldrig backtester live, prispanelen kräver nät
    och ska aldrig blockera en request). null om den inte körts än."""
    path = Path(config.anchor(config.RESULTS_DIR)) / "portfolio_backtest.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return _clean(json.load(f))


@app.get("/api/paper-ledger")
def get_paper_ledger(limit: int = 520, segment: Optional[str] = None):
    """
    Framåtblickande pappershandels-historik (live track record). Returnerar
    en tom lista om liggaren ännu inte börjat byggas (första körningarna) i
    stället för 404 – frontend visar då ett 'ingen historik än'-tillstånd.
    """
    path = _seg_dir(segment) / "paper_ledger.csv"
    if not path.exists():
        return []
    return _records(_read_csv(path).tail(limit))
