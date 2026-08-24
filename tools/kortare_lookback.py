"""ANDRA VÄGAR MOT "SENA PÅ BOLLEN"

Allt vi prövat modifierar den långsamma signalen. Detta byter ut den.

A. KORTARE LOOKBACK som rankningssignal.
   Championen är 0,5 x rank(12m) + 0,5 x rank(18m). SPARF prövade 12m mot
   12m+18m — alltså längre. Kortare kombinationer är oprövade:
   3+6, 6+12, 3+12, 6+18, samt rena 3m, 6m.

B. TVÅ HASTIGHETER. Kärna på 12+18 plus en satellitdel vald på 3+6.

C. FÖRVARNINGSPOOL. Köp namn på rank 31-60 vars rank förbättrats kraftigt,
   och håll dem tills de når topp-30 eller faller ur 60.

Allt mot STACK_H i båda fönstren, med samma tvåfönsterkriterium.

Kör: /opt/momentum/venv/bin/python tools/kortare_lookback.py
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

OUT = V2 / "research_k/kortare_lookback_results.json"
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


def bygg(F, veckor):
    """Rankning på medelvärdet av percentilrankerna för de angivna fönstren."""
    ut = {}
    for dt in F["eval_dates"]:
        rows = [{"kod": r["kod"]} for r in F["rankings"][dt]]
        for w in veckor:
            for r in rows:
                r[f"m{w}"] = mom(F, r["kod"], dt, w)
            g = sorted((r[f"m{w}"], r["kod"]) for r in rows if r[f"m{w}"] is not None)
            gr = defaultdict(list)
            for val, kod in g:
                gr[val].append(kod)
            rk, pos = {}, 1
            for val in sorted(gr):
                ks = gr[val]
                rk.update({kod: (pos + pos + len(ks) - 1) / 2 / max(1, len(g)) for kod in ks})
                pos += len(ks)
            for r in rows:
                r[f"r{w}"] = rk.get(r["kod"])
        raa = []
        for r in rows:
            vs = [r[f"r{w}"] for w in veckor]
            raa.append(float(np.mean(vs)) if all(v is not None for v in vs) else None)
        med = float(np.median([y for y in raa if y is not None])) if any(y is not None for y in raa) else .5
        sc = [{**r, "score": med if y is None else y} for r, y in zip(rows, raa)]
        sc.sort(key=lambda z: (z["score"], z["kod"]), reverse=True)
        ut[dt] = sc
    return ut


def sim(F, rankings=None, N=30, hyst_rank=35, satellit_rank=None, sat_platser=0,
        forvarning=False):
    R = rankings or F["rankings"]
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    for pi, dt in enumerate(dts):
        raw = R[dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            kand = [r["kod"] for r in raw if r["kod"] not in keep]
            if sat_platser and satellit_rank is not None:
                srm = {r["kod"]: i + 1 for i, r in enumerate(satellit_rank[dt])}
                sat = sorted([k for k in kand], key=lambda k: srm.get(k, 999))[:sat_platser]
                kand = sat + [k for k in kand if k not in sat]
            if forvarning and pi > 0:
                fr = {r["kod"]: i + 1 for i, r in enumerate(R[dts[pi - 1]])}
                lyft = sorted([k for k in kand if 30 < rm.get(k, 999) <= 60
                               and fr.get(k, 999) - rm.get(k, 999) >= 20],
                              key=lambda k: rm.get(k, 999))[:5]
                kand = lyft + [k for k in kand if k not in lyft]
            sel0 = (keep + kand)[:N]
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


def rap(namn, a26, a19, ut):
    d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
    rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
    ut[namn] = {"f2020_2026": {**S.stat(a26), **d26}, "f2014_2019": {**S.stat(a19), **d19},
                "bada_positiva": bool(rep)}
    print(f"  {namn:<28}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
          f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}   {'JA' if rep else '-'}")


def main():
    ut = {"version": "KORTARE_LOOKBACK_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "A_lookback": {}, "B_tva_hastigheter": {}, "C_forvarning": {}}
    print("A. KORTARE LOOKBACK SOM RANKNINGSSIGNAL")
    print(f"  {'signal':<28}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}   repl")
    print(f"  {'baslinje 52+78v':<28}{S.stat(BAS['26'])['cagr']:>8.2%}{'—':>9}"
          f"{S.stat(BAS['19'])['cagr']:>9.2%}{'—':>9}")
    for vk, namn in (((13, 26), "13+26v (3+6 mån)"), ((26, 52), "26+52v (6+12 mån)"),
                     ((13, 52), "13+52v (3+12 mån)"), ((26, 78), "26+78v (6+18 mån)"),
                     ((13,), "endast 13v (3 mån)"), ((26,), "endast 26v (6 mån)"),
                     ((13, 26, 52), "13+26+52v")):
        a26 = sim(S.F26, rankings=bygg(S.F26, vk))
        a19 = sim(S.F19, rankings=bygg(S.F19, vk))
        rap(namn, a26, a19, ut["A_lookback"])

    print("\nB. TVÅ HASTIGHETER — kärna 12+18, satellitplatser valda på 3+6 mån")
    print(f"  {'variant':<28}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}   repl")
    s26, s19 = bygg(S.F26, (13, 26)), bygg(S.F19, (13, 26))
    for p in (3, 5, 8):
        a26 = sim(S.F26, satellit_rank=s26, sat_platser=p)
        a19 = sim(S.F19, satellit_rank=s19, sat_platser=p)
        rap(f"{p} snabba platser", a26, a19, ut["B_tva_hastigheter"])

    print("\nC. FÖRVARNINGSPOOL — namn på rank 31-60 som lyft minst 20 platser")
    print(f"  {'variant':<28}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}   repl")
    a26, a19 = sim(S.F26, forvarning=True), sim(S.F19, forvarning=True)
    rap("förvarningspool 5 platser", a26, a19, ut["C_forvarning"])

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for g in (ut["A_lookback"], ut["B_tva_hastigheter"], ut["C_forvarning"])
            for v in g.values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
