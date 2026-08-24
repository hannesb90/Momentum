"""Faktoriell analys av H0_V3_PORTFOLIO_LAYER_FACTORIAL. Ingen ny simulering.

Huvudeffekter enligt Yates: medelvardet av en faktors parvisa skillnad over
SAMTLIGA kombinationer av ovriga faktorer. Explicit icke-sekventiellt.

  K4a  ren namnfilter-kanal      = E2 - E0  (samma exponering, olika namn)
  K4b  kassakanal                = E1 - E2  (samma namn, olika exponering)
  K4   SMA som den faktiskt kors = E1 - E0  = K4a + K4b + interaktion

Osakerhet: parvis block bootstrap, block 13, 2000 dragningar, SEED 20260815.
"""
from __future__ import annotations
import json
from itertools import product
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
UT = V2 / "research_k/h0_v3_portfolio_factorial"
PPY, BLOCK, DRAWS, SEED = 13.0, 13, 2000, 20260815
EXP = ("E0", "E1", "E2"); K5 = ("likavikt", "invvol1.5"); K6 = ("noFR", "FR")
K7 = ("inget", "legacy", "waterfill")
key = lambda e, v, f, t: f"{e}|{v}|{f}|{t}"


def boot_idx(n, rng):
    out = []
    while len(out) < n:
        s = rng.integers(0, max(1, n - BLOCK + 1))
        out.extend(range(s, min(s + BLOCK, n)))
    return np.array(out[:n])


def cagr_mat(M, idx):
    return np.prod(1 + M[:, idx], axis=1) ** (PPY / M.shape[1]) - 1


def analys(wn):
    ser = json.loads((UT / f"nettoserier_{wn}.json").read_text())
    names = list(ser); M = np.array([ser[k] for k in names], float)
    pos = {k: i for i, k in enumerate(names)}
    n = M.shape[1]
    rng = np.random.default_rng(SEED)
    idxs = [boot_idx(n, rng) for _ in range(DRAWS)]
    base = cagr_mat(M, np.arange(n))
    B = np.array([cagr_mat(M, ix) for ix in idxs])          # (DRAWS, n_armar)

    def kontrast(pairs):
        """pairs: lista av (hog_key, lag_key). Returnerar medel-delta + KI."""
        hi = [pos[a] for a, _ in pairs]; lo = [pos[b] for _, b in pairs]
        d = float(np.mean(base[hi] - base[lo]))
        db = np.mean(B[:, hi] - B[:, lo], axis=1)
        return {"effekt_pp": round(100 * d, 3),
                "ki_lo_pp": round(100 * float(np.percentile(db, 2.5)), 3),
                "ki_hi_pp": round(100 * float(np.percentile(db, 97.5)), 3),
                "andel_positiva": round(float(np.mean(db > 0)), 4),
                "n_par": len(pairs)}

    P = lambda t7: [t for t in K7 if t in t7]
    prim = ("inget", "legacy")                                # primar faktoriell
    hu = {}
    hu["K4a_namnfilter_E2_minus_E0"] = kontrast(
        [(key("E2", v, f, t), key("E0", v, f, t)) for v, f, t in product(K5, K6, prim)])
    hu["K4b_kassakanal_E1_minus_E2"] = kontrast(
        [(key("E1", v, f, t), key("E2", v, f, t)) for v, f, t in product(K5, K6, prim)])
    hu["K4_SMA_som_den_kors_E1_minus_E0"] = kontrast(
        [(key("E1", v, f, t), key("E0", v, f, t)) for v, f, t in product(K5, K6, prim)])
    hu["K5_invvol_minus_likavikt"] = kontrast(
        [(key(e, "invvol1.5", f, t), key(e, "likavikt", f, t)) for e, f, t in product(EXP, K6, prim)])
    hu["K6_FR_minus_ingen"] = kontrast(
        [(key(e, v, "FR", t), key(e, v, "noFR", t)) for e, v in product(EXP, K5) for t in prim])
    hu["K7_legacy_minus_inget_tak"] = kontrast(
        [(key(e, v, f, "legacy"), key(e, v, f, "inget")) for e, v, f in product(EXP, K5, K6)])
    hu["K7_waterfill_minus_inget_tak"] = kontrast(
        [(key(e, v, f, "waterfill"), key(e, v, f, "inget")) for e, v, f in product(EXP, K5, K6)])
    hu["K7_legacy_minus_waterfill_SPEC_MOT_IMPL"] = kontrast(
        [(key(e, v, f, "legacy"), key(e, v, f, "waterfill")) for e, v, f in product(EXP, K5, K6)])

    # ---- tvavagsinteraktioner (primar design)
    inter = {}
    def eff_K5(e, f, t): return base[pos[key(e, "invvol1.5", f, t)]] - base[pos[key(e, "likavikt", f, t)]]
    def eff_K6(e, v, t): return base[pos[key(e, v, "FR", t)]] - base[pos[key(e, v, "noFR", t)]]
    def eff_K7(e, v, f): return base[pos[key(e, v, f, "legacy")]] - base[pos[key(e, v, f, "inget")]]
    inter["K5xK6"] = round(100 * float(
        np.mean([eff_K5(e, "FR", t) - eff_K5(e, "noFR", t) for e, t in product(EXP, prim)])), 3)
    inter["K5xK7"] = round(100 * float(
        np.mean([eff_K5(e, f, "legacy") - eff_K5(e, f, "inget") for e, f in product(EXP, K6)])), 3)
    inter["K6xK7"] = round(100 * float(
        np.mean([eff_K6(e, v, "legacy") - eff_K6(e, v, "inget") for e, v in product(EXP, K5)])), 3)
    for a, b in (("E1", "E0"), ("E2", "E0"), ("E1", "E2")):
        nm = {"E1E0": "K4", "E2E0": "K4a", "E1E2": "K4b"}[a + b]
        inter[f"{nm}xK5"] = round(100 * float(np.mean(
            [(base[pos[key(a, "invvol1.5", f, t)]] - base[pos[key(a, "likavikt", f, t)]]) -
             (base[pos[key(b, "invvol1.5", f, t)]] - base[pos[key(b, "likavikt", f, t)]])
             for f, t in product(K6, prim)])), 3)
        inter[f"{nm}xK7"] = round(100 * float(np.mean(
            [(base[pos[key(a, v, f, "legacy")]] - base[pos[key(a, v, f, "inget")]]) -
             (base[pos[key(b, v, f, "legacy")]] - base[pos[key(b, v, f, "inget")]])
             for v, f in product(K5, K6)])), 3)
    inter["K5xK6xK7"] = round(100 * float(np.mean(
        [(eff_K5(e, "FR", "legacy") - eff_K5(e, "noFR", "legacy")) -
         (eff_K5(e, "FR", "inget") - eff_K5(e, "noFR", "inget")) for e in EXP])), 3)

    # ---- additivitetstest: summa huvudeffekter mot faktisk total
    tom = base[pos[key("E0", "likavikt", "noFR", "inget")]]
    full = base[pos[key("E1", "invvol1.5", "FR", "legacy")]]
    summa = (hu["K4_SMA_som_den_kors_E1_minus_E0"]["effekt_pp"] +
             hu["K5_invvol_minus_likavikt"]["effekt_pp"] +
             hu["K6_FR_minus_ingen"]["effekt_pp"] +
             hu["K7_legacy_minus_inget_tak"]["effekt_pp"])
    add = {"tom_arm_cagr": round(100 * float(tom), 3), "full_arm_H0V3_cagr": round(100 * float(full), 3),
           "faktisk_total_pp": round(100 * float(full - tom), 3),
           "summa_huvudeffekter_pp": round(summa, 3),
           "TOTAL_INTERAKTION_pp": round(100 * float(full - tom) - summa, 3)}
    return {"huvudeffekter": hu, "interaktioner": inter, "additivitet": add,
            "n_paneler": n, "n_armar": len(names)}


if __name__ == "__main__":
    res = json.loads((UT / "results.json").read_text())
    out = {"version": "H0_V3_PORTFOLIO_FACTORIAL_ANALYS_V1",
           "prereg_sha256": res["prereg_sha256"], "fonster": {}}
    for wn in res["fonster"]:
        out["fonster"][wn] = analys(wn)
    (UT / "factorial_analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "factorial_analysis.json")
