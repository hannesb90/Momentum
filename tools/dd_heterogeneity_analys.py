"""DD-heterogenitet: OVERALL forst, darefter subgrupper enligt fryst standard."""
from __future__ import annotations
import hashlib, json, math, sys
from pathlib import Path
import numpy as np
from scipy import stats
UT = Path("/home/hannesb/momentum_v2/research_k/dd_heterogeneity_closure")
DD = ["-0.1", "-0.2", "-0.3", "-0.4"]; MIN_EV = 30

def load(wn):
    return [json.loads(l) for l in open(UT / f"holdings_{wn}.jsonl")]

def klust(y, pid):
    """Medelvarde med panelklustrad SE."""
    y = np.asarray(y, float); pid = np.asarray(pid)
    n = len(y); m = float(y.mean()); G = len(np.unique(pid))
    if G < 2: return m, np.nan, np.nan, n, G
    s = np.array([ (y[pid == p] - m).sum() for p in np.unique(pid) ])
    var = (G / (G - 1)) * (s ** 2).sum() / n ** 2
    se = math.sqrt(max(var, 0))
    t = m / se if se > 0 else np.nan
    return m, se, t, n, G

def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: (ps[i] is None, ps[i])); out=[None]*len(ps); run=0.0
    for r,i in enumerate(idx):
        if ps[i] is None: continue
        adj=min(1.0,(len(ps)-r)*ps[i]); run=max(run,adj); out[i]=round(run,5)
    return out

res = {"version":"DD_HETEROGENEITY_ANALYS_V1",
       "prereg_sha256": hashlib.sha256((UT/"DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE_PREREGISTRATION.json").read_bytes()).hexdigest(),
       "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
       "PRIMARY_OVERALL":{}, "SECONDARY_HETEROGENEITY":{}, "MULTIPLICITET":{}}

for wn in ("W1_2014_2019","W2_2020_2026"):
    ev = load(wn); res["PRIMARY_OVERALL"][wn]={}; res["SECONDARY_HETEROGENEITY"][wn]={}
    for lv in DD:
        E=[r for r in ev if lv in r["events"]]
        if not E: continue
        pid=[r["pi"] for r in E]
        blk={"n_events":len(E),"n_paneler":len(set(pid))}
        for h in ("fwd5","fwd10","fwd20","fwd_mid","fwd_slut"):
            y=[r["events"][lv][h] for r in E]
            m,se,t,n,G=klust(y,pid)
            p=2*(1-stats.t.cdf(abs(t),G-1)) if np.isfinite(t) else None
            blk[h]={"medel_pct":round(100*m,3),"se_pct":round(100*se,3),"t":round(float(t),3) if np.isfinite(t) else None,
                    "p":round(p,5) if p is not None else None,
                    "ki95_pct":[round(100*(m-1.96*se),3),round(100*(m+1.96*se),3)],
                    "MDE80_pct":round(100*2.80*se,3)}
        for f in ("ater_entry","ater_peak","positiv_slut"):
            blk[f"P_{f}"]=round(float(np.mean([r["events"][lv][f] for r in E])),4)
        blk["medel_dag_till_event"]=round(float(np.mean([r["events"][lv]["dag"] for r in E])),1)
        ds=[r["events"][lv]["dd_over_sigma"] for r in E if r["events"][lv]["dd_over_sigma"] is not None]
        blk["dd_over_sigma_median"]=round(float(np.median(ds)),3) if ds else None
        res["PRIMARY_OVERALL"][wn][lv]=blk

    # ---- SEKUNDAR: heterogenitet i fwd_slut
    dims={"volatility":lambda r:r["vol_terc"],"size":lambda r:r["size_terc"],
          "sector":lambda r:r["icb"],"profitability":lambda r:(None if r["lonsam"] is None else ("LONSAM" if r["lonsam"] else "OLONSAM")),
          "liquidity":lambda r:r["liq_terc"]}
    for dim,fn in dims.items():
        res["SECONDARY_HETEROGENEITY"][wn][dim]={}
        for lv in DD:
            E=[r for r in ev if lv in r["events"] and fn(r) is not None]
            grp=sorted(set(fn(r) for r in E))
            out={}
            for g in grp:
                S=[r for r in E if fn(r)==g]
                if len(S)<MIN_EV: out[g]={"n":len(S),"status":"NOT_IDENTIFIABLE"}; continue
                y=[r["events"][lv]["fwd_slut"] for r in S]; pid=[r["pi"] for r in S]
                m,se,t,n,G=klust(y,pid)
                out[g]={"n":n,"medel_pct":round(100*m,3),"se_pct":round(100*se,3),
                        "t":round(float(t),3) if np.isfinite(t) else None,
                        "ki95_pct":[round(100*(m-1.96*se),3),round(100*(m+1.96*se),3)],
                        "MDE80_pct":round(100*2.80*se,3),"status":"OK"}
            # interaktion: skillnad mellan ytter grupper
            ok=[g for g in grp if out.get(g,{}).get("status")=="OK"]
            if len(ok)>=2:
                a,b=ok[0],ok[-1]
                Sa=[r for r in E if fn(r)==a]; Sb=[r for r in E if fn(r)==b]
                ya=np.array([r["events"][lv]["fwd_slut"] for r in Sa]); yb=np.array([r["events"][lv]["fwd_slut"] for r in Sb])
                d=float(ya.mean()-yb.mean())
                sed=math.sqrt(out[a]["se_pct"]**2+out[b]["se_pct"]**2)/100
                td=d/sed if sed>0 else np.nan
                out["INTERAKTION"]={"jamfor":[a,b],"diff_pct":round(100*d,3),"se_pct":round(100*sed,3),
                    "t":round(float(td),3) if np.isfinite(td) else None,
                    "p":round(float(2*(1-stats.norm.cdf(abs(td)))),5) if np.isfinite(td) else None}
            res["SECONDARY_HETEROGENEITY"][wn][dim][lv]=out
    # Holm inom familj
    for dim in dims:
        ps=[]; nyck=[]
        for lv in DD:
            it=res["SECONDARY_HETEROGENEITY"][wn][dim].get(lv,{}).get("INTERAKTION")
            if it and it.get("p") is not None: ps.append(it["p"]); nyck.append(lv)
        for lv,pa in zip(nyck,holm(ps)):
            res["SECONDARY_HETEROGENEITY"][wn][dim][lv]["INTERAKTION"]["holm_p"]=pa
        res["MULTIPLICITET"].setdefault(wn,{})[dim]={"n_tester":len(ps),"raa_p":ps,"holm_p":holm(ps)}

(UT/"analys.json").write_text(json.dumps(res,ensure_ascii=False,indent=1))
print("PRIMARY — framatavkastning fran DD-event till innehavsperiodens slut (fwd_slut)\n")
print(f"{'fonster':16}{'DD':6}{'events':>8}{'medel %':>9}{'SE':>7}{'t':>7}{'p':>9}{'KI 95%':>20}{'MDE80':>8}{'P(pos)':>8}")
for wn in res["PRIMARY_OVERALL"]:
    for lv in DD:
        b=res["PRIMARY_OVERALL"][wn].get(lv)
        if not b: continue
        f=b["fwd_slut"]
        print(f"{wn[:14]:16}{lv:6}{b['n_events']:8}{f['medel_pct']:9.2f}{f['se_pct']:7.2f}{str(f['t']):>7}{str(f['p']):>9}[{f['ki95_pct'][0]:+7.2f},{f['ki95_pct'][1]:+7.2f}]{f['MDE80_pct']:8.2f}{b['P_positiv_slut']:8.3f}")
