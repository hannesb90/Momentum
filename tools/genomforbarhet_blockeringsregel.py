"""GENOMFÖRBARHETSKONTROLL — sammansatt blockeringsregel (ej ett hypotestest)

Räknar tre saker på befintlig, redan beräknad data. Ingen CAGR beräknas, ingen
regel utvärderas, ingen arm jämförs. Syftet är enbart att avgöra om den
föreslagna regeln är väldefinierad över hela fönstret.

  1. Hur ofta binder "-5 % efter halva fönstret"?  Andel innehav vars avkastning
     över rebalanspanelen (= fram till mellanpanelen) understiger -5 %.
  2. Hur snabbt tömmer en PERMANENT spärr ("addera aldrig ett namn vi sålt med
     regeln") den valbara poolen?
  3. Hur stort är universumet per panel, dvs hur mycket finns att spärra bort.

Kör: /opt/momentum/venv/bin/python tools/genomforbarhet_blockeringsregel.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

N, TROSKEL = 30, -0.05


def analys(F, namn):
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    univ = [len(F["rankings"][dt]) for dt in dts]

    # ---- 1+3: bindningsfrekvens i CANONICAL H0 (utan att regeln appliceras)
    w, binder, innehav, per_panel = {}, 0, 0, []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            mal = {k: 1.0 / N for k in [r["kod"] for r in raw][:N]}
            n_bind = sum(1 for k in mal if ret.get((k, dt), 0.0) < TROSKEL)
            binder += n_bind
            innehav += len(mal)
            per_panel.append(n_bind)
        else:
            mal = dict(w)
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}

    # ---- 2: permanent spärr — hur snabbt tar poolen slut
    spard, w2, historik, kollaps = set(), {}, [], None
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w2:
            valbara = [r["kod"] for r in raw if r["kod"] not in spard]
            historik.append({"panel": pi, "dt": dt, "sparrade": len(spard),
                             "valbara": len(valbara), "universum": len(raw)})
            if len(valbara) < N and kollaps is None:
                kollaps = {"panel": pi, "dt": dt, "valbara": len(valbara),
                           "sparrade": len(spard)}
            sel = valbara[:N]
            mal = {k: 1.0 / N for k in sel}
            # regel 1: allt som faller under -5 % till mellanpanelen saljs OCH sparras
            for k in sel:
                if ret.get((k, dt), 0.0) < TROSKEL:
                    spard.add(k)
        else:
            mal = dict(w2)
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w2 = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}

    print(f"=== {namn} ===")
    print(f"  paneler {len(dts)}, rebalanspaneler {len(per_panel)}, "
          f"universum per panel: median {int(np.median(univ))} "
          f"(min {min(univ)}, max {max(univ)})")
    print(f"  1) '-5 % efter halva fonstret' binder pa "
          f"{binder}/{innehav} = {binder/innehav:.1%} av innehaven")
    print(f"     per rebalans: median {np.median(per_panel):.0f} av {N} namn, "
          f"min {min(per_panel)}, max {max(per_panel)}")
    print(f"  2) permanent sparr — sparrade namn over tid:")
    for h in historik[::4]:
        print(f"     panel {h['panel']:>2} {h['dt']}  sparrade {h['sparrade']:>3}  "
              f"valbara {h['valbara']:>3} av {h['universum']}")
    sista = historik[-1]
    print(f"     SLUT: sparrade {sista['sparrade']} av universum {sista['universum']}, "
          f"valbara {sista['valbara']}")
    if kollaps:
        print(f"     *** POOLEN RACKER INTE TILL fran panel {kollaps['panel']} "
              f"({kollaps['dt']}): bara {kollaps['valbara']} valbara for N=30")
    else:
        print(f"     poolen racker hela fonstret (min valbara "
              f"{min(h['valbara'] for h in historik)})")
    print()


for namn, F in (("2020-2026", S.F26), ("2014-2019", S.F19)):
    analys(F, namn)
