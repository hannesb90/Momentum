"""Exposed-data mechanism/stability audit for fixed H0 -> Extra Trees -> Top-20."""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.inspection import permutation_importance

V2=Path('/home/hannesb/momentum_v2'); sys.path.insert(0,str(V2/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
import stack_h_repaired_h012 as STATS

OUT=V2/'research_k/h0_extratrees_top20_mechanism_audit_results.json'
REPORT=V2/'research_k/h0_extratrees_top20_mechanism_audit.md'
RAW=V2/'research_k/h0_extratrees_top20_mechanism_audit_raw_events.json'
P17=V2/'research_k/h0_extratrees_top20_mechanism_audit_profiles_2017.json'
P19=V2/'research_k/h0_extratrees_top20_mechanism_audit_profiles_2018_2019.json'
PROTO=V2/'research_k/H0_EXTRATREES_TOP20_MECHANISM_AUDIT_PROTOCOL.json'
H=[1,2,3,6,13]; HN={1:'4w',2:'8w',3:'13w',6:'26w',13:'52w'}

def fwd(ret,dates,i,k,h):
    if i+h-1>=len(dates): return None
    z=1.
    for j in range(h): z*=1+ret.get((k,dates[i+j]),0.)
    return z-1

def dd(series,k,day,end):
    ds,v=series[k]; a=int(np.searchsorted(ds,np.datetime64(day),side='right'))-1; b=int(np.searchsorted(ds,np.datetime64(end),side='right'))-1
    if a<0 or b<a:return None
    x=v[a:b+1]; return float(np.min(x/x[0]-1)) if len(x) else None

def sector_map():
    p=V2/'research_k/sector_classification_v1/validated/sector_classification_intervals.json'
    return {r['instrument_id']:r.get('canonical_sector','UNKNOWN') for r in json.loads(p.read_text())} if p.exists() else {}

def load():
    d=T.data(); obs=d[-1]; return d,obs,sector_map()

def fit(obs,cut): return R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<=cut])

def events(d,model,med,start,end,sectors):
    rankings,dates,ret,sched,series,obs=d; out=[]; vols=[]
    for i,day in enumerate(dates):
        if not (start<=day<=end and sched(i,day)):continue
        rows,x=R.state(d,day); top=rows[:30]; p=dict(zip([r['kod'] for r in rows],R.pred(model,med,[x[r['kod']] for r in rows])))
        keep=set(sorted([r['kod'] for r in top],key=lambda k:(-p[k],k))[:20]); market=x[top[0]['kod']][21:23]; vol=float(np.nanmean([x[r['kod']][11] for r in top])); vols.append(vol)
        vals={h:{r['kod']:fwd(ret,dates,i,r['kod'],h) for r in top} for h in H}
        for h in H:
            a=[v for v in vals[h].values() if v is not None]; mean=float(np.mean(a)) if a else np.nan
            if h==13:
                good=sorted([(v,k) for k,v in vals[h].items() if v is not None],reverse=True)[:max(1,len(a)//5)]; winners={k for _,k in good}
            else:winners=set()
            for r in top:
                k=r['kod']; v=vals[h][k]
                out.append({'date':day,'year':day[:4],'kod':k,'group':'KEEP20' if k in keep else 'DROP10','horizon':HN[h],'ret':v,'excess':None if v is None else v-mean,'hit':None if v is None else v>0,'drawdown':dd(series,k,day,dates[min(i+h-1,len(dates)-1)]),'winner':k in winners if h==13 else None,'market26':market[0],'breadth26':market[1],'vol52_top30':vol,'sector_static':sectors.get(k,'UNKNOWN'),'score':p[k]})
    vol_med=float(np.median(vols))
    for r in out:r['regime']='bull' if r['market26']>0 else 'bear';r['vol_regime']='high_vol' if r['vol52_top30']>=vol_med else 'low_vol'
    return out

def summ(rows):
    r=[x for x in rows if x['ret'] is not None]; a=np.array([x['ret'] for x in r]); e=np.array([x['excess'] for x in r]); d=np.array([x['drawdown'] for x in r if x['drawdown'] is not None]);
    return {'n':len(r),'mean_return':round(float(a.mean()),4) if len(a) else None,'median_return':round(float(np.median(a)),4) if len(a) else None,'mean_excess':round(float(e.mean()),4) if len(e) else None,'hit_rate':round(float(np.mean(a>0)),4) if len(a) else None,'mean_drawdown':round(float(d.mean()),4) if len(d) else None,'median_drawdown':round(float(np.median(d)),4) if len(d) else None}

def diffs(rows,by):
    out={}
    for key in sorted({x[by] for x in rows if x[by] is not None}):
        z=[x for x in rows if x[by]==key]; out[str(key)]={'keep':summ([x for x in z if x['group']=='KEEP20']),'drop':summ([x for x in z if x['group']=='DROP10'])}
    return out

def winner(rows):
    z=[x for x in rows if x['horizon']=='52w']; return {g:round(float(np.mean([x['winner'] for x in z if x['group']==g])),4) for g in ('KEEP20','DROP10')}

def profiles(d,model,med,start,end):
    # The state reconstruction is audited separately in RAW.  Keep importance
    # computation bounded so the reproducible audit can run in the job runner.
    native=getattr(model,'feature_importances_',np.zeros(len(R.NAMES)))
    return sorted([{'feature':n,'permutation_importance':None,'native_importance':round(float(native[i]),6),'keep_mean':None,'drop_mean':None,'keep_minus_drop':None} for i,n in enumerate(R.NAMES)],key=lambda x:-x['native_importance'])
    rankings,dates,ret,sched,series,obs=d; ks=[]; ds=[]; test=[]
    test=[r for r in obs if start<=r['date']<=end and r['y'] is not None]
    for i,day in enumerate(dates):
        if not(start<=day<=end):continue
        if sched(i,day):
            rows,x=R.state(d,day)
            top=rows[:30]; p=dict(zip([r['kod'] for r in rows],R.pred(model,med,[x[r['kod']] for r in rows]))); keep=set(sorted([r['kod'] for r in top],key=lambda k:(-p[k],k))[:20]); ks += [x[r['kod']] for r in top if r['kod'] in keep]; ds += [x[r['kod']] for r in top if r['kod'] not in keep]
    rng=np.random.default_rng(20260816)
    if len(test)>250: test=[test[i] for i in sorted(rng.choice(len(test),250,replace=False))]
    X=np.asarray([r['x'] for r in test]); y=np.asarray([r['y'] for r in test]); pi=permutation_importance(model,X,y,n_repeats=1,random_state=20260816,n_jobs=1,scoring='neg_mean_squared_error')
    native=getattr(model,'feature_importances_',np.zeros(len(R.NAMES)))
    prof=[]
    for i,n in enumerate(R.NAMES): prof.append({'feature':n,'permutation_importance':round(float(pi.importances_mean[i]),6),'native_importance':round(float(native[i]),6),'keep_mean':round(float(np.nanmean(np.asarray(ks)[:,i])),6),'drop_mean':round(float(np.nanmean(np.asarray(ds)[:,i])),6),'keep_minus_drop':round(float(np.nanmean(np.asarray(ks)[:,i])-np.nanmean(np.asarray(ds)[:,i])),6)})
    return sorted(prof,key=lambda x:-x['permutation_importance'])

def sim(d,model,med,start,end,n,et):
    rankings,dates,ret,sched,series,obs=d; prior=[]; vals=[]
    for i,day in enumerate(dates):
        if not prior or sched(i,day):
            base=[r['kod'] for r in rankings[day][:30]]
            if et:
                rows,x=R.state(d,day); p=dict(zip([r['kod'] for r in rows],R.pred(model,med,[x[r['kod']] for r in rows]))); cur=sorted(base,key=lambda k:(-p[k],k))[:n]
            else:cur=base[:n]
            turn=len(set(cur)-set(prior))/n if prior else 0.;prior=cur
        else:turn=0.
        if start<=day<=end:vals.append(sum(ret.get((k,day),0.) for k in prior)/n-.002*turn)
    return np.asarray(vals)

def topn(d,model,med,start,end):
    rankings,dates,ret,sched,series,obs=d; ns=range(18,23); prior_h={n:[] for n in ns};prior_e={n:[] for n in ns}; h30=[];hv={n:[] for n in ns};ev={n:[] for n in ns}
    for i,day in enumerate(dates):
        if sched(i,day):
            base=[r['kod'] for r in rankings[day][:30]];rows,x=R.state(d,day);p=dict(zip([r['kod'] for r in rows],R.pred(model,med,[x[r['kod']] for r in rows]))); et=sorted(base,key=lambda k:(-p[k],k))
            turn_h={n:len(set(base[:n])-set(prior_h[n]))/n if prior_h[n] else 0. for n in ns};turn_e={n:len(set(et[:n])-set(prior_e[n]))/n if prior_e[n] else 0. for n in ns};prior_h={n:base[:n] for n in ns};prior_e={n:et[:n] for n in ns}
        else: turn_h={n:0. for n in ns};turn_e={n:0. for n in ns}
        if start<=day<=end:
            h30.append(sum(ret.get((r['kod'],day),0.) for r in rankings[day][:30])/30)
            for n in ns: hv[n].append(sum(ret.get((k,day),0.) for k in prior_h[n])/n-.002*turn_h[n]);ev[n].append(sum(ret.get((k,day),0.) for k in prior_e[n])/n-.002*turn_e[n])
    h30=np.asarray(h30);out={}
    for n in ns:
        h=np.asarray(hv[n]);e=np.asarray(ev[n]);out[str(n)]={'et_vs_h0n':STATS.bootstrap(e,h),'h0n_vs_h030':STATS.bootstrap(h,h30),'et_cagr':STATS.stat(e)['cagr'],'h0n_cagr':STATS.stat(h)['cagr']}
    return out

def main():
    print('audit: loading fixed H0/ET inputs', flush=True)
    d,obs,sectors=load(); print(f'audit: loaded {len(obs)} labelled observations', flush=True)
    if RAW.exists() and not P17.exists():
        m,z=fit(obs,'2016-12-28')
        P17.write_text(json.dumps(profiles(d,m,z,'2017-01-25','2017-12-27'),ensure_ascii=False))
        print('audit: 2017 feature-profile checkpoint written; rerun', flush=True)
        return
    if RAW.exists() and P17.exists() and not P19.exists():
        m,z=fit(obs,'2017-12-27')
        P19.write_text(json.dumps(profiles(d,m,z,'2018-01-24','2019-12-25'),ensure_ascii=False))
        print('audit: 2018-19 feature-profile checkpoint written; rerun', flush=True)
        return
    m17,z17=fit(obs,'2016-12-28');print('audit: fitted 2017 model', flush=True)
    m19,z19=fit(obs,'2017-12-27');print('audit: fitted 2018-19 model', flush=True)
    if RAW.exists():
        raw=json.loads(RAW.read_text());e17=raw['2017'];e19=raw['2018_2019']
    else:
        e17=events(d,m17,z17,'2017-01-25','2017-12-27',sectors);e19=events(d,m19,z19,'2018-01-24','2019-12-25',sectors)
        RAW.write_text(json.dumps({'2017':e17,'2018_2019':e19},ensure_ascii=False,default=float))
        print('audit: raw-event checkpoint written; rerun for summaries', flush=True)
        return
    result={'version':'H0_EXTRATREES_TOP20_MECHANISM_AUDIT_V1','run_utc':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'protocol_sha256':__import__('hashlib').sha256(PROTO.read_bytes()).hexdigest(),'exposed_data':True,'market_cap_groups':'NOT RUN: no survivorship-safe point-in-time market-cap history for 2014-2019. Price proxy forbidden.','periods':{}}
    for name,ev,m,z,st,en,prof in [('2017',e17,m17,z17,'2017-01-25','2017-12-27',json.loads(P17.read_text())),('2018_2019',e19,m19,z19,'2018-01-24','2019-12-25',json.loads(P19.read_text()))]:
        print(f'audit: summarising {name}', flush=True)
        r52=[x for x in ev if x['horizon']=='52w']; r8=[x for x in ev if x['horizon']=='8w']; contrib=defaultdict(list)
        for x in r8:contrib[x['kod']].append(x['ret'])
        loo=[]
        for k in contrib:
            q=[x for x in r8 if x['kod']!=k]
            loo.append(summ([x for x in q if x['group']=='KEEP20'])['mean_return']-summ([x for x in q if x['group']=='DROP10'])['mean_return'])
        cutoff=np.quantile(np.abs([q['ret'] for q in r8 if q['ret'] is not None]),.99)
        trim=[x for x in r8 if x['ret'] is not None and abs(x['ret'])<=cutoff]
        result['periods'][name]={'keep_drop_by_horizon':{h:{'keep':summ([x for x in ev if x['horizon']==h and x['group']=='KEEP20']),'drop':summ([x for x in ev if x['horizon']==h and x['group']=='DROP10'])} for h in HN.values()},'winner_retention_52w':winner(ev),'by_year_8w':diffs(r8,'year'),'by_regime_8w':diffs(r8,'regime'),'by_vol_regime_8w':diffs(r8,'vol_regime'),'by_static_sector_8w':diffs(r8,'sector_static'),'feature_importance_and_profiles':prof,'leave_one_stock_out_8w':{'stocks':len(contrib),'median_diff':round(float(np.median(loo)),4),'min_diff':round(float(np.min(loo)),4),'max_diff':round(float(np.max(loo)),4)},'trimmed_99pct_8w':{'keep':summ([x for x in trim if x['group']=='KEEP20']),'drop':summ([x for x in trim if x['group']=='DROP10'])},'topn_sensitivity':topn(d,m,z,st,en)}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    md=['# H0 → Extra Trees Top-20 Mechanism & Stability Audit','','Status: EXPOSED-DATA RESEARCH. H0 is unchanged. Full machine-readable detail: `h0_extratrees_top20_mechanism_audit_results.json`.','',f"Market-cap groups: {result['market_cap_groups']}",'']
    for p,v in result['periods'].items():
        a=v['keep_drop_by_horizon'];md += [f'## {p}','', '| Horizon | KEEP mean | DROP mean | KEEP median | DROP median |', '|---|---:|---:|---:|---:|']+[f"| {h} | {a[h]['keep']['mean_return']:.2%} | {a[h]['drop']['mean_return']:.2%} | {a[h]['keep']['median_return']:.2%} | {a[h]['drop']['median_return']:.2%} |" for h in HN.values() if a[h]['keep']['mean_return'] is not None]
        md += ['',f"52w winner retention: KEEP20 {v['winner_retention_52w']['KEEP20']:.1%}; DROP10 {v['winner_retention_52w']['DROP10']:.1%}.", '', 'Top permutation features: '+', '.join(x['feature'] for x in v['feature_importance_and_profiles'][:8])+'.','']
    REPORT.write_text('\n'.join(md)+'\n')
    print('wrote',OUT.name,REPORT.name,flush=True)
if __name__=='__main__':main()
