"""GÅR DET ATT SKÄRPA RANKNINGSSIGNALEN?

Poängen är 0,5 x percentilrank(12m) + 0,5 x percentilrank(18m). Rank 1 och
rank 30 skiljs av 0,1055 percentilenheter — 0,003 per plats. Percentiltransformen
kastar bort HUR MYCKET bättre ett namn är och behåller bara ordningen. Det spelar
roll när två signaler ska vägas ihop.

Fem sätt att skärpa, alla oprövade:

  A  z-poäng i stället för percentilrank vid sammanvägningen
  B  ojämn horisontvikt (0,7/0,3 och 0,3/0,7)
  C  krav på samstämmighet — båda signalerna måste vara inom topp-X
  D  riskjusterat momentum: momentum delat med volatilitet
  E  tre horisonter 12+18+24 månader

Mot STACK_H i båda fönstren.

Kör: /opt/momentum/venv/bin/python tools/skarpare_ranking.py
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

OUT = V2 / "research_k/skarpare_ranking_results.json"
COST = 0.002
SER = {"26": {k: (np.array([np.datetime64(x) for x in ds]), np.array(adj))
              for k, (ds, adj) in S.PS26.items()},
       "19": M.SERIE}


def W(F):
    return "19" if F is S.F19 else "26"


def mom(F, k, dt, weeks):
    s = SER[W(F)].get(k)
    if s is None:
        return None
    ds, v = s
    now = np.datetime64(dt)
    mal = now - np.timedelta64(int(7 * weeks), "D")
    i = int(np.searchsorted(ds, now, side="right")) - 1
    j = int(np.searchsorted(ds, mal, side="right")) - 1
    if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
        return None
    return float(v[i] / v[j] - 1)


def pct(vals):
    g = sorted((v, k) for k, v in vals.items() if v is not None)
    gr = defaultdict(list)
    for v, k in g:
        gr[v].append(k)
    rk, pos = {}, 1
    for v in sorted(gr):
        ks = gr[v]
        rk.update({k: (pos + pos + len(ks) - 1) / 2 / max(1, len(g)) for k in ks})
        pos += len(ks)
    return rk


def z(vals, vinsorisera=3.0):
    v = np.array([x for x in vals.values() if x is not None], dtype=float)
    if len(v) < 5:
        return {}
    mu, sd = float(np.mean(v)), float(np.std(v, ddof=1))
    if sd <= 0:
        return {}
    return {k: float(np.clip((x - mu) / sd, -vinsorisera, vinsorisera))
            for k, x in vals.items() if x is not None}


def bygg(F, metod, vikter=(0.5, 0.5), horisonter=(52, 78), samst_topp=None):
    ut = {}
    for dt in F["eval_dates"]:
        koder = [r["kod"] for r in F["rankings"][dt]]
        sig = {}
        for h in horisonter:
            raa = {k: mom(F, k, dt, h) for k in koder}
            if metod == "riskjust":
                raa = {k: (v / max(F["vol_fn"](k, dt), 0.05) if v is not None else None)
                       for k, v in raa.items()}
            sig[h] = z(raa) if metod == "z" else pct(raa)
        vw = dict(zip(horisonter, vikter)) if len(vikter) == len(horisonter) else \
            {h: 1.0 / len(horisonter) for h in horisonter}
        poang, giltiga = {}, []
        for k in koder:
            vs = [sig[h].get(k) for h in horisonter]
            if all(v is not None for v in vs):
                poang[k] = float(sum(vw[h] * sig[h][k] for h in horisonter))
                giltiga.append(k)
        if samst_topp:
            ordn = {h: sorted([k for k in giltiga], key=lambda k: -sig[h][k]) for h in horisonter}
            topp = set(giltiga)
            for h in horisonter:
                topp &= set(ordn[h][:samst_topp])
            for k in giltiga:
                if k not in topp:
                    poang[k] -= 10.0
        med = float(np.median(list(poang.values()))) if poang else 0.0
        sc = [{"kod": k, "score": poang.get(k, med)} for k in koder]
        sc.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = sc
    return ut


def sim(F, rankings, N=30, hyst_rank=35):
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    for pi, dt in enumerate(dts):
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:N]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
        if prevw:
            w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                and prevw.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * ts
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets)


BAS = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}


def main():
    ut = {"version": "SKARPARE_RANKING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "resultat": {}}
    print(f"  {'variant':<30}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}   repl")
    print(f"  {'baslinje (percentil 50/50)':<30}{S.stat(BAS['26'])['cagr']:>8.2%}{'—':>9}"
          f"{S.stat(BAS['19'])['cagr']:>9.2%}{'—':>9}")
    varianter = [
        ("A z-poäng 50/50", dict(metod="z")),
        ("B percentil 70/30 (12m tyngst)", dict(metod="pct", vikter=(0.7, 0.3))),
        ("B percentil 30/70 (18m tyngst)", dict(metod="pct", vikter=(0.3, 0.7))),
        ("C samstämmighet topp-60", dict(metod="pct", samst_topp=60)),
        ("C samstämmighet topp-40", dict(metod="pct", samst_topp=40)),
        ("D riskjusterat momentum", dict(metod="riskjust")),
        ("E tre horisonter 12+18+24", dict(metod="pct", horisonter=(52, 78, 104),
                                           vikter=(1/3, 1/3, 1/3))),
    ]
    for namn, kw in varianter:
        a26 = sim(S.F26, bygg(S.F26, **kw))
        a19 = sim(S.F19, bygg(S.F19, **kw))
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["resultat"][namn] = {"f2020_2026": {**S.stat(a26), **d26},
                                "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
        print(f"  {namn:<30}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}   {'JA' if rep else '-'}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in ut["resultat"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['resultat'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
