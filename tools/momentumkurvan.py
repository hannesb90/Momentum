"""VAR PÅ SIN EGEN MOMENTUMKURVA ÄR BOLAGET NÄR VI KÖPER?

Rankningen är tvärsnittlig: percentil av 12m- och 18m-momentum mot alla andra
samma panel. Den säger ingenting om bolagets EGEN momentumbana. En aktie kan
rankas högt medan dess momentum redan toppat och fallit i flera månader.

Mäter tre lägesmått per innehav och panel:
  toppnara   är mom_12m nu det högsta av de senaste 6 panelerna?
  lutning    mom_12m nu minus mom_12m för 3 paneler sedan
  percentil  var i sin egen 12-panelsfördelning ligger mom_12m nu?

Steg 1 (deskriptivt): framåtavkastning betingad på läget i kurvan.
Steg 2 (regel): entryfilter mot STACK_H i båda fönstren.

Kör: /opt/momentum/venv/bin/python tools/momentumkurvan.py
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

OUT = V2 / "research_k/momentumkurvan_results.json"
COST = 0.002

SER = {"26": {k: (np.array([np.datetime64(x) for x in ds]), np.array(adj))
              for k, (ds, adj) in S.PS26.items()},
       "19": M.SERIE}


def W(F):
    return "19" if F is S.F19 else "26"


def mom(F, k, dt, weeks=52):
    s = SER[W(F)].get(k)
    if s is None:
        return None
    ds, v = s
    now = np.datetime64(dt)
    mal = now - np.timedelta64(7 * weeks, "D")
    i = int(np.searchsorted(ds, now, side="right")) - 1
    j = int(np.searchsorted(ds, mal, side="right")) - 1
    if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
        return None
    return float(v[i] / v[j] - 1)


_kurva = {}


def lage(F, k, dt, dts, pi):
    """(toppnara, lutning_3p, percentil_i_egen_12p_fordelning)"""
    key = (W(F), k, dt)
    if key in _kurva:
        return _kurva[key]
    hist = []
    for j in range(max(0, pi - 11), pi + 1):
        m = mom(F, k, dts[j])
        if m is not None:
            hist.append(m)
    if len(hist) < 4:
        _kurva[key] = (None, None, None)
        return _kurva[key]
    nu = hist[-1]
    sex = hist[-6:] if len(hist) >= 6 else hist
    toppnara = nu >= max(sex) - 1e-12
    lut = nu - hist[-4] if len(hist) >= 4 else None
    pct = float(np.mean(np.array(hist) <= nu))
    _kurva[key] = (toppnara, lut, pct)
    return _kurva[key]


def steg1(F, namn):
    dts, ret = F["eval_dates"], F["returns_map"]
    grupper = defaultdict(list)
    for pi, dt in enumerate(dts):
        for r in F["rankings"][dt][:30]:
            k = r["kod"]
            if not F["sma_fn"](k, dt):
                continue
            tn, lut, pct = lage(F, k, dt, dts, pi)
            if tn is None:
                continue
            fw = 1.0
            for j in range(pi, min(pi + 3, len(dts))):
                fw *= 1 + ret.get((k, dts[j]), 0.0)
            fw -= 1
            grupper["toppnära" if tn else "ej toppnära"].append(fw)
            if lut is not None:
                grupper["stigande momentum" if lut > 0 else "fallande momentum"].append(fw)
            if pct is not None:
                b = "percentil 0-50" if pct <= 0.5 else ("percentil 50-90" if pct <= 0.9 else "percentil 90-100")
                grupper[b].append(fw)
    ut = {}
    print(f"\n  {namn} — framåtavkastning 3 paneler")
    for g in ("toppnära", "ej toppnära", "stigande momentum", "fallande momentum",
              "percentil 0-50", "percentil 50-90", "percentil 90-100"):
        a = np.array(grupper.get(g, []))
        if len(a) < 20:
            continue
        t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
        ut[g] = {"n": len(a), "medel": round(float(a.mean()), 4),
                 "median": round(float(np.median(a)), 4), "t": round(t, 2)}
        print(f"    {g:<22}n={len(a):>5}  medel {a.mean():+7.2%}  median {np.median(a):+7.2%}  t {t:+5.2f}")
    return ut


def sim(F, N=30, filt=None, hyst_rank=35):
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            kand = [r["kod"] for r in raw if r["kod"] not in keep]
            if filt:
                kand = [k for k in kand if filt(F, k, dt, dts, pi)]
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


def main():
    ut = {"version": "MOMENTUMKURVAN_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    print("STEG 1 — var i sin egen momentumkurva, och vad händer sedan?")
    ut["steg1"] = {"2020_2026": steg1(S.F26, "2020-2026"), "2014_2019": steg1(S.F19, "2014-2019")}

    print("\nSTEG 2 — som entryfilter mot STACK_H")
    print(f"  {'filter':<34}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    filter_ = {
        "köp inte toppnära momentum": lambda F, k, dt, dts, pi: not (lage(F, k, dt, dts, pi)[0] or False),
        "köp bara toppnära momentum": lambda F, k, dt, dts, pi: bool(lage(F, k, dt, dts, pi)[0]),
        "köp bara stigande momentum": lambda F, k, dt, dts, pi: (lage(F, k, dt, dts, pi)[1] or 0) > 0,
        "köp bara fallande momentum": lambda F, k, dt, dts, pi: (lage(F, k, dt, dts, pi)[1] or 0) <= 0,
        "köp inte percentil >90": lambda F, k, dt, dts, pi: (lage(F, k, dt, dts, pi)[2] or 0) <= 0.9,
        "köp bara percentil >90": lambda F, k, dt, dts, pi: (lage(F, k, dt, dts, pi)[2] or 0) > 0.9,
    }
    ut["steg2"] = {}
    for namn, f in filter_.items():
        a26, a19 = sim(S.F26, filt=f), sim(S.F19, filt=f)
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["steg2"][namn] = {"f2020_2026": {**S.stat(a26), **d26},
                             "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
        print(f"  {namn:<34}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
              f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in ut["steg2"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['steg2'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
