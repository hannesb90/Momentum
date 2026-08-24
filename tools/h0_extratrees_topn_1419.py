"""Fixed Extra Trees selection within H0 Top-30 at N=10/15/20; diagnostic only."""
from __future__ import annotations

import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as BASE
import h1419_motor as M
import stack_h_repaired_h012 as STATS
import h0_validator_model_race_1419 as R

PRE = V2 / "research_k/H0_EXTRATREES_TOPN_1419_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_extratrees_topn_1419_results.json"
COST = .002

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def data():
    parts=[]
    for i in range(8): parts.extend(json.loads((V2 / "research_k" / f"h0_validator_1419_features_{i}.json").read_text()))
    rankings, dates, returns, entry, schedule = BASE.early_loader()
    R.FEATURE_CACHE.clear(); R.FEATURE_CACHE.update({(r["date"],r["kod"]):r["x"] for r in parts})
    return rankings, dates, returns, schedule, M.SERIE, parts

def sim(d, model, med, start, end, n, et):
    rankings, dates, returns, schedule, series, obs=d; prior=[]; vals=[]; turns=[]
    for i, day in enumerate(dates):
        active=start <= day <= end
        if not prior or schedule(i,day):
            base=[r["kod"] for r in rankings[day][:30]]
            if et:
                rows,x=R.state(d,day); p=dict(zip([r["kod"] for r in rows],R.pred(model,med,[x[r["kod"]] for r in rows])))
                current=sorted(base,key=lambda k:(-p[k],k))[:n]
            else: current=base[:n]
            turn=len(set(current)-set(prior))/n if prior else 0.; prior=current
        else: turn=0.
        if active: vals.append(sum(returns.get((k,day),0.) for k in prior)/n-COST*turn); turns.append(turn)
    return np.asarray(vals),{"total_one_way_turnover":round(float(sum(turns)),4),"mean_one_way_turnover":round(float(np.mean(turns)),4)}

def run_window(d, model, med, start, end):
    h30,dh30=sim(d,model,med,start,end,30,False); out={"h0_top30":{**STATS.stat(h30),**dh30}}
    for n in (10,15,20):
        hn,dhn=sim(d,model,med,start,end,n,False); en,den=sim(d,model,med,start,end,n,True)
        out[f"n{n}"]={"h0_topn":{**STATS.stat(hn),**dhn},"extra_trees_topn":{**STATS.stat(en),**den},"extra_trees_vs_h0_topn":STATS.bootstrap(en,hn),"h0_topn_vs_h0_top30":STATS.bootstrap(hn,h30)}
    return out

def main():
    pre=json.loads(PRE.read_text())
    if pre["status"]!="PREREGISTERED_BEFORE_RESULTS": raise SystemExit("inactive prereg")
    d=data(); obs=d[-1]; train=[r for r in obs if r["y"] is not None and r["date"]<="2016-12-28"]
    model,med=R.fit("extra_trees",train)
    result={"version":pre["version"],"run_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"preregistration_sha256":sha(PRE),"diagnostic_only":True,"train_n":len(train),"development_2017":run_window(d,model,med,"2017-01-25","2017-12-27")}
    model,med=R.fit("extra_trees",[r for r in obs if r["y"] is not None and r["date"]<="2017-12-27"])
    result["final_2018_2019"]=run_window(d,model,med,"2018-01-24","2019-12-25")
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    for w in ("development_2017","final_2018_2019"):
        print(w,{n:{"et":result[w][f"n{n}"]["extra_trees_vs_h0_topn"]["delta_cagr"],"conc":result[w][f"n{n}"]["h0_topn_vs_h0_top30"]["delta_cagr"]} for n in (10,15,20)},flush=True)
if __name__=="__main__": main()
