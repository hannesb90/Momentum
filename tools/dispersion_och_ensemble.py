"""TVÅ NYA ANGREPPSVÄGAR

A. SPRIDNINGEN SOM KONVIKTIONSMÅTT
   Rankningen är platt i genomsnitt (0,1055 percentilenheter mellan rank 1 och
   30). Men spridningen varierar panel för panel. Hypotes: när toppen är tätt
   hopklumpad är urvalet nästan godtyckligt och signalen svag; när den är
   utspridd är den informativ. Testas som (1) prediktor för topp-30:s
   överavkastning och (2) som regel: variera exponering eller N med spridningen.

B. ENSEMBLE AV DE FRYSTA MODELLERNA
   De sex är korrelerade men inte identiska. Jämnviktad blandning är oprövad,
   och variansreduktion genom ensemble är den mest robusta effekten i statistik.
   Testas som ren blandning av nettoserierna samt som blandning av urvalen.

Kör: /opt/momentum/venv/bin/python tools/dispersion_och_ensemble.py
"""
from __future__ import annotations
import json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/dispersion_och_ensemble_results.json"
COST = 0.002


def spridning(F, dt):
    sc = [r["score"] for r in F["rankings"][dt]]
    if len(sc) < 60:
        return None
    return float(sc[0] - sc[29])


def del_a1(F, namn):
    """Predicerar spridningen topp-30:s överavkastning mot universumet?"""
    dts, ret = F["eval_dates"], F["returns_map"]
    sp, ex = [], []
    for pi, dt in enumerate(dts[:-1]):
        d = spridning(F, dt)
        if d is None:
            continue
        t30 = np.mean([ret.get((r["kod"], dt), 0.0) for r in F["rankings"][dt][:30]])
        alla = np.mean([ret.get((r["kod"], dt), 0.0) for r in F["rankings"][dt]])
        sp.append(d); ex.append(t30 - alla)
    a, b = np.array(sp), np.array(ex)
    r = float(np.corrcoef(a, b)[0, 1])
    t = float(r * math.sqrt((len(a) - 2) / max(1e-12, 1 - r ** 2)))
    q = np.quantile(a, [0.33, 0.67])
    grupp = {"låg spridning": b[a <= q[0]], "mellan": b[(a > q[0]) & (a <= q[1])],
             "hög spridning": b[a > q[1]]}
    print(f"\n  {namn}: spridning median {np.median(a):.4f}, "
          f"korr mot topp-30:s överavkastning {r:+.3f} (t {t:+.2f})")
    for g, v in grupp.items():
        print(f"     {g:<16}n={len(v):>3}  överavkastning {np.mean(v):+.2%}")
    return {"korrelation": round(r, 4), "t": round(t, 2),
            "median_spridning": round(float(np.median(a)), 4),
            "per_tercil": {g: round(float(np.mean(v)), 4) for g, v in grupp.items()}}


def sim_disp(F, N=30, laget=None, hyst_rank=35):
    """laget: None | 'exponering' | 'antal' — hur spridningen styr."""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    alla_sp = [spridning(F, dt) for dt in dts]
    giltiga = [x for x in alla_sp if x is not None]
    med = float(np.median(giltiga)) if giltiga else 0.1
    prev, prevw, nets = [], {}, []
    for pi, dt in enumerate(dts):
        d = alla_sp[pi] or med
        kvot = d / med
        Nk = N
        if laget == "antal":
            Nk = int(np.clip(round(N * min(1.4, max(0.6, kvot))), 15, 45))
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:Nk]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < Nk:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: Nk - len(sel0)]
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / N
        if laget == "exponering":
            ts = ts * float(np.clip(kvot, 0.6, 1.3))
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
    ut = {"version": "DISPERSION_OCH_ENSEMBLE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    print("A1. PREDICERAR SPRIDNINGEN URVALETS VÄRDE?")
    ut["A1"] = {"2020_2026": del_a1(S.F26, "2020-2026"), "2014_2019": del_a1(S.F19, "2014-2019")}

    print("\nA2. SPRIDNINGEN SOM REGEL")
    print(f"  {'variant':<28}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}   repl")
    ut["A2"] = {}
    for lag, namn in (("exponering", "exponering styrs av spridning"),
                      ("antal", "antal innehav styrs av spridning")):
        a26, a19 = sim_disp(S.F26, laget=lag), sim_disp(S.F19, laget=lag)
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["A2"][namn] = {"f2020_2026": {**S.stat(a26), **d26},
                          "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
        print(f"  {namn:<28}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}   {'JA' if rep else '-'}")

    print("\nB. ENSEMBLE AV DE FRYSTA MODELLERNA")
    kfg = {"V_A": dict(use_erc=False, use_fr=False, use_hysteresis=False, use_ntz=False),
           "V_B": dict(use_erc=False, use_fr=False, use_hysteresis=False, use_ntz=False, use_tv=True),
           "ERC": dict(use_fr=False, use_hysteresis=False, use_ntz=False),
           "FR": dict(use_erc=False, use_hysteresis=False, use_ntz=False),
           "PRUNED_D": dict(use_hysteresis=False, use_ntz=False),
           "STACK_H": dict()}
    ser = {}
    for w_, F in (("26", S.F26), ("19", S.F19)):
        ser[w_] = {n: S.kor(**F, **kw)[0] for n, kw in kfg.items()}
    ut["B"] = {}
    print(f"  {'blandning':<28}{'CAGR26':>8}{'Sharpe':>8}{'CAGR19':>9}{'Sharpe':>8}")
    for namn, delar in (("alla sex", list(kfg)), ("de fyra utan V_B", ["V_A", "ERC", "FR", "PRUNED_D"]),
                        ("ERC + FR + PRUNED + H", ["ERC", "FR", "PRUNED_D", "STACK_H"])):
        e26 = np.mean([ser["26"][d] for d in delar], axis=0)
        e19 = np.mean([ser["19"][d] for d in delar], axis=0)
        d26, d19 = S.boot(e26, BAS["26"]), S.boot(e19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["B"][namn] = {"f2020_2026": {**S.stat(e26), **d26},
                         "f2014_2019": {**S.stat(e19), **d19}, "bada_positiva": bool(rep)}
        print(f"  {namn:<28}{S.stat(e26)['cagr']:>8.2%}{S.stat(e26)['sharpe']:>8.3f}"
              f"{S.stat(e19)['cagr']:>9.2%}{S.stat(e19)['sharpe']:>8.3f}"
              f"   Δ {d26['delta_cagr']:+.2%}/{d19['delta_cagr']:+.2%}  {'JA' if rep else '-'}")
    print(f"  {'STACK_H ensam':<28}{S.stat(BAS['26'])['cagr']:>8.2%}{S.stat(BAS['26'])['sharpe']:>8.3f}"
          f"{S.stat(BAS['19'])['cagr']:>9.2%}{S.stat(BAS['19'])['sharpe']:>8.3f}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
