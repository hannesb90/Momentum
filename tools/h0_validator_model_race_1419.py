"""Fixed six-model H0 consensus race, exits and early entries, on 2014--19."""
from __future__ import annotations

import hashlib, json, math, sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
from catboost import CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as BASE
import h1419_motor as M
import stack_h_repaired_h012 as STATS

EXIT_PRE = V2 / "research_k/H0_VALIDATOR_MODEL_RACE_1419_PREREGISTRATION.json"
ENTRY_PRE = V2 / "research_k/H0_VALIDATOR_MODEL_RACE_1419_EARLY_ENTRY_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_validator_model_race_1419_results.json"
N, COST = 30, .002
NAMES = ["h0_score", "h0_rank", "m12_rank", "m18_rank", "mom4", "mom13", "mom26", "mom52", "mom12_1", "accel13", "vol13", "vol52", "downvol52", "trend_t52", "trend_consistency52", "sma26_gap", "sma52_gap", "high52_ratio", "maxdd52", "skew52", "kurt52", "market_median26", "market_breadth26"]
FEATURE_CACHE = {}


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def price(series, kod, day):
    ds, v = series.get(kod, (np.array([]), np.array([])))
    i = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    return (i, float(v[i])) if i >= 0 else (-1, None)

def ret(series, kod, day, days):
    i, p = price(series, kod, day); ds, v = series.get(kod, (np.array([]), np.array([])))
    j = int(np.searchsorted(ds, np.datetime64(day) - np.timedelta64(days, "D"), side="right")) - 1
    return p / v[j] - 1 if p is not None and j >= 0 and v[j] > 0 else np.nan

def feat(series, day, row, rank, market):
    kod = row["kod"]; i, p = price(series, kod, day); ds, v = series.get(kod, (np.array([]), np.array([])))
    if i < 260: return [row["score"], rank, row.get("m12_rank"), row.get("m18_rank")] + [np.nan] * (len(NAMES) - 4)
    daily = np.diff(v[i-260:i+1]) / v[i-260:i]
    r4, r13, r26, r52 = (ret(series, kod, day, d) for d in (28, 91, 182, 364))
    _, p4 = price(series, kod, str(np.datetime64(day) - np.timedelta64(28, "D")))
    _, p26 = price(series, kod, str(np.datetime64(day) - np.timedelta64(182, "D")))
    _, p52 = price(series, kod, str(np.datetime64(day) - np.timedelta64(364, "D")))
    mom121 = p4 / p52 - 1 if p4 and p52 else np.nan
    accel = r13 - (p26 / p52 - 1) if p26 and p52 else np.nan
    lo = daily[-260:]; neg = lo[lo < 0]; x = np.arange(len(lo), dtype=float); y = np.log(v[i-259:i+1]); xc = x-x.mean(); yc=y-y.mean(); sxx=float(xc@xc); slope=float(xc@yc)/sxx; resid=yc-slope*xc; se=math.sqrt(float(resid@resid)/max(1,len(x)-2)/sxx); trend=slope/se if se else 0.
    win=v[i-260:i+1]; peak=np.maximum.accumulate(win); dd=float(np.min(win/peak-1))
    return [row["score"], rank, row.get("m12_rank"), row.get("m18_rank"), r4, r13, r26, r52, mom121, accel,
            float(np.std(daily[-65:])), float(np.std(lo)), float(np.std(neg)) if len(neg) >= 10 else np.nan,
            trend, float(np.mean(daily > 0)), p/np.mean(v[i-130:i])-1, p/np.mean(win)-1, p/np.max(win), dd,
            float(((lo-lo.mean())**3).mean() / (lo.std()**3)) if lo.std() else 0., float(((lo-lo.mean())**4).mean() / (lo.std()**4)-3) if lo.std() else 0., market[0], market[1]]

def eight(returns, dates, i, kod):
    return None if i + 1 >= len(dates) else float((1+returns.get((kod, dates[i]),0.))*(1+returns.get((kod,dates[i+1]),0.))-1)

def load_obs(lo=0, hi=None):
    rankings, dates, returns, entry, schedule = BASE.early_loader(); series = M.SERIE; out=[]
    hi = len(dates) if hi is None else min(hi, len(dates))
    for i in range(lo, hi):
        day = dates[i]
        r26 = {r["kod"]: ret(series, r["kod"], day, 182) for r in rankings[day]}
        z=np.asarray([v for v in r26.values() if np.isfinite(v)]); market=(float(np.median(z)),float(np.mean(z>0))) if len(z) else (np.nan,np.nan)
        for rank,row in enumerate(rankings[day],1):
            out.append({"date":day,"kod":row["kod"],"y":eight(returns,dates,i,row["kod"]),"x":feat(series,day,row,rank,market)})
    return rankings, dates, returns, schedule, series, out

def impute(train, x):
    med=np.asarray([np.nanmedian(train[:,j]) if np.isfinite(train[:,j]).any() else 0. for j in range(train.shape[1])])
    return np.where(np.isnan(x),med,x),med

def make(name):
    if name == "ridge": return Ridge(alpha=10.)
    if name == "random_forest": return RandomForestRegressor(n_estimators=300,max_depth=4,min_samples_leaf=40,max_features="sqrt",random_state=20260816,n_jobs=1)
    if name == "extra_trees": return ExtraTreesRegressor(n_estimators=300,max_depth=5,min_samples_leaf=30,max_features="sqrt",random_state=20260816,n_jobs=1)
    if name == "hist_gradient_boosting": return HistGradientBoostingRegressor(max_iter=100,learning_rate=.05,max_leaf_nodes=7,min_samples_leaf=40,l2_regularization=10.,random_state=20260816)
    if name == "lightgbm": return lgb.LGBMRegressor(n_estimators=80,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=40,reg_lambda=10.,reg_alpha=1.,colsample_bytree=.7,subsample=.8,random_state=20260816,n_jobs=1,verbosity=-1)
    return CatBoostRegressor(iterations=100,depth=3,learning_rate=.03,l2_leaf_reg=10.,loss_function="RMSE",random_seed=20260816,verbose=False,thread_count=1)

def fit(name, rows):
    raw=np.asarray([r["x"] for r in rows],float); x,med=impute(raw,raw); return make(name).fit(x,np.asarray([r["y"] for r in rows])),med
def pred(model,med,x): return model.predict(np.where(np.isnan(np.asarray(x,float)),med,np.asarray(x,float)))

def state(data, day):
    rankings,dates,returns,schedule,series,obs=data; rr=rankings[day]
    if FEATURE_CACHE:
        return rr, {r["kod"]: FEATURE_CACHE[(day, r["kod"])] for r in rr}
    r26={r["kod"]:ret(series,r["kod"],day,182) for r in rr}; z=np.asarray([v for v in r26.values() if np.isfinite(v)]); market=(float(np.median(z)),float(np.mean(z>0))) if len(z) else (np.nan,np.nan)
    return rr, {r["kod"]:feat(series,day,r,j+1,market) for j,r in enumerate(rr)}

def ic(model,med,obs,start,end):
    vs=[]
    for d in sorted({r["date"] for r in obs if r["y"] is not None and start<=r["date"]<=end}):
        rs=[r for r in obs if r["date"]==d and r["y"] is not None]; y=np.asarray([r["y"] for r in rs]); p=pred(model,med,[r["x"] for r in rs])
        if y.std() and p.std(): vs.append(float(spearmanr(y,p).statistic))
    return {"panels":len(vs),"mean_spearman_ic":round(float(np.mean(vs)),4),"positive_share":round(float(np.mean(np.asarray(vs)>0)),4)}

def simulate(data,model,med,start,end,mode):
    rankings,dates,returns,schedule,series,obs=data; prior=[]; vals=[]; turns=[]; changes=0
    for i,day in enumerate(dates):
        active=start<=day<=end
        if not prior or schedule(i,day):
            rows,x=state(data,day); base=[r["kod"] for r in rows[:N]]; current=base
            if active and model is not None:
                p=dict(zip([r["kod"] for r in rows],pred(model,med,[x[r["kod"]] for r in rows]))); order=sorted(p,key=lambda k:(-p[k],k)); mr={k:j+1 for j,k in enumerate(order)}
                if mode == "exit" and prior:
                    add=[k for k in prior if k not in base and mr.get(k,999)<=N]; new=[k for k in base if k not in prior]; drop=set(sorted(new,key=lambda k:(p[k],k))[:len(add)]); current=[k for k in base if k not in drop]+add
                elif mode == "entry":
                    add=[r["kod"] for r in rows[30:60] if mr.get(r["kod"],999)<=N]; add=sorted(add,key=lambda k:(-p[k],k))[:2]; drop=set(sorted(base,key=lambda k:(p[k],k))[:len(add)]); current=[k for k in base if k not in drop]+add
                changes+=len(add)
            turn=len(set(current)-set(prior))/N if prior else 0.; prior=current
        else: turn=0.
        if active: vals.append(sum(returns.get((k,day),0.) for k in prior)/N-COST*turn); turns.append(turn)
    return np.asarray(vals),{"total_one_way_turnover":round(float(sum(turns)),4),"mean_one_way_turnover":round(float(np.mean(turns)),4),"changes":changes}

def eval_model(name,train,data,obs,start,end):
    model,med=fit(name,train); base,db=simulate(data,None,None,start,end,"exit"); ex,de=simulate(data,model,med,start,end,"exit"); en,dn=simulate(data,model,med,start,end,"entry")
    return {"train_n":len(train),"ic":ic(model,med,obs,start,end),"baseline_h0":{**STATS.stat(base),**db},"exit_consensus":{**STATS.stat(ex),**de},"early_entry":{**STATS.stat(en),**dn},"exit_delta":STATS.bootstrap(ex,base),"entry_delta":STATS.bootstrap(en,base)}

def main():
    a,b=json.loads(EXIT_PRE.read_text()),json.loads(ENTRY_PRE.read_text())
    if a["status"]!="PREREGISTERED_BEFORE_RESULTS" or b["status"]!="PREREGISTERED_BEFORE_RESULTS": raise SystemExit("inactive prereg")
    if len(sys.argv) == 3 and sys.argv[1] == "--feature-chunk":
        chunk = int(sys.argv[2]); lo, hi = chunk * 10, (chunk + 1) * 10
        data = load_obs(lo, hi)
        p = V2 / "research_k" / f"h0_validator_1419_features_{chunk}.json"
        p.write_text(json.dumps(data[-1], ensure_ascii=False) + "\n")
        print(f"chunk={chunk} rows={len(data[-1])}", flush=True)
        return
    parts = []
    for chunk in range(8):
        p = V2 / "research_k" / f"h0_validator_1419_features_{chunk}.json"
        if not p.exists(): raise SystemExit(f"missing feature chunk {chunk}")
        parts.extend(json.loads(p.read_text()))
    rankings, dates, returns, entry, schedule = BASE.early_loader()
    data=(rankings, dates, returns, schedule, M.SERIE, parts); obs=parts
    FEATURE_CACHE.update({(r["date"], r["kod"]): r["x"] for r in obs})
    train=[r for r in obs if r["y"] is not None and r["date"]<="2016-12-28"]
    print(f"observations={len(obs)} train={len(train)}", flush=True)
    result={"version":a["version"],"run_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"exit_prereg_sha256":sha(EXIT_PRE),"entry_prereg_sha256":sha(ENTRY_PRE),"diagnostic_only":True,"models":{}}
    all_models=["ridge","random_forest","extra_trees","hist_gradient_boosting","lightgbm","catboost"]
    selected = [sys.argv[2]] if len(sys.argv) == 3 and sys.argv[1] == "--model" else all_models
    for name in selected:
        print("running",name,flush=True); dev=eval_model(name,train,data,obs,"2017-01-25","2017-12-27"); final=eval_model(name,[r for r in obs if r["date"]<="2017-12-27"],data,obs,"2018-01-24","2019-12-25"); result["models"][name]={"development_2017":dev,"final_2018_2019":final}
    if len(selected) == 1:
        p = V2 / "research_k" / f"h0_validator_model_race_1419_{selected[0]}.json"
        p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
        print(f"wrote {p.name}", flush=True)
        return
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    for n,v in result["models"].items(): print(n,v["final_2018_2019"]["ic"],v["final_2018_2019"]["exit_delta"],v["final_2018_2019"]["entry_delta"],flush=True)
if __name__=="__main__": main()
