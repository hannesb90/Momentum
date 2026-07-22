"""
stock_deep_dive.py – på-begäran fördjupning FÖR ETT INNEHAV på den nya
aktiedetaljsidan (/aktie/:ticker): ärligt motställda bull/bear-argument för
att FORTSÄTTA äga just detta bolag nu, plus kort konkurrentkontext. Samma
"REN NARRATIV, ALDRIG SIGNAL"-disciplin som portfolio_commentary.py/
insight_report.py/security_analysis.py – skriver ALDRIG ett nytt köp/sälj-
råd, bara vad modellens redan beräknade poäng + färska nyheter/konkurrenter
säger i klartext.

Skiljer sig från security_analysis.py (Skanner: HYPOTETISK NY position, hur
den skulle påverka portföljen som helhet) genom att gälla ett BEFINTLIGT
innehav – frågan är inte "vad händer om jag köper" utan "varför ser
bolagets läge ut som det gör, och vad talar för/emot att fortsätta äga
det". Headless Sonnet + WebSearch, samma låsning som resten (ingen
Montrose, ingen filåtkomst).

Två separata på-begäran-funktioner (samma mönster som portfolio_commentary.py
build()/ask()):
  analyze(ticker) – bull/bear-narrativ + konkurrentkontext, en gång per klick.
  ask(ticker, question) – fri följdfråga scopad till just detta bolag.

    python stock_deep_dive.py AZA.ST
    python stock_deep_dive.py AZA.ST --ask "Vilka är de största riskerna just nu?"
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402
import claude_headless as ch  # noqa: E402

_TOOLS = "WebSearch"


def _csv_row(path: Path, ticker: str) -> Optional[dict]:
    if not path.exists():
        return None
    import pandas as pd
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return None
    hit = df[df["ticker"].astype(str).str.upper() == ticker.upper()]
    if hit.empty:
        return None
    row = hit.iloc[0].to_dict()
    return {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()}


def _holding(ticker: str) -> Optional[dict]:
    for r in pf._safe(pf.load_holdings, [], "innehav"):
        if str(r.get("ticker") or "").upper() == ticker.upper():
            return r
    return None


def _insight_summary(ticker: str) -> Optional[str]:
    path = Path(config.anchor(config.RESULTS_DIR)) / "insight_report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for c in data.get("companies", []):
        if str(c.get("ticker") or "").upper() == ticker.upper():
            summary = (c.get("summary") or "").strip()
            # insight_report.py skriver denna placeholder när nattjobbets
            # generering misslyckades - det är ett felmeddelande, inte en
            # narrativ, och ska inte in i LLM-underlaget som om det vore en.
            if not summary or summary == "Kunde inte generera sammanfattning.":
                return None
            return summary
    return None


def _case_change(ticker: str) -> Optional[dict]:
    path = Path(config.anchor(config.RESULTS_DIR)) / "case_changes.csv"
    return _csv_row(path, ticker)


def _underlag(ticker: str) -> tuple[str, str]:
    """Bygger textunderlaget + bolagsnamnet. Delas mellan analyze() och ask()
    så en följdfråga svarar mot samma grund som den ursprungliga analysen."""
    # anchor() på BÅDA (var tidigare bara på quant): utan den är sökvägen
    # CWD-relativ, och på Pi:n (MOMENTUM_HOME satt, tjänsten kan köra med
    # annan arbetskatalog) hittades quality-betyget då tyst aldrig.
    quality = _csv_row(Path(config.anchor(config.RESULTS_DIR)) / "quality_shortlist.csv", ticker)
    quant = _csv_row(Path(config.anchor(config.RESULTS_DIR)) / "quant_shortlist.csv", ticker)
    holding = _holding(ticker)
    name = (holding or {}).get("name") or (quality or {}).get("name") or (quant or {}).get("name") or ticker

    lines = [f"BOLAG: {name} ({ticker})"]

    if holding:
        lines.append(f"Innehav: {holding.get('value')} kr" +
                      (f" (bucket {holding.get('bucket')})" if holding.get("bucket") else ""))
        cost = holding.get("cost")
        if cost and holding.get("value"):
            gain = holding["value"] / cost - 1
            lines.append(f"Orealiserad avkastning sedan köp: {gain:+.1%}")

    if quality:
        lines.append(f"Kvalitetsbetyg (LLM/PM-analys, källa {quality.get('quality_source', 'llm')}): "
                      f"{quality.get('composite')}/5" + (f" – {quality.get('pitch')}" if quality.get("pitch") else ""))
        if quality.get("red_flags"):
            lines.append(f"Flaggade risker: {quality['red_flags']}")
    if quant:
        lines.append(f"Kvantbetyg (hård data): {quant.get('quant_score')}% "
                      f"(kvalitet {quant.get('quality')}, tillväxt {quant.get('growth')}, "
                      f"trygghet {quant.get('safety')}, värde {quant.get('value')})")
        if quant.get("roe") is not None:
            # TradingView-scannerns fält (return_on_equity m.fl.) är redan
            # procenttal (15.2 = 15.2%), INTE en fraktion - ingen *100 här.
            lines.append(f"ROE {quant['roe']:.1f}%, P/S {quant.get('ps')}, EV/EBITDA {quant.get('ev_ebitda')}")

    case = _case_change(ticker)
    if case:
        lines.append(f"Caseförändring (senaste 90d PM/nyheter mot föregående 90d): {case.get('status')} "
                      f"– {case.get('reasons')}")

    insight = _insight_summary(ticker)
    if insight:
        lines.append(f"\nSenaste narrativa sammanfattning (nattlig, PM/VD-ord + nyheter):\n{insight}")

    import altdata.avanza as av
    news = pf._safe(lambda: av.news_for_ticker(ticker, limit=6), [], "avanza-nyheter")
    if news:
        lines.append("\nFärska nyheter/PM (Avanza, verifierade):")
        for n in news:
            lines.append(f"  [{n.get('date')}] {n.get('headline')} – {n.get('intro')}")

    return "\n".join(lines), name


_ANALYZE_PROMPT = """Du är en NEUTRAL, sansad investerarassistent. Nedan är
underlaget för ETT bolag som användaren REDAN ÄGER (eller följer) – redan
beräknade modellpoäng, ev. caseförändring, färsk narrativ sammanfattning och
nyheter.

Använd WebSearch för att komplettera med: (a) bredare kontext till varför
bolaget presterar som det gör, och (b) 2-3 av bolagets närmaste konkurrenter
och kortfattat hur det går för DEM just nu (samma bransch, jämförbar
verksamhet). Prioritera svenska finansmedier (site:efn.se, site:omni.se/ekonomi)
innan bredare sökning.

Skriv på SVENSKA, i JSON med tre fält:
  "bull_case": 2-4 meningar, de STARKASTE ärliga argumenten för att fortsätta
    äga bolaget just nu, grundat i underlaget + sökning.
  "bear_case": 2-4 meningar, de STARKASTE ärliga argumenten mot / riskerna med
    att fortsätta äga bolaget just nu. Var lika ärlig och konkret här som i
    bull_case – tunna eller självklara motargument är inte till hjälp.
  "competitors": 2-4 meningar om bolagets 2-3 närmaste konkurrenter och hur
    det går för dem, som kontext till bolagets egen utveckling.

VIKTIGT: Skriv ALDRIG en köp/sälj-rekommendation ("sälj denna aktie", "öka
positionen") – bull/bear är två sidor av samma mynt för att ge en ÄRLIG bild,
inte ett förtäckt råd. Gissa aldrig siffror, bara resonemang/orsaker får
komma från sökning.

Svara ENDAST med kompakt JSON, ingen markdown:
{{"bull_case": "...", "bear_case": "...", "competitors": "..."}}

UNDERLAG:
{underlag}
"""

_ASK_PROMPT = """Du är en NEUTRAL, sansad investerarassistent. Användaren har
en fråga om ETT specifikt bolag i sin portfölj/bevakning. Nedan är underlaget
för bolaget (modellpoäng, caseförändring, narrativ, nyheter). Använd WebSearch
vid behov för att komplettera med fakta/kontext, prioritera svenska
finansmedier (site:efn.se, site:omni.se/ekonomi) innan bredare sökning.

Svara på svenska i löpande text, 3-8 meningar, grundat i underlaget och det du
hittar. Skriv ALDRIG ett köp/sälj-råd – bara vad som faktiskt syns i data/
nyheter, i klartext. Om frågan inte går att svara på utifrån underlaget/sökning,
säg det ärligt i stället för att gissa.

BOLAG: {name} ({ticker})
UNDERLAG:
{underlag}

FRÅGA: {question}

Svara ENDAST med kompakt JSON: {{"answer": "..."}}
"""


def analyze(ticker: str) -> dict:
    underlag, name = _underlag(ticker)
    prompt = _ANALYZE_PROMPT.format(underlag=underlag)
    result = ch.run(prompt, _TOOLS, timeout=150)
    if "error" in result or not (result.get("bull_case") or result.get("bear_case")):
        return {"ticker": ticker, "name": name, "error": result.get("error", "tomt svar")}
    return {"ticker": ticker, "name": name, "bull_case": result.get("bull_case"),
            "bear_case": result.get("bear_case"), "competitors": result.get("competitors")}


def ask(ticker: str, question: str) -> dict:
    underlag, name = _underlag(ticker)
    prompt = _ASK_PROMPT.format(underlag=underlag, name=name, ticker=ticker, question=question)
    result = ch.run(prompt, _TOOLS, timeout=120, text_fallback_key="answer")
    if "error" in result or not result.get("answer"):
        return {"ticker": ticker, "answer": None, "error": result.get("error", "tomt svar")}
    return {"ticker": ticker, "answer": result["answer"]}


def _latest_report(ticker: str) -> Optional[dict]:
    """Senaste FAKTISKA rapport-PM (is_report_pm – skiljer en riktig rapport
    från t.ex. en inbjudan till rapportpresentationen, samma lärdom
    quality_screener._company_context() redan betalat för) ur MFN-cachen
    (kan vara topplad av avanza.avanza_news_as_mfn_items() om MFN självt är
    fruset, se mfn_fetch.refresh_universe). None om ingen hittas."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except (json.JSONDecodeError, OSError):
        return None
    from altdata.mfn_fundamentals import is_report_pm
    reports = sorted([it for it in items if is_report_pm(it)],
                     key=lambda it: it.get("published", ""), reverse=True)
    return reports[0] if reports else None


_REPORT_ANALYSIS_PROMPT = """Du är en NEUTRAL, sansad investerarassistent.
Nedan är den SENASTE rapporten (pressmeddelande) för ETT bolag användaren
äger/följer.

BOLAG: {name} ({ticker})
SENASTE RAPPORT ({report_date} – {report_title}):
{report_text}

Gör FYRA saker:
1. "key_figures_summary": 2-4 meningar, sammanfatta de VIKTIGASTE
   nyckeltalen (omsättning, tillväxt, resultat/marginal, kassaflöde om
   angivet) OCH annan viktig information (större händelser, förvärv,
   kontrakt, guidance-ändringar) - EXAKT vad som står i rapporten ovan,
   gissa aldrig en siffra som inte anges där.
2. "ceo_commentary_assessment": 2-3 meningar - läs VD-ordet/kommentaren i
   rapporten. Är tonen substantiell och konkret, eller vag/floskelaktig?
   Backar VD:ns påståenden upp av siffrorna i SAMMA rapport, eller finns
   en diskrepans (t.ex. optimistisk ton trots svaga siffror, eller tvärtom)?
3. Använd WebSearch för att hitta PUBLICERADE ANALYTIKERESTIMAT (konsensus
   för omsättning/resultat) för SAMMA period som rapporten avser.
   "vs_estimates": om du hittar estimat, jämför utfallet mot dem (slog/
   missade/i linje, med siffror om möjligt). Hittar du INGA publicerade
   estimat (vanligt för mindre bolag) - skriv det ärligt ("inga
   publicerade estimat hittades för perioden") i stället för att gissa.
4. "verdict": "bull", "bear" eller "neutral" (om genuint blandat) - är
   rapporten SAMMANTAGET positiv eller negativ för caset? "verdict_reasoning":
   1-2 meningar som motiverar.

VIKTIGT: Skriv ALDRIG en köp/sälj-rekommendation. Allt i key_figures_summary/
ceo_commentary_assessment måste stå i rapporttexten ovan - allt i
vs_estimates måste komma från en faktisk sökträff, gissa aldrig siffror.

Svara ENDAST med kompakt JSON, ingen markdown:
{{"key_figures_summary": "...", "ceo_commentary_assessment": "...",
  "vs_estimates": "...", "verdict": "bull|bear|neutral", "verdict_reasoning": "..."}}
"""


def report_analysis(ticker: str, name: str = None) -> dict:
    """"Rapportanalys": sammanfattning av nyckeltal + VD-ord-bedömning ur
    SENASTE rapporten, plus jämförelse mot analytikerestimat (WebSearch -
    ÄRLIGT "inga estimat hittades" om inget publicerat finns, vanligt för
    mindre bolag, se _REPORT_ANALYSIS_PROMPT) och en bull/bear-slutsats för
    rapporten specifikt (skiljer sig från analyze()/DeepDiveBox, som
    bedömer HELA caset - det här är bara "var DEN HÄR rapporten bra eller
    dålig"). INGEN egen cache - alltid färskt vid klick, samma mönster som
    analyze()."""
    rep = _latest_report(ticker)
    if not rep:
        return {"ticker": ticker, "error": "ingen rapport hittad i MFN-cachen för den här tickern"}
    text = (rep.get("text") or "")[:config.QUALITY_MAX_CHARS]
    if not text:
        return {"ticker": ticker, "error": "rapporten saknar text i cachen"}
    if not name:
        holding = _holding(ticker)
        quality = _csv_row(Path(config.anchor(config.RESULTS_DIR)) / "quality_shortlist.csv", ticker)
        name = (holding or {}).get("name") or (quality or {}).get("name") or ticker
    prompt = _REPORT_ANALYSIS_PROMPT.format(
        name=name, ticker=ticker,
        report_date=(rep.get("published") or "")[:10],
        report_title=rep.get("title") or "", report_text=text)
    result = ch.run(prompt, "WebSearch", timeout=150)
    if "error" in result or not result.get("key_figures_summary"):
        return {"ticker": ticker, "name": name, "error": result.get("error", "tomt svar")}
    return {"ticker": ticker, "name": name,
            "report_date": (rep.get("published") or "")[:10], "report_title": rep.get("title"),
            "key_figures_summary": result.get("key_figures_summary"),
            "ceo_commentary_assessment": result.get("ceo_commentary_assessment"),
            "vs_estimates": result.get("vs_estimates"),
            "verdict": result.get("verdict"), "verdict_reasoning": result.get("verdict_reasoning")}


_ETF_COMPOSITION_TTL_DAYS = 7

_ETF_COMPOSITION_PROMPT = """Du är en NEUTRAL research-assistent. Sök upp de
UNGEFÄR 10 STÖRSTA innehaven i ETF:en {name} (ticker {ticker}) samt dess
sektor- och geografiska fördelning, från en tillförlitlig källa (t.ex.
fondbolagets egen sida, justetf.com, morningstar.se eller Avanzas egen sida
för fonden - avanza.se/fonder eller sök "{ticker} avanza innehav"). Ange
källa och datum om det anges i källan.

Svara ENDAST med kompakt JSON, ingen markdown:
{{"top_holdings": [{{"name": "...", "weight_pct": ...}}, ...],
  "sectors": [{{"name": "...", "weight_pct": ...}}, ...],
  "regions": [{{"name": "...", "weight_pct": ...}}, ...],
  "as_of": "<datum om angivet i källan, annars null>",
  "source": "<källans namn, t.ex. 'ishares.com'>"}}
Hittar du inget för ett fält (t.ex. ingen geografisk fördelning angiven) -
sätt det fältet till en tom lista. Hitta ALDRIG på siffror eller innehav du
inte faktiskt hittat i en källa."""


def _etf_cache_path(ticker: str) -> Path:
    d = Path(config.anchor("cache/etf_composition"))
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ticker.upper()}.json"


def etf_composition(ticker: str, name: str = None) -> dict:
    """ETF:ens ~10 största innehav + sektor-/geografisk fördelning, via
    headless Claude + WebSearch. Ingen Avanza-endpoint hittad för detta
    (VERIFIERAT 2026-07-22: flera varianter av /_api/market-guide/stock/
    {{id}}/holdings, /_api/fund-guide/{{id}} m.fl. gav antingen 404 eller ett
    tomt {{}} - trots att avanza.se:s EGEN webbsida visar innehav/länder/
    branscher-flikar för samma instrument, så det finns uppenbarligen en
    endpoint, bara inte en vi hittat via gissning).

    Cachas 7 dagar (cache/etf_composition/<ticker>.json, TTL i
    _ETF_COMPOSITION_TTL_DAYS) - sammansättningen ändras långsamt, och ett
    WebSearch-anrop tar ~2-3 min, för långsamt för att göra om vid varje
    sidvisning. name: valfritt (bättre sökträff om det skickas med, t.ex.
    "VanEck Semiconductor UCITS ETF" i stället för bara "VVSM.DE")."""
    cp = _etf_cache_path(ticker)
    if cp.exists():
        try:
            cached = json.loads(cp.read_text(encoding="utf-8"))
            age_days = (datetime.now(timezone.utc) -
                        datetime.fromisoformat(cached["cached_at"])).days
            if age_days < _ETF_COMPOSITION_TTL_DAYS:
                return cached
        except Exception:  # noqa: BLE001 – trasig/gammal cache-fil -> hämta om
            pass
    prompt = _ETF_COMPOSITION_PROMPT.format(name=name or ticker, ticker=ticker)
    result = ch.run(prompt, _TOOLS, timeout=170)
    if "error" in result or not result.get("top_holdings"):
        return {"ticker": ticker, "error": result.get("error", "tomt svar")}
    out = {"ticker": ticker,
           "top_holdings": result.get("top_holdings") or [],
           "sectors": result.get("sectors") or [],
           "regions": result.get("regions") or [],
           "as_of": result.get("as_of"),
           "source": result.get("source"),
           "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


_ETF_ANALYZE_PROMPT = """Du är en NEUTRAL, sansad investerarassistent. Nedan är
sammansättningen av en ETF som användaren REDAN ÄGER (eller följer).

FOND: {name} ({ticker})
STÖRSTA INNEHAV:
{holdings_lines}
SEKTORFÖRDELNING: {sectors_line}
GEOGRAFISK FÖRDELNING: {regions_line}

Använd WebSearch vid behov för att bedöma fonden UTIFRÅN INNEHAVEN OVAN:

1. "quality": ett kvalitetsbetyg 1-5 (5=utmärkt) för de STÖRSTA INNEHAVEN
   SAMMANTAGET (affärskvalitet: lönsamhet, tillväxt, konkurrensläge,
   värdering i stort) - INTE ett betyg på fonden som produkt (avgift m.m.).
   Detta är EN NY bedömning, inte ett snitt av några existerande betyg -
   sök upp faktisk info om du är osäker på ett innehav, gissa aldrig.
2. "quality_reasoning": 2-3 meningar som motiverar betyget, namnge gärna
   ett par av de största innehaven som exempel.
3. "bull_case": 2-4 meningar, de starkaste ärliga argumenten för att
   fortsätta äga fonden just nu.
4. "bear_case": 2-4 meningar, de starkaste riskerna/motargumenten - lika
   ärligt och konkret som bull_case.
5. "concentration_note": 1-2 meningar om koncentrationsrisk OM relevant
   (t.ex. om en sektor/region/enskilt innehav dominerar kraftigt jämfört
   med en bred indexfond), annars null.

VIKTIGT: Skriv ALDRIG en köp/sälj-rekommendation. Gissa aldrig siffror -
bara resonemang/orsaker får komma från sökning.

Svara ENDAST med kompakt JSON, ingen markdown:
{{"quality": <1-5 eller null>, "quality_reasoning": "...", "bull_case": "...",
  "bear_case": "...", "concentration_note": "..." eller null}}
"""


def etf_analyze(ticker: str, name: str = None) -> dict:
    """Bull/bear + ETT LLM-bedömt kvalitetsbetyg (1-5) för en ETF:s STÖRSTA
    INNEHAV sammantaget - INTE ett snitt av modellens per-aktie-betyg (de
    täcker bara svenska börsbolag; en global ETF:s största innehav är
    typiskt utländska jätteboalg som Nvidia/Apple utan någon sådan poäng
    att snitta över, se beslut 2026-07-22). Samma kvalitativa disciplin
    som quality_screener.py, fast riktad mot en fonds innehav i stort i
    stället för ett enskilt bolags rapport.

    Bygger på etf_composition()s redan kända (cachade 7 dagar) innehavs-
    lista som kontext - undviker att söka efter "vad äger fonden" två
    gånger. Görs INGEN egen server-cache här (till skillnad från
    etf_composition) - samma "alltid färskt vid klick"-mönster som
    analyze() för enskilda aktier, eftersom bull/bear-bedömningen är mer
    tidskänslig än den relativt stabila innehavslistan.

    OBS prestandan: om etf_composition() INTE redan är cachad (kall cache)
    tar detta anropet self ~150s + composition-hämtningens egna ~80-170s -
    frontend bör därför hämta/visa sammansättningen FÖRST (samma ordning
    som EtfCompositionBox → EtfDeepDiveBox på aktiedetaljsidan) så den
    här funktionen nästan alltid träffar en varm cache för composition-
    delen."""
    comp = etf_composition(ticker, name)
    if comp.get("error") or not comp.get("top_holdings"):
        return {"ticker": ticker, "name": name or ticker,
                "error": comp.get("error", "ingen sammansättning hittad – hämta sammansättningen först")}
    holdings_lines = "\n".join(
        f"  - {h.get('name')}: {h.get('weight_pct')}%" for h in comp["top_holdings"])
    sectors_line = ", ".join(
        f"{s.get('name')} {s.get('weight_pct')}%" for s in comp.get("sectors") or []) or "okänd"
    regions_line = ", ".join(
        f"{r.get('name')} {r.get('weight_pct')}%" for r in comp.get("regions") or []) or "okänd"
    prompt = _ETF_ANALYZE_PROMPT.format(name=name or ticker, ticker=ticker,
                                         holdings_lines=holdings_lines,
                                         sectors_line=sectors_line, regions_line=regions_line)
    result = ch.run(prompt, _TOOLS, timeout=150)
    if "error" in result or not (result.get("bull_case") or result.get("bear_case")):
        return {"ticker": ticker, "name": name or ticker, "error": result.get("error", "tomt svar")}
    return {"ticker": ticker, "name": name or ticker,
            "quality": result.get("quality"), "quality_reasoning": result.get("quality_reasoning"),
            "bull_case": result.get("bull_case"), "bear_case": result.get("bear_case"),
            "concentration_note": result.get("concentration_note")}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    tk = sys.argv[1]
    if "--ask" in sys.argv:
        q = sys.argv[sys.argv.index("--ask") + 1]
        out = ask(tk, q)
    elif "--etf" in sys.argv:
        out = etf_composition(tk)
    elif "--etf-analyze" in sys.argv:
        out = etf_analyze(tk)
    elif "--report" in sys.argv:
        out = report_analysis(tk)
    else:
        out = analyze(tk)
    print(json.dumps(out, ensure_ascii=False, indent=2))
