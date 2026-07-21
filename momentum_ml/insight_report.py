"""
insight_report.py – nattligt narrativt lager ovanpå redan befintlig data:
senaste pressmeddelande/VD-ord, riktiga daterade nyheter/analytikernoter
via Avanzas /_api/market-guide/news/{id} (verifierat 2026-07-17 – MFN-PM +
Finwire-telegram, se altdata/avanza.py), plus WebSearch som komplement för
bredare kontext/ton, för dina innehav + modellens topp-10 sammanvägda
rankning.

REN NARRATIV, ALDRIG SIGNAL – dev-loggen (#18) visade redan att PM-/rapport-
/VD-ton inte bär OOS-alfa, och social buzz är en dokumenterat brusig
återvändsgränd (UTVECKLINGSLOGG §10, "jaga dem inte utan en billig
validate-first-test"). Det här skriver INGET till signals/scores/rankningen
– bara en läsvärd sammanfattning per bolag, för Bedömning-fliken.

Batchar ~5 bolag per headless-anrop (samma princip som quality_screener.py:s
batch_prompt_chunks – flera bolag i EN AI-konversation) för att hålla
kostnad/kvalitet i schack. Headless Claude låst till EXAKT WebSearch – kan
inte röra Montrose, filer eller något annat.

    python insight_report.py
    python insight_report.py --limit 6      # snabbare testkörning
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402
import claude_headless as ch  # noqa: E402

BATCH_SIZE = getattr(config, "INSIGHT_BATCH_SIZE", 5)
MAX_TICKERS = getattr(config, "INSIGHT_MAX_TICKERS", 20)


def _mfn_latest(ticker, n=1):
    """Senaste n PM (valfri källa, inte bara uppdragsanalys) – rått underlag,
    så headless-Claude ser samma sak en människa skulle läsa."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return []
    items = sorted(items, key=lambda x: x.get("published", ""), reverse=True)[:n]
    return [{"date": str(it.get("published", ""))[:10], "title": str(it.get("title", ""))[:120],
             "text": str(it.get("text", ""))[:600]} for it in items]


def _avanza_news(ticker, n=5):
    """Riktiga, daterade nyheter/PM/analytikernoter direkt från Avanza
    (altdata.avanza.news_for_ticker – verifierat 2026-07-17, MFN-
    pressmeddelanden + Finwire-telegram, se avanza.py:s _NEWS_ENDPOINT_
    CANDIDATES-kommentar). GRUNDDATA, inte gissning – headless-Claude ska
    förklara/kontextualisera dessa, inte hitta på egna. Tom lista vid fel
    (nätverk/ingen träff) – aldrig en krasch, bara mindre underlag."""
    import altdata.avanza as av
    try:
        return av.news_for_ticker(ticker, limit=n)
    except Exception:  # noqa: BLE001
        return []


def _universe():
    """Innehav + modellens topp-10 sammanvägda rankning, deduplicerat på
    ticker. Innehav vinner om ett bolag är med i båda (behåller held/cost)."""
    rows = pf.load_holdings()
    held = {(r.get("ticker") or "").upper(): r for r in rows if r.get("ticker")}
    top = pf._safe(lambda: pf._unified_rank(rows, top_n=10), [], "sammanvägd rank")
    sell_watch = {s["ticker"]: s for s in pf._safe(lambda: pf._takeprofit(rows), [], "säljvakt")}
    scores = pf._safe(pf._load_scores, {}, "poängkarta")

    out = {}
    for tk, r in held.items():
        out[tk] = {"ticker": tk, "name": r["name"], "held": True}
    for c in top:
        tk = c["ticker"]
        out.setdefault(tk, {"ticker": tk, "name": c["name"], "held": False})
        out[tk]["rank_note"] = c.get("note")
    for tk, entry in out.items():
        sc = scores.get(tk, {})
        entry["quality"] = sc.get("quality")
        entry["quant"] = sc.get("quant")
        entry["prob_up"] = sc.get("prob_up")
        entry["value_zone"] = sc.get("value_zone") or sc.get("zone")
        sw = sell_watch.get(tk)
        if sw:
            entry["sell_watch"] = {"action": sw.get("action"), "reasons": sw.get("reasons")}
        entry["mfn"] = _mfn_latest(tk)
    # Innehav prioriteras om universumet måste kapas (kostnadstak) – de är
    # dina riktiga pengar, kandidaterna bara idéer.
    ordered = sorted(out.values(), key=lambda e: not e.get("held"))
    capped = ordered[:MAX_TICKERS]
    # Avanza-nyheter hämtas EFTER kapningen (live nätverksanrop, till
    # skillnad från _mfn_latest()s lokala cache-läsning) – slösa aldrig
    # anrop på bolag som ändå kapas bort.
    for entry in capped:
        entry["avanza_news"] = _avanza_news(entry["ticker"])
    return capped


def _context_block(e):
    lines = [f"### {e['ticker']} – {e['name']}",
             "Innehav" if e.get("held") else "Kandidat (modellens topplista, inte ägd)"]
    if e.get("rank_note"):
        lines.append(f"Modellens motivering: {e['rank_note']}")
    facts = []
    if e.get("quality") is not None:
        facts.append(f"kvalitet {e['quality']:.1f}/5")
    if e.get("quant") is not None:
        facts.append(f"kvant {e['quant']:.0f}")
    if e.get("prob_up") is not None:
        facts.append(f"P(upp) {e['prob_up']:.0%}")
    if e.get("value_zone"):
        facts.append(f"värdering: {e['value_zone']}")
    if facts:
        lines.append("Modellens siffror: " + ", ".join(facts))
    if e.get("sell_watch"):
        sw = e["sell_watch"]
        lines.append(f"Säljvakt flaggar: {sw.get('action')} ({', '.join(sw.get('reasons') or [])})")
    if e.get("mfn"):
        for pm in e["mfn"]:
            lines.append(f"Senaste PM ({pm['date']}): {pm['title']} – {pm['text']}")
    else:
        lines.append("Inget cachat pressmeddelande.")
    if e.get("avanza_news"):
        lines.append("Färska nyheter/PM/analytikernoter (Avanza, VERIFIERADE – inte att hitta på egna):")
        for n in e["avanza_news"]:
            src = f"{n.get('category') or ''}/{n.get('source') or ''}".strip("/")
            lines.append(f"  [{n.get('date')}] ({src}) {n.get('headline')} – {n.get('intro')}")
    else:
        lines.append("Inga Avanza-nyheter hittade (nätverksfel eller ingen träff).")
    return "\n".join(lines)


_PROMPT_HEAD = """Du är en NEUTRAL, sansad investerarassistent. För VARJE bolag nedan:
1. Läs underlaget (redan känd data – förklara det, citera det inte rått).
2. Basera dig FRÄMST på de "Färska nyheter/PM/analytikernoter"-rader som
   redan finns i underlaget (riktiga, daterade MFN-pressmeddelanden och
   Finwire-analytikernoter från Avanza – GRUNDDATA, inte att gissa på).
   Använd WebSearch bara som KOMPLEMENT: bredare kontext, reaktion/tolkning
   av det som redan står där, eller om raden ovan saknas/är tunn helt.
   Prioritera svenska finansmedier i sökningen – sök gärna explicit t.ex.
   "site:efn.se <bolag>", "site:omni.se/ekonomi <bolag>",
   "site:swedbank-aktiellt.se <bolag>" (Swedbanks fritt tillgängliga dagliga
   analyser/veckobrev) – innan en bredare sökning. FÖR UTLÄNDSKA bolag/
   tematiska ETF:er (t.ex. halvledare/AI/rymdteknik-fonder) där svenska
   medier sällan har täckning, sök i stället mot etablerade, i huvudsak
   FRIA engelskspråkiga källor: "site:cnbc.com <bolag>",
   "site:marketwatch.com <bolag>", "site:seekingalpha.com <bolag>". Ta med
   en allmän känsla av analytiker-/marknadston om den
   framgår (gissa aldrig fram en "social ton" du inte faktiskt sett).
3. Skriv 2-4 meningar på SVENSKA: vad har hänt, är det materiellt för caset,
   vad säger nyheterna/tonen, hur ser det ut mot modellens siffror.

VIKTIGT: Det här är BAKGRUND, inte rådgivning. Skriv ALDRIG "köp"/"sälj"/
"behåll" eller någon köprekommendation – bara vad som faktiskt hänt och hur
det förhåller sig till modellens data. Hittar du inget nytt, säg det kort
("inga färska nyheter") istället för att gissa.

Svara ENDAST med kompakt JSON, en nyckel per ticker, ingen markdown:
  {"TICKER1": "sammanfattning...", "TICKER2": "sammanfattning...", ...}

Bolagen:
"""


def _run_batch(entries):
    prompt = _PROMPT_HEAD + "\n\n".join(_context_block(e) for e in entries)
    result = ch.run(prompt, "WebSearch", timeout=180)
    if "error" in result:
        print(f"[insight] batch ({', '.join(e['ticker'] for e in entries)}) misslyckades: {result['error']}")
        return {}, result["error"]
    return {k: v for k, v in result.items() if isinstance(v, str)}, None


def build(limit=None):
    universe = _universe()
    if limit:
        universe = universe[:int(limit)]
    if not universe:
        print("[insight] inga bolag att analysera (inga innehav/rankningar).")
        return
    by_ticker = {e["ticker"]: e for e in universe}
    summaries = {}
    for i in range(0, len(universe), BATCH_SIZE):
        batch = universe[i:i + BATCH_SIZE]
        print(f"[insight] batch {i // BATCH_SIZE + 1}: {', '.join(e['ticker'] for e in batch)}")
        result, err = _run_batch(batch)
        summaries.update(result)
        if err:
            argv = ["--limit", str(limit)] if limit else []
            if ch.queue_retry(__file__, argv, err):
                # Kvoten är slut för hela körningen - fler batchar skulle
                # bara upprepa samma fel, hela skriptet är redan ombokat.
                break

    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "companies": [{"ticker": tk, "name": e["name"], "held": e.get("held", False),
                          "summary": summaries.get(tk, "Kunde inte generera sammanfattning.")}
                         for tk, e in by_ticker.items()]}
    p = pf._results_dir() / "insight_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for c in out["companies"] if c["ticker"] in summaries)
    print(f"[insight] {ok}/{len(universe)} sammanfattade → {p}")


if __name__ == "__main__":
    lim = None
    if len(sys.argv) > 2 and sys.argv[1] == "--limit":
        lim = sys.argv[2]
    build(lim)
