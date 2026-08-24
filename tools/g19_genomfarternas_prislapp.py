"""G19 — GENOMFARTERNAS PRISLAPP I H0

FÖRREGISTRERAD I docs/QUANT_TERM_H0_GAP_LEDGER.md, Batch 1.

Hypotes: innehav som varar högst 2 paneler har en genomsnittlig positions-
avkastning som INTE skiljer sig från noll i båda fönstren, mätt som avkastning
under innehavstiden minus universumets avkastning samma paneler.

Falsifieras om genomfartspopulationen har signifikant negativ överavkastning i
BÅDA fönstren — då är whipsaw en verklig och kvantifierad kostnad, och först då
är begrepp 1-7 värda att pröva som åtgärd.

VARFÖR DEN MÅSTE KÖRAS FÖRE G1/G2/G6
  Utan denna vet vi inte om det finns något att åtgärda. Att testa hysteres och
  band innan vi konstaterat att genomfarterna kostar är att pröva botemedel mot
  en sjukdom vi inte diagnosticerat.

DEFINITION FÖR H0
  H0 ombalanserar varannan panel. Ett namn som köps vid en ombalansering och
  säljs vid nästa hålls därför exakt 2 paneler. Det är den KORTAST MÖJLIGA
  innehavstiden och den naturliga genomfartsdefinitionen för H0. Den tidigare
  siffran 44,3 % kom från en waterfill-konstruktion med N=20 och gäller inte här.

MÄTNING
  Per spell: geometrisk avkastning över innehavspanelerna, minus universumets
  geometriska avkastning över SAMMA paneler. Höger-censurerade spells (fortfarande
  ägda vid periodens slut) exkluderas.

STATISTISKT FÖRBEHÅLL
  Spells överlappar i tid och samma namn återkommer. Ett naivt t-värde
  överskattar därför precisionen. Rapporterar både naivt t och ett
  namn-klustrat t, samt antal distinkta namn.

Kör: /opt/momentum/venv/bin/python tools/g19_genomfarternas_prislapp.py
"""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/g19_genomfarternas_prislapp_results.json"
COST = 0.002
PPY = 13
N = 30


def kor_h0(F):
    """H0 enligt låset. Returnerar nettoserie samt urvalet per panel."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    prev, prevw, nets, urval, oms = [], {}, [], [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        if schedf(pi, dt) or not prev:
            sel = [r["kod"] for r in raw][:N]
        else:
            sel = [k for k in prev if k in elig]
            if len(sel) < N:
                sel += [r["kod"] for r in raw if r["kod"] not in sel][: N - len(sel)]
        urval.append(sel)
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
    return np.array(nets), urval, float(np.mean(oms)) * PPY


def spells(F, urval):
    """Sammanhängande innehavsperioder per namn. Höger-censurerade markeras."""
    dts, ret = F["eval_dates"], F["returns_map"]
    univ = np.array([float(np.mean([ret.get((r["kod"], dt), 0.0) for r in F["rankings"][dt]]))
                     for dt in dts])
    per = defaultdict(list)
    for pi, sel in enumerate(urval):
        for k in sel:
            per[k].append(pi)
    ut = []
    sista = len(dts) - 1
    for k, idx in per.items():
        start = idx[0]; forra = idx[0]
        for i in idx[1:] + [None]:
            if i is None or i != forra + 1:
                paneler = list(range(start, forra + 1))
                r = float(np.prod([1 + ret.get((k, dts[p]), 0.0) for p in paneler]) - 1)
                u = float(np.prod([1 + univ[p] for p in paneler]) - 1)
                ut.append({"kod": k, "start": start, "slut": forra,
                           "langd": len(paneler), "ret": r, "univ": u,
                           "excess": (1 + r) / (1 + u) - 1,
                           "censurerad": forra == sista})
                if i is not None:
                    start = i
            if i is not None:
                forra = i
    return [s for s in ut if not s["censurerad"]], univ


def klustrat_t(v, grupp):
    """t-värde med klusterrobust standardfel på namnnivå."""
    v = np.asarray(v, float)
    m = v.mean()
    g = defaultdict(list)
    for x, k in zip(v, grupp):
        g[k].append(x - m)
    n, G = len(v), len(g)
    if G < 3:
        return float("nan")
    meat = sum(sum(a) ** 2 for a in g.values())
    se = math.sqrt(meat) / n
    just = math.sqrt(G / max(1, G - 1))
    return float(m / (se * just)) if se > 0 else float("nan")


def main():
    ut = {"version": "G19_GENOMFARTERNAS_PRISLAPP_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "FÖRREGISTRERAD",
          "hypotes": "genomfarter (<=2 paneler) har överavkastning som ej skiljer sig från noll",
          "falsifieras_om": "signifikant negativ överavkastning i BÅDA fönstren",
          "definition": "H0 ombalanserar varannan panel; kortast möjliga spell är 2 paneler",
          "fonster": {}}

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        nets, urval, oms = kor_h0(F)
        sp, univ = spells(F, urval)
        st = S.stat(nets)
        print(f"\n{namn}   H0 CAGR {st['cagr']:.2%}, omsättning {oms:.1%}/år, "
              f"{len(F['eval_dates'])} paneler")
        print(f"  avslutade spells: {len(sp)}, distinkta namn: {len({s['kod'] for s in sp})}")

        langder = defaultdict(list)
        for s in sp:
            langder[s["langd"]].append(s)
        print(f"\n  {'längd':<10}{'antal':>7}{'andel':>8}{'medel exc':>11}{'median':>9}"
              f"{'t naivt':>9}{'t klustrat':>12}")
        fordelning = {}
        for L in sorted(langder):
            g = langder[L]
            e = np.array([x["excess"] for x in g])
            tn = e.mean() / (e.std(ddof=1) / math.sqrt(len(e))) if len(e) > 3 and e.std(ddof=1) > 0 else float("nan")
            tk = klustrat_t(e, [x["kod"] for x in g])
            fordelning[L] = {"n": len(g), "andel": round(len(g) / len(sp), 4),
                             "medel_excess": round(float(e.mean()), 5),
                             "median_excess": round(float(np.median(e)), 5),
                             "t_naivt": round(float(tn), 2), "t_klustrat": round(float(tk), 2)}
            if len(g) >= 5:
                print(f"  {L:<10}{len(g):>7}{len(g)/len(sp):>8.1%}{e.mean():>+11.2%}"
                      f"{np.median(e):>+9.2%}{tn:>9.2f}{tk:>12.2f}")

        gen = [s for s in sp if s["langd"] <= 2]
        lang = [s for s in sp if s["langd"] > 2]
        eg = np.array([s["excess"] for s in gen])
        el = np.array([s["excess"] for s in lang])
        tg_n = eg.mean() / (eg.std(ddof=1) / math.sqrt(len(eg)))
        tg_k = klustrat_t(eg, [s["kod"] for s in gen])
        tl_k = klustrat_t(el, [s["kod"] for s in lang])
        print(f"\n  PRIMÄRT UTFALL")
        print(f"    genomfarter (<=2 paneler): n={len(gen)} ({len(gen)/len(sp):.1%} av alla)")
        print(f"      medel överavkastning {eg.mean():+.2%}   median {np.median(eg):+.2%}")
        print(f"      t naivt {tg_n:+.2f}   t klustrat på namn {tg_k:+.2f}")
        print(f"    längre innehav (>2): n={len(lang)}  medel {el.mean():+.2%}  "
              f"t klustrat {tl_k:+.2f}")

        # aktiekapital bundet i genomfarter och deras kostnad
        panelvikt_gen = sum(s["langd"] for s in gen) / N
        panelvikt_alla = sum(s["langd"] for s in sp) / N
        genomfarter_per_ar = len(gen) / (len(F["eval_dates"]) / PPY)
        kostnad_ar = genomfarter_per_ar * 2 * COST / N
        print(f"    andel av portföljens paneltid i genomfarter: "
              f"{panelvikt_gen/panelvikt_alla:.1%}")
        print(f"    genomfarter per år: {genomfarter_per_ar:.1f}  "
              f"=> handelskostnad {kostnad_ar:.2%}/år")

        signifikant_negativ = eg.mean() < 0 and tg_k < -1.96
        print(f"    HYPOTESEN i detta fönster: "
              f"{'FALLER (signifikant negativ)' if signifikant_negativ else 'HÅLLER'}")

        ut["fonster"][w_] = {
            "h0": {**st, "omsattning_ar": round(oms, 4)},
            "n_spells": len(sp), "n_namn": len({s["kod"] for s in sp}),
            "fordelning_per_langd": fordelning,
            "primart": {
                "n_genomfarter": len(gen), "andel_av_spells": round(len(gen) / len(sp), 4),
                "medel_excess": round(float(eg.mean()), 5),
                "median_excess": round(float(np.median(eg)), 5),
                "t_naivt": round(float(tg_n), 2), "t_klustrat": round(float(tg_k), 2),
                "langre_medel_excess": round(float(el.mean()), 5),
                "langre_t_klustrat": round(float(tl_k), 2),
                "andel_paneltid": round(panelvikt_gen / panelvikt_alla, 4),
                "genomfarter_per_ar": round(genomfarter_per_ar, 1),
                "handelskostnad_ar": round(kostnad_ar, 5),
                "signifikant_negativ": bool(signifikant_negativ)}}

    a = ut["fonster"]["2020_2026"]["primart"]["signifikant_negativ"]
    b = ut["fonster"]["2014_2019"]["primart"]["signifikant_negativ"]
    ut["dom"] = ("HYPOTESEN FALLER — genomfarter är signifikant värdeförstörande i båda fönstren"
                 if a and b else
                 "HYPOTESEN HÅLLER — genomfarterna är inte påvisat värdeförstörande i båda fönstren")
    print(f"\nDOM: {ut['dom']}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
