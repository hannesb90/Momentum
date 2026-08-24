"""KÖ MOT STACK_H, DEL 2 — RESTEN AV TESTERNA

Del 1 körde portföljstorlek, NTZ-band, ombalansering, hysteresgräns,
komponentablation och köpband. Detta är resten, mot samma basmodell och i båda
fönstren.

Ur dagens familjer:
  C1 låt vinnarna rida            C2 skip-månad i rankningen
  C3 topp-5-spärr                 C4 snäv utgång för stämplade
  C5 återinträdesspärr            C6 satellitplats för stigande återvändare
  C7 asymmetrisk ombalansering    C8 time stop
  C9 drawdown-stop                C10 trendstyrka som filter
  C11 korrelationsfyllnad         C12 svansstruktur

Ur sessionerna 2026-08-13/14:
  D1 T4 aliasering — matcha signalens lookback mot ombalanseringsfrekvensen
  D2 minsta innehavstid efter viktökning
  D3 drawdown-rank-exit (N3:s dd30/dd40 x rank50/rank70)

Kör: /opt/momentum/venv/bin/python tools/ko_mot_stack_h_del2.py
"""
from __future__ import annotations
import json, math, sys, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

UT = V2 / "research_k/ko_mot_stack_h"
LOGG = UT / "_logg_del2c.md"
COST = 0.002


def logga(t):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(t + "\n")
    print(t, flush=True)


def sim(F, N=30, lat_rida=False, stampel_exit=None, stampel_spar=None, karens=0,
        satellit=0, asym=False, time_stop=None, dd_stop=None, trend_min=None,
        korr_gr=None, hyst_rank=35, min_hold_efter_okning=0, dd_rank_exit=None,
        rankings_override=None):
    """STACK_H med valfri överlagring. Returnerar nettoserien."""
    rankings = rankings_override or F["rankings"]
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    stamplad, var_stamplad, har_haft, sparr = set(), set(), set(), {}
    alder, ingang, okt_vid = {}, {}, {}
    beslut_nr = 0
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            beslut_nr += 1
            if prev:
                keep = []
                for k in prev:
                    if k not in elig:
                        continue
                    r_ = rm.get(k, 999)
                    gr = hyst_rank
                    if stampel_spar and k in stamplad:
                        gr = stampel_spar
                    if stampel_exit and k in stamplad and r_ > stampel_exit:
                        sparr[k] = beslut_nr + karens
                        continue
                    if time_stop and alder.get(k, 0) >= time_stop:
                        continue
                    if dd_stop and k in ingang:
                        i_ = M._idx(k, dt) if F is S.F19 else None
                        if i_ is not None and ingang[k] and M.SERIE[k][1][i_] / ingang[k] - 1 <= -dd_stop:
                            continue
                    if dd_rank_exit and k in ingang:
                        dd_tr, rank_tr = dd_rank_exit
                        i_ = M._idx(k, dt) if F is S.F19 else None
                        if (i_ is not None and ingang[k]
                                and M.SERIE[k][1][i_] / ingang[k] - 1 <= -dd_tr and r_ > rank_tr):
                            continue
                    if min_hold_efter_okning and okt_vid.get(k) is not None \
                            and beslut_nr - okt_vid[k] < min_hold_efter_okning:
                        keep.append(k); continue
                    if r_ <= gr:
                        keep.append(k)
            else:
                keep = []
            kand = [r["kod"] for r in raw if r["kod"] not in keep
                    and sparr.get(r["kod"], -1) <= beslut_nr]
            if trend_min is not None:
                kand = [k for k in kand if _trend(F, k, dt) is not None and _trend(F, k, dt) >= trend_min]
            if satellit and prev:
                sat = [k for k in kand if k in var_stamplad][:satellit]
                kand = sat + [k for k in kand if k not in sat]
            if korr_gr is not None:
                valda, vek = [], []
                for k in keep + kand:
                    if len(valda) >= N:
                        break
                    v = _dagsret(F, k, dt)
                    if v is not None and any(abs(float(np.corrcoef(v, u)[0, 1])) > korr_gr for u in vek):
                        continue
                    valda.append(k)
                    if v is not None:
                        vek.append(v)
                sel0 = valda[:N]
            else:
                sel0 = (keep + kand)[:N]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        for k in prev:
            if k not in sel0:
                har_haft.add(k)
                (var_stamplad.add(k) if k in stamplad else var_stamplad.discard(k))
                alder.pop(k, None); ingang.pop(k, None); okt_vid.pop(k, None)
        stamplad &= set(sel0)
        for k in sel0:
            if rm.get(k, 999) <= 5:
                stamplad.add(k)
            alder[k] = alder.get(k, 0) + 1
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / N
        if lat_rida and prevw and not sched:
            w = np.array([prevw.get(k, ts / n) for k in sel]); w = w / np.sum(w) * ts
        else:
            vols = np.array([volf(k, dt) for k in sel])
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            w = inv / np.sum(inv) * ts
            w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
            w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
            if prevw:
                w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                    and prevw.get(k, 0.0) > 0) else w[i]
                              for i, k in enumerate(sel)])
                if asym and sched:
                    w = np.array([min(w[i], prevw.get(k, w[i]))
                                  if (prevw.get(k, 0.0) > 0
                                      and ret.get((k, dts[pi - 1]), 0.0) < 0) else w[i]
                                  for i, k in enumerate(sel)])
                w = w / np.sum(w) * ts
        if sched and prevw:
            for i, k in enumerate(sel):
                if prevw.get(k, 0.0) > 0 and w[i] > prevw[k] + 1e-9:
                    okt_vid[k] = beslut_nr
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        for k in sel:
            if k not in ingang:
                i_ = M._idx(k, dt) if F is S.F19 else None
                ingang[k] = float(M.SERIE[k][1][i_]) if i_ is not None else None
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets)


_tc, _rc = {}, {}


def _serie(F, k):
    if F is S.F19:
        return M.SERIE.get(k)
    ds, adj = S.PS26.get(k, (None, None))
    return (np.array([np.datetime64(x) for x in ds]), adj) if ds is not None else None


def _idx(F, k, dt):
    s = _serie(F, k)
    if s is None:
        return None
    i = int(np.searchsorted(s[0], np.datetime64(dt), side="right")) - 1
    return i if i >= 0 else None


def _trend(F, k, dt):
    key = (id(F), k, dt)
    if key not in _tc:
        i = _idx(F, k, dt); s = _serie(F, k)
        if i is None or i < 252 or s is None:
            _tc[key] = None
        else:
            v = s[1][i - 252:i + 1]
            if np.any(v <= 0):
                _tc[key] = None
            else:
                y = np.log(v); x = np.arange(len(y), dtype=float)
                yh = np.polyval(np.polyfit(x, y, 1), x)
                st_ = float(np.sum((y - y.mean()) ** 2))
                _tc[key] = 1 - float(np.sum((y - yh) ** 2)) / st_ if st_ > 0 else None
    return _tc[key]


def _dagsret(F, k, dt):
    key = (id(F), k, dt)
    if key not in _rc:
        i = _idx(F, k, dt); s = _serie(F, k)
        if i is None or i < 252 or s is None:
            _rc[key] = None
        else:
            v = s[1][i - 252:i + 1]
            _rc[key] = (np.diff(v) / v[:-1]) if np.all(v > 0) else None
    return _rc[key]


BAS = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}


def rapport(namn, kw26, kw19=None):
    a26 = sim(S.F26, **kw26)
    a19 = sim(S.F19, **(kw19 or kw26))
    d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
    rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
    logga(f"  {namn:<32}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
          f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
    return {"f2020_2026": {**S.stat(a26), **d26}, "f2014_2019": {**S.stat(a19), **d19},
            "bada_positiva": bool(rep)}


def main():
    logga(f"\n# Kö mot STACK_H del 2c, snäv utgång med verklig karens — {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n")
    logga(f"  {'variant':<32}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    ut = {"version": "KO_MOT_STACK_H_DEL2B_BINDANDE_TROSKLAR",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "C": {}}
    T = ut["C"]
    for ex in (5, 8, 12, 20):
        for ka in (1, 3):
            T[f"snav_{ex}_karens{ka}"] = rapport(f"snäv utgång >{ex}, karens {ka}",
                                                 dict(stampel_exit=ex, karens=ka))
    (UT / "resultat_del2c.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in T.values() if v["bada_positiva"])
    logga(f"\nPositiva i BÅDA fönstren: {n} av {len(T)}")
    logga(f"Skrivet: {UT/'resultat_del2c.json'}")


if __name__ == "__main__":
    main()
