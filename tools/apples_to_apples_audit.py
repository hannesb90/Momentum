"""APPLES-TO-APPLES: H0 V3 vs H0->ET/XGB pa EXAKT samma paneler.

Resultatrekonstruktion. Ingen modell tranas, ingen parameter optimeras, inget N valjs.
Urvalen ar de forregistrerade: H0 Topp-30, H0 Topp-20, ET Topp-20, XGB Topp-20.
Portfoljlagret ar H0 V3:s exakta, med den faktoriella uppdelningens flaggor for att
separera SELECTION EFFECT fran WEIGHTING/RISK-LAYER EFFECT.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/apples_to_apples_audit"; UT.mkdir(exist_ok=True)
RACE = V2 / "research_k/global_ml_full_pit_race"
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
COST, PPY, RF = 0.002, 13.0, 0.0224
BLOCK, DRAWS, SEED = 13, 2000, 20260815
POOL, N20, N30 = 30, 20, 30


def stat(x):
    x = np.asarray(x, float); w = np.cumprod(1 + x)
    c = float(w[-1] ** (PPY / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "sharpe": round((c - RF) / v, 4) if v else 0.0,
            "vol": round(v, 4), "maxdd": round(float((w / np.maximum.accumulate(w) - 1).min()), 4),
            "total_return": round(float(w[-1] - 1), 4), "n_paneler": len(x)}


def boot(a, b):
    rng = np.random.default_rng(SEED); n = len(a); out = []
    for _ in range(DRAWS):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, max(1, n - BLOCK + 1)); idx.extend(range(s, min(s + BLOCK, n)))
        idx = np.array(idx[:n])
        out.append(np.prod(1 + a[idx]) ** (PPY / n) - np.prod(1 + b[idx]) ** (PPY / n))
    out = np.asarray(out)
    return {"delta_pp": round(100 * (np.prod(1 + a) ** (PPY / n) - np.prod(1 + b) ** (PPY / n)), 3),
            "ki_lo_pp": round(100 * float(np.percentile(out, 2.5)), 3),
            "ki_hi_pp": round(100 * float(np.percentile(out, 97.5)), 3),
            "andel_pos": round(float(np.mean(out > 0)), 3)}


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ab = json.loads((V2 / "research_k/cross_model_arch_b/results.json").read_text())["fonster"]
    ut = {"version": "APPLES_TO_APPLES_AUDIT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "ingen_traning": True, "ingen_optimering": True, "fonster": {}}
    for wn, frozen in (("W1_2014_2019", "research_k/h0_v3/h0_v3_RESULTAT.json"),
                       ("W2_2020_2026", "research_k/h0_v3_window2/result.json")):
        W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = sorted(preds["EXTRATREES"]); fe = W["paneler"].index(dagar[0])
        nev = len(dagar)

        def sma_ok(k, d):
            i = idx(k, d)
            if i is None or i < 200: return True
            _, v = ser[k]; return v[i] >= float(np.mean(v[i - 200:i]))

        def bekr(k, d):
            i = idx(k, d)
            if i is None or i < 120: return False
            _, v = ser[k]; ma = float(np.mean(v[i - 120:i])); r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return bool(v[i] >= ma and float(np.std(r) * math.sqrt(252)) < 0.35)

        def vol(k, d):
            i = idx(k, d)
            if i is None or i < 61: return 0.25
            _, v = ser[k]; r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return float(np.std(r) * math.sqrt(252))

        pool = lambda d: [r["kod"] for r in rk[d]][:POOL]
        SEL = {"H0_top30": (lambda d: pool(d), N30), "H0_top20": (lambda d: pool(d), N20),
               "ET_top20": (lambda d: sorted(pool(d), key=lambda k: (-preds["EXTRATREES"].get(d, {}).get(k, -1e18), k)), N20),
               "XGB_top20": (lambda d: sorted(pool(d), key=lambda k: (-preds["XGBOOST"].get(d, {}).get(k, -1e18), k)), N20)}

        def kor(of, N, exp="E1", vikt="invvol1.5", fr=True, tak="legacy", likavikt=False):
            prev, nets, kassa, antal, oms, kost = [], [], [], [], [], []
            for i, d in enumerate(W["paneler"]):
                if i % 2 == 0 or not prev:
                    cur = of(d)[:N]; turn = len(set(cur) - set(prev)) / max(1, N) if prev else 0.0; prev = cur
                else: turn = 0.0
                if i < fe: continue
                if likavikt:
                    nets.append(sum(rm.get((k, d), 0.) for k in prev) / max(1, len(prev)) - COST * turn)
                    kassa.append(0.0); antal.append(len(prev)); oms.append(turn); kost.append(COST * turn); continue
                sel = [k for k in prev if sma_ok(k, d)] if exp in ("E1", "E2") else list(prev)
                n = len(sel); antal.append(n); oms.append(turn); kost.append(COST * turn)
                if n == 0:
                    nets.append(0.0); kassa.append(1.0); continue
                ts = n / N if exp == "E1" else 1.0
                kassa.append(1.0 - ts)
                if vikt == "invvol1.5":
                    inv = 1.0 / (np.maximum(np.array([vol(k, d) for k in sel]), 0.05) ** 1.5)
                    w = inv / np.sum(inv) * ts
                else: w = np.full(n, ts / n)
                if fr: w = w * np.array([1.0 if bekr(k, d) else 0.75 for k in sel])
                if tak == "legacy":
                    w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
                else: w = w / np.sum(w) * ts
                nets.append(float(np.sum(w * np.array([rm.get((k, d), 0.) for k in sel]))) - COST * turn)
            return (np.asarray(nets), float(np.mean(kassa)), float(np.mean(antal)),
                    float(np.sum(oms)), float(np.sum(kost)))

        # ---------- DEL 1: huvudtabell ----------
        tab, S = {}, {}
        for lbl, (of, N) in SEL.items():
            for mode, kw in (("EW", dict(likavikt=True)), ("V3LAYER", dict())):
                nm = f"{lbl}_{mode}"
                nets, ka, an, om, ko = kor(of, N, **kw)
                S[nm] = nets
                tab[nm] = {**stat(nets), "N": N, "turnover_total": round(om, 4),
                           "mean_turnover": round(om / nev, 4), "kostnad_total": round(ko, 4),
                           "mean_kassa": round(ka, 4), "mean_exposure": round(1 - ka, 4),
                           "mean_innehav": round(an, 2)}
        for a, b in (("ET_top20_EW", "H0_top20_EW"), ("XGB_top20_EW", "H0_top20_EW"),
                     ("ET_top20_V3LAYER", "H0_top20_V3LAYER"), ("XGB_top20_V3LAYER", "H0_top20_V3LAYER"),
                     ("ET_top20_EW", "H0_top30_EW"), ("XGB_top20_EW", "H0_top30_EW"),
                     ("ET_top20_V3LAYER", "H0_top30_V3LAYER"), ("XGB_top20_V3LAYER", "H0_top30_V3LAYER")):
            tab[a].setdefault("vs", {})[b] = {**boot(S[a], S[b]),
                "delta_sharpe": round(tab[a]["sharpe"] - tab[b]["sharpe"], 4),
                "delta_maxdd_pp": round(100 * (tab[a]["maxdd"] - tab[b]["maxdd"]), 2)}

        # ---------- DEL 2: officiella H0 V3 periodmatchad ----------
        fz = json.loads((V2 / frozen).read_text())["nettoserie_h0"]
        officiell = {"hela_fonstret": stat(fz), "periodmatchad": stat(fz[-nev:])}

        # ---------- DEL 3: faktoriell uppdelning per URVAL ----------
        fac = {}
        for lbl, (of, N) in SEL.items():
            arms = {}
            for e, v_, f_, t_ in product(("E0", "E1", "E2"), ("likavikt", "invvol1.5"), (False, True), ("inget", "legacy")):
                nets, *_ = kor(of, N, exp=e, vikt=v_, fr=f_, tak=t_)
                arms[f"{e}|{v_}|{'FR' if f_ else 'noFR'}|{t_}"] = float(np.prod(1 + nets) ** (PPY / nev) - 1)
            K = lambda pairs: round(100 * float(np.mean([arms[a] - arms[b] for a, b in pairs])), 3)
            P = list(product(("likavikt", "invvol1.5"), ("noFR", "FR"), ("inget", "legacy")))
            fac[lbl] = {
                "K4a_namnfilter": K([(f"E2|{v}|{f}|{t}", f"E0|{v}|{f}|{t}") for v, f, t in P]),
                "K4b_kassakanal": K([(f"E1|{v}|{f}|{t}", f"E2|{v}|{f}|{t}") for v, f, t in P]),
                "K4_SMA_som_kors": K([(f"E1|{v}|{f}|{t}", f"E0|{v}|{f}|{t}") for v, f, t in P]),
                "K5_invvol": K([(f"{e}|invvol1.5|{f}|{t}", f"{e}|likavikt|{f}|{t}")
                                for e, f, t in product(("E0", "E1", "E2"), ("noFR", "FR"), ("inget", "legacy"))]),
                "K6_FR": K([(f"{e}|{v}|FR|{t}", f"{e}|{v}|noFR|{t}")
                            for e, v, t in product(("E0", "E1", "E2"), ("likavikt", "invvol1.5"), ("inget", "legacy"))]),
                "K7_tak": K([(f"{e}|{v}|{f}|legacy", f"{e}|{v}|{f}|inget")
                             for e, v, f in product(("E0", "E1", "E2"), ("likavikt", "invvol1.5"), ("noFR", "FR"))]),
                "tom_arm_cagr_pct": round(100 * arms["E0|likavikt|noFR|inget"], 3),
                "full_arm_cagr_pct": round(100 * arms["E1|invvol1.5|FR|legacy"], 3)}
            fac[lbl]["total_lagereffekt_pp"] = round(fac[lbl]["full_arm_cagr_pct"] - fac[lbl]["tom_arm_cagr_pct"], 3)
        ut["fonster"][wn] = {"n_eval_paneler": nev, "forsta": dagar[0], "sista": dagar[-1],
                             "kostnadsmodell": "20 bp enkelriktat pa namnbaserad omsattning",
                             "tabell": tab, "H0_V3_officiell": officiell, "faktoriell_per_urval": fac}
        for k, v in S.items(): np.save(UT / f"nets_{wn}_{k}.npy", v)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
