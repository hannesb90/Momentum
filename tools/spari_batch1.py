#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import spearmanr

from decision_portfolio_v2 import V2,annualized,dump,evaluation,ic_metrics,manifest
from decision_portfolio_v3_execution import build_portfolio,execution_returns

ROOT=V2;RI=ROOT/'research_i';OUT=RI/'results/SPARI_BATCH1_V1';COST=.002;N=30
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
PROTECTED=('panels','validated','spard','spare','sparf','sparg','trackh','repair_df')
def protected_hashes():return {p.relative_to(ROOT).as_posix():sha(p) for x in PROTECTED for p in sorted((ROOT/x).rglob('*')) if p.is_file()}
def verify_prereg():
 f=json.loads((RI/'I0_FREEZE.json').read_text())
 for x in f['files']:assert sha(ROOT/x['path'])==x['sha256'],x['path']
 p=json.loads((RI/'batch1_preregistration.json').read_text())
 for path,h in p['locked_inputs'].items():assert sha(ROOT/path)==h,path
 assert not OUT.exists(),'Batch 1 output already exists; no overwrite'
 return p,f
def load():
 rows=json.loads((ROOT/'panels/core_panel.json').read_text());fund=json.loads((ROOT/'panels/core_fundamenta_panel.json').read_text())
 cols=['kod','panel_date','price_date','mom_52w','mom_12_1','residual_momentum_52w','trend_consistency_52w','trend_strength_52w','max_drawdown_52w','vol_52w','market_regime_vol']
 d=pd.DataFrame([{k:r.get(k) for k in cols} for r in rows]);ff=pd.DataFrame([{'kod':r['kod'],'panel_date':r['panel_date'],'has_fundamenta':r.get('has_fundamenta'),'fundamenta_days_since':r.get('fundamenta_days_since'),'return_since_last_report_ttm':r.get('return_since_last_report_ttm')} for r in fund])
 prices=json.loads((ROOT/'validated/prices/prices_validated.json').read_text());series={k:(np.array([np.datetime64(r['d']) for r in rs]),np.array([r['adj'] for r in rs],float)) for k,rs in prices.items()}
 def val(k,date,weeks):
  ds,vs=series[k];t=np.datetime64(date);goal=t-np.timedelta64(7*weeks,'D');i=np.searchsorted(ds,t,'right')-1;j=np.searchsorted(ds,goal,'right')-1
  return np.nan if i<0 or j<0 or int((goal-ds[j])/np.timedelta64(1,'D'))>10 else vs[i]/vs[j]-1
 d['mom_12m']=[val(k,x,52) for k,x in zip(d.kod,d.panel_date)];d['mom_18m']=[val(k,x,78) for k,x in zip(d.kod,d.panel_date)]
 assert np.nanmax(np.abs(d.mom_12m-d.mom_52w))<1e-12
 d=d.merge(ff,on=['kod','panel_date'],how='left',validate='one_to_one')
 return d,prices
def ranked_score(d,col):
 z=d[['kod','panel_date',col]].copy();z['score']=z[col].fillna(z.groupby('panel_date')[col].transform('median'));return z[['kod','panel_date','score']]
def champion_scores(d):
 z=d[['kod','panel_date','mom_12m','mom_18m']].copy();a=z.groupby('panel_date').mom_12m.rank(pct=True);b=z.groupby('panel_date').mom_18m.rank(pct=True);z['score']=(a+b)/2;z['score']=z.score.fillna(z.groupby('panel_date').score.transform('median'));return z[['kod','panel_date','score']]
def blend(champ,factor):
 z=champ.merge(factor,on=['kod','panel_date'],suffixes=('_c','_f'),validate='one_to_one');a=z.groupby('panel_date').score_c.rank(pct=True);b=z.groupby('panel_date').score_f.rank(pct=True);z['score']=(a+b)/2;return z[['kod','panel_date','score']]
def oos(z):return z[(z.panel_date>='2024-01-01')&(z.panel_date<='2025-12-31')].copy()
def extra_metrics(metrics,art,pret,cost=COST):
 contrib=defaultdict(float)
 weights={(r['panel_date'],r['kod']):r['weight'] for r in art['holdings']}
 for p in art['returns']:
  for (dt,k),w in weights.items():
   if dt==p['panel_date']:contrib[k]+=w*pret.get((k,dt),0)
 ranked=sorted(contrib.items(),key=lambda x:x[1],reverse=True);total=sum(v for _,v in ranked)
 def leave(n):
  excluded={k for k,_ in ranked[:n]};rr=[]
  for p in art['returns']:
   dt=p['panel_date'];gross=sum(w*pret.get((k,dt),0) for (x,k),w in weights.items() if x==dt and k not in excluded);rr.append(gross-p['transaction_cost'])
  return annualized(rr)
 metrics={**metrics,'top5_tickers':[k for k,_ in ranked[:5]],'leave_top5_out_cagr':leave(5),'top3_arithmetic_contribution_share':sum(v for _,v in ranked[:3])/total if total else None,'top5_arithmetic_contribution_share':sum(v for _,v in ranked[:5])/total if total else None}
 return metrics,ranked
def assess(scores,name,targets,pret,emeta):
 s=oos(scores);ic=ic_metrics(s,targets,n=N);pm,art=build_portfolio(s,n=N,every=2,cost=COST,model=name,returns_map=pret,execution_meta=emeta);pm,contrib=extra_metrics(pm,art,pret);return {'ic':ic,'portfolio':pm,'ticker_contribution':contrib},art
def weekly_features(prices,d):
 wanted=d[(d.panel_date>='2024-01-01')&(d.panel_date<='2025-12-31')][['kod','panel_date']];out=[]
 for k,g in wanted.groupby('kod'):
  rs=prices[k];x=pd.Series([r['adj'] for r in rs],index=pd.to_datetime([r['d'] for r in rs])).sort_index();wr=x.resample('W-FRI').last().dropna().pct_change()
  for date in g.panel_date:
   w=wr.loc[:date].tail(52).dropna();jump=(1-float(w.abs().max()/w.abs().sum())) if len(w)>=26 and w.abs().sum()>0 else None;cons=float((w>0).mean()) if len(w)>=26 else None
   out.append({'kod':k,'panel_date':date,'jump_diffuseness_52w_spec':jump,'trend_consistency_rebuilt':cons})
 return pd.DataFrame(out)
def weighted_overlay(champ,d,pret,emeta,kind):
 s=oos(champ);lookup=d.set_index(['kod','panel_date']);dates=sorted(s.panel_date.unique());prev={};hold=[];trades=[];periods=[];contrib=defaultdict(float)
 for ix,date in enumerate(dates):
  g=s[s.panel_date==date].sort_values(['score','kod'],ascending=[False,False]);reb=ix%2==0 or not prev
  if reb:
   ids=list(g.head(N).kod)
   if kind=='inverse_vol':
    vv=np.array([lookup.loc[(k,date),'vol_52w'] for k in ids],float);med=np.nanmedian(vv[(vv>0)&np.isfinite(vv)]);vv=np.where((vv>0)&np.isfinite(vv),vv,med);raw=1/vv;ws=raw/raw.sum()
   else:
    mv=float(lookup.loc[(ids[0],date),'market_regime_vol']);exposure=min(1.0,0.10/(math.sqrt(52)*mv)) if mv>0 else 1.0;ws=np.repeat(exposure/N,N)
   cur=dict(zip(ids,map(float,ws)))
  else:cur=prev.copy()
  turn=sum(max(0,cur.get(k,0)-prev.get(k,0)) for k in set(cur)|set(prev));gross=sum(w*pret.get((k,date),0) for k,w in cur.items());net=gross-COST*turn;bench=float(np.mean([pret.get((k,date),0) for k in g.kod]));evaluable=any(emeta.get((k,date),{}).get('next_panel_date') for k in g.kod)
  for k,w in cur.items():hold.append({'model':kind,'panel_date':date,'kod':k,'weight':w,'rebalance':reb});contrib[k]+=w*pret.get((k,date),0)
  if reb:
   for k in sorted(set(cur)|set(prev)):
    delta=cur.get(k,0)-prev.get(k,0)
    if abs(delta)>1e-15:trades.append({'model':kind,'panel_date':date,'kod':k,'side':'BUY' if delta>0 else 'SELL','weight_change':delta,'execution_price_date':emeta.get((k,date),{}).get('entry_execution_date')})
  if evaluable:periods.append({'model':kind,'panel_date':date,'gross_return':gross,'net_return':net,'benchmark_return':bench,'turnover':turn,'transaction_cost':COST*turn,'rebalance':reb})
  prev=cur
 nr=np.array([x['net_return'] for x in periods]);br=np.array([x['benchmark_return'] for x in periods]);ex=nr-br;wealth=np.cumprod(1+nr);dd=wealth/np.maximum.accumulate(wealth)-1;ranked=sorted(contrib.items(),key=lambda x:x[1],reverse=True)
 def leave(n):
  bad={k for k,_ in ranked[:n]};rr=[]
  for p in periods:rr.append(sum(r['weight']*pret.get((r['kod'],p['panel_date']),0) for r in hold if r['panel_date']==p['panel_date'] and r['kod'] not in bad)-p['transaction_cost'])
  return annualized(rr)
 pm={'cagr_net':annualized(nr.tolist()),'benchmark_cagr':annualized(br.tolist()),'annualized_excess':annualized(nr.tolist())-annualized(br.tolist()),'sharpe_excess':float(ex.mean()/ex.std(ddof=1)*math.sqrt(13)),'max_drawdown':float(dd.min()),'mean_turnover':float(np.mean([x['turnover'] for x in periods])),'leave_top3_out_cagr':leave(3),'leave_top5_out_cagr':leave(5),'top3_tickers':[k for k,_ in ranked[:3]],'top5_tickers':[k for k,_ in ranked[:5]]}
 return pm,{'rankings':[],'holdings':hold,'trades':trades,'returns':periods},ranked
def alpha_class(x,champ):
 a,b=x['ic'],champ['ic'];pa,pb=x['portfolio'],champ['portfolio'];full=a['mean_ic52']>=b['mean_ic52']+.01 and a['median_ic52']>=b['median_ic52'] and a['mean_topN_ic52']>=b['mean_topN_ic52'] and a['positive_ic_share']>=b['positive_ic_share'] and all(v['mean_ic52']>0 for v in a['calendar_year'].values()) and (pa['leave_top3_out_cagr']-pa['benchmark_cagr']) >= (pb['leave_top3_out_cagr']-pb['benchmark_cagr'])
 direction=a['mean_ic52']>b['mean_ic52'] or a['mean_topN_ic52']>b['mean_topN_ic52']
 return 'STÖD' if full else ('SVAGT STÖD' if direction else 'INGET STÖD')
def main():
 prereg,freeze=verify_prereg();scope_before=protected_hashes();d,prices=load();pret,emeta=execution_returns();targets=evaluation(d);champ=champion_scores(d);base=ranked_score(d,'mom_52w');results={};artifacts={'rankings':[],'holdings':[],'trades':[],'returns':[]};tested=0
 refs={}
 for name,s in [('pure_12m',base),('frozen_champion',champ)]:
  refs[name],a=assess(s,name,targets,pret,emeta)
  for k in artifacts:artifacts[k]+=a[k]
 # Report data gate plus explicitly non-decisional raw drift diagnostic.
 q=d[(d.panel_date>='2024-01-01')&(d.panel_date<='2025-12-31')];cover=float(q.return_since_last_report_ttm.notna().mean());stale=q.loc[q.return_since_last_report_ttm.notna(),'fundamenta_days_since'];report_score=d[d.return_since_last_report_ttm.notna()][['kod','panel_date','return_since_last_report_ttm']].rename(columns={'return_since_last_report_ttm':'score'});report_ic=ic_metrics(oos(report_score),targets,n=N)
 results['report_attention_pead']={'classification':'KAN INTE TESTAS KORREKT','coverage':cover,'days_since_min_median_max':[int(stale.min()),float(stale.median()),int(stale.max())],'diagnostic_raw_report_drift_ic':report_ic,'reason':'Only date-level report provenance and accumulated return exist; no verified publication time, initial reaction window, QA-approved event turnover or surprise. Fundamental survivorship also prevents a comparable portfolio.'};tested+=1
 results['dividend_gap']={'classification':'KAN INTE TESTAS KORREKT','reason':'V2 registry explicitly excludes dividend_yield_ttm and has no QA-approved PIT per-share dividend-change event chain.'}
 # Dispersion is a date-common regime proxy, never a cross-sectional factor.
 icpd={r['panel_date']:r['ic52'] for r in refs['frozen_champion']['ic']['per_date']};disp=q.groupby('panel_date').mom_12_1.std();z=pd.DataFrame({'dispersion':disp,'ic':[icpd.get(x) for x in disp.index]}).dropna();rho=float(spearmanr(z.dispersion,z.ic).statistic);med=z.dispersion.median();lo=z[z.dispersion<=med].ic.mean();hi=z[z.dispersion>med].ic.mean();results['dispersion_proxy']={'classification':'SVAGT STÖD' if abs(rho)>=.3 and np.sign(lo-hi)==np.sign(-rho) else 'INGET STÖD','definition':'price proxy, not analyst dispersion','n_panel_dates':len(z),'spearman_proxy_vs_champion_ic':rho,'low_dispersion_mean_ic':float(lo),'high_dispersion_mean_ic':float(hi)};tested+=1
 results['insider_gap']={'classification':'KAN INTE TESTAS KORREKT','reason':'No manifested PIT FI transaction source in frozen V2 inputs; legacy name-matched cache is forbidden.'}
 # Alpha factors: solo and fixed preregistered 50/50 blend.
 factor_defs={'residual_momentum':'residual_momentum_52w','trend_consistency':'trend_consistency_rebuilt','trend_strength':'trend_strength_52w','drawdown_resilience':'drawdown_resilience'}
 d['drawdown_resilience']=-d.max_drawdown_52w.abs();wf=weekly_features(prices,d);d=d.merge(wf,on=['kod','panel_date'],how='left',validate='one_to_one');max_cons=float(np.nanmax(np.abs(d.trend_consistency_52w-d.trend_consistency_rebuilt)));factor_defs['jump_diffuseness']='jump_diffuseness_52w_spec'
 alpha={}
 for name,col in factor_defs.items():
  fs=ranked_score(d,col);bs=blend(champ,fs);solo,aa=assess(fs,name+'_solo',targets,pret,emeta);bl,ab=assess(bs,name+'_blend',targets,pret,emeta)
  for art in (aa,ab):
   for k in artifacts:artifacts[k]+=art[k]
  alpha[name]={'classification':alpha_class(bl,refs['frozen_champion']),'solo':solo,'blend':bl};tested+=1
 results['residual_momentum']=alpha.pop('residual_momentum');results['momentum_quality']={'classification':max((x['classification'] for x in alpha.values()),key=lambda x:['INGET STÖD','SVAGT STÖD','STÖD'].index(x)),'trend_consistency_rebuild_max_abs_diff':max_cons,'already_tested_not_rerun':['risk_adj_momentum_52w','mom_52w_over_downside_vol'],'variants':alpha}
 # Risk overlays preserve champion selection.
 risk={}
 for name,kind in [('inverse_vol_sizing','inverse_vol'),('target_vol','target_vol')]:
  pm,a,tc=weighted_overlay(champ,d,pret,emeta,kind);cp=refs['frozen_champion']['portfolio'];ok=pm['sharpe_excess']>cp['sharpe_excess'] and pm['max_drawdown']>=cp['max_drawdown']+.01 and pm['annualized_excess']>=cp['annualized_excess']-.02 and pm['mean_turnover']<=cp['mean_turnover']+1e-12 and (pm['leave_top3_out_cagr']-pm['benchmark_cagr']) >= (cp['leave_top3_out_cagr']-cp['benchmark_cagr'])-.01;risk[name]={'classification':'RISKFÖRBÄTTRING' if ok else 'INGET STÖD','portfolio':pm,'ticker_contribution':tc,'rankings_unchanged':True}
  for k in artifacts:artifacts[k]+=a[k]
  tested+=1
 results.update(risk);results['references']=refs;results['multiple_testing']={'hypothesis_families':8,'actual_variants_results_reviewed':tested,'preregistered_variants':9,'diagnostic_followups':0,'failed_variants_retained':True}
 OUT.mkdir(parents=True)
 for name,obj in results.items():dump(OUT/(name+'.json'),obj)
 for k,v in artifacts.items():dump(OUT/(k+'.json'),v)
 scope_after=protected_hashes();dump(OUT/'protected_scope_audit.json',{'status':'PASS' if scope_before==scope_after else 'FAIL','files':len(scope_before),'before_aggregate':hashlib.sha256(json.dumps(scope_before,sort_keys=True).encode()).hexdigest(),'after_aggregate':hashlib.sha256(json.dumps(scope_after,sort_keys=True).encode()).hexdigest(),'changed':sorted(k for k in set(scope_before)|set(scope_after) if scope_before.get(k)!=scope_after.get(k))});assert scope_before==scope_after
 dump(OUT/'run_provenance.json',{'run_id':prereg['run_id'],'I0_freeze_sha256':sha(RI/'I0_FREEZE.json'),'preregistration_sha256':sha(RI/'batch1_preregistration.json'),'input_hashes':prereg['locked_inputs'],'code_sha256':sha(ROOT/'tools/spari_batch1.py'),'decision_rows':len(d),'target_evaluation_rows':len(targets),'oos_panel_dates':sorted(oos(champ).panel_date.unique()),'target_never_used_for_selection':True})
 dump(OUT/'manifest.json',manifest(OUT));print(json.dumps({'status':'COMPLETE','out':str(OUT),'tested':tested},indent=2))
if __name__=='__main__':main()
