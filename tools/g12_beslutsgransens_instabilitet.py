"""G12 — BESLUTSGRÄNSENS INSTABILITET I H0

FÖRREGISTRERAD I docs/QUANT_TERM_H0_GAP_LEDGER.md, Batch 1.

Hypotes: om H0:s poäng störs med brus av samma storleksordning som det
observerade poängavståndet per rankplats (sigma = 0,0036), är den resulterande
CAGR-spridningen över 200 dragningar MINDRE ÄN +/-1,0 procentenhet i båda
fönstren.

Falsifieras om spridningen överstiger +/-1,0 pp — då vilar H0:s redovisade
resultat i väsentlig grad på gränsbrus snarare än på signalen.

VARFÖR DEN ÄR FÖRST I KÖN
  Detta mäter inte en förbättring. Det mäter hur mycket av det BEFINTLIGA
  resultatet som är reellt. Faller hypotesen ändras tolkningen av varje annat
  tal i programmet.

BRUSETS FORM
  Oberoende dragning per (panel, namn). Det är den korrekta modellen för
  gränsinstabilitet: frågan är hur mycket den exakta ORDNINGEN spelar roll, inte
  om poängen är systematiskt skev. Ett persistent brus per namn skulle mäta
  något annat — en snedvriden signal, inte en ostadig gräns.

H0:s KONSTRUKTION (trackh/H0_LOCK.json)
  topp 30, LIKA VIKT 1/30, ombalans var andra fyraveckorspanel, mellanpanel
  behåller, 20 bp enkelsidigt. Ingen hysteres, inget band, ingen SMA-grind.

SEKUNDÄRT (ej förregistrerat, redovisas separat)
  - sigma-svep 0,5x / 1x / 2x / 4x
  - fönsterspecifikt poänggap per rankplats
  - hur många av topp-30 som faktiskt byts av bruset

Kör: /opt/momentum/venv/bin/python tools/g12_beslutsgransens_instabilitet.py
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/g12_beslutsgransens_instabilitet_results.json"
COST = 0.002
PPY = 13
SIGMA_PREREG = 0.0036
N_DRAG = 200


def h0(F, rankings=None, N=30):
    """H0 exakt enligt låset: topp-N, lika vikt, ombalans var andra panel."""
    R = rankings if rankings is not None else F["rankings"]
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    prev, prevw, nets, oms = [], {}, [], []
    for pi, dt in enumerate(dts):
        raw = R[dt]
        elig = {r["kod"] for r in raw}
        if schedf(pi, dt) or not prev:
            sel = [r["kod"] for r in raw][:N]
        else:
            sel = [k for k in prev if k in elig]
            if len(sel) < N:
                sel += [r["kod"] for r in raw if r["kod"] not in sel][: N - len(sel)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); oms.append(0.0); prev, prevw = sel, {}; continue
        w = np.full(n, 1.0 / N)
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        oms.append(turn)
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel, curr
    return np.array(nets), float(np.mean(oms)) * PPY


def stor(F, sigma, rng):
    """Ny rankningsdict med oberoende brus per (panel, namn)."""
    ut = {}
    for dt in F["eval_dates"]:
        raw = F["rankings"][dt]
        e = rng.normal(0.0, sigma, len(raw))
        nya = [{"kod": r["kod"], "score": r["score"] + float(e[i])} for i, r in enumerate(raw)]
        nya.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = nya
    return ut


def bytesgrad(F, rankings, N=30):
    d = []
    for dt in F["eval_dates"]:
        a = {r["kod"] for r in F["rankings"][dt][:N]}
        b = {r["kod"] for r in rankings[dt][:N]}
        d.append(len(a - b))
    return float(np.mean(d))


def poanggap(F, N=30):
    g = [F["rankings"][dt][0]["score"] - F["rankings"][dt][N - 1]["score"]
         for dt in F["eval_dates"] if len(F["rankings"][dt]) > N]
    return float(np.median(g)), float(np.median(g)) / (N - 1)


def main():
    ut = {"version": "G12_BESLUTSGRANSENS_INSTABILITET_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "FÖRREGISTRERAD, primärt utfall är sigma=0,0036 med 200 dragningar",
          "hypotes": "CAGR-spridningen är mindre än +/-1,0 pp i båda fönstren",
          "falsifieras_om": "spridningen överstiger +/-1,0 pp",
          "brusform": "oberoende dragning per (panel, namn)",
          "fonster": {}}

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        bas, oms = h0(F)
        b = S.stat(bas)
        gap, per_rank = poanggap(F)
        print(f"\n{namn}")
        print(f"  H0 ostört: CAGR {b['cagr']:.2%}  vol {b['vol']:.2%}  "
              f"maxDD {b['maxdd']:.2%}  omsättning {oms:.1%}/år")
        print(f"  poänggap rank 1->30: {gap:.4f}  =>  {per_rank:.5f} per rankplats")

        rng = np.random.default_rng(20260817)
        c, byten = [], []
        for i in range(N_DRAG):
            r = stor(F, SIGMA_PREREG, rng)
            c.append(S.stat(h0(F, r)[0])["cagr"])
            if i < 40:
                byten.append(bytesgrad(F, r))
        c = np.array(c)
        spann_lo, spann_hi = float(np.percentile(c, 2.5)), float(np.percentile(c, 97.5))
        halv = (spann_hi - spann_lo) / 2
        faller = halv > 0.01
        print(f"\n  PRIMÄRT UTFALL — sigma {SIGMA_PREREG}, {N_DRAG} dragningar")
        print(f"    CAGR medel {c.mean():.2%}  sd {c.std(ddof=1):.2%}")
        print(f"    95 %-spann [{spann_lo:.2%}, {spann_hi:.2%}]  halva bredden {halv:.2%}")
        print(f"    min {c.min():.2%}  max {c.max():.2%}  vidd {c.max()-c.min():.2%}")
        print(f"    ostört utfall {b['cagr']:.2%} ligger på percentil "
              f"{float((c < b['cagr']).mean()):.0%}")
        print(f"    namn i topp-30 som bruset byter ut: {np.mean(byten):.2f} per panel")
        print(f"    HYPOTESEN: {'FALLER (spridning > +/-1,0 pp)' if faller else 'HÅLLER'}")

        rad = {"h0_ostort": {**b, "omsattning_ar": round(oms, 4)},
               "poanggap_1_till_30": round(gap, 5), "gap_per_rankplats": round(per_rank, 6),
               "primart": {"sigma": SIGMA_PREREG, "n_dragningar": N_DRAG,
                           "cagr_medel": round(float(c.mean()), 4),
                           "cagr_sd": round(float(c.std(ddof=1)), 4),
                           "ki95": [round(spann_lo, 4), round(spann_hi, 4)],
                           "halva_bredden": round(halv, 4),
                           "min": round(float(c.min()), 4), "max": round(float(c.max()), 4),
                           "ostort_percentil": round(float((c < b["cagr"]).mean()), 3),
                           "byten_topp30_per_panel": round(float(np.mean(byten)), 2),
                           "hypotesen_faller": bool(faller)}}

        # sekundärt: sigma-svep, inklusive fönstrets eget gap per rankplats
        print(f"\n  SEKUNDÄRT (ej förregistrerat) — sigma-svep")
        print(f"    {'sigma':<12}{'medel':>9}{'sd':>8}{'95%-spann':>22}{'byten':>8}")
        sek = {}
        for mult, etikett in ((0.5, "0,5x"), (1.0, "1x"), (2.0, "2x"), (4.0, "4x")):
            s = SIGMA_PREREG * mult
            rng2 = np.random.default_rng(20260817 + int(mult * 10))
            cc, bb = [], []
            for i in range(80):
                r = stor(F, s, rng2)
                cc.append(S.stat(h0(F, r)[0])["cagr"])
                if i < 20:
                    bb.append(bytesgrad(F, r))
            cc = np.array(cc)
            lo, hi = float(np.percentile(cc, 2.5)), float(np.percentile(cc, 97.5))
            sek[etikett] = {"sigma": round(s, 6), "medel": round(float(cc.mean()), 4),
                            "sd": round(float(cc.std(ddof=1)), 4), "ki95": [round(lo, 4), round(hi, 4)],
                            "byten_per_panel": round(float(np.mean(bb)), 2)}
            print(f"    {etikett + f' ({s:.4f})':<12}{cc.mean():>9.2%}{cc.std(ddof=1):>8.2%}"
                  f"   [{lo:>7.2%},{hi:>7.2%}]{np.mean(bb):>8.2f}")
        # fönstrets eget gap
        rng3 = np.random.default_rng(20260901)
        cc = np.array([S.stat(h0(F, stor(F, per_rank, rng3))[0])["cagr"] for _ in range(80)])
        lo, hi = float(np.percentile(cc, 2.5)), float(np.percentile(cc, 97.5))
        sek["fonstrets_eget_gap"] = {"sigma": round(per_rank, 6), "medel": round(float(cc.mean()), 4),
                                     "sd": round(float(cc.std(ddof=1)), 4),
                                     "ki95": [round(lo, 4), round(hi, 4)]}
        print(f"    {'eget gap':<12}{cc.mean():>9.2%}{cc.std(ddof=1):>8.2%}   [{lo:>7.2%},{hi:>7.2%}]")
        rad["sekundart_sigmasvep"] = sek
        ut["fonster"][w_] = rad

    a = ut["fonster"]["2020_2026"]["primart"]["hypotesen_faller"]
    b = ut["fonster"]["2014_2019"]["primart"]["hypotesen_faller"]
    ut["dom"] = ("HYPOTESEN FALLER I BÅDA FÖNSTREN" if a and b else
                 "HYPOTESEN FALLER I ETT FÖNSTER" if a or b else "HYPOTESEN HÅLLER I BÅDA")
    print(f"\nDOM: {ut['dom']}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
