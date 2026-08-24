"""A1 — REBALANSFREKVENSEN SOM ALDRIG SVEPTES

SPARF F6 var ett TVÅPUNKTSTEST: 4 veckor mot 8 veckor. Åtta vann och blev
kontrakt. Ingen längre takt prövades. Legacy prövade fem takter och fann
motsatsen: "kontraktets 52v är sämst av fem prövade takter" (2026-08-04), och
efter startveckekontroll "13v är enda som överlever" (2026-08-05).

Rebalansfrekvensen är en av modellens tre grundparametrar. Signal och N valdes
på svep; frekvensen valdes på två punkter.

METOD
  Panelerna är 28 dagar. sched_fn(pi, dt) = (pi - o) % k == 0 ger rebalans var
  k:te panel. k=1 -> 4 veckor, k=2 -> 8 veckor (BASLINJE), k=3 -> 12 veckor,
  k=4 -> 16 veckor, k=6 -> 24 veckor, k=13 -> 52 veckor.

  KRITISKT: varje takt körs över SAMTLIGA k fasförskjutningar o = 0..k-1.
  En enskild fas mäter vilken startvecka som råkade passa, inte takten. Legacys
  metodlärdom 2026-08-05 var exakt denna: "Kontroll mot startvecka hör hemma
  FÖRE optimeringen, inte efter — annars optimerar man bort effekten."

  Rapporterar medel, min, max och sd över faserna. En takt vinner bara om dess
  SÄMSTA fas slår baslinjens MEDELFAS — annars är fyndet en faseffekt.

Kör: /opt/momentum/venv/bin/python tools/a1_rebalansfrekvens.py
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/a1_rebalansfrekvens_results.json"
TAKTER = [(1, "4 veckor"), (2, "8 veckor (KONTRAKT)"), (3, "12 veckor"),
          (4, "16 veckor"), (6, "24 veckor"), (13, "52 veckor")]


def kor_takt(F, k, o):
    kw = {x: y for x, y in F.items() if x != "sched_fn"}
    return S.kor(**kw, sched_fn=lambda pi, dt: (pi - o) % k == 0)


def main():
    ut = {"version": "A1_REBALANSFREKVENS_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "metod": "svep 4/8/12/16/24/52 veckor, samtliga fasförskjutningar per takt",
          "fonster": {}}

    # baslinjekontroll först
    bas26 = S.kor(**S.F26)[0]
    bas19 = S.kor(**S.F19)[0]
    print(f"baslinjekontroll: STACK_H {S.stat(bas26)['cagr']:.2%} / "
          f"{S.stat(bas19)['cagr']:.2%}  (registret 13,56 %)")
    if abs(S.stat(bas26)["cagr"] - 0.1356) > 0.004:
        sys.exit("AVBRYTER: baslinjen reproducerar inte")

    for w_, F, bas, namn in (("2020_2026", S.F26, bas26, "2020-2026"),
                             ("2014_2019", S.F19, bas19, "2014-2019")):
        print(f"\n{namn}   (baslinjens kanoniska fas: CAGR {S.stat(bas)['cagr']:.2%})")
        print(f"  {'takt':<22}{'medel':>8}{'min':>8}{'max':>8}{'sd':>7}"
              f"{'oms':>8}{'maxDD':>9}{'Sharpe':>8}")
        rad = {}
        for k, etikett in TAKTER:
            faser = []
            for o in range(k):
                nets, oms, n = kor_takt(F, k, o)
                st = S.stat(nets)
                faser.append({"fas": o, "nets": nets, "cagr": st["cagr"], "oms": oms,
                              "maxdd": st["maxdd"], "sharpe": st["sharpe"], "n": n})
            c = np.array([f["cagr"] for f in faser])
            sd = float(c.std(ddof=1)) if len(c) > 1 else 0.0
            b = max(faser, key=lambda f: f["cagr"])
            rad[etikett] = {
                "k_paneler": k, "n_faser": len(faser),
                "cagr_medel": round(float(c.mean()), 4), "cagr_min": round(float(c.min()), 4),
                "cagr_max": round(float(c.max()), 4), "cagr_sd": round(sd, 4),
                "oms_medel": round(float(np.mean([f["oms"] for f in faser])), 4),
                "maxdd_medel": round(float(np.mean([f["maxdd"] for f in faser])), 4),
                "sharpe_medel": round(float(np.mean([f["sharpe"] for f in faser])), 3),
                "innehav_medel": round(float(np.mean([f["n"] for f in faser])), 2),
                "per_fas": [{"fas": f["fas"], "cagr": round(f["cagr"], 4),
                             "oms": round(f["oms"], 4)} for f in faser],
                "boot_basta_fas_mot_baslinje": S.boot(b["nets"], bas)}
            print(f"  {etikett:<22}{c.mean():>8.2%}{c.min():>8.2%}{c.max():>8.2%}{sd:>7.2%}"
                  f"{rad[etikett]['oms_medel']:>8.1%}{rad[etikett]['maxdd_medel']:>9.2%}"
                  f"{rad[etikett]['sharpe_medel']:>8.3f}")
        ut["fonster"][w_] = rad

    # avgörande: slår någon takts SÄMSTA fas baslinjens MEDELFAS, i båda fönstren?
    print("\nAVGÖRANDE TEST — en takt vinner bara om dess SÄMSTA fas slår "
          "baslinjens MEDELFAS i BÅDA fönstren")
    b26 = ut["fonster"]["2020_2026"]["8 veckor (KONTRAKT)"]["cagr_medel"]
    b19 = ut["fonster"]["2014_2019"]["8 veckor (KONTRAKT)"]["cagr_medel"]
    print(f"  baslinjens medelfas: {b26:.2%} / {b19:.2%}")
    ut["dom"] = {}
    for k, etikett in TAKTER:
        a = ut["fonster"]["2020_2026"][etikett]
        b = ut["fonster"]["2014_2019"][etikett]
        robust = a["cagr_min"] > b26 and b["cagr_min"] > b19
        medel = a["cagr_medel"] > b26 and b["cagr_medel"] > b19
        ut["dom"][etikett] = {"slar_pa_medel_bada": bool(medel),
                              "slar_pa_samsta_fas_bada": bool(robust),
                              "delta_medel_26": round(a["cagr_medel"] - b26, 4),
                              "delta_medel_19": round(b["cagr_medel"] - b19, 4)}
        print(f"  {etikett:<22}Δmedel {a['cagr_medel']-b26:>+7.2%}/{b['cagr_medel']-b19:>+7.2%}"
              f"   medel {'JA' if medel else '- '}   sämsta fas {'JA' if robust else '-'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
