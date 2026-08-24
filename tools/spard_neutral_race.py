"""Preregistered neutral Spår D race. Never writes A/B/C/target."""
from __future__ import annotations
import hashlib, json, math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, ElasticNet
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
from catboost import CatBoostRegressor

V2=Path("/home/hannesb/momentum_v2"); CFG=V2/"spard/core_race_preregistration.json"
OUT=V2/"spard/results/SPARD_CORE_NEUTRAL_RACE_V1"; SEED=20260808

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(path,obj): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(obj,ensure_ascii=False,indent=1,sort_keys=True),encoding="utf-8")
def finite(x): return None if x is None or not math.isfinite(float(x)) else float(x)

def guard(cfg):
    paths={"core_panel.json":V2/"panels/core_panel.json","core_fundamenta_panel.json":V2/"panels/core_fundamenta_panel.json","target_table.json":V2/"panels/target_table.json","feature_registry.json":V2/"docs/probes/feature_registry.json"}
    actual={k:sha(v) for k,v in paths.items()}
    if actual!=cfg["inputs_frozen"]: raise RuntimeError(f"FROZEN INPUT DRIFT: {actual}")
    return actual

def models(name):
    common=dict(random_state=SEED,n_jobs=4)
    if name=="ridge": return make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),Ridge(alpha=10.0))
    if name=="elasticnet": return make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),ElasticNet(alpha=.01,l1_ratio=.5,max_iter=5000,random_state=SEED))
    if name=="lightgbm": return make_pipeline(SimpleImputer(strategy="median"),LGBMRegressor(n_estimators=300,learning_rate=.03,max_depth=4,num_leaves=15,min_child_samples=50,subsample=.8,colsample_bytree=.8,reg_lambda=1,verbosity=-1,**common))
    if name=="xgboost": return make_pipeline(SimpleImputer(strategy="median"),XGBRegressor(n_estimators=300,learning_rate=.03,max_depth=3,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=1,objective="reg:squarederror",**common))
    if name=="catboost": return make_pipeline(SimpleImputer(strategy="median"),CatBoostRegressor(iterations=300,learning_rate=.03,depth=4,l2_leaf_reg=3,loss_function="RMSE",verbose=False,random_seed=SEED,thread_count=4,allow_writing_files=False))
    raise KeyError(name)

def load_data(panel_name, feature_ids):
    panel=json.loads((V2/f"panels/{panel_name}").read_text()); target=json.loads((V2/"panels/target_table.json").read_text())
    tm={(k,r["panel_date"]):r for k,rs in target.items() for r in rs}
    rows=[]
    for r in panel:
        t=tm[(r["kod"],r["panel_date"])]
        if t["target_fwd52w"] is None: continue
        x={f:r.get(f) for f in feature_ids}
        rows.append({"kod":r["kod"],"panel_date":r["panel_date"],"price_date":r["price_date"],"y":t["target_fwd52w"],"has_fundamenta":r.get("has_fundamenta"),**x})
    return pd.DataFrame(rows)

def split_defs(df):
    specs=[("validation_2023","validation","2023-01-01","2023-12-31"),("oos_2024","test","2024-01-01","2024-12-31"),("oos_2025","test","2025-01-01","2025-12-31")]
    out=[]
    for name,role,lo,hi in specs:
        cutoff=(date.fromisoformat(lo)-timedelta(weeks=52)).isoformat()
        tr=df[df.panel_date<=cutoff]; ev=df[(df.panel_date>=lo)&(df.panel_date<=hi)]
        out.append(dict(name=name,role=role,eval_from=lo,eval_to=hi,train_to=cutoff,n_train=len(tr),n_eval=len(ev),train_dates=tr.panel_date.nunique(),eval_dates=ev.panel_date.nunique(),train_first=tr.panel_date.min(),train_last=tr.panel_date.max(),eval_first=ev.panel_date.min(),eval_last=ev.panel_date.max()))
    return out

def fit_predict(df,features,names,tag):
    splits=split_defs(df); preds=[]
    for s in splits:
        tr=df[df.panel_date<=s["train_to"]]; ev=df[(df.panel_date>=s["eval_from"])&(df.panel_date<=s["eval_to"])]
        for name in names:
            m=models(name); m.fit(tr[features],tr.y); score=m.predict(ev[features])
            for (_,r),z in zip(ev.iterrows(),score): preds.append({"dataset":tag,"model":name,"split":s["name"],"role":s["role"],"kod":r.kod,"panel_date":r.panel_date,"score":float(z),"target_fwd52w":float(r.y),"has_fundamenta":None if pd.isna(r.has_fundamenta) else bool(r.has_fundamenta)})
    return preds,splits

def ic_metrics(rows):
    by=defaultdict(list)
    for r in rows: by[r["panel_date"]].append(r)
    per=[]
    for dt,rs in sorted(by.items()):
        scores=np.array([r["score"] for r in rs]); ys=np.array([r["target_fwd52w"] for r in rs])
        ic=finite(spearmanr(scores,ys).statistic) if len(np.unique(scores))>1 else None
        top=sorted(rs,key=lambda z:(z["score"],z["kod"]),reverse=True)[:30]
        tic=finite(spearmanr([r["score"] for r in top],[r["target_fwd52w"] for r in top]).statistic) if len({r["score"] for r in top})>1 else None
        per.append({"panel_date":dt,"n":len(rs),"ic52":ic,"top30_ic52":tic,"distinct_scores":len(set(scores)),"tie_share":1-len(set(scores))/len(scores),"score_min":float(scores.min()),"score_median":float(np.median(scores)),"score_max":float(scores.max()),"score_std":float(scores.std())})
    vals=[r["ic52"] for r in per if r["ic52"] is not None]; top=[r["top30_ic52"] for r in per if r["top30_ic52"] is not None]
    years={}
    for y in sorted({r["panel_date"][:4] for r in per}):
        v=[r["ic52"] for r in per if r["panel_date"].startswith(y) and r["ic52"] is not None]
        years[y]={"n_dates":len(v),"mean_ic52":finite(np.mean(v)),"median_ic52":finite(np.median(v)),"positive_share":finite(np.mean(np.array(v)>0))}
    # adjacent-date rank stability on overlapping tickers
    stab=[]; dates=sorted(by)
    for a,b in zip(dates,dates[1:]):
        x={r["kod"]:r["score"] for r in by[a]}; y={r["kod"]:r["score"] for r in by[b]}; common=sorted(set(x)&set(y))
        if len(common)>2: stab.append(finite(spearmanr([x[k] for k in common],[y[k] for k in common]).statistic))
    return {"n_obs":len(rows),"n_dates":len(per),"mean_ic52":finite(np.mean(vals)),"median_ic52":finite(np.median(vals)),"positive_ic_share":finite(np.mean(np.array(vals)>0)),"mean_top30_ic52":finite(np.mean(top)),"median_top30_ic52":finite(np.median(top)),"calendar_year":years,"score_quality":{"min_distinct_per_date":min(r["distinct_scores"] for r in per),"median_distinct_per_date":finite(np.median([r["distinct_scores"] for r in per])),"max_tie_share":max(r["tie_share"] for r in per),"min_score_std":min(r["score_std"] for r in per),"median_adjacent_rank_stability":finite(np.median([x for x in stab if x is not None]))},"per_date":per}

def sector_map():
    live=json.loads((V2/"docs/probes/instruments_live.json").read_text()); byisin={(r.get("isin") or "").upper():r.get("sectorId") for r in live}
    master=json.loads((V2/"docs/probes/instrument_master.json").read_text()); out={}
    for r in master:
        e=r.get("eodhd") or {}; k=e.get("code"); isin=(e.get("isin") or "").upper()
        if k and k not in out: out[k]=byisin.get(isin)
    return out

def price_returns():
    core=json.loads((V2/"panels/core_panel.json").read_text()); prices=json.loads((V2/"validated/prices/prices_validated.json").read_text()); terminal=json.loads((V2/"validated/terminal_events.json").read_text())
    by=defaultdict(dict)
    for r in core: by[r["kod"]][r["panel_date"]]=r["price_date"]
    dates=sorted({r["panel_date"] for r in core}); nxt=dict(zip(dates,dates[1:]))
    adj={k:{r["d"]:r["adj"] for r in rs} for k,rs in prices.items()}; last={k:rs[-1]["d"] for k,rs in prices.items()}
    ret={}
    for k,ds in by.items():
        for dt,p0d in ds.items():
            nd=nxt.get(dt)
            if not nd: continue
            p1d=ds.get(nd)
            if p1d: ret[(k,dt)]=adj[k][p1d]/adj[k][p0d]-1
            elif k in terminal and dt < terminal[k]["event_date"] <= nd: ret[(k,dt)]=adj[k][last[k]]/adj[k][p0d]-1
            else: ret[(k,dt)]=0.0
    return ret

def annualized(rs):
    if not rs:return None
    wealth=np.cumprod(1+np.array(rs)); years=len(rs)/13
    return finite(wealth[-1]**(1/years)-1) if wealth[-1]>0 else -1.0

def portfolio(rows):
    by=defaultdict(list)
    for r in rows: by[r["panel_date"]].append(r)
    pret=price_returns(); sec=sector_map(); prev=set(); periods=[]; contrib=defaultdict(float); sector=Counter(); selections=Counter()
    for dt,rs in sorted(by.items()):
        chosen=sorted(rs,key=lambda z:(z["score"],z["kod"]),reverse=True)[:30]; ids={r["kod"] for r in chosen}; turn=1-len(ids&prev)/30 if prev else 1.0
        cr={r["kod"]:pret.get((r["kod"],dt),0.0)/len(chosen) for r in chosen}; gross=sum(cr.values()); net=gross-.002*turn
        bench=np.mean([pret.get((r["kod"],dt),0.0) for r in rs]) if rs else 0
        periods.append({"panel_date":dt,"gross_return_4w":gross,"net_return_4w":net,"benchmark_return_4w":float(bench),"excess_return_4w":net-bench,"turnover":turn,"n":len(chosen)})
        for k,v in cr.items(): contrib[k]+=v; selections[k]+=1; sector[str(sec.get(k) or "UNKNOWN")]+=1
        prev=ids
    nr=[r["net_return_4w"] for r in periods]; br=[r["benchmark_return_4w"] for r in periods]; ex=[a-b for a,b in zip(nr,br)]; wealth=np.cumprod(1+np.array(nr)); dd=wealth/np.maximum.accumulate(wealth)-1
    base=annualized(nr); be=annualized(br); ann_ex=None if base is None or be is None else base-be
    ranked=sorted(contrib.items(),key=lambda z:z[1],reverse=True); top3=[k for k,_ in ranked[:3]]
    def leave(excluded):
        rr=[]
        for dt,rs in sorted(by.items()):
            ch=[r for r in sorted(rs,key=lambda z:(z["score"],z["kod"]),reverse=True)[:30] if r["kod"] not in excluded]
            rr.append(float(np.mean([pret.get((r["kod"],dt),0.0) for r in ch])) if ch else 0)
        return annualized(rr)
    loo={k:leave({k}) for k,_ in ranked}
    return {"n_periods":len(periods),"cagr":base,"benchmark_cagr":be,"annualized_excess":ann_ex,"sharpe":finite(np.mean(ex)/np.std(ex,ddof=1)*math.sqrt(13)) if len(ex)>1 and np.std(ex,ddof=1)>0 else None,"max_drawdown":finite(dd.min()),"mean_turnover":finite(np.mean([r["turnover"] for r in periods])),"n_changes":sum(r["turnover"]>0 for r in periods),"hit_rate_vs_benchmark":finite(np.mean(np.array(ex)>0)),"best_ticker":ranked[0] if ranked else None,"worst_ticker":ranked[-1] if ranked else None,"ticker_contribution":dict(ranked),"leave_one_ticker_out_cagr":loo,"leave_top3_out_cagr":leave(set(top3)),"top3_tickers":top3,"sector_selection_share":{k:v/sum(sector.values()) for k,v in sector.items()},"periods":periods}

def evaluate(preds,tag):
    out={}
    for model in sorted({r["model"] for r in preds}):
        mr=[r for r in preds if r["model"]==model]; out[model]={}
        for role in ("validation","test"):
            rr=[r for r in mr if r["role"]==role]; out[model][role]={"ic":ic_metrics(rr),"portfolio":portfolio(rr)}
        out[model]["all_eval"]={"ic":ic_metrics(mr),"portfolio":portfolio(mr)}
    return out

def baseline_momentum(df):
    out=[]
    for s in split_defs(df):
        ev=df[(df.panel_date>=s["eval_from"])&(df.panel_date<=s["eval_to"])]
        med=ev.groupby("panel_date")["mom_52w"].median().to_dict()
        for _,r in ev.iterrows(): out.append({"dataset":"CORE","model":"momentum_52w","split":s["name"],"role":s["role"],"kod":r.kod,"panel_date":r.panel_date,"score":float(r.mom_52w) if not pd.isna(r.mom_52w) else float(med[r.panel_date]),"target_fwd52w":float(r.y),"has_fundamenta":None})
    return out

def manifest_tree(root):
    files=[]
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name!="manifest.json": files.append({"path":p.relative_to(root).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)})
    return {"files":files,"aggregate_sha256":hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()}

def main():
    cfg=json.loads(CFG.read_text()); inputs=guard(cfg); reg=json.loads((V2/"docs/probes/feature_registry.json").read_text())
    coref=[r["id"] for r in reg["CORE"] if r.get("status")!="UTESLUTEN" and not r.get("ej_feature")]
    fundf=[r["id"] for r in reg["FUNDAMENTA"] if r.get("status")!="UTESLUTEN" and not r.get("ej_feature")]
    assert len(coref)==29 and len(fundf)==18
    core=load_data("core_panel.json",coref); splits=split_defs(core); dump(OUT/"split_manifest.json",{"created_before_fit":True,"embargo_weeks":52,"splits":splits,"features":coref,"input_hashes":inputs})
    names=["ridge","elasticnet","lightgbm","xgboost","catboost"]
    cp,sp=fit_predict(core,coref,names,"CORE"); cp+=baseline_momentum(core)
    dump(OUT/"core_predictions.json",cp); cm=evaluate(cp,"CORE"); dump(OUT/"core_metrics.json",cm)
    # Lock CORE before selection/challenger.
    core_lock={"predictions_sha256":sha(OUT/"core_predictions.json"),"metrics_sha256":sha(OUT/"core_metrics.json"),"split_manifest_sha256":sha(OUT/"split_manifest.json")}; dump(OUT/"CORE_LOCK.json",core_lock)
    eligible=[]
    for n in names:
        m=cm[n]["test"]; ic=m["ic"]; p=m["portfolio"]
        fragile=(p["annualized_excess"] is not None and p["annualized_excess"]>0 and (p["leave_top3_out_cagr"] is None or p["leave_top3_out_cagr"]-p["benchmark_cagr"]<=0 or (p["annualized_excess"]-(p["leave_top3_out_cagr"]-p["benchmark_cagr"]))/p["annualized_excess"]>=.5))
        deg=ic["score_quality"]["min_distinct_per_date"]<10 or ic["score_quality"]["min_score_std"]<1e-12
        if ic["median_ic52"]>0 and ic["mean_ic52"]>0 and not fragile and not deg: eligible.append(n)
    selected=sorted(eligible,key=lambda n:cm[n]["test"]["ic"]["median_ic52"],reverse=True)[:2]
    dump(OUT/"selection.json",{"rule":cfg["selection_rule"],"eligible":eligible,"selected":selected})
    challenger={}; fp=[]
    if selected:
        fund=load_data("core_fundamenta_panel.json",coref+fundf); fp,_=fit_predict(fund,coref+fundf,selected,"CORE_FUNDAMENTA"); dump(OUT/"fundamenta_predictions.json",fp); challenger=evaluate(fp,"CORE_FUNDAMENTA"); dump(OUT/"fundamenta_metrics.json",challenger)
        subgroup={}
        for n in selected:
            subgroup[n]={}
            for flag in (True,False):
                rr=[r for r in fp if r["role"]=="test" and r["has_fundamenta"] is flag]
                subgroup[n][str(flag)]=ic_metrics(rr) if rr else None
        dump(OUT/"fundamenta_coverage_subgroups.json",subgroup)
    dump(OUT/"environment.json",{"python":__import__("sys").version,"numpy":np.__version__,"pandas":pd.__version__,"sklearn":__import__("sklearn").__version__,"lightgbm":__import__("lightgbm").__version__,"xgboost":__import__("xgboost").__version__,"catboost":__import__("catboost").__version__})
    dump(OUT/"manifest.json",manifest_tree(OUT)); print(json.dumps({"status":"COMPLETE","selected":selected,"core_rows":len(core),"output":str(OUT)},indent=2))

if __name__=="__main__": main()
