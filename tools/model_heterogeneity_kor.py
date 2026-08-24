"""MODEL_HETEROGENEITY_BY_SIZE_AND_ICB — varierar H0/ET/XGB:s RELATIVA edge med population?

Forregistrering: research_k/model_heterogeneity/preregistration.json
Estimand: MODEL x SIZE och MODEL x ICB. INTE routingvarde, INTE nodvis CAGR.
INGA MODELLER TRANAS.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/model_heterogeneity"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
POOL, PPY, BLOCK, DRAWS, SEED = 30, 13.0, 13, 2000, 20260815


def ols_cl(y, X, pid):
    b = np.linalg.solve(X.T @ X, X.T @ y); e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X); meat = np.zeros((X.shape[1], X.shape[1]))
    for p in np.unique(pid):
        m = pid == p; s = X[m].T @ e[m]; meat += np.outer(s, s)
    Gn = len(np.unique(pid)); n, k = X.shape
    return b, XtXi @ ((Gn / (Gn - 1)) * ((n - 1) / (n - k)) * meat) @ XtXi


def wald_lika(b, V, idx):
    if len(idx) < 2: return None, None, 0
    Rm = np.zeros((len(idx) - 1, len(b)))
    for i, j in enumerate(idx[1:]): Rm[i, j] = 1.0; Rm[i, idx[0]] = -1.0
    Rb = Rm @ b
    try: Wv = float(Rb @ np.linalg.solve(Rm @ V @ Rm.T, Rb))
    except np.linalg.LinAlgError: return None, None, 0
    df = len(idx) - 1
    return round(Wv, 3), float(1 - stats.chi2.cdf(Wv, df)), df


def demean(x, pid):
    x = np.asarray(x, float); o = x.copy()
    for p in np.unique(pid):
        m = pid == p; o[m] = x[m] - x[m].mean()
    return o


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
    ut = {"version": "MODEL_HETEROGENEITY_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm = W["rankings"], W["retmap"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]
        DATA = {"FULL": [], "POOL": []}; saknat = 0
        for pi, d in enumerate(dagar):
            u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
            h0s = {r["kod"]: r["score"] for r in rk[d]}
            for popn, names in (("FULL", u), ("POOL", [k for k in [r["kod"] for r in rk[d]][:POOL] if (k, d) in rm])):
                mc, ic = {}, {}
                for k in names:
                    r_ = G.nasdaq_rad(k, isin.get(k), d)
                    mc[k] = float(r_["market_cap"]) if (r_ and r_.get("market_cap")) else None
                    ic[k] = (r_.get("industry") if r_ else None)
                ok = [k for k in names if mc[k] and ic[k]]
                if popn == "FULL": saknat += len(names) - len(ok)
                if len(ok) < 15: continue
                pct = {}
                for e, sc in (("H0", {k: h0s[k] for k in ok}),
                              ("ET", {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in ok}),
                              ("XGB", {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in ok})):
                    v = np.array([sc[k] for k in ok], float)
                    if not np.all(np.isfinite(v)): pct = None; break
                    pct[e] = dict(zip(ok, np.argsort(np.argsort(v)).astype(float) / max(1, len(v) - 1)))
                if pct is None: continue
                ls = np.array([math.log1p(mc[k]) for k in ok]); ls = (ls - ls.mean()) / (ls.std() or 1)
                for j, k in enumerate(ok):
                    DATA[popn].append({"p": pi, "k": k, "ret": rm[(k, d)], "s": float(ls[j]),
                                       "icb": ic[k], "pH0": pct["H0"][k], "pET": pct["ET"][k], "pXGB": pct["XGB"][k]})
        res = {"n_paneler": len(dagar), "n_saknat_market_cap_eller_icb_FULL": saknat, "populationer": {}}
        for popn in ("FULL", "POOL"):
            rows = DATA[popn]
            pid = np.array([r["p"] for r in rows]); y = np.array([r["ret"] for r in rows], float)
            s = np.array([r["s"] for r in rows], float)
            out = {"n_obs": len(rows), "n_paneler": int(len(np.unique(pid))), "size": {}, "icb": {}}
            for mod, key in (("ET", "pET"), ("XGB", "pXGB"), ("ET_vs_XGB", None)):
                d_ = (np.array([r[key] for r in rows], float) - np.array([r["pH0"] for r in rows], float)
                      if key else np.array([r["pET"] for r in rows], float) - np.array([r["pXGB"] for r in rows], float))
                # ---- SIZE: g1*d + g2*s + g3*(d*s), panel-FE via demeaning
                X = np.column_stack([demean(d_, pid), demean(s, pid), demean(d_ * s, pid)])
                b, V = ols_cl(demean(y, pid), X, pid)
                se = np.sqrt(np.diag(V))
                # blockbootstrap pa g3
                P = np.unique(pid); nP = len(P); rng = np.random.default_rng(SEED); bs = []
                for _ in range(DRAWS):
                    ix = []
                    while len(ix) < nP:
                        st = rng.integers(0, max(1, nP - BLOCK + 1)); ix.extend(range(st, min(st + BLOCK, nP)))
                    ix = ix[:nP]
                    sel = np.concatenate([np.where(pid == P[j])[0] for j in ix])
                    p2 = np.concatenate([np.full((pid == P[j]).sum(), n2) for n2, j in enumerate(ix)])
                    try:
                        bb, _ = ols_cl(demean(y[sel], p2), np.column_stack(
                            [demean(d_[sel], p2), demean(s[sel], p2), demean((d_ * s)[sel], p2)]), p2)
                        bs.append(bb[2])
                    except np.linalg.LinAlgError: pass
                bs = np.asarray(bs)
                g1, g3 = float(b[0]), float(b[2])
                out["size"][mod] = {
                    "g1_edge": round(g1, 6), "g1_edge_pp_per_ar": round(100 * g1 * PPY, 3),
                    "g3_interaktion": round(g3, 6), "t_g3": round(g3 / se[2], 3) if se[2] else None,
                    "ki_lo": round(float(np.percentile(bs, 2.5)), 6), "ki_hi": round(float(np.percentile(bs, 97.5)), 6),
                    "edge_forandring_over_4SD_pp_per_ar": round(100 * g3 * 4 * PPY, 3),
                    "materialitet_kvot": round(abs(g3 * 4) / abs(g1), 3) if g1 else None}
                if mod == "ET_vs_XGB": continue
                # ---- ICB: gamma_g per grupp + d*s som kontroll
                grp = sorted({r["icb"] for r in rows})
                Xg = [demean(np.array([d_[i] if rows[i]["icb"] == g else 0.0 for i in range(len(rows))]), pid) for g in grp]
                X2 = np.column_stack(Xg + [demean(s, pid), demean(d_ * s, pid)])
                b2, V2_ = ols_cl(demean(y, pid), X2, pid)
                Wv, pv, df = wald_lika(b2, V2_, list(range(len(grp))))
                per = {g: round(100 * float(b2[i]) * PPY, 3) for i, g in enumerate(grp)}
                out["icb"][mod] = {"omnibus_W": Wv, "omnibus_p": round(pv, 5) if pv is not None else None, "df": df,
                                   "n_grupper": len(grp), "edge_per_grupp_pp_per_ar": per,
                                   "spridning_pp": round(max(per.values()) - min(per.values()), 3),
                                   "mellan_grupp_sd_pp": round(float(np.std(list(per.values()), ddof=1)), 3)}
            res["populationer"][popn] = out
        ut["fonster"][wn] = res
        print(f"{wn}: FULL {len(DATA['FULL'])} obs, POOL {len(DATA['POOL'])} obs", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
