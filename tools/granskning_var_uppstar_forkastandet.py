"""GRANSKNING: VAR I TIDEN UPPSTÅR FÖRKASTANDET?

Inventeringen av 106 tvåfönstervarianter visar ett systematiskt mönster:

  75 % är NEGATIVA i 2020-2026   (median -1,03 %)
  42 % är POSITIVA i 2014-2019   (median -0,29 %)
  33 % är negativa i det sena OCH positiva i det tidiga fönstret

Det sena fönstret gör alltså nästan hela förkastandearbetet. Tvåfönsterkriteriet
är i praktiken ett "måste överleva 2020-2026"-kriterium.

2020-2026 innehåller två skarpa V-bottnar: mars 2020 och 2022. Varje regel som
BESKÄR eller ROTERAR säljer nedtryckta namn strax innan de vänder. Om
förkastandet drivs av ett fåtal sådana paneler är slutsatsen inte "mekanismen
saknar värde" utan "mekanismen tål inte en V-botten" — vilket är ett helt annat
påstående och pekar mot en annan åtgärd.

METOD
  Nettoserien per panel dekomponeras. För varje regel beräknas skillnaden mot
  baslinjen panel för panel, och summan delas upp på:

    nedgångspaneler   universumets avkastning < 0
    uppgångspaneler   universumets avkastning >= 0
    vändpaneler       panelen EFTER en nedgång större än -8 %

  Rapporterar även hur stor andel av det totala underskottet som de fem värsta
  panelerna står för. Om fem paneler av 66 bär mer än hälften är resultatet
  inte en egenskap hos mekanismen utan hos ett par datum.

Kör: /opt/momentum/venv/bin/python tools/granskning_var_uppstar_forkastandet.py
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import granskning_statisk_vs_dynamisk as D

OUT = V2 / "research_k/granskning_var_uppstar_forkastandet_results.json"


def universumserie(F):
    return np.array([float(np.mean([F["returns_map"].get((r["kod"], dt), 0.0)
                                    for r in F["rankings"][dt]])) for dt in F["eval_dates"]])


def dekomponera(diff, univ, dts):
    ned = univ < 0
    upp = ~ned
    vand = np.zeros(len(univ), dtype=bool)
    for i in range(1, len(univ)):
        if univ[i - 1] < -0.08:
            vand[i] = True
    varsta = np.argsort(diff)[:5]
    return {
        "total": float(diff.sum()),
        "nedgangspaneler": {"n": int(ned.sum()), "summa": float(diff[ned].sum()),
                            "medel": float(diff[ned].mean()) if ned.any() else 0.0},
        "uppgangspaneler": {"n": int(upp.sum()), "summa": float(diff[upp].sum()),
                            "medel": float(diff[upp].mean()) if upp.any() else 0.0},
        "vandpaneler": {"n": int(vand.sum()), "summa": float(diff[vand].sum()),
                        "datum": [dts[i] for i in np.where(vand)[0]]},
        "fem_varsta": {"summa": float(diff[varsta].sum()),
                       "andel_av_total": (float(diff[varsta].sum() / diff.sum())
                                          if diff.sum() != 0 else None),
                       "datum": [dts[int(i)] for i in varsta]}}


def main():
    for F in (S.F26, S.F19):
        D.bygg_sc(F); D._REG[id(F)] = D.regim(F)
    bas = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}
    print(f"baslinjekontroll: {S.stat(bas['26'])['cagr']:.2%} / {S.stat(bas['19'])['cagr']:.2%}")

    univ = {"26": universumserie(S.F26), "19": universumserie(S.F19)}
    dts = {"26": S.F26["eval_dates"], "19": S.F19["eval_dates"]}
    print(f"\nfönsterkaraktär:")
    for w in ("26", "19"):
        u = univ[w]
        print(f"  {'2020-2026' if w=='26' else '2014-2019'}: "
              f"{int((u<0).sum())}/{len(u)} nedgångspaneler, "
              f"sämsta panel {u.min():+.2%}, "
              f"paneler under -8 %: {int((u<-0.08).sum())}")

    regler = [("swap 10 % sämsta", dict(regel="swap_rel", q=0.10)),
              ("swap 20 % sämsta", dict(regel="swap_rel", q=0.20)),
              ("lutning bort 20 %", dict(regel="lutning_rel", q=0.20)),
              ("lutning bort 33 %", dict(regel="lutning_rel", q=0.33)),
              ("blankning bort 10 %", dict(regel="blank_rel", q=0.10))]

    ut = {"version": "GRANSKNING_VAR_UPPSTAR_FORKASTANDET_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "fonsterkarakter": {w: {"n_paneler": len(univ[w]),
                                  "n_nedgang": int((univ[w] < 0).sum()),
                                  "samsta_panel": float(univ[w].min()),
                                  "n_under_minus8": int((univ[w] < -0.08).sum())}
                              for w in ("26", "19")},
          "regler": {}}

    for namn, kw in regler:
        ut["regler"][namn] = {}
        print(f"\n{namn}")
        for w, F in (("26", S.F26), ("19", S.F19)):
            a = D.sim(F, **kw)[0]
            diff = a - bas[w]
            d = dekomponera(diff, univ[w], dts[w])
            ut["regler"][namn]["2020_2026" if w == "26" else "2014_2019"] = d
            fon = "2020-2026" if w == "26" else "2014-2019"
            print(f"  {fon}: total {d['total']:+.1%}  |  "
                  f"nedgång {d['nedgangspaneler']['summa']:+.1%} ({d['nedgangspaneler']['n']} pan)  "
                  f"uppgång {d['uppgangspaneler']['summa']:+.1%} ({d['uppgangspaneler']['n']} pan)  "
                  f"vändpaneler {d['vandpaneler']['summa']:+.1%} ({d['vandpaneler']['n']} pan)")
            av = d["fem_varsta"]["andel_av_total"]
            print(f"     fem värsta panelerna: {d['fem_varsta']['summa']:+.1%}"
                  + (f" = {av:.0%} av totalen" if av and d['total'] < 0 else "")
                  + f"   {', '.join(d['fem_varsta']['datum'][:3])}")

    print("\nSAMMANFATTNING — bär vändpanelerna förkastandet?")
    for namn in ut["regler"]:
        a = ut["regler"][namn]["2020_2026"]
        andel = a["vandpaneler"]["summa"] / a["total"] if a["total"] < 0 else None
        print(f"  {namn:<22} 2020-2026 total {a['total']:+.1%}, "
              f"varav vändpaneler {a['vandpaneler']['summa']:+.1%}"
              + (f" = {andel:.0%}" if andel else ""))

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
