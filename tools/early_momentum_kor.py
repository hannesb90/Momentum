"""EARLY_MOMENTUM_ACCELERATION_AUDIT. DIAGNOSTIK. A = retrospektiv, B = forward-eligible."""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/early_momentum_audit"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "EARLY_MOMENTUM_ACCELERATION_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
IX = {n: i for i, n in enumerate(R.NAMES)} if hasattr(R, "NAMES") else None
NTOP, MIN = 20, 30

def dm(x, pid):
    x = np.asarray(x, float); o = x.copy()
    for p in np.unique(pid): m = pid == p; o[m] = x[m] - x[m].mean()
    return o

def ols(y, X, pid):
    XtX = X.T @ X; kond = float(np.linalg.cond(XtX))
    if kond > 1e12: return None, None, kond
    b = np.linalg.solve(XtX, X.T @ y); e = y - X @ b; Xi = np.linalg.inv(XtX)
    meat = np.zeros_like(XtX)
    for p in np.unique(pid):
        m = pid == p; s = X[m].T @ e[m]; meat += np.outer(s, s)
    Gn = len(np.unique(pid)); n, k = X.shape
    return b, Xi @ ((Gn/(Gn-1))*((n-1)/(n-k))*meat) @ Xi, kond

def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: (ps[i] is None, ps[i])); o=[None]*len(ps); run=0.0
    for r,i in enumerate(idx):
        if ps[i] is None: continue
        a=min(1.0,(len(ps)-r)*ps[i]); run=max(run,a); o[i]=round(run,5)
    return o

def bygg(wn):
    W = R.load_window(wn); rk, P = W["rankings"], W["paneler"]
    obs = R.build_obs(W)
    names = R.NAMES
    ix = {n: i for i, n in enumerate(names)}
    # rank_pct per panel
    rp = {}
    for d in P:
        rows = rk.get(d, []); n = len(rows)
        for j, r in enumerate(rows, 1): rp[(r["kod"], d)] = 1.0 - (j-1)/max(1, n-1)
    pidx = {d: i for i, d in enumerate(P)}
    ut = []
    for o in obs:
        if o["y"] is None: continue
        d = o["date"]; i = pidx[d]; k = o["kod"]; x = o["x"]
        if i < 4: continue
        # rank_slope = rank_pct(t-1) - rank_pct(t-3), relativt DENNA panel
        r1 = rp.get((k, P[i-1])); r3 = rp.get((k, P[i-3]))
        slope = (r1 - r3) if (r1 is not None and r3 is not None) else None
        rec = {"panel": d, "pi": i, "kod": k, "y": o["y"], "rank_pct": rp.get((k, d)), "rank_slope": slope,
               "bana": [rp.get((k, P[i-j])) for j in (4, 3, 2, 1, 0)]}
        for nm in ("h0_score", "h0_rank", "mom4", "mom13", "mom26", "mom52", "mom12_1", "accel13",
                   "vol13", "vol52", "trend_consistency52"):
            v = x[ix[nm]] if nm in ix else None
            rec[nm] = None if (v is None or not np.isfinite(v)) else float(v)
        nr = G.nasdaq_rad(k, None, d) or {}
        rec["mc"] = nr.get("market_cap"); rec["icb"] = CWMAP.get(nr.get("industry"))
        rec["rebalans"] = (i % 2 == 0)
        rec["kopt"] = bool(i % 2 == 0 and rp.get((k, d)) is not None and
                           k in [r["kod"] for r in rk[d]][:NTOP])
        ut.append(rec)
    return ut, P

def analys(rows, wn):
    R_ = [r for r in rows if r["y"] is not None and r["rank_pct"] is not None and r["rank_slope"] is not None
          and r["mom52"] is not None and r["mom13"] is not None and r["accel13"] is not None]
    pid = np.array([r["pi"] for r in R_]); y = dm([r["y"] for r in R_], pid)
    col = {n: dm([r[n] for r in R_], pid) for n in ("rank_pct","rank_slope","accel13","mom52","mom13","vol13")}
    out = {"n": len(R_), "n_paneler": int(len(np.unique(pid)))}
    def fit(nms):
        X = np.column_stack([col[n] for n in nms]); b, V, kond = ols(y, X, pid)
        if b is None: return {"status":"NOT_IDENTIFIABLE","kondition":kond}
        e = y - X @ b; r2 = 1 - float(e@e)/float(y@y)
        d = {"status":"OK","R2":round(r2,6),"kondition":round(kond,1)}
        for i, n in enumerate(nms):
            se = math.sqrt(V[i,i]); t = b[i]/se
            d[n] = {"b": round(float(b[i]),6), "t": round(float(t),3),
                    "p": round(float(2*(1-stats.norm.cdf(abs(t)))),5),
                    "ki95":[round(float(b[i]-1.96*se),6), round(float(b[i]+1.96*se),6)]}
        return d
    out["rank_familj"] = {"M1": fit(["rank_pct"]), "M2": fit(["rank_pct","rank_slope"]),
                          "M3": fit(["rank_pct","rank_slope","accel13"])}
    out["momentum_familj"] = {"N1": fit(["mom52"]), "N2": fit(["mom52","mom13"]),
                              "N3": fit(["mom52","mom13","accel13"])}
    out["multivariat"] = fit(["mom52","mom13","accel13","rank_pct","rank_slope","vol13"])
    # rank-IC per signal
    out["rank_IC"] = {}
    for n in ("rank_pct","rank_slope","accel13","mom13","mom52"):
        ics=[]
        for p in np.unique(pid):
            m = pid==p
            if m.sum() < 20: continue
            a=np.array([R_[i][n] for i in range(len(R_)) if pid[i]==p])
            b_=np.array([R_[i]["y"] for i in range(len(R_)) if pid[i]==p])
            if a.std()==0 or b_.std()==0: continue
            ics.append(float(stats.spearmanr(a,b_)[0]))
        if ics:
            m=float(np.mean(ics)); se=float(np.std(ics,ddof=1)/math.sqrt(len(ics)))
            out["rank_IC"][n]={"medel":round(m,4),"se":round(se,4),"t":round(m/se,3) if se>0 else None,"n_paneler":len(ics)}
    # kvintilspread for accel13 och rank_slope
    out["kvintiler"]={}
    for n in ("accel13","rank_slope"):
        lab={}
        for p in np.unique(pid):
            S=sorted([i for i in range(len(R_)) if pid[i]==p], key=lambda i:R_[i][n])
            for j,i in enumerate(S): lab[i]=min(5,5*j//max(1,len(S))+1)
        q={}
        for g in range(1,6):
            S=[i for i in range(len(R_)) if lab[i]==g]
            if len(S)<MIN: q[f"Q{g}"]={"n":len(S),"status":"NOT_IDENTIFIABLE"}; continue
            yy=np.array([R_[i]["y"] for i in S]); pp=pid[S]
            m=float(yy.mean()); Gn=len(np.unique(pp))
            s=np.array([(yy[pp==p]-m).sum() for p in np.unique(pp)])
            se=math.sqrt(max((Gn/(Gn-1))*(s**2).sum()/len(yy)**2,0))
            q[f"Q{g}"]={"n":len(S),"medel_pct":round(100*m,3),"se_pct":round(100*se,3)}
        out["kvintiler"][n]=q
    return out, R_

def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    res = {"version":"EARLY_MOMENTUM_AUDIT_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "prereg_sha256": sha(UT / "EARLY_MOMENTUM_ACCELERATION_PREREGISTRATION.json"),
           "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
           "B_FORWARD_ELIGIBLE":{}, "A_RETROSPEKTIV":{}, "LEAD":{}, "HETEROGENITET":{}, "MULTIPLICITET":{}}
    for wn in ("W1_2014_2019","W2_2020_2026"):
        rows, P = bygg(wn)
        with open(UT / f"obs_{wn}.jsonl","w") as f:
            for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        b_, R_ = analys(rows, wn)
        res["B_FORWARD_ELIGIBLE"][wn] = b_
        # ---- A: retrospektiv bana for faktiska kop mot kontroll B (rank 21-30)
        kop=[r for r in rows if r["kopt"]]
        ktrl=[r for r in rows if r["rebalans"] and not r["kopt"] and r["rank_pct"] is not None
              and r["h0_rank"] is not None and 21 <= r["h0_rank"] <= 30]
        def prof(S):
            o={}
            for n in ("rank_pct","rank_slope","accel13","mom13","mom52","vol13"):
                v=[r[n] for r in S if r.get(n) is not None]
                o[n]=round(float(np.mean(v)),4) if v else None
            bn=[r["bana"] for r in S if all(x is not None for x in r["bana"])]
            o["rank_pct_bana_t4_till_t0"]=[round(float(np.mean([b[j] for b in bn])),4) for j in range(5)] if bn else None
            o["n"]=len(S)
            return o
        res["A_RETROSPEKTIV"][wn]={"KOP":prof(kop),"KONTROLL_B_rank21_30":prof(ktrl),
            "STATUS":"DESKRIPTIV — utfallsbetingad, far ej ligga till grund for hypotes"}
        print(f"{wn}: B n={b_['n']} paneler={b_['n_paneler']} | A kop={len(kop)} kontrollB={len(ktrl)}", flush=True)
    (UT/"analys.json").write_text(json.dumps(res,ensure_ascii=False,indent=1))
    print("skrivet:", UT/"analys.json")

if __name__ == "__main__":
    main()
