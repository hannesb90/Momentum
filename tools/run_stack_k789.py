"""Kombinerad stack: V-A + K9-blend (urval) + K8-grind + K7 FCF-overlay (vikt).
DIAGNOSTISK. Ingen registerändring, ingen försegling bruten, ingen challenger."""
from __future__ import annotations
import importlib.util, json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2=Path("/home/hannesb/momentum_v2"); PIT=V2/"validated/kpi_pit"; COST=0.002; PPY=13.0
spec=importlib.util.spec_from_file_location("h2h",V2/"tools/research_all_6_models_head_to_head.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
core_df,prices,terminal=m.load_data()
returns_map,all_dates=m.execution_engine(core_df,prices,terminal)
vol_map,price_series=m.compute_vols(prices,window=60)
rankings=m.derive_h0_scores(core_df,prices)
eval_dates=sorted(rankings.keys()); anchor=all_dates.index(m.PHASE_ANCHOR_H0)%2

def lk(f):
    rows=json.loads((PIT/f"{f}.json").read_text()); per=defaultdict(list)
    for r in rows: per[r["kod"]].append((r["report_date"],r["v"]))
    for k in per: per[k].sort()
    return {k:([d for d,_ in v],[x for _,x in v]) for k,v in per.items()}
def at(L,kod,dt):
    e=L.get(kod)
    if not e: return None
    d,v=e; i=bisect_right(d,dt)-1
    return v[i] if i>=0 else None
EBIT=lk("55_Rorelseresultat_r12"); VM=lk("30_Vinstmarginal_r12"); FM=lk("24_FCF_Marginal_r12")

def pctrank(v):
    n=len(v)
    if n<2: return np.full(n,.5)
    o=np.argsort(v,kind="mergesort"); r=np.empty(n,float); i=0
    while i<n:
        j=i
        while j+1<n and v[o[j+1]]==v[o[i]]: j+=1
        r[o[i:j+1]]=(i+j)/2.; i=j+1
    return r/(n-1)

def sim(use_k9,use_k8,use_k7):
    prev,out=[],[]
    for dt in eval_dates:
        sched=all_dates.index(dt)%2==anchor
        raw=rankings[dt]
        if use_k9:                                   # K9: ranka om urvalet
            kods=[r["kod"] for r in raw]; sc=np.array([r["score"] for r in raw],float)
            gap=np.array([ (at(VM,k,dt) - at(FM,k,dt)) if (at(VM,k,dt) is not None and at(FM,k,dt) is not None)
                           else np.nan for k in kods])
            ok=np.isfinite(gap)
            blend=pctrank(sc).copy()
            if ok.sum()>=20:
                b=0.5*pctrank(sc[ok])+0.5*pctrank(-gap[ok]); blend[ok]=b
            order=np.argsort(-blend,kind="mergesort")
            raw=[raw[i] for i in order]
        elig={r["kod"] for r in raw}
        sel0=[r["kod"] for r in raw[:30]] if (sched or not prev) else [k for k in prev if k in elig]
        if not (sched or not prev) and len(sel0)<30:
            sel0+=[r["kod"] for r in raw if r["kod"] not in sel0][:30-len(sel0)]
        turn=0.0 if not prev else 1.0-len(set(sel0)&set(prev))/len(sel0)
        sel=[]
        for k in sel0:
            ok=True
            if k in price_series:
                ds,adj=price_series[k]
                i=next((j for j in range(len(ds)-1,-1,-1) if ds[j]<=dt),None)
                if i is not None and i>=200 and adj[i]<float(np.mean(adj[i-200:i])): ok=False
            if ok and use_k8:
                e=at(EBIT,k,dt)
                if e is not None and e<=0: ok=False
            if ok: sel.append(k)
        n=len(sel); vols=np.array([vol_map.get((k,dt),0.25) for k in sel],float)
        if n>0:
            iv=1.0/np.maximum(vols,0.05); w=iv/np.sum(iv)*(n/30.0)
            w=np.clip(w,0.01,0.06); w=w/np.sum(w)*(n/30.0)
            if use_k7:                               # K7: 0.75x om FCF-marginal i nedre tercilen
                fv=np.array([at(FM,k,dt) if at(FM,k,dt) is not None else np.nan for k in sel])
                good=np.isfinite(fv)
                mult=np.ones(n)
                if good.sum()>=6:
                    cut=np.nanpercentile(fv[good],33.3)
                    mult[good & (fv<=cut)]=0.75
                w=w*mult; w=np.clip(w,0.01,0.06); w=w/np.sum(w)*(n/30.0)
        else: w=np.array([])
        rets=np.array([returns_map.get((k,dt),0.0) for k in sel]) if n>0 else np.array([])
        out.append(float(np.sum(w*rets))-COST*turn if n>0 else 0.0)
        prev=sel0
    return np.array(out)

def st(x):
    w=np.cumprod(1+x); dd=w/np.maximum.accumulate(w)-1
    return (w[-1]**(PPY/len(x))-1, x.std(ddof=1)*math.sqrt(PPY), float(dd.min()))

arms={"V-A (referens)":(False,False,False),
      "+K8 grind":(False,True,False),
      "+K8 +K7":(False,True,True),
      "+K8 +K7 +K9 (full stack)":(True,True,True)}
print("="*84); print("KOMBINERAD STACK — diagnostisk, ingen registerändring"); print("="*84)
print(f"  {'arm':28s} {'CAGR':>9s} {'vol':>9s} {'MaxDD':>9s} {'Sharpe*':>9s}")
res={}
base=None
for name,(k9,k8,k7) in arms.items():
    r=sim(k9,k8,k7); c,v,d=st(r)
    if base is None: base=r
    sh=(c-0.0224)/v
    print(f"  {name:28s} {c:9.2%} {v:9.2%} {d:9.2%} {sh:9.2f}")
    res[name]={"cagr":c,"vol":v,"maxdd":d,"sharpe_vs_rf":sh}
    if name!="V-A (referens)":
        dd=r-base; t=dd.mean()/dd.std(ddof=1)*math.sqrt(len(dd)) if dd.std(ddof=1)>0 else 0
        h=len(r)//2
        c1,_,_=st(r[:h]); c1b,_,_=st(base[:h]); c2,_,_=st(r[h:]); c2b,_,_=st(base[h:])
        res[name].update({"t_paired_vs_VA":float(t),"block1_delta":float(c1-c1b),"block2_delta":float(c2-c2b)})
print("\n  * Sharpe mot riskfritt 2,24 %/år (periodens snitt)\n")
print(f"  {'arm':28s} {'t vs V-A':>9s} {'block1':>9s} {'block2':>9s}")
for n,v in res.items():
    if "t_paired_vs_VA" in v:
        print(f"  {n:28s} {v['t_paired_vs_VA']:+9.2f} {v['block1_delta']:+9.2%} {v['block2_delta']:+9.2%}")
json.dump({"version":"STACK_K789_DIAGNOSTIC_V1","run_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
 "note":"DIAGNOSTIC ONLY. Registry not modified. Seal not broken. No challenger created.",
 "arms":res},open(V2/"research_k/stack_k789_diagnostic.json","w"),ensure_ascii=False,indent=2)
print("\nskrev stack_k789_diagnostic.json")
