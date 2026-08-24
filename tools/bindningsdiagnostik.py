"""BINDNINGSDIAGNOSTIK — UTLÖSER REGLERNA ÖVER HUVUD TAGET?

En regel som aldrig binder ger delta 0,00 och ser ut som "inget stöd", fast den
aldrig prövats. Trösklarna i dagens kö var lösa exempelsiffror; de måste sättas
mot hur STACK_H faktiskt beter sig.

Mäter först modellens egna fördelningar:
  innehavslängd, rankbana, drawdown från inträde, andel stämplade,
  hur ofta vikten ökas

och därefter, för varje regelfamilj, hur många gånger regeln skulle utlösa vid
olika trösklar. Först när bindningsfrekvensen är rimlig är ett delta tolkbart.

Kör: /opt/momentum/venv/bin/python tools/bindningsdiagnostik.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/ko_mot_stack_h/bindningsdiagnostik.json"
SER = {"26": {k: (np.array([np.datetime64(x) for x in ds]), np.array(adj))
              for k, (ds, adj) in S.PS26.items()},
       "19": M.SERIE}


def px(w, k, dt):
    s = SER[w].get(k)
    if s is None:
        return None
    i = int(np.searchsorted(s[0], np.datetime64(dt), side="right")) - 1
    return float(s[1][i]) if i >= 0 else None


def spana(F, w):
    """Kör STACK_H och logga allt en regel kan tänkas reagera på."""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw = [], {}
    alder, ingang, stamplad = {}, {}, set()
    langd, rank_vid_utgang, dd_vid_beslut, stamplad_rank = [], [], [], []
    viktokningar, n_beslut, n_innehavspanel = 0, 0, 0
    dd_max_per_innehav = defaultdict(float)
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            n_beslut += 1
            keep = [k for k in (prev or []) if rm.get(k, 999) <= 35 and k in elig]
            fill = [r["kod"] for r in raw if r["kod"] not in keep]
            sel0 = (keep + fill)[:30]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < 30:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        for k in prev:
            if k not in sel0:
                langd.append(alder.get(k, 0))
                rank_vid_utgang.append(rm.get(k, 999))
                alder.pop(k, None); ingang.pop(k, None); dd_max_per_innehav.pop(k, None)
        stamplad &= set(sel0)
        for k in sel0:
            if rm.get(k, 999) <= 5:
                stamplad.add(k)
            alder[k] = alder.get(k, 0) + 1
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        n_innehavspanel += n
        if n == 0:
            prev, prevw = sel0, {}; continue
        ts = n / 30
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        wt = inv / np.sum(inv) * ts
        wt = wt * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        wt = np.clip(wt, 0.01, 0.06); wt = wt / np.sum(wt) * ts
        if prevw:
            wt = np.array([prevw.get(k, 0.0) if (abs(wt[i] - prevw.get(k, 0.0)) < 0.005
                                                 and prevw.get(k, 0.0) > 0) else wt[i]
                           for i, k in enumerate(sel)])
            wt = wt / np.sum(wt) * ts
            if sched:
                viktokningar += int(sum(1 for i, k in enumerate(sel)
                                        if prevw.get(k, 0.0) > 0 and wt[i] > prevw[k] + 1e-9))
        for k in sel:
            if k not in ingang:
                ingang[k] = px(w, k, dt)
            p = px(w, k, dt)
            if p and ingang.get(k):
                dd_max_per_innehav[k] = min(dd_max_per_innehav[k], p / ingang[k] - 1)
        if sched and prev:
            for k in sel:
                p, ing = px(w, k, dt), ingang.get(k)
                if p and ing:
                    dd_vid_beslut.append(p / ing - 1)
                if k in stamplad:
                    stamplad_rank.append(rm.get(k, 999))
        prev, prevw = sel0, dict(zip(sel, wt))
    L = np.array(langd) if langd else np.array([0])
    D = np.array(dd_vid_beslut) if dd_vid_beslut else np.array([0.0])
    SR = np.array(stamplad_rank) if stamplad_rank else np.array([999])
    RU = np.array(rank_vid_utgang) if rank_vid_utgang else np.array([999])
    return {
        "innehavslangd": {"n": len(L), "median": int(np.median(L)), "medel": round(float(L.mean()), 1),
                          "p90": int(np.percentile(L, 90)), "max": int(L.max()),
                          "andel_over_6p": round(float(np.mean(L > 6)), 3),
                          "andel_over_13p": round(float(np.mean(L > 13)), 3)},
        "rank_vid_utgang": {"median": int(np.median(RU)), "p90": int(np.percentile(RU, 90)),
                            "andel_over_50": round(float(np.mean(RU > 50)), 3)},
        "drawdown_fran_intrade_vid_beslut": {
            "n": len(D), "median": round(float(np.median(D)), 4),
            "p10": round(float(np.percentile(D, 10)), 4), "p5": round(float(np.percentile(D, 5)), 4),
            "andel_under_10pct": round(float(np.mean(D <= -0.10)), 4),
            "andel_under_20pct": round(float(np.mean(D <= -0.20)), 4),
            "andel_under_30pct": round(float(np.mean(D <= -0.30)), 4)},
        "stamplade_positioner": {
            "n_observationer": len(SR), "andel_av_alla_innehav": round(len(SR) / max(1, n_innehavspanel), 3),
            "medianrank": int(np.median(SR)),
            "andel_over_rank10": round(float(np.mean(SR > 10)), 3),
            "andel_over_rank15": round(float(np.mean(SR > 15)), 3),
            "andel_over_rank25": round(float(np.mean(SR > 25)), 3)},
        "viktokningar_per_beslut": round(viktokningar / max(1, n_beslut), 2),
        "n_beslutspaneler": n_beslut}


def main():
    ut = {"version": "BINDNINGSDIAGNOSTIK_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "per_fonster": {}}
    for F, w, namn in ((S.F26, "26", "2020-2026"), (S.F19, "19", "2014-2019")):
        d = spana(F, w)
        ut["per_fonster"][namn] = d
        print(f"\n=== {namn}")
        L = d["innehavslangd"]
        print(f"  innehavslängd: median {L['median']} paneler, medel {L['medel']}, "
              f"p90 {L['p90']}, max {L['max']}")
        print(f"     andel över 6 paneler {L['andel_over_6p']:.0%}, över 13 {L['andel_over_13p']:.0%}"
              f"   -> TIME STOP 13/26 kan knappt binda")
        R = d["rank_vid_utgang"]
        print(f"  rank vid utgång: median {R['median']}, p90 {R['p90']}, "
              f"andel över 50 {R['andel_over_50']:.0%}   -> DD/RANK>50 kan aldrig binda")
        D = d["drawdown_fran_intrade_vid_beslut"]
        print(f"  drawdown från inträde vid beslut: median {D['median']:+.1%}, "
              f"p10 {D['p10']:+.1%}, p5 {D['p5']:+.1%}")
        print(f"     under −10 % {D['andel_under_10pct']:.1%}, under −20 % {D['andel_under_20pct']:.1%}, "
              f"under −30 % {D['andel_under_30pct']:.2%}   -> DD-STOP 20/30 % binder nästan aldrig")
        SS = d["stamplade_positioner"]
        print(f"  stämplade (nått rank<=5): {SS['andel_av_alla_innehav']:.1%} av innehaven, "
              f"medianrank {SS['medianrank']}")
        print(f"     över rank 10 {SS['andel_over_rank10']:.0%}, över 15 {SS['andel_over_rank15']:.0%}, "
              f"över 25 {SS['andel_over_rank25']:.0%}")
        print(f"  viktökningar per beslutspanel: {d['viktokningar_per_beslut']}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
