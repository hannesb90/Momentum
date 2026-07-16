"""
portfolio.py – Portfölj-medveten analys + nytt-kapital-plan.

Läser dina innehav (cache/portfolio_holdings.csv – GITIGNORERAD, personlig data),
klassar per hink (broad/sweden/theme/leverage), jämför mot en diversifierad
mål-fördelning (config.PORTFOLIO_TARGET) och riktar NYTT kapital mot det du är
underviktad i. Fyll-mot-mål via inflöden – ingen försäljning, ingen skatt, ingen
timing. Innehav läggs in manuellt (CLI eller i appen, som skriver samma fil).

    python portfolio.py analyze
    python portfolio.py newcapital 10000
    python portfolio.py backtest 5000 36    # "nästa köp" mot index: 5000 kr/mån, 36 mån
    python portfolio.py exitscan            # "end this now": sektor+teknik → exit_signals.json
    python portfolio.py sizein 10000 4      # dela ett köp i 4 trancher (lika + dip-viktat)

    # Modellval (balanced/buffett/momentum) vs index – backtest() ovan testar bara
    # HINK-fördelningen, inte vilka aktier modellen faktiskt väljer. Riktig
    # bakåtblick omöjlig (bara dagens kvalitets-/kvant-/värde-data finns) – därför
    # framåt-spårning (ärligt) + illustrativ bakåtblick (snabbt men ogiltigt):
    python portfolio.py snapshot_model              # frys DAGENS plockningar (aktiv modell) + kurs
    python portfolio.py track_model                 # avkastning per modell-snapshot vs index hittills
    python portfolio.py lookback_model 6             # ⚠ ILLUSTRATIV bakåtblick, 6 månader, alla 3 modeller
"""
import sys
import csv
import json
import re
import bisect
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import config

BUCKETS = ("broad", "sweden", "theme", "leverage")
BUCKET_LABEL = {"broad": "Bred kärna (World/US/EM)", "sweden": "Sverige",
                "theme": "Tematiskt", "leverage": "Hävstång"}


def holdings_path() -> Path:
    return Path(config.anchor(config.PORTFOLIO_HOLDINGS_FILE))


def _results_dir() -> Path:
    """results/ förankrad under $MOMENTUM_HOME (om satt) → app och CLI delar filer."""
    return Path(config.anchor(config.RESULTS_DIR))


def value_log_path() -> Path:
    return Path(config.anchor(config.PORTFOLIO_VALUE_LOG))


def cash_path() -> Path:
    return Path(config.anchor("cache/montrose_cash.json"))


def save_cash(available_sek, total_sek=None) -> None:
    """Sparar ISK-kontots tillgängliga köpkraft från senaste Montrose-synken
    (skrivs av sync_montrose_holdings.py --from-montrose). Läses av Nästa
    köp så en föreslagen biljett kan varnas mot faktisk kassa – t.ex. en
    månadsinsättning som ännu inte landat."""
    from datetime import datetime, timezone
    p = cash_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "available_sek": round(float(available_sek or 0)),
        "total_sek": (round(float(total_sek)) if total_sek else None),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False), encoding="utf-8")


def load_cash() -> Optional[dict]:
    p = cash_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 – trasig/halvskriven fil → ingen kassa-varning, inte en krasch
        return None


def log_value(total) -> None:
    """Upsert:ar dagens totala portföljvärde i framåt-loggen (en punkt per dag).
    Bygger en äkta personlig utvecklingskurva från och med nu."""
    from datetime import date
    if not total or float(total) <= 0:
        return
    p = value_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("date"):
                rows[r["date"]] = r.get("value_sek", "")
    rows[date.today().isoformat()] = str(round(float(total)))   # dagens = senaste spar
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value_sek"])
        for d in sorted(rows):
            w.writerow([d, rows[d]])


def load_value_log() -> list:
    p = value_log_path()
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        try:
            out.append({"date": r["date"], "value": float(r["value_sek"])})
        except (ValueError, KeyError):
            continue
    return out


def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _signed_num(v):
    """Som _num men BEHÅLLER negativa/noll-värden – för storheter där ett
    negativt tal är meningsfullt (ROE, tillväxt), till skillnad från kurser/
    värden där _num:s 'kasta ≤0' är rätt."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _score_num(v):
    """För POÄNG/BETYG (kvalitet 0–5, kvant, value_score, soft, prob_up):
    0 är ett giltigt, meningsfullt värde – SÄMSTA betyget, inte 'saknas'.
    _num kastar ≤0 (rätt för kurser/belopp) och gjorde att ett bolag med
    betyg exakt 0 räknades som obetygsatt → neutral 0,5-fallback i
    sammanvägningen, dvs. sämsta bolaget fick medelbetyg. Negativt är
    däremot aldrig en giltig poäng → None."""
    try:
        f = float(v)
        return f if f >= 0 else None
    except (TypeError, ValueError):
        return None


_CLOSES_CACHE: dict = {}


def _latest_close_map(path, col) -> dict:
    """{TICKER: sista giltiga <col>-värde per ticker} ur en prices-CSV, via
    pandas groupby (C-fart) i stället för en Python-csv-radloop.

    prices.csv har ALLA tickers × ALLA dagar (stor fil); den gamla radloopen
    med csv.DictReader tog ~2,9s på Pi:n (338 000 rader). Läser BARA ticker +
    den efterfrågade kolumnen (usecols) och tar sista GILTIGA raden per ticker
    med dropna + groupby().tail(1) – exakt samma semantik som radloopens
    'sista raden med giltig kurs vinner', oberoende av filordning (så ingen
    kronologi-antagande behövs här, till skillnad från signals-svansen).
    Memoiserad per (fil, mtime)."""
    try:
        mt = Path(path).stat().st_mtime
    except OSError:
        return {}
    key = f"{path}::{col}"
    hit = _CLOSES_CACHE.get(key)
    if hit is not None and hit[0] == mt:
        return hit[1]
    import pandas as pd
    out: dict = {}
    try:
        header = pd.read_csv(path, nrows=0)
        if "ticker" in header.columns and col in header.columns:
            df = pd.read_csv(path, usecols=["ticker", col]).dropna(subset=[col])
            if not df.empty:
                last = df.groupby("ticker", sort=False).tail(1)
                for _, row in last.iterrows():
                    tk = str(row.get("ticker") or "").upper()
                    v = _num(row.get(col))
                    if tk and v:
                        out[tk] = v
    except Exception:  # noqa: BLE001
        out = {}
    _CLOSES_CACHE[key] = (mt, out)
    return out


def _latest_closes(include_quotes: bool = True) -> dict:
    """{ticker: senaste stängningskurs i SEK}. Källor i ordning:
      1. Segmentens prices.csv (modellens universum, skrivs nattligt).
      2. holdings_quotes.csv – kompletterande Yahoo-hämtning för innehav
         UTANFÖR universum (utländska ETF:er, micro caps), redan i SEK.
    """
    out = {}
    for seg in config.SEGMENTS.values():
        pp = Path(seg.get("results_dir", "")) / "prices.csv"
        if pp.exists():
            out.update(_latest_close_map(pp, "close"))   # sista giltiga per ticker
    if include_quotes:
        qp = _results_dir() / "holdings_quotes.csv"
        if qp.exists():
            try:
                for r in csv.DictReader(open(qp, encoding="utf-8")):
                    tk = (r.get("ticker") or "").upper()
                    v = _num(r.get("close_sek"))
                    if tk and v:
                        out.setdefault(tk, v)   # prices.csv vinner om båda finns
            except Exception:  # noqa: BLE001
                pass
    return out


def fetch_holding_quotes(tickers: Optional[list] = None) -> dict:
    """
    Hämtar senaste kurs (omräknad till SEK) för innehav vars ticker INTE täcks
    av modellens prices.csv: utländska ETF:er (EUR/USD/GBp) och svenska bolag
    utanför segmentens universum (micro caps). Direkt från samma kurskälla som
    resten av pipelinen (Yahoo) – kräver nät. Körs dels nattligt via main.py
    STEG 5 (tickers=None → läser load_holdings() från disk), dels direkt från
    save_holdings() med en explicit ticker-lista – det senare täcker fallet
    "nyss tillagt innehav" vars ticker ÄNNU inte finns på disk (raden har inte
    skrivits än) och som annars inte fått något pris förrän nästa nattkörning.
    Skriver results/holdings_quotes.csv som _latest_closes() plockar upp.
    Valutor: fast_info.currency; GBp (pence) → /100 → GBP; växlas via <CUR>SEK=X.
    """
    if tickers is None:
        rows = load_holdings(refresh=False)
        tickers = [(r.get("ticker") or "").upper() for r in rows]
    have = _latest_closes(include_quotes=False)
    need = sorted({(t or "").upper() for t in tickers} - set(have) - {""})
    if not need:
        return {}
    import yfinance as yf

    fx_cache = {"SEK": 1.0}

    def fx(cur):
        cur = (cur or "SEK").upper()
        if cur not in fx_cache:
            try:
                h = yf.Ticker(f"{cur}SEK=X").history(period="5d")["Close"].dropna()
                fx_cache[cur] = float(h.iloc[-1]) if len(h) else None
            except Exception:  # noqa: BLE001
                fx_cache[cur] = None
        return fx_cache[cur]

    out = {}
    for tk in need:
        try:
            t = yf.Ticker(tk)
            h = t.history(period="7d")["Close"].dropna()
            if not len(h):
                continue
            px = float(h.iloc[-1])
            try:
                fi = t.fast_info
                cur = fi.get("currency") if hasattr(fi, "get") else getattr(fi, "currency", None)
            except Exception:  # noqa: BLE001
                cur = None
            # BUGG (fixad): föll tidigare tyst tillbaka till "SEK" när
            # valutan inte gick att slå upp – för en icke-svensk ticker
            # (exakt fallet detta ska hantera) ger det ett TYST FEL värde,
            # inte bara ett saknat: en $150-aktie visades som 150 kr i
            # stället för ~1500 kr, en 10x undervärdering utan varning.
            # Bättre att hoppa över tickern helt (behåller manuellt/
            # inköpsvärde) än att spara ett säkert felaktigt pris.
            if not cur:
                print(f"[quotes] {tk}: kunde inte slå upp valuta, hoppar (ingen SEK-gissning)")
                continue
            if cur == "GBp":                      # London-notering i pence
                px, cur = px / 100.0, "GBP"
            rate = fx(cur)
            if not rate:
                print(f"[quotes] {tk}: kunde inte hämta växelkurs för {cur}, hoppar")
                continue
            out[tk] = round(px * rate, 4)
        except Exception as e:  # noqa: BLE001
            print(f"[quotes] {tk}: {e}")
    if out:
        qp = _results_dir() / "holdings_quotes.csv"
        qp.parent.mkdir(parents=True, exist_ok=True)
        with open(qp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ticker", "close_sek"])
            for tk, v in sorted(out.items()):
                w.writerow([tk, v])
        print(f"[quotes] {len(out)}/{len(need)} kompletterande kurser sparade (SEK): "
              f"{', '.join(sorted(out))}")
    return out


def _refresh_values(rows: list) -> list:
    """Innehav med ANTAL + ticker får värdet omräknat mot senaste stängningskurs
    (uppdateras därmed automatiskt av varje nattlig körning). Insatt härleds ur
    antal × inköpskurs när det saknas. Innehav utan antal/ticker (utländska
    ETF:er, klumpsummor) behåller sitt manuella värde."""
    closes = _latest_closes()
    for r in rows:
        sh, bp = r.get("shares"), r.get("buy_price")
        px = closes.get((r.get("ticker") or "").upper())
        if sh and px:
            r["value"] = sh * px
            r["auto"] = True               # frontend: "uppdateras nattligt"
        elif sh and bp and not r.get("value"):
            # Kurs saknas i prices.csv (t.ex. före nästa nattkörning) → visa
            # åtminstone inköpsvärdet i stället för 0 kr. Blir auto när kursen finns.
            r["value"] = sh * bp
        if sh and bp and not r.get("cost"):
            r["cost"] = sh * bp
    return rows


def load_holdings(refresh: bool = True) -> list:
    p = holdings_path()
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"name": r["name"].strip(), "value": float(r["value_sek"]),
                             "bucket": (r.get("bucket") or "theme").strip(),
                             "ticker": (r.get("ticker") or "").strip().upper(),
                             "cost": _num(r.get("cost_sek")),
                             "shares": _num(r.get("shares")),
                             "buy_price": _num(r.get("buy_price"))})
            except (ValueError, KeyError):
                continue
    return _refresh_values(rows) if refresh else rows


def target_path() -> Path:
    return Path(config.anchor(getattr(config, "PORTFOLIO_TARGET_FILE", "cache/portfolio_target.json")))


def load_target() -> dict:
    """Användarens egen målfördelning om sparad, annars config-defaulten.
    Alltid normaliserad (broad+sweden+theme=1, leverage=0)."""
    base = dict(config.PORTFOLIO_TARGET)
    p = target_path()
    if p.exists():
        try:
            saved = json.loads(p.read_text(encoding="utf-8"))
            for b in ("broad", "sweden", "theme"):
                if b in saved:
                    base[b] = saved[b]
        except Exception:  # noqa: BLE001 – trasig fil → default
            pass
    return _normalize_target(base)


def _normalize_target(d: dict) -> dict:
    """Behåll broad/sweden/theme, klamp [0,1], normalisera till summa 1. leverage=0
    (evidens: hävstång ger decay/ruinrisk – aldrig ett nytt-kapital-mål)."""
    vals = {}
    for b in ("broad", "sweden", "theme"):
        try:
            vals[b] = max(0.0, min(1.0, float(d.get(b, 0.0))))
        except (TypeError, ValueError):
            vals[b] = 0.0
    s = sum(vals.values())
    if s <= 0:
        vals = {"broad": 0.60, "sweden": 0.15, "theme": 0.20}
        s = 1.0
    out = {b: round(v / s, 4) for b, v in vals.items()}
    out["leverage"] = 0.0
    return out


def save_target(d: dict) -> dict:
    """Persistera användarens målfördelning (normaliserad). Returnerar det sparade."""
    norm = _normalize_target(d)
    p = target_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(norm, ensure_ascii=False), encoding="utf-8")
    return norm


def save_holdings(rows) -> None:
    p = holdings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Hämta färsk kurs direkt för ev. NYA/okända tickers i denna sparning –
    # annars syns inget marknadspris förrän nästa nattkörning (kan vara
    # timmar bort). Bygger ticker-listan från de INKOMMANDE raderna, inte
    # load_holdings() (disk-versionen känner ännu inte till en nyss
    # tillagd rad). fetch_holding_quotes() filtrerar själv bort tickers som
    # redan är kända (prices.csv/holdings_quotes.csv) – kostar bara ett
    # nätanrop för det som faktiskt är nytt, inte varje sparning.
    incoming_tickers = [
        (r.get("ticker") or "").strip().upper() or _resolve_ticker(r.get("name", ""))
        for r in rows
    ]
    try:
        fetch_holding_quotes(incoming_tickers)
    except Exception as e:  # noqa: BLE001 – nätfel ska aldrig blocka en sparning
        print(f"[save_holdings] direkt kurshämtning misslyckades (icke-kritiskt): {e}")
    closes = _latest_closes()
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "value_sek", "bucket", "ticker",
                                          "cost_sek", "shares", "buy_price"])
        w.writeheader()
        for r in rows:
            b = r.get("bucket", "theme")
            name = r.get("name", "")
            tk = (r.get("ticker") or "").strip().upper() or _resolve_ticker(name)  # auto-fyll ticker
            sh = _num(r.get("shares"))
            bp = _num(r.get("buy_price"))
            cost = _num(r.get("cost") if r.get("cost") is not None else r.get("cost_sek"))
            if not cost and sh and bp:
                cost = sh * bp                          # insatt = antal × inköpskurs
            val = float(r.get("value", r.get("value_sek", 0)) or 0)
            if sh and closes.get(tk):
                val = sh * closes[tk]                   # värde = antal × senaste kurs
            elif sh and bp and not val:
                val = sh * bp                           # kurs saknas → inköpsvärde, aldrig 0
            w.writerow({"name": name,
                        "value_sek": val,
                        "bucket": b if b in BUCKETS else "theme",
                        "ticker": tk,
                        "cost_sek": (round(cost) if cost else ""),
                        "shares": (sh if sh else ""),
                        "buy_price": (bp if bp else "")})
    total = sum(r2["value"] for r2 in load_holdings())
    log_value(total)                                   # framåt-logg: dagens totalvärde


# ── Namn → ticker/sektor (svenska universumet) ────────────────────────────────
_UNIVERSE = None


def _universe():
    global _UNIVERSE
    if _UNIVERSE is None:
        _UNIVERSE = []
        p = Path(__file__).parent / "data" / "sweden_universe.csv"
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                _UNIVERSE.append((r["ticker"].strip().upper(), r["name"].strip(),
                                  (r.get("sector") or "").strip()))
    return _UNIVERSE


# Utländska ETF-issuers finns INTE i svenska universumet → försök aldrig matcha dem
# mot universumet (annars falska träffar, t.ex. 'Global X ...' → 'Enad Global 7 AB').
_ETF_ISSUERS = ("vaneck", "van eck", "wisdomtree", "wisdom tree", "global x", "globalx",
                "hanetf", "han etf", "xact", "ishares", "xtrackers", "amundi", "spdr",
                "invesco", "lyxor", "first trust", "ark ", "ucits")

# Kurerad namn→ticker-karta (delsträng i gemener → ticker med börs-suffix). Täcker
# ETF:er + svenska bolag som saknas i universumet. Suffix styr priskällan (.ST Sthlm,
# .DE Xetra, .L London); fel suffix → "ingen prisdata" (felsäkert), byt då i appen.
_CURATED = {
    "vaneck semiconductor": "VVSM.DE",
    "global x blockchain": "BLCH.L",
    "global x data center": "V9N.DE",
    "wisdomtree uranium": "WNUC.L",
    "wisdomtree physical ai": "PAIW.L",
    "ishares msci acwi": "IUSQ.DE",
    "vaneck space": "JEDI.L",
    "future of defence": "ASWC.L",
    "xact bull 2": "XACTBULL2.ST",
    "acconeer": "ACCON.ST",
    "plejd": "PLEJD.ST",
    "physitrack": "PTRK.ST",
}


def _resolve_ticker(name) -> str:
    """Namn → ticker: (1) kurerad karta, (2) hoppa utländska ETF-issuers, (3) säker
    delsträngs-träff i svenska universumet. Lös ord-matchning är borttagen – den gav
    falska träffar (Global X → EG7)."""
    nl = (name or "").lower().strip()
    if not nl:
        return ""
    for key, tk in _CURATED.items():
        if key in nl:
            return tk
    if any(k in nl for k in _ETF_ISSUERS):
        return ""
    for tk, nm, _ in _universe():
        if nl in nm.lower():
            return tk
    return ""


_SECTOR_MAP = None


def _sector_of(ticker) -> str:
    # Tidigare en LINJÄR scan av HELA universumet per anrop – och _unified_rank
    # anropar detta en gång per bolag i sin loop (×2 rankningsomgångar per
    # next_buy), vilket blev O(n²) i universumstorlek. Osynligt förr men en
    # verklig bidragande orsak till 30s-hängningen sedan value_shortlist.csv
    # gjorde poängkartan universumsstor. Bygg en dict EN gång (universumet är
    # redan cachat i _universe()) → O(1)-uppslag.
    global _SECTOR_MAP
    if _SECTOR_MAP is None:
        _SECTOR_MAP = {t: sec for t, _, sec in _universe()}
    return _SECTOR_MAP.get((ticker or "").upper(), "")


def _kinds():
    out = {}
    uf = Path(getattr(config, "ETF_ROT_UNIVERSE_FILE", ""))
    if uf and uf.exists():
        with open(uf, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["ticker"]] = r.get("kind", "")
    return out


_RESEARCH_FIRMS = ("analyst group", "redeye", "emergers", "carlsquare", "erik penser",
                   "penser", "mangold", "kalqyl", "analysguiden", "nordic issuing")
_RIKTKURS = re.compile(r"riktkurs\D{0,25}(\d[\d\s.,]*)\s*(kr|sek)", re.I)


_RESEARCH_CACHE: dict = {}


def _research_note(ticker):
    """Token-fri skanning av MFN-cachen: senaste uppdragsanalys-PM + ev. riktkurs.
    OBS: uppdragsanalys är BETALD av bolaget → positivt biased. Visas som narrativ,
    inte signal.

    Memoiserad på filens mtime: att öppna+json-parsa+fulltextsöka en MFN-fil är
    DYRT (de riktiga filerna är stora – hela PM-historiken med fulltext), och
    profilering på Pi:n visade 14,5s spenderat här när det kördes en gång per
    bolag i universumet. Anropas numera bara LAT för topp-kandidaterna
    (_unified_rank), och den här cachen gör upprepade anrop gratis tills filen
    ändras."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return None
    hit = _RESEARCH_CACHE.get(ticker)
    if hit is not None and hit[0] == mt:
        return hit[1]
    result = _research_note_uncached(p)
    _RESEARCH_CACHE[ticker] = (mt, result)
    return result


def _research_note_uncached(p):
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return None
    for it in sorted(items, key=lambda x: x.get("published", ""), reverse=True)[:40]:
        blob = (str(it.get("title", "")) + " " + str(it.get("text", "")))
        low = blob.lower()
        if any(f in low for f in _RESEARCH_FIRMS) or "uppdragsanalys" in low:
            m = _RIKTKURS.search(blob)
            return {"date": str(it.get("published", ""))[:10],
                    "riktkurs": (m.group(1).strip() if m else None),
                    "title": str(it.get("title", ""))[:70]}
    return None


_SIGNALS_CACHE: dict = {}


def _latest_signals(path) -> dict:
    """{TICKER: {prob_up, pred_signal, name}} – senaste raden per ticker ur en
    signals.csv. Memoiserad per (fil, mtime): samma fil läses annars flera
    gånger per next_buy (_load_scores för båda segmenten + _momentum_picks)."""
    try:
        mt = Path(path).stat().st_mtime
    except OSError:
        return {}
    key = str(path)
    hit = _SIGNALS_CACHE.get(key)
    if hit is not None and hit[0] == mt:
        return hit[1]
    out = _latest_signals_uncached(path)
    _SIGNALS_CACHE[key] = (mt, out)
    return out


_SIGNALS_TAIL_BYTES = 8 * 1024 * 1024   # 8 MB ≈ ~1 år av veckosignaler för hela universumet


def _latest_signals_uncached(path) -> dict:
    """Senaste raden per ticker – läser BARA slutet av filen, inte hela historiken.

    signals.csv innehåller ALLA tickers × ALLA veckor MED alla feature-kolumner
    (100+ MB på storsegmentet). Att skanna hela filen bara för sista raden per
    ticker var flaskhalsen (~12s i den gamla csv-radloopen; även pandas med
    usecols måste läsa varje byte). Men filen är KRONOLOGISK → de senaste
    raderna ligger sist. Vi seek:ar därför till de sista _SIGNALS_TAIL_BYTES,
    kastar en trolig halv rad, och parsar bara svansen med pandas (usecols för
    de fyra kolumner vi behöver). groupby().tail(1) ger sista raden per ticker.

    Följd: en ticker som inte handlats på ~1 år saknas – men den är per
    definition ingen aktuell köpkandidat, så det är korrekt att utelämna dess
    inaktuella signal. Liten fil (< svansen) läses i sin helhet."""
    import io
    import pandas as pd

    p = Path(path)
    try:
        with open(p, "rb") as f:
            header_line = f.readline()
            size = p.stat().st_size
            if size > _SIGNALS_TAIL_BYTES + len(header_line):
                f.seek(-_SIGNALS_TAIL_BYTES, io.SEEK_END)
                f.readline()          # kasta en sannolikt partiell första rad
            chunk = f.read()
    except OSError:
        return {}
    if not header_line:
        return {}
    cols = header_line.decode("utf-8", "replace").rstrip("\r\n").split(",")
    want = [c for c in ("ticker", "name", "prob_up", "pred_signal") if c in cols]
    if "ticker" not in want or not chunk:
        return {}
    try:
        df = pd.read_csv(io.BytesIO(header_line + chunk), usecols=want)
    except Exception:  # noqa: BLE001
        return {}
    if df.empty:
        return {}
    last = df.groupby("ticker", sort=False).tail(1)
    out = {}
    for _, row in last.iterrows():
        tk = str(row.get("ticker") or "").strip().upper()
        if tk:
            out[tk] = {"prob_up": row.get("prob_up"),
                       "pred_signal": row.get("pred_signal"),
                       "name": row.get("name")}
    return out


def _momentum_picks():
    """Momentum-köpsignaler för svenska småbolag (Signaler-vyn). Loser mot index –
    idéer, inte edge."""
    seg = config.SEGMENTS.get("small", {})
    sp = Path(seg.get("results_dir", "")) / "signals.csv"
    if not sp.exists():
        return []
    latest = _latest_signals(sp)   # pandas-snabb, delad med _load_scores
    def pu(r):
        try:
            return float(r.get("prob_up") or 0)
        except (ValueError, TypeError):
            return 0.0
    buys = [(tk, r) for tk, r in latest.items() if str(r.get("pred_signal")) in ("1", "1.0", "1")]
    buys.sort(key=lambda x: pu(x[1]), reverse=True)
    return [{"name": r.get("name") or tk, "ticker": tk,
             "note": f"momentum P(upp) {pu(r):.0%}", "source": "momentum"} for tk, r in buys[:5]]


def _candidates() -> dict:
    """Konkreta idéer från övriga vyer, per hink – bolag/teman, inte bara breda ETF:er.
    sweden = kvalitets-screenern + momentum-signaler (+ uppdragsanalys om funnen);
    theme = rotationens starkaste teman."""
    out = {"sweden": [], "theme": []}
    seen = set()

    def add_sweden(name, ticker, note, source):
        if not ticker or ticker in seen:
            return
        seen.add(ticker)
        c = {"name": name, "ticker": ticker, "note": note, "source": source}
        r = _research_note(ticker)
        if r:
            c["analys"] = r
        out["sweden"].append(c)

    # Kvalitets-screenern → svenska kvalitetsbolag (hög composite + billig/rimlig).
    qp = _results_dir() / "quality_shortlist.csv"
    if qp.exists():
        try:
            rows = list(csv.DictReader(open(qp, encoding="utf-8")))
            def comp(r):
                try:
                    return float(r.get("composite") or 0)
                except ValueError:
                    return 0.0
            picks = sorted([r for r in rows if comp(r) >= 4.0 and r.get("zone") in ("billig", "rimlig")],
                           key=comp, reverse=True)
            for r in picks[:5]:
                add_sweden(r.get("name") or r.get("ticker"), r.get("ticker"),
                           f"kvalitet {r.get('composite')} · {r.get('zone')}", "kvalitet")
        except Exception:  # noqa: BLE001
            pass
    # Momentum-signaler → svenska småbolag.
    for m in _momentum_picks():
        add_sweden(m["name"], m["ticker"], m["note"], "momentum")

    # Rotationen → starkaste tema-ETF:erna (för temadelen).
    rp = _results_dir() / "etf_rotation.csv"
    if rp.exists():
        try:
            kinds = _kinds()
            rows = list(csv.DictReader(open(rp, encoding="utf-8")))
            themes = [r for r in rows if kinds.get(r.get("etf")) == "theme"]
            def mom(r):
                try:
                    return float(r.get("rel_mom") or 0)
                except ValueError:
                    return 0.0
            for r in sorted(themes, key=mom, reverse=True)[:5]:
                out["theme"].append({"name": r.get("sector"), "ticker": r.get("etf"),
                                     "note": f"rel.mom {mom(r):+.0%}", "source": "rotation"})
        except Exception:  # noqa: BLE001
            pass
    return out


def months_to_target(rows, amount, threshold=None, max_months=360):
    """
    Antal månadsinsättningar (à `amount`) tills den breda kärnan når `threshold`
    andel av portföljen via fyll-mot-mål (nytt kapital till undervikt, inget säljs).
    threshold=None → kärnans målvikt (helt i balans). Simulerar månad för månad.
    0 = redan där, None = längre än max_months.

    OBS: att nå MÅLVIKTEN begränsas ofta inte av kärnan utan av den STÖRSTA
    övervikten – den måste spädas ut, vilket bara sker när totalen växer. En stor
    övervikt (t.ex. Sverige 56%) tar därför lång tid att späda till 15% enbart via
    inflöden. Kärnan blir största innehav långt innan hela portföljen är i balans.
    """
    tgt = load_target()
    buckets = {b: 0.0 for b in BUCKETS}
    for r in rows:
        buckets[r["bucket"] if r["bucket"] in buckets else "theme"] += r.get("value", 0.0)
    tb = float(threshold if threshold is not None else tgt.get("broad", 0.65))
    total = sum(buckets.values())
    if total > 0 and buckets["broad"] / total >= tb - 0.005:
        return 0
    amount = float(amount or 0)
    if amount <= 0:
        return None
    for m in range(1, max_months + 1):
        for b, kr in _fill_split(buckets, amount, tgt).items():
            buckets[b] = buckets.get(b, 0.0) + kr
        total = sum(buckets.values())
        if total > 0 and buckets["broad"] / total >= tb - 0.005:
            return m
    return None


_COMPUTE_CACHE: dict = {}


def compute(rows, amount=None) -> dict:
    # Cache som next_buy: datan ändras nattligt + vid innehavssparning. Innehav-
    # sidan slipper då räkna om (~3 s på Pi:n) vid varje appstart.
    _ck = (round(float(amount or 0)), _data_mtime())
    if _ck in _COMPUTE_CACHE:
        return _COMPUTE_CACHE[_ck]
    total = sum(r["value"] for r in rows) or 0.0
    buckets = {b: 0.0 for b in BUCKETS}
    for r in rows:
        buckets[r["bucket"] if r["bucket"] in buckets else "theme"] += r["value"]
    warnings = []
    if total > 0:
        if buckets["broad"] / total < 0.10:
            warnings.append("Ingen bred diversifierad kärna – allt är riktade vad.")
        if buckets["leverage"] > 0:
            warnings.append(f"Hävstång i portföljen ({buckets['leverage']/total:.0%}) – decay/ruinrisk på sikt.")
        if buckets["theme"] / total > 0.30:
            warnings.append(f"Hög tema-koncentration ({buckets['theme']/total:.0%}) – rör sig ofta ihop.")
        big = max(rows, key=lambda r: r["value"], default=None)
        if big and big["value"] / total > 0.12:
            warnings.append(f"Störst enskilt innehav: {big['name']} ({big['value']/total:.0%}).")

    tgt = load_target()

    # Steg 3 i modellen ("bevaka innehavens framsteg och utsikter"): varje
    # innehav får sin FUNDAMENTA-status ur poängkartan (value_screener +
    # quality) – inte bara pris/vinst. Frontend visar detta per innehavskort,
    # så bevakningen inte enbart vilar på TA-baserade exit-alarm.
    scores = _safe(_load_scores, {}, "poängkarta")

    def _fund_status(tk: str):
        sc = scores.get((tk or "").upper())
        if not sc or not sc.get("has_value_data"):
            return None
        issues = []
        if sc.get("meets_roe_bar") is False:
            issues.append("ROE under barren")
        if sc.get("meets_debt_bar") is False:
            issues.append("skuld över barren")
        g = sc.get("rev_growth_yoy")
        if g is not None and g < 0:
            issues.append("krympande intäkter")
        if sc.get("value_zone") == "dyr":
            issues.append("värdering dyr")
        return {"roe": sc.get("roe"), "rev_growth_yoy": g,
                "value_zone": sc.get("value_zone") or None,
                "ok": not issues, "issues": issues}

    out = {"total": round(total, 0),
           "buckets": {b: (round(buckets[b] / total, 4) if total else 0.0) for b in BUCKETS},
           "buckets_sek": {b: round(buckets[b], 0) for b in BUCKETS},
           "target": tgt,
           "warnings": warnings,
           "candidates": _candidates(),
           "housemoney": _house_money(rows),
           "holdings": [{"name": r["name"], "value": round(r["value"], 0), "bucket": r["bucket"],
                         "ticker": (tk := (r.get("ticker") or _resolve_ticker(r["name"]))),
                         "cost": (round(r["cost"]) if r.get("cost") else None),
                         "shares": r.get("shares"), "buy_price": r.get("buy_price"),
                         "auto": bool(r.get("auto")),
                         "fundamentals": _fund_status(tk)} for r in rows]}

    if amount:
        after = total + amount
        gaps = {b: max(0.0, tgt.get(b, 0.0) * after - buckets[b]) for b in BUCKETS}
        gsum = sum(gaps.values()) or 1.0
        plan = {b: round(amount * g / gsum) for b, g in gaps.items() if g > 0}
        broad_etfs = {}
        if plan.get("broad", 0) > 0:
            n = len(config.PORTFOLIO_BROAD_ETFS) or 1
            broad_etfs = {lbl: {"ticker": tk, "kr": round(plan["broad"] / n)}
                          for lbl, tk in config.PORTFOLIO_BROAD_ETFS.items()}
        out["newcapital"] = {"amount": amount, "plan": plan, "broad_etfs": broad_etfs}
        out["riskon"] = _riskon_plan(amount)          # aggressiv motpol (ingen riskberäkning)
    # Väg till balans: när blir kärnan DOMINANT (≥50%) och när är HELA portföljen
    # på mål (begränsas ofta av största övervikten, inte av kärnan).
    proj_amt = amount or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000)
    out["months_core_50"] = _safe(lambda: months_to_target(rows, proj_amt, threshold=0.50), None, "months_core_50")
    out["months_to_core"] = _safe(lambda: months_to_target(rows, proj_amt), None, "months_to_core")
    out["proj_amount"] = round(float(proj_amt))
    if len(_COMPUTE_CACHE) > 8:
        _COMPUTE_CACHE.clear()
    _COMPUTE_CACHE[_ck] = out
    return out


_SCORES_CACHE: dict = {}


def _scores_mtime() -> float:
    """Senaste mtime bland ENBART de filer _load_scores faktiskt läser
    (kvalitet/kvant/value-shortlists + signals per segment). MEDVETET utan
    modellvals-/innehavs-/målfilerna som _data_mtime tar med – poängkartan
    beror INTE på dem, så ett modellbyte eller en innehavssparning ska INTE
    tvinga en (dyr) ombyggnad av kartan. (_research_note läser MFN-cachen per
    ticker; dess sällsynta ändringar plockas upp när någon score-CSV ändras
    nattligt eller vid API-omstart – lågriskavvägning för en liten
    ranknings-bonus.)"""
    paths = [_results_dir() / "quality_shortlist.csv",
             _results_dir() / "quant_shortlist.csv",
             _results_dir() / "value_shortlist.csv"]
    for seg in config.SEGMENTS.values():
        paths.append(Path(seg.get("results_dir", "")) / "signals.csv")
        paths.append(Path(seg.get("results_dir", "")) / "mfn_events.csv")
        paths.append(Path(seg.get("results_dir", "")) / "soft_signals.csv")
    m = 0.0
    for p in paths:
        try:
            m = max(m, p.stat().st_mtime)
        except OSError:
            pass
    return m


def _load_scores() -> dict:
    """Memoiserad omslag runt _load_scores_uncached, nycklad på _scores_mtime().

    KRITISKT för prestanda: next_buy anropar _load_scores FYRA gånger
    (_unified_rank för sverige-slotten, _opportunity → _unified_rank + direkt,
    _takeprofit) och varje bygge probar _research_note() – en JSON-fil per
    ticker från MFN-cachen – för VARJE bolag i poängkartan (~2600 sedan
    value_shortlist.csv). Fyra gånger 2600 långsamma SD-kort-läsningar var en
    huvudorsak till 30s-hängningen. Kartan är en ren funktion av score-filerna
    på disk → cacha den på deras mtime, så den byggs EN gång per
    datauppdatering, inte per anrop (och INTE om vid varje modellbyte).
    Nattjobbet som skriver om CSV:erna ändrar mtime → cachen ogiltigförklaras
    automatiskt. Alla anropare är läs-only (verifierat) → att dela objektet
    är säkert."""
    key = _scores_mtime()
    hit = _SCORES_CACHE.get("entry")
    if hit is not None and hit[0] == key:
        return hit[1]
    out = _load_scores_uncached()
    _SCORES_CACHE["entry"] = (key, out)
    return out


def _load_scores_uncached() -> dict:
    """
    SAMMANSLAGNINGEN: en per-ticker-poängkarta ur ALLA modellers output.
      quality  – Kvalitet-vyns composite (LLM+kvant-merged, 0–5) + värderingszon
      quant    – token-fria kvant-screenerns betyg (skala varierar → percentilrankas)
      prob_up  – momentum-modellens senaste P(upp), båda segmenten
      research – uppdragsanalys/analys-anteckning finns
    Saknade filer/kolumner ignoreras tyst – kartan byggs av det som finns.
    """
    out = {}

    def ent(tk, name=None):
        e = out.setdefault(tk, {"ticker": tk})
        if name and not e.get("name"):
            e["name"] = name
        return e

    qp = _results_dir() / "quality_shortlist.csv"
    if qp.exists():
        try:
            for r in csv.DictReader(open(qp, encoding="utf-8")):
                tk = (r.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                e = ent(tk, r.get("name"))
                e["quality"] = _score_num(r.get("composite"))
                e["zone"] = (r.get("zone") or "").strip()
        except Exception:  # noqa: BLE001
            pass

    kp = _results_dir() / "quant_shortlist.csv"
    if kp.exists():
        try:
            rows_k = list(csv.DictReader(open(kp, encoding="utf-8")))
            col = next((c for c in ("grade", "quant_score", "composite", "score", "total")
                        if rows_k and _score_num(rows_k[0].get(c)) is not None), None)
            if col:
                for r in rows_k:
                    tk = (r.get("ticker") or "").strip().upper()
                    v = _score_num(r.get(col))
                    if tk and v is not None:
                        ent(tk, r.get("name"))["quant"] = v
        except Exception:  # noqa: BLE001
            pass

    # Buffett-värdeskreenern (value_screener.py). Egen zon-kolumn ('billig'/
    # 'rimlig'/'dyr'/'förlust') SEPARAT från quality-screenerns 'zone' –
    # olika värderingsbaser (owner earnings vs EBITDA/P/S) – så den lagras
    # som 'value_zone', inte skriver över 'zone'. Buffett-barren
    # (meets_roe_bar/meets_debt_bar) tas med för köp-vaktens hårda grind.
    vp = _results_dir() / "value_shortlist.csv"
    if vp.exists():
        try:
            for r in csv.DictReader(open(vp, encoding="utf-8")):
                tk = (r.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                e = ent(tk, r.get("name"))
                e["value_score"] = _score_num(r.get("value_score"))
                e["value_zone"] = (r.get("zone") or "").strip()
                e["meets_roe_bar"] = str(r.get("meets_roe_bar")).strip().lower() == "true"
                e["meets_debt_bar"] = str(r.get("meets_debt_bar")).strip().lower() == "true"
                # Råvarusektor-uteslutningen (value_screener.py:s egen Buffett-bar/
                # checklista, se _COMMODITY_SECTORS där) LÄSTES ALDRIG in här – denna
                # köp-motors EGEN is_buffett-grind (se _rank_buy_candidates nedan)
                # kollade bara meets_roe_bar/meets_debt_bar, aldrig sektorn. Verkligt
                # fel: Lundin Gold (Materials, guld-cyklisk utan prissättningsmakt)
                # klarade båda hårda barren numeriskt och dök upp som "bästa köp
                # enligt ALLA modeller" i Buffett-modellen trots att den redan var
                # uteslutet ur value_screener.py:s EGNA Buffett-lista.
                e["commodity_sector"] = str(r.get("commodity_sector")).strip().lower() == "true"
                # OT-grindens två pris-baserade flaggor (value_screener._price_risk):
                # uppvärderad-utan-resultat resp. extremvolatil – läses in HÄR så
                # is_buffett-grinden nedan ser samma verklighet som value_screener.py:s
                # egen Buffett-lista (commodity_sector-lärdomen: två 'Buffett'-ytor
                # får aldrig glida isär igen).
                e["rerated_up"] = str(r.get("rerated_up")).strip().lower() == "true"
                e["high_vol"] = str(r.get("high_vol")).strip().lower() == "true"
                # Nordiska sekundärnoteringar (t.ex. Medistim ASA/MEDIO.ST, NOK):
                # VERIFIERAT (currency_check mot Medistim ASAs riktiga bokslut)
                # att Buffett-KVOTERNA (ROE/D-E/multipel) är valuta-oberoende och
                # alltså giltiga oavsett - ingen uteslutning här, bara en etikett
                # så 'why'-texten aldrig tyst antar SEK.
                e["currency"] = (r.get("currency") or "SEK").strip()
                # OBS: _num() slänger negativa tal (den är byggd för kurser/
                # värden) – ROE och tillväxt KAN vara negativa och är då just
                # det säljvakten bryr sig om, så parsa dem direkt med float().
                e["roe"] = _signed_num(r.get("roe"))
                e["rev_growth_yoy"] = _signed_num(r.get("rev_growth_yoy"))
                e["has_value_data"] = True
        except Exception:  # noqa: BLE001
            pass

    for seg in config.SEGMENTS.values():
        sp = Path(seg.get("results_dir", "")) / "signals.csv"
        if not sp.exists():
            continue
        for tk, r in _latest_signals(sp).items():   # pandas-snabb (var ~12s i en radloop)
            p = _score_num(r.get("prob_up"))
            if p is not None:
                e = ent(tk, r.get("name"))
                # Ticker i BÅDA segmenten (bytt börsvärdesklass, t.ex. Smart Eye):
                # ta det starkaste segmentets prob_up – men då MÅSTE pred_signal
                # följa med från SAMMA segment. Tidigare togs max(prob_up) medan
                # pred_signal ovillkorligt skrevs över av sist lästa segmentet
                # (small) → en post kunde säga prob_up 68% (large) och samtidigt
                # "modellen har släppt bolaget" (small:s signal), vilket
                # säljvakten läser som en äkta sälj-bekräftelse.
                if p >= (e.get("prob_up") or 0.0):
                    e["prob_up"] = p
                    e["pred_signal"] = str(r.get("pred_signal"))

    # Mjuka värden TOKEN-FRITT (altdata/soft_signals.py, nattligt): destillerad
    # LLM-elev (eller lexikon-läge). Används som KVALITETS-FALLBACK enbart där
    # LLM-betyget saknas – LLM:en vinner ALLTID när den finns – och märks med
    # quality_source="soft" så why-etiketten aldrig kan förväxla källorna.
    # Röda flaggor (going concern, vinstvarning...) följer med till säljvakten.
    for seg in config.SEGMENTS.values():
        sfp = Path(seg.get("results_dir", "")) / "soft_signals.csv"
        if not sfp.exists():
            continue
        try:
            for r in csv.DictReader(open(sfp, encoding="utf-8")):
                tk = (r.get("ticker") or "").strip().upper()
                if not tk:
                    continue
                soft = _score_num(r.get("soft_score"))
                llm = _score_num(r.get("llm_composite"))   # LLM-facit ur quality-CACHEN
                e = ent(tk, r.get("name"))
                if e.get("quality") is None:
                    # LLM vinner ÄVEN här: llm_composite täcker bolag som är
                    # LLM-betygsatta i cachen men inte (längre) står i
                    # quality_shortlist.csv (t.ex. äldre screen-körning) –
                    # elevens gissning går aldrig före lärarens faktiska svar.
                    if llm is not None:
                        e["quality"] = llm
                    elif soft is not None:
                        e["quality"] = soft
                        e["quality_source"] = "soft"
                try:
                    e["red_flag_count"] = int(r.get("red_flag_count") or 0)
                except (TypeError, ValueError):
                    pass
                if r.get("red_flags"):
                    e["soft_red_flags"] = r["red_flags"]
        except Exception:  # noqa: BLE001
            pass

    # MFN-händelser (insynshandel + senaste rapportdatum, altdata/mfn_events.py,
    # nattligt genererad). BERIKAR bara befintliga poster – en ticker med enbart
    # insynsdata kan ändå aldrig rankas (kräver minst ett fundament-betyg).
    for seg in config.SEGMENTS.values():
        evp = Path(seg.get("results_dir", "")) / "mfn_events.csv"
        if not evp.exists():
            continue
        try:
            for r in csv.DictReader(open(evp, encoding="utf-8")):
                tk = (r.get("ticker") or "").strip().upper()
                e = out.get(tk)
                if e is None:
                    continue
                try:
                    e["insider_buys_90d"] = int(r.get("insider_buys_90d") or 0)
                    e["insider_sells_90d"] = int(r.get("insider_sells_90d") or 0)
                except (TypeError, ValueError):
                    pass
                if r.get("last_report_date"):
                    e["last_report_date"] = r["last_report_date"]
        except Exception:  # noqa: BLE001
            pass

    # OBS: 'research' (uppdragsanalys-flaggan) sätts INTE eagert här längre.
    # _research_note() fulltext-skannar en stor MFN-fil per bolag (~14,5s för
    # hela universumet i profileringen) → beräknas numera LAT i _unified_rank,
    # bara för topp-kandidaterna. Konsumenter (bara _unified_rank via
    # _composite_score) tål att flaggan saknas = ingen bonus (verifierat att
    # inga andra läsare finns).
    return out


def _load_flows() -> dict:
    """{ticker: flow-rad} ur flow_snapshot.csv över båda segmenten (CMF/relvol/SMA20)."""
    out = {}
    for seg in config.SEGMENTS.values():
        fp = Path(seg.get("results_dir", "")) / "flow_snapshot.csv"
        if not fp.exists():
            continue
        try:
            for r in csv.DictReader(open(fp, encoding="utf-8")):
                out.setdefault((r.get("ticker") or "").upper(), r)
        except Exception:  # noqa: BLE001
            pass
    return out


def _opportunity(rows, amount) -> dict:
    """
    OPPORTUNISTISKT KÖP (denna månad): låt den bästa satelliten front-loada en del
    av månadsinsättningen NÄR den visar BEKRÄFTAD styrka – inte på hopp inför en
    katalysator. Kärnan hämtas ikapp nästa månad automatiskt (fyll-mot-mål gör dig
    undervikt kärnan efter en satellit-tung månad → nästa insättning styrs dit).

    PEAD-disciplin: köp den BEKRÄFTADE driften, inte ryktet. En kandidat
    diskvalificeras (→ 'vänta på bekräftelse') om något av detta gäller:
      · distribution: CMF 13v < 0 (flöden UT – de stora kliver av)
      · trendbrott: kurs < SMA20
      · värdering: zon 'dyr' (redan förbi fundamenta)
    Klarar den grinden får den front-loada upp till OPPORTUNITY_MAX_SHARE av
    beloppet. Utan rapportkalender (MFN) approximeras 'bekräftad' med flödena
    ovan; det fångar 'köp inte in i en fallande kniv eller en froth-topp'.
    """
    ranked = _unified_rank(rows, top_n=5)
    if not ranked:
        return None
    scores = _load_scores()
    flows = _load_flows()
    cap = round(float(amount) * float(getattr(config, "OPPORTUNITY_MAX_SHARE", 0.5)))
    # Värderings-spärren följer vald modells bas: buffett-läget zonar på
    # owner earnings (value_zone, samma som _unified_rank:s dyr-uteslutning),
    # övriga på quality-screenerns EBITDA/P/S-zon. TIMING-signalerna (CMF/
    # SMA20) är däremot avsiktligt kvar i ALLA lägen – det är köp-vaktens
    # uttalade roll ("köp inte just här idag – nästa månad ser bättre ut"),
    # TA som timing-grind, inte som rankningsvikt.
    model = _safe(active_model, "balanced", "aktiv modell")
    zone_key = "value_zone" if model == "buffett" else "zone"

    def evaluate(c):
        tk = c["ticker"]
        fl = flows.get(tk, {})
        sc = scores.get(tk, {})
        try:
            cmf = float(fl.get("cmf_13w"))
        except (TypeError, ValueError):
            cmf = None
        below = str(fl.get("below_sma20")) == "1"
        zone = sc.get(zone_key)
        blocks = []
        if cmf is not None and cmf < 0:
            blocks.append(f"distribution (CMF {cmf:+.2f} – flöden ut)")
        if below:
            blocks.append("trendbrott (kurs < SMA20)")
        if zone == "dyr":
            blocks.append("värdering 'dyr' (förbi fundamenta)")
        # PEAD på RIKTIGA rapportdatum (mfn_events.csv). Kvartalsrytm ≈ 91 dagar:
        #  · BLACKOUT strax före väntad nästa rapport (est. sista rapport + 91d):
        #    "köp inte ryktet" – exakt den disciplin docstringen beskriver, nu
        #    med faktiskt datum i stället för enbart flödes-approximationen.
        #  · Färsk rapport (≤ PEAD_FRESH_DAYS) + redan passerade flödes-/trend-
        #    grindar = bekräftad drift → uttrycklig PEAD-bekräftelse.
        days_since = None
        lr = sc.get("last_report_date")
        if lr:
            try:
                import datetime as _dt
                days_since = (_dt.date.today() - _dt.date.fromisoformat(str(lr)[:10])).days
            except (TypeError, ValueError):
                days_since = None
        confirm = []
        if days_since is not None:
            lo = int(getattr(config, "PEAD_BLACKOUT_MIN_DAYS", 77))
            hi = int(getattr(config, "PEAD_BLACKOUT_MAX_DAYS", 104))
            fresh = int(getattr(config, "PEAD_FRESH_DAYS", 42))
            if lo <= days_since <= hi:
                blocks.append(f"rapport väntas snart (senaste för {days_since}d sedan, "
                              f"kvartalsrytm) – köp inte ryktet (PEAD)")
            elif days_since <= fresh:
                confirm.append(f"PEAD: rapport för {days_since}d sedan – driften bekräftad")
        # Kluster av insynsköp (netto ≥ 2 på 90d) – stark oberoende bekräftelse.
        ins_net = (sc.get("insider_buys_90d") or 0) - (sc.get("insider_sells_90d") or 0)
        if ins_net >= 2:
            confirm.append(f"insynsköp-kluster ({sc.get('insider_buys_90d')} köp 90d)")
        if cmf is not None and cmf >= 0.03:
            confirm.append(f"ackumulation (CMF {cmf:+.2f})")
        if not below and fl:
            confirm.append("trend intakt (över SMA20)")
        return blocks, confirm

    for c in ranked:
        blocks, confirm = evaluate(c)
        if not blocks:
            return {
                "confirmed": True, "ticker": c["ticker"], "name": c["name"],
                "kr": cap, "note": c["note"], "score": c["score"],
                "confirmations": confirm or ["klarar grinden (inga varningsflaggor)"],
                "advice": (f"Front-loada upp till {cap:,.0f} kr denna månad i {c['name']} – "
                           "bekräftad styrka, inte hopp. Kärnan hämtas ikapp nästa månad. "
                           "OBS: taktiskt vad, inte kärna – det är obevisad edge.").replace(",", " "),
            }
    top = ranked[0]
    blocks, _ = evaluate(top)
    return {
        "confirmed": False, "ticker": top["ticker"], "name": top["name"],
        "kr": 0, "note": top["note"], "score": top["score"], "blocked_by": blocks,
        "advice": (f"Bästa satelliten ({top['name']}) är INTE bekräftad just nu: "
                   f"{', '.join(blocks)}. Köp inte in i det – följ den vanliga fördelningen och "
                   "vänta tills flödena/trenden vänt (eller en rapport bekräftat driften)."),
    }


def _pct_rank(sorted_vals, v):
    """Percentil av v bland sorted_vals (0..1). Skalfri normalisering mellan modeller.

    sorted_vals MÅSTE redan vara sorterad (stigande, None borttaget) av anroparen –
    _unified_rank sorterar en gång per rankningsomgång och återanvänder listan för
    varje bolag. Sorterade man om här per anrop (som tidigare) blev hela
    _unified_rank O(n² log n) i antal bolag – obemärkt med en handfull test-
    tickers, men en verklig hängning (30s+ timeout) med hela Sverige-universumet
    (~2600+ bolag) efter att value_shortlist.csv gjorde 'scores' mycket större.
    bisect ger O(log n) per uppslag istället.

    LIKA VÄRDEN får MITTRANK (snitt av bisect_left/bisect_right) – samma
    tie-fix som _ranks() i quant-/value-screenern fick i matematik-granskningen,
    men denna separata implementation missades då. Enbart bisect_right gav alla
    i ett tie-block TOPPEN av blocket: kvalitetsbetyget (0–5 i 0,1-steg) har
    tunga ties, så modalvärdet (t.ex. 40/100 bolag på 3,5) fick percentil 0,70
    i stället för ärliga 0,50 – en systematisk uppblåsning av tie-tunga källor
    (kvalitet/kvant-betyg) relativt kontinuerliga (value_score/P(upp)) i den
    sammanvägda poängen. Rangordningen INOM ett tie-block var alltid lika –
    skevheten satt i viktningen MELLAN källor."""
    if not sorted_vals or v is None:
        return None
    lo = bisect.bisect_left(sorted_vals, v)
    hi = bisect.bisect_right(sorted_vals, v)
    return ((lo + hi) / 2) / len(sorted_vals)


# Viktprofiler per rank-modell (köp-vakten). Nycklar: quality/quant/value/
# momentum + research-bonus. "balanced" är IDENTISK med den mix som gällde
# innan modellvalet fanns (value=0), så default-beteendet är oförändrat.
_MODEL_WEIGHTS = {
    "balanced": {"quality": 0.45, "quant": 0.20, "value": 0.00, "momentum": 0.25, "research": 0.10},
    "buffett":  {"quality": 0.30, "quant": 0.10, "value": 0.40, "momentum": 0.05, "research": 0.15},
    "momentum": {"quality": 0.15, "quant": 0.10, "value": 0.00, "momentum": 0.70, "research": 0.05},
}


def _model_file() -> Path:
    return Path(config.anchor(getattr(config, "PORTFOLIO_MODEL_FILE", "cache/portfolio_model.json")))


def active_model() -> str:
    """Vald rank-modell ('balanced'/'buffett'/'momentum'), persisterad i cache/.
    Okänt/trasigt värde faller tillbaka på default."""
    default = getattr(config, "PORTFOLIO_MODEL_DEFAULT", "balanced")
    p = _model_file()
    if p.exists():
        try:
            m = json.loads(p.read_text(encoding="utf-8")).get("model")
            if m in _MODEL_WEIGHTS:
                return m
        except Exception:  # noqa: BLE001
            pass
    return default if default in _MODEL_WEIGHTS else "balanced"


def set_active_model(model: str) -> str:
    """Persisterar vald modell. Okänt namn ignoreras (behåller nuvarande)."""
    if model not in _MODEL_WEIGHTS:
        return active_model()
    p = _model_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model": model}, ensure_ascii=False), encoding="utf-8")
    return model


def _composite_score(e: dict, model: str, w: dict, q_sorted, k_sorted, v_sorted, research=None):
    """Sammanvägd poäng + 'why'-etiketter för ETT bolag under viktprofilen
    `w`, mot en given universums-fördelning (redan sorterade quality/quant/
    value-listor – se _pct_rank:s docstring). Utbruten ur _unified_rank:s
    loop så SAMMA formel kan återanvändas av altdata/manual_scan.py (testar
    en enskild scenario-aktie mot samma fördelning som resten av
    universumet).
    Returnerar None om bolaget saknar alla tre fundament-betyg (kräver
    minst ett – köp-och-behåll, inte bara fart). OBS: score är RÅ (oavrundad,
    ingen sektor-/koncentrations-justering) – det portfölj-medvetna påslaget
    (sektorstraff m.m.) hör hemma hos anroparen, inte här.

    research: uppdragsanalys-bonus. None (default) = läs e['research'] (bakåt-
    kompatibelt för manual_scan som sätter den själv). _unified_rank kör i två
    pass och skickar EXPLICIT False i pass 1 (bas-poäng utan att läsa någon
    MFN-fil) och True bara för topp-kandidaterna i pass 2 – så den dyra
    fulltextskanningen sker bara för en handfull bolag, inte hela universumet."""
    if research is None:
        research = bool(e.get("research"))
    is_buffett = (model == "buffett")
    qn = _pct_rank(q_sorted, e.get("quality"))
    kn = _pct_rank(k_sorted, e.get("quant"))
    vn = _pct_rank(v_sorted, e.get("value_score"))
    if qn is None and kn is None and vn is None:
        return None                      # köp-och-behåll: kräver fundament, inte bara fart
    pn = e.get("prob_up")
    # Coalesce: en modell ska inte straffa ett bolag för att EN datakälla
    # saknas – fall tillbaka på de andra fundament-betygen. Bara signaler
    # som modellen FAKTISKT viktar (>0) räknas in i fallbacken, så
    # 'balanced' (value-vikt 0) ger exakt samma resultat som innan
    # value-screenern fanns – bekräftat identiskt via test.
    weighted_present = [x for x, wname in ((qn, "quality"), (kn, "quant"), (vn, "value"))
                        if x is not None and w[wname] > 0]
    fb = (sum(weighted_present) / len(weighted_present)) if weighted_present else 0.5
    score = (w["quality"] * (qn if qn is not None else fb)
             + w["quant"] * (kn if kn is not None else fb)
             + w["value"] * (vn if vn is not None else fb)
             + w["momentum"] * (pn if pn is not None else 0.5)
             + (w["research"] if research else 0.0))
    # Insynsköp-bonus (mfn_events.csv): NETTO-kluster av PDMR-köp senaste 90d –
    # en av de mest robust dokumenterade positiva signalerna. Kräver netto ≥ 2
    # (enstaka köp är ofta program-brus, kluster är den belagda signalen).
    # Additiv liten bonus som research – config 0 stänger av. Data kommer ur
    # den redan lästa poängkartan (INGA fil-läsningar här, till skillnad från
    # research-bonusen som därför körs lat i pass 2).
    ins_net = (e.get("insider_buys_90d") or 0) - (e.get("insider_sells_90d") or 0)
    ins_bonus = float(getattr(config, "PORTFOLIO_INSIDER_BONUS", 0.05))
    if ins_net >= 2 and ins_bonus > 0:
        score += ins_bonus
    why = []
    if e.get("quality") is not None:
        # "mjuk-kvalitet" = token-fri destillerad/lexikon-poäng (soft_signals),
        # bara använd när LLM-betyg saknas – källan ska aldrig gå att förväxla.
        qlabel = "mjuk-kvalitet" if e.get("quality_source") == "soft" else "kvalitet"
        why.append(f"{qlabel} {e['quality']:.1f}/5" + (f" · {e['zone']}" if e.get("zone") else ""))
    if is_buffett and e.get("value_score") is not None:
        why.append(f"value {e['value_score']:.0f}" + (f" · {e['value_zone']}" if e.get("value_zone") else "")
                   + (f" [{e['currency']}]" if e.get("currency") and e["currency"] != "SEK" else ""))
    if e.get("quant") is not None:
        why.append(f"kvant {e['quant']:.0f}")
    if pn is not None:
        why.append(f"P(upp) {pn:.0%}")
    if research:
        why.append("uppdragsanalys ✓")
    if ins_net >= 2 and ins_bonus > 0:
        why.append(f"insynsköp-kluster ({e.get('insider_buys_90d')} köp 90d)")
    return score, why, {"quality_pctl": qn, "quant_pctl": kn, "value_pctl": vn}


def _unified_rank(rows, top_n=3, model=None) -> list:
    """
    'Absolut bästa nästa köp' bland svenska aktier: EN rankning som väger ihop
    alla modeller enligt den VALDA viktprofilen (se _MODEL_WEIGHTS / active_model)
    och PORTFÖLJ-MEDVETENHET:
      · zon 'dyr' utesluts (betala inte upp för att momentum lyser) – för
        buffett-modellen gäller value_screenerns egen owner-earnings-zon
      · buffett-modellen har dessutom en HÅRD grind: klarar bolaget inte
        ROE- och skuld-barren (meets_roe_bar/meets_debt_bar) kvalificerar det
        inte alls, oavsett momentum ("köp inte skräp bara för att det är billigt").
        Samma grind utesluter råvarusektorer (commodity_sector, se
        value_screener.py:s _COMMODITY_SECTORS) – ett VERIFIERAT äkta fel
        (Lundin Gold, guld-cyklisk utan prissättningsmakt) visade att denna
        rankning läste meets_roe_bar/meets_debt_bar men aldrig commodity_sector
        ur value_shortlist.csv, trots att value_screener.py:s EGEN Buffett-
        lista redan uteslöt bolaget – två separata "Buffett"-ytor som glidit isär
      · innehav som redan är >8% av portföljen utesluts (koncentrera inte mer)
      · samma sektor som portföljens största (>25%) straffas
      · kräver minst ETT fundament-betyg (kvalitet/kvant/value) – inte bara fart
    """
    scores = _load_scores()
    if not scores:
        return []
    model = model or active_model()
    w = _MODEL_WEIGHTS.get(model, _MODEL_WEIGHTS["balanced"])
    is_buffett = (model == "buffett")

    total = sum(r["value"] for r in rows) or 0.0
    owned_frac, sector_frac = {}, {}
    for r in rows:
        tk = (r.get("ticker") or _resolve_ticker(r["name"]) or "").upper()
        if tk and total:
            owned_frac[tk] = owned_frac.get(tk, 0.0) + r["value"] / total
            sec = _sector_of(tk)
            if sec:
                sector_frac[sec] = sector_frac.get(sec, 0.0) + r["value"] / total
    big_sectors = {s for s, f in sector_frac.items() if f > 0.25}

    q_all = [e.get("quality") for e in scores.values()]
    k_all = [e.get("quant") for e in scores.values()]
    v_all = [e.get("value_score") for e in scores.values()]
    # Sorteras EN gång här och återanvänds för varje bolag i loopen nedan
    # (_pct_rank kräver redan sorterad indata) – se _pct_rank:s docstring.
    q_sorted = sorted(x for x in q_all if x is not None)
    k_sorted = sorted(x for x in k_all if x is not None)
    v_sorted = sorted(x for x in v_all if x is not None)
    # PASS 1 – bas-poäng UTAN uppdragsanalys-bonus (research=False → läser INGEN
    # MFN-fil). Att läsa research eagert för varje bolag i universumet var ~14,5s
    # (profilerat). Bonusen läggs på lat i pass 2 nedan, bara för topp-kandidaterna.
    ranked = []
    for tk, e in scores.items():
        # Dyr-uteslutning: buffett tittar på owner-earnings-zonen (value_zone),
        # övriga på quality-screenerns EBITDA/P/S-zon.
        dyr_zone = e.get("value_zone") if is_buffett else e.get("zone")
        if dyr_zone == "dyr":
            continue
        if owned_frac.get(tk, 0.0) > 0.08:
            continue
        # Buffett-grind: kräver att BÅDA hårda barren klaras (om value-data
        # finns för bolaget alls; saknas den helt får bolaget inte passera
        # buffett-grinden – köp bara det vi faktiskt kunnat värdera).
        if is_buffett:
            if e.get("value_score") is None:
                continue
            if not (e.get("meets_roe_bar") and e.get("meets_debt_bar")):
                continue
            if e.get("commodity_sector"):
                continue
            # OT-grinden (samma fyra spärrar som value_screener.py:s egen
            # Buffett-lista): säkerhetsmarginal (bara config.BUFFETT_BUY_ZONES,
            # default 'billig' – "uppsida med marginal när jag köper"; 'okänd'/
            # tom zon faller också bort: köp bara det vi faktiskt kunnat
            # värdera), ej uppvärderad utan resultat, ej extremvolatil.
            if (e.get("value_zone") or "") not in getattr(config, "BUFFETT_BUY_ZONES", ("billig",)):
                continue
            if e.get("rerated_up") or e.get("high_vol"):
                continue
        res = _composite_score(e, model, w, q_sorted, k_sorted, v_sorted, research=False)
        if res is None:
            continue
        score, why, _pctls = res
        sec = _sector_of(tk)
        if sec in big_sectors:
            score -= 0.15
        ranked.append({"ticker": tk, "name": e.get("name") or tk,
                       "score": round(score, 3), "note": " · ".join(why),
                       "source": f"sammanvägd ({model})"})
    ranked.sort(key=lambda x: -x["score"])

    # PASS 2 – lägg på uppdragsanalys-bonusen LAT, bara för topp-K kandidaterna.
    # Bonusen är liten (≤0.15) och ADDERAS bara → en generös marginal (K) räcker
    # för att fånga alla som den skulle kunna putta upp i topp-N, utan att läsa
    # en MFN-fil per bolag i hela universumet (bara ~dussintal svenska småbolag
    # har betald analys ändå). research-vikt 0 (ingen modell har det) skulle
    # göra pass 2 meningslös → hoppa då direkt.
    if w["research"] > 0 and ranked:
        K = max(top_n * 5, 20)
        for cand in ranked[:K]:
            if _research_note(cand["ticker"]):
                cand["score"] = round(cand["score"] + w["research"], 3)
                cand["note"] = (cand["note"] + " · uppdragsanalys ✓") if cand["note"] else "uppdragsanalys ✓"
        ranked.sort(key=lambda x: -x["score"])
    return ranked[:top_n]


def _takeprofit_ledger_path() -> Path:
    return Path(config.anchor("cache/takeprofit_ledger.json"))


def _update_takeprofit_ledger(ticker: str, price: float, level: int) -> None:
    """Loggar kursen vid ett skarpt säljvakts-råd (nivå ≥2). Högsta kurs
    behålls per ticker – rådet återkommer ofta vecka efter vecka medan kursen
    stiger, och det är TOPPEN av rådperioden som är framtidskurs-proxyn."""
    p = _takeprofit_ledger_path()
    try:
        ledger = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        ledger = {}
    cur = ledger.get(ticker)
    if cur is None or price > float(cur.get("price") or 0):
        import datetime as _dt
        ledger[ticker] = {"price": round(price, 2), "level": level,
                          "date": _dt.date.today().isoformat()}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def _refill_candidates(rows) -> list:
    """FYLLA PÅ-REGELN (OT: 'fylla på kan jag göra om jag nått framtidskurs,
    sålt av en del enligt modellen och värdet åter gått ner en bit under
    framtidskursen'). Vår översättning:

      1. Säljvakten gav ett skarpt råd (nivå ≥2 – 'ta hem vinsten'/'sälj')
         vid kurs P (liggaren ovan – vår framtidskurs-proxy).
      2. Kursen har sedan fallit ≥ config.REFILL_DISCOUNT under P.
      3. Du äger fortfarande bolaget (påfyllnad, inte återuppståndelse av
         helt sålda positioner).
      4. Caset håller fortfarande: inga röda flaggor, inte värderingszon
         'dyr', och (om value-data finns) klarar fortfarande ROE/skuld-barren
         – ett bolag som fallit för att CASET försämrats är ingen påfyllnad,
         det är en varning.

    Rent rådgivande – köper inget, flyttar inga kronor i planen."""
    p = _takeprofit_ledger_path()
    if not p.exists():
        return []
    try:
        ledger = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    held = {(r.get("ticker") or "").upper(): r for r in rows}
    watch = {t: v for t, v in ledger.items() if t in held}
    if not watch:
        return []
    discount = float(getattr(config, "REFILL_DISCOUNT", 0.10))

    closes: dict = {}
    for seg in config.SEGMENTS.values():
        pp = Path(seg.get("results_dir", "")) / "prices.csv"
        if not pp.exists():
            continue
        try:
            for r in csv.DictReader(open(pp, encoding="utf-8")):
                tk = (r.get("ticker") or "").upper()
                if tk in watch:
                    v = _num(r.get("close"))
                    if v:
                        closes[tk] = v   # sista raden per ticker vinner (kronologisk fil)
        except Exception:  # noqa: BLE001
            continue

    scores = _load_scores()
    out = []
    for tk, entry in watch.items():
        price_now = closes.get(tk)
        tp_price = float(entry.get("price") or 0)
        if not price_now or tp_price <= 0:
            continue
        if price_now > tp_price * (1 - discount):
            continue
        sc = scores.get(tk, {})
        if int(sc.get("red_flag_count") or 0) > 0:
            continue
        if sc.get("zone") == "dyr" or sc.get("value_zone") == "dyr":
            continue
        if sc.get("has_value_data") and (sc.get("meets_roe_bar") is False
                                         or sc.get("meets_debt_bar") is False):
            continue
        dip = 1 - price_now / tp_price
        out.append({
            "ticker": tk, "name": held[tk].get("name") or tk,
            "tp_price": round(tp_price, 2), "tp_date": entry.get("date"),
            "price": round(price_now, 2), "dip": round(dip, 4),
            "why": (f"Säljvakten flaggade 'ta hem vinsten' vid ~{tp_price:.0f} kr "
                    f"({entry.get('date')}); kursen är nu {dip:.0%} under den nivån "
                    f"och caset håller fortfarande – läge att fylla på om du tog hem vinst då."),
        })
    out.sort(key=lambda x: -x["dip"])
    return out


def _takeprofit(rows) -> list:
    """
    SÄLJVAKTEN v2 – en TRAPPA som armeras på DIN vinst, inte aktiens kurs.

    ARMERAS bara om DU faktiskt är i vinst: orealiserad gain (value/cost − 1) ≥
    TAKEPROFIT_GAIN. En aktie som rusat i marknaden INNAN du köpte den (eller som
    du köpt dyrt) armerar alltså aldrig – det finns ingen vinst att ta hem. Styrka
    i sig är inte säljskäl (momentum-vinnare fortsätter oftare än de rekylerar) →
    gainen armerar bara; bekräftelser eskalerar rådet:

      nivå 1 'bevaka'         du är upp ≥ TAKEPROFIT_GAIN men trend/flöden/
                              värdering håller – rid vinnaren vidare.
      nivå 2 'ta hem vinsten' armerad + minst en bekräftelse:
                                · melt-up: ≥ TAKEPROFIT_ACCEL_SHARE av uppgången
                                  de senaste 4 veckorna
                                · värdering: zon 'dyr' (runnit förbi fundamenta)
                                · distribution: CMF 13v < 0 (flöden UT)
                                · modellen har släppt bolaget (pred_signal 0)
                                · sprungit ≥ GAP_PP ifrån index (froth-kontext)
                              → house money: sälj vinsten, behåll insatsen.
      nivå 3 'sälj'           armerad + TRENDBROTT (kurs < SMA20).

    Innehav UTAN inköpspris kan inte bedömas (vet ej om du är i vinst); visar en
    'ange inköpspris'-notis om aktien ser överhettad ut i marknaden.
    Trösklarna kalibreras empiriskt med tune_takeprofit.py – 0.50 är startvärde.
    """
    gain_min = float(getattr(config, "TAKEPROFIT_GAIN", 0.50))
    gap_min = float(getattr(config, "TAKEPROFIT_GAP_PP", 0.50))
    weeks = int(getattr(config, "TAKEPROFIT_WEEKS", 26))
    accel_share = float(getattr(config, "TAKEPROFIT_ACCEL_SHARE", 0.5))
    tickers = {(r.get("ticker") or _resolve_ticker(r["name"]) or "").upper(): r
               for r in rows}
    tickers.pop("", None)
    if not tickers:
        return []
    # ISK-antagande: under gränsen är en försäljning skattefri (bara courtage) →
    # house-money-rådet är billigt att följa. Över gränsen tillkommer reavinstskatt.
    total = sum(r.get("value", 0.0) for r in rows)
    is_isk = total <= float(getattr(config, "PORTFOLIO_ISK_LIMIT", 300000))
    tax_note = (" På ISK är detta skattefritt – bara courtage." if is_isk
                else " OBS: vanlig depå – reavinstskatt tillkommer, så väg vinsten mot skatten.")
    scores = _load_scores()
    flags, seen = [], set()
    for seg in config.SEGMENTS.values():
        rd = Path(seg.get("results_dir", ""))
        pp, bb = rd / "prices.csv", rd / "portfolio.csv"
        if not (pp.exists() and bb.exists()):
            continue
        try:
            closes = {}
            for r in csv.DictReader(open(pp, encoding="utf-8")):
                tk = (r.get("ticker") or "").upper()
                if tk in tickers:
                    closes.setdefault(tk, []).append(_num(r.get("close")))
            idx = [v for v in (_num(r.get("omxs30_value"))
                               for r in csv.DictReader(open(bb, encoding="utf-8"))) if v]
            flows = {}
            fp = rd / "flow_snapshot.csv"
            if fp.exists():
                for r in csv.DictReader(open(fp, encoding="utf-8")):
                    flows[(r.get("ticker") or "").upper()] = r
        except Exception:  # noqa: BLE001
            continue
        if len(idx) <= weeks:
            continue
        idx_ret = idx[-1] / idx[-1 - weeks] - 1
        for tk, series in closes.items():
            if tk in seen or len(series) <= weeks or not series[-1] or not series[-1 - weeks]:
                continue
            seen.add(tk)
            hr = tickers[tk]
            h_ret = series[-1] / series[-1 - weeks] - 1   # aktiens marknadsavk. (kontext)
            gap = h_ret - idx_ret

            # ── ARMERING: DIN orealiserade vinst, inte aktiens kurs ──────────
            cost = hr.get("cost")
            gain = (hr["value"] / cost - 1) if (cost and cost > 0 and hr.get("value")) else None

            # Marknads-froth-bekräftelser (beräknas oavsett – styr eskaleringen).
            confirms = []
            if h_ret > 0.10 and len(series) > 5 and series[-5]:
                share = (series[-1] / series[-5] - 1) / h_ret
                if share >= accel_share:
                    confirms.append(f"melt-up: {share:.0%} av uppgången på 4v")
            sc = scores.get(tk, {})
            if sc.get("zone") == "dyr":
                confirms.append("värdering: zon 'dyr'")
            # ── CASET HAR ÄNDRATS (fundamenta) – Buffett-säljvaktens kärna ────
            # "Sälj när caset ändras": ett bolag man köpt för dess kvalitet ska
            # säljas när kvaliteten FALLER, inte bara när kursen rusat. Kräver
            # value_screener-data (has_value_data) – utan den är dessa triggers
            # tysta (påverkar inte innehav vi ännu inte kunnat värdera). ÄRLIGT:
            # vi jämför mot BARREN idag, inte mot bolagets skick när du köpte
            # (vi sparar inte ingångs-fundamenta) – så detta fångar "klarar inte
            # längre kvalitetskraven", vilket är den relevanta säljsignalen även
            # om vi inte kan säga exakt när övergången skedde.
            if sc.get("has_value_data"):
                if sc.get("value_zone") == "dyr":
                    confirms.append("caset: owner-earnings-värdering nu 'dyr'")
                if sc.get("meets_roe_bar") is False:
                    roe = sc.get("roe")
                    confirms.append(f"caset: ROE {roe:.0%} under kvalitetsbarren"
                                    if roe is not None else "caset: ROE under kvalitetsbarren")
                if sc.get("meets_debt_bar") is False:
                    confirms.append("caset: skuldsättning över trygghetsbarren")
                g = sc.get("rev_growth_yoy")
                if g is not None and g < 0:
                    confirms.append(f"caset: intäkterna krymper ({g:+.0%} YoY)")
            # Insynsförsäljningar (oberoende av value-data): NETTO-kluster av
            # PDMR-sälj på 90d. Enstaka sälj är ofta diversifiering/privatekonomi
            # (svag signal) → kräver netto ≤ -2 precis som köp-klustret kräver ≥ 2.
            ins_net = (sc.get("insider_buys_90d") or 0) - (sc.get("insider_sells_90d") or 0)
            if ins_net <= -2:
                confirms.append(f"insynsförsäljningar ({sc.get('insider_sells_90d')} sälj-PM 90d)")
            # Regelbaserade röda flaggor ur senaste 12m PM-text (soft_signals):
            # going concern/vinstvarning/kontrollbalansräkning m.fl. – allvarliga
            # HÄNDELSER, inte ton, och aldrig modellberoende.
            if int(sc.get("red_flag_count") or 0) > 0:
                confirms.append(f"röda flaggor i PM: {sc.get('soft_red_flags') or sc.get('red_flag_count')}")
            fl = flows.get(tk, {})
            try:
                cmf = float(fl.get("cmf_13w"))   # _num duger inte: den slänger negativa tal
            except (TypeError, ValueError):
                cmf = None
            if cmf is not None and cmf < 0:
                confirms.append(f"distribution: CMF {cmf:+.2f} (flöden ut)")
            if sc.get("pred_signal") in ("0", "0.0"):
                confirms.append("modellen har släppt bolaget")
            if gap >= gap_min:
                confirms.append(f"sprungit +{gap:.0%} ifrån index på {weeks}v")
            broken = str(fl.get("below_sma20")) == "1"

            if gain is None:
                # Kan inte bedöma vinst utan inköpspris. Nämn bara om aktien ser
                # överhettad ut (froth-bekräftelse) – annars tyst.
                if confirms and gap >= gap_min:
                    flags.append({
                        "name": hr["name"], "ticker": tk, "level": 0, "action": "ange inköpspris",
                        "gain": None, "ret": round(h_ret, 4), "index_ret": round(idx_ret, 4),
                        "gap": round(gap, 4), "weeks": weeks, "house_money_kr": None,
                        "reasons": confirms,
                        "advice": ("Ser överhettad ut i marknaden, men du saknar inköpspris – "
                                   "ange det i Innehav så vet vakten om du faktiskt är i vinst att ta hem."),
                    })
                continue
            if gain < gain_min:
                continue   # du är inte tillräckligt i vinst → ingen vinst att skydda

            level = 1
            if confirms:
                level = 2
            if broken:
                confirms.append("TRENDBROTT: kurs under SMA20")
                level = 3
            action = {1: "bevaka", 2: "ta hem vinsten", 3: "sälj"}[level]
            house_kr = round(hr["value"] - cost)   # gain>0 garanterat här
            # FYLLA PÅ-LIGGAREN (OT: "nått framtidskurs, sålt av en del, värdet
            # åter under framtidskursen"): kursen vid ett skarpt 'ta hem
            # vinsten'/'sälj'-råd är vår proxy för framtidskursen – loggas så
            # _refill_candidates() senare kan föreslå påfyllnad när kursen
            # fallit en marginal under den. Högsta rådnivå-kursen behålls
            # (rådet kan återkomma vecka efter vecka på stigande kurs).
            if level >= 2 and series[-1]:
                _update_takeprofit_ledger(tk, float(series[-1]), level)
            flags.append({
                "name": hr["name"], "ticker": tk,
                "gain": round(gain, 4), "ret": round(h_ret, 4), "index_ret": round(idx_ret, 4),
                "gap": round(gap, 4), "weeks": weeks, "level": level, "action": action,
                "reasons": confirms or ["din vinst ≥ tröskeln men inga varningssignaler – bara bevaka"],
                "house_money_kr": house_kr,
                "advice": {
                    1: f"Du är upp {gain:.0%} men trend/flöden/värdering håller – rid vinnaren vidare, bevaka.",
                    2: f"Du är upp {gain:.0%} MED varningssignal. House money: sälj vinsten, behåll insatsen." + tax_note,
                    3: f"Du är upp {gain:.0%} och trenden är bruten – vinsten avdunstar. Överväg att sälja." + tax_note,
                }[level],
            })
    flags.sort(key=lambda f: (-f["level"], -(f.get("gain") or 0)))
    return flags


_UNIVERSE_CACHE: list = []


def universe() -> list:
    """
    Alla sökbara värdepapper appen känner till, för sök/filtrera vid innehav:
      · svenska börsbolag + börshandlade fonder (data/sweden_universe.csv m.fl.)
      · breda kärn-ETF:er (config.PORTFOLIO_CORE_ETF/PORTFOLIO_BROAD_ETFS)
      · rotationens region/tema-ETF:er (rotation_universe.csv)
    Returnerar [{ticker, name, sector, bucket}] sorterat på namn. Bucket är ett
    FÖRSLAG (broad/sweden/theme) så tillägg hamnar rätt hink direkt.
    """
    if _UNIVERSE_CACHE:
        return _UNIVERSE_CACHE
    out = {}

    def add(ticker, name, sector, bucket):
        tk = (ticker or "").strip().upper()
        if not tk or tk in out:
            return
        out[tk] = {"ticker": tk, "name": (name or tk).strip(),
                   "sector": (sector or "").strip(), "bucket": bucket}

    # Breda kärn-ETF:er först (så de rankas som broad även om de dyker upp nedan).
    core = getattr(config, "PORTFOLIO_CORE_ETF", None)
    if core:
        add(core[0], core[1], "Global", "broad")
    for lbl, tk in getattr(config, "PORTFOLIO_BROAD_ETFS", {}).items():
        add(tk, lbl, "Bred", "broad")

    # Svenska universumet (bolag + börsfonder) via den förbyggda CSV:n.
    try:
        from data.data_loader import load_sweden_universe
        tickers, sector_map, _cap, name_map = load_sweden_universe()
        for tk in tickers:
            add(tk, name_map.get(tk), sector_map.get(tk), "sweden")
    except Exception:  # noqa: BLE001 – universum-fil saknas → hoppa svenska delen
        pass

    # Rotationens region/tema-ETF:er.
    uf = Path(__file__).parent / getattr(config, "ETF_ROT_UNIVERSE_FILE", "")
    if getattr(config, "ETF_ROT_UNIVERSE_FILE", "") and uf.exists():
        try:
            for r in csv.DictReader(open(uf, encoding="utf-8")):
                kind = (r.get("kind") or "").strip()
                bucket = "theme" if kind == "theme" else "broad"
                add(r.get("ticker"), r.get("name"), r.get("group"), bucket)
        except Exception:  # noqa: BLE001
            pass

    _UNIVERSE_CACHE.extend(sorted(out.values(), key=lambda x: x["name"].lower()))
    return _UNIVERSE_CACHE


def _safe(fn, default, label):
    """Kör fn(); returnera default + logga vid fel så EN trasig delkomponent
    (opportunist/säljvakt/sammanvägd rank) inte sänker hela Nästa köp-kortet."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"[portfolio] Nästa köp: '{label}' misslyckades: {e}")
        traceback.print_exc()
        return default


_NEXTBUY_CACHE: dict = {}


def _data_mtime() -> float:
    """Senaste ändringstid bland alla filer Nästa köp läser. Datan skrivs nattligt
    (kl 02) + när du sparar innehav – så länge inget ändrats är resultatet
    identiskt och kan cachas i stället för att räknas om vid varje appstart.

    MÅSTE inkludera ALLT som påverkar svaret – annars serveras en inaktuell
    plan. Två poster lades till i efterhand efter en verklig bugg: modellvals-
    filen (utan den gjorde ett modellbyte i appen INGENTING – cache-nyckeln
    ändrades inte, gamla planen serverades) och value_shortlist.csv (ny
    Buffett-data invaliderade inte cachen)."""
    paths = [holdings_path(), target_path(), _model_file()]
    for seg in config.SEGMENTS.values():
        rd = Path(seg.get("results_dir", ""))
        for f in ("signals.csv", "quality_shortlist.csv", "quant_shortlist.csv",
                  "value_shortlist.csv", "mfn_events.csv", "soft_signals.csv",
                  "flow_snapshot.csv", "prices.csv", "portfolio.csv",
                  "etf_rotation.csv", "etf_rotation_meta.json"):
            paths.append(rd / f)
    m = 0.0
    for p in paths:
        try:
            m = max(m, p.stat().st_mtime)
        except OSError:
            pass
    return m


def _log_sweden_picks(picks: list) -> None:
    """Punkt-i-tid-logg av 'Nästa köp'-Sverige-rekommendationerna (sammanvägd rank),
    en rad per dag. Ingen befintlig fil har detta – _unified_rank() läser bara
    DAGENS snapshot-CSV:er (quality/quant är inte historiskt loggade), så en
    riktig IC/hit-rate-validering av just DESSA rekommendationer (så som
    tune_case_tracker.py gör för caseförändringar) kräver att vi först bygger
    upp historik framåt. Loggas max en gång per kalenderdag (näst-köp cachas
    ändå bara om per (belopp, data_mtime), så detta körs sällan)."""
    log_path = _results_dir() / "sweden_picks_history.csv"
    from datetime import date
    today = date.today().isoformat()
    if log_path.exists():
        try:
            last = log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
            if last.startswith(today + ","):
                return
        except OSError:
            pass
    write_header = not log_path.exists()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "ticker", "name", "score", "note"])
        for p in picks:
            w.writerow([today, p.get("ticker"), p.get("name"), p.get("score"), p.get("note")])


def _clamp01(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.5


def _ta_confirm(ticker) -> float:
    """TA-timing i [0,1] för en ticker ur flödesdatan (samma signaler som
    _opportunity/säljvakten använder): CMF 13v ≥ 0 (inflöden) och kurs ≥ SMA20
    (intakt trend) → nära 1; utflöden + trendbrott → nära 0. 0.5 = neutral/okänd.
    Detta är TA:s AVSIKTLIGA roll – timing, inte rankningsvikt."""
    fl = _load_flows().get((ticker or "").upper(), {})
    score = 0.5
    try:
        cmf = float(fl.get("cmf_13w"))
        score += 0.25 if cmf >= 0 else -0.25
    except (TypeError, ValueError):
        pass
    below = str(fl.get("below_sma20"))
    if below == "1":
        score -= 0.25
    elif below == "0":
        score += 0.25
    return _clamp01(score)


def _bucket_attractiveness(rows, model, risk_on) -> dict:
    """Attraktivitets-poäng i [0,1] per hink för NÄSTA krona – hur bra är det
    bästa tillgängliga köpet där just nu (framåtblickande).

      · broad (kärnan): en REGIM-baserad baslinje. Kärnan är den evidensbackade
        defaulten → mer attraktiv i svag marknad (bear), mindre i stark (bull)
        där satelliterna får mer utrymme att förtjäna kapital.
      · sweden: 70% AKTIV modells rank-score för bästa svenska aktien + 30%
        (snitt av de ANDRA modellernas rank + TA-timing) – så andra modeller och
        teknisk timing ges lite inflytande (config DYNAMIC_ALLOC_MODEL_WEIGHT).
        Ingen kvalificerad kandidat (t.ex. tom buffett-grind) → 0 = ingen tilt.
      · theme: rotationsstyrka gate:ad på risk-on-regim (+ TA). Rotationen slog
        aldrig index netto → hålls modest, aldrig kärnersättare.
      · leverage: 0 (målvikt 0, tiltas aldrig mot).
    """
    regime_base = {True: 0.45, False: 0.68, None: 0.55}.get(risk_on, 0.55)
    attr = {"broad": regime_base, "sweden": 0.0, "theme": 0.0, "leverage": 0.0}

    mw = float(getattr(config, "DYNAMIC_ALLOC_MODEL_WEIGHT", 0.70))
    active = _safe(lambda: _unified_rank(rows, top_n=1, model=model), [], "attraktivitet aktiv")
    if active:
        s_active = _clamp01(active[0].get("score"))
        others = [m for m in _MODEL_WEIGHTS if m != model]
        oscores = []
        for m in others:
            p = _safe(lambda m=m: _unified_rank(rows, top_n=1, model=m), [], "attraktivitet övrig")
            if p:
                oscores.append(_clamp01(p[0].get("score")))
        s_other = (sum(oscores) / len(oscores)) if oscores else s_active
        ta = _ta_confirm(active[0].get("ticker"))
        attr["sweden"] = _clamp01(mw * s_active + (1 - mw) * (0.5 * s_other + 0.5 * ta))

    if risk_on:                    # tema bara relevant i risk-on (annars 0)
        cands = _safe(_candidates, {"theme": []}, "attraktivitet tema")
        tpick = (cands.get("theme") or [None])[0]
        if tpick:
            attr["theme"] = _clamp01(0.5 * 0.55 + 0.5 * _ta_confirm(tpick.get("ticker")) + 0.1)
    return attr


def _dynamic_fill_split(bucket_vals, amount, targets, attr, meta_out=None):
    """Fyll-mot-mål (bas) + BUNDEN, attraktivitets-driven tilt + KÄRNGOLV.

    Basen är _fill_split (framåtblickande mot målvikten). Ovanpå den får
    satelliter som är MER attraktiva än kärnans baslinje dra en TAKAD andel av
    insättningen från kärnan, proportionellt mot hur mycket mer attraktiva de
    är. Kärngolvet skyddar den evidensbackade kärnan. Slår inget satelliterna
    kärnan (attraktivitet ≤ kärnans) → ingen tilt, målvikten avgör (tiebreaker).

    STRENGTH 0 → returnerar EXAKT _fill_split (bevisat identiskt) – en säker
    reträtt och regressionsgaranti."""
    base = _fill_split(bucket_vals, amount, targets)
    strength = float(getattr(config, "DYNAMIC_ALLOC_TILT_STRENGTH", 0.0) or 0.0)
    if strength <= 0 or amount <= 0 or not attr:
        return base
    core_attr = attr.get("broad", 0.55)
    # Tilta ALDRIG mot en hink användaren satt målvikt 0 på – den bundna tilten
    # omfördelar INOM den valda strategin och får inte återinföra en hink som
    # uttryckligen valts bort (verifierat fel innan: mål sweden=0 men attraktiv
    # aktie → 16% av insättningen gick ändå till sweden).
    excess = {b: (max(0.0, attr.get(b, 0.0) - core_attr)
                  if float(targets.get(b, 0.0) or 0.0) > 0 else 0.0)
              for b in ("sweden", "theme")}
    esum = sum(excess.values())
    if esum <= 0:                    # inget slår kärnan → mål-gap styr (tiebreaker)
        return base
    max_share = float(getattr(config, "DYNAMIC_ALLOC_MAX_SHARE", 0.40))
    floor_share = float(getattr(config, "DYNAMIC_ALLOC_CORE_FLOOR", 0.30))
    # Hur stor andel som får divergera mot satelliterna: skalas av tilt-styrkan
    # och av hur mycket mer attraktiva de är (esum), takad av max_share.
    tilt_frac = min(max_share, strength * min(1.0, esum))
    pull = amount * tilt_frac
    # Kärngolvet: kärnan behåller minst floor_share OM den är underviktad (har
    # mål-gap). Är kärnan redan på/över mål (base broad ~0) finns inget golv att
    # skydda – då tas tilten inte från kärnan (inget att ta) och basen står.
    core_base = base.get("broad", 0.0) + base.get("leverage", 0.0)
    core_floor = floor_share * amount if core_base > 0 else 0.0
    pull = min(pull, max(0.0, core_base - core_floor))
    if pull <= 0:
        return base
    final = dict(base)
    # dra från kärnan (broad; hävstångs-kronor räknas som kärna nedströms ändå)
    final["broad"] = final.get("broad", 0.0) - pull
    for b in ("sweden", "theme"):
        final[b] = final.get(b, 0.0) + pull * excess[b] / esum
    if meta_out is not None:
        meta_out.update({"tilt_frac": round(pull / amount, 4), "attr": {k: round(v, 3) for k, v in attr.items()},
                         "pulled_to": {b: round(pull * excess[b] / esum) for b in ("sweden", "theme") if excess[b] > 0}})
    return final


def next_buy(rows, amount=None) -> dict:
    """
    KÄRNAN ("Nästa köp"): ETT rangordnat, konkret svar på var nästa krona ska in.

    Hierarkin är evidensordningen från våra egna tester, inte tycke:
      1. BRED KÄRNA – en enda global fond. I varje netto-test vi kört (aktie-
         holdout, ETF-rotationens OOS-svep) slog den varje aktiv variant.
      2. SVERIGE-SATELLIT – modellens bästa kandidat. Ärligt stämplad OBEVISAD
         (holdouten var negativ); får bara den kapacitet målfördelningen ger.
      3. TEMA-SATELLIT – rotationens starkaste tema, bara i risk-on. Rotationen
         slog aldrig index netto → minsta hinken, aldrig kärnersättning.
    En satellit utan kandidat/regim-stöd skickar sina kronor till kärnan i
    stället – planen blir alltid ett komplett "så här placeras hela beloppet".
    """
    amount = float(amount or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000))

    # Cache: datan laddas nattligt (kl 02) + vid innehavssparning. Så länge inga
    # av filerna ändrats är svaret identiskt → räkna INTE om vid varje appstart.
    cache_key = (round(amount), _data_mtime())
    if cache_key in _NEXTBUY_CACHE:
        return _NEXTBUY_CACHE[cache_key]

    tgt = load_target()
    buckets = {b: 0.0 for b in BUCKETS}
    for r in rows:
        buckets[r["bucket"] if r["bucket"] in buckets else "theme"] += r.get("value", 0.0)

    core_tk, core_name = getattr(config, "PORTFOLIO_CORE_ETF",
                                 ("IUSQ.DE", "iShares MSCI ACWI (hela världen)"))
    risk_on = None
    try:
        meta = json.loads((_results_dir() / "etf_rotation_meta.json").read_text(encoding="utf-8"))
        risk_on = bool(meta.get("risk_on"))
    except Exception:  # noqa: BLE001 – rotation ej körd → gate:a inte på regim
        risk_on = None

    # Dynamisk, framåtblickande fördelning: fyll-mot-mål (bas) + bunden,
    # attraktivitets-driven tilt + kärngolv (se _dynamic_fill_split). Med
    # DYNAMIC_ALLOC_TILT_STRENGTH=0 blir detta EXAKT dagens _fill_split.
    model = _safe(active_model, "balanced", "aktiv modell")
    attr = _safe(lambda: _bucket_attractiveness(rows, model, risk_on), {}, "attraktivitet")
    tilt_meta: dict = {}
    plan = _dynamic_fill_split(buckets, amount, tgt, attr, meta_out=tilt_meta)

    cands = _safe(_candidates, {"sweden": [], "theme": []}, "kandidater")

    skipped = []
    # Min-köp: satellit-poster under denna gräns är inte värda courtage/spread →
    # viks in i kärnan denna månad (fyll-mot-mål bygger dem nästa månad).
    min_trade = float(getattr(config, "NEXT_BUY_MIN_TRADE_SEK", 500))
    broad_kr = plan.get("broad", 0.0) + plan.get("leverage", 0.0)  # hävstång (mål 0) → kärnan

    theme_kr = plan.get("theme", 0.0)
    theme_pick = (cands.get("theme") or [None])[0]
    if theme_kr > 0 and risk_on is False:
        skipped.append({"bucket": "theme", "reason": "risk-off i rotationens regim → kronorna går till kärnan"})
        broad_kr += theme_kr
        theme_kr = 0.0
    elif theme_kr > 0 and not theme_pick:
        skipped.append({"bucket": "theme", "reason": "ingen tema-signal → kronorna går till kärnan"})
        broad_kr += theme_kr
        theme_kr = 0.0
    elif 0 < theme_kr < min_trade:
        skipped.append({"bucket": "theme",
                        "reason": f"under min-köp ({min_trade:.0f} kr) → läggs på kärnan, byggs nästa månad"})
        broad_kr += theme_kr
        theme_kr = 0.0

    sweden_kr = plan.get("sweden", 0.0)
    # Sverige-slotten fylls av den SAMMANVÄGDA rankningen (viktprofil enligt
    # vald modell, portfölj-medveten). Fallbacken till de gamla per-modell-
    # kandidaterna (kvalitet + RENA MOMENTUM-picks) gäller BARA utanför
    # buffett-läget: i buffett är en tom rankning inte "data saknas" utan
    # grindens AVSIKTLIGA svar ("inget bolag klarar ROE/skuld-barren just nu →
    # håll disciplinen, kronorna går till kärnan") – att då punta på momentum-
    # kandidater vore att kringgå exakt den grind modellen finns för.
    sweden_picks = _safe(lambda: _unified_rank(rows, top_n=2), [], "sammanvägd rank")
    if not sweden_picks and model != "buffett":
        sweden_picks = (cands.get("sweden") or [])[:2]
    if sweden_kr > 0 and not sweden_picks:
        reason = ("inga bolag klarar Buffett-barren (ROE/skuld/värdering) just nu → "
                  "håll disciplinen, kronorna går till kärnan"
                  if model == "buffett" else
                  "inga svenska kandidater just nu → kronorna går till kärnan")
        skipped.append({"bucket": "sweden", "reason": reason})
        broad_kr += sweden_kr
        sweden_kr = 0.0
    elif 0 < sweden_kr < min_trade:
        skipped.append({"bucket": "sweden",
                        "reason": f"under min-köp ({min_trade:.0f} kr) → läggs på kärnan, byggs nästa månad"})
        broad_kr += sweden_kr
        sweden_kr = 0.0
    else:
        # Begränsa antal Sverige-poster så VARJE post ≥ min-köp (inga 60-kr-splittar).
        max_picks = max(1, int(sweden_kr // min_trade))
        sweden_picks = sweden_picks[:min(len(sweden_picks), max_picks)]

    if sweden_kr >= min_trade and sweden_picks:
        _safe(lambda: _log_sweden_picks(sweden_picks), None, "sverige-punkt-i-tid-logg")

    out_rows = []
    if broad_kr > 0.5:
        out_rows.append({
            "kr": round(broad_kr), "ticker": core_tk, "name": core_name, "bucket": "broad",
            "why": "Bred global kärna – slog varje aktiv variant netto i våra tester. Här byggs förmögenheten.",
            "evidence": "kärna",
        })
    if sweden_kr >= min_trade and sweden_picks:
        per = sweden_kr / len(sweden_picks)
        for c in sweden_picks:
            # source är "sammanvägd (<modell>)" sedan modellvalet infördes.
            unified = str(c.get("source") or "").startswith("sammanvägd")
            out_rows.append({
                "kr": round(per), "ticker": c.get("ticker"), "name": c.get("name"), "bucket": "sweden",
                "why": ((f"Bästa köp enligt ALLA modeller sammanvägt: {c.get('note')}. "
                         "Köp-och-behåll-vad – obevisat (holdout minus).") if unified else
                        f"Modellens bästa Sverige-kandidat ({c.get('note')}). Aktivt vad – obevisat (holdout minus)."),
                "evidence": "satellit",
            })
    if theme_kr >= min_trade and theme_pick:
        out_rows.append({
            "kr": round(theme_kr), "ticker": theme_pick.get("ticker"), "name": theme_pick.get("name"),
            "bucket": "theme",
            "why": f"Starkaste tema i rotationen ({theme_pick.get('note')}). Taktiskt – rotationen slår inte index netto.",
            "evidence": "satellit",
        })
    out_rows.sort(key=lambda r: -r["kr"])
    for i, r in enumerate(out_rows, 1):
        r["order"] = i

    total = sum(v for v in buckets.values())
    result = {
        "amount": round(amount),
        "risk_on": risk_on,
        "rows": out_rows,
        "best": (out_rows[0] if out_rows else None),   # DET enskilt bästa köpet just nu
        "opportunity": _safe(lambda: _opportunity(rows, amount), None, "opportunist"),
        "sell_watch": _safe(lambda: _takeprofit(rows), [], "säljvakt"),
        # OBS ordning: _takeprofit ovan uppdaterar fylla på-liggaren, så refill
        # beräknas EFTER den (dict-literaler evalueras uppifrån och ner).
        "refill": _safe(lambda: _refill_candidates(rows), [], "fyll på"),
        "isk": sum(r.get("value", 0.0) for r in rows) <= float(getattr(config, "PORTFOLIO_ISK_LIMIT", 300000)),
        "skipped": skipped,
        "tilt": (tilt_meta or None),   # dynamisk fördelning: hur mycket som tiltats mot satelliterna
        "buckets": {b: (round(buckets[b] / total, 4) if total else 0.0) for b in BUCKETS},
        "target": tgt,
        "has_holdings": bool(rows),
        "cash": _safe(load_cash, None, "montrose-kassa"),   # None om ingen Montrose-synk kört än
        "note": ("Köp och behåll: nya kronor fyller mot målet – ingen försäljning, ingen timing. "
                 "Enda sälj-regeln är säljvakten: innehav som rusat kraftigt ifrån index på kort tid "
                 "flaggas för att ta hem vinsten (behåll insatsen). Kärnan är evidensbackad; "
                 "satelliterna är aktiva vad som måste förtjäna sin plats i din framåt-logg."),
    }
    if len(_NEXTBUY_CACHE) > 8:
        _NEXTBUY_CACHE.clear()
    _NEXTBUY_CACHE[cache_key] = result
    return result


def _house_money(rows) -> list:
    """Per innehav med KÄND insats: sälj vinsten, behåll ursprungskapitalet. Kräver
    cost (insatt) < value. sell_frac = vinst/(1+vinst) → frigör exakt insatsen som cash."""
    out = []
    for r in rows:
        cost, val = r.get("cost"), r.get("value")
        if not cost or not val or val <= cost:
            continue
        gain = val / cost - 1.0
        reclaim = val - cost                          # vinsten = det du säljer för att låsa insatsen
        out.append({"name": r["name"], "ticker": r.get("ticker") or _resolve_ticker(r["name"]),
                    "cost": round(cost), "value": round(val), "gain": round(gain, 4),
                    "sell_sek": round(reclaim), "sell_frac": round(reclaim / val, 4),
                    "keep_sek": round(cost)})
    out.sort(key=lambda x: x["gain"], reverse=True)
    return out


def _riskon_plan(amount) -> dict:
    """RISK ON: strunta i mål-mixen, koncentrera nytt kapital i kandidatlistornas
    toppnamn (momentum + starkaste tema). Ingen riskberäkning – medveten edge-jakt."""
    cand = _candidates()
    picks = list(cand.get("sweden", []))[:4] + list(cand.get("theme", []))[:2]
    if not picks:
        return {"amount": amount, "picks": [],
                "warning": "Inga kandidater tillgängliga – kör screener/rotation först."}
    n = len(picks)
    # Konvex vikt: topnamnen får mest (n, n-1, …), normaliserat.
    weights = list(range(n, 0, -1))
    wsum = sum(weights)
    plan = []
    for w, c in zip(weights, picks):
        plan.append({"name": c.get("name"), "ticker": c.get("ticker"),
                     "source": c.get("source"), "note": c.get("note"),
                     "kr": round(amount * w / wsum)})
    return {"amount": amount, "picks": plan,
            "warning": ("RISK ON: koncentrerat, ingen riskberäkning, ingen bred kärna. "
                        "Kan gå väldigt fel – detta är edge-jakt, inte sparande.")}


# ── Backtest: "nästa köp" (fyll-mot-mål) mot index ────────────────────────────
# Ärlig fråga: "nästa köp" styr BARA vart nytt kapital går (säljer aldrig). Rätt
# jämförelse är därför SAMMA gamla bok, men varje ny krona i index istället. Vi visar
# också "allt om till index nu" som aggressiv referens (säljer allt → index idag).
# Buckets proxas av ETF:er: broad = korg av PORTFOLIO_BROAD_ETFS, sweden = småbolags-
# index, theme = likaviktad korg av tema-ETF:erna, index = ETF_ROT_BENCHMARK (ACWI).
# Hävstångs-sleeven proxas av broad-korgen; den får ändå aldrig nytt kapital (mål 0)
# och är identisk i båda strategierna → påverkar inte A-vs-index-domen.

def _fill_split(bucket_vals, amount, targets) -> dict:
    """Fördela `amount` mot målvikterna: allt till de underviktade hinkarna (gap),
    proportionellt. Om alla ligger på/över mål → fördela efter målvikt."""
    after = sum(bucket_vals.values()) + amount
    gaps = {b: max(0.0, targets.get(b, 0.0) * after - bucket_vals.get(b, 0.0)) for b in bucket_vals}
    gsum = sum(gaps.values())
    if gsum <= 0:
        tsum = sum(targets.get(b, 0.0) for b in bucket_vals) or 1.0
        return {b: amount * targets.get(b, 0.0) / tsum for b in bucket_vals}
    return {b: amount * g / gsum for b, g in gaps.items()}


def _irr_monthly(cfs):
    """Månads-IRR via bisektion (cfs = kassaflöden per månad, sista inkl. slutvärde)."""
    def npv(r):
        return sum(c / (1 + r) ** k for k, c in enumerate(cfs))
    lo, hi = -0.9, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _proxy_prices(months=None):
    """Prispanel (vecka × proxy) för hinkarna + index. Nät → körs på Pi:n."""
    import pandas as pd
    from data.data_loader import fetch_weekly_data
    broad = list(config.PORTFOLIO_BROAD_ETFS.values())
    theme = [t for t, k in _kinds().items() if k == "theme"]
    sweden = [config.SEGMENTS.get("small", {}).get("index_ticker", "XACT-SMABOLAG.ST")]
    index = [config.ETF_ROT_BENCHMARK]
    allt = sorted(set(broad + theme + sweden + index))
    data = fetch_weekly_data(allt, use_cache=True)
    close = {t: d["Close"] for t, d in data.items()
             if d is not None and not d["Close"].dropna().empty}
    px = pd.DataFrame(close).sort_index().ffill(limit=1)
    px.index = pd.to_datetime(px.index)

    def basket(tickers):
        cols = [t for t in tickers if t in px.columns]
        if not cols:
            return None
        sub = px[cols]
        norm = sub / sub.apply(lambda c: c[c.first_valid_index()] if c.first_valid_index() is not None else float("nan"))
        return norm.mean(axis=1)

    proxies = {"broad": basket(broad), "sweden": basket(sweden),
               "theme": basket(theme), "index": basket(index)}
    proxies["leverage"] = proxies["broad"]
    out = pd.DataFrame({k: v for k, v in proxies.items() if v is not None}).dropna()
    if months:
        out = out[out.index >= out.index[-1] - pd.DateOffset(months=months)]
    return out


def _dca_backtest(px, targets, start_book, monthly):
    """Simulerar månatliga insättningar på en prispanel. Returnerar värde-serier +
    sammanfattning för tre strategier med IDENTISK startbok (utom 'allt-in-index')."""
    idx = list(px.index)
    p0 = px.iloc[0]
    cols = [b for b in BUCKETS if b in px.columns]
    uA = {b: (start_book.get(b, 0.0) / p0[b] if p0.get(b, 0) else 0.0) for b in cols}
    uB_legacy = dict(uA)                      # index-för-nytt: samma gamla bok
    uB_index = 0.0
    V0 = float(sum(start_book.values()))
    uC_index = V0 / p0["index"] if p0.get("index", 0) else 0.0   # allt om till index nu
    valsA, valsB, valsC, contrib_months = [], [], [], 0
    prev_m = None
    for ts in idx:
        p = px.loc[ts]
        if prev_m is not None and (ts.year, ts.month) != prev_m:
            c = monthly
            contrib_months += 1
            split = _fill_split({b: uA[b] * p[b] for b in cols}, c, targets)
            for b, amt in split.items():
                if p.get(b, 0):
                    uA[b] += amt / p[b]
            if p.get("index", 0):
                uB_index += c / p["index"]
                uC_index += c / p["index"]
        prev_m = (ts.year, ts.month)
        valsA.append(sum(uA[b] * p[b] for b in cols))
        valsB.append(sum(uB_legacy[b] * p[b] for b in cols) + uB_index * p.get("index", 0))
        valsC.append(uC_index * p.get("index", 0))
    invested = V0 + monthly * contrib_months
    cfs = [-V0] + [-monthly] * contrib_months
    def summarize(vals):
        import pandas as pd
        s = pd.Series(vals, index=idx)
        final = float(s.iloc[-1])
        cf = list(cfs); cf[-1] = cf[-1] + final
        r = _irr_monthly(cf)
        maxdd = float((s / s.cummax() - 1).min())
        return {"final": final, "invested": invested,
                "irr_year": ((1 + r) ** 12 - 1) if r is not None else None,
                "maxdd": maxdd, "series": s}
    span_years = (idx[-1] - idx[0]).days / 365.25 if len(idx) > 1 else 0.0
    return {"A": summarize(valsA), "B": summarize(valsB), "C": summarize(valsC),
            "months": contrib_months, "years": span_years}


_BACKTEST_CACHE: dict = {}


def backtest_result(monthly=5000, months=None):
    """Ren beräkning (ingen print/IO förutom prispanelens egen cache) – används
    av både CLI:t (backtest()) och API:t. None om prisdata saknas (kräver nät,
    körs på Pi:n). Cachas per (belopp, fönster, data_mtime) – API:t ska ALDRIG
    räkna om vid varje sidladdning (se api/main.py:s princip: servern läser
    bara redan genererade resultat, kör inga backtester live)."""
    cache_key = (round(float(monthly)), months, _data_mtime())
    if cache_key in _BACKTEST_CACHE:
        return _BACKTEST_CACHE[cache_key]

    rows = load_holdings()
    start_book = {b: 0.0 for b in BUCKETS}
    for r in rows:
        start_book[r["bucket"] if r["bucket"] in start_book else "theme"] += r["value"]
    V0 = sum(start_book.values())
    try:
        px = _proxy_prices(months=months)
    except Exception as e:  # noqa: BLE001
        print(f"[backtest] kunde inte bygga prispanel: {e}\n  (kör på Pi:n – molnet saknar nät)")
        return None
    if px.empty or "index" not in px.columns or len(px) < 30:
        return None
    # Användarens SPARADE målvikter (load_target) – inte config-defaulten.
    # Annars backtestas en annan fördelning än den next_buy faktiskt kör med
    # så fort användaren justerat målet i appen.
    res = _dca_backtest(px, load_target(), start_book, monthly)
    from datetime import datetime
    out = {
        "start_value": round(V0), "monthly": monthly,
        "months": res["months"], "years": round(res["years"], 1),
        "generated": datetime.now().isoformat(timespec="seconds"),
    }
    for k in ("A", "B", "C"):
        s = res[k]
        out[k] = {
            "final": round(s["final"]), "invested": round(s["invested"]),
            "irr_year": (round(s["irr_year"], 4) if s["irr_year"] is not None else None),
            "maxdd": round(s["maxdd"], 4),
        }
    if len(_BACKTEST_CACHE) > 8:
        _BACKTEST_CACHE.clear()
    _BACKTEST_CACHE[cache_key] = out
    return out


def backtest(monthly=5000, months=None):
    out = backtest_result(monthly, months)
    if out is None:
        print("[backtest] för lite prisdata för proxyserierna – cachea ETF:erna först (kör på Pi:n).")
        return
    a, b, c = out["A"], out["B"], out["C"]
    print(f"\n  \"NÄSTA KÖP\" (fyll-mot-mål) MOT INDEX")
    print(f"  Startbok {out['start_value']:,.0f} kr · {out['monthly']:,.0f} kr/mån · {out['months']} insättningar "
          f"· {out['years']:.1f} år".replace(",", " "))
    print(f"  Totalt insatt: {a['invested']:,.0f} kr\n".replace(",", " "))
    def line(name, s):
        irr = f"{s['irr_year']:+.1%}" if s["irr_year"] is not None else "  n/a"
        print(f"   {name:<34}slutvärde {s['final']:>10,.0f} kr   IRR/år {irr:>7}   maxDD {s['maxdd']:>6.1%}"
              .replace(",", " "))
    line("A) Nästa köp → fyll mot mål", a)
    line("B) Nästa köp → allt i index", b)
    line("C) Sälj allt → index idag", c)
    print()
    da = a["final"] - b["final"]
    print(f"  A − B (allokeringens effekt på NYTT kapital): {da:>+10,.0f} kr "
          f"({da / b['final']:+.1%})".replace(",", " "))
    print("  A vs B isolerar det enda 'nästa köp' styr: vart nya pengar går (ingen försäljning).")
    print("  C är referens om du säljer om HELA boken till index idag (skatt/spread ej medräknat).")
    if da < 0:
        print("  → Att styra nytt kapital mot mål-mixen SLÅR INTE ren index-insättning här.")
    else:
        print("  → Fyll-mot-mål gav ett litet övertag mot ren index-insättning i perioden.")
    out_path = _results_dir() / "portfolio_backtest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Sparat: {out_path} (läses av /api/portfolio-backtest)")


# ── Modellval vs index (balanced/buffett/momentum) ─────────────────────────
# OVANSTÅENDE backtest()/backtest_result() testar bara HINK-fördelningen
# (fyll-mot-mål vs index) med breda ETF-korgar som proxy för Sverige-hinken –
# den simulerar ALDRIG vilka enskilda aktier _unified_rank faktiskt väljer,
# så den kan inte svara på "blev Buffett-läget bättre eller sämre än
# momentum/balanced". En RIKTIG bakåtblickande backtest av modellvalet är
# dessutom omöjlig: vi har bara DAGENS kvalitets-/kvant-/värde-poäng, ingen
# historik över hur de såg ut för N månader sedan (quality/quant-CSV:erna är
# ögonblicksbilder, inte tidsserier). Samma mönster som quality_screener.py:s
# snapshot/track/lookback (ärligt sätt att hantera en icke-backtestbar,
# diskretionär tratt): frys dagens plockningar PER MODELL med ingångskurs,
# jämför framåt när tid gått – plus en explicit ILLUSTRATIV bakåtblick för
# en omedelbar (men vetenskapligt ogiltig) fingervisning.

def _model_bench_ticker() -> str:
    return config.SEGMENTS.get("large", {}).get("index_ticker", "XACT-SVERIGE.ST")


def snapshot_model_picks(label: Optional[str] = None) -> None:
    """Fryser dagens topp-plockningar (unified_rank, AKTIV modell) med
    ingångskurs → results/model_picks_ledger.csv. Kör detta separat under
    varje modell (byt med set_active_model/frontend-väljaren mellan
    körningarna) för att bygga upp jämförbara snapshots. Kör 'track_model_picks'
    om några veckor/månader för det ärliga svaret."""
    import datetime
    from data.data_loader import fetch_weekly_data

    model = active_model()
    rows = load_holdings()
    ranked = _unified_rank(rows, top_n=5, model=model)
    if not ranked:
        print(f"[snapshot_model_picks] inga kandidater i '{model}'-läget just nu "
              "(t.ex. kan buffett-grinden ge tomt om inget bolag klarar ROE/skuld-barren) "
              "– inget att frysa. Det är i sig ett giltigt resultat: håll kapital i kärnan.")
        return
    bench = _model_bench_ticker()
    tickers = list(dict.fromkeys([r["ticker"] for r in ranked] + [bench]))
    data = fetch_weekly_data(tickers, use_cache=True)

    def last_close(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        return round(float(s.iloc[-1]), 4) if len(s) else None

    bench_px = last_close(bench)
    today = datetime.date.today().isoformat()
    label = label or today
    out_rows = []
    for r in ranked:
        px = last_close(r["ticker"])
        if px is None:
            continue
        out_rows.append({"snapshot": label, "date": today, "model": model,
                         "ticker": r["ticker"], "name": r["name"], "score": r["score"],
                         "entry_price": px, "bench_ticker": bench, "bench_entry": bench_px})
    if not out_rows:
        print("[snapshot_model_picks] inga ingångskurser (Yahoo?) – avbryter.")
        return
    ledger = _results_dir() / "model_picks_ledger.csv"
    exists = ledger.exists()
    with open(ledger, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        if not exists:
            w.writeheader()
        for row in out_rows:
            w.writerow(row)
    print(f"[snapshot_model_picks] '{model}'/'{label}': frös {len(out_rows)} plockningar @ {today} "
          f"(index {bench}) → {ledger}")
    print("  Byt modell och kör igen för att jämföra – kör 'track_model_picks' om några veckor/månader.")


def track_model_picks() -> None:
    """Läser model_picks_ledger.csv, visar avkastning PER MODELL vs index till
    dags dato (likaviktad, ingen ombalansering). Modellvalets riktiga scorecard –
    kräver att snapshot_model_picks körts minst en gång (helst under flera
    modeller, på samma eller olika dagar) för att ge något att jämföra."""
    import pandas as pd
    from data.data_loader import fetch_weekly_data

    ledger = _results_dir() / "model_picks_ledger.csv"
    if not ledger.exists():
        print("[track_model_picks] ingen ledger än – kör 'snapshot_model_picks' först "
              "(gärna under flera modeller för att kunna jämföra).")
        return
    led = pd.read_csv(ledger)
    tickers = list(dict.fromkeys(list(led["ticker"]) + list(led["bench_ticker"].dropna().unique())))
    data = fetch_weekly_data(tickers, use_cache=True)

    def cur(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        return float(s.iloc[-1]) if len(s) else None

    print("\n  MODELLVAL vs INDEX (framåt-spårning, likaviktad, ingen ombalansering)\n")
    for (model, label), g in led.groupby(["model", "snapshot"]):
        rets = [cur(r["ticker"]) / r["entry_price"] - 1
                for _, r in g.iterrows()
                if cur(r["ticker"]) and r["entry_price"]]
        if not rets:
            continue
        port = sum(rets) / len(rets)
        be = g["bench_entry"].dropna()
        bt = g["bench_ticker"].dropna()
        bench_ret = None
        if len(be) and len(bt):
            bc = cur(bt.iloc[0])
            if bc:
                bench_ret = bc / float(be.iloc[0]) - 1
        line = f"  {model:<10} {str(label):<12} {len(rets):>2} bolag   portfölj {port:+.1%}"
        if bench_ret is not None:
            line += f"   index {bench_ret:+.1%}   alfa {port - bench_ret:+.1%}"
        print(line)
    print("\n  (Enkel framåt-scorecard – ingen ombalansering. Fler snapshots över tid = mer robust,\n"
          "   och framför allt: fler DAGAR med snapshots under respektive modell, inte bara en.)")


def lookback_model_picks(months: int = 6) -> None:
    """ILLUSTRATIV bakåtblick (EJ giltig backtest): visar hur DAGENS topp-
    plockningar under VARJE modell (balanced/buffett/momentum) hade utvecklats
    de senaste `months` månaderna, sida vid sida med index. VARNING:
    look-ahead + survivorship – vi väljer dagens kandidater (rankade med
    DAGENS kvalitets-/kvant-/värde-data) och tittar bakåt, exakt samma
    begränsning som quality_screener.py:s lookback(). En snabb, grov
    fingervisning – inte bevis. Använd snapshot_model_picks/track_model_picks
    för det ärliga, framåtblickande testet."""
    import pandas as pd
    import datetime
    from data.data_loader import fetch_weekly_data

    rows = load_holdings()
    bench = _model_bench_ticker()
    per_model = {m: _unified_rank(rows, top_n=5, model=m) for m in _MODEL_WEIGHTS}
    if not any(per_model.values()):
        print("[lookback_model_picks] ingen modell gav några kandidater – kör "
              "quality_screener/quant_screener/value_screener på Pi:n först.")
        return
    all_tickers = {bench}
    for ranked in per_model.values():
        all_tickers.update(r["ticker"] for r in ranked)
    data = fetch_weekly_data(list(all_tickers), use_cache=True)
    cutoff = pd.Timestamp(datetime.date.today()) - pd.Timedelta(days=int(months * 30.4))

    def window(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        if s.empty:
            return None
        s.index = pd.to_datetime(s.index)
        past = s[s.index <= cutoff]
        p0 = float(past.iloc[-1]) if len(past) else float(s.iloc[0])
        p1 = float(s.iloc[-1])
        return p0, p1, (p1 / p0 - 1), len(past) > 0

    bw = window(bench)
    print(f"\n  BAKÅTBLICK {months}m – dagens topp-plockningar PER MODELL, likaviktad")
    print("  ⚠ EJ giltig backtest: look-ahead + survivorship (dagens kandidater rankade med DAGENS")
    print("  data, inte den historiska rankningen från för N månader sedan)\n")
    for model, ranked in per_model.items():
        if not ranked:
            print(f"  {model:<10} (inga kandidater just nu – t.ex. buffett-grinden gav tomt)")
            continue
        rets, short_hist = [], 0
        for r in ranked:
            w = window(r["ticker"])
            if not w:
                continue
            p0, p1, ret, full = w
            rets.append(ret)
            if not full:
                short_hist += 1
        if not rets:
            print(f"  {model:<10} (ingen kursdata)")
            continue
        port = sum(rets) / len(rets)
        line = f"  {model:<10} {len(rets)} bolag   snitt {port:+.1%}"
        if bw:
            line += f"   index {bw[2]:+.1%}   alfa {port - bw[2]:+.1%}"
        if short_hist:
            line += f"   ({short_hist} med kortare historik än {months}m)"
        print(line)
    print("\n  Enda ärliga testet: 'snapshot_model_picks' idag → 'track_model_picks' framåt.")


# ── Size in/out (trancher) ────────────────────────────────────────────────────
def size_in(amount, tranches=4, dip_step=0.05):
    """Dela ett köp i trancher istället för allt på en gång. Två scheman:
    LIKA (tidsbaserat) och DIP-VIKTAT (köp mer ju djupare fallet)."""
    tranches = max(1, int(tranches))
    equal = [{"steg": i + 1, "kr": round(amount / tranches),
              "trigger": ("nu" if i == 0 else f"om {i} perioder / vid −{i * dip_step:.0%}")}
             for i in range(tranches)]
    # Dip-viktat: vikter 1,2,3,… (mer kapital längre ned), triggat av allt djupare fall.
    w = list(range(1, tranches + 1))
    wsum = sum(w)
    dip = [{"steg": i + 1, "kr": round(amount * w[i] / wsum),
            "trigger": ("nu" if i == 0 else f"vid −{i * dip_step:.0%} från nu")}
           for i in range(tranches)]
    return {"amount": amount, "tranches": tranches, "equal": equal, "dip": dip}


# ── Exit-alarm: "END THIS NOW" (sektor svag OCH tekniskt brutet) ──────────────
def _sector_table():
    """results/sector_momentum.csv → {sektor_lower: {rank, total, mom13, mom26}}."""
    p = _results_dir() / "sector_momentum.csv"
    if not p.exists():
        return {}, 0
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    total = len(rows)
    out = {}
    for r in rows:
        def f(k):
            try:
                return float(r.get(k) or 0)
            except ValueError:
                return 0.0
        out[(r.get("sector") or "").lower()] = {
            "rank": int(float(r.get("rank") or 0)), "total": total,
            "mom13": f("momentum_13w"), "mom26": f("momentum_26w")}
    return out, total


def _sector_weak(sector, table, total):
    """Svag sektor = LÅGT RANKAD (nedre ~40%) OCH icke-positiv 13v-trend. Kräver båda:
    en sektor som ligger lågt men fortfarande STIGER (positiv 13v) räknas inte som svag."""
    if not sector or not table:
        return None, ""
    sl = sector.lower()
    hit = table.get(sl)
    if hit is None:                                   # fuzzy: dela ord (GICS-namn ≠ modellens)
        for k, v in table.items():
            if k and (k in sl or sl in k or k.split()[0] == sl.split()[0]):
                hit = v
                break
    if hit is None:
        return None, ""
    low_rank = bool(total and hit["rank"] > 0.6 * total)
    weak = low_rank and hit["mom13"] <= 0
    note = f"sektor {sector}: rank {hit['rank']}/{total}, 13v {hit['mom13']:+.1%}"
    return weak, note


def _tech_signal(close):
    """Tekniskt brutet = under 40v-MA och fallande momentum. 'strong' = djupt under MA."""
    import pandas as pd
    c = close.dropna()
    if len(c) < 45:
        return None
    ma40 = c.rolling(40).mean().iloc[-1]
    price = c.iloc[-1]
    mom13 = price / c.iloc[-14] - 1 if len(c) > 14 else 0.0
    mom26 = price / c.iloc[-27] - 1 if len(c) > 27 else 0.0
    below = bool(price < ma40)
    broken = below and mom13 < 0
    strong = below and price < 0.90 * ma40 and mom13 < 0 and mom26 < 0
    return {"price": round(float(price), 2), "ma40": round(float(ma40), 2),
            "below_ma": below, "mom13": round(float(mom13), 4), "mom26": round(float(mom26), 4),
            "broken": broken, "strong": strong,
            "note": f"{'under' if below else 'över'} 40v-MA · 13v {mom13:+.1%} · 26v {mom26:+.1%}"}


def exitscan():
    """Skannar innehaven: flaggar RÖTT ('end this now') när sektorn är svag OCH kursen
    tekniskt brutet, GULT när en av dem slår till. Skriver results/exit_signals.json.
    Kräver prisdata (körs på Pi:n). Körs numera automatiskt varje natt via
    main.py:s portfölj-uppdateringsblock (tidigare bara CLI, aldrig
    schemalagd – exit_signals.json kunde bli stale utan att någon märkte
    det) – fortfarande körbar manuellt (`python portfolio.py exitscan`) för
    en direktuppdatering mellan nattkörningarna."""
    import json as _json
    from datetime import datetime, timezone
    rows = load_holdings()
    if not rows:
        print("[exitscan] inga innehav.")
        return
    resolved = []
    for r in rows:
        tk = (r.get("ticker") or _resolve_ticker(r["name"])).upper()
        resolved.append((r, tk))
    tickers = sorted({tk for _, tk in resolved if tk})
    prices = {}
    if tickers:
        try:
            from data.data_loader import fetch_weekly_data
            data = fetch_weekly_data(tickers, use_cache=True)
            prices = {t: d["Close"] for t, d in data.items()
                      if d is not None and not d["Close"].dropna().empty}
        except Exception as e:  # noqa: BLE001
            print(f"[exitscan] kunde inte hämta priser: {e} (kör på Pi:n)")
    table, total = _sector_table()
    out = []
    for r, tk in resolved:
        sec = _sector_of(tk) if tk else ""
        weak, snote = _sector_weak(sec, table, total)
        tech = _tech_signal(prices[tk]) if tk in prices else None
        broken = bool(tech and tech["broken"])
        strong = bool(tech and tech["strong"])
        if broken and weak:
            tier = "red"
        elif (broken and sec == "") and strong:       # ETF utan sektor: djupt tekniskt brott
            tier = "red"
        elif broken or weak:
            tier = "amber"
        elif tk and tech is None:
            tier = "unknown"
        else:
            tier = "ok"
        out.append({"name": r["name"], "ticker": tk, "bucket": r.get("bucket"),
                    "sector": sec, "tier": tier,
                    "sector_note": snote, "tech_note": (tech["note"] if tech else "ingen prisdata")})
    order = {"red": 0, "amber": 1, "unknown": 2, "ok": 3}
    out.sort(key=lambda x: order.get(x["tier"], 9))
    res = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "holdings": out}
    p = _results_dir() / "exit_signals.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(res, ensure_ascii=False))
    reds = [o for o in out if o["tier"] == "red"]
    ambers = [o for o in out if o["tier"] == "amber"]
    print(f"[exitscan] {len(out)} innehav · {len(reds)} RÖDA (end this now) · {len(ambers)} gula → {p}")
    for o in reds:
        print(f"   🔴 {o['name']:<24} {o['ticker']:<12} {o['tech_note']} | {o['sector_note']}")
    for o in ambers:
        print(f"   🟡 {o['name']:<24} {o['ticker']:<12} {o['tech_note']} | {o['sector_note']}")


def _write_json(data):
    out = _results_dir() / "portfolio_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False))


def analyze():
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in i appen eller cache/portfolio_holdings.csv")
        return
    d = compute(rows)
    print(f"\n  PORTFÖLJ – {d['total']:,.0f} kr, {len(rows)} innehav\n".replace(",", " "))
    print(f"  {'Hink':<26}{'nu':>8}{'mål':>8}{'diff':>8}")
    for b in BUCKETS:
        cur, tgt = d["buckets"][b], d["target"].get(b, 0.0)
        print(f"  {BUCKET_LABEL[b]:<26}{cur:>7.0%}{tgt:>8.0%}{cur - tgt:>+8.0%}")
    print("\n  Varningar:")
    for w in d["warnings"]:
        print(f"   ⚠ {w}")
    _write_json(d)


def newcapital(amount):
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in dem först.")
        return
    d = compute(rows, amount=amount)
    print(f"\n  NYTT KAPITAL: {amount:,.0f} kr → fyll mot målet (ingen försäljning)\n".replace(",", " "))
    for b, kr in sorted(d["newcapital"]["plan"].items(), key=lambda x: -x[1]):
        print(f"   {BUCKET_LABEL[b]:<26}{kr:>10,.0f} kr   ({kr/amount:.0%})".replace(",", " "))
    for lbl, e in d["newcapital"]["broad_etfs"].items():
        print(f"     {lbl:<20}{e['ticker']:<10}{e['kr']:>9,.0f} kr".replace(",", " "))
    _write_json(d)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if cmd == "analyze":
        analyze()
    elif cmd == "newcapital":
        newcapital(float(sys.argv[2]) if len(sys.argv) > 2 else 10000)
    elif cmd == "backtest":
        monthly = float(sys.argv[2]) if len(sys.argv) > 2 else 5000
        months = int(sys.argv[3]) if len(sys.argv) > 3 else None
        backtest(monthly, months)
    elif cmd == "exitscan":
        exitscan()
    elif cmd == "snapshot_model":
        snapshot_model_picks(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "track_model":
        track_model_picks()
    elif cmd == "lookback_model":
        lookback_model_picks(int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    elif cmd == "quotes":
        fetch_holding_quotes()
    elif cmd == "sizein":
        amt = float(sys.argv[2]) if len(sys.argv) > 2 else 10000
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        d = size_in(amt, n)
        print(f"\n  SIZE IN: {amt:,.0f} kr i {n} trancher\n".replace(",", " "))
        print("  Lika (tidsbaserat):")
        for t in d["equal"]:
            print(f"   {t['steg']}. {t['kr']:>8,.0f} kr   {t['trigger']}".replace(",", " "))
        print("  Dip-viktat (mer ju djupare fall):")
        for t in d["dip"]:
            print(f"   {t['steg']}. {t['kr']:>8,.0f} kr   {t['trigger']}".replace(",", " "))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
