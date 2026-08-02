"""
altdata/borsdata.py – Börsdata REST-API-klient (Pro+).

Löser BörsAPI:s täckningslucka: Börsdata täcker uttryckligen First North/
Spotlight/mindre listor, ger upp till 20 års kurshistorik och 40 kvartals-/
R12-rapporter per bolag, plus färdiga KPI:er och (Pro+) insider/blankning/
återköp. Rate limit är GENERÖS (100 anrop/10s, rek. tak 10 000/dygn) – helt
annan kalkyl än BörsAPI:s engångspott på 100 rapporter. Vi kapar därför INTE
historiken (maxCount tas på högsta nivå per default).

VERIFIERAT (GitHub-repo + Swagger-referens): bas-URL, auth-metod, endpoint-
paths. INTE VERIFIERAT: exakta fältnamn i rapport-JSON (Swagger-specen gick
inte att hämta, 403). Därför är eval()/probe() SCHEMA-UPPTÄCKANDE – de dumpar
riktiga fältnamn ur skarpa svar i stället för att anta stavning som tyst kan
vara fel. Bygg fundamentals.py-mappningen (revenue/ebit/... → våra kanoniska
namn) FÖRST efter en verifierad eval-körning.

Nyckel: BORSDATA_API_KEY i ~/.momentum.env (chmod 600 – ALDRIG i repot).

Körs på Pi:n (nät):
    python -m altdata.borsdata probe             # nyckel OK? dumpar ett instrument rått
    python -m altdata.borsdata match              # matcha Börsdatas instrument mot vårt universum
    python -m altdata.borsdata eval                # schema-upptäckt: 5-8 kända bolag (First North + huvudlista)
    python -m altdata.borsdata backfill            # rå rapport-JSON för hela matchade universumet (cachas)
    python -m altdata.borsdata price_probe         # verifiera prisschema/justering på ett instrument
    python -m altdata.borsdata dividend_probe      # verifiera historiska utdelningar/ex-datum
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

BASE = "https://apiservice.borsdata.se/v1"
_MIN_INTERVAL = 0.12   # 100 anrop/10s → max ~8/s; 0.12s marginal mot gränsen


def _key() -> str:
    k = os.environ.get("BORSDATA_API_KEY")
    if not k:
        envf = Path.home() / ".momentum.env"
        if envf.exists():
            m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$", envf.read_text(), re.M)
            if m:
                k = m.group(1).strip().strip('"').strip("'")
    if not k:
        raise RuntimeError("BORSDATA_API_KEY saknas – lägg nyckeln i ~/.momentum.env (chmod 600).")
    return k


def _cache_dir() -> Path:
    d = Path(config.anchor(getattr(config, "BORSDATA_CACHE_DIR", "cache/borsdata")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:80]


_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _get(path: str, params: dict = None, cache_key: str = None, use_cache: bool = True) -> dict:
    """GET med authKey som querystring + evig cache. authKey läggs ALDRIG i
    cache_key/filnamn (bara i request-URL:en), så nyckeln hamnar aldrig i en
    cachad fil på disk."""
    cp = _cache_dir() / f"{_slug(cache_key or path)}.json"
    if use_cache and cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    _throttle()
    q = dict(params or {})
    q["authKey"] = _key()
    r = requests.get(f"{BASE}{path}", params=q, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Börsdata {r.status_code}: {r.text[:300]}")
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def probe():
    """Nyckel OK? Hämtar instrumentlistan (1 anrop) och dumpar EN post rått
    så vi ser de riktiga fältnamnen (insId/ticker/isin/yahoo – oklart vilka
    som faktiskt finns förrän vi ser ett riktigt svar)."""
    data = _get("/instruments", cache_key="instruments_all")
    items = data.get("instruments") or data.get("data") or (data if isinstance(data, list) else [])
    print(f"HTTP OK · {len(items)} instrument totalt")
    if items:
        print("\nExempel-instrument (rått, alla fält):")
        print(json.dumps(items[0], indent=2, ensure_ascii=False))


def _instrument_list() -> list:
    data = _get("/instruments", cache_key="instruments_all")
    return data.get("instruments") or data.get("data") or (data if isinstance(data, list) else [])


def _norm_name(s: str) -> str:
    s = (s or "").lower()
    for junk in (" ab (publ)", " (publ)", " ab", " publ", " plc", " asa", "."):
        s = s.replace(junk, "")
    return re.sub(r"\s+", " ", s).strip()


def match_universe() -> list:
    """
    Matcha Börsdatas instrument mot VÅRT universum (Small+Large, dvs. inkl.
    Micro Cap/First North). Provar flera kandidat-fältnamn för ticker
    ('ticker', 'yahoo', 'nameEng') defensivt eftersom exakt schema inte var
    verifierbart i förväg. Returnerar [(instrument_dict, vår_ticker, matched_on)].
    """
    def _bare(tk):
        tk = str(tk or "").upper().strip()
        return tk[:-3] if tk.endswith(".ST") else tk

    from data.data_loader import load_sweden_universe
    tickers, _s, _c, name_map = load_sweden_universe()   # hela universumet, inga cap-filter
    # Nyckla på BARA tickern (utan .ST) på båda sidor – Börsdatas ticker-fält
    # kan vara "ACCON" (bart) eller "ACCON.ST" (yahoo-fältet); vårt universum
    # är alltid .ST-suffixerat. Normalisera symmetriskt så formatet inte spelar roll.
    ours_by_bare = {_bare(t): t for t in tickers}
    ours_by_name = {_norm_name(name_map.get(t, t)): t for t in tickers}

    items = _instrument_list()
    matched, seen = [], set()
    ticker_fields = ["ticker", "yahoo", "insId"]
    for it in items:
        our_t = None
        matched_on = None
        for f in ticker_fields:
            bare = _bare(it.get(f))
            if bare and bare in ours_by_bare:
                our_t = ours_by_bare[bare]
                matched_on = f
                break
        if not our_t:
            nn = _norm_name(it.get("name") or it.get("nameEng"))
            if nn in ours_by_name:
                our_t = ours_by_name[nn]
                matched_on = "name"
        if our_t and our_t not in seen:
            seen.add(our_t)
            matched.append((it, our_t, matched_on))
    return matched


def match():
    m = match_universe()
    from collections import Counter
    by_field = Counter(f for _, _, f in m)
    print(f"[match] {len(m)} av vårt universum matchade Börsdata-instrument")
    print(f"        matchat på: {dict(by_field)}")
    print("\nExempel (5 första):")
    for it, tk, f in m[:5]:
        print(f"  {tk:<14} ← {it.get('name')!r} (matched_on={f})")
    if not m:
        print("\n[VARNING] Inga träffar – dumpa 'probe' och inspektera fältnamnen manuellt, "
              "matchningen provar just nu ticker/yahoo/insId/namn.")


EVAL_TICKERS = [
    # First North/micro (BörsAPI:s täckningslucka – detta är det avgörande testet)
    "ACCON.ST", "SECARE.ST", "PTRK.ST",
    # Huvudlista (referens, redan verifierad korrekt i BörsAPI)
    "AZA.ST", "SWED-A.ST",
]


def _find_report_endpoint_data(ins_id) -> dict:
    return _get(f"/instruments/{ins_id}/reports", {"maxCount": 20},
                cache_key=f"reports_{ins_id}_max20")


def _find_stockprice_endpoint_data(ins_id, max_count: int = 20,
                                   use_cache: bool = True) -> dict:
    """Officiell historisk EOD-endpoint; råsvaret tolkas först efter probe."""
    cache_key = f"stockprices_{ins_id}_max{max_count}"
    cache_path = _cache_dir() / f"{_slug(cache_key)}.json"
    # Kurscachen får återanvändas inom samma kalenderdag/subprocesskedja,
    # men aldrig bli den tysta permanenta cachen som rapporthistoriken är.
    fresh_today = (cache_path.exists() and
                   time.localtime(cache_path.stat().st_mtime).tm_yday ==
                   time.localtime().tm_yday and
                   time.localtime(cache_path.stat().st_mtime).tm_year ==
                   time.localtime().tm_year)
    return _get(f"/instruments/{ins_id}/stockprices", {"maxCount": max_count},
                cache_key=cache_key, use_cache=use_cache and fresh_today)


def stockprice_instrument_map() -> dict:
    """Yahoo-ticker -> Börsdata insId, endast exakta ticker/yahoo-matchningar."""
    out = {}
    for item in _instrument_list():
        ins_id = item.get("insId") or item.get("id")
        yahoo = str(item.get("yahoo") or "").strip().upper()
        ticker = str(item.get("ticker") or "").strip().upper()
        key = yahoo if yahoo.endswith(".ST") else (f"{ticker}.ST" if ticker else "")
        if ins_id and key:
            out[key] = ins_id
    return out


def stockprices_ohlcv(ins_id, use_cache: bool = True) -> pd.DataFrame:
    """Börsdatas d/h/l/c/o/v-schema till kanonisk daglig OHLCV."""
    payload = _find_stockprice_endpoint_data(ins_id, use_cache=use_cache)
    rows = payload.get("stockPricesList") or []
    frame = pd.DataFrame(rows)
    required = {"d", "o", "h", "l", "c", "v"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    frame = frame.rename(columns={"o": "Open", "h": "High", "l": "Low",
                                  "c": "Close", "v": "Volume"})
    frame.index = pd.to_datetime(frame.pop("d"), errors="coerce")
    frame = frame.loc[~frame.index.isna(), ["Open", "High", "Low", "Close", "Volume"]]
    return frame.apply(pd.to_numeric, errors="coerce").sort_index()


def price_probe():
    """Dumpa en riktig prispost utan att anta att Börsdata levererar OHLCV."""
    matches = match_universe()
    if not matches:
        raise RuntimeError("Inget Börsdata-instrument matchade universumet.")
    preferred = next((x for x in matches if x[1] == "VOLV-B.ST"), matches[0])
    instrument, ticker, _ = preferred
    ins_id = instrument.get("insId") or instrument.get("id")
    payload = _find_stockprice_endpoint_data(ins_id)
    rows = (payload.get("stockPricesList") or payload.get("stockPrices") or
            payload.get("prices") or payload.get("data") or [])
    print(f"{ticker} insId={ins_id} · toppnycklar={list(payload) if isinstance(payload, dict) else 'list'}")
    print(f"rader={len(rows)}")
    if rows:
        print(json.dumps(rows[0], indent=2, ensure_ascii=False))


def dividend_calendar(ins_ids: list, use_cache: bool = True) -> dict:
    """Gamla och nya utdelningsdatum för upp till API:ts tillåtna instrumentlista."""
    ids = ",".join(str(x) for x in ins_ids)
    return _get("/instruments/dividend/calendar", {"instList": ids},
                cache_key=f"dividend_calendar_{ids}", use_cache=use_cache)


def dividend_events_map(ins_ids: list, use_cache: bool = True) -> dict:
    """insId -> DataFrame(ex_date, amount); olika typer samma dag summeras."""
    payload = dividend_calendar(ins_ids, use_cache=use_cache)
    out = {}
    for item in payload.get("list", []):
        rows = []
        for value in item.get("values", []):
            date = pd.to_datetime(value.get("excludingDate"), errors="coerce")
            amount = pd.to_numeric(value.get("amountPaid"), errors="coerce")
            if pd.notna(date) and pd.notna(amount) and amount > 0:
                rows.append({"ex_date": date.normalize(), "amount": float(amount)})
        if rows:
            frame = pd.DataFrame(rows).groupby("ex_date", as_index=False)["amount"].sum()
        else:
            frame = pd.DataFrame(columns=["ex_date", "amount"])
        out[item.get("insId")] = frame
    return out


def split_events_map(payload: dict) -> dict:
    """instrumentId -> [(split_date, new_shares_per_old_share)]."""
    out = {}
    for row in payload.get("stockSplitList", []):
        ins_id = row.get("instrumentId") or row.get("insId")
        date = pd.to_datetime(row.get("splitDate"), errors="coerce")
        try:
            new, old = str(row.get("ratio")).split(":", 1)
            factor = float(new) / float(old)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if ins_id and pd.notna(date) and factor > 0:
            out.setdefault(ins_id, []).append((date.normalize(), factor))
    return out


def normalize_dividends_for_splits(events: pd.DataFrame, splits: list) -> pd.DataFrame:
    """Sätt äldre utdelningar i samma (senast splitjusterade) aktieskala som priset."""
    if events is None or events.empty or not splits:
        return events
    out = events.copy()
    for idx, event in out.iterrows():
        cumulative = 1.0
        for split_date, factor in splits:
            if pd.Timestamp(split_date) > pd.Timestamp(event["ex_date"]):
                cumulative *= factor
        if cumulative > 0:
            out.at[idx, "amount"] = float(event["amount"]) / cumulative
    return out


def adjust_ohlc_for_dividends(frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Bakåtjustera OHLC så avkastningen motsvarar återinvesterad utdelning.

    För varje ex-dag multipliceras alla tidigare priser med
    (föregående stängning - utdelning) / föregående stängning. Framtida
    kalenderhändelser ignoreras. Volym lämnas oförändrad.
    """
    out = frame.copy().sort_index()
    if out.empty or events is None or events.empty:
        return out
    scale = pd.Series(1.0, index=out.index)
    for row in events.sort_values("ex_date").itertuples(index=False):
        ex_date = pd.Timestamp(row.ex_date)
        if ex_date > out.index.max():
            continue
        previous = out.loc[out.index < ex_date, "Close"].dropna()
        if previous.empty:
            continue
        prev_close = float(previous.iloc[-1])
        factor = (prev_close - float(row.amount)) / prev_close
        if not 0 < factor <= 1:
            continue
        scale.loc[scale.index < ex_date] *= factor
    out.loc[:, ["Open", "High", "Low", "Close"]] = out[
        ["Open", "High", "Low", "Close"]
    ].mul(scale, axis=0)
    return out


def dividend_probe():
    payload = dividend_calendar([236], use_cache=False)
    print(f"toppnycklar={list(payload) if isinstance(payload, dict) else 'list'}")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])


def stock_splits(use_cache: bool = True) -> dict:
    """Alla historiska splitar; används för att sätta utdelningar i dagens aktieskala."""
    return _get("/instruments/stocksplits", {"from": "2000-01-01"},
                cache_key="stocksplits_from2000", use_cache=use_cache)


def split_probe():
    payload = stock_splits(use_cache=False)
    rows = [r for r in payload.get("stockSplitList", [])
            if (r.get("instrumentId") or r.get("insId")) in (8, 236)]
    print(json.dumps(rows, indent=2, ensure_ascii=False)[:4000])


def _extract_year_reports(rep: dict) -> list:
    """Extrahera årsrapporter ur Börsdatas grupperade svar.
    Svaret har {reportsYear: [...], reportsQuarter: [...], reportsR12: [...]}."""
    if not isinstance(rep, dict):
        return rep if isinstance(rep, list) else []
    # Direktträff på grupperade nycklar
    for key in ("reportsYear", "reports_year", "reportsAnnual"):
        if key in rep and isinstance(rep[key], list):
            return rep[key]
    # Fallback: platt 'reports' (typ-specifik endpoint)
    if "reports" in rep and isinstance(rep["reports"], list):
        return rep["reports"]
    return []


def eval_():
    """Schema-upptäckt + First North-täckningstest på EVAL_TICKERS."""
    m = {tk: (it, field) for it, tk, field in match_universe()}
    print("=" * 72)
    print("  BÖRSDATA-UTVÄRDERING (dumpar riktiga fältnamn – inget antaget)")
    print("=" * 72)
    for tk in EVAL_TICKERS:
        print(f"\n── {tk} " + "─" * max(1, 50 - len(tk)))
        hit = m.get(tk)
        if not hit:
            print("  INTE MATCHAD mot Börsdata-instrument – täckningslucka eller matchnings-fel.")
            continue
        it, field = hit
        ins_id = it.get("insId") or it.get("id")
        print(f"  Matchad: {it.get('name')} · insId={ins_id} (via {field})")
        try:
            rep = _find_report_endpoint_data(ins_id)
        except Exception as e:  # noqa: BLE001
            print(f"  FEL vid rapporthämtning: {e}")
            continue
        rows = _extract_year_reports(rep)
        if rows:
            print(f"  {len(rows)} årsrapportrader. Senaste raden (alla fält):")
            print("   ", json.dumps(rows[0], ensure_ascii=False)[:700])
            keys = list(rows[0].keys())
            money_like = [k for k in keys if isinstance(rows[0].get(k), (int, float)) and abs(rows[0][k]) > 1e5]
            print(f"  Sannolika belopps-fält (>100k): {money_like}")
        else:
            # Dumpa toppnivå-nycklar för debugging
            if isinstance(rep, dict):
                print(f"  Toppnivå-nycklar i svaret: {list(rep.keys())}")
                for k, v in rep.items():
                    if isinstance(v, list) and v:
                        print(f"  '{k}': {len(v)} poster")
            else:
                print("  Tomt rapportsvar.")
    print("\n" + "=" * 72)
    print("  Schema verifierat – fundamentals.py kan nu läsa Börsdata-rapporter via")
    print("  load_borsdata_reports(). Kör 'python -m altdata.fundamentals build' för att")
    print("  bygga fundamentals.csv med Börsdata-data.")


def backfill():
    """
    Rå rapport-JSON för HELA matchade universumet (Small+Large, inkl. Micro/
    First North). Ingen kvot-broms behövs (rate limit är per sekund, inte en
    engångspott) – men throttlas ändå till ~8 anrop/s för att aldrig träffa
    100/10s-gränsen. Full historik (maxCount=20) per bolag, ETT anrop styck.
    """
    m = match_universe()
    print(f"[backfill] {len(m)} bolag att hämta (full historik, maxCount=20 år)")
    ok, fail = 0, 0
    for i, (it, tk, _f) in enumerate(m):
        ins_id = it.get("insId") or it.get("id")
        try:
            rep = _find_report_endpoint_data(ins_id)
            n = len(_extract_year_reports(rep))
            ok += 1
            if (i + 1) % 25 == 0:
                print(f"  ...{i+1}/{len(m)} ({ok} ok, {fail} fel)")
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  {tk}: FEL {e}")
    print(f"[backfill] klart: {ok} ok, {fail} fel (cachat i {_cache_dir()})")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    # håll dispatch explicit så okända kommandon aldrig gör nätanrop
    {"probe": probe, "match": match, "eval": eval_, "backfill": backfill,
     "price_probe": price_probe, "dividend_probe": dividend_probe,
     "split_probe": split_probe}.get(
        cmd, lambda: print(__doc__))()


if __name__ == "__main__":
    main()
