"""Fore/efter-diff: Spar B valutabuggfix. Jamfor gammal (buggig, sakerhetskopierad)
mot ny (reparerad) validated-data, per tabell och monetart falt."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
GAMMAL = V2 / "validated/_SUPERSEDED_2026-08-08_valutabugg"
NY = V2 / "validated/fundamentals"

MONETARA_FALT = [
    "revenues", "gross_Income", "operating_Income", "profit_Before_Tax",
    "profit_To_Equity_Holders", "total_Assets", "total_Equity",
    "total_Liabilities_And_Equity", "current_Assets", "current_Liabilities",
    "non_Current_Assets", "non_Current_Liabilities", "cash_And_Equivalents",
    "net_Debt", "tangible_Assets", "intangible_Assets", "financial_Assets",
    "cash_Flow_From_Operating_Activities", "cash_Flow_From_Investing_Activities",
    "cash_Flow_From_Financing_Activities", "cash_Flow_For_The_Year", "free_Cash_Flow",
    "earnings_Per_Share", "dividend",
]


def diff_tabell(namn: str, fil: str) -> dict:
    gammal = {(r["insid"], r["year"], r.get("period")): r
              for r in json.loads((GAMMAL / fil).read_text(encoding="utf-8"))}
    ny = {(r["insid"], r["year"], r.get("period")): r
          for r in json.loads((NY / fil).read_text(encoding="utf-8"))}
    assert set(gammal) == set(ny), f"{namn}: radnycklar skiljer sig - INTE bara varden andrade!"

    per_falt = {}
    sek_orörd = {"testade": 0, "avvikande": 0}
    berorda_kod = set()
    berorda_valuta = defaultdict(set)
    for falt in MONETARA_FALT:
        andrade, faktorer = 0, []
        for nyckel, g in gammal.items():
            n = ny[nyckel]
            gv, nv = g.get(falt), n.get(falt)
            cur = g.get("currency")
            if cur == "SEK":
                sek_orörd["testade"] += 1
                if gv != nv and not (gv is None and nv is None):
                    if gv is None or nv is None or abs((gv or 0) - (nv or 0)) > 1e-6:
                        sek_orörd["avvikande"] += 1
                continue
            if gv is None or nv is None:
                continue
            if gv == 0:
                continue
            if gv != nv:
                andrade += 1
                faktorer.append(gv / nv if nv else None)
                berorda_kod.add(g.get("kod"))
                berorda_valuta[cur].add(g.get("kod"))
        faktorer = [f for f in faktorer if f]
        per_falt[falt] = {
            "andrade_rader": andrade,
            "max_forandringsfaktor": max(faktorer) if faktorer else None,
            "median_forandringsfaktor": statistics.median(faktorer) if faktorer else None,
            "min_forandringsfaktor": min(faktorer) if faktorer else None,
        }
    return {
        "n_rader_totalt": len(gammal),
        "n_instrument_berorda": len(berorda_kod),
        "berorda_kod": sorted(berorda_kod),
        "berorda_valutor": {k: sorted(v) for k, v in berorda_valuta.items()},
        "sek_kontroll": sek_orörd,
        "per_falt": per_falt,
    }


def main() -> None:
    resultat = {}
    for namn, fil in (("ar", "fundamentals_year_validated.json"),
                       ("kvartal", "fundamentals_quarter_validated.json"),
                       ("r12", "fundamentals_r12_validated.json")):
        resultat[namn] = diff_tabell(namn, fil)
        r = resultat[namn]
        print(f"== {namn} ==")
        print(f"  {r['n_rader_totalt']} rader totalt, {r['n_instrument_berorda']} instrument berörda")
        print(f"  SEK-kontroll: {r['sek_kontroll']['testade']} testade, "
              f"{r['sek_kontroll']['avvikande']} oväntat ändrade (ska vara 0)")
        print(f"  valutor berörda: {list(r['berorda_valutor'].keys())}")
        for falt, s in r["per_falt"].items():
            if s["andrade_rader"]:
                print(f"    {falt:38s} {s['andrade_rader']:5d} rader  "
                      f"median×{s['median_forandringsfaktor']:.3f}  "
                      f"max×{s['max_forandringsfaktor']:.3f}  min×{s['min_forandringsfaktor']:.3f}")

    (V2 / "docs/probes/sparB_valutafix_diff.json").write_text(
        json.dumps(resultat, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefakt: docs/probes/sparB_valutafix_diff.json")


if __name__ == "__main__":
    main()
