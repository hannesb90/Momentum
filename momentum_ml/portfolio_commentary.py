"""
portfolio_commentary.py – en daglig, läsvärd "förvaltarkommentar" som
sammanfattar din portfölj i klartext PER INNEHAV (vikt, vinst/förlust,
kvalitets-/kvant-/momentum-betyg, fundamenta-flaggor, sektor, kommande
rapportdatum, färsk nyhets-/PM-sammanfattning) OCH PER SEKTOR (momentum
senaste 4/13/26 veckor, rotation in/ut) för sektorerna dina innehav faktiskt
tillhör – inte bara hink-fördelning.

Använder headless Claudes inbyggda WebSearch (låst, se _TOOLS nedan) för att
förklara VARFÖR en sektor/ett bolag rört sig ("X har fallit senaste tiden
till följd av Y, men bedöms fortsatt ha Z – därför inget skäl att korrigera
positionen"), inte bara vad siffrorna redan visar. REN NARRATIV, ALDRIG
SIGNAL – gäller fortfarande: kommentaren får resonera om huruvida en rörelse
ser tillfällig/strukturell ut, men ska ALDRIG skriva en ny köp/sälj-instruktion
utöver vad Nästa köp-planen/säljvakten redan säger.

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
<sektor/bolag>" – innan en bredare sökning som "<sektor> aktier <senaste
händelse>" eller "<bolag> nyheter". Skriv sedan analytiker-stil, konkret
orsak + bedömning, i stil med: "Halvledarsektorn har fallit tungt senaste
veckorna till följd av X, men bedöms fortsatt ha goda tillväxtutsikter och
är därför inte ett skäl att korrigera positionen." Gissa ALDRIG en orsak
utan att ha sökt fram den – hittar du inget, säg det kort istället.

Skriv en förvaltarkommentar på SVENSKA (10-15 meningar, löpande text, inga
punktlistor). Den ska vara KONKRET:
  - Nämn MINST 3 SPECIFIKA innehav vid namn med ett konkret skäl ur
    underlaget (t.ex. "Acconeer är upp X% och kvalitetsbetyget är starkt",
    "Swedbank flaggas för hög skuldsättning", "Smart Eye rapporterar om N
    dagar"). Inga vaga formuleringar ("några innehav har gått bra") när
    underlaget har namngivna siffror att peka på.
  - Kommentera MINST 1-2 SEKTORER/UNDERTEMAN med konkret momentum-siffra
    OCH en research-baserad förklaring till rörelsen (se ovan) – inte bara
    "sektorn har gått bra/dåligt". Använd UNDERLAGETS mest specifika nivå
    du har siffror för (PER FINT UNDERTEMA om det finns för innehavet,
    annars PER SEKTOR/GICS) – "Medicinsk utrustning" är mer läsvärt och
    precist än "Health Care" när båda finns.
  - Kommentera SEKTOREXPONERING om ett innehav sticker ut (koncentration,
    en sektor som bär större delen av vinsten/förlusten).
  - Nämn kommande RAPPORTER inom de närmaste veckorna om någon finns i
    underlaget ("förväntningar").
  - Väv in exit-alarm/säljvakt/fundamenta-flaggor på innehavsnivå, inte
    bara som en generisk varningsrad.
  - Avsluta med vad MODELLEN skulle ändra (Nästa köp-planen, i klartext).

VIKTIGT: sammanfatta och förklara siffrorna i underlaget korrekt – gissa
aldrig på SIFFROR (bara på ORSAKER får du använda sökning). Skriv ALDRIG en
ny köp/sälj-rekommendation utöver vad som redan står i underlaget (Nästa
köp-planen/säljvakten) – du får bedöma om en rörelse ser tillfällig eller
strukturell ut, men det är fortfarande läsvärd bakgrund, inte nytt
investeringsråd.

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


if __name__ == "__main__":
    build()
