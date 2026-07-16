"""
portfolio_commentary.py – en månatlig, läsvärd "förvaltarkommentar" som
sammanfattar din portfölj i klartext: vad som driver den, vad som skaver,
vad modellen skulle ändra. Ren syntes av data som redan finns (hink-drift,
varningar, exit-alarm, säljvakt, Nästa köp-planen) – ingen ny datakälla,
inget nytt verktyg, inga tools alls i headless-anropet (bara text in, text
ut). REN NARRATIV, ALDRIG SIGNAL, samma disciplin som insight_report.py.

Körs månadsvis (1:a varje månad), inte nattligt – det här är en syntes över
tid, inte en daglig uppdatering.

    python portfolio_commentary.py
"""
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
sökning, ingen ny data). Skriv en kort förvaltarkommentar på SVENSKA (4-7
meningar, löpande text, inga punktlistor):
  - Vad DRIVER portföljen just nu (vad som gått bra/dåligt).
  - Vad SKAVER (varningar, obalanser, exit-alarm, säljvakt).
  - Vad MODELLEN skulle ändra (Nästa köp-planen, i klartext).

VIKTIGT: sammanfatta och förklara siffrorna, gissa inte på nytt data. Skriv
ALDRIG en köp/sälj-rekommendation utöver vad som redan står i underlaget –
det här är en läsvärd sammanfattning, inte nytt investeringsråd.

Svara ENDAST med kompakt JSON, ingen markdown: {{"commentary": "..."}}

UNDERLAG:
{underlag}
"""


def _underlag():
    rows = pf.load_holdings()
    d = pf.compute(rows)
    nb = pf._safe(lambda: pf.next_buy(rows), {}, "nästa köp")
    exit_path = pf._results_dir() / "exit_signals.json"
    exits = json.loads(exit_path.read_text(encoding="utf-8")) if exit_path.exists() else {}
    insight_path = pf._results_dir() / "insight_report.json"
    insight = json.loads(insight_path.read_text(encoding="utf-8")) if insight_path.exists() else {}

    lines = [f"Totalt värde: {d['total']:,.0f} kr, {len(rows)} innehav".replace(",", " ")]
    lines.append("Hinkar (nu vs mål): " + ", ".join(
        f"{pf.BUCKET_LABEL[b]} {d['buckets'][b]:.0%} (mål {d['target'].get(b, 0):.0%})"
        for b in pf.BUCKETS))
    if d.get("warnings"):
        lines.append("Varningar: " + "; ".join(d["warnings"]))
    if nb.get("rows"):
        lines.append("Nästa köp-planen (" + str(nb.get("amount")) + " kr): " + "; ".join(
            f"{r['ticker']} {r['kr']} kr ({r['bucket']})" for r in nb["rows"]))
    if nb.get("sell_watch"):
        lines.append("Säljvakt: " + "; ".join(
            f"{s['name']} ({s.get('action')})" for s in nb["sell_watch"] if s.get("level", 0) >= 1))
    reds = [e for e in (exits.get("holdings") or []) if e.get("tier") == "red"]
    if reds:
        lines.append("Exit-alarm RÖTT: " + ", ".join(e["name"] for e in reds))
    if insight.get("companies"):
        lines.append("Färska sammanfattningar: " + " | ".join(
            f"{c['ticker']}: {c['summary']}" for c in insight["companies"] if c.get("held")))
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
