"""PIT_SIZE_HETEROGENEITY — varierar ET/XGB:s relativa fordel mot H0 med bolagsstorlek?

Forregistrering: research_k/pit_size_heterogeneity/preregistration.json
INGA MODELLER TRANAS. Frysta F0-prediktioner aateranvands ordagrant.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/pit_size_heterogeneity"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
POOL, NSEL, PPY = 30, 20, 13.0
BLOCK, DRAWS, SEED = 13, 2000, 20260815
MDE_REF_PP_PER_PANEL = 0.65   # storsta observerade relativa selektionsfordel, ur forregistreringen


def within(x, pid):
    x = np.asarray(x, float); out = x.copy()
    for p in np.unique(pid):
        m = pid == p; out[m] = x[m] - x[m].mean()
    return out


def ols_cluster(y, X, pid):
    XtX = X.T @ X
    b = np.linalg.solve(XtX, X.T @ y)
    e = y - X @ b
    XtXi = np.linalg.inv(XtX)
    meat = np.zeros_like(XtX)
    for p in np.unique(pid):
        m = pid == p; Xg = X[m]; eg = e[m]
        s = Xg.T @ eg
        meat += np.outer(s, s)
    G_ = len(np.unique(pid)); n, k = X.shape
    c = (G_ / (G_ - 1)) * ((n - 1) / (n - k))
    V = XtXi @ (c * meat) @ XtXi
    return b, np.sqrt(np.diag(V))


def build(wn):
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    W = R.load_window(wn); rk, rm = W["rankings"], W["retmap"]
    isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
             for m in ("EXTRATREES", "XGBOOST")}
    rows = []
    saknat = 0
    for pi, d in enumerate(sorted(preds["EXTRATREES"])):
        if d not in rk: continue
        pool = [r["kod"] for r in rk[d]][:POOL]
        pool = [k for k in pool if (k, d) in rm]
        if len(pool) < 25: continue
        mc = {}
        for k in pool:
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            v = r_.get("market_cap") if r_ else None
            if v: mc[k] = float(v)
        saknat += len(pool) - len(mc)
        ok = [k for k in pool if k in mc]
        if len(ok) < 20: continue
        order = sorted(ok, key=lambda k: mc[k])
        pct = {k: (i / (len(order) - 1)) for i, k in enumerate(order)}   # [0,1] inom poolen
        h20 = set(pool[:NSEL])
        sel = {"H0": h20}
        for m, nm in (("EXTRATREES", "ET"), ("XGBOOST", "XGB")):
            s = preds[m].get(d, {})
            sel[nm] = set(sorted(pool, key=lambda k: (-s.get(k, -1e18), k))[:NSEL])
        for k in ok:
            rows.append({"panel": pi, "dt": d, "kod": k, "ret": rm[(k, d)],
                         "s": pct[k] - 0.5, "mcap": mc[k],
                         "H0": 1.0 if k in sel["H0"] else 0.0,
                         "ET": 1.0 if k in sel["ET"] else 0.0,
                         "XGB": 1.0 if k in sel["XGB"] else 0.0})
    return rows, saknat


def test(rows, mod):
    pid = np.array([r["panel"] for r in rows])
    y = np.array([r["ret"] for r in rows], float)
    d = np.array([r[mod] - r["H0"] for r in rows], float)
    s = np.array([r["s"] for r in rows], float)
    Xc = np.column_stack([within(d, pid), within(s, pid), within(d * s, pid)])
    yc = within(y, pid)
    b, se = ols_cluster(yc, Xc, pid)
    # blockbootstrap over paneler
    P = np.unique(pid); nP = len(P); rng = np.random.default_rng(SEED); bs = []
    for _ in range(DRAWS):
        ix = []
        while len(ix) < nP:
            st = rng.integers(0, max(1, nP - BLOCK + 1)); ix.extend(range(st, min(st + BLOCK, nP)))
        ix = ix[:nP]
        sel = np.concatenate([np.where(pid == P[j])[0] for j in ix])
        pid2 = np.concatenate([np.full((pid == P[j]).sum(), n) for n, j in enumerate(ix)])
        try:
            bb, _ = ols_cluster(within(y[sel], pid2),
                                np.column_stack([within(d[sel], pid2), within(s[sel], pid2),
                                                 within((d * s)[sel], pid2)]), pid2)
            bs.append(bb[2])
        except np.linalg.LinAlgError:
            pass
    bs = np.asarray(bs)
    # icke-linjaritetsdiagnostik (forregistrerad, ej primar)
    X4 = np.column_stack([within(d, pid), within(s, pid), within(d * s, pid), within(d * s * s, pid)])
    b4, se4 = ols_cluster(yc, X4, pid)
    return {"beta1_d": round(float(b[0]), 6), "beta3_interaktion": round(float(b[2]), 6),
            "se_beta3_cluster": round(float(se[2]), 6),
            "t_beta3": round(float(b[2] / se[2]), 3) if se[2] else None,
            "MDE_t3_pp_per_panel": round(300 * float(se[2]), 4),
            "boot_ki_lo": round(float(np.percentile(bs, 2.5)), 6),
            "boot_ki_hi": round(float(np.percentile(bs, 97.5)), 6),
            "boot_andel_pos": round(float(np.mean(bs > 0)), 3),
            "n_obs": len(rows), "n_paneler": int(len(np.unique(pid))),
            "n_avvikande": int((d != 0).sum()),
            "beta3_med_kvadratterm": round(float(b4[2]), 6),
            "beta4_kvadrat": round(float(b4[3]), 6), "t_beta4": round(float(b4[3] / se4[3]), 3) if se4[3] else None}


def terciler(rows, mod):
    out = {}
    for lo, hi, nm in ((-0.5, -1 / 6, "liten"), (-1 / 6, 1 / 6, "mellan"), (1 / 6, 0.5, "stor")):
        g = [r for r in rows if lo <= r["s"] < hi or (nm == "stor" and r["s"] >= hi)]
        if not g: continue
        dv = np.array([r[mod] - r["H0"] for r in g]); rv = np.array([r["ret"] for r in g])
        selR = [r["ret"] for r in g if r[mod] == 1]; selH = [r["ret"] for r in g if r["H0"] == 1]
        out[nm] = {"n": len(g), "n_avvikande": int((dv != 0).sum()),
                   "medel_ret_vald_R": round(float(np.mean(selR)), 5) if selR else None,
                   "medel_ret_vald_H0": round(float(np.mean(selH)), 5) if selH else None,
                   "R_minus_H0_pp": round(100 * (float(np.mean(selR)) - float(np.mean(selH))), 3) if selR and selH else None,
                   "differentialbidrag_pp": round(100 * float(np.mean(dv * rv)) * NSEL, 3)}
    return out


def main():
    ut = {"version": "PIT_SIZE_HETEROGENEITY_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        rows, saknat = build(wn)
        r = {"n_obs": len(rows), "n_saknat_market_cap": saknat, "test": {}, "terciler": {}}
        for mod in ("ET", "XGB"):
            r["test"][mod] = test(rows, mod)
            r["terciler"][mod] = terciler(rows, mod)
        ut["fonster"][wn] = r
        print(f"{wn}: {len(rows)} obs, {saknat} utan market_cap", flush=True)
        for mod in ("ET", "XGB"):
            t = r["test"][mod]
            print(f"   {mod:4s} beta3 {t['beta3_interaktion']:+.5f}  t {t['t_beta3']:+.2f}  "
                  f"MDE(t=3) {t['MDE_t3_pp_per_panel']:.3f} pp/panel  n_avvik {t['n_avvikande']}", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
