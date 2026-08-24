"""KÖ MOT STACK_H, DEL 3 — DE SISTA FYRA FAMILJERNA

Del 2 hade en bugg: drawdown-baserade regler läste priser endast i
2014-2019-fönstret (`if F is S.F19`), så de kunde aldrig utlösas på 2020-2026.
Här är prisåtkomsten fönsteroberoende.

  E1  drawdown-stop 20/30 %
  E2  drawdown-rank-exit (N3:s dd30/dd40 x rank50/rank70)
  E3  skip-månad i rankningen (12-1, 12-2)
  E4  T4 aliasering — matcha signalens lookback mot ombalanseringsfrekvensen
  E5  svansstruktur på STACK_H (diagnostik, ingen variant)

Kör: /opt/momentum/venv/bin/python tools/ko_mot_stack_h_del3.py
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

UT = V2 / "research_k/ko_mot_stack_h"
LOGG = UT / "_logg_del3.md"
COST = 0.002


def logga(t):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(t + "\n")
    print(t, flush=True)


# ---------- fönsteroberoende prisåtkomst ----------
SER = {"26": {k: (np.array([np.datetime64(x) for x in ds]), np.array(adj))
              for k, (ds, adj) in S.PS26.items()},
       "19": M.SERIE}


def W(F):
    return "19" if F is S.F19 else "26"


def px(F, k, dt):
    s = SER[W(F)].get(k)
    if s is None:
        return None
    i = int(np.searchsorted(s[0], np.datetime64(dt), side="right")) - 1
    return float(s[1][i]) if i >= 0 else None


def sim(F, N=30, dd_stop=None, dd_rank_exit=None, rankings_override=None, hyst_rank=35):
    rankings = rankings_override or F["rankings"]
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets, ingang = [], {}, [], {}
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = rankings[dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            keep = []
            for k in (prev or []):
                if k not in elig:
                    continue
                r_ = rm.get(k, 999)
                p, ing = px(F, k, dt), ingang.get(k)
                if dd_stop and p and ing and p / ing - 1 <= -dd_stop:
                    continue
                if dd_rank_exit:
                    dtr, rtr = dd_rank_exit
                    if p and ing and p / ing - 1 <= -dtr and r_ > rtr:
                        continue
                if r_ <= hyst_rank:
                    keep.append(k)
            fill = [r["kod"] for r in raw if r["kod"] not in keep]
            sel0 = (keep + fill)[:N]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        for k in prev:
            if k not in sel0:
                ingang.pop(k, None)
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
        for k in sel:
            if k not in ingang:
                ingang[k] = px(F, k, dt)
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets)


def bygg_rank(F, skip_v):
    """Rankning med momentum som slutar skip_v veckor före panelen."""
    ut = {}
    for dt in F["eval_dates"]:
        rows = []
        for r in F["rankings"][dt]:
            k = r["kod"]; s = SER[W(F)].get(k)
            if s is None:
                continue
            ds, v = s; now = np.datetime64(dt)
            i = int(np.searchsorted(ds, now - np.timedelta64(7 * skip_v, "D"), side="right")) - 1
            d = {"kod": k}
            for wk, nm in ((52, "a"), (78, "b")):
                j = int(np.searchsorted(ds, now - np.timedelta64(7 * (wk + skip_v), "D"), side="right")) - 1
                d[nm] = float(v[i] / v[j] - 1) if (i >= 0 and j >= 0) else None
            rows.append(d)
        for col in ("a", "b"):
            g = sorted((x[col], x["kod"]) for x in rows if x[col] is not None)
            gr = defaultdict(list)
            for val, kod in g:
                gr[val].append(kod)
            rk, pos = {}, 1
            for val in sorted(gr):
                ks = gr[val]
                rk.update({kod: (pos + pos + len(ks) - 1) / 2 / max(1, len(g)) for kod in ks})
                pos += len(ks)
            for x in rows:
                x[col + "r"] = rk.get(x["kod"])
        raa = [0.5 * (x["ar"] + x["br"]) if x["ar"] is not None and x["br"] is not None else None
               for x in rows]
        med = float(np.median([y for y in raa if y is not None])) if any(y is not None for y in raa) else .5
        sc = [{**x, "score": med if y is None else y} for x, y in zip(rows, raa)]
        sc.sort(key=lambda z: (z["score"], z["kod"]), reverse=True)
        ut[dt] = sc
    return ut


BAS = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}


def rapport(namn, kw):
    a26, a19 = sim(S.F26, **kw), sim(S.F19, **kw)
    d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
    rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
    logga(f"  {namn:<34}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
          f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
    return {"f2020_2026": {**S.stat(a26), **d26}, "f2014_2019": {**S.stat(a19), **d19},
            "bada_positiva": bool(rep)}


def main():
    logga(f"\n# Kö mot STACK_H del 3 — {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n")
    logga(f"  {'variant':<34}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    ut = {"version": "KO_MOT_STACK_H_DEL3_V1", "E": {}}
    E = ut["E"]
    for dd in (0.20, 0.30):
        E[f"E1_dd_stop_{int(dd*100)}"] = rapport(f"drawdown-stop {int(dd*100)} %", dict(dd_stop=dd))
    for dd, rk in ((0.30, 50), (0.30, 70), (0.40, 50), (0.40, 70)):
        E[f"E2_dd{int(dd*100)}_rank{rk}"] = rapport(f"dd{int(dd*100)} + rank>{rk}",
                                                    dict(dd_rank_exit=(dd, rk)))
    for skip, nm in ((4, "skip 4 veckor (12-1)"), (8, "skip 8 veckor (12-2)")):
        a26 = sim(S.F26, rankings_override=bygg_rank(S.F26, skip))
        a19 = sim(S.F19, rankings_override=bygg_rank(S.F19, skip))
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        logga(f"  {nm:<34}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
              f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
        E[f"E3_{nm}"] = {"f2020_2026": {**S.stat(a26), **d26},
                         "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
    # E4: T4 aliasering — matcha signalens lookback mot ombalanseringen (8 v)
    for skip, nm in ((2, "aliasering: signal -2v"),):
        a26 = sim(S.F26, rankings_override=bygg_rank(S.F26, skip))
        a19 = sim(S.F19, rankings_override=bygg_rank(S.F19, skip))
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        logga(f"  {nm:<34}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
              f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
        E[f"E4_{nm}"] = {"f2020_2026": {**S.stat(a26), **d26},
                         "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
    # E5: svansstruktur på STACK_H
    sv = {}
    for w_, nm in (("26", "2020-2026"), ("19", "2014-2019")):
        x = BAS[w_]
        wl = np.cumprod(1 + x); b3 = np.sort(x)[-3:]
        u3 = float(np.prod(1 + np.array([y for y in x if y not in b3])))
        sv[nm] = {"medel_panel": round(float(x.mean()), 4), "median_panel": round(float(np.median(x)), 4),
                  "andel_negativa": round(float(np.mean(x < 0)), 3),
                  "andel_uppgang_fran_3_basta": round(1 - (u3 - 1) / (float(wl[-1]) - 1), 3)}
        logga(f"  svans {nm}: medel {sv[nm]['medel_panel']:+.2%} median {sv[nm]['median_panel']:+.2%}, "
              f"{sv[nm]['andel_uppgang_fran_3_basta']:.0%} ur 3 bästa paneler")
    ut["E5_svansstruktur"] = sv
    (UT / "resultat_del3.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in E.values() if v["bada_positiva"])
    logga(f"\nPositiva i BÅDA fönstren: {n} av {len(E)}")
    logga(f"Skrivet: {UT/'resultat_del3.json'}")


if __name__ == "__main__":
    main()
