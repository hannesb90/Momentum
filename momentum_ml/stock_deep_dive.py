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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    tk = sys.argv[1]
    if "--ask" in sys.argv:
        q = sys.argv[sys.argv.index("--ask") + 1]
        out = ask(tk, q)
    else:
        out = analyze(tk)
    print(json.dumps(out, ensure_ascii=False, indent=2))
