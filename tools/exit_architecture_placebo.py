"""Matchad slumpexit-placebo enligt EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION DEL PLACEBO.

Exakt lika manga forsaljningar som den riktiga armen, vid slumpmassigt valda handelsdagar
bland de dagar namnet halls, samma replacement-policy och samma kostnader — men utan att
drawdown har med saken att gora. 1000 dragningar, SEED 20260815.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/exit_architecture_factorial"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
_e = importlib.util.spec_from_file_location("E", V2 / "tools/exit_architecture_factorial_kor.py")
E = importlib.util.module_from_spec(_e); _e.loader.exec_module(E)
R, COST, NTOP, PPY = E.R, E.COST, E.NTOP, E.PPY
DRAWS = 1000


def kor_placebo(W, order_fn, fe, exits_per_panel, policy, ser, panel_lista, rng):
    P = W["paneler"]; vals = []; prior = []
    pi = 0
    for i, day in enumerate(P):
        if i + 1 >= len(P): break
        if i % 2 == 0 or not prior:
            cur = order_fn(day)[:NTOP]
            turn = len(set(cur) - set(prior)) / max(1, NTOP) if prior else 0.0
            prior = cur
        else: turn = 0.0
        if i < fe: continue
        d_start, d_end = day, P[i + 1]
        nex = exits_per_panel[pi]; pi += 1
        valda = set(rng.choice(len(prior), size=min(nex, len(prior)), replace=False)) if nex else set()
        rs = []; kost_extra = 0.0
        for si, k in enumerate(prior):
            if k not in ser: rs.append(0.0); continue
            ds, v = ser[k]
            a = int(np.searchsorted(ds, np.datetime64(d_start), side="right"))
            b = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
            if a > b or a >= len(v) or v[a] <= 0: rs.append(0.0); continue
            if si not in valda or b - a < 2:
                rs.append(float(v[b] / v[a]) - 1.0); continue
            te = int(rng.integers(a + 1, b))            # slumpmassig exitdag, T+1 redan inbakad
            m = float(v[te] / v[a]); kost_extra += COST / max(1, NTOP)
            if policy == "NEXT_RANKED":
                d_ex = ds[te]
                pd_ = max([p for p in panel_lista if p <= str(np.datetime64(d_ex, "D"))], default=None)
                ny = None
                if pd_:
                    for c in order_fn(pd_):
                        if c not in prior and c in ser: ny = c; break
                if ny:
                    dsr, vr = ser[ny]
                    ri = int(np.searchsorted(dsr, d_ex, side="right")) - 1
                    rj = int(np.searchsorted(dsr, np.datetime64(d_end), side="right")) - 1
                    if ri >= 0 and rj > ri and vr[ri] > 0: m *= float(vr[rj] / vr[ri])
            rs.append(m - 1.0)
        vals.append(float(np.mean(rs)) - COST * turn - kost_extra)
    return np.asarray(vals)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fonster", required=True, choices=list(E.FONSTER))
    ap.add_argument("--nivaer", default="20,30,40")
    a = ap.parse_args(); wn = E.FONSTER[a.fonster]
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    W = R.load_window(wn); rk, ser, P = W["rankings"], W["serie"], W["paneler"]
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = sorted(preds["EXTRATREES"]); fe = P.index(dagar[0])
    ordrar = E.bygg_order(wn, rk, preds)
    res = json.loads((UT / f"results_{a.fonster}.json").read_text())
    nivaer = [int(x) for x in a.nivaer.split(",")]
    ut = {"version": "EXIT_ARCHITECTURE_PLACEBO_V1", "fonster_roll": a.fonster, "draws": DRAWS,
          "seed": 20260815, "prereg_sha256": sha(UT / "EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json"),
          "placebo": {}}
    for s, of in ordrar.items():
        base = np.load(UT / f"nets_{a.fonster}_{s}_BASE.npy")
        bc = R.stat(base)["cagr"]
        ut["placebo"][s] = {}
        for lvl in nivaer:
            for pol in ("CASH", "NEXT_RANKED"):
                nm = f"DD{lvl}_{pol}"
                arm = res["armar"][s][nm]
                # exits per panel ur de faktiska handelserna
                hand = [h.split("|")[0] for h in arm["exit_handelser"]]
                from collections import Counter
                cnt = Counter(hand)
                paneler = [p for i, p in enumerate(P[:-1]) if i >= fe]
                epp = [cnt.get(p, 0) for p in paneler]
                rng = np.random.default_rng(20260815)
                nulls = []
                for _ in range(DRAWS):
                    n = kor_placebo(W, of, fe, epp, pol, ser, list(P), rng)
                    nulls.append(100 * (R.stat(n)["cagr"] - bc))
                nulls = np.array(nulls); obs = arm["excess_cagr_pp"]
                pct = float(np.mean(nulls < obs))
                ut["placebo"][s][nm] = {"observerad_excess_pp": obs, "n_exits": arm["n_exits"],
                    "placebo_median_pp": round(float(np.median(nulls)), 3),
                    "placebo_p5_pp": round(float(np.percentile(nulls, 5)), 3),
                    "placebo_p95_pp": round(float(np.percentile(nulls, 95)), 3),
                    "percentil": round(pct, 4), "OVER_P95": bool(obs > np.percentile(nulls, 95))}
                print(f"  {s} {nm}: obs {obs:+.2f} pp, placebo median {np.median(nulls):+.2f} p95 {np.percentile(nulls,95):+.2f}, percentil {pct:.3f} {'OVER' if obs>np.percentile(nulls,95) else 'inuti'}", flush=True)
    (UT / f"placebo_{a.fonster}.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / f"placebo_{a.fonster}.json")


if __name__ == "__main__":
    main()
