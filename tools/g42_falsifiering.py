"""G42 — TRE FALSIFIERINGSSTEG FÖR SMA200-ERSÄTTNINGSREGELN

Locked H0 (G29-rättad): 7,20 % / 31,56 %. G42-kandidaten: 9,35 % / 33,16 %.

STEG 1 PLACEBO — huvudtestet. Är regeln bättre än lika många SLUMPMÄSSIGA byten
  inom samma mekaniska sökutrymme? Placebot matchar exakt: antal byten per panel,
  N=30, rebalanstiming, exekvering, kostnad, likaviktsåterställning OCH det
  rankdjup G42 faktiskt når. Placebot får inte ett sämre kandidatuniversum.
  1000 dragningar, fast seed 20260817.

STEG 2 ATTRIBUTION — för varje faktiskt byte: A = namnet under SMA200 som tas
  bort, B = nästa H0-rankade kandidat över SMA200. Dekomponering mot en neutral
  referens M = medelavkastningen för de behållna topp-30-namnen:
      B − A = (M − A) + (B − M)
              avoidance   selection
  Ingen grupp definieras med framtida avkastning.

STEG 3 gjordes read-only ur registret, se ledgern.

Kör: /opt/momentum/venv/bin/python tools/g42_falsifiering.py
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
import h1419_motor as M

OUT = V2 / "research_k/g42_falsifiering_results.json"
LEDGER = V2 / "research_k/g42_eventledger.jsonl"
COST = 0.002
PPY = 13
N = 30
DRAG = 1000
SEED = 20260817
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]


def kor(F, smaf=None, byten_plan=None, rng=None, samla=False):
    """smaf satt -> G42. byten_plan satt -> placebo med matchat antal och djup."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w, nets, turns = {}, [], []
    plan, events = [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        koder = [r["kod"] for r in raw]
        if schedf(pi, dt) or not w:
            sel = koder[:N]
            if smaf is not None:
                ok = [k for k in sel if smaf(k, dt)]
                bort = [k for k in sel if k not in ok]
                ers, djup = [], N
                for j in range(N, len(koder)):
                    djup = j + 1
                    if len(ers) >= len(bort):
                        break
                    if smaf(koder[j], dt):
                        ers.append(koder[j])
                sel = (ok + ers)[:N]
                plan.append({"pi": pi, "n": len(ers), "djup": djup})
                if samla and ers:
                    events.append({"pi": pi, "dt": dt, "A": bort[:len(ers)], "B": ers,
                                   "behallna": ok})
            elif byten_plan is not None:
                p = byten_plan[len(plan)] if len(plan) < len(byten_plan) else {"n": 0, "djup": N}
                plan.append(p)
                n_ = min(p["n"], N)
                if n_ > 0:
                    pool = koder[N:max(p["djup"], N + n_)]
                    if len(pool) >= n_:
                        ut_i = rng.choice(N, size=n_, replace=False)
                        inn = rng.choice(len(pool), size=n_, replace=False)
                        kvar = [sel[i] for i in range(N) if i not in set(ut_i)]
                        sel = kvar + [pool[i] for i in inn]
            mal = {k: 1.0 / N for k in sel}
            t_ = sum(mal.values())
            mal = {k: v / t_ for k, v in mal.items()} if t_ > 0 else {}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w); turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        g = float(sum(mal[k] * r[k] for k in mal))
        nets.append(g - COST * turn); turns.append(turn)
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(turns), plan, events


def framat(F, k, pi, h):
    dts, ret = F["eval_dates"], F["returns_map"]
    if pi + h > len(dts):
        return None
    p = 1.0
    for i in range(pi, pi + h):
        v = ret.get((k, dts[i]))
        if v is None:
            return None
        p *= (1 + v)
    return p - 1


def main():
    ut = {"version": "G42_FALSIFIERING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "seed": SEED, "n_dragningar": DRAG, "fonster": {}}
    alla_ev = []

    for w_, F, namn, smaf in (("2020_2026", S.F26, "2020-2026", S.sma26),
                              ("2014_2019", S.F19, "2014-2019", M.sma_ok)):
        nH, tH, _, _ = kor(F)
        nG, tG, plan, events = kor(F, smaf=smaf, samla=True)
        sH, sG = S.stat(nH), S.stat(nG)
        dG = sG["cagr"] - sH["cagr"]
        n_byten = [p["n"] for p in plan]
        djup = [p["djup"] for p in plan]
        print(f"\n{'='*76}\n{namn}")
        print(f"  locked H0 {sH['cagr']:.2%}   G42 {sG['cagr']:.2%}   Δ {dG:+.2%}")
        print(f"  byten: {np.mean(n_byten):.2f}/panel (max {max(n_byten)}), "
              f"rankdjup som G42 når: median {int(np.median(djup))}, max {max(djup)}")

        # ---- STEG 1 PLACEBO
        rng = np.random.default_rng(SEED)
        pd_, ps, pm = [], [], []
        for _ in range(DRAG):
            nP, tP, _, _ = kor(F, byten_plan=plan, rng=rng)
            sP = S.stat(nP)
            pd_.append(sP["cagr"] - sH["cagr"]); ps.append(sP["sharpe"] - sH["sharpe"])
            pm.append(sP["maxdd"] - sH["maxdd"])
        pd_ = np.array(pd_); ps = np.array(ps); pm = np.array(pm)
        perc = float((pd_ < dG).mean())
        p_ensidigt = float((pd_ >= dG).mean())
        print(f"\n  STEG 1 — PLACEBO ({DRAG} dragningar, matchat antal och rankdjup)")
        print(f"    placebo Δ CAGR: medel {pd_.mean():+.2%}  median {np.median(pd_):+.2%}")
        print(f"      p5 {np.percentile(pd_,5):+.2%}  p25 {np.percentile(pd_,25):+.2%}  "
              f"p75 {np.percentile(pd_,75):+.2%}  p95 {np.percentile(pd_,95):+.2%}")
        print(f"    G42 Δ {dG:+.2%}  →  percentil {perc:.1%}   "
              f"ensidigt p = {p_ensidigt:.3f}")
        print(f"    Sharpe: G42 {sG['sharpe']-sH['sharpe']:+.3f} mot placebo "
              f"medel {ps.mean():+.3f} (percentil {float((ps < sG['sharpe']-sH['sharpe']).mean()):.1%})")
        print(f"    MaxDD:  G42 {sG['maxdd']-sH['maxdd']:+.2%} mot placebo "
              f"medel {pm.mean():+.2%}")
        print(f"    omsättning/år: H0 {tH.mean()*PPY:.1%}  G42 {tG.mean()*PPY:.1%}")

        klarar = p_ensidigt < 0.05
        print(f"    KLARAR PLACEBO (p<0,05): {'JA' if klarar else 'NEJ'}")

        # ---- STEG 2 ATTRIBUTION
        rader = []
        for e in events:
            pi = e["pi"]
            for a, b in zip(e["A"], e["B"]):
                rad = {"fonster": namn, "dt": e["dt"], "A": a, "B": b}
                for h, et in HOR:
                    ra, rb = framat(F, a, pi, h), framat(F, b, pi, h)
                    mvals = [framat(F, k, pi, h) for k in e["behallna"]]
                    mvals = [x for x in mvals if x is not None]
                    m_ = float(np.mean(mvals)) if mvals else None
                    rad[f"A_{et}"] = ra; rad[f"B_{et}"] = rb; rad[f"M_{et}"] = m_
                    rad[f"BmA_{et}"] = (rb - ra) if (ra is not None and rb is not None) else None
                    rad[f"avoid_{et}"] = (m_ - ra) if (ra is not None and m_ is not None) else None
                    rad[f"select_{et}"] = (rb - m_) if (rb is not None and m_ is not None) else None
                rader.append(rad)
        alla_ev.extend(rader)
        print(f"\n  STEG 2 — ATTRIBUTION ({len(rader)} faktiska byten)")
        print(f"    {'horisont':<10}{'B − A':>10}{'t':>7}{'avoidance':>12}{'t':>7}"
              f"{'selection':>12}{'t':>7}")
        attr = {}
        for h, et in HOR:
            v = np.array([r[f"BmA_{et}"] for r in rader if r.get(f"BmA_{et}") is not None])
            av = np.array([r[f"avoid_{et}"] for r in rader if r.get(f"avoid_{et}") is not None])
            se = np.array([r[f"select_{et}"] for r in rader if r.get(f"select_{et}") is not None])
            if len(v) < 8:
                continue
            f_ = lambda x: float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
            attr[et] = {"BmA": round(float(v.mean()), 5), "t_BmA": round(f_(v), 2),
                        "avoidance": round(float(av.mean()), 5), "t_avoid": round(f_(av), 2),
                        "selection": round(float(se.mean()), 5), "t_select": round(f_(se), 2),
                        "n": len(v)}
            print(f"    {et:<10}{v.mean():>+10.2%}{f_(v):>7.2f}{av.mean():>+12.2%}"
                  f"{f_(av):>7.2f}{se.mean():>+12.2%}{f_(se):>7.2f}")

        # robusthet: trimning och leave-one-stock-out på bytesnivå
        v4 = [(r["A"], r.get("BmA_12v")) for r in rader if r.get("BmA_12v") is not None]
        arr = np.array([x[1] for x in v4])
        lo, hi = np.percentile(arr, [5, 95])
        trim = arr[(arr >= lo) & (arr <= hi)]
        per_namn = defaultdict(list)
        for a, x in v4:
            per_namn[a].append(x)
        varst = sorted(per_namn.items(), key=lambda y: -abs(sum(y[1])))[:3]
        print(f"    robusthet 12v: otrimmat {arr.mean():+.2%}, "
              f"trimmat 5-95 {trim.mean():+.2%}")
        print(f"      tre namn med störst absolut bidrag: "
              f"{', '.join(f'{k} ({sum(v):+.1%})' for k,v in varst)}")
        utan = arr.mean()
        if varst:
            kvar = [x for a, x in v4 if a != varst[0][0]]
            utan = float(np.mean(kvar))
            print(f"      utan {varst[0][0]}: {utan:+.2%}")

        ut["fonster"][w_] = {
            "h0": sH, "g42": sG, "delta_cagr": round(dG, 5),
            "byten_per_panel": round(float(np.mean(n_byten)), 3),
            "rankdjup_median": int(np.median(djup)), "rankdjup_max": int(max(djup)),
            "placebo": {"medel": round(float(pd_.mean()), 5),
                        "median": round(float(np.median(pd_)), 5),
                        "p5": round(float(np.percentile(pd_, 5)), 5),
                        "p25": round(float(np.percentile(pd_, 25)), 5),
                        "p75": round(float(np.percentile(pd_, 75)), 5),
                        "p95": round(float(np.percentile(pd_, 95)), 5),
                        "g42_percentil": round(perc, 4),
                        "p_ensidigt": round(p_ensidigt, 4),
                        "klarar": bool(klarar),
                        "sharpe_placebo_medel": round(float(ps.mean()), 4),
                        "maxdd_placebo_medel": round(float(pm.mean()), 5)},
            "attribution": attr,
            "robusthet_12v": {"otrimmat": round(float(arr.mean()), 5),
                              "trimmat_5_95": round(float(trim.mean()), 5),
                              "utan_storsta_namn": round(float(utan), 5),
                              "storsta_namn": varst[0][0] if varst else None},
            "omsattning_ar": {"h0": round(float(tH.mean()) * PPY, 4),
                              "g42": round(float(tG.mean()) * PPY, 4)}}

    with open(LEDGER, "w") as f:
        for r in alla_ev:
            f.write(json.dumps(r, ensure_ascii=False, default=float) + "\n")

    a = ut["fonster"]["2020_2026"]["placebo"]["klarar"]
    b = ut["fonster"]["2014_2019"]["placebo"]["klarar"]
    ut["dom_placebo"] = ("KLARAR PLACEBO I BÅDA FÖNSTREN" if a and b else
                         "KLARAR I ETT FÖNSTER" if (a or b) else
                         "FALLER PLACEBO I BÅDA FÖNSTREN")
    print(f"\n{'='*76}\nPLACEBODOM: {ut['dom_placebo']}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"Skrivet: {OUT}\nEventledger: {LEDGER} ({len(alla_ev)} byten)")


if __name__ == "__main__":
    main()
