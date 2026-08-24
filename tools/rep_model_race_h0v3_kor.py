"""REP_MODEL_RACE_H0V3 — exekvering av den lasta preregistreringen.

Preregistrering: 8c301cf82a0c05f4dc869e757eb1be0320d204bbab934ae400c76e34ccd2555f

Featuredefinitionerna (F0, 23 st) ar ordagrant de som lastes i
H0_VALIDATOR_MODEL_RACE_1419_PREREGISTRATION och implementerades i
tools/h0_validator_model_race_1419.py:feat(). Rankningen ar H0 V3:s exakta regel.
"""
from __future__ import annotations
import json, math, sys, hashlib
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
from h0_v3_eligibility import medlem as PITMEDLEM
import h0_v3_window2_kor as X

O = V2 / "research_k/rep_model_race_h0v3"
N, COST, PPY = 30, 0.002, 13.0
BLOCK, DRAWS, SEED_BOOT = 13, 2000, 20260815
SEED = 20260819
NAMES = ["h0_score","h0_rank","m12_rank","m18_rank","mom4","mom13","mom26","mom52","mom12_1",
         "accel13","vol13","vol52","downvol52","trend_t52","trend_consistency52","sma26_gap",
         "sma52_gap","high52_ratio","maxdd52","skew52","kurt52","market_median26","market_breadth26"]

WINDOWS = {
 "W1_2014_2019": {"prices":"validated/prices_h1419/prices_h1419_universum_v2.json",
   "start":"2014-01-01","slut":"2019-12-31","isin":"h1419",
   "train_initial_end":"2015-12-31","refit_years":[2017,2018,2019]},
 "W2_2020_2026": {"prices":"validated/prices/prices_validated.json",
   "start":"2020-01-02","slut":"2026-07-24","isin":"canonical",
   "train_initial_end":"2022-12-30","refit_years":[2024,2025,2026]},
}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def isin_map(kind):
    if kind == "canonical": return X.bygg_isin_hint()
    rows = json.loads((V2/"validated/prices_h1419/membership_h1419_v2.json").read_text())["rows"]
    m = {r["kod"]: r.get("kalla") for r in rows}
    return {k:(v if isinstance(v,str) and len(v)==12 and v[:2].isalpha() else None) for k,v in m.items()}

def load_window(w):
    cfg = WINDOWS[w]
    priser = json.loads((V2/cfg["prices"]).read_text())
    serie = {k:(np.array([np.datetime64(r["d"]) for r in rs]),
                np.array([r["adj"] for r in rs],dtype=float)) for k,rs in priser.items()}
    ISIN = isin_map(cfg["isin"])
    P=[]; c=date.fromisoformat(cfg["start"])
    while c <= date.fromisoformat(cfg["slut"]): P.append(c.isoformat()); c += timedelta(days=28)
    def idx(k,d0):
        ds,_=serie[k]; i=int(np.searchsorted(ds,np.datetime64(d0),side="right"))-1
        return i if i>=0 else None
    def handlas(k,d0):
        i=idx(k,d0)
        if i is None: return False
        ds,_=serie[k]; return int((np.datetime64(d0)-ds[i])/np.timedelta64(1,"D"))<=30
    def mom(k,d0,weeks):
        ds,v=serie[k]; now=np.datetime64(d0); mal=now-np.timedelta64(7*weeks,"D")
        i=int(np.searchsorted(ds,now,side="right"))-1; j=int(np.searchsorted(ds,mal,side="right"))-1
        if i<0 or j<0 or int((mal-ds[j])/np.timedelta64(1,"D"))>10: return None
        return float(v[i]/v[j]-1.0)
    rankings={}
    for d0 in P:
        rows=[]
        for k in serie:
            if not handlas(k,d0): continue
            if not PITMEDLEM(k,ISIN.get(k),d0)[0]: continue
            rows.append({"kod":k,"m12":mom(k,d0,52),"m18":mom(k,d0,78)})
        for col in ("m12","m18"):
            g=sorted((r[col],r["kod"]) for r in rows if r[col] is not None)
            gr=defaultdict(list)
            for val,kod in g: gr[val].append(kod)
            rk={}; pos=1
            for val in sorted(gr):
                ks=gr[val]; s=(pos+pos+len(ks)-1)/2/max(1,len(g))
                for kod in ks: rk[kod]=s
                pos+=len(ks)
            for r in rows: r[col+"_rank"]=rk.get(r["kod"])
        raa=[0.5*(r["m12_rank"]+r["m18_rank"]) if r["m12_rank"] is not None and r["m18_rank"] is not None
             else None for r in rows]
        med=float(np.median([x for x in raa if x is not None])) if any(x is not None for x in raa) else 0.5
        sc=[{**r,"score":med if v is None else v} for r,v in zip(rows,raa)]
        sc.sort(key=lambda x:(x["score"],x["kod"]),reverse=True)
        rankings[d0]=sc
    retmap={}
    for k in serie:
        ds,v=serie[k]
        for a in range(len(P)-1):
            d0,nd=P[a],P[a+1]
            i=int(np.searchsorted(ds,np.datetime64(d0),side="right"))
            j=int(np.searchsorted(ds,np.datetime64(nd),side="right"))
            retmap[(k,d0)]=float(v[j-1]/v[i]-1.0) if (i<len(ds) and j-1<len(ds) and i<j and v[i]>0) else 0.0
        retmap[(k,P[-1])]=0.0
    return {"cfg":cfg,"serie":serie,"paneler":P,"rankings":rankings,"retmap":retmap,"idx":idx}

def price_at(serie,kod,day):
    ds,v=serie.get(kod,(np.array([]),np.array([])))
    i=int(np.searchsorted(ds,np.datetime64(day),side="right"))-1
    return (i,float(v[i])) if i>=0 else (-1,None)

def ret_at(serie,kod,day,days):
    i,p=price_at(serie,kod,day); ds,v=serie.get(kod,(np.array([]),np.array([])))
    j=int(np.searchsorted(ds,np.datetime64(day)-np.timedelta64(days,"D"),side="right"))-1
    return p/v[j]-1 if (p is not None and j>=0 and v[j]>0) else np.nan

def feat(serie,day,row,rank,market):
    kod=row["kod"]; i,p=price_at(serie,kod,day); ds,v=serie.get(kod,(np.array([]),np.array([])))
    if i<260: return [row["score"],rank,row.get("m12_rank"),row.get("m18_rank")]+[np.nan]*(len(NAMES)-4)
    daily=np.diff(v[i-260:i+1])/v[i-260:i]
    r4,r13,r26,r52=(ret_at(serie,kod,day,d) for d in (28,91,182,364))
    _,p4=price_at(serie,kod,str(np.datetime64(day)-np.timedelta64(28,"D")))
    _,p26=price_at(serie,kod,str(np.datetime64(day)-np.timedelta64(182,"D")))
    _,p52=price_at(serie,kod,str(np.datetime64(day)-np.timedelta64(364,"D")))
    mom121=p4/p52-1 if p4 and p52 else np.nan
    accel=r13-(p26/p52-1) if p26 and p52 else np.nan
    lo=daily[-260:]; neg=lo[lo<0]; x=np.arange(len(lo),dtype=float); y=np.log(v[i-259:i+1])
    xc=x-x.mean(); yc=y-y.mean(); sxx=float(xc@xc); slope=float(xc@yc)/sxx
    resid=yc-slope*xc; se=math.sqrt(float(resid@resid)/max(1,len(x)-2)/sxx); trend=slope/se if se else 0.
    win=v[i-260:i+1]; peak=np.maximum.accumulate(win); dd=float(np.min(win/peak-1))
    return [row["score"],rank,row.get("m12_rank"),row.get("m18_rank"),r4,r13,r26,r52,mom121,accel,
            float(np.std(daily[-65:])),float(np.std(lo)),float(np.std(neg)) if len(neg)>=10 else np.nan,
            trend,float(np.mean(daily>0)),p/np.mean(v[i-130:i])-1,p/np.mean(win)-1,p/np.max(win),dd,
            float(((lo-lo.mean())**3).mean()/(lo.std()**3)) if lo.std() else 0.,
            float(((lo-lo.mean())**4).mean()/(lo.std()**4)-3) if lo.std() else 0.,market[0],market[1]]

def build_obs(W):
    serie,P,rk,rm=W["serie"],W["paneler"],W["rankings"],W["retmap"]
    obs=[]
    for i,day in enumerate(P):
        r26={r["kod"]:ret_at(serie,r["kod"],day,182) for r in rk[day]}
        z=np.asarray([x for x in r26.values() if np.isfinite(x)])
        market=(float(np.median(z)),float(np.mean(z>0))) if len(z) else (np.nan,np.nan)
        for j,row in enumerate(rk[day],1):
            y=None if i+2>=len(P) else float((1+rm.get((row["kod"],P[i]),0.))*(1+rm.get((row["kod"],P[i+1]),0.))-1)
            obs.append({"date":day,"kod":row["kod"],"y":y,"x":feat(serie,day,row,j,market)})
    return obs

def make(name):
    from sklearn.ensemble import ExtraTreesRegressor,RandomForestRegressor,HistGradientBoostingRegressor
    if name=="EXTRATREES": return ExtraTreesRegressor(n_estimators=300,max_depth=5,min_samples_leaf=30,max_features="sqrt",random_state=SEED,n_jobs=1)
    if name=="RANDOM_FOREST": return RandomForestRegressor(n_estimators=300,max_depth=4,min_samples_leaf=40,max_features="sqrt",random_state=SEED,n_jobs=1)
    if name=="HIST_GRADIENT_BOOSTING": return HistGradientBoostingRegressor(max_iter=100,learning_rate=.05,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=10.,random_state=SEED)
    if name=="LIGHTGBM":
        import lightgbm as lgb
        return lgb.LGBMRegressor(n_estimators=80,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=40,reg_lambda=10.,reg_alpha=1.,colsample_bytree=.7,subsample=.8,random_state=SEED,n_jobs=1,verbosity=-1)
    if name=="CATBOOST":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(iterations=100,depth=3,learning_rate=.03,l2_leaf_reg=10.,loss_function="RMSE",random_seed=SEED,verbose=False,thread_count=1)
    if name=="XGBOOST":
        from xgboost import XGBRegressor
        return XGBRegressor(n_estimators=300,learning_rate=.03,max_depth=3,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=1.,random_state=SEED,n_jobs=1)
    raise ValueError(name)

def impute(train,x):
    med=np.asarray([np.nanmedian(train[:,j]) if np.isfinite(train[:,j]).any() else 0. for j in range(train.shape[1])])
    return np.where(np.isnan(x),med,x),med

# ---------- portfolj, likavikt, samma cadens och kostnad som H0 V3 ----------
def simulate(W, order_fn, start_i, top_n=N):
    P,rm=W["paneler"],W["retmap"]; prior=[]; vals=[]; turns=[]
    for i,day in enumerate(P):
        if i%2==0 or not prior:
            cur=order_fn(day,i)[:top_n]
            turn=len(set(cur)-set(prior))/max(1,top_n) if prior else 0.0
            prior=cur
        else: turn=0.0
        if i>=start_i:
            vals.append(sum(rm.get((k,day),0.) for k in prior)/max(1,len(prior))-COST*turn)
            turns.append(turn)
    return np.asarray(vals),np.asarray(turns),prior

def stat(x,rf=0.0224):
    w=np.cumprod(1+x); dd=w/np.maximum.accumulate(w)-1
    c=float(w[-1]**(PPY/len(x))-1); v=float(x.std(ddof=1)*math.sqrt(PPY))
    return {"cagr":round(c,4),"vol":round(v,4),"maxdd":round(float(dd.min()),4),
            "sharpe":round((c-rf)/v,4) if v>0 else 0.0}

def boot_ci(a,b):
    rng=np.random.default_rng(SEED_BOOT); nb=int(math.ceil(len(a)/BLOCK)); out=[]
    for _ in range(DRAWS):
        idx=[]
        for _ in range(nb):
            s=rng.integers(0,len(a)-BLOCK+1); idx.extend(range(s,s+BLOCK))
        idx=np.array(idx[:len(a)])
        out.append(np.cumprod(1+a[idx])[-1]**(PPY/len(a))-np.cumprod(1+b[idx])[-1]**(PPY/len(b)))
    lo,hi=np.percentile(out,[2.5,97.5]); d=a-b
    t=float(d.mean()/(d.std(ddof=1)/math.sqrt(len(d)))) if d.std(ddof=1)>0 else 0.0
    return {"delta_cagr":round(float(np.mean([stat(a)["cagr"]-stat(b)["cagr"]])),4),
            "ki_lo":round(float(lo),4),"ki_hi":round(float(hi),4),"t":round(t,3),
            "t_overlap_korr":round(t/math.sqrt(2),3),
            "andel_bootstrap_positiva":round(float(np.mean(np.asarray(out)>0)),3)}

def cost_sens(W,order_fn,start_i,bps,top_n=N):
    P,rm=W["paneler"],W["retmap"]; prior=[]; vals=[]
    for i,day in enumerate(P):
        if i%2==0 or not prior:
            cur=order_fn(day,i)[:top_n]; turn=len(set(cur)-set(prior))/max(1,top_n) if prior else 0.; prior=cur
        else: turn=0.
        if i>=start_i: vals.append(sum(rm.get((k,day),0.) for k in prior)/max(1,len(prior))-bps*turn)
    return stat(np.asarray(vals))["cagr"]

def conc(W,order_fn,start_i,top_n=N):
    P,rm=W["paneler"],W["retmap"]; prior=[]; bidrag=defaultdict(float); np_=0
    for i,day in enumerate(P):
        if i%2==0 or not prior: prior=order_fn(day,i)[:top_n]
        if i>=start_i:
            np_+=1
            for k in prior: bidrag[k]+=rm.get((k,day),0.)/max(1,len(prior))
    tot=sum(v for v in bidrag.values() if v>0)
    top3=sorted(bidrag.values(),reverse=True)[:3]
    return {"n_unika_namn":len(bidrag),"top3_bidrag_andel":round(sum(top3)/tot,4) if tot>0 else None}
