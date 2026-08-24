"""A3 — POÄNGUTJÄMNING (legacy test08, aldrig prövad på H0)

H0-poängen är 0,5 x percentilrank(12m) + 0,5 x percentilrank(18m), beräknad på
nytt varje panel. Den är brusig: rank 1 och rank 30 skiljs av 0,1055
percentilenheter, och ett bra kvartal flyttar ett bolag 13 platser. Toppen blir
därmed en lista över namn som nyligen accelererat — och acceleration
medelåterför.

Utjämning dämpar precis det. Ett namn måste hålla sig högt över flera paneler
för att nå toppen, i stället för att ta sig dit på ett enda kvartal.

Legacy (test08, mot LambdaRank-baslinjen): EMA2/EMA3 förbättrade ALLA perioder
i första körningen 2026-07-26, men omvalideringen 2026-07-30 höll inte —
holdout-förbättringen +3,05 pp föll bort och span4 blev marginellt bäst.
Oavgjord, och aldrig prövad på H0.

VARIANTER
  EMA span 2, 3, 4 paneler
  Enkelt glidande medel över 2, 3, 4 paneler
  Kombination: 0,5 x aktuell poäng + 0,5 x EMA3   (halv dämpning)

Utjämnade poäng skickas rakt in i den kanoniska motorn via `rankings`-
parametern, så inget annat i STACK_H ändras.

PLACEBO: regeln byter ut vilka namn som ägs, så den jämförs mot slumpmässig
omkastning av lika många namn per panel.

Kör: /opt/momentum/venv/bin/python tools/a3_poangutjamning.py
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

OUT = V2 / "research_k/a3_poangutjamning_results.json"
RNG = np.random.default_rng(20260816)


def utjamna(F, metod, m, blandning=None):
    """Bygger nya rankings med utjämnad poäng. Historik per kod, inga framtida värden."""
    dts = F["eval_dates"]
    hist = defaultdict(list)          # kod -> [(panelindex, poäng)]
    ut = {}
    alfa = 2.0 / (m + 1.0)
    ema = {}
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        nya = []
        for r in raw:
            k, sc = r["kod"], r["score"]
            hist[k].append(sc)
            if metod == "ema":
                ema[k] = sc if k not in ema else alfa * sc + (1 - alfa) * ema[k]
                v = ema[k]
            else:                      # glidande medel över de m senaste panelerna
                v = float(np.mean(hist[k][-m:]))
            if blandning is not None:
                v = blandning * sc + (1 - blandning) * v
            nya.append({"kod": k, "score": float(v)})
        nya.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = nya
    return ut


def placebo_rankings(F, n_kast):
    """Kastar om n_kast slumpmässiga namn inom topp-60 varje panel."""
    ut = {}
    for dt in F["eval_dates"]:
        raw = [dict(r) for r in F["rankings"][dt]]
        topp = raw[:60]
        m = min(n_kast, len(topp))
        if m >= 2:
            idx = RNG.choice(len(topp), size=m, replace=False)
            poang = [topp[i]["score"] for i in idx]
            RNG.shuffle(poang)
            for i, p in zip(idx, poang):
                topp[i]["score"] = p
        raw = topp + raw[60:]
        raw.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = raw
    return ut


def kor_med(F, rankings):
    kw = {x: y for x, y in F.items() if x != "rankings"}
    return S.kor(rankings=rankings, **kw)[0]


def byten(F, rankings, N=30):
    """Hur många namn i topp-N skiljer sig från originalrankningen, per panel."""
    d = []
    for dt in F["eval_dates"]:
        a = {r["kod"] for r in F["rankings"][dt][:N]}
        b = {r["kod"] for r in rankings[dt][:N]}
        d.append(len(a - b))
    return float(np.mean(d))


def main():
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    print(f"baslinjekontroll: STACK_H {S.stat(bas26)['cagr']:.2%} / {S.stat(bas19)['cagr']:.2%}")
    if abs(S.stat(bas26)["cagr"] - 0.1356) > 0.004:
        sys.exit("AVBRYTER: baslinjen reproducerar inte")

    ut = {"version": "A3_POANGUTJAMNING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "varianter": {}}
    varianter = [("EMA span 2", dict(metod="ema", m=2)),
                 ("EMA span 3", dict(metod="ema", m=3)),
                 ("EMA span 4", dict(metod="ema", m=4)),
                 ("glidande medel 2", dict(metod="ma", m=2)),
                 ("glidande medel 3", dict(metod="ma", m=3)),
                 ("glidande medel 4", dict(metod="ma", m=4)),
                 ("halv dämpning (0,5 + 0,5 EMA3)", dict(metod="ema", m=3, blandning=0.5))]

    print(f"\n  {'variant':<32}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}{'byten':>8}  repl")
    print(f"  {'STACK_H (obehandlad poäng)':<32}{S.stat(bas26)['cagr']:>8.2%}{'—':>9}"
          f"{S.stat(bas19)['cagr']:>9.2%}{'—':>9}")
    for namn, kw in varianter:
        r26, r19 = utjamna(S.F26, **kw), utjamna(S.F19, **kw)
        a26, a19 = kor_med(S.F26, r26), kor_med(S.F19, r19)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        b26, b19 = byten(S.F26, r26), byten(S.F19, r19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["varianter"][namn] = {"f2020_2026": {**S.stat(a26), **d26, "byten_topp30": round(b26, 2)},
                                 "f2014_2019": {**S.stat(a19), **d19, "byten_topp30": round(b19, 2)},
                                 "bada_positiva": bool(rep)}
        print(f"  {namn:<32}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{b26:>4.1f}/{b19:<3.1f}  {'JA' if rep else '-'}")

    # placebo för den bästa varianten, matchat på antal utbytta namn
    b = max(ut["varianter"], key=lambda k: min(ut["varianter"][k]["f2020_2026"]["delta_cagr"],
                                               ut["varianter"][k]["f2014_2019"]["delta_cagr"]))
    print(f"\nPLACEBO för bästa varianten ({b}) — slumpmässig omkastning av lika många "
          f"namn, 40 dragningar")
    ut["placebo"] = {"variant": b}
    for w_, F, bas, namn in (("2020_2026", S.F26, bas26, "2020-2026"),
                             ("2014_2019", S.F19, bas19, "2014-2019")):
        nk = ut["varianter"][b][f"f{w_}"]["byten_topp30"]
        d = np.array([S.boot(kor_med(F, placebo_rankings(F, max(1, round(nk)))), bas)["delta_cagr"]
                      for _ in range(40)])
        reg = ut["varianter"][b][f"f{w_}"]["delta_cagr"]
        inom = abs(reg - d.mean()) <= 2 * d.std(ddof=1)
        ut["placebo"][namn] = {"n_kastade": nk, "medel": round(float(d.mean()), 5),
                               "sd": round(float(d.std(ddof=1)), 5), "regelns_delta": reg,
                               "inom_placebobandet": bool(inom)}
        print(f"  {namn}: placebo {d.mean():+.2%} sd {d.std(ddof=1):.2%} "
              f"band [{d.mean()-2*d.std(ddof=1):+.2%},{d.mean()+2*d.std(ddof=1):+.2%}] "
              f"regel {reg:+.2%} → {'INOM (= slump)' if inom else 'UTANFÖR'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["varianter"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['varianter'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
