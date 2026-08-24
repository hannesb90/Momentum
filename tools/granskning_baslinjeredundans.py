"""GRANSKNING: MÄTTES REGLERNA MOT EN BASLINJE SOM REDAN GÖR DERAS JOBB?

Nästan varje add-on i programmet prövades mot STACK_H. Men STACK_H innehåller
redan fyra mekanismer som gör delar av samma arbete:

  hysteres rank 35   ejicerar namn vars rank förfallit — samma jobb som en
                     exitregel, en swapregel och delvis en utjämningsregel
  NTZ 0,005          fryser små viktändringar — samma jobb som en bytesbudget
                     och en minsta innehavstid
  ERC (invvol^1,5)   dämpar volatila namn — samma jobb som ett riskfilter
  FR-overlay         nedviktar obekräftade namn — samma jobb som ett kvalitetsfilter

Om en regel prövas mot en baslinje som redan absorberat dess effekt kan den
bara mätas på det MARGINELLA tillskottet. Ett nollresultat betyder då "tillför
inget utöver hysteresen", inte "mekanismen saknar värde".

Detta skript kör samma regler mot TVÅ baslinjer:

  BAR      Control C + invers vol, inga overlays        (use_erc/fr/hyst/ntz av)
  STACK_H  den fullständiga frysta modellen

Om en regel är positiv mot BAR i båda fönstren men noll mot STACK_H, då var
förkastandet ett artefakt av baslinjevalet — mekanismen fungerar, den är bara
redundant med hysteresen.

Om den är noll mot BÅDA, är förkastandet äkta.

Kör: /opt/momentum/venv/bin/python tools/granskning_baslinjeredundans.py
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/granskning_baslinjeredundans_results.json"

BAR = dict(use_erc=False, use_fr=False, use_hysteresis=False, use_ntz=False)
FULL = dict()


# ---------- regel 1: poängutjämning (A3) ----------
def rank_utjamnad(F, m=3):
    ema, ut = {}, {}
    a = 2.0 / (m + 1.0)
    for dt in F["eval_dates"]:
        nya = []
        for r in F["rankings"][dt]:
            k, sc = r["kod"], r["score"]
            ema[k] = sc if k not in ema else a * sc + (1 - a) * ema[k]
            nya.append({"kod": k, "score": float(ema[k])})
        nya.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = nya
    return ut


# ---------- regel 2: köpband (rekrytera under toppen) ----------
# hanteras via kor():s kopband-parameter

# ---------- regel 3: kortare lookback som rankning ----------
def rank_blandad(F, vikt_kort=0.3):
    """Blandar in den snabbaste tillgängliga informationen: förändringen i
    poäng sedan förra panelen, som proxy för kort momentum."""
    dts = F["eval_dates"]
    forra, ut = {}, {}
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        n = len(raw)
        pct = {r["kod"]: 1.0 - i / max(1, n - 1) for i, r in enumerate(raw)}
        d = {k: pct[k] - forra.get(k, pct[k]) for k in pct}
        lo, hi = min(d.values()), max(d.values())
        rng = max(1e-9, hi - lo)
        nya = [{"kod": r["kod"],
                "score": (1 - vikt_kort) * r["score"] + vikt_kort * ((d[r["kod"]] - lo) / rng)}
               for r in raw]
        nya.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = nya
        forra = pct
    return ut


def kor(F, extra, rankings=None):
    kw = {x: y for x, y in F.items() if x != "rankings"}
    return S.kor(rankings=rankings if rankings is not None else F["rankings"], **kw, **extra)[0]


def main():
    ut = {"version": "GRANSKNING_BASLINJEREDUNDANS_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "fraga": "Föll reglerna för att de saknar värde, eller för att STACK_H "
                   "redan gör deras jobb?", "regler": {}}

    baslinjer = {}
    for namn, extra in (("BAR", BAR), ("STACK_H", FULL)):
        baslinjer[namn] = {"26": kor(S.F26, extra), "19": kor(S.F19, extra)}
        s26, s19 = S.stat(baslinjer[namn]["26"]), S.stat(baslinjer[namn]["19"])
        print(f"baslinje {namn:<8} 2020-2026 {s26['cagr']:>7.2%}  "
              f"2014-2019 {s19['cagr']:>7.2%}  Sharpe {s26['sharpe']:.3f}/{s19['sharpe']:.3f}")
        ut.setdefault("baslinjer", {})[namn] = {"f2020_2026": s26, "f2014_2019": s19}
    if abs(S.stat(baslinjer["STACK_H"]["26"])["cagr"] - 0.1356) > 0.004:
        sys.exit("AVBRYTER: STACK_H reproducerar inte")

    regler = [
        ("poängutjämning EMA3", lambda F, e: kor(F, e, rank_utjamnad(F, 3))),
        ("poängutjämning EMA2", lambda F, e: kor(F, e, rank_utjamnad(F, 2))),
        ("köpband rank 11-40", lambda F, e: kor(F, {**e, "kopband": (11, 40)})),
        ("köpband rank 16-45", lambda F, e: kor(F, {**e, "kopband": (16, 45)})),
        ("kort momentum 30 % inblandat", lambda F, e: kor(F, e, rank_blandad(F, 0.3))),
        ("kort momentum 15 % inblandat", lambda F, e: kor(F, e, rank_blandad(F, 0.15))),
        ("N=20 i stället för 30", lambda F, e: kor(F, {**e, "N": 20})),
        ("N=40 i stället för 30", lambda F, e: kor(F, {**e, "N": 40})),
    ]

    print(f"\n{'regel':<32}{'mot BAR 26':>12}{'19':>9}{'  bådaBAR':>10}"
          f"{'mot STACK_H 26':>16}{'19':>9}{'  bådaSH':>9}")
    for namn, fn in regler:
        rad = {}
        for bl, extra in (("BAR", BAR), ("STACK_H", FULL)):
            a26 = fn(S.F26, extra); a19 = fn(S.F19, extra)
            d26 = S.boot(a26, baslinjer[bl]["26"]); d19 = S.boot(a19, baslinjer[bl]["19"])
            rad[bl] = {"f2020_2026": {**S.stat(a26), **d26},
                       "f2014_2019": {**S.stat(a19), **d19},
                       "bada_positiva": bool(d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0)}
        ut["regler"][namn] = rad
        b, s = rad["BAR"], rad["STACK_H"]
        print(f"{namn:<32}{b['f2020_2026']['delta_cagr']:>+12.2%}"
              f"{b['f2014_2019']['delta_cagr']:>+9.2%}{'JA' if b['bada_positiva'] else '-':>10}"
              f"{s['f2020_2026']['delta_cagr']:>+16.2%}"
              f"{s['f2014_2019']['delta_cagr']:>+9.2%}{'JA' if s['bada_positiva'] else '-':>9}")

    print("\nDOM PER REGEL")
    ut["dom"] = {}
    for namn in ut["regler"]:
        b = ut["regler"][namn]["BAR"]["bada_positiva"]
        s = ut["regler"][namn]["STACK_H"]["bada_positiva"]
        if b and not s:
            d = "REDUNDANT — fungerar mot bar modell, absorberad av STACK_H"
        elif b and s:
            d = "FUNGERAR MOT BÅDA"
        elif s and not b:
            d = "BEROENDE — kräver STACK_H:s overlays"
        else:
            d = "ÄKTA FÖRKASTANDE — noll mot båda baslinjerna"
        ut["dom"][namn] = d
        print(f"  {namn:<32}{d}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
