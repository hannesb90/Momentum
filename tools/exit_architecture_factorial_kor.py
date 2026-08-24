"""EXIT_ARCHITECTURE_FACTORIAL — daglig motor med intraperiod-drawdownexit.

Forregistrering: research_k/exit_architecture_factorial/EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen troskelsokning. Reentry roas inte.

Kor: python tools/exit_architecture_factorial_kor.py --fonster SELECTION
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/exit_architecture_factorial"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
if sha(V2 / "tools/h0_v3_kor.py") != "f844eaea4492d53976c3565b5a194c40f1c0c0d1324aad743059f2e85a1715af":
    sys.exit("AVBRYTER: H0 V3 ar inte den frysta versionen.")

_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
COST, NTOP, PPY = R.COST, 20, R.PPY
DD_NIVAER = [-0.10, -0.20, -0.30, -0.40]
FONSTER = {"SELECTION": "W1_2014_2019", "VALIDATION": "W2_2020_2026"}


def bygg_order(wn, rk, preds):
    """S1/S2/S3 exakt som i cross_model_arch_b."""
    def s1(day): return [r["kod"] for r in rk[day]]
    def sml(m):
        def f(day):
            p = [r["kod"] for r in rk[day]][:30]; s = preds[m].get(day, {})
            return sorted(p, key=lambda k: (-s.get(k, -1e18), k))
        return f
    return {"S1": s1, "S2": sml("EXTRATREES"), "S3": sml("XGBOOST")}


def sleeve(ser, k0, d_start, d_end, thr, policy, kand_fn, agda, idxf):
    """En viktandels utveckling under en panel. Returnerar (multipel, exits, kostnadsenheter, dagar_till_exit, repl_namn, kassa_dagar)."""
    ds0, v0 = ser[k0]
    i = int(np.searchsorted(ds0, np.datetime64(d_start), side="right"))          # T+1-ingang
    j = int(np.searchsorted(ds0, np.datetime64(d_end), side="right")) - 1
    if i > j or i >= len(v0) or v0[i] <= 0:
        return 1.0, 0, 0.0, None, None, 0
    if thr is None:
        return float(v0[j] / v0[i]), 0, 0.0, None, None, 0

    mult = 1.0; cur = k0; ci, cj = i, j; peak = float(v0[i])
    exits = 0; kost = 0.0; forsta_dag = None; repl = None; kassadagar = 0
    used = set(agda)
    while True:
        ds, v = ser[cur]
        trig = None
        for t in range(ci, cj + 1):
            px = float(v[t])
            if px > peak: peak = px
            if px / peak - 1.0 <= thr:
                trig = t; break
        if trig is None or trig >= cj:                       # ingen trigger, eller for sent att exekvera
            mult *= float(v[cj] / v[ci]); break
        te = trig + 1                                        # T+1-exekvering
        mult *= float(v[te] / v[ci]); exits += 1; kost += COST
        if forsta_dag is None: forsta_dag = te - i
        if policy == "CASH":
            kassadagar += cj - te; break
        d_ex = ds[te]
        ny = kand_fn(str(np.datetime64(d_ex, "D")), used | {cur})
        if ny is None:
            kassadagar += cj - te; break
        dsr, vr = ser[ny]
        ri = int(np.searchsorted(dsr, d_ex, side="right")) - 1
        rj = int(np.searchsorted(dsr, np.datetime64(d_end), side="right")) - 1
        if ri < 0 or rj <= ri or vr[ri] <= 0:
            kassadagar += cj - te; break
        used.add(ny); repl = ny; cur = ny; ci, cj = ri, rj; peak = float(vr[ri])
    return mult, exits, kost, forsta_dag, repl, kassadagar


def kor_arm(W, order_fn, fe, thr, policy, ser, rk, panel_lista):
    P = W["paneler"]; vals = []; turns = []
    prior = []; diag = {"exits": 0, "repl": 0, "ingen_kandidat": 0, "dagar": [], "kassadagar": 0, "n_sleeves": 0,
                        "exit_handelser": set()}
    peaks_start = {}
    for i, day in enumerate(P):
        if i + 1 >= len(P): break
        if i % 2 == 0 or not prior:
            cur = order_fn(day)[:NTOP]
            turn = len(set(cur) - set(prior)) / max(1, NTOP) if prior else 0.0
            prior = cur; kop_day = day
        else:
            turn = 0.0
        if i < fe:
            continue
        d_start, d_end = day, P[i + 1]

        def kand_fn(datum, uteslut):
            pd_ = max([p for p in panel_lista if p <= datum], default=None)
            if pd_ is None: return None
            for k in order_fn(pd_):
                if k not in uteslut and k in ser: return k
            return None

        rs = []; kost_extra = 0.0
        for k in prior:
            if k not in ser: rs.append(0.0); continue
            m, ex, ko, dg, rp, kd = sleeve(ser, k, d_start, d_end, thr, policy, kand_fn, set(prior), None)
            rs.append(m - 1.0); kost_extra += ko / max(1, NTOP)
            if ex:
                diag["exits"] += ex; diag["exit_handelser"].add((str(d_start), k))
                if rp: diag["repl"] += 1
                else: diag["ingen_kandidat"] += 1
                if dg is not None: diag["dagar"].append(dg)
            diag["kassadagar"] += kd; diag["n_sleeves"] += 1
        vals.append(float(np.mean(rs)) - COST * turn - kost_extra)
        turns.append(turn + kost_extra / max(COST, 1e-12) / max(1, NTOP))
    return np.asarray(vals), np.asarray(turns), diag


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fonster", required=True, choices=list(FONSTER))
    a = ap.parse_args(); wn = FONSTER[a.fonster]
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    W = R.load_window(wn); rk, ser, P = W["rankings"], W["serie"], W["paneler"]
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = sorted(preds["EXTRATREES"]); fe = P.index(dagar[0])
    ordrar = bygg_order(wn, rk, preds)
    panel_lista = [p for p in P]

    ut = {"version": "EXIT_ARCHITECTURE_FACTORIAL_V1", "fonster_roll": a.fonster, "fonster": wn,
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json"),
          "n_eval_paneler": len(dagar), "reproduktionsgrind": {}, "armar": {}}

    # ---------- REPRODUKTIONSGRIND
    gate_ok = True
    for s, of in ordrar.items():
        fro, _, _ = R.simulate(W, lambda d, i, f=of: f(d), fe, top_n=NTOP)
        ny, _, _ = kor_arm(W, of, fe, None, "CASH", ser, rk, panel_lista)
        n = min(len(fro), len(ny))
        c_f = float(np.prod(1 + fro[:n]) ** (PPY / n) - 1); c_n = float(np.prod(1 + ny[:n]) ** (PPY / n) - 1)
        d = abs(c_f - c_n)
        ut["reproduktionsgrind"][s] = {"fryst_cagr": round(c_f, 8), "ny_motor_cagr": round(c_n, 8),
                                       "abs_diff": float(f"{d:.3e}"), "n_paneler": n,
                                       "PASS": bool(d < 1e-6)}
        if d >= 1e-6: gate_ok = False
        print(f"GRIND {s}: fryst {c_f:.8f} ny {c_n:.8f} diff {d:.3e} {'PASS' if d < 1e-6 else 'FAIL'}", flush=True)
    ut["GRIND_TOTAL"] = "PASS" if gate_ok else "FAIL"
    if not gate_ok:
        (UT / f"results_{a.fonster}.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
        sys.exit("AVBRYTER: reproduktionsgrinden faller. Inga DD-armar kors.")

    # ---------- ARMAR
    for s, of in ordrar.items():
        base, tb, _ = kor_arm(W, of, fe, None, "CASH", ser, rk, panel_lista)
        ut["armar"][s] = {"BASE": {**R.stat(base), "mean_turnover": round(float(np.mean(tb)), 4)}}
        np.save(UT / f"nets_{a.fonster}_{s}_BASE.npy", base)
        for thr in DD_NIVAER:
            for pol in ("CASH", "NEXT_RANKED"):
                nets, tu, dg = kor_arm(W, of, fe, thr, pol, ser, rk, panel_lista)
                np.save(UT / f"nets_{a.fonster}_{s}_DD{abs(int(thr*100))}_{pol}.npy", nets)
                st = R.stat(nets); ex = R.boot_ci(nets, base)
                cal = round(st["cagr"] / abs(st["maxdd"]), 4) if st["maxdd"] else None
                ut["armar"][s][f"DD{abs(int(thr*100))}_{pol}"] = {
                    **st, "calmar": cal, "excess_cagr_pp": round(100 * (st["cagr"] - R.stat(base)["cagr"]), 3),
                    "ki_lo_pp": round(100 * ex["ki_lo"], 3), "ki_hi_pp": round(100 * ex["ki_hi"], 3),
                    "andel_boot_pos": ex["andel_bootstrap_positiva"],
                    "mean_turnover": round(float(np.mean(tu)), 4),
                    "n_exits": dg["exits"], "n_replacements": dg["repl"],
                    "n_ingen_kandidat": dg["ingen_kandidat"],
                    "medel_dagar_till_exit": round(float(np.mean(dg["dagar"])), 2) if dg["dagar"] else None,
                    "kassaandel": round(dg["kassadagar"] / max(1, dg["n_sleeves"] * 28), 5),
                    "exit_handelser": sorted(f"{d}|{k}" for d, k in dg["exit_handelser"])}
                print(f"  {s} DD{abs(int(thr*100))} {pol}: excess {100*(st['cagr']-R.stat(base)['cagr']):+.2f} pp, {dg['exits']} exits", flush=True)
    (UT / f"results_{a.fonster}.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / f"results_{a.fonster}.json")


if __name__ == "__main__":
    main()
