"""PIT_ICB_HETEROGENEITY — FAMILY A (inom H0 topp-30) och FAMILY B (hela universumet).

Forregistrering: research_k/pit_icb_heterogeneity/preregistration.json
ICB anvands enbart for POPULATIONSSTRATIFIERING, aldrig som feature.
INGA MODELLER TRANAS.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/pit_icb_heterogeneity"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
NSEL, MIN_A, MIN_B, PANELANDEL, TOPPCT = 20, 5, 8, 0.5, 0.10
SEED = 20260815


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def within(x, pid):
    x = np.asarray(x, float); o = x.copy()
    for p in np.unique(pid):
        m = pid == p; o[m] = x[m] - x[m].mean()
    return o


def ols_cluster(y, X, pid):
    b = np.linalg.solve(X.T @ X, X.T @ y); e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X); meat = np.zeros_like(X.T @ X)
    for p in np.unique(pid):
        m = pid == p; s = X[m].T @ e[m]; meat += np.outer(s, s)
    Gn = len(np.unique(pid)); n, k = X.shape
    V = XtXi @ ((Gn / (Gn - 1)) * ((n - 1) / (n - k)) * meat) @ XtXi
    return b, V


def wald(b, V, idx):
    """Test att koefficienterna i idx alla ar lika (skillnad mot den forsta)."""
    if len(idx) < 2: return None, None, 0
    Rm = np.zeros((len(idx) - 1, len(b)))
    for i, j in enumerate(idx[1:]):
        Rm[i, j] = 1.0; Rm[i, idx[0]] = -1.0
    Rb = Rm @ b; M = Rm @ V @ Rm.T
    try: W = float(Rb @ np.linalg.solve(M, Rb))
    except np.linalg.LinAlgError: return None, None, 0
    from scipy import stats
    df = len(idx) - 1
    return round(W, 3), round(float(1 - stats.chi2.cdf(W, df)), 5), df


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "PIT_ICB_HETEROGENEITY_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True,
          "icb_anvandning": "POPULATIONSSTRATIFIERING", "fonster": {}}
    KVAL = {}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]

        def nas(k, d, f):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            v = r_.get(f) if r_ else None
            return float(v) if v else np.nan

        def sup(k, d):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            return (r_.get("supersector") if r_ else None) or None

        def vol60(k, d):
            i = idx(k, d)
            if i is None or i < 61: return np.nan
            _, v = ser[k]; r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return float(np.std(r) * math.sqrt(252))

        # ---------- bygg cell-data ----------
        rowsA, cellB = [], []
        cntA, cntB = defaultdict(int), defaultdict(int)
        for pi, d in enumerate(dagar):
            u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
            h0s = {r["kod"]: r["score"] for r in rk[d]}
            s_of = {k: sup(k, d) for k in u}
            # FAMILY A
            pool = [k for k in [r["kod"] for r in rk[d]][:30] if (k, d) in rm]
            selA = {"H0": set(pool[:NSEL])}
            for m, nm in (("EXTRATREES", "ET"), ("XGBOOST", "XGB")):
                s = preds[m].get(d, {})
                selA[nm] = set(sorted(pool, key=lambda k: (-s.get(k, -1e18), k))[:NSEL])
            gsA = defaultdict(list)
            for k in pool:
                if s_of.get(k): gsA[s_of[k]].append(k)
            for sc, ks in gsA.items():
                if len(ks) < MIN_A: continue
                cntA[sc] += 1
                for k in ks:
                    rowsA.append({"p": pi, "sc": sc, "ret": rm[(k, d)],
                                  "H0": 1.0 if k in selA["H0"] else 0.0,
                                  "ET": 1.0 if k in selA["ET"] else 0.0,
                                  "XGB": 1.0 if k in selA["XGB"] else 0.0,
                                  "lmc": math.log1p(nas(k, d, "market_cap")) if np.isfinite(nas(k, d, "market_cap")) else np.nan,
                                  "vol": vol60(k, d), "spr": nas(k, d, "avg_closing_spread"),
                                  "vel": nas(k, d, "turnover_velocity")})
            # FAMILY B
            gsB = defaultdict(list)
            for k in u:
                if s_of.get(k): gsB[s_of[k]].append(k)
            for sc, ks in gsB.items():
                if len(ks) < MIN_B: continue
                cntB[sc] += 1
                ret = np.array([rm[(k, d)] for k in ks])
                dem = ret - ret.mean()          # demeanas inom sektor-panel (DEL 11)
                rec = {"p": pi, "sc": sc, "n": len(ks)}
                nt = max(3, int(round(TOPPCT * len(ks))))
                for nm, sco in (("H0", {k: h0s[k] for k in ks}),
                                ("ET", {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in ks}),
                                ("XGB", {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in ks})):
                    v = [sco[k] for k in ks]
                    if not np.all(np.isfinite(v)): rec[f"ic_{nm}"] = np.nan; rec[f"top_{nm}"] = np.nan; continue
                    rec[f"ic_{nm}"] = sp(v, dem)
                    top = sorted(ks, key=lambda k: -sco[k])[:nt]
                    rec[f"top_{nm}"] = float(np.mean([dem[ks.index(k)] for k in top]))
                cellB.append(rec)
        KVAL[wn] = {"A": {k: v / len(dagar) for k, v in cntA.items()},
                    "B": {k: v / len(dagar) for k, v in cntB.items()}}
        ut["fonster"][wn] = {"n_paneler": len(dagar), "rowsA": len(rowsA), "cellB": len(cellB),
                             "panelandel_A": KVAL[wn]["A"], "panelandel_B": KVAL[wn]["B"]}
        np.save(UT / f"_tmp_{wn}.npy", np.array([0]))
        (UT / f"_rowsA_{wn}.json").write_text(json.dumps(rowsA))
        (UT / f"_cellB_{wn}.json").write_text(json.dumps(cellB))
        print(f"{wn}: {len(dagar)} paneler, FAMILY A {len(rowsA)} namn-obs, FAMILY B {len(cellB)} sektor-paneler", flush=True)

    # ---------- kvalifikation: >=50 % av panelerna i BADA fonstren ----------
    W1, W2 = "W1_2014_2019", "W2_2020_2026"
    qualA = sorted([s for s in KVAL[W1]["A"] if KVAL[W1]["A"].get(s, 0) >= PANELANDEL and KVAL[W2]["A"].get(s, 0) >= PANELANDEL])
    qualB = sorted([s for s in KVAL[W1]["B"] if KVAL[W1]["B"].get(s, 0) >= PANELANDEL and KVAL[W2]["B"].get(s, 0) >= PANELANDEL])
    ut["kvalificerade"] = {"FAMILY_A": qualA, "FAMILY_B": qualB,
        "FAMILY_A_status": "OK" if len(qualA) >= 3 else "NOT_IDENTIFIABLE_INSUFFICIENT_POWER",
        "FAMILY_B_status": "OK" if len(qualB) >= 3 else "NOT_IDENTIFIABLE_INSUFFICIENT_POWER",
        "alla_supersektorer_A": {w: {k: round(v, 3) for k, v in sorted(KVAL[w]["A"].items(), key=lambda x: -x[1])} for w in KVAL},
        "alla_supersektorer_B": {w: {k: round(v, 3) for k, v in sorted(KVAL[w]["B"].items(), key=lambda x: -x[1])} for w in KVAL}}
    print(f"\nKVALIFICERADE supersektorer: FAMILY A {len(qualA)} {qualA}  ->  {ut['kvalificerade']['FAMILY_A_status']}")
    print(f"                             FAMILY B {len(qualB)} {qualB}  ->  {ut['kvalificerade']['FAMILY_B_status']}")
    (UT / "results_step1.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results_step1.json")


if __name__ == "__main__":
    main()
