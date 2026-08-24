"""PIT_ICB_HETEROGENEITY steg 2 — INDUSTRY-nivan som EXPLORATORY_DIAGNOSTIC.

Supersektor-nivan (primar) foll pa n-kravet: kodsystemet byttes 2020-07 och de tva
fonstren har NOLL gemensamma supersektorkoder. Industry-etiketterna overlever brytet
for sju grupper. Denna korning ar darfor EXPLORATORISK och kan inte ge en primar dom.
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
UT = V2 / "research_k/pit_icb_heterogeneity"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
NSEL, MIN_A, MIN_B, PANELANDEL, TOPPCT = 20, 5, 8, 0.5, 0.10
DELADE = ["Basic Materials", "Financials", "Health Care", "Industrials", "Technology",
          "Telecommunications", "Utilities"]


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def ols_cluster(y, X, pid):
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
    return round(Wv, 3), round(float(1 - stats.chi2.cdf(Wv, df)), 5), df


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "PIT_ICB_INDUSTRY_EXPLORATORY_V1", "klass": "EXPLORATORY_DIAGNOSTIC",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"),
          "varfor_exploratorisk": "Primarnivan supersector foll: ICB bytte kodsystem 2020-07, noll gemensamma koder mellan fonstren.",
          "delade_industries": DELADE, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm = W["rankings"], W["retmap"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]

        def ind(k, d):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            return (r_.get("industry") if r_ else None)

        rowsA, cellB = [], []
        cA, cB = defaultdict(int), defaultdict(int)
        for pi, d in enumerate(dagar):
            u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
            h0s = {r["kod"]: r["score"] for r in rk[d]}
            io = {k: ind(k, d) for k in u}
            pool = [k for k in [r["kod"] for r in rk[d]][:30] if (k, d) in rm]
            selA = {"H0": set(pool[:NSEL])}
            for m, nm in (("EXTRATREES", "ET"), ("XGBOOST", "XGB")):
                s = preds[m].get(d, {})
                selA[nm] = set(sorted(pool, key=lambda k: (-s.get(k, -1e18), k))[:NSEL])
            gA = defaultdict(list)
            for k in pool:
                if io.get(k) in DELADE: gA[io[k]].append(k)
            for sc, ks in gA.items():
                if len(ks) < MIN_A: continue
                cA[sc] += 1
                for k in ks:
                    rowsA.append({"p": pi, "sc": sc, "ret": rm[(k, d)],
                                  "ET": (1.0 if k in selA["ET"] else 0.0) - (1.0 if k in selA["H0"] else 0.0),
                                  "XGB": (1.0 if k in selA["XGB"] else 0.0) - (1.0 if k in selA["H0"] else 0.0)})
            gB = defaultdict(list)
            for k in u:
                if io.get(k) in DELADE: gB[io[k]].append(k)
            for sc, ks in gB.items():
                if len(ks) < MIN_B: continue
                cB[sc] += 1
                ret = np.array([rm[(k, d)] for k in ks]); dem = ret - ret.mean()
                rec = {"p": pi, "sc": sc, "n": len(ks)}
                nt = max(3, int(round(TOPPCT * len(ks))))
                for nm, sco in (("H0", {k: h0s[k] for k in ks}),
                                ("ET", {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in ks}),
                                ("XGB", {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in ks})):
                    v = [sco[k] for k in ks]
                    if not np.all(np.isfinite(v)): rec[f"ic_{nm}"] = None; rec[f"top_{nm}"] = None; continue
                    rec[f"ic_{nm}"] = sp(v, dem)
                    top = sorted(ks, key=lambda k: -sco[k])[:nt]
                    rec[f"top_{nm}"] = float(np.mean([dem[ks.index(k)] for k in top]))
                cellB.append(rec)
        nd = len(dagar)
        qA = sorted([s for s in cA if cA[s] / nd >= PANELANDEL])
        qB = sorted([s for s in cB if cB[s] / nd >= PANELANDEL])
        res = {"n_paneler": nd, "kvalificerade_A": qA, "kvalificerade_B": qB,
               "panelandel_A": {k: round(v / nd, 3) for k, v in sorted(cA.items(), key=lambda x: -x[1])},
               "panelandel_B": {k: round(v / nd, 3) for k, v in sorted(cB.items(), key=lambda x: -x[1])}}

        # ---- FAMILY A omnibus
        res["FAMILY_A"] = {}
        for mod in ("ET", "XGB"):
            rr = [r for r in rowsA if r["sc"] in qA]
            if len(set(r["sc"] for r in rr)) < 2: res["FAMILY_A"][mod] = {"status": "INSUFFICIENT_POWER"}; continue
            secs = sorted(set(r["sc"] for r in rr)); pid = np.array([r["p"] for r in rr])
            y = np.array([r["ret"] for r in rr]); dv = np.array([r[mod] for r in rr])
            Xc = [np.where(np.array([r["sc"] for r in rr]) == s, dv, 0.0) for s in secs]
            pans = sorted(set(pid)); Xp = [(pid == p).astype(float) for p in pans[1:]]
            X = np.column_stack(Xc + Xp + [np.ones(len(rr))])
            b, V = ols_cluster(y, X, pid)
            Wv, pv, df = wald_lika(b, V, list(range(len(secs))))
            res["FAMILY_A"][mod] = {"omnibus_W": Wv, "omnibus_p": pv, "df": df, "n_obs": len(rr),
                "per_sektor_pp": {s: round(100 * float(b[i]), 3) for i, s in enumerate(secs)}}
        # ---- FAMILY B omnibus
        res["FAMILY_B"] = {}
        cc = [c for c in cellB if c["sc"] in qB and c.get("ic_H0") is not None]
        for mod in ("ET", "XGB"):
            good = [c for c in cc if c.get(f"ic_{mod}") is not None and np.isfinite(c[f"ic_{mod}"]) and np.isfinite(c["ic_H0"])]
            secs = sorted(set(c["sc"] for c in good))
            if len(secs) < 2: res["FAMILY_B"][mod] = {"status": "INSUFFICIENT_POWER"}; continue
            pid = np.array([c["p"] for c in good])
            y = np.array([c[f"ic_{mod}"] - c["ic_H0"] for c in good])
            Xs = [np.array([1.0 if c["sc"] == s else 0.0 for c in good]) for s in secs]
            pans = sorted(set(pid)); Xp = [(pid == p).astype(float) for p in pans[1:]]
            X = np.column_stack(Xs + Xp)
            b, V = ols_cluster(y, X, pid)
            Wv, pv, df = wald_lika(b, V, list(range(len(secs))))
            per = {}
            for s in secs:
                g = [c for c in good if c["sc"] == s]
                per[s] = {"n_celler": len(g),
                          "dIC": round(float(np.mean([c[f"ic_{mod}"] - c["ic_H0"] for c in g])), 4),
                          "IC_H0": round(float(np.mean([c["ic_H0"] for c in g])), 4),
                          f"IC_{mod}": round(float(np.mean([c[f"ic_{mod}"] for c in g])), 4),
                          "dTOP_pp": round(100 * float(np.mean([c[f"top_{mod}"] - c["top_H0"] for c in g])), 3)}
            res["FAMILY_B"][mod] = {"omnibus_W": Wv, "omnibus_p": pv, "df": df, "n_celler": len(good), "per_sektor": per}
        ut["fonster"][wn] = res
        print(f"{wn}: A kval {qA}\n           B kval {qB}", flush=True)
    (UT / "results_industry_exploratory.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=str))
    print("skrivet:", UT / "results_industry_exploratory.json")


if __name__ == "__main__":
    main()
