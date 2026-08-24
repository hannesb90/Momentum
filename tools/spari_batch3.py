#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import pearsonr
from spari_batch1 import ROOT,RI,COST,N,load,champion_scores,oos,assess,extra_metrics,sha
from decision_portfolio_v2 import annualized,dump,evaluation,ic_metrics,manifest
from decision_portfolio_v3_execution import build_portfolio,execution_returns

OUT=RI/'results/SPARI_BATCH3_FINAL_LEGACY_V1';PRE=RI/'batch3_preregistration.json';FREEZE=RI/'I3_PREREG_FREEZE.json';THRESH=.85
def verify():
 f=json.loads(FREEZE.read_text())
 for x in f['files']:assert sha(ROOT/x['path'])==x['sha256'],x['path']
 assert not OUT.exists(),'no overwrite';return json.loads(PRE.read_text())
def rank_score(d,col):
 z=d[['kod','panel_date',col]].dropna().copy();z['score']=z.groupby('panel_date')[col].rank(pct=True);return z[['kod','panel_date','score']]
def blend_exact(a,b):
 z=a.merge(b,on=['kod','panel_date'],suffixes=('_h0','_factor'),validate='one_to_one');z['score']=.5*z.score_h0.rank(pct=True)+.5*z.score_factor.rank(pct=True);return z[['kod','panel_date','score']]
def delta_ic(x,b):return {k:x[k]-b[k] for k in ('mean_ic52','median_ic52','mean_topN_ic52','positive_ic_share')}
def corr_order(champ,prices):
 weekly={}
 for k,rs in prices.items():
  s=pd.Series([r['adj'] for r in rs],index=pd.to_datetime([r['d'] for r in rs])).sort_index();weekly[k]=s.resample('W-FRI').last().pct_change()
 out=[];diag=[]
 for dt,g in champ.groupby('panel_date'):
  ordered=list(g.sort_values(['score','kod'],ascending=[False,False]).kod);chosen=[];rejected=[];missing=0;lo=pd.Timestamp(dt)-pd.Timedelta(days=182);hi=pd.Timestamp(dt)
  for k in ordered:
   ok=True
   for h in chosen:
    q=pd.concat([weekly[k].loc[lo:hi],weekly[h].loc[lo:hi]],axis=1).dropna()
    if len(q)<13:missing+=1;continue
    c=float(q.corr().iloc[0,1])
    if c>THRESH:ok=False;break
   if ok:chosen.append(k)
   else:rejected.append(k)
   if len(chosen)>=N:break
  selected=set(chosen);rank={k:i for i,k in enumerate(ordered)}
  for k in ordered:out.append({'kod':k,'panel_date':dt,'score':2-rank[k]/10000 if k in selected else 1-rank[k]/10000,'correlation_selected':k in selected})
  diag.append({'panel_date':dt,'selected':chosen,'rejected_before_fill':rejected,'n_rejected':len(rejected),'missing_pair_comparisons':missing,'filled':len(chosen)})
 return pd.DataFrame(out),diag
def port_blocks(art):
 out={}
 for y in sorted({r['panel_date'][:4] for r in art['returns']}):
  z=[r for r in art['returns'] if r['panel_date'].startswith(y)];nr=[r['net_return'] for r in z];br=[r['benchmark_return'] for r in z];out[y]={'cagr':annualized(nr),'benchmark_cagr':annualized(br),'excess_cagr':annualized(nr)-annualized(br),'n_periods':len(z)}
 return out
def bootstrap_delta_ic(a,b,draws=5000):
 aa={r['panel_date']:r['ic52'] for r in a['per_date']};bb={r['panel_date']:r['ic52'] for r in b['per_date']};d=np.array([aa[k]-bb[k] for k in sorted(set(aa)&set(bb))]);rng=np.random.default_rng(20260809);vals=[]
 for _ in range(draws):
  x=[]
  while len(x)<len(d):
   i=int(rng.integers(0,max(1,len(d)-1)));x.extend(d[i:i+2])
  vals.append(float(np.mean(x[:len(d)])))
 return {'draws':draws,'block_panel_dates':2,'delta_mean_ic_ci95':[float(np.percentile(vals,2.5)),float(np.percentile(vals,97.5))],'probability_positive':float(np.mean(np.array(vals)>0))}
def main():
 pre=verify();d,prices=load();fund=pd.DataFrame(json.loads((ROOT/'panels/core_fundamenta_panel.json').read_text()));pret,emeta=execution_returns();targets=evaluation(d);h0=champion_scores(d);h0res,h0art=assess(h0,'H0',targets,pret,emeta)
 # ALPHA: ROA, no imputation and exact matched coverage.
 roa=fund[['kod','panel_date','has_fundamenta','roa_ttm']].copy();roa=roa[(roa.has_fundamenta==True)&pd.to_numeric(roa.roa_ttm,errors='coerce').notna()];roa['roa_ttm']=pd.to_numeric(roa.roa_ttm);rs=rank_score(roa,'roa_ttm');matched_h0=h0.merge(rs[['kod','panel_date']],on=['kod','panel_date'],validate='one_to_one');solo=rs;blend=blend_exact(matched_h0,rs)
 mhic=ic_metrics(oos(matched_h0),targets,n=N);sic=ic_metrics(oos(solo),targets,n=N);bic=ic_metrics(oos(blend),targets,n=N);dm=delta_ic(bic,mhic);accept=dm['mean_ic52']>=.01 and dm['median_ic52']>=0 and dm['mean_topN_ic52']>=0 and dm['positive_ic_share']>=0 and all(v['mean_ic52']>0 for v in bic['calendar_year'].values())
 bm,bart=build_portfolio(oos(blend),n=N,every=2,cost=COST,model='roa_blend_matched',returns_map=pret,execution_meta=emeta);bm,_=extra_metrics(bm,bart,pret);hm,hart=build_portfolio(oos(matched_h0),n=N,every=2,cost=COST,model='h0_roa_matched',returns_map=pret,execution_meta=emeta);hm,_=extra_metrics(hm,hart,pret)
 terminals=set(json.loads((ROOT/'validated/terminal_events.json').read_text()));oosfund=roa[(roa.panel_date>='2024-01-01')&(roa.panel_date<='2025-12-31')];all_oos=fund[(fund.panel_date>='2024-01-01')&(fund.panel_date<='2025-12-31')]
 roa_result={'classification':'STÖD — NY CHALLENGER' if accept else ('SVAGT STÖD' if dm['mean_ic52']>0 else 'INGET STÖD'),'type':'ALPHA','population_A_available_roa':{'rows':len(oosfund),'instruments':int(oosfund.kod.nunique()),'panel_dates':int(oosfund.panel_date.nunique()),'coverage_of_fund_panel':len(oosfund)/len(all_oos),'terminal_instruments_with_roa':len(set(oosfund.kod)&terminals)},'population_B_exact_matched':{'rows':len(oos(matched_h0)),'H0_rows_equal_challenger_rows':len(oos(matched_h0))==len(oos(blend))},'solo_roa_ic':sic,'matched_H0_ic':mhic,'blend_ic':bic,'delta_blend_minus_matched_H0':dm,'matched_H0_portfolio':hm,'blend_portfolio':bm,'survivorship_warning':'67/68 terminal instruments lack fundamentals; even support is not fully survivorship-safe alpha.'}
 if accept:roa_result['robustness']=bootstrap_delta_ic(bic,mhic)
 # RISK/ALLOCATION: fixed correlation-refill threshold.
 cs,cdiag=corr_order(h0,prices);cres,cart=assess(cs,'correlation_refill_085',targets,pret,emeta);cp=cres['portfolio'];hp=h0res['portfolio'];phase_cs=oos(cs);phase_h0=oos(h0);cs1=phase_cs[phase_cs.panel_date>sorted(phase_cs.panel_date.unique())[0]];h01=phase_h0[phase_h0.panel_date>sorted(phase_h0.panel_date.unique())[0]];c1,a1=assess(cs1,'corr_phase1',targets,pret,emeta);h1,ha1=assess(h01,'h0_phase1',targets,pret,emeta)
 corr_accept=cp['sharpe_excess']>hp['sharpe_excess'] and cp['max_drawdown']>=hp['max_drawdown']+.01 and cp['annualized_excess']>=hp['annualized_excess']-.02 and cp['mean_turnover']<=hp['mean_turnover']+.10 and (cp['leave_top3_out_cagr']-cp['benchmark_cagr'])>=(hp['leave_top3_out_cagr']-hp['benchmark_cagr'])-.01 and (cp['leave_top5_out_cagr']-cp['benchmark_cagr'])>=(hp['leave_top5_out_cagr']-hp['benchmark_cagr'])-.01 and c1['portfolio']['annualized_excess']>0
 corr_result={'classification':'STÖD — NY CHALLENGER' if corr_accept else ('SVAGT STÖD' if cp['max_drawdown']>hp['max_drawdown'] or cp['sharpe_excess']>hp['sharpe_excess'] else 'INGET STÖD'),'type':'RISK/ALLOKERING','legacy_replication_threshold':THRESH,'H0':h0res,'challenger':cres,'delta':{k:cp[k]-hp[k] for k in ('cagr_net','annualized_excess','sharpe_excess','max_drawdown','mean_turnover','leave_top3_out_cagr','leave_top5_out_cagr')},'phase_1':{'H0':h1,'challenger':c1},'time_blocks':{'H0':port_blocks(h0art),'challenger':port_blocks(cart)},'selection_diagnostics':cdiag}
 if corr_accept:corr_result['robustness_status']='ACCEPTED_FOR_PRE-REGISTERED_FALSIFICATION'
 OUT.mkdir(parents=True);dump(OUT/'roa_profitability_quality.json',roa_result);dump(OUT/'correlation_refill_085.json',corr_result);dump(OUT/'correlation_rankings.json',cart['rankings']);dump(OUT/'correlation_holdings.json',cart['holdings']);dump(OUT/'correlation_trades.json',cart['trades']);dump(OUT/'correlation_returns.json',cart['returns']);dump(OUT/'run_provenance.json',{'prereg_freeze_sha256':sha(FREEZE),'preregistration_sha256':sha(PRE),'coverage_matrix_sha256':sha(RI/'LEGACY_V2_COVERAGE_MATRIX_PRE_BATCH3.json'),'core_fund_panel_sha256':sha(ROOT/'panels/core_fundamenta_panel.json'),'prices_sha256':sha(ROOT/'validated/prices/prices_validated.json'),'target_sha256':sha(ROOT/'panels/target_table.json'),'code_sha256':sha(ROOT/'tools/spari_batch3.py'),'target_never_used_for_selection':True,'reviewed_variants':2});dump(OUT/'summary.json',{'run_id':pre['run_id'],'results':{'roa_profitability_quality':roa_result['classification'],'correlation_refill_085':corr_result['classification']},'new_forward_challengers':[],'stop_legacy_replication_after_batch3':True});dump(OUT/'manifest.json',manifest(OUT));print(json.dumps(json.loads((OUT/'summary.json').read_text()),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
