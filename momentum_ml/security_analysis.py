"""
security_analysis.py – på-begäran AI-analys FÖR ETT BOLAG i Skanner-fliken:
en läsvärd sammanfattning (samma "REN NARRATIV, ALDRIG SIGNAL"-disciplin
som portfolio_commentary.py/insight_report.py) av VARFÖR modellens
poäng ser ut som de gör, plus hur en NY position i just detta bolag
skulle påverka DIN portfölj som helhet – inte bara bolaget isolerat.

Skiljer sig från insight_report.py (nattlig batch, ~20 bolag i förväg) och
portfolio_commentary.py (veckovis syntes över hela portföljen) genom att
vara ETT bolag, på begäran, från Skanner-knappen – samma mönster som
montrose_ticket.py:s on-demand headless-anrop från API:t (se
api/main.py:s /api/trade-ticket, som redan kör headless Claude synkront
inom en request). Headless Sonnet + WebSearch, samma låsning som resten
(ingen Montrose, ingen filåtkomst) – kan bara läsa/sammanfatta, aldrig
agera.

Portföljpåverkan beräknas LOKALT (portfolio.compute() före/efter en
HYPOTETISK extra rad, sparas ALDRIG till riktiga innehav) – inget LLM
behövs för siffrorna, bara för att förklara dem i klartext.

    python security_analysis.py AZA.ST
    python security_analysis.py AZA.ST --amount 5000
"""
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402
import claude_headless as ch  # noqa: E402
from altdata import manual_scan as ms  # noqa: E402

_TOOLS = "WebSearch"

# Samma breda namn-baserade heuristik som sync_montrose_holdings.py:s
# _guess_bucket() – återanvänds inte direkt (den modulen importerar redan
# portfolio, vi vill undvika ett cirkulärt beroende), men EXAKT samma regler.
_LEVERAGE_WORDS = ("bull", "bear", "x2", "x3", "leverag", "daily")
_BROAD_NAME_HINTS = ("world", "acwi", "s&p 500", "global", "msci")


def _guess_bucket(ticker: str, name: str) -> str:
    nl = (name or "").lower()
    tl = (ticker or "").upper()
    if any(w in nl or w in tl.lower() for w in _LEVERAGE_WORDS):
        return "leverage"
    if any(h in nl for h in _BROAD_NAME_HINTS):
        return "broad"
    if tl.endswith(".ST"):
        return "sweden"
    return "theme"


def _portfolio_impact(ticker: str, name: str, amount: float) -> dict:
    """REN SIMULERING – lägger ALDRIG till en riktig innehavsrad. Jämför
    portfolio.compute() FÖRE/EFTER en hypotetisk extra position: hink-
    balans, om bolaget delar tema/sektor med redan stora positioner
    (koncentrationsrisk osynlig om man bara tittar på bolaget isolerat)."""
    bucket = _guess_bucket(ticker, name)
    rows = pf.load_holdings()
    before = pf.compute(rows)
    hyp_rows = rows + [{"name": name or ticker, "ticker": ticker, "value": amount,
                        "bucket": bucket, "cost": amount, "shares": None, "buy_price": None}]
    after = pf.compute(hyp_rows)

    b_total, a_total = before.get("total") or 0.0, after.get("total") or 0.0
    bucket_pct = {
        b: {"before": round((before["buckets"].get(b, 0.0) / b_total) if b_total else 0.0, 4),
            "after": round((after["buckets"].get(b, 0.0) / a_total) if a_total else 0.0, 4)}
        for b in pf.BUCKETS
    }

    _, theme = pf._safe(lambda: pf._theme_of_labeled(ticker), ("", ""), "tema")
    same_theme_kr = 0.0
    if theme:
        for r in rows:
            tk = (r.get("ticker") or "").upper()
            if tk and pf._safe(lambda t=tk: pf._theme_of_labeled(t)[1], "", "tema") == theme:
                same_theme_kr += r.get("value", 0.0)

    return {
        "bucket": bucket, "amount": amount, "theme": theme or None,
        "new_position_share_of_portfolio": round(amount / a_total, 4) if a_total else None,
        "same_theme_existing_share_before": round(same_theme_kr / b_total, 4) if (b_total and theme) else None,
        "bucket_before_after": bucket_pct,
        "new_warnings": [w for w in after.get("warnings", []) if w not in before.get("warnings", [])],
    }


def _underlag(ticker: str, scan_result: dict, impact: dict) -> str:
    lines = [f"BOLAG: {scan_result.get('name')} ({ticker})",
             f"Helhetsbetyg (skanner-scenario): {scan_result.get('overall_score')}%"]
    vm = scan_result.get("value_metrics") or {}
    if vm.get("roe") is not None:
        lines.append(f"ROE {vm['roe']:.1%} (klarar bar: {vm.get('meets_roe_bar')}), "
                      f"skuld/EK {vm.get('debt_equity')} (klarar bar: {vm.get('meets_debt_bar')}), "
                      f"värderingszon: {vm.get('zone')}")
    for m, mo in (scan_result.get("models") or {}).items():
        if mo.get("score") is not None:
            lines.append(f"Modell {m}: {mo['score']:.3f} – {mo.get('why') or ''}")
        elif mo.get("excluded_reason"):
            lines.append(f"Modell {m}: skulle uteslutas – {mo['excluded_reason']}")
    if scan_result.get("positives"):
        lines.append("Gynnar aktien: " + "; ".join(scan_result["positives"]))
    if scan_result.get("negatives"):
        lines.append("Sänker betyget: " + "; ".join(scan_result["negatives"]))

    import altdata.avanza as av
    news = pf._safe(lambda: av.news_for_ticker(ticker, limit=5), [], "avanza-nyheter")
    if news:
        lines.append("\nFärska nyheter/PM (Avanza, verifierade):")
        for n in news:
            lines.append(f"  [{n.get('date')}] {n.get('headline')} – {n.get('intro')}")

    lines.append(f"\nPORTFÖLJPÅVERKAN av en hypotetisk ny position på {impact['amount']:.0f} kr "
                 f"(hink: {impact['bucket']}):")
    lines.append(f"  Andel av totala portföljen efter köp: {impact['new_position_share_of_portfolio']:.1%}"
                 if impact.get("new_position_share_of_portfolio") is not None else "  (kunde inte beräknas)")
    if impact.get("theme"):
        lines.append(f"  Tema/sektor: {impact['theme']}"
                      + (f" – redan {impact['same_theme_existing_share_before']:.1%} av portföljen INNAN detta köp"
                         if impact.get("same_theme_existing_share_before") else " – inget annat innehav i samma tema idag"))
    for b, pct in impact.get("bucket_before_after", {}).items():
        if abs(pct["after"] - pct["before"]) >= 0.005:
            lines.append(f"  Hink {b}: {pct['before']:.1%} → {pct['after']:.1%}")
    if impact.get("new_warnings"):
        lines.append("  NYA varningar detta köp skulle utlösa: " + "; ".join(impact["new_warnings"]))
    return "\n".join(lines)


_PROMPT = """Du är en NEUTRAL, sansad investerarassistent. Nedan är analysunderlaget
för ETT bolag (redan beräknade modellpoäng, färska nyheter, och hur en
hypotetisk ny position skulle påverka användarens PORTFÖLJ som helhet).

Använd WebSearch för att komplettera med bredare kontext/förklaring till varför
bolaget presterar som det gör (bransch, senaste händelser) – prioritera svenska
finansmedier (site:efn.se, site:omni.se/ekonomi) innan bredare sökning.

Skriv 4-8 meningar på SVENSKA, löpande text:
  1. Vad bolaget gör och varför modellens poäng ser ut som de gör (grundat i
     underlaget, inte gissat).
  2. VIKTIGAST: kommentera portföljpåverkan konkret – om bolaget delar tema/sektor
     med redan stora positioner (koncentrationsrisk), och hur hink-balansen
     skulle förändras. Detta är själva poängen med analysen, inte en fotnot.
  3. Nämn eventuella färska nyheter kort om relevanta.

VIKTIGT: Skriv ALDRIG en köp/sälj-rekommendation ("köp denna aktie",
"undvik denna") – bara vad som redan syns i modellens poäng och
portföljpåverkan, i klartext. Gissa aldrig siffror, bara ORSAKER får
komma från sökning.

Svara ENDAST med kompakt JSON, ingen markdown: {{"analysis": "..."}}

UNDERLAG:
{underlag}
"""


def analyze(ticker: str, overrides: Optional[dict] = None, segment: Optional[str] = None,
            amount: Optional[float] = None) -> dict:
    scan_result = ms.scan(ticker, overrides or {}, segment=segment)
    amount = float(amount or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000))
    impact = _portfolio_impact(ticker, scan_result.get("name"), amount)
    prompt = _PROMPT.format(underlag=_underlag(ticker, scan_result, impact))
    result = ch.run(prompt, _TOOLS, timeout=120)
    if "error" in result or not result.get("analysis"):
        return {"ticker": ticker, "impact": impact,
                "analysis": None, "error": result.get("error", "tomt svar")}
    return {"ticker": ticker, "impact": impact, "analysis": result["analysis"]}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    tk = sys.argv[1]
    amt = None
    if "--amount" in sys.argv:
        amt = float(sys.argv[sys.argv.index("--amount") + 1])
    out = analyze(tk, amount=amt)
    print(json.dumps(out, ensure_ascii=False, indent=2))
