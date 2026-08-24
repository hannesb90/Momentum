"""FULL_HISTORY_SIZE_ICB_POWER_REASSESSMENT — poolad analys over 98 beslutspaneler.

Forregistrering: research_k/full_history_power/FULL_HISTORY_SIZE_ICB_POWER_REASSESSMENT_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen routing. Ingen ny cutpoint. Ingen fonstersokning.
Aterbrukar build() ur model_heterogeneity_controls_kor.py oforandrat.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/full_history_power"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "FULL_HISTORY_SIZE_ICB_POWER_REASSESSMENT_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")

_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F)
dm, ols_cl, wald, build, CWMAP = F.dm, F.ols_cl, F.wald, F.build, F.CWMAP
PPY = 13.0
Z975, Z80, Z90 = 1.959964, 0.841621, 1.281552


def mde_pp(se_b, sd_d, power_z):
    return 100.0 * (Z975 + power_z) * se_b * sd_d * PPY


def size_test(rows, key, ctrl):
    pid = np.array([r["p"] for r in rows]); y = dm(np.array([r["ret"] for r in rows]), pid)
    d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
    s = np.array([r["s"] for r in rows]); sd_d = float(np.std(d_))
    C = [dm(d_, pid), dm(s, pid), dm(d_ * s, pid)]; i3 = 2
    if ctrl:
        for c in ("vol", "liq", "spr"):
            v = np.array([r[c] for r in rows]); C += [dm(v, pid), dm(d_ * v, pid)]
    X = np.column_stack(C)
    b, V = ols_cl(y, X, pid)
    if b is None: return {"status": "SINGULAR"}
    se = math.sqrt(V[i3, i3]); t = float(b[i3] / se)
    G = len(np.unique(pid))
    # naiv SE som diagnostik: homoskedastisk, ignorerar klustring
    e = y - X @ b; s2 = float(e @ e) / (len(y) - X.shape[1])
    se_naiv = math.sqrt(s2 * np.linalg.inv(X.T @ X)[i3, i3])
    return {"status": "OK", "b": round(float(b[i3]), 6), "se_klustrad": round(se, 6),
            "se_naiv_DIAGNOSTIK": round(se_naiv, 6),
            "se_kvot_klustrad_over_naiv": round(se / se_naiv, 2),
            "t": round(t, 3), "p": round(2 * (1 - stats.t.cdf(abs(t), G - 1)), 5),
            "n_obs": len(rows), "n_paneler": G, "sd_d": round(sd_d, 4),
            "std_effekt_pp_per_ar": round(100 * float(b[i3]) * sd_d * PPY, 3),
            "MDE80_pp_per_ar": round(mde_pp(se, sd_d, Z80), 3),
            "MDE90_pp_per_ar": round(mde_pp(se, sd_d, Z90), 3)}


def icb_test(rows, key, grp, ctrl):
    n = len(rows); pid = np.array([r["p"] for r in rows]); y = dm(np.array([r["ret"] for r in rows]), pid)
    d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
    s = np.array([r["s"] for r in rows]); sd_d = float(np.std(d_))
    C = [dm(np.array([d_[i] if rows[i]["cw"] == g else 0. for i in range(n)]), pid) for g in grp]
    idxg = list(range(len(grp)))
    for g in grp[1:]:
        C.append(dm(np.array([1. if rows[i]["cw"] == g else 0. for i in range(n)]), pid))
    C += [dm(s, pid), dm(d_ * s, pid)]
    if ctrl:
        for c in ("vol", "liq", "spr"):
            v = np.array([r[c] for r in rows]); C += [dm(v, pid), dm(d_ * v, pid)]
    b, V = ols_cl(y, np.column_stack(C), pid)
    Wv, pv, df = wald(b, V, idxg)
    if b is None: return {"status": "SINGULAR"}
    per = {g: round(100 * float(b[idxg[i]]) * sd_d * PPY, 3) for i, g in enumerate(grp)}
    # omnibus-MDE: icke-central chi2 langs den observerade kontrastriktningen
    Rm = np.zeros((len(idxg) - 1, len(b)))
    for i, j in enumerate(idxg[1:]): Rm[i, j] = 1.; Rm[i, idxg[0]] = -1.
    RVR = Rm @ V @ Rm.T; Rb = Rm @ b
    nrm = float(np.linalg.norm(Rb))
    mde = {}
    if nrm > 0:
        u = Rb / nrm
        q = float(u @ np.linalg.solve(RVR, u))
        crit = stats.chi2.ppf(0.95, len(idxg) - 1)
        for lbl, pw in (("MDE80", 0.80), ("MDE90", 0.90)):
            lo, hi = 0.0, 500.0
            for _ in range(80):
                mid = (lo + hi) / 2
                if 1 - stats.ncx2.cdf(crit, len(idxg) - 1, mid) < pw: lo = mid
                else: hi = mid
            c = math.sqrt(((lo + hi) / 2) / q)          # kontrastlangd vid onskad power
            mde[lbl + "_mellan_grupp_sd_pp"] = round(100 * c / math.sqrt(len(grp)) * sd_d * PPY, 3)
    return {"status": "OK", "omnibus_W": Wv, "omnibus_p": round(pv, 5), "df": df,
            "n_obs": n, "n_paneler": len(np.unique(pid)), "n_grupper": len(grp),
            "std_edge_per_grupp_pp_per_ar_DESKRIPTIVT": per,
            "mellan_grupp_sd_pp": round(float(np.std(list(per.values()), ddof=1)), 3), **mde}


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R

    block, offs = {}, 0
    alla = []
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        rs = build(wn, G, R, H, WK)
        for r in rs: r["cw"] = CWMAP[r["icb"]]
        pmax = max(r["p"] for r in rs)
        for r in rs: r["p"] = r["p"] + offs; r["block"] = wn
        block[wn] = {"n_obs": len(rs), "n_paneler": len(set(r["p"] for r in rs)),
                     "panelindex": [min(r["p"] for r in rs), max(r["p"] for r in rs)]}
        offs += pmax + 1
        alla += rs
    paneler = sorted({r["p"] for r in alla})
    ny = {p: i for i, p in enumerate(paneler)}          # kompaktera till 0..97
    for r in alla: r["p"] = ny[r["p"]]
    NP = len(paneler)
    grp = sorted({r["cw"] for r in alla})

    ut = {"version": "FULL_HISTORY_SIZE_ICB_POWER_REASSESSMENT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "FULL_HISTORY_SIZE_ICB_POWER_REASSESSMENT_PREREGISTRATION.json"),
          "ingen_traning": True, "prediktionsklass": "EXISTING_FROZEN_OOS",
          "n_poolade_paneler": NP, "n_obs": len(alla), "block": block, "icb_grupper": grp,
          "POOLAD": {}, "PER_BLOCK": {}, "STABILITET_T1T2T3": {}}

    for popn in ("FULL", "POOL"):
        rows = alla if popn == "FULL" else [r for r in alla if r["inpool"] == 1.0]
        o = {"n_obs": len(rows), "n_paneler": len(set(r["p"] for r in rows)), "size": {}, "icb": {}}
        g2 = sorted({r["cw"] for r in rows})
        for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
            o["size"][mod] = {lbl: size_test(rows, key, c) for lbl, c in (("RAW", False), ("EFTER_KONTROLL", True))}
            o["icb"][mod] = {lbl: icb_test(rows, key, g2, c) for lbl, c in (("RAW", False), ("EFTER_KONTROLL", True))}
        ut["POOLAD"][popn] = o

    # jamforelse: samma test separat per originalblock
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        rows = [r for r in alla if r["block"] == wn]
        g2 = sorted({r["cw"] for r in rows})
        ut["PER_BLOCK"][wn] = {"n_obs": len(rows), "n_paneler": len(set(r["p"] for r in rows)),
            "size": {m: size_test(rows, k, False) for m, k in (("ET", "pET"), ("XGB", "pXGB"))},
            "icb": {m: icb_test(rows, k, g2, False) for m, k in (("ET", "pET"), ("XGB", "pXGB"))}}

    # DEL 9: tre mekaniska kronologiska block pa panelindex
    grans = [(0, 32), (33, 65), (66, 97)]
    for i, (a, b_) in enumerate(grans, 1):
        rows = [r for r in alla if a <= r["p"] <= b_]
        g2 = sorted({r["cw"] for r in rows})
        dat = sorted({(r["p"], r["block"]) for r in rows})
        ut["STABILITET_T1T2T3"][f"T{i}"] = {
            "panelindex": [a, b_], "n_paneler": len(set(r["p"] for r in rows)), "n_obs": len(rows),
            "kallblock": sorted({r["block"] for r in rows}),
            "size": {m: size_test(rows, k, False) for m, k in (("ET", "pET"), ("XGB", "pXGB"))},
            "icb": {m: icb_test(rows, k, g2, False) for m, k in (("ET", "pET"), ("XGB", "pXGB"))}}
        print(f"T{i} klart: {len(rows)} obs", flush=True)

    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
