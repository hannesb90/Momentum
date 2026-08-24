"""KÖ MOT STACK_H, DEL 4 — ENTRYFILTER OCH VIKTTILT UR SESSIONERNA

De familjer ur sessionerna 2026-08-13/14 som är prisbaserade och därför körbara
i båda fönstren, men som ännu inte prövats mot STACK_H:

  F1  tröskelklättraren som entryfilter (kräv N passerade rankströsklar)
  F2  rankförändring som entryfilter (kräv att namnet klättrat)
  F3  rankbaserad vikttilt (vikt ~ rank^±a ovanpå ERC)
  F4  volymexplosion som entryfilter (volym mot 20-dagarsmedian)
  F5  dippfilter vid inträde (köp inte / köp bara namn som fallit senaste 4v)
  F6  fångstgrad korrekt mätt: andel av namnets rörelse som portföljen fångade

Volym hämtas ur EODHD-arkivet för båda fönstren.

Kör: /opt/momentum/venv/bin/python tools/ko_mot_stack_h_del4.py
"""
from __future__ import annotations
import gzip, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

UT = V2 / "research_k/ko_mot_stack_h"
LOGG = UT / "_logg_del4.md"
COST = 0.002

SER = {"26": {k: (np.array([np.datetime64(x) for x in ds]), np.array(adj))
              for k, (ds, adj) in S.PS26.items()},
       "19": M.SERIE}


def logga(t):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(t + "\n")
    print(t, flush=True)


def W(F):
    return "19" if F is S.F19 else "26"


# ---------- volym ur arkivet ----------
_vol_cache = {}


def volym(k, dt):
    if k not in _vol_cache:
        rows = None
        for kat in ("active", "delisted"):
            p = EOD / kat / "eod" / f"{k}.json.gz"
            if p.exists():
                try:
                    with gzip.open(p, "rt") as f:
                        rows = json.load(f)
                    break
                except Exception:
                    pass
        _vol_cache[k] = ({r["date"]: r.get("volume") or 0 for r in rows},
                         [r["date"] for r in rows]) if rows else ({}, [])
    m, ds = _vol_cache[k]
    if not ds:
        return None
    i = np.searchsorted(ds, dt, side="right") - 1
    if i < 20:
        return None
    hist = [m.get(d, 0) for d in ds[i - 20:i]]
    hist = [h for h in hist if h]
    v = m.get(ds[i], 0)
    return (v / float(np.median(hist))) if (v and hist and np.median(hist) > 0) else None


def idx(F, k, dt):
    s = SER[W(F)].get(k)
    if s is None:
        return None
    i = int(np.searchsorted(s[0], np.datetime64(dt), side="right")) - 1
    return i if i >= 0 else None


def mom_dagar(F, k, dt, dagar):
    i = idx(F, k, dt); s = SER[W(F)].get(k)
    if i is None or s is None or i < dagar:
        return None
    return float(s[1][i] / s[1][i - dagar] - 1)


def sim(F, N=30, entry_filter=None, rank_tilt=0.0, hyst_rank=35, logga_fangst=False):
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    fangst = []
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = F["rankings"][dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            kand = [r["kod"] for r in raw if r["kod"] not in keep]
            if entry_filter:
                kand = [k for k in kand if entry_filter(F, k, dt, rm)]
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
        if rank_tilt:
            rr = np.array([max(1, rm.get(k, N)) for k in sel], dtype=float)
            w = w * (rr ** (-rank_tilt))
            w = w / np.sum(w) * ts
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
        rets = np.array([ret.get((k, dt), 0.0) for k in sel])
        if logga_fangst:
            for k, wi, ri in zip(sel, w, rets):
                if abs(ri) > 1e-9:
                    fangst.append((ri, wi * ri / abs(ri) * np.sign(ri)))
        nets.append(float(np.sum(w * rets)) - COST * turn)
        prev, prevw = sel0, curr
    return (np.array(nets), fangst) if logga_fangst else np.array(nets)


BAS = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}


def rapport(namn, kw):
    a26, a19 = sim(S.F26, **kw), sim(S.F19, **kw)
    d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
    rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
    logga(f"  {namn:<36}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
          f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
    return {"f2020_2026": {**S.stat(a26), **d26}, "f2014_2019": {**S.stat(a19), **d19},
            "bada_positiva": bool(rep)}


def main():
    logga(f"\n# Kö mot STACK_H del 4 — {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n")
    logga(f"  {'variant':<36}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    ut = {"version": "KO_MOT_STACK_H_DEL4_V1", "F": {}}
    T = ut["F"]

    # F1 tröskelklättrare: kräv att namnet passerat minst k av trösklarna 100/60/40 senaste 6 paneler
    def klattrare(k_min):
        def f(F, k, dt, rm):
            dts = F["eval_dates"]; pi = dts.index(dt)
            rs = [F["rankings"]  # rank vid tidigare paneler
                  for _ in ()]
            banor = []
            for j in range(max(0, pi - 6), pi + 1):
                d2 = dts[j]
                rk = {r["kod"]: i + 1 for i, r in enumerate(F["rankings"][d2])}.get(k)
                if rk:
                    banor.append(rk)
            if len(banor) < 2:
                return True
            passerade = sum(1 for tr in (100, 60, 40)
                            if any(a > tr >= b for a, b in zip(banor, banor[1:])))
            return passerade >= k_min
        return f
    for km in (1, 2):
        T[f"F1_klattrare_min{km}"] = rapport(f"tröskelklättrare, minst {km} tröskel",
                                             dict(entry_filter=klattrare(km)))

    # F2 rankförändring: kräv att namnet klättrat sedan förra panelen
    def klattrat(F, k, dt, rm):
        dts = F["eval_dates"]; pi = dts.index(dt)
        if pi == 0:
            return True
        fr = {r["kod"]: i + 1 for i, r in enumerate(F["rankings"][dts[pi - 1]])}.get(k)
        return fr is None or rm.get(k, 999) < fr
    T["F2_klattrat"] = rapport("kräv klättring sedan förra panelen", dict(entry_filter=klattrat))

    # F3 rankviktning
    for a in (0.15, 0.3, -0.15):
        T[f"F3_ranktilt_{a}"] = rapport(f"rankvikt-tilt a={a:+.2f}", dict(rank_tilt=a))

    # F4 volymexplosion
    def volfilter(minkvot):
        def f(F, k, dt, rm):
            v = volym(k, dt)
            return v is None or v >= minkvot
        return f
    for mk in (1.5, 3.0):
        T[f"F4_volym_{mk}"] = rapport(f"volym >= {mk}x 20d-median", dict(entry_filter=volfilter(mk)))

    # F5 dippfilter
    def dipp(krav):
        def f(F, k, dt, rm):
            m = mom_dagar(F, k, dt, 20)
            if m is None:
                return True
            return m < 0 if krav == "bara_dipp" else m >= 0
        return f
    T["F5_bara_dippade"] = rapport("köp bara namn som fallit 4v", dict(entry_filter=dipp("bara_dipp")))
    T["F5_inga_dippade"] = rapport("köp inte namn som fallit 4v", dict(entry_filter=dipp("ingen_dipp")))

    # F6 fångstgrad
    fang = {}
    for F, nm in ((S.F26, "2020-2026"), (S.F19, "2014-2019")):
        _, fg = sim(F, logga_fangst=True)
        v = [w for r, w in fg if r > 0]; f_ = [w for r, w in fg if r < 0]
        fang[nm] = {"n_vinnare": len(v), "n_forlorare": len(f_),
                    "fangst_vinnare": round(float(np.mean(v)), 5),
                    "fangst_forlorare": round(float(np.mean(f_)), 5),
                    "asymmetri": round(float(np.mean(v) - abs(np.mean(f_))), 5)}
        logga(f"  fångst {nm}: vinnare {fang[nm]['fangst_vinnare']:.4f} "
              f"(n={len(v)}), förlorare {fang[nm]['fangst_forlorare']:.4f} (n={len(f_)})")
    ut["F6_fangstgrad"] = fang

    (UT / "resultat_del4.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in T.values() if v["bada_positiva"])
    logga(f"\nPositiva i BÅDA fönstren: {n} av {len(T)}")
    logga(f"Skrivet: {UT/'resultat_del4.json'}")


if __name__ == "__main__":
    main()
