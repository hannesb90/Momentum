"""COMPLETE_MODEL_HETEROGENEITY_CONTROLS — slutfor size/ICB-sparet.

Forregistrering: research_k/model_heterogeneity_controls/MODEL_HETEROGENEITY_CONTROLS_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen routing. Inget trad. Inga makrovariabler.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/model_heterogeneity_controls"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "MODEL_HETEROGENEITY_CONTROLS_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
POOL, PPY, BLOCK, DRAWS, SEED = 30, 13.0, 13, 2000, 20260815


def dm(x, pid):
    x = np.asarray(x, float); o = x.copy()
    for p in np.unique(pid):
        m = pid == p; o[m] = x[m] - x[m].mean()
    return o


def ols_cl(y, X, pid):
    XtX = X.T @ X
    if np.linalg.cond(XtX) > 1e12: return None, None
    b = np.linalg.solve(XtX, X.T @ y); e = y - X @ b; XtXi = np.linalg.inv(XtX)
    meat = np.zeros_like(XtX)
    for p in np.unique(pid):
        m = pid == p; s = X[m].T @ e[m]; meat += np.outer(s, s)
    Gn = len(np.unique(pid)); n, k = X.shape
    return b, XtXi @ ((Gn / (Gn - 1)) * ((n - 1) / (n - k)) * meat) @ XtXi


def wald(b, V, idx):
    if b is None or len(idx) < 2: return None, None, 0
    Rm = np.zeros((len(idx) - 1, len(b)))
    for i, j in enumerate(idx[1:]): Rm[i, j] = 1.; Rm[i, idx[0]] = -1.
    Rb = Rm @ b
    try: Wv = float(Rb @ np.linalg.solve(Rm @ V @ Rm.T, Rb))
    except np.linalg.LinAlgError: return None, None, 0
    return round(Wv, 3), float(1 - stats.chi2.cdf(Wv, len(idx) - 1)), len(idx) - 1


def build(wn, G, R, H, WK):
    W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
    isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]
    rows = []
    for pi, d in enumerate(dagar):
        u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
        h0s = {r["kod"]: r["score"] for r in rk[d]}
        pool = set([r["kod"] for r in rk[d]][:POOL])
        rec = {}
        for k in u:
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            if not r_: continue
            mc = r_.get("market_cap"); ic = r_.get("industry")
            lq = r_.get("turnover_velocity"); sp_ = r_.get("avg_closing_spread")
            i2 = idx(k, d)
            if i2 is None or i2 < 61: continue
            _, v = ser[k]; rr = np.diff(v[i2 - 60:i2 + 1]) / v[i2 - 60:i2]
            vo = float(np.std(rr) * math.sqrt(252))
            if not (mc and ic and lq and sp_ and np.isfinite(vo)): continue
            rec[k] = dict(mc=float(mc), icb=ic, liq=float(lq), spr=float(sp_), vol=vo)
        ok = [k for k in u if k in rec]
        if len(ok) < 20: continue
        pct = {}
        bad = False
        for e, sc in (("H0", {k: h0s[k] for k in ok}),
                      ("ET", {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in ok}),
                      ("XGB", {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in ok})):
            v = np.array([sc[k] for k in ok], float)
            if not np.all(np.isfinite(v)): bad = True; break
            pct[e] = dict(zip(ok, np.argsort(np.argsort(v)).astype(float) / max(1, len(v) - 1)))
        if bad: continue
        z = lambda a: (np.asarray(a, float) - np.mean(a)) / (np.std(a) or 1)
        S = z([math.log1p(rec[k]["mc"]) for k in ok]); VO = z([rec[k]["vol"] for k in ok])
        LQ = z([rec[k]["liq"] for k in ok]); SP = z([rec[k]["spr"] for k in ok])
        for j, k in enumerate(ok):
            rows.append({"p": pi, "k": k, "ret": rm[(k, d)], "s": float(S[j]), "vol": float(VO[j]),
                         "liq": float(LQ[j]), "spr": float(SP[j]), "icb": rec[k]["icb"],
                         "inpool": 1.0 if k in pool else 0.0,
                         "pH0": pct["H0"][k], "pET": pct["ET"][k], "pXGB": pct["XGB"][k]})
    return rows


def kolumner(rows, d_, spec, grp):
    n = len(rows); pid = np.array([r["p"] for r in rows])
    s = np.array([r["s"] for r in rows]); nm = []
    if "ICB" in spec:
        # Sum_g d*1[g] == d exakt -> den fristaende d-kolumnen maste UTESLUTAS.
        # ICB-dummies: en referenskategori utesluts (summan absorberas av panel-FE).
        C = [dm(s, pid), dm(d_ * s, pid)]; nm += ["s", "d_s"]
        for g in grp:
            C.append(dm(np.array([d_[i] if rows[i]["icb"] == g else 0. for i in range(n)]), pid)); nm.append(f"d_icb_{g}")
        for g in grp[1:]:
            C.append(dm(np.array([1. if rows[i]["icb"] == g else 0. for i in range(n)]), pid)); nm.append(f"icb_{g}")
    else:
        C = [dm(d_, pid), dm(s, pid), dm(d_ * s, pid)]; nm += ["d", "s", "d_s"]
    if "CTRL" in spec:
        for c in ("vol", "liq", "spr"):
            v = np.array([r[c] for r in rows])
            C.append(dm(v, pid)); nm.append(c)
            C.append(dm(d_ * v, pid)); nm.append(f"d_{c}")
    return np.column_stack(C), nm, pid


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
    ut = {"version": "MODEL_HETEROGENEITY_CONTROLS_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "MODEL_HETEROGENEITY_CONTROLS_PREREGISTRATION.json"),
          "crosswalk_sha256": sha(UT / "ICB_HISTORICAL_CROSSWALK.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        allrows = build(wn, G, R, H, WK)
        res = {"n_obs_full": len(allrows)}
        for popn in ("FULL", "POOL"):
            rows = allrows if popn == "FULL" else [r for r in allrows if r["inpool"] == 1.0]
            grp = sorted({r["icb"] for r in rows})
            y = np.array([r["ret"] for r in rows]); pid0 = np.array([r["p"] for r in rows])
            o = {"n_obs": len(rows), "n_grupper": len(grp), "size": {}, "icb": {}, "sd_d": {}}
            for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
                d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
                sd_d = float(np.std(d_)); o["sd_d"][mod] = round(sd_d, 4)
                # ---- SIZE: tre specifikationer
                sz = {}
                for lbl, spec in (("RAW", ""), ("EFTER_ICB", "ICB"), ("FULLT", "ICB+CTRL")):
                    X, nm, pid = kolumner(rows, d_, spec, grp)
                    b, V = ols_cl(dm(y, pid0), X, pid0)
                    if b is None: sz[lbl] = {"status": "SINGULAR"}; continue
                    i3 = nm.index("d_s"); se = math.sqrt(V[i3, i3])
                    t = float(b[i3] / se)
                    sz[lbl] = {"b3": round(float(b[i3]), 6), "t": round(t, 3),
                               "p": round(2 * (1 - stats.t.cdf(abs(t), len(np.unique(pid0)) - 1)), 5),
                               "std_effekt_pp_per_ar": round(100 * float(b[i3]) * sd_d * PPY, 3),
                               "raw_effekt_4SD_pp_per_ar": round(100 * float(b[i3]) * 4 * PPY, 2)}
                o["size"][mod] = sz
                # ---- ICB: tre specifikationer
                ic = {}
                for lbl, spec in (("RAW", "ICB_ONLY"), ("EFTER_SIZE", "ICB"), ("FULLT", "ICB+CTRL")):
                    if spec == "ICB_ONLY":
                        C = [dm(np.array([d_[i] if rows[i]["icb"] == g else 0. for i in range(len(rows))]), pid0) for g in grp]
                        idxg = list(range(len(grp)))
                        for g in grp[1:]:
                            C.append(dm(np.array([1. if rows[i]["icb"] == g else 0. for i in range(len(rows))]), pid0))
                        X = np.column_stack(C)
                    else:
                        X, nm, _ = kolumner(rows, d_, spec, grp)
                        idxg = [nm.index(f"d_icb_{g}") for g in grp]
                    b, V = ols_cl(dm(y, pid0), X, pid0)
                    Wv, pv, df = wald(b, V, idxg)
                    per = {g: round(100 * float(b[idxg[i]]) * sd_d * PPY, 3) for i, g in enumerate(grp)} if b is not None else {}
                    ic[lbl] = {"omnibus_W": Wv, "omnibus_p": round(pv, 5) if pv is not None else None, "df": df,
                               "std_edge_per_grupp_pp_per_ar": per,
                               "mellan_grupp_sd_pp": round(float(np.std(list(per.values()), ddof=1)), 3) if per else None}
                o["icb"][mod] = ic
            res[popn] = o
        # ---- DEL 12 trevags + DEL 13 populationsinteraktion, bada pa FULL
        rows = allrows; grp = sorted({r["icb"] for r in rows}); pid0 = np.array([r["p"] for r in rows])
        y = np.array([r["ret"] for r in rows]); s = np.array([r["s"] for r in rows])
        stor = [g for g in grp if sum(1 for r in rows if r["icb"] == g) >= 50]
        res["DEL12"] = {}; res["DEL13"] = {}
        for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
            d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
            if len(stor) >= 8:
                # Sum_g d*s*1[g] == d*s och Sum_g d*1[g] == d -> bada fristaende termer utesluts
                C = [dm(s, pid0)]
                C += [dm(np.array([d_[i] * s[i] if rows[i]["icb"] == g else 0. for i in range(len(rows))]), pid0) for g in stor]
                idxs = list(range(1, 1 + len(stor)))
                C += [dm(np.array([d_[i] if rows[i]["icb"] == g else 0. for i in range(len(rows))]), pid0) for g in stor]
                X = np.column_stack(C)
                b, V = ols_cl(dm(y, pid0), X, pid0)
                Wv, pv, df = wald(b, V, idxs)
                res["DEL12"][mod] = {"status": "IDENTIFIERBAR" if b is not None else "SINGULAR",
                                     "n_grupper": len(stor), "omnibus_W": Wv,
                                     "omnibus_p": round(pv, 5) if pv is not None else None, "df": df}
            else:
                res["DEL12"][mod] = {"status": "NOT_IDENTIFIABLE_WITH_CURRENT_HISTORY", "n_grupper_over_50": len(stor)}
            ip = np.array([r["inpool"] for r in rows])
            X = np.column_stack([dm(d_, pid0), dm(s, pid0), dm(d_ * s, pid0), dm(ip, pid0),
                                 dm(d_ * ip, pid0), dm(d_ * s * ip, pid0)])
            b, V = ols_cl(dm(y, pid0), X, pid0)
            if b is not None:
                se = math.sqrt(V[5, 5]); t = float(b[5] / se)
                res["DEL13"][mod] = {"d_s_inpool": round(float(b[5]), 6), "t": round(t, 3),
                                     "p": round(2 * (1 - stats.t.cdf(abs(t), len(np.unique(pid0)) - 1)), 5),
                                     "tolkning": "positiv = size-interaktionen ar mindre negativ inuti H0-poolen"}
        ut["fonster"][wn] = res
        print(f"{wn} klart: {len(allrows)} obs med samtliga kontroller", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
