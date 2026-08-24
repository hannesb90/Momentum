"""A2 — STAGGERADE KOHORTER (legacy N3-55, aldrig prövad i v2)

I dag rebalanserar modellen HELA portföljen samtidigt var 8:e vecka. Alternativet
är att dela kapitalet i k delportföljer (sleeves) som rebalanserar med förskjuten
fas: sleeve o rebalanserar vid paneler där (pi - o) % k == 0.

Varje sleeve behåller EXAKT samma regler, samma N, samma signal. Ingen ny
parameter, ingen ny tröskel. Det enda som ändras är att besluten sprids ut i
tiden i stället för att klumpas ihop.

TVÅ SAKER TESTAS
  1. Variansreduktion. Medelvärdet av k svagt korrelerade serier har lägre
     volatilitet än varje enskild serie. Lägre volatilitet ger mindre
     variansdrag och därmed högre geometrisk avkastning vid samma aritmetiska.
  2. Fasoberoende. A1 visade att fasspridningen växer kraftigt med k — vid 52
     veckor är spannet 6,65–14,84 % i 2020-2026 enbart beroende på startvecka.
     En kohortportfölj äger ALLA faser samtidigt och kan därför inte ha tur
     eller otur med startveckan.

KONSTRUKTION
  Kohortens nettoserie = medelvärdet av de k sleevernas nettoserier. Det
  motsvarar en portfölj med 1/k i varje sleeve som återställs till likavikt
  varje panel. Det är inte identiskt med buy-and-hold över sleeves — den
  skillnaden är liten men reell och redovisas som förbehåll.

  Kostnaden ligger redan inne i varje sleeves nettoserie. Varje sleeve
  omsätter 1/k av kapitalet, så total omsättning är i samma storleksordning.

Kör: /opt/momentum/venv/bin/python tools/a2_staggerade_kohorter.py
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/a2_staggerade_kohorter_results.json"
TAKTER = [(2, "8 veckor, 2 kohorter"), (3, "12 veckor, 3 kohorter"),
          (4, "16 veckor, 4 kohorter"), (6, "24 veckor, 6 kohorter"),
          (13, "52 veckor, 13 kohorter")]


def sleeve(F, k, o):
    kw = {x: y for x, y in F.items() if x != "sched_fn"}
    return S.kor(**kw, sched_fn=lambda pi, dt: (pi - o) % k == 0)


def main():
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    print(f"baslinjekontroll: STACK_H {S.stat(bas26)['cagr']:.2%} / {S.stat(bas19)['cagr']:.2%}")
    if abs(S.stat(bas26)["cagr"] - 0.1356) > 0.004:
        sys.exit("AVBRYTER: baslinjen reproducerar inte")

    ut = {"version": "A2_STAGGERADE_KOHORTER_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "forbehall": "Kohortserien är medelvärdet av sleevernas nettoserier, "
                       "alltså likaviktsåterställning varje panel, inte buy-and-hold över sleeves.",
          "fonster": {}}

    for w_, F, bas, namn in (("2020_2026", S.F26, bas26, "2020-2026"),
                             ("2014_2019", S.F19, bas19, "2014-2019")):
        b = S.stat(bas)
        print(f"\n{namn}")
        print(f"  {'konstruktion':<26}{'CAGR':>8}{'Δ':>9}{'vol':>8}{'maxDD':>9}"
              f"{'Sharpe':>8}{'korr':>7}")
        print(f"  {'STACK_H (en portfölj)':<26}{b['cagr']:>8.2%}{'—':>9}{b['vol']:>8.2%}"
              f"{b['maxdd']:>9.2%}{b['sharpe']:>8.3f}")
        rad = {}
        for k, etikett in TAKTER:
            sl = [sleeve(F, k, o)[0] for o in range(k)]
            koh = np.mean(sl, axis=0)
            st = S.stat(koh)
            bo = S.boot(koh, bas)
            # medelkorrelation mellan sleeves
            if k > 1:
                cm = np.corrcoef(np.array(sl))
                mk = float((cm.sum() - k) / (k * (k - 1)))
            else:
                mk = 1.0
            enskild = [S.stat(x)["cagr"] for x in sl]
            rad[etikett] = {
                "k": k, **st, **bo,
                "sleeve_cagr_medel": round(float(np.mean(enskild)), 4),
                "sleeve_cagr_min": round(float(np.min(enskild)), 4),
                "sleeve_cagr_max": round(float(np.max(enskild)), 4),
                "sleeve_vol_medel": round(float(np.mean([S.stat(x)["vol"] for x in sl])), 4),
                "medelkorr_mellan_sleeves": round(mk, 3),
                "variansvinst_pp": round(st["cagr"] - float(np.mean(enskild)), 4)}
            print(f"  {etikett:<26}{st['cagr']:>8.2%}{bo['delta_cagr']:>+9.2%}{st['vol']:>8.2%}"
                  f"{st['maxdd']:>9.2%}{st['sharpe']:>8.3f}{mk:>7.3f}")
        ut["fonster"][w_] = rad

    print("\nVARIANSVINSTEN — kohortens CAGR minus medelsleeven (ren geometrisk effekt)")
    print(f"  {'konstruktion':<26}{'2020-2026':>12}{'2014-2019':>12}")
    for k, etikett in TAKTER:
        a = ut["fonster"]["2020_2026"][etikett]
        b = ut["fonster"]["2014_2019"][etikett]
        print(f"  {etikett:<26}{a['variansvinst_pp']:>+12.2%}{b['variansvinst_pp']:>+12.2%}")

    print("\nAVGÖRANDE — positiv mot STACK_H i BÅDA fönstren?")
    ut["dom"] = {}
    for k, etikett in TAKTER:
        a = ut["fonster"]["2020_2026"][etikett]
        b = ut["fonster"]["2014_2019"][etikett]
        rep = a["delta_cagr"] > 0 and b["delta_cagr"] > 0
        ki = a["ki_lo"] > 0 and b["ki_lo"] > 0
        ut["dom"][etikett] = {"bada_positiva": bool(rep), "bada_ki_over_noll": bool(ki),
                              "delta_26": a["delta_cagr"], "delta_19": b["delta_cagr"],
                              "sharpe_26": a["sharpe"], "sharpe_19": b["sharpe"]}
        print(f"  {etikett:<26}Δ {a['delta_cagr']:>+7.2%}/{b['delta_cagr']:>+7.2%}"
              f"   KI26 [{a['ki_lo']:+.2%},{a['ki_hi']:+.2%}]"
              f"   {'BÅDA POSITIVA' if rep else '-'}{'  KI>0' if ki else ''}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
