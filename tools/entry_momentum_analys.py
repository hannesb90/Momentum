from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
from scipy import stats
UT = Path("/home/hannesb/momentum_v2/research_k/entry_momentum_saturation")
MIN = 30

def load(wn): return [json.loads(l) for l in open(UT / f"entry_{wn}.jsonl")]

def dm(x, pid):
    x = np.asarray(x, float); o = x.copy()
    for p in np.unique(pid): m = pid == p; o[m] = x[m] - x[m].mean()
    return o

def ols_cl(y, X, pid):
    XtX = X.T @ X
    if np.linalg.cond(XtX) > 1e12: return None, None
    b = np.linalg.solve(XtX, X.T @ y); e = y - X @ b; Xi = np.linalg.inv(XtX)
    meat = np.zeros_like(XtX)
    for p in np.unique(pid):
        m = pid == p; s = X[m].T @ e[m]; meat += np.outer(s, s)
    G = len(np.unique(pid)); n, k = X.shape
    return b, Xi @ ((G/(G-1))*((n-1)/(n-k))*meat) @ Xi

def sat(rows, mkey, wins=False):
    R = [r for r in rows if r.get(mkey) is not None]
    if len(R) < MIN: return {"status": "NOT_IDENTIFIABLE", "n": len(R)}
    pid = np.array([r["pi"] for r in R]); M = np.array([r[mkey] for r in R], float)
    y = np.array([r["R_slut"] for r in R], float)
    if wins:
        for p in np.unique(pid):
            m = pid == p
            if m.sum() >= 5:
                lo, hi = np.percentile(M[m], [1, 99]); M[m] = np.clip(M[m], lo, hi)
    X = np.column_stack([dm(M, pid), dm(M**2, pid)])
    b, V = ols_cl(dm(y, pid), X, pid)
    if b is None: return {"status": "SINGULAR", "n": len(R)}
    out = {"status": "OK", "n": len(R), "n_paneler": int(len(np.unique(pid)))}
    for i, nm in enumerate(("b1_linjar", "b2_kvadrat")):
        se = math.sqrt(V[i, i]); t = b[i]/se if se > 0 else float("nan")
        out[nm] = {"b": round(float(b[i]), 5), "se": round(se, 5),
                   "t": round(float(t), 3) if np.isfinite(t) else None,
                   "p": round(float(2*(1-stats.norm.cdf(abs(t)))), 5) if np.isfinite(t) else None,
                   "ki95": [round(float(b[i]-1.96*se), 5), round(float(b[i]+1.96*se), 5)]}
    return out

def klust(y, pid):
    y = np.asarray(y, float); pid = np.asarray(pid); n = len(y); m = float(y.mean())
    G = len(np.unique(pid))
    if G < 2 or n == 0: return m, float("nan")
    s = np.array([(y[pid == p] - m).sum() for p in np.unique(pid)])
    return m, math.sqrt(max((G/(G-1))*(s**2).sum()/n**2, 0))

def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: (ps[i] is None, ps[i])); o=[None]*len(ps); run=0.0
    for r,i in enumerate(idx):
        if ps[i] is None: continue
        a=min(1.0,(len(ps)-r)*ps[i]); run=max(run,a); o[i]=round(run,5)
    return o

res = {"version":"ENTRY_MOMENTUM_ANALYS_V1",
  "prereg_sha256": hashlib.sha256((UT/"ENTRY_MOMENTUM_SATURATION_PREREGISTRATION.json").read_bytes()).hexdigest(),
  "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
  "DEL4_FORDELNING":{}, "DEL16_POWER":{}, "DEL5_SATURATION":{}, "DEL6_KVANTILER":{},
  "INTERAKTIONER":{}, "MULTIPLICITET":{}}

for wn in ("W1_2014_2019","W2_2020_2026"):
    ev = load(wn); pid = [r["pi"] for r in ev]; M = np.array([r["m12"] for r in ev])
    res["DEL4_FORDELNING"][wn] = {"OVERALL": {"n": len(M), "mean": round(float(M.mean()),4),
        "median": round(float(np.median(M)),4), "sd": round(float(M.std(ddof=1)),4),
        **{f"p{q}": round(float(np.percentile(M,q)),4) for q in (10,25,50,75,90,95,99)},
        "min": round(float(M.min()),4), "max": round(float(M.max()),4)}}
    for dim,fn in (("size",lambda r:r["size_terc"]),("vol",lambda r:r["vol_terc"]),("sektor",lambda r:r["icb"])):
        d={}
        for g in sorted(set(fn(r) for r in ev if fn(r))):
            m=np.array([r["m12"] for r in ev if fn(r)==g])
            if len(m)<MIN: d[g]={"n":len(m),"status":"NOT_IDENTIFIABLE"}; continue
            d[g]={"n":len(m),"median":round(float(np.median(m)),4),"p90":round(float(np.percentile(m,90)),4),
                  "p99":round(float(np.percentile(m,99)),4),"max":round(float(m.max()),4)}
        res["DEL4_FORDELNING"][wn][dim]=d
    res["DEL16_POWER"][wn]={"andel_over": {f"+{int(x*100)}%": round(float(np.mean(M>x)),4) for x in (.2,.3,.4,.5,.75,1.0)},
        "antal_over": {f"+{int(x*100)}%": int((M>x).sum()) for x in (.2,.3,.4,.5,.75,1.0)}}
    # ---- DEL 5
    res["DEL5_SATURATION"][wn]={}
    for lbl,mk in (("m12_raw","m12"),("m18_raw","m18"),("m12_vol","m12_vol"),("m12_sektorpct","m12_sektorpct")):
        raw=sat(ev,mk,False); win=sat(ev,mk,True)
        d={"oklippt":raw,"vinsoriserad":win}
        if raw.get("status")=="OK" and win.get("status")=="OK":
            sr=np.sign(raw["b2_kvadrat"]["b"]); sw=np.sign(win["b2_kvadrat"]["b"])
            d["b2_samma_tecken"]=bool(sr==sw)
            d["KVADRAT_DOM"]="OK" if sr==sw else "NOT_IDENTIFIABLE"
        res["DEL5_SATURATION"][wn][lbl]=d
    # ---- DEL 6 kvintiler
    res["DEL6_KVANTILER"][wn]={}
    for lbl,mk in (("m12_raw","m12"),("m12_vol","m12_vol"),("m12_sektorpct","m12_sektorpct")):
        R=[r for r in ev if r.get(mk) is not None]
        lab={}
        for p in set(r["pi"] for r in R):
            S=sorted([r for r in R if r["pi"]==p], key=lambda r:r[mk])
            for j,r in enumerate(S): lab[id(r)]=f"Q{min(5,5*j//max(1,len(S))+1)}"
        q={}
        for g in ("Q1","Q2","Q3","Q4","Q5"):
            S=[r for r in R if lab[id(r)]==g]
            if len(S)<MIN: q[g]={"n":len(S),"status":"NOT_IDENTIFIABLE"}; continue
            m,se=klust([r["R_slut"] for r in S],[r["pi"] for r in S])
            q[g]={"n":len(S),"medel_pct":round(100*m,3),"se_pct":round(100*se,3),
                  "median_m":round(float(np.median([r[mk] for r in S])),4)}
        res["DEL6_KVANTILER"][wn][lbl]=q
    # ---- interaktioner
    res["INTERAKTIONER"][wn]={}; res["MULTIPLICITET"][wn]={}
    for dim,fn in (("size",lambda r:r["size_terc"]),("volatility",lambda r:r["vol_terc"]),
                   ("sector",lambda r:r["icb"]),
                   ("profitability",lambda r:(None if r["lonsam"] is None else ("LONSAM" if r["lonsam"] else "OLONSAM")))):
        out={}; ps=[]; ny=[]
        for g in sorted(set(fn(r) for r in ev if fn(r) is not None)):
            S=[r for r in ev if fn(r)==g]
            o=sat(S,"m12",True)
            if o.get("status")!="OK": out[g]={"n":len(S),"status":"NOT_IDENTIFIABLE"}; continue
            out[g]={"n":o["n"],"b1":o["b1_linjar"]["b"],"b1_t":o["b1_linjar"]["t"],
                    "b2":o["b2_kvadrat"]["b"],"b2_t":o["b2_kvadrat"]["t"],"b2_p":o["b2_kvadrat"]["p"],
                    "b2_ki":o["b2_kvadrat"]["ki95"],"status":"OK"}
            ps.append(o["b2_kvadrat"]["p"]); ny.append(g)
        for g,pa in zip(ny,holm(ps)): out[g]["b2_holm_p"]=pa
        res["INTERAKTIONER"][wn][dim]=out
        res["MULTIPLICITET"][wn][dim]={"n":len(ps),"raa_p":ps,"holm_p":holm(ps)}

(UT/"analys.json").write_text(json.dumps(res,ensure_ascii=False,indent=1))
print("DEL 4 — momentumfordelning bland INNEHAVEN (m12)\n")
print(f"{'fonster':13}{'n':>6}{'median':>9}{'p75':>9}{'p90':>9}{'p95':>9}{'p99':>9}{'max':>9}")
for wn,d in res["DEL4_FORDELNING"].items():
    o=d["OVERALL"]; print(f"{wn[:11]:13}{o['n']:6}{o['median']:9.3f}{o['p75']:9.3f}{o['p90']:9.3f}{o['p95']:9.3f}{o['p99']:9.3f}{o['max']:9.2f}")
print("\nDEL 16 — andel innehav over niva")
for wn,d in res["DEL16_POWER"].items():
    print(f"  {wn}: " + "  ".join(f"{k} {v:.3f} (n={d['antal_over'][k]})" for k,v in d["andel_over"].items()))
print("\nDEL 5 — SATURATION, kvadratterm b2 (vinsoriserad)")
for wn,d in res["DEL5_SATURATION"].items():
    for lbl,v in d.items():
        w=v.get("vinsoriserad",{})
        if w.get("status")!="OK": print(f"  {wn[:11]} {lbl:14} {w.get('status')}"); continue
        b2=w["b2_kvadrat"]; b1=w["b1_linjar"]
        print(f"  {wn[:11]} {lbl:14} n={w['n']:5} b1={b1['b']:+8.5f}(t={b1['t']:+6.2f})  b2={b2['b']:+9.6f}(t={b2['t']:+6.2f}, p={b2['p']})  tecken_stabilt={v.get('b2_samma_tecken')}")
