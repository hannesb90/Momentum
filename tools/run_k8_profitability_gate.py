"""K8 — lönsamhetsgrind. Kör EXAKT den låsta preregistreringen (sha256 73289cc8...)."""
from __future__ import annotations
import importlib.util, json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2=Path("/home/hannesb/momentum_v2"); PIT=V2/"validated/kpi_pit"
OUT=V2/"research_k/k8_profitability_gate_results.json"
COST=0.002; PPY=13.0

spec=importlib.util.spec_from_file_location("h2h",V2/"tools/research_all_6_models_head_to_head.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
core_df,prices,terminal=m.load_data()
returns_map,all_dates=m.execution_engine(core_df,prices,terminal)
vol_map,price_series=m.compute_vols(prices,window=60)
rankings=m.derive_h0_scores(core_df,prices)
eval_dates=sorted(rankings.keys()); anchor=all_dates.index(m.PHASE_ANCHOR_H0)%2

rows=json.loads((PIT/"55_Rorelseresultat_r12.json").read_text())
per=defaultdict(list)
for r in rows: per[r["kod"]].append((r["report_date"],r["v"]))
for k in per: per[k].sort()
EBIT={k:([d for d,_ in v],[x for _,x in v]) for k,v in per.items()}

def ebit_at(kod,dt):
    e=EBIT.get(kod)
    if not e: return None
    d,v=e; i=bisect_right(d,dt)-1
    return v[i] if i>=0 else None

def sim(gate):
    prev,out,nblock=[],[],[]
    for dt in eval_dates:
        sched=all_dates.index(dt)%2==anchor
        raw=rankings[dt]; elig={r["kod"] for r in raw}
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
            if ok and gate:
                e=ebit_at(k,dt)
                if e is not None and e<=0: ok=False          # utesluter ENDAST på positivt bevis
            if ok: sel.append(k)
        nblock.append(len(sel0)-len(sel))
        n=len(sel); vols=np.array([vol_map.get((k,dt),0.25) for k in sel],float)
        if n>0:
            iv=1.0/np.maximum(vols,0.05); w=iv/np.sum(iv)*(n/30.0)
            w=np.clip(w,0.01,0.06); w=w/np.sum(w)*(n/30.0)
        else: w=np.array([])
        rets=np.array([returns_map.get((k,dt),0.0) for k in sel]) if n>0 else np.array([])
        out.append(float(np.sum(w*rets))-COST*turn if n>0 else 0.0)
        prev=sel0
    return np.array(out),np.array(nblock)

def st(x):
    w=np.cumprod(1+x); dd=w/np.maximum.accumulate(w)-1
    return (w[-1]**(PPY/len(x))-1, x.std(ddof=1)*math.sqrt(PPY), float(dd.min()))

base,_=sim(False); gated,nb=sim(True)
cb,vb,db=st(base); cg,vg,dg=st(gated)
d=gated-base; t=d.mean()/d.std(ddof=1)*math.sqrt(len(d)) if d.std(ddof=1)>0 else 0.0
h=len(base)//2
c1b,_,_=st(base[:h]); c1g,_,_=st(gated[:h]); c2b,_,_=st(base[h:]); c2g,_,_=st(gated[h:])

print("="*74); print("K8 — LÖNSAMHETSGRIND (EBIT > 0)"); print("="*74)
print(f"  uteslutna slots/panel: medel {nb.mean():.2f}  max {nb.max()}  paneler utan uteslutning {(nb==0).sum()}/{len(nb)}")
print(f"\n  {'':10s} {'CAGR':>9s} {'vol':>9s} {'MaxDD':>9s}")
print(f"  {'ogrindad':10s} {cb:9.2%} {vb:9.2%} {db:9.2%}")
print(f"  {'grindad':10s} {cg:9.2%} {vg:9.2%} {dg:9.2%}")
print(f"  {'skillnad':10s} {cg-cb:+9.2%} {vg-vb:+9.2%} {dg-db:+9.2%}")
print(f"\n  parvis t på periodskillnad: {t:+.2f}   (krav >= 2.0)")
print(f"  CAGR-skillnad block1 {c1g-c1b:+.2%}   block2 {c2g-c2b:+.2%}")
maxdd_ok=(dg-db)>=0.01; cagr_ok=(cg-cb)>=-0.01; t_ok=t>=2.0; blocks_ok=(c1g-c1b)*(c2g-c2b)>0
if not maxdd_ok or not cagr_ok: cls="INGET STOD"
elif maxdd_ok and cagr_ok and t_ok and blocks_ok: cls="GRIND STODD"
else: cls="SVAGT STOD"
print(f"\n  barer: MaxDD+1pp {maxdd_ok}  CAGR-tak {cagr_ok}  t>=2 {t_ok}  block {blocks_ok}")
print(f"  KLASSIFICERING: {cls}")
json.dump({"version":"SPARK_K8_RESULT_V1","run_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
 "prereg_sha256":json.loads((V2/"research_k/K8_PREREG_FREEZE.json").read_text())["sha256"],
 "ungated":{"cagr":cb,"vol":vb,"maxdd":db},"gated":{"cagr":cg,"vol":vg,"maxdd":dg},
 "t_paired":float(t),"block1_cagr_delta":float(c1g-c1b),"block2_cagr_delta":float(c2g-c2b),
 "mean_blocked_slots":float(nb.mean()),"classification":cls},open(OUT,"w"),ensure_ascii=False,indent=2)
print(f"\nskrev {OUT.name}")
