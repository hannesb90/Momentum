from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import stats
V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2/"tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2/"research_k/delayed_detection_audit"
_g = importlib.util.spec_from_file_location("G", V2/"tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2/"tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
NTOP, STAB = 20, 5

def kl(y,pid):
    y=np.asarray(y,float); pid=np.asarray(pid); n=len(y)
    if n==0: return float('nan'),float('nan')
    m=float(y.mean()); Gn=len(np.unique(pid))
    if Gn<2: return m,float('nan')
    s=np.array([(y[pid==p]-m).sum() for p in np.unique(pid)])
    return m, math.sqrt(max((Gn/(Gn-1))*(s**2).sum()/n**2,0))

res={"version":"DELAYED_DETECTION_ANALYS_V1",
     "plan_sha256": hashlib.sha256((UT/"DELAYED_DETECTION_PLAN.json").read_bytes()).hexdigest(),
     "DEL15":"PASS 1.0000 universum/top20/full ordning i bada fonstren",
     "DEL17_SAMPLING":{}, "DEL22_TAXONOMI":{}, "DEL9_10_OWNERSHIP":{}, "DEL23_STABILITET":{},
     "DEL19_PRE_ENTRY_RETURN":{}, "DEL18_FUTURE_X_DELAY":{}, "DEL20_PHASE":{}, "DEL28_FALSE_TWINS":{},
     "DEL4_ABSOLUT_RANK":{}, "DEL30_HETEROGENITET":{}, "DEL26_LEDGER_TOPP":{}}

for wn in ("W1_2014_2019","W2_2020_2026"):
    W=R.load_window(wn); rk,P,ser=W["rankings"],W["paneler"],W["serie"]
    obs=R.build_obs(W); ob={(o["kod"],o["date"]):o for o in obs}
    dtop=json.load(open(UT/f"daglig_top20_{wn}.json"))
    drank=json.load(open(UT/f"daglig_rank_{wn}.json"))
    dagar=sorted(dtop.keys())
    didx={d:i for i,d in enumerate(dagar)}
    top20={d:[r["kod"] for r in rk[d]][:NTOP] for d in P}
    rankp={}
    for d in P:
        rows=rk.get(d,[]); n=len(rows)
        for j,r in enumerate(rows,1): rankp[(r["kod"],d)]=(j,1.0-(j-1)/max(1,n-1))
    # ---- agandeperioder ur rebalanspaneler
    reb=[i for i in range(len(P)) if i%2==0]
    own=defaultdict(list)   # kod -> lista av (start_reb_idx, slut_reb_idx)
    for k in ser:
        cur=None
        for ri,i in enumerate(reb):
            inn = k in top20[P[i]]
            if inn and cur is None: cur=ri
            elif not inn and cur is not None: own[k].append((cur,ri-1)); cur=None
        if cur is not None: own[k].append((cur,len(reb)-1))
    E=[]
    for ri,i in enumerate(reb):
        if i+2>=len(P) or ri==0: continue
        forra=set(top20[P[i-2]])
        for k in top20[P[i]]:
            if k in forra: continue
            o=ob.get((k,P[i]))
            if o is None or o["y"] is None: continue
            ed=None
            ds,_=ser[k] if k in ser else (None,None)
            # faktisk entrydag = T+1 efter panelen
            j=int(np.searchsorted(ds, np.datetime64(P[i]), side="right")) if ds is not None else None
            if j is None or j>=len(ds): continue
            ed=str(np.datetime64(ds[j],"D"))
            if ed not in didx: continue
            # intervallet sedan foregaende rebalanspanel
            pd_=P[i-2]
            jp=int(np.searchsorted(ds, np.datetime64(pd_), side="right"))
            sd=str(np.datetime64(ds[jp],"D")) if jp<len(ds) else None
            fenster=[d for d in dagar if (sd is None or d>=sd) and d<ed]
            first=None
            for d in fenster:
                if k in dtop[d]: first=d; break
            delay = (didx[ed]-didx[first]) if first else 0
            # stabilitet
            if first:
                run=0
                for d in [x for x in dagar if x>=first and x<ed]:
                    if k in dtop[d]: run+=1
                    else: break
                eft=[x for x in dagar if x>=first and x<ed]
                andel=sum(1 for d in eft if k in dtop[d])/max(1,len(eft))
                worst=max([drank[d].get(k,999) for d in eft if k in drank[d]] or [999])
                stabil = run>=STAB
            else: run=0; andel=0.0; worst=None; stabil=False
            # pre-entry return efter qualification
            per=None
            if first:
                pj=didx_price=int(np.searchsorted(ds, np.datetime64(first), side="right"))-1
                if 0<=pj<len(ds) and j<len(ds) and ds[pj]<ds[j]:
                    _,v=ser[k]; per=float(v[j]/v[pj]-1.0) if v[pj]>0 else None
            # agandehistorik
            per_list=own.get(k,[])
            tidigare=[p for p in per_list if p[1]<ri]
            if not tidigare: klass="FIRST_EVER_ENTRY"; gap=None
            else:
                gap=ri-tidigare[-1][1]-1
                klass="REENTRY_SHORT_GAP" if gap<=1 else ("REENTRY_MEDIUM_GAP" if gap<=4 else "REENTRY_LONG_GAP")
            # taxonomi
            if delay==0: tax="TRUE_SIGNAL_LATENCY"
            elif stabil: tax="SAMPLING_LATENCY"
            else: tax="TRANSIENT_INTRAPANEL_TOPN"
            if klass!="FIRST_EVER_ENTRY" and tax=="TRUE_SIGNAL_LATENCY": tax="REENTRY_CONTINUITY"
            nr=G.nasdaq_rad(k,None,P[i]) or {}
            ix={n2:j2 for j2,n2 in enumerate(R.NAMES)}
            x=o["x"]
            E.append({"kod":k,"panel":P[i],"ri":ri,"pi":i,"entry_dag":ed,"y":o["y"],
                "rank_entry":rankp.get((k,P[i]),(None,None))[0],
                "first_daily_topn":first,"sampling_delay":delay,"run_dagar":run,"andel_topn":round(andel,3),
                "worst_rank":worst,"stabil":stabil,"pre_entry_ret":per,
                "ownership":klass,"gap_perioder":gap,"n_tidigare_perioder":len(tidigare),
                "taxonomi":tax,"phase":round((didx[first]-didx[fenster[0]])/max(1,len(fenster)),3) if first and fenster else None,
                "mom52":float(x[ix["mom52"]]) if np.isfinite(x[ix["mom52"]]) else None,
                "mom13":float(x[ix["mom13"]]) if np.isfinite(x[ix["mom13"]]) else None,
                "vol13":float(x[ix["vol13"]]) if np.isfinite(x[ix["vol13"]]) else None,
                "mc":nr.get("market_cap"),"icb":CWMAP.get(nr.get("industry"))})
    byp={}
    for r in E: byp.setdefault(r["pi"],[]).append(r)
    for p,S in byp.items():
        S2=sorted(S,key=lambda r:r["y"])
        for jj,r in enumerate(S2): r["tercil"]=["NEDRE","MITTEN","OVRE"][min(2,3*jj//max(1,len(S2)))]
    with open(UT/f"ledger_{wn}.jsonl","w") as f:
        for r in E: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    n=len(E); pid=np.array([r["pi"] for r in E]); y=np.array([r["y"] for r in E])
    dl=np.array([r["sampling_delay"] for r in E],float)
    from collections import Counter
    res["DEL17_SAMPLING"][wn]={"n":n,"median":float(np.median(dl)),"mean":round(float(dl.mean()),2),
        "p75":float(np.percentile(dl,75)),"p90":float(np.percentile(dl,90)),"max":float(dl.max()),
        "bins":{"0":round(float(np.mean(dl==0)),4),"1-5":round(float(np.mean((dl>=1)&(dl<=5))),4),
                "6-10":round(float(np.mean((dl>=6)&(dl<=10))),4),"11-20":round(float(np.mean((dl>=11)&(dl<=20))),4),
                "21-40":round(float(np.mean((dl>=21)&(dl<=40))),4),"40+":round(float(np.mean(dl>40)),4)}}
    res["DEL22_TAXONOMI"][wn]={k:round(v/n,4) for k,v in Counter(r["taxonomi"] for r in E).most_common()}
    res["DEL9_10_OWNERSHIP"][wn]={"andelar":{k:round(v/n,4) for k,v in Counter(r["ownership"] for r in E).most_common()},
        "andel_reentry":round(sum(1 for r in E if r["ownership"]!="FIRST_EVER_ENTRY")/n,4)}
    for t in ("OVRE","NEDRE"):
        S=[r for r in E if r["tercil"]==t]
        res["DEL9_10_OWNERSHIP"][wn][f"andel_reentry_{t}"]=round(sum(1 for r in S if r["ownership"]!="FIRST_EVER_ENTRY")/max(1,len(S)),4)
    for nm in ("FIRST_EVER_ENTRY","REENTRY_SHORT_GAP","REENTRY_MEDIUM_GAP","REENTRY_LONG_GAP"):
        S=[r for r in E if r["ownership"]==nm]
        if len(S)>=30:
            m,se=kl([r["y"] for r in S],[r["pi"] for r in S])
            res["DEL9_10_OWNERSHIP"][wn][f"y_{nm}"]={"n":len(S),"medel_pct":round(100*m,3),"se_pct":round(100*se,3)}
        else: res["DEL9_10_OWNERSHIP"][wn][f"y_{nm}"]={"n":len(S),"status":"NOT_IDENTIFIABLE"}
    S=[r for r in E if r["sampling_delay"]>0]
    res["DEL23_STABILITET"][wn]={"n_med_delay":len(S),
        "andel_stabila":round(sum(1 for r in S if r["stabil"])/max(1,len(S)),4),
        "median_run":float(np.median([r["run_dagar"] for r in S])) if S else None,
        "median_andel_topn":round(float(np.median([r["andel_topn"] for r in S])),3) if S else None}
    if S:
        pe=[r["pre_entry_ret"] for r in S if r["pre_entry_ret"] is not None]
        res["DEL19_PRE_ENTRY_RETURN"][wn]={"n":len(pe),"medel_pct":round(100*float(np.mean(pe)),3),
            "median_pct":round(100*float(np.median(pe)),3),"p25":round(100*float(np.percentile(pe,25)),3),
            "p75":round(100*float(np.percentile(pe,75)),3)}
        ph=[r["phase"] for r in S if r["phase"] is not None]
        res["DEL20_PHASE"][wn]={"n":len(ph),"median":round(float(np.median(ph)),3),
            "andel_forsta_tredjedelen":round(float(np.mean(np.array(ph)<1/3)),3),
            "andel_sista_tredjedelen":round(float(np.mean(np.array(ph)>2/3)),3)}
    o={}
    for lbl,mask in (("delay_0",dl==0),("delay_1_5",(dl>=1)&(dl<=5)),("delay_6plus",dl>=6)):
        if mask.sum()<30: o[lbl]={"n":int(mask.sum()),"status":"NOT_IDENTIFIABLE"}; continue
        m,se=kl(y[mask],pid[mask])
        o[lbl]={"n":int(mask.sum()),"medel_pct":round(100*m,3),"se_pct":round(100*se,3),
                "andel_ovre":round(float(np.mean([E[j]["tercil"]=="OVRE" for j in range(n) if mask[j]])),4)}
    res["DEL18_FUTURE_X_DELAY"][wn]=o
    res["DEL4_ABSOLUT_RANK"][wn]={"median_rank_entry":float(np.median([r["rank_entry"] for r in E if r["rank_entry"]]))}
    res["DEL26_LEDGER_TOPP"][wn]=[{kk:r[kk] for kk in ("kod","panel","y","rank_entry","first_daily_topn",
        "sampling_delay","stabil","ownership","n_tidigare_perioder","taxonomi","mom52")}
        for r in sorted([x for x in E if x["tercil"]=="OVRE"],key=lambda x:-x["y"])[:8]]
(UT/"analys.json").write_text(json.dumps(res,ensure_ascii=False,indent=1))
print("KLART")
