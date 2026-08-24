#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from decision_portfolio_v2 import V2, evaluation, load_decision
from decision_portfolio_v3_execution import execution_returns
from rebuild_sparf_pit import derive

OUT=V2/'sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3'
F=V2/'repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT'
PRE=V2/'sparg/v4_g_preregistration.json'
N=30; COST=.002

def dump(name,x):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n');return p
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def finite(x):return None if x is None or not math.isfinite(float(x)) else float(x)
def ann(rs):
 if len(rs)==0:return None
 w=float(np.prod(1+np.asarray(rs,float)));return finite(w**(13/len(rs))-1) if w>0 else -1.0
def metrics(periods,cost_bps=None):
 cost=COST if cost_bps is None else cost_bps/10000
 nr=np.array([p['gross_return']-cost*p['turnover'] for p in periods]);br=np.array([p['benchmark_return'] for p in periods]);ex=nr-br
 w=np.cumprod(1+nr);dd=w/np.maximum.accumulate(w)-1
 return {'n_periods':len(periods),'total_return':finite(np.prod(1+nr)-1),'cagr':ann(nr),'benchmark_cagr':ann(br),'excess_cagr':finite(ann(nr)-ann(br)),'sharpe_excess':finite(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if len(ex)>1 and ex.std(ddof=1)>0 else None,'max_drawdown':finite(dd.min()),'mean_turnover':finite(np.mean([p['turnover'] for p in periods])),'hit_rate':finite(np.mean(ex>0)),'arithmetic_excess':finite(ex.sum())}
def ic_rows(scores,targets):
 x=scores.merge(targets,on=['kod','panel_date'],how='inner',validate='one_to_one');out=[]
 for dt,g in x.groupby('panel_date',sort=True):
  top=g.sort_values(['score','kod'],ascending=[False,False]).head(N)
  out.append({'panel_date':dt,'n':len(g),'ic52':finite(spearmanr(g.score,g.y).statistic) if g.score.nunique()>1 else None,'top30_ic52':finite(spearmanr(top.score,top.y).statistic) if top.score.nunique()>1 else None})
 return out
def ic_summary(rows):
 v=np.array([r['ic52'] for r in rows if r['ic52'] is not None]);t=np.array([r['top30_ic52'] for r in rows if r['top30_ic52'] is not None])
 return {'n_dates':len(rows),'mean_ic52':finite(v.mean()) if len(v) else None,'median_ic52':finite(np.median(v)) if len(v) else None,'positive_ic_share':finite(np.mean(v>0)) if len(v) else None,'mean_top30_ic52':finite(t.mean()) if len(t) else None}
def phase_portfolio(scores,phase):
 pret,_=execution_returns();dates=sorted(scores.panel_date.unique());prev=[];holds=[];trades=[];periods=[];ranks=[]
 for ix,dt in enumerate(dates):
  g=scores[scores.panel_date==dt].sort_values(['score','kod'],ascending=[False,False]);ranks += [{'panel_date':dt,'rank':i+1,'kod':r.kod,'score':float(r.score)} for i,(_,r) in enumerate(g.iterrows())]
  reb=(ix%2==phase) or not prev
  ids=list(g.head(N).kod) if reb else [k for k in prev if k in set(g.kod)]
  if not reb and len(ids)<N:ids += [k for k in g.kod if k not in ids][:N-len(ids)]
  buys=sorted(set(ids)-set(prev));sells=sorted(set(prev)-set(ids));turn=len(buys)/N if prev else len(ids)/N
  gross=sum(pret.get((k,dt),0) for k in ids)/N;bench=float(np.mean([pret.get((k,dt),0) for k in g.kod]))
  holds += [{'panel_date':dt,'kod':k,'weight':1/N,'rebalance':reb} for k in ids]
  trades += [{'panel_date':dt,'kod':k,'side':'BUY','weight':1/N} for k in buys]+[{'panel_date':dt,'kod':k,'side':'SELL','weight':1/N} for k in sells]
  periods.append({'panel_date':dt,'gross_return':gross,'net_return':gross-COST*turn,'benchmark_return':bench,'turnover':turn,'transaction_cost':COST*turn,'rebalance':reb})
  prev=ids
 return metrics(periods),{'rankings':ranks,'holdings':holds,'trades':trades,'returns':periods}
def ticker_analysis(holds,periods):
 pret,_=execution_returns();dates=sorted({p['panel_date'] for p in periods});byd={d:[h['kod'] for h in holds if h['panel_date']==d] for d in dates};con=defaultdict(float)
 for d,ids in byd.items():
  for k in ids:con[k]+=pret.get((k,d),0)/N
 ranked=sorted(con.items(),key=lambda z:z[1],reverse=True);base=metrics(periods);out={'contribution_ranked':[{'kod':k,'arithmetic_return_contribution':v} for k,v in ranked]}
 for q in (1,3,5,10):
  excluded={k for k,_ in ranked[:q]};old=[];ps=[]
  for p in periods:
   ids=[k for k in byd[p['panel_date']] if k not in excluded];buys=set(ids)-set(old);gross=sum(pret.get((k,p['panel_date']),0) for k in ids)/N
   ps.append({**p,'gross_return':gross,'turnover':len(buys)/N});old=ids
  m=metrics(ps);out['leave_top_'+str(q)]={'tickers':sorted(excluded),'metrics':m,'share_of_arithmetic_excess':finite(sum(con[k] for k in excluded)/base['arithmetic_excess']) if base['arithmetic_excess'] else None}
 loos=[]
 for k,_ in ranked:
  old=[];ps=[]
  for p in periods:
   ids=[x for x in byd[p['panel_date']] if x!=k];buys=set(ids)-set(old);gross=sum(pret.get((x,p['panel_date']),0) for x in ids)/N;ps.append({**p,'gross_return':gross,'turnover':len(buys)/N});old=ids
  loos.append({'kod':k,'cagr':metrics(ps)['cagr'],'excess_cagr':metrics(ps)['excess_cagr']})
 out['leave_one_ticker_out']=loos;return out
def block_analysis(ic,periods,holds):
 specs=json.loads(PRE.read_text())['time_blocks'];out=[]
 for b in specs:
  ir=[r for r in ic if b['from']<=r['panel_date']<=b['to']];pr=[r for r in periods if b['from']<=r['panel_date']<=b['to']];hs=[r for r in holds if b['from']<=r['panel_date']<=b['to']];c=Counter(r['kod'] for r in hs);total=sum(c.values())
  out.append({**b,'ic':ic_summary(ir),'portfolio':metrics(pr),'top_ticker_selection_share':finite(max(c.values())/total) if total else None})
 total=sum(abs(x['portfolio']['arithmetic_excess'] or 0) for x in out)
 for x in out:x['share_of_absolute_block_excess']=finite(abs(x['portfolio']['arithmetic_excess'] or 0)/total) if total else None
 return out
def terminal_audit(rankings,holds,periods):
 events=json.loads((V2/'validated/terminal_events.json').read_text());prices=json.loads((V2/'validated/prices/prices_validated.json').read_text());pret,_=execution_returns();held={(r['kod'],r['panel_date']) for r in holds};ranked=defaultdict(list)
 for r in rankings:
  if r['kod'] in events:ranked[r['kod']].append(r)
 rows=[]
 for k,rs in sorted(ranked.items()):
  ev=events[k];hp=sorted(d for kk,d in held if kk==k);ps=prices[k]
  owned_returns=[{'panel_date':d,'return':pret.get((k,d),0)} for d in hp]
  rows.append({'kod':k,'first_selection_eligible_date':min(r['panel_date'] for r in rs),'best_rank':min(r['rank'] for r in rs),'holding_dates':hp,'first_entry':hp[0] if hp else None,'last_holding':hp[-1] if hp else None,'last_market_price_date':ps[-1]['d'],'last_adjusted_price':ps[-1]['adj'],'event_date':ev['event_date'],'event_type':ev['event_type'],'evidence':ev.get('evidence'),'successor':ev.get('successor'),'owned_period_returns':owned_returns,'economic_contribution':finite(sum(x['return']/N for x in owned_returns))})
 no_terminal={r['kod'] for r in rows};old=[];diag=[]
 for p in periods:
  ids=[h['kod'] for h in holds if h['panel_date']==p['panel_date'] and h['kod'] not in no_terminal];buys=set(ids)-set(old);gross=sum(pret.get((k,p['panel_date']),0) for k in ids)/N;diag.append({**p,'gross_return':gross,'turnover':len(buys)/N});old=ids
 return {'ranked_terminal_instruments':len(rows),'held_terminal_instruments':sum(bool(r['holding_dates']) for r in rows),'instruments':rows,'champion_including_terminal':metrics(periods),'diagnostic_without_all_terminal_instruments':metrics(diag)}
def missing_audit(dec,scores,holds,periods):
 test=dec[(dec.panel_date>='2024-01-01')&(dec.panel_date<='2025-12-31')].copy();s=scores.merge(test[['kod','panel_date','mom_18m']],on=['kod','panel_date']);s['missing18']=s.mom_18m.isna();hr={(r['kod'],r['panel_date']) for r in holds};s['selected']=[(k,d) in hr for k,d in zip(s.kod,s.panel_date)];pret,_=execution_returns();sel=s[s.selected];near=[]
 for dt,g in s.groupby('panel_date'):
  g=g.sort_values(['score','kod'],ascending=[False,False]).reset_index(drop=True);cut=g.iloc[N-1].score;near.append({'panel_date':dt,'cutoff_score':float(cut),'ties_at_cutoff':int((g.score==cut).sum()),'missing18_within_ranks_25_35':int(g.iloc[24:35].missing18.sum())})
 missholds=sel[sel.missing18];con=sum(pret.get((r.kod,r.panel_date),0)/N for _,r in missholds.iterrows())
 return {'decision_rows':len(s),'missing18_rows':int(s.missing18.sum()),'missing18_share':float(s.missing18.mean()),'selected_rows':len(sel),'selected_missing18_rows':len(missholds),'selected_missing18_share':float(missholds.shape[0]/len(sel)),'missing18_arithmetic_return_contribution':finite(con),'missing18_mean_rank':finite(np.mean([next(x['rank'] for x in json.loads((F/'rankings.json').read_text()) if x['model']=='F6_8w' and x['kod']==r.kod and x['panel_date']==r.panel_date) for _,r in missholds.iterrows()])) if len(missholds) else None,'cutoff_ties':near}
def membership_audit(holds,periods):
 core=pd.DataFrame(json.loads((V2/'panels/core_panel.json').read_text()))[['kod','panel_date','membership_verified']];h=pd.DataFrame(holds).merge(core,on=['kod','panel_date'],how='left',validate='one_to_one');pret,_=execution_returns();out={}
 for flag,g in h.groupby('membership_verified',dropna=False):out[str(bool(flag))]={'holding_rows':len(g),'share':len(g)/len(h),'arithmetic_return_contribution':finite(sum(pret.get((r.kod,r.panel_date),0)/N for _,r in g.iterrows()))}
 return {'groups':out,'verified_holding_share':float(h.membership_verified.mean()),'large_mid_small_status':'NOT_TESTABLE: no PIT segment history in frozen panel','liquidity_segment_status':'NOT_TESTABLE: turnover/Amihud blocked and no frozen PIT liquidity segment','interpretation':'membership attribution is diagnostic; unknown group is retained'}
def bootstrap(ic_c,ic_b,pc,pb,ticker):
 cfg=json.loads(PRE.read_text())['bootstrap'];rng=np.random.default_rng(cfg['seed']);B=cfg['draws'];L=cfg['block_length_panel_dates'];n=len(pc);pairs=pd.DataFrame(ic_c).merge(pd.DataFrame(ic_b),on='panel_date',suffixes=('_c','_b'));vals={k:[] for k in ['mean_ic','delta_ic','excess_mean','sharpe','cagr','leave_top3_excess','delta_portfolio_excess_mean','delta_portfolio_cagr']}
 top=set(ticker['leave_top_3']['tickers']);holds=[r for r in json.loads((F/'holdings.json').read_text()) if r['model']=='F6_8w'];pret,_=execution_returns();byd={d:[h['kod'] for h in holds if h['panel_date']==d and h['kod'] not in top] for d in sorted({p['panel_date'] for p in pc})};l3=[];old=[]
 for p in pc:
  ids=byd[p['panel_date']];turn=len(set(ids)-set(old))/N;l3.append(sum(pret.get((k,p['panel_date']),0) for k in ids)/N-COST*turn-p['benchmark_return']);old=ids
 for _ in range(B):
  idx=[]
  while len(idx)<n:
   st=int(rng.integers(0,max(1,n-L+1)));idx.extend(range(st,min(st+L,n)))
  idx=np.array(idx[:n]);nr=np.array([pc[i]['net_return'] for i in idx]);br=np.array([pc[i]['benchmark_return'] for i in idx]);ex=nr-br
  vals['excess_mean'].append(float(ex.mean()));vals['sharpe'].append(float(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if ex.std(ddof=1)>0 else 0);vals['cagr'].append(ann(nr));vals['leave_top3_excess'].append(float(np.mean(np.array(l3)[idx])))
  bnr=np.array([pb[i]['net_return'] for i in idx]);vals['delta_portfolio_excess_mean'].append(float((nr-bnr).mean()));vals['delta_portfolio_cagr'].append(float(ann(nr)-ann(bnr)))
  j=rng.integers(0,len(pairs),len(pairs));vals['mean_ic'].append(float(pairs.ic52_c.iloc[j].mean()));vals['delta_ic'].append(float((pairs.ic52_c-pairs.ic52_b).iloc[j].mean()))
 def s(v):
  a=np.asarray(v,float);return {'mean':finite(a.mean()),'p2_5':finite(np.quantile(a,.025)),'median':finite(np.median(a)),'p97_5':finite(np.quantile(a,.975)),'probability_positive':finite(np.mean(a>0))}
 return {'method':cfg,'n_portfolio_dates':n,'n_paired_ic_dates':len(pairs),'distributions':{k:s(v) for k,v in vals.items()}}
def main():
 assert sha(V2/'repair_df/FREEZE_MANIFEST.json')==json.loads(PRE.read_text())['freeze']['manifest_sha256']
 rawscores=json.loads((F/'scores.json').read_text());champ=pd.DataFrame(rawscores['combo_12m_18m']);champ=champ[champ.role=='test'][['kod','panel_date','score']];base=pd.DataFrame(rawscores['F1_mom_52w']);base=base[base.role=='test'][['kod','panel_date','score']]
 allret=json.loads((F/'returns.json').read_text());allhold=json.loads((F/'holdings.json').read_text());allrank=json.loads((F/'rankings.json').read_text());alltrade=json.loads((F/'trades.json').read_text())
 pc=[r for r in allret if r['model']=='F6_8w'];pb=[r for r in allret if r['model']=='F1_mom_52w'];hc=[r for r in allhold if r['model']=='F6_8w'];rc=[r for r in allrank if r['model']=='F6_8w'];tc=[r for r in alltrade if r['model']=='F6_8w']
 dec=derive(load_decision('core_panel.json',['mom_4w','mom_26w','mom_52w','mom_12_1','vol_52w','downside_vol_52w','risk_adj_momentum_52w','trend_consistency_52w','price_vs_sma52w','residual_momentum_52w','market_regime_trend','drawdown_current_104w']));tar=evaluation(dec);icc=ic_rows(champ,tar);icb=ic_rows(base,tar)
 # Phase 0 must reproduce frozen champion exactly.
 m0,a0=phase_portfolio(champ,0);keys=('panel_date','kod','weight','rebalance');assert sha(dump('_phase0_holdings_check.json',[{k:r[k] for k in keys} for r in a0['holdings']]))==sha(dump('_frozen_holdings_check.json',[{k:r[k] for k in keys} for r in hc]))
 phases=[]
 for phase in (0,1):
  m,a=phase_portfolio(champ,phase);phases.append({'phase':phase,'metrics':m,'leave_top3_excess':ticker_analysis(a['holdings'],a['returns'])['leave_top_3']['metrics']['excess_cagr']})
 cagr=[x['metrics']['cagr'] for x in phases];champ_pct=sum(x<=cagr[0] for x in cagr)/len(cagr)
 phase_result={'phases':phases,'distribution':{'min_cagr':min(cagr),'median_cagr':float(np.median(cagr)),'mean_cagr':float(np.mean(cagr)),'max_cagr':max(cagr),'champion_phase_percentile':champ_pct}}
 ticker=ticker_analysis(hc,pc);blocks={'champion':block_analysis(icc,pc,hc),'baseline_12m':block_analysis(icb,pb,[r for r in allhold if r['model']=='F1_mom_52w'])}
 costs={str(bp):metrics(pc,bp) for bp in (0,20,40,60,100)};lo=0;hi=10000
 for _ in range(60):
  mid=(lo+hi)/2
  if metrics(pc,mid)['excess_cagr']>0:lo=mid
  else:hi=mid
 costs['break_even_bps']=hi
 terminal=terminal_audit(rc,hc,pc);missing=missing_audit(dec,champ,hc,pc);membership=membership_audit(hc,pc)
 bench_recalc=[];pret,_=execution_returns()
 for p in pc:
  g=champ[champ.panel_date==p['panel_date']];bench=float(np.mean([pret.get((k,p['panel_date']),0) for k in g.kod]));bench_recalc.append(abs(bench-p['benchmark_return']))
 benchmark={'metrics':metrics(pc),'max_absolute_period_recalculation_error':max(bench_recalc),'same_decision_universe':True,'target_required':False,'transaction_cost':'none for passive equal-weight diagnostic benchmark'}
 boot=bootstrap(icc,icb,pc,pb,ticker)
 hb=[r for r in allhold if r['model']=='F1_mom_52w'];rb=[r for r in allrank if r['model']=='F1_mom_52w'];complete=set(zip(dec[dec.mom_18m.notna()].kod,dec[dec.mom_18m.notna()].panel_date));icc_complete=ic_rows(champ[[((k,d) in complete) for k,d in zip(champ.kod,champ.panel_date)]],tar);icb_complete=ic_rows(base[[((k,d) in complete) for k,d in zip(base.kod,base.panel_date)]],tar)
 comparison={'champion':{'ic':ic_summary(icc),'portfolio':metrics(pc),'ticker_ablation':ticker,'terminal':{'including':terminal['champion_including_terminal'],'without':terminal['diagnostic_without_all_terminal_instruments']},'cost_stress':costs},'baseline_12m':{'ic':ic_summary(icb),'portfolio':metrics(pb),'ticker_ablation':ticker_analysis(hb,pb),'terminal':terminal_audit(rb,hb,pb),'cost_stress':{str(bp):metrics(pb,bp) for bp in (0,20,40,60,100)},'rebalance_phase_status':'4w baseline has no alternate phase on frozen 4w panel'},'complete_18m_subset':{'champion':ic_summary(icc_complete),'baseline_12m':ic_summary(icb_complete)},'delta':{'mean_ic52':ic_summary(icc)['mean_ic52']-ic_summary(icb)['mean_ic52'],'top30_ic52':ic_summary(icc)['mean_top30_ic52']-ic_summary(icb)['mean_top30_ic52'],'cagr':metrics(pc)['cagr']-metrics(pb)['cagr'],'excess_cagr':metrics(pc)['excess_cagr']-metrics(pb)['excess_cagr']}}
 outputs={'G2_time_blocks.json':blocks,'G3_rebalance_phase.json':phase_result,'G4_ticker_concentration.json':ticker,'G5_sector.json':{'status':'NOT_TESTABLE_PIT','reason':'Frozen data contains no historically versioned sector classification; current sectorId is not backcast.'},'G6_universe.json':membership,'G7_terminal.json':terminal,'G8_missing18.json':missing,'G9_cost_stress.json':costs,'G10_benchmark.json':benchmark,'G11_bootstrap.json':boot,'G12_12m_comparison.json':comparison}
 for n,x in outputs.items():dump(n,x)
 dump('rankings.json',rc);dump('holdings.json',hc);dump('trades.json',tc);dump('returns.json',pc);dump('ic_per_date.json',icc)
 # Remove temporary equality-check artifacts after their hashes have proved identity.
 (OUT/'_phase0_holdings_check.json').unlink();(OUT/'_frozen_holdings_check.json').unlink()
 print(json.dumps({'status':'COMPLETE','champion':comparison['champion'],'phase':phase_result['distribution'],'bootstrap':boot['distributions']['delta_ic']},indent=2))
if __name__=='__main__':main()
