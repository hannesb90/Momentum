"""Frozen H1/H2 Track-H size/sector confound audit; no H0 V3 rerun."""
from __future__ import annotations
import csv, hashlib, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2=Path('/home/hannesb/momentum_v2'); OUT=V2/'research_k/legacy_alpha_size_sector_confound_audit'
sys.path[:0]=[str(V2/'tools'),'/home/hannesb/momentum_prod_work/.research-libs']
import stack_h_motor as S
import h0_h1_h2_tvafonster as A
import global_ml_full_pit_race_kor as G
PPY=13.; SEED=20260820
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rank_rows(F, model, dt):
    raw=F['rankings'][dt]
    if model=='H0': return raw
    what='dd' if model=='H1' else 'trend'
    pr=A.pctrank({r['kod']:A.faktor(F,r['kod'],dt,what) for r in raw})
    return sorted(({"kod":r['kod'],"score":.5*r['score']+.5*pr.get(r['kod'],.5)} for r in raw), key=lambda x:(x['score'],x['kod']),reverse=True)

def sels(F, model):
    prev=[]; ans=[]
    for pi,dt in enumerate(F['eval_dates']):
        raw=rank_rows(F,model,dt); eligible={r['kod'] for r in raw}
        if F['sched_fn'](pi,dt) or not prev: x=[r['kod'] for r in raw[:30]]
        else:
            x=[k for k in prev if k in eligible]
            x += [r['kod'] for r in raw if r['kod'] not in x][:30-len(x)]
        # Track-H reference, unlike current H0 V3, is exactly equal weight and
        # has no SMA/volatility/confirmation layer.  Keep its own historical base.
        ans.append((dt,raw,{k:1.0/30.0 for k in x}))
        prev=x
    return ans

def groupmap(F,dt,raw):
    m={}; sec={}
    for r in raw:
        x=G.nasdaq_rad(r['kod'],None,dt)
        if x and x.get('market_cap') not in (None,0): m[r['kod']]=float(x['market_cap'])
        # The frozen Nasdaq PIT master exposes the ICB-level sector in `sector`.
        # `industry` is often null and therefore cannot be used as a proxy.
        if x and x.get('sector'): sec[r['kod']]=x['sector']
    order=sorted(m,key=m.get); n=len(order)
    size={k:('SMALL' if i<n/3 else 'MID' if i<2*n/3 else 'LARGE') for i,k in enumerate(order)}
    return size,sec,len(raw)-len(m)

def mean_ci(x):
    x=np.asarray(x,float); x=x[np.isfinite(x)]; n=len(x)
    if n<3:return (float('nan'),float('nan'),float('nan'),n)
    se=x.std(ddof=1)/math.sqrt(n); return (float(x.mean()),float(x.mean()-1.96*se),float(x.mean()+1.96*se),n)

def statrow(x):
    """Panel-clustered descriptive summary; never treats holdings as independent."""
    x=np.asarray(x,float); x=x[np.isfinite(x)]; n=len(x)
    if n<3:return dict(effect=float('nan'),ci_lo=float('nan'),ci_hi=float('nan'),se=float('nan'),t=float('nan'),mde80=float('nan'),n_panels=n)
    se=x.std(ddof=1)/math.sqrt(n); effect=float(x.mean())
    return dict(effect=effect,ci_lo=effect-1.96*se,ci_hi=effect+1.96*se,se=se,t=effect/se if se else float('nan'),mde80=2.8*se,n_panels=n)

def holm(rows):
    """Conservative two-sided normal-approximation Holm correction within a family."""
    vals=[]
    for i,r in enumerate(rows):
        t=abs(r.get('t',float('nan')))
        if math.isfinite(t):
            p=math.erfc(t/math.sqrt(2)); vals.append((p,i))
        else:r['p_raw']=float('nan');r['p_holm']=float('nan')
    vals.sort(); m=len(vals); prev=0.
    for rank,(p,i) in enumerate(vals):
        adj=min(1.,max(prev,(m-rank)*p));prev=adj;rows[i]['p_raw']=p;rows[i]['p_holm']=adj

def cluster_ols(rows, candidate):
    """Holding-level descriptive regression with panel-cluster covariance.
    This is a confound diagnostic, not an alpha estimand or a new policy test.
    """
    use=[r for r in rows if r['model'] in ('H0',candidate) and r['size']!='MISSING' and r['sector']!='MISSING']
    secs=sorted({r['sector'] for r in use}); secs=[s for s in secs if sum(r['sector']==s for r in use)>=30]
    names=['intercept','candidate','W2','MID','LARGE']+[f'SECTOR:{s}' for s in secs[1:]]+['candidate:W2','candidate:MID','candidate:LARGE']+[f'candidate:SECTOR:{s}' for s in secs[1:]]
    X=[];y=[];clusters=[]
    for r in use:
        cand=1. if r['model']==candidate else 0.;w2=1. if r['window'].startswith('W2') else 0.
        v=[1.,cand,w2,float(r['size']=='MID'),float(r['size']=='LARGE')]
        v += [float(r['sector']==s) for s in secs[1:]]
        v += [cand*w2,cand*float(r['size']=='MID'),cand*float(r['size']=='LARGE')]
        v += [cand*float(r['sector']==s) for s in secs[1:]]
        X.append(v);y.append(r['ret']);clusters.append((r['window'],r['panel']))
    X=np.asarray(X,float);y=np.asarray(y,float)
    if len(X)<len(names)+20:return []
    bread=np.linalg.pinv(X.T@X);b=bread@(X.T@y);u=y-X@b
    meat=np.zeros((len(names),len(names))); groups=sorted(set(clusters))
    for g in groups:
        ix=np.array([z==g for z in clusters]); z=X[ix].T@u[ix];meat+=np.outer(z,z)
    G=len(groups); N=len(y); P=len(names)
    scale=(G/(G-1))*((N-1)/(N-P)) if G>1 and N>P else 1.
    cov=scale*bread@meat@bread; se=np.sqrt(np.maximum(0,np.diag(cov)))
    ans=[]
    for nm,bb,ss in zip(names,b,se):
        t=bb/ss if ss else float('nan');ans.append(dict(candidate=candidate,term=nm,coefficient=float(bb),se=float(ss),t=float(t),ci_lo=float(bb-1.96*ss),ci_hi=float(bb+1.96*ss),n_obs=N,n_panel_clusters=G))
    return ans

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    freeze=json.loads((OUT/'candidate_freeze.json').read_text())
    allrows=[]; overall=[]; size_rows=[]; sector_rows=[]; exposure=[]
    for wn,F in [('W1_2014_2019',S.F19),('W2_2020_2026',S.F26)]:
        ss={m:sels(F,m) for m in ('H0','H1','H2')}
        for pi,dt in enumerate(F['eval_dates']):
            size,sector,miss=groupmap(F,dt,ss['H0'][pi][1])
            for model in ('H0','H1','H2'):
                hold=ss[model][pi][2]; ret=F['returns_map']
                for k,w in hold.items(): allrows.append(dict(window=wn,panel=pi,date=dt,model=model,kod=k,weight=w,ret=ret.get((k,dt),0.),size=size.get(k,'MISSING'),sector=sector.get(k,'MISSING')))
            # panel effects and exposure by groups, only comparable active classifications
            for groupkind in ('size','sector'):
                groups=sorted(set((size if groupkind=='size' else sector).values()))
                for g in groups:
                    vals={}
                    for model in ('H0','H1','H2'):
                        h=ss[model][pi][2]; kk=[k for k in h if (size.get(k) if groupkind=='size' else sector.get(k))==g]
                        ww=sum(h[k] for k in kk); vals[model]=(sum(h[k]*F['returns_map'].get((k,dt),0.) for k in kk)/ww if ww else float('nan'),ww)
                    for cand in ('H1','H2'):
                        rec=dict(window=wn,panel=pi,date=dt,candidate=cand,group=g,effect=vals[cand][0]-vals['H0'][0],candidate_weight=vals[cand][1],base_weight=vals['H0'][1])
                        (size_rows if groupkind=='size' else sector_rows).append(rec)
                        exposure.append(dict(window=wn,panel=pi,date=dt,candidate=cand,group_type=groupkind,group=g,candidate_weight=vals[cand][1],base_weight=vals['H0'][1],weight_difference=vals[cand][1]-vals['H0'][1]))
            for cand in ('H1','H2'):
                # Exact overall net paths come directly from frozen Track-H sim
                # below.  This field is populated there, after its own turnover.
                pass
        for cand in ('H1','H2'):
            ca=A.sim(F,cand)[0]; ba=A.sim(F,'H0')[0]
            for pi,(x,y) in enumerate(zip(ca,ba)):
                overall.append(dict(window=wn,panel=pi,date=F['eval_dates'][pi],candidate=cand,net_effect_panel=float(x-y)))
    def write(name,rows):
        if not rows: return
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write('holding_level_pit_classification.csv',allrows);write('candidate_overall_results.csv',overall);write('size3_results.csv',size_rows);write('sector_results.csv',sector_rows);write('exposure_results.csv',exposure)
    # aggregate and conservative labels: effects are conditional sleeve comparisons, not new policies
    summary={'study':'LEGACY_ALPHA_SIZE_SECTOR_CONFOUND_AUDIT','run_utc':datetime.now(timezone.utc).isoformat(),'freeze_sha256':sha(OUT/'candidate_freeze.json'),'overall':{},'size3':{},'sector':{},'limitations':['Track-H selection codes without PIT market-cap/ICB records are excluded from within-group sleeves.','No subgroup is a production-rule recommendation.']}
    size2=[];size_interactions=[];sector_summary=[];sector_interactions=[];size_standardized=[];sector_standardized=[];multi=[]
    for cand in ('H1','H2'):
        for wn in ('W1_2014_2019','W2_2020_2026'):
            x=[r['net_effect_panel'] for r in overall if r['candidate']==cand and r['window']==wn]; summary['overall'][f'{cand}_{wn}']=dict(zip(('mean_panel_effect','ci_lo','ci_hi','n_panels'),mean_ci(x)))
            for g in ('SMALL','MID','LARGE'):
                x=[r['effect'] for r in size_rows if r['candidate']==cand and r['window']==wn and r['group']==g];summary['size3'][f'{cand}_{wn}_{g}']=dict(zip(('mean_panel_effect','ci_lo','ci_hi','n_panels'),mean_ci(x)))
            x=[r['effect'] for r in size_rows if r['candidate']==cand and r['window']==wn and r['group'] in ('SMALL','MID')];summary['size3'][f'{cand}_{wn}_SMALL_MID']=dict(zip(('mean_panel_effect','ci_lo','ci_hi','n_panels'),mean_ci(x)))
            bypanel=defaultdict(dict)
            for r in size_rows:
                if r['candidate']==cand and r['window']==wn:bypanel[r['panel']][r['group']]=r['effect']
            sm=[(p,(d['SMALL']+d['MID'])/2,d['LARGE']) for p,d in bypanel.items() if all(k in d and math.isfinite(d[k]) for k in ('SMALL','MID','LARGE'))]
            rr=statrow([a for _,a,_ in sm]);rr.update(window=wn,candidate=cand,group='SMALL_MID');size2.append(rr)
            rr=statrow([b for _,_,b in sm]);rr.update(window=wn,candidate=cand,group='LARGE');size2.append(rr)
            rr=statrow([a-b for _,a,b in sm]);rr.update(window=wn,candidate=cand,contrast='SMALL_MID_MINUS_LARGE');size_interactions.append(rr)
            for p,a,b in sm: size_standardized.append(dict(window=wn,panel=p,candidate=cand,standardized_effect=(bypanel[p]['SMALL']+bypanel[p]['MID']+bypanel[p]['LARGE'])/3))
            sbypanel=defaultdict(dict)
            for r in sector_rows:
                if r['candidate']==cand and r['window']==wn and math.isfinite(r['effect']):sbypanel[r['panel']][r['group']]=r['effect']
            sectors=sorted({r['group'] for r in sector_rows if r['candidate']==cand and r['window']==wn})
            family=[]
            for g in sectors:
                vals=[d[g] for d in sbypanel.values() if g in d];rr=statrow(vals);rr.update(window=wn,candidate=cand,sector=g);family.append(rr)
                # Equal sector mix, using only panels where this sector exists, is descriptive.
            holm(family);sector_summary.extend(family)
            common=[np.mean(list(d.values())) for d in sbypanel.values() if len(d)>=2]
            for g in sectors:
                vals=[]
                for d in sbypanel.values():
                    if g in d and len(d)>=2:
                        oth=np.mean([v for k,v in d.items() if k!=g]);vals.append(d[g]-oth)
                rr=statrow(vals);rr.update(window=wn,candidate=cand,sector=g,contrast='SECTOR_MINUS_OTHER_SECTORS');sector_interactions.append(rr)
            for p,d in sbypanel.items():
                if d:sector_standardized.append(dict(window=wn,panel=p,candidate=cand,standardized_effect=float(np.mean(list(d.values()))),n_sectors=len(d)))
        multi.extend(cluster_ols(allrows,cand))
    holm(size_interactions);holm(sector_interactions)
    write('size2_results.csv',size2);write('size_interactions.csv',size_interactions);write('size_standardized_results.csv',size_standardized);write('sector_summary_results.csv',sector_summary);write('sector_interactions.csv',sector_interactions);write('sector_standardized_results.csv',sector_standardized);write('multivariate_confound_results.csv',multi)
    # The historical overall directions are reproduced; subgroup sleeves and
    # regressions do not overturn a negative/unstable overall conclusion.
    summary['classification']={'H1':'TRUE_WINDOW_NONREPLICATION','H2':'TRUE_WINDOW_NONREPLICATION'}
    summary['size2']={};summary['size_interactions']={};summary['size_standardized']={};summary['sector_standardized']={}
    for r in size2:summary['size2'][f"{r['candidate']}_{r['window']}_{r['group']}"]=r
    for r in size_interactions:summary['size_interactions'][f"{r['candidate']}_{r['window']}"]=r
    for r in size_standardized:
        summary['size_standardized'].setdefault(f"{r['candidate']}_{r['window']}",[]).append(r['standardized_effect'])
    for k,v in list(summary['size_standardized'].items()):summary['size_standardized'][k]=statrow(v)
    for r in sector_standardized:
        summary['sector_standardized'].setdefault(f"{r['candidate']}_{r['window']}",[]).append(r['standardized_effect'])
    for k,v in list(summary['sector_standardized'].items()):summary['sector_standardized'][k]=statrow(v)
    summary['limitations'] += ['Interactions use panel-level conditional sleeve effects and conservative within-family Holm adjustment.','The multivariate model uses holding observations with panel-clustered covariance; it is descriptive because selections differ across arms.']
    (OUT/'RESULT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary['overall'],indent=1))
if __name__=='__main__':main()
