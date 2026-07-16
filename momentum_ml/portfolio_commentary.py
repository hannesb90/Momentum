"""
portfolio_commentary.py – en veckovis, läsvärd "förvaltarkommentar" som
sammanfattar din portfölj i klartext PER INNEHAV: vikt, vinst/förlust,
kvalitets-/kvant-/momentum-betyg, fundamenta-flaggor, sektor, kommande
rapportdatum och färsk nyhets-/PM-sammanfattning (om insight_report.py
körts) – inte bara hink-fördelning. Ren syntes av data som redan finns,
ingen ny datakälla, inget nytt verktyg, inga tools alls i headless-anropet
(bara text in, text ut). REN NARRATIV, ALDRIG SIGNAL, samma disciplin som
insight_report.py.

Körs veckovis (måndagar), inte nattligt – det här är en syntes över tid,
inte en daglig uppdatering.

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

_PROMPT = """Du är en NEUTRAL, sansad portföljanalytiker. Nedan är hela
analysunderlaget för en persons portfölj (siffror redan beräknade – ingen
sökning, ingen ny data), MED ett avsnitt PER INNEHAV (vikt, vinst/förlust,
modellens kvalitets-/kvant-/momentum-betyg, fundamenta-flaggor, sektor,
kommande rapportdatum, färsk nyhets-/PM-sammanfattning om sådan finns).

Skriv en förvaltarkommentar på SVENSKA (8-12 meningar, löpande text, inga
punktlistor). Den ska vara KONKRET, inte bara hink-fördelning:
  - Nämn MINST 3 SPECIFIKA innehav vid namn med ett konkret skäl ur
    underlaget (t.ex. "Acconeer är upp X% och kvalitetsbetyget är starkt",
    "Swedbank flaggas för hög skuldsättning", "Smart Eye rapporterar om N
    dagar"). Inga vaga formuleringar ("några innehav har gått bra") när
    underlaget har namngivna siffror att peka på.
  - Kommentera SEKTOREXPONERING om ett innehav sticker ut (koncentration,
    en sektor som bär större delen av vinsten/förlusten).
  - Nämn kommande RAPPORTER inom de närmaste veckorna om någon finns i
    underlaget ("förväntningar").
  - Väv in exit-alarm/säljvakt/fundamenta-flaggor på innehavsnivå, inte
    bara som en generisk varningsrad.
  - Avsluta med vad MODELLEN skulle ändra (Nästa köp-planen, i klartext).

VIKTIGT: sammanfatta och förklara siffrorna i underlaget, gissa ALDRIG på ny
data (ingen sökning tillgänglig här). Skriv ALDRIG en köp/sälj-rekommendation
utöver vad som redan står i underlaget – det här är en läsvärd sammanfattning
av redan beräknad data, inte nytt investeringsråd.

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
        sec = pf._safe(lambda: pf._sector_of(tk), "", "sektor") if tk else ""
        if sec:
            parts.append(f"sektor {sec}")
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
    # Tomt allowedTools + dontAsk = inga verktyg alls tillåtna (ren textsyntes
    # av underlaget ovan, ingen sökning, ingen filåtkomst).
    result = ch.run(prompt, "", timeout=150)
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
