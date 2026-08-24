"""INFORMATION_EXIT_SELECTION — M1 SMA200_TRANSITION och M2 TOPN_EXIT, kassapolicy.

Forregistrering: research_k/information_exit/INFORMATION_EXIT_MECHANISM_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen troskel. Ingen rotation. Ingen reentry.

TILLSTAND PERSISTERAR OVER HELA INNEHAVSPERIODEN (tva paneler), enligt forregistreringen:
"kapitalet ligger i kassa till nasta ORDINARIE rebalansering". Panelvikterna aterstalls vid
varje panelgrans precis som i den frysta motorn, men EXIT-tillstandet bars over gransen.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/information_exit"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "INFORMATION_EXIT_MECHANISM_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
_e = importlib.util.spec_from_file_location("E", V2 / "tools/exit_architecture_factorial_kor.py")
E = importlib.util.module_from_spec(_e); _e.loader.exec_module(E)
R, COST, NTOP, PPY = E.R, E.COST, E.NTOP, E.PPY
FONSTER = E.FONSTER


def kor_arm(W, of, fe, mek, ser, rk):
    """mek = None | 'M1' | ('M2', 20) | ('M2', 30)."""
    P = W["paneler"]; vals = []; turns = []
    prior = []; ute = {}          # namn -> True nar det lamnat innehavet i denna rebalansperiod
    over_vid_kop = {}
    diag = {"exits": 0, "dagar": [], "n_sleeves": 0, "kassapaneler": 0, "handelser": []}
    for i, day in enumerate(P):
        if i + 1 >= len(P): break
        if i % 2 == 0 or not prior:
            cur = of(day)[:NTOP]
            turn = len(set(cur) - set(prior)) / max(1, NTOP) if prior else 0.0
            prior = cur; ute = {}; over_vid_kop = {}
            if mek == "M1":                      # transition-only: flagga vid KOP
                for k in prior:
                    if k not in ser: continue
                    ds, v = ser[k]
                    a = int(np.searchsorted(ds, np.datetime64(day), side="right"))
                    over_vid_kop[k] = bool(a < len(v) and a >= 200 and v[a] >= float(np.mean(v[a - 200:a])))
        else:
            turn = 0.0
            if isinstance(mek, tuple) and mek[0] == "M2":     # rankkontroll vid MELLANPANELEN
                topn = set(of(day)[:mek[1]]) if mek[1] == 20 else set([r["kod"] for r in rk[day]][:mek[1]])
                for k in prior:
                    if k not in ute and k not in topn:
                        ute[k] = True; diag["exits"] += 1; diag["handelser"].append(f"{day}|{k}")
        if i < fe: continue
        d_start, d_end = day, P[i + 1]
        rs = []; kost = 0.0
        for k in prior:
            if k not in ser: rs.append(0.0); continue
            if ute.get(k):
                rs.append(0.0)                    # kassa hela panelen
                if ute[k] == "ny": kost += COST / NTOP; ute[k] = True
                diag["kassapaneler"] += 1; continue
            ds, v = ser[k]
            a = int(np.searchsorted(ds, np.datetime64(d_start), side="right"))
            b = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
            diag["n_sleeves"] += 1
            if a > b or a >= len(v) or v[a] <= 0: rs.append(0.0); continue
            if mek == "M1" and over_vid_kop.get(k):
                tr = None
                for t in range(a, b + 1):
                    if t < 200: continue
                    if v[t] < float(np.mean(v[t - 200:t])): tr = t; break
                if tr is not None and tr < b:
                    te = tr + 1
                    rs.append(float(v[te] / v[a]) - 1.0); kost += COST / NTOP
                    ute[k] = True; diag["exits"] += 1; diag["dagar"].append(te - a)
                    diag["handelser"].append(f"{d_start}|{k}")
                    continue
            rs.append(float(v[b] / v[a]) - 1.0)
        # M2:s exits kostar vid panelstart
        if isinstance(mek, tuple):
            nya = sum(1 for k in prior if ute.get(k) and f"{d_start}|{k}" not in ())
        vals.append(float(np.mean(rs)) - COST * turn - kost)
        turns.append(turn)
    return np.asarray(vals), np.asarray(turns), diag


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fonster", required=True, choices=list(FONSTER))
    a = ap.parse_args(); wn = FONSTER[a.fonster]
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    W = R.load_window(wn); rk, ser, P = W["rankings"], W["serie"], W["paneler"]
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = sorted(preds["EXTRATREES"]); fe = P.index(dagar[0])
    ordrar = E.bygg_order(wn, rk, preds)
    ut = {"version": "INFORMATION_EXIT_SELECTION_V1", "fonster_roll": a.fonster, "fonster": wn,
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "INFORMATION_EXIT_MECHANISM_PREREGISTRATION.json"),
          "n_eval_paneler": len(dagar), "reproduktionsgrind": {}, "armar": {}}

    ok = True
    for s, of in ordrar.items():
        fro, _, _ = R.simulate(W, lambda d, i, f=of: f(d), fe, top_n=NTOP)
        ny, _, _ = kor_arm(W, of, fe, None, ser, rk)
        n = min(len(fro), len(ny))
        cf = float(np.prod(1 + fro[:n]) ** (PPY / n) - 1); cn = float(np.prod(1 + ny[:n]) ** (PPY / n) - 1)
        d = abs(cf - cn); ok &= d < 1e-6
        ut["reproduktionsgrind"][s] = {"fryst": round(cf, 8), "ny": round(cn, 8), "diff": float(f"{d:.3e}"), "PASS": bool(d < 1e-6)}
        print(f"GRIND {s}: {cf:.8f} mot {cn:.8f} diff {d:.3e} {'PASS' if d<1e-6 else 'FAIL'}", flush=True)
    ut["GRIND_TOTAL"] = "PASS" if ok else "FAIL"
    if not ok:
        (UT / f"results_{a.fonster}.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
        sys.exit("AVBRYTER: reproduktionsgrinden faller.")

    MEK = [("M1_SMA200_TRANSITION", "M1"), ("M2_TOPN_EXIT_20", ("M2", 20)), ("M2_TOPN_EXIT_30", ("M2", 30))]
    for s, of in ordrar.items():
        base, tb, _ = kor_arm(W, of, fe, None, ser, rk)
        np.save(UT / f"nets_{a.fonster}_{s}_BASE.npy", base)
        bs = R.stat(base)
        ut["armar"][s] = {"BASE": {**bs, "mean_turnover": round(float(np.mean(tb)), 4)}}
        for nm, mek in MEK:
            nets, tu, dg = kor_arm(W, of, fe, mek, ser, rk)
            np.save(UT / f"nets_{a.fonster}_{s}_{nm}.npy", nets)
            st = R.stat(nets); ex = R.boot_ci(nets, base)
            c40 = R.cost_sens(W, lambda d, i, f=of: f(d), fe, 0.004, top_n=NTOP)
            ut["armar"][s][nm] = {**st,
                "calmar": round(st["cagr"] / abs(st["maxdd"]), 4) if st["maxdd"] else None,
                "excess_cagr_pp": round(100 * (st["cagr"] - bs["cagr"]), 3),
                "ki_lo_pp": round(100 * ex["ki_lo"], 3), "ki_hi_pp": round(100 * ex["ki_hi"], 3),
                "andel_boot_pos": ex["andel_bootstrap_positiva"],
                "delta_sharpe": round(st["sharpe"] - bs["sharpe"], 3),
                "delta_maxdd_pp": round(100 * (st["maxdd"] - bs["maxdd"]), 3),
                "n_exits": dg["exits"], "kassapaneler": dg["kassapaneler"],
                "medel_dagar_till_exit": round(float(np.mean(dg["dagar"])), 2) if dg["dagar"] else None,
                "handelser": dg["handelser"]}
            print(f"  {s} {nm}: excess {100*(st['cagr']-bs['cagr']):+.2f} pp, KI[{100*ex['ki_lo']:+.2f},{100*ex['ki_hi']:+.2f}], {dg['exits']} exits", flush=True)
    (UT / f"results_{a.fonster}.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / f"results_{a.fonster}.json")


if __name__ == "__main__":
    main()
