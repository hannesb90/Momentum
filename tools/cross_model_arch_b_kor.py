"""CROSS_MODEL_ARCH_B_H0_POOL_ML_RANK — konfirmatoriskt test.

Forregistrering: research_k/cross_model_arch_b/preregistration.json
INGA MODELLER TRANAS. De redan frysta, forregistrerade och tva ganger reproducerade
F0-prediktionerna fran GLOBAL_ML_FULL_PIT_FEATURE_RACE aateranvands ordagrant.

Kor: /opt/momentum/venv/bin/python tools/cross_model_arch_b_kor.py
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/cross_model_arch_b"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
PRE = json.loads((UT / "preregistration.json").read_text())
POOL, NPRIM, NSEK = 30, 20, [10, 15]

_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G)
R = G.R
PPY, BLOCK, DRAWS, SEED = 13.0, 13, 2000, 20260815


def z(x):
    r = np.argsort(np.argsort(np.asarray(x, float))).astype(float)
    return (r - r.mean()) / (r.std() or 1.0)


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def resid_ic(ms, ret, ctrls):
    a = z(ms)
    if ctrls:
        X = np.vstack([z(c) for c in ctrls]).T
        beta = np.linalg.lstsq(X, a, rcond=None)[0]
        a = a - X @ beta
    return sp(a, ret)


def boot(a, b):
    rng = np.random.default_rng(SEED); n = len(a); out = []
    for _ in range(DRAWS):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, max(1, n - BLOCK + 1)); idx.extend(range(s, min(s + BLOCK, n)))
        idx = np.array(idx[:n])
        out.append(np.prod(1 + a[idx]) ** (PPY / n) - np.prod(1 + b[idx]) ** (PPY / n))
    out = np.asarray(out); d = a - b
    t = float(d.mean() / (d.std(ddof=1) / math.sqrt(n))) if d.std(ddof=1) > 0 else 0.0
    return {"excess_pp": round(100 * float(np.prod(1 + a) ** (PPY / n) - np.prod(1 + b) ** (PPY / n)), 3),
            "ki_lo_pp": round(100 * float(np.percentile(out, 2.5)), 3),
            "ki_hi_pp": round(100 * float(np.percentile(out, 97.5)), 3),
            "t": round(t, 3), "andel_boot_pos": round(float(np.mean(out > 0)), 3),
            "hit_rate": round(float(np.mean(a > b)), 4)}


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "CROSS_MODEL_ARCH_B_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = sorted(preds["EXTRATREES"])
        fe = W["paneler"].index(dagar[0])

        def vol60(k, d):
            i = idx(k, d)
            if i is None or i < 61: return np.nan
            _, v = ser[k]; r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return float(np.std(r) * math.sqrt(252))

        def nas(k, d, f):
            r = G.nasdaq_rad(k, isin.get(k), d)
            v = r.get(f) if r else None
            return float(v) if v not in (None, 0) else np.nan

        def pool_of(d):
            return [r["kod"] for r in rk[d]][:POOL]

        def of_h0(day, i): return pool_of(day)

        def of_ml(m):
            def f(day, i):
                p = pool_of(day); s = preds[m].get(day, {})
                return sorted(p, key=lambda k: (-s.get(k, -1e18), k))
            return f

        res = {"n_eval_paneler": len(dagar), "forsta_panel": dagar[0], "sista_panel": dagar[-1], "armar": {}}
        serier = {}
        for namn, of, n in [("B0_H0_top30", of_h0, 30), ("B1_H0_top20", of_h0, NPRIM),
                            ("T1_ExtraTrees_top20", of_ml("EXTRATREES"), NPRIM),
                            ("T2_XGBoost_top20", of_ml("XGBOOST"), NPRIM)] + \
                           [(f"B1_H0_top{n}", of_h0, n) for n in NSEK] + \
                           [(f"T1_ExtraTrees_top{n}", of_ml("EXTRATREES"), n) for n in NSEK] + \
                           [(f"T2_XGBoost_top{n}", of_ml("XGBOOST"), n) for n in NSEK]:
            nets, turns, _ = R.simulate(W, of, fe, top_n=n)
            serier[namn] = nets
            res["armar"][namn] = {**R.stat(nets), "n": n,
                                  "turnover": round(float(np.sum(turns)), 4),
                                  "mean_turnover": round(float(np.mean(turns)), 4),
                                  "cost_10bp": R.cost_sens(W, of, fe, 0.001, top_n=n),
                                  "cost_40bp": R.cost_sens(W, of, fe, 0.004, top_n=n)}
        # excess mot B1 (koncentrationsmatchad)
        for t in ("T1_ExtraTrees", "T2_XGBoost"):
            for n in [NPRIM] + NSEK:
                res["armar"][f"{t}_top{n}"]["vs_B1"] = boot(serier[f"{t}_top{n}"], serier[f"B1_H0_top{n}"])
                a = set(); b = set()
                res["armar"][f"{t}_top{n}"]["primar" if n == NPRIM else "robusthet"] = True

        # ---- IC-stegen inom H0-poolen
        ics = {m: {k: [] for k in ("ic", "r_h0", "r_h0_vol", "r_h0_vol_size", "r_h0_vol_size_spread")}
               for m in preds}
        ovl = {m: [] for m in preds}; rho = {m: [] for m in preds}
        for d in dagar:
            p = [k for k in pool_of(d) if (k, d) in rm]
            if len(p) < 20: continue
            h0r = {r["kod"]: r["score"] for r in rk[d]}
            ret = [rm[(k, d)] for k in p]
            hs = [h0r[k] for k in p]
            vo = [vol60(k, d) for k in p]
            mc = [math.log1p(nas(k, d, "market_cap")) if np.isfinite(nas(k, d, "market_cap")) else np.nan for k in p]
            spr = [nas(k, d, "avg_closing_spread") for k in p]
            ok = [i for i in range(len(p)) if np.isfinite(vo[i]) and np.isfinite(mc[i]) and np.isfinite(spr[i])]
            if len(ok) < 20: continue
            P = [p[i] for i in ok]; RT = [ret[i] for i in ok]; HS = [hs[i] for i in ok]
            VO = [vo[i] for i in ok]; MC = [mc[i] for i in ok]; SP = [spr[i] for i in ok]
            for m in preds:
                s = preds[m].get(d, {})
                if not all(k in s for k in P): continue
                ms = [s[k] for k in P]
                ics[m]["ic"].append(sp(ms, RT))
                ics[m]["r_h0"].append(resid_ic(ms, RT, [HS]))
                ics[m]["r_h0_vol"].append(resid_ic(ms, RT, [HS, VO]))
                ics[m]["r_h0_vol_size"].append(resid_ic(ms, RT, [HS, VO, MC]))
                ics[m]["r_h0_vol_size_spread"].append(resid_ic(ms, RT, [HS, VO, MC, SP]))
                rho[m].append(sp(ms, HS))
                mt = sorted(P, key=lambda k: (-s.get(k, -1e18), k))[:NPRIM]
                ovl[m].append(len(set(mt) & set([r["kod"] for r in rk[d]][:NPRIM])))
        res["ic"] = {}
        for m in preds:
            f = lambda L: (round(float(np.nanmean(L)), 4),
                           round(float(np.nanmean(L) / (np.nanstd(L, ddof=1) / math.sqrt(len(L)))), 2),
                           round(float(np.mean(np.asarray(L) > 0)), 3))
            res["ic"][m] = {k: dict(zip(("medel", "t", "andel_pos"), f(v))) for k, v in ics[m].items()}
            res["ic"][m]["rho_H0"] = round(float(np.nanmean(rho[m])), 4)
            res["ic"][m]["namnoverlapp_top20_mot_H0top20"] = round(float(np.mean(ovl[m])), 2)
            res["ic"][m]["n_paneler"] = len(ics[m]["ic"])
        ut["fonster"][wn] = res
        for k, v in serier.items(): np.save(UT / f"nets_{wn}_{k}.npy", v)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
