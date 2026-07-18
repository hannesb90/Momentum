"""
portfolio_commentary.py – ett dagligt, läsvärt RESEARCH-brev om portföljen.

MEDVETET INTE en sammanfattning av portföljfördelning/vikt/kvalitets-betyg
– den datan syns redan i Översikt/Innehav/Sektorer, och brevet ska aldrig
bara recitera den (verklig lärdom 2026-07-18: tidigare version blev till
stor del en upprepning av vad varje annan vy redan visar). Underlaget
(_underlag()) ger fortfarande PER INNEHAV/PER SEKTOR-siffror som GRUND för
resonemanget, men prompten (_PROMPT) kräver uttryckligen att varje mening
ska tillföra research-baserad insikt – annars utelämnas den posten.

Använder headless Claudes inbyggda WebSearch (låst, se _TOOLS nedan) för att
förklara VARFÖR en sektor/ett bolag/ett globalt tema rört sig ("X har
fallit senaste tiden till följd av Y, men bedöms fortsatt ha Z – därför
inget skäl att korrigera positionen"), inte bara vad siffrorna redan visar.
REN NARRATIV, ALDRIG SIGNAL – gäller fortfarande: kommentaren får resonera
om huruvida en rörelse ser tillfällig/strukturell ut, men ska ALDRIG skriva
en ny köp/sälj-instruktion utöver vad Nästa köp-planen/säljvakten redan säger.

Körs dagligen kl 23:00 (momentum-commentary.timer), EFTER morgonens
nattträning/watchlist-synk/insight-rapport samma kalenderdag – kommentaren
citerar alltid färska siffror, inte gårdagens.

    python portfolio_commentary.py
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402
import claude_headless as ch  # noqa: E402

_TOOLS = "WebSearch"

_PROMPT = """Du är en NEUTRAL, sansad portföljanalytiker. Nedan är
analysunderlaget för en persons portfölj (siffror redan beräknade) MED ett
avsnitt PER INNEHAV (vikt, vinst/förlust, modellens kvalitets-/kvant-/
momentum-betyg, fundamenta-flaggor, sektor, kommande rapportdatum, färsk
nyhets-/PM-sammanfattning om sådan finns) och ETT AVSNITT PER SEKTOR
(momentum senaste 4/13/26 veckor, rankning, rotation in/ut) för sektorerna
portföljen faktiskt är exponerad mot.

Använd WebSearch för att TA REDA PÅ VARFÖR en sektor eller ett innehav med
en tydlig rörelse (stor uppgång/nedgång senaste veckorna, eller lågt
rankad/het sektor) faktiskt rört sig. Prioritera svenska finansmedier – sök
gärna explicit t.ex. "site:efn.se <sektor/bolag>", "site:omni.se/ekonomi
<sektor/bolag>", "site:swedbank-aktiellt.se <sektor/bolag>" (Swedbanks
fritt tillgängliga dagliga analyser/veckobrev) – innan en bredare sökning
som "<sektor> aktier <senaste händelse>" eller "<bolag> nyheter". FÖR DE
GLOBALA TEMANA (halvledare/AI/rymdteknik m.fl. – ofta amerikanskt
dominerade, där svenska medier har tunn täckning) sök i stället mot
etablerade, i huvudsak FRIA engelskspråkiga källor – använd ETF:ENS EGET
NAMN eller bransch som sökord (INTE den svenska temaetiketten, den ger
inga träffar på engelskspråkiga sajter), t.ex. "site:cnbc.com VanEck
Semiconductor" eller "site:seekingalpha.com semiconductor ETF" – se
etf_name i underlaget för respektive tema. Skriv sedan analytiker-stil, konkret
orsak + bedömning, i stil med: "Halvledarsektorn har fallit tungt senaste
veckorna till följd av X, men bedöms fortsatt ha goda tillväxtutsikter och
är därför inte ett skäl att korrigera positionen." Gissa ALDRIG en orsak
utan att ha sökt fram den – hittar du inget, säg det kort istället.

VIKTIGAST AV ALLT: appen visar redan hink-fördelning, vikt per innehav,
kvalitets-/kvant-betyg och sektorexponering i egna vyer (Översikt/Innehav/
Sektorer) – UPPREPA DEM INTE i brevet, de tillför inget den redan inte
sett. Brevets enda existensberättigande är RESEARCH-baserad ANALYS
(WebSearch-underbyggd VARFÖR) som INTE syns någon annanstans i appen.
Varje mening ska tillföra ny insikt, inte recitera en siffra ur underlaget.

Skriv en förvaltarkommentar på SVENSKA (8-12 meningar, löpande text, inga
punktlistor). Den ska vara KONKRET och ANALYSTUNG:
  - Nämn MINST 3 SPECIFIKA innehav/teman vid namn, men ENDAST med skäl du
    faktiskt hittat via sökning (VARFÖR de rört sig, vad branschen/
    analytiker säger) – inte "Acconeer har starkt kvalitetsbetyg" (redan
    synligt i appen) utan "Acconeer är upp X% efter att [källa] rapporterat
    Y". Hittar du ingen research-grundad förklaring för ett innehav, hoppa
    över det och välj ett annat du faktiskt kan förklara – gissa aldrig.
  - Kommentera MINST 1-2 SEKTORER/UNDERTEMAN med en research-baserad
    förklaring till rörelsen (se ovan). Använd UNDERLAGETS mest specifika
    nivå (PER FINT UNDERTEMA om det finns, annars PER SEKTOR/GICS) –
    "Medicinsk utrustning" är mer läsvärt och precist än "Health Care".
  - Nämn kommande RAPPORTER inom de närmaste veckorna kort, ENDAST om du
    kan koppla dem till en förväntning du faktiskt hittat via sökning –
    annars utelämna, ett bart datum utan sammanhang är redan synligt i
    appen.
  - Väv in exit-alarm/säljvakt/fundamenta-flaggor BARA om du kan lägga
    till en research-baserad förklaring till varför – annars är den
    tekniska flaggan redan synlig i Bedömning-fliken, upprepa den inte
    utan ny insikt.
  - Om GLOBALA TEMAN finns i underlaget: nämn kort vilket tema som leder/
    släpar just nu OCH varför (se sökinstruktionen ovan), särskilt om det
    påverkar bedömningen av ett INNEHAVT tema-ETF.
  - Avsluta med EN mening om vad MODELLEN skulle ändra (Nästa köp-planen,
    i klartext) – inte en upprepning av hela planen, bara skälet.

VIKTIGT: sammanfatta och förklara siffrorna i underlaget korrekt – gissa
aldrig på SIFFROR (bara på ORSAKER får du använda sökning). Skriv ALDRIG en
ny köp/sälj-rekommendation utöver vad som redan står i underlaget (Nästa
köp-planen/säljvakten) – du får bedöma om en rörelse ser tillfällig eller
strukturell ut, men det är fortfarande läsvärd bakgrund, inte nytt
investeringsråd. Detta gäller ÄVEN de globala teman som INTE är innehav –
ett hett tema i tabellen är INTE en köpsignal, skriv aldrig "överväg att
köpa X" bara för att temat leder rankningen.

Svara ENDAST med kompakt JSON, ingen markdown: {{"commentary": "..."}}

UNDERLAG:
{underlag}
"""


def _report_calendar(tickers):
    """{ticker: {date, type}} för kommande rapporter inom READ_CALENDAR_DAYS
    – "förväntningar" i kommentaren. Skriven av altdata.avanza.calendar(),
    tom/saknas om den aldrig körts (ingen crash, bara mindre underlag)."""
    from datetime import date, timedelta
    out = {}
    horizon = (date.today() + timedelta(days=45)).isoformat()
    for seg in config.SEGMENTS.values():
        p = Path(seg.get("results_dir", "")) / "report_calendar.csv"
        if not p.exists():
            continue
        try:
            for r in csv.DictReader(open(p, encoding="utf-8")):
                tk = (r.get("ticker") or "").upper()
                d = r.get("next_report_date") or ""
                if tk in tickers and d and d <= horizon:
                    out[tk] = {"date": d, "type": r.get("next_report_type") or ""}
        except Exception:  # noqa: BLE001
            pass
    return out


def _sector_context(tickers):
    """Momentum/rankning/rotation för sektorerna portföljen faktiskt är
    exponerad mot, ur results/sector_momentum.csv (skriven nattligt av
    main.py). Tom lista om filen saknas – inte en crash, bara mindre
    underlag. Sektor-ETF:er (fonder) räknas aldrig in i detta – se fixen i
    backtest.sector_momentum.sector_momentum_snapshot()."""
    held_sectors = {pf._safe(lambda tk=tk: pf._sector_of(tk), "", "sektor")
                    for tk in tickers if tk}
    held_sectors.discard("")
    if not held_sectors:
        return []
    p = pf._results_dir() / "sector_momentum.csv"
    if not p.exists():
        return []
    out = []
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("sector") not in held_sectors:
                continue
            out.append(r)
    except Exception:  # noqa: BLE001
        return []
    return out


def _theme_context(tickers):
    """Momentum/rankning/rotation för Avanzas FINA underteman portföljen är
    exponerad mot (results/theme_momentum.csv, se backtest/theme_momentum.py
    – t.ex. "Medicinsk utrustning" skilt från "Bioteknik", där GICS-sektorn
    ovan bara ser en gemensam "Health Care"). Tom lista om filen saknas
    (theme_momentum-extraktionen inte körd än) – inte en crash."""
    held_themes = {pf._safe(lambda tk=tk: pf._theme_of(tk), "", "tema")
                   for tk in tickers if tk}
    held_themes.discard("")
    if not held_themes:
        return []
    p = pf._results_dir() / "theme_momentum.csv"
    if not p.exists():
        return []
    out = []
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if r.get("theme") not in held_themes:
                continue
            out.append(r)
    except Exception:  # noqa: BLE001
        return []
    return out


def _theme_fund_names() -> dict:
    """theme -> [alla fondnamn i temat] ur cache/fund_niche_themes.csv, INTE
    bara temats primärval. Fixar en verklig lucka: "(INNEHAV)" i GLOBALA
    TEMAN matchade tidigare bara mot primärvalets etf_name (billigast
    avgift), så ett tema visades som "ej ägt" om du äger EN ANNAN fond i
    samma tema (t.ex. WisdomTree Uranium när primärvalet är VanEck Uranium
    & Nuclear – samma tema, olika instrument, samma faktiska exponering).
    Tom dict om filen saknas – inte en crash, bara fallback till etf_name."""
    p = Path(config.anchor("cache")) / "fund_niche_themes.csv"
    out: dict = {}
    if not p.exists():
        return out
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            theme, name = r.get("theme"), r.get("name")
            if theme and name:
                out.setdefault(theme, []).append(name)
    except Exception:  # noqa: BLE001
        return {}
    return out


def _global_theme_context():
    """Momentum/rankning/rotation för de GLOBALA temana (rymd/drönare,
    humanoider, halvledare, robotik, cybersäkerhet, kvant, ... – se
    global_theme_momentum.py) UTAN filter mot innehav: hela poängen är att
    se vilket tema som är hetast JUST NU, inte bara de du redan äger (till
    skillnad från _sector_context()/_theme_context() som filtrerar mot
    portföljens faktiska exponering). Tom lista om filen saknas (kör inte
    ännu / global_theme_momentum.py inte kört) – ingen crash."""
    p = pf._results_dir() / "global_theme_momentum.csv"
    if not p.exists():
        return []
    try:
        return list(csv.DictReader(open(p, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return []


def _underlag():
    rows = pf.load_holdings()
    d = pf.compute(rows)
    nb = pf._safe(lambda: pf.next_buy(rows), {}, "nästa köp")
    scores = pf._safe(pf._load_scores, {}, "poängkarta")
    exit_path = pf._results_dir() / "exit_signals.json"
    exits = json.loads(exit_path.read_text(encoding="utf-8")) if exit_path.exists() else {}
    exit_by_ticker = {e["ticker"]: e for e in (exits.get("holdings") or [])}
    insight_path = pf._results_dir() / "insight_report.json"
    insight = json.loads(insight_path.read_text(encoding="utf-8")) if insight_path.exists() else {}
    insight_by_ticker = {c["ticker"]: c["summary"] for c in insight.get("companies", [])}
    holdings = d.get("holdings") or []
    calendar = _report_calendar({(h.get("ticker") or "").upper() for h in holdings})

    lines = [f"Totalt värde: {d['total']:,.0f} kr, {len(rows)} innehav".replace(",", " ")]
    lines.append("Hinkar (nu vs mål): " + ", ".join(
        f"{pf.BUCKET_LABEL[b]} {d['buckets'][b]:.0%} (mål {d['target'].get(b, 0):.0%})"
        for b in pf.BUCKETS))
    if d.get("warnings"):
        lines.append("Varningar: " + "; ".join(d["warnings"]))

    lines.append("\nPER INNEHAV (sorterat efter storlek):")
    total_val = d["total"] or 1.0
    for h in sorted(holdings, key=lambda x: -(x.get("value") or 0)):
        tk = (h.get("ticker") or "").upper()
        andel = (h.get("value") or 0) / total_val
        parts = [f"{h['name']} ({tk or 'okänd ticker'})", f"{andel:.0%} av portföljen"]
        if h.get("cost"):
            gain = h["value"] / h["cost"] - 1.0
            parts.append(f"vinst {gain:+.0%}")
        sc = scores.get(tk, {})
        facts = []
        if sc.get("quality") is not None:
            facts.append(f"kvalitet {sc['quality']:.1f}/5")
        if sc.get("quant") is not None:
            facts.append(f"kvant {sc['quant']:.0f}")
        if sc.get("prob_up") is not None:
            facts.append(f"P(upp) {sc['prob_up']:.0%}")
        if facts:
            parts.append(", ".join(facts))
        fund = h.get("fundamentals")
        if fund and not fund.get("ok"):
            parts.append("fundamenta-flagg: " + ", ".join(fund.get("issues") or []))
        sec_label, sec = pf._safe(lambda: pf._theme_of_labeled(tk), ("", ""), "tema/sektor") if tk else ("", "")
        if sec:
            parts.append(f"{sec_label} {sec}")
        ex = exit_by_ticker.get(tk)
        if ex and ex.get("tier") not in (None, "ok"):
            parts.append(f"exit-alarm {ex['tier']}: {ex.get('tech_note')}")
        cal = calendar.get(tk)
        if cal:
            parts.append(f"rapport {cal['date']} ({cal['type']})")
        note = insight_by_ticker.get(tk)
        if note:
            parts.append(f"nyligen: {note}")
        lines.append("  - " + " · ".join(parts))

    sectors = _sector_context({(h.get("ticker") or "").upper() for h in holdings})
    if sectors:
        lines.append("\nPER SEKTOR (portföljens sektorer, momentum/rankning/rotation):")
        for s in sorted(sectors, key=lambda x: int(float(x.get("rank") or 999))):
            def f(k):
                try:
                    return float(s.get(k) or 0)
                except ValueError:
                    return 0.0
            lines.append(
                f"  - {s.get('sector')}: rank {s.get('rank')} ({s.get('n_stocks')} bolag i sektorn), "
                f"momentum 4v {f('momentum_4w'):+.1%} · 13v {f('momentum_13w'):+.1%} "
                f"· 26v {f('momentum_26w'):+.1%}, rotation: {s.get('flow') or 'okänd'}")

    themes = _theme_context({(h.get("ticker") or "").upper() for h in holdings})
    if themes:
        lines.append("\nPER FINT UNDERTEMA (Avanzas egen klassificering, mer detaljerad än GICS-"
                      "sektorn ovan – t.ex. \"Medicinsk utrustning\" skilt från \"Bioteknik\"):")
        for th in sorted(themes, key=lambda x: int(float(x.get("rank") or 999))):
            def f(k):
                try:
                    return float(th.get(k) or 0)
                except ValueError:
                    return 0.0
            lines.append(
                f"  - {th.get('theme')}: rank {th.get('rank')} ({th.get('n_stocks')} bolag), "
                f"momentum 4v {f('momentum_4w'):+.1%} · 13v {f('momentum_13w'):+.1%} "
                f"· 26v {f('momentum_26w'):+.1%}, rotation: {th.get('flow') or 'okänd'}")

    global_themes = _global_theme_context()
    if global_themes:
        # Namnmatchning, INTE ticker – global_theme_momentum.py:s rader kan nu
        # komma från fund_niche_themes.csv (orderbookId-baserad "id:12345",
        # matchar aldrig våra egna .DE/.L-tickers) i stället för den gamla
        # handplockade listans riktiga tickers. Ömsesidig substräng-jämförelse
        # (fondnamn kan skilja lite i formulering mellan Montrose/Avanza) –
        # bara en läsvärd etikett, inget som beräkningar hänger på.
        held_names = [(h.get("name") or "").lower() for h in holdings if h.get("name")]
        theme_names = _theme_fund_names()

        def _is_held(theme: str, etf_name: str) -> bool:
            # Hela temats fondlista i första hand (fångar "äger en ANNAN
            # fond i samma tema än primärvalet") – etf_name bara som
            # fallback när temat saknas i fund_niche_themes.csv (t.ex. den
            # gamla handplockade GLOBAL_THEMES-fallbacken i global_theme_
            # momentum.py om klassificeraren aldrig körts).
            names = theme_names.get(theme) or ([etf_name] if etf_name else [])
            return any((n or "").lower() and
                      any((n or "").lower() in hn or hn in (n or "").lower() for hn in held_names)
                      for n in names)

        lines.append("\nGLOBALA TEMAN (tematiska ETF:er, rankade mot VARANDRA – omfattar teman "
                      "utan svensk motsvarighet, t.ex. rymd/drönare vs humanoida robotar; "
                      "'(INNEHAV)' markerar de du redan äger, resten är bara bevakning. "
                      "Avgift = årlig totalkostnad, redan viktad in i primärvalet per tema):")
        for gt in sorted(global_themes, key=lambda x: int(float(x.get("rank") or 999))):
            def f(k):
                try:
                    return float(gt.get(k) or 0)
                except ValueError:
                    return 0.0
            held_flag = " (INNEHAV)" if _is_held(gt.get("theme"), gt.get("etf_name")) else ""
            fee = gt.get("fee")
            fee_note = f", avgift {float(fee):.2%}" if fee not in (None, "", "None") else ""
            lines.append(
                f"  - {gt.get('theme')}{held_flag}: rank {gt.get('rank')} ({gt.get('etf_name')}{fee_note}), "
                f"momentum 4v {f('momentum_4w'):+.1%} · 13v {f('momentum_13w'):+.1%} "
                f"· 26v {f('momentum_26w'):+.1%}, rotation: {gt.get('flow') or 'okänd'}")

    if nb.get("rows"):
        lines.append("\nNästa köp-planen (" + str(nb.get("amount")) + " kr): " + "; ".join(
            f"{r['ticker']} {r['kr']} kr ({r['bucket']}) – {r.get('why', '')}" for r in nb["rows"]))
    if nb.get("sell_watch"):
        lines.append("Säljvakt (utöver ev. per-innehav-flaggor ovan): " + "; ".join(
            f"{s['name']} ({s.get('action')})" for s in nb["sell_watch"] if s.get("level", 0) >= 1))
    return "\n".join(lines)


def build():
    rows = pf.load_holdings()
    if not rows:
        print("[commentary] inga innehav – hoppar.")
        return
    prompt = _PROMPT.format(underlag=_underlag())
    # WebSearch, INGET annat (ingen Montrose, ingen filåtkomst) - låst via
    # --allowedTools + --permission-mode dontAsk i claude_headless.run.
    # Flera sökningar (en per sektor/innehav med tydlig rörelse) -> längre
    # timeout än insight_report.py:s per-batch-anrop.
    result = ch.run(prompt, _TOOLS, timeout=240)
    if "error" in result or not result.get("commentary"):
        print(f"[commentary] misslyckades: {result.get('error', 'tomt svar')}")
        return
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "commentary": result["commentary"]}
    p = pf._results_dir() / "portfolio_commentary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[commentary] skriven → {p}")


_ASK_PROMPT = """Du är en NEUTRAL, sansad portföljanalytiker som just skrev
förvaltarkommentaren nedan om användarens portfölj. Användaren har en
FÖLJDFRÅGA på den – svara direkt på FRÅGAN, grundat i underlaget (samma
data kommentaren byggdes från). Använd WebSearch bara om frågan kräver
research du inte redan har i underlaget (t.ex. "varför" en rörelse skett) –
gissa aldrig en orsak utan att ha sökt fram den, säg då kort att du inte
hittade något i stället.

VIKTIGT: Skriv ALDRIG en köp/sälj-rekommendation – bara vad som redan syns
i underlaget/planen eller vad research faktiskt visar. Om frågan ber om
rådgivning ("ska jag sälja X?"), svara med vad DATAN/planen redan säger
(t.ex. vad säljvakten/Nästa köp-planen visar) utan att själv formulera ett
nytt råd. Om frågan är orelaterad till portföljen/marknaden, säg det kort.

Svara koncist på SVENSKA (1-4 meningar, löpande text – längre bara om
frågan kräver det). Svara ENDAST med kompakt JSON, ingen markdown:
{{"answer": "..."}}

FÖRVALTARKOMMENTAREN (redan skriven):
{commentary}

UNDERLAG (samma data kommentaren byggdes från):
{underlag}

FÖLJDFRÅGA: {question}
"""


def ask(question: str) -> dict:
    """På-begäran svar på en fri följdfråga om förvaltarkommentaren/
    portföljen – samma underlag som build() men EN fråga i taget, synkront
    (samma mönster som security_analysis.analyze()). Skriver ALDRIG till
    portfolio_commentary.json - ren fråga/svar, ingen cache."""
    question = (question or "").strip()
    if not question:
        return {"answer": None, "error": "ingen fråga angiven"}
    rows = pf.load_holdings()
    if not rows:
        return {"answer": None, "error": "inga innehav"}
    p = pf._results_dir() / "portfolio_commentary.json"
    prior = json.loads(p.read_text(encoding="utf-8")).get("commentary") if p.exists() else None
    prompt = _ASK_PROMPT.format(commentary=prior or "(ingen genererad än)",
                                 underlag=_underlag(), question=question)
    result = ch.run(prompt, _TOOLS, timeout=120)
    if "error" in result or not result.get("answer"):
        return {"answer": None, "error": result.get("error", "tomt svar")}
    return {"answer": result["answer"]}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--ask":
        print(json.dumps(ask(" ".join(sys.argv[2:])), ensure_ascii=False, indent=2))
    else:
        build()
