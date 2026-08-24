from __future__ import annotations
import hashlib,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from spard_neutral_race import V2,sha,dump,manifest_tree,load_data,split_defs,ic_metrics,price_returns,sector_map,annualized

OUT=V2/"sparf/results/SPARF_SYSTEMATIC_MOMENTUM_V1"; CFG=V2/"sparf/preregistration.json"; COST=.002
def finite(x): return None if x is None or not math.isfinite(float(x)) else float(x)
def rows_for(df,col,name):
 out=[]
 for s in split_defs(df):
  ev=df[(df.panel_date>=s['eval_from'])&(df.panel_date<=s['eval_to'])]; med=ev.groupby('panel_date')[col].median().to_dict()
  for _,r in ev.iterrows():
   v=r[col]; v=med[r.panel_date] if pd.isna(v) else v
   out.append({'model':name,'split':s['name'],'role':s['role'],'kod':r.kod,'panel_date':r.panel_date,'score':float(v),'target_fwd52w':float(r.y)})
 return out
def derive(df):
 prices=json.loads((V2/'validated/prices/prices_validated.json').read_text()); series={k:(np.array([np.datetime64(r['d']) for r in rs]),np.array([r['adj'] for r in rs],dtype=float)) for k,rs in prices.items()}
 def value(k,dt,w):
  ds,vs=series[k]; t=np.datetime64(dt); target=t-np.timedelta64(7*w,'D'); i=np.searchsorted(ds,t,side='right')-1; j=np.searchsorted(ds,target,side='right')-1
  if i<0 or j<0 or int((target-ds[j])/np.timedelta64(1,'D'))>10:return np.nan
  return vs[i]/vs[j]-1
 for w,n in ((26,'6m'),(39,'9m'),(52,'12m'),(78,'18m')):
  vals=[value(k,d,w) for k,d in zip(df.kod,df.panel_date)]; short=[value(k,d,4) for k,d in zip(df.kod,df.panel_date)]
  df['mom_'+n]=vals
  df['mom_'+n+'_skip1m']=[(1+a)/(1+b)-1 if pd.notna(a) and pd.notna(b) and b>-1 else np.nan for a,b in zip(vals,short)]
 assert np.nanmax(np.abs(df.mom_12m-df.mom_52w))<1e-12
 for a,b,n in [('mom_6m','mom_12m','combo_6m_12m'),('mom_9m','mom_12m','combo_9m_12m'),('mom_12m','mom_18m','combo_12m_18m')]:
  df[n]=(df.groupby('panel_date')[a].rank(pct=True)+df.groupby('panel_date')[b].rank(pct=True))/2
 df['mom_52w_over_downside_vol']=df.mom_52w/df.downside_vol_52w.replace(0,np.nan)
 return df
def portfolio(rows,n=30,every=1,gate=None,buffer=None):
 by=defaultdict(list)
 for r in rows:
  if r['role']=='test': by[r['panel_date']].append(r)
 pret=price_returns(); sec=sector_map(); dates=sorted(by); prev=[]; periods=[]; holdings={}; contrib=defaultdict(float); selections=defaultdict(int); secs=defaultdict(int)
 for ix,dt in enumerate(dates):
  ranked=sorted(by[dt],key=lambda z:(z['score'],z['kod']),reverse=True)
  if ix%every!=0 and prev: chosen=[r for r in ranked if r['kod'] in prev]
  else:
   eligible=[r for r in ranked if gate is None or gate(r)]
   if buffer and prev:
    ranks={r['kod']:i+1 for i,r in enumerate(ranked)}; keep=[r for r in ranked if r['kod'] in prev and ranks[r['kod']]<=buffer and (gate is None or gate(r))]; ids={r['kod'] for r in keep}; chosen=keep+[r for r in eligible if r['kod'] not in ids][:max(0,n-len(keep))]
   else: chosen=eligible[:n]
  ids=[r['kod'] for r in chosen]; turn=(len(set(ids)-set(prev))/n) if prev else len(ids)/n
  gross=sum(pret.get((k,dt),0) for k in ids)/n; net=gross-COST*turn; bench=np.mean([pret.get((r['kod'],dt),0) for r in ranked]);
  periods.append({'panel_date':dt,'gross':gross,'net':net,'benchmark':float(bench),'turnover':turn,'invested_share':len(ids)/n})
  holdings[dt]=ids
  for k in ids: contrib[k]+=pret.get((k,dt),0)/n; selections[k]+=1; secs[str(sec.get(k) or 'UNKNOWN')]+=1
  prev=ids
 nr=[p['net'] for p in periods]; gr=[p['gross'] for p in periods]; br=[p['benchmark'] for p in periods]; ex=np.array(nr)-np.array(br); wealth=np.cumprod(1+np.array(nr)); dd=wealth/np.maximum.accumulate(wealth)-1; rankedc=sorted(contrib.items(),key=lambda z:z[1],reverse=True); top3=[k for k,_ in rankedc[:3]]
 def leave(excluded):
  rr=[]; old=[]
  for dt in dates:
   ids=[k for k in holdings[dt] if k not in excluded]; turn=(len(set(ids)-set(old))/n) if old else len(ids)/n; rr.append(sum(pret.get((k,dt),0) for k in ids)/n-COST*turn); old=ids
  return annualized(rr)
 return {'n':n,'rebalance_multiple':every,'cagr_net':annualized(nr),'cagr_gross':annualized(gr),'benchmark_cagr':annualized(br),'sharpe_excess':finite(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if ex.std(ddof=1)>0 else None,'max_drawdown':finite(dd.min()),'mean_turnover':finite(np.mean([p['turnover'] for p in periods])),'mean_invested_share':finite(np.mean([p['invested_share'] for p in periods])),'top3_tickers':top3,'best_ticker':rankedc[0] if rankedc else None,'worst_ticker':rankedc[-1] if rankedc else None,'leave_top3_out_cagr':leave(set(top3)),'leave_one_ticker_out_cagr':{k:leave({k}) for k,_ in rankedc},'sector_selection_share':{k:v/sum(secs.values()) for k,v in secs.items()},'periods':periods}
def ic_for_n(rows,n):
 out=ic_metrics(rows); by=defaultdict(list)
 for r in rows: by[r['panel_date']].append(r)
 vals=[]
 for rs in by.values():
  top=sorted(rs,key=lambda z:(z['score'],z['kod']),reverse=True)[:n]
  if len({r['score'] for r in top})>1: vals.append(float(spearmanr([r['score'] for r in top],[r['target_fwd52w'] for r in top]).statistic))
 out['portfolio_n']=n; out['mean_topN_ic52']=finite(np.mean(vals)); out['median_topN_ic52']=finite(np.median(vals)); return out
def assess(rows,n=30,every=1,gate=None,buffer=None):
 test=[r for r in rows if r['role']=='test']; return {'ic':ic_for_n(test,n),'portfolio':portfolio(rows,n,every,gate,buffer)}
def robust(ch,base):
 a,b=ch['ic'],base['ic']; pa,pb=ch['portfolio'],base['portfolio']; years=a['calendar_year']
 return a['mean_ic52']>=b['mean_ic52']+.01 and a['median_ic52']>=b['median_ic52'] and a['mean_top30_ic52']>=b['mean_top30_ic52'] and a['positive_ic_share']>=b['positive_ic_share'] and all(v['mean_ic52']>0 for v in years.values()) and (pa['leave_top3_out_cagr']-pa['benchmark_cagr']) >= (pb['leave_top3_out_cagr']-pb['benchmark_cagr'])
def main():
 cfg=json.loads(CFG.read_text()); assert sha(V2/'panels/core_panel.json')==cfg['inputs']['core_panel.json']; assert sha(V2/'panels/target_table.json')==cfg['inputs']['target_table.json']; assert sha(V2/'validated/prices/prices_validated.json')==cfg['inputs']['prices_validated.json']
 cols=['mom_4w','mom_26w','mom_52w','mom_12_1','vol_52w','downside_vol_52w','risk_adj_momentum_52w','trend_consistency_52w','price_vs_sma52w','residual_momentum_52w','market_regime_trend','drawdown_current_104w']; df=derive(load_data('core_panel.json',cols)); allrows={}
 champion=rows_for(df,'mom_52w','champion_mom_52w'); base=assess(champion); allrows['champion']=champion; dump(OUT/'F1_champion.json',base)
 signal_ids=cfg['signal_challengers']; f2={}
 for x in signal_ids: allrows[x]=rows_for(df,x,x); f2[x]=assess(allrows[x]); f2[x]['passes']=robust(f2[x],base)
 winner=next((x for x in signal_ids if f2[x]['passes']), 'champion'); dump(OUT/'F2_signal.json',{'winner':winner,'results':f2})
 current=allrows[winner] if winner!='champion' else champion; current_metrics=assess(current)
 quality=[x for x in cfg['quality_challengers'] if x!='trend_consistency_52w']; f3={}
 for x in quality: allrows[x]=rows_for(df,x,x); f3[x]=assess(allrows[x]); f3[x]['passes']=robust(f3[x],current_metrics)
 qw=next((x for x in quality if f3[x]['passes']),'unchanged'); dump(OUT/'F3_quality.json',{'winner':qw,'results':f3});
 if qw!='unchanged': current=allrows[qw]; current_metrics=assess(current)
 lookup={(r.kod,r.panel_date):r for _,r in df.iterrows()}; gates={'mom_52w_positive':lambda r: lookup[(r['kod'],r['panel_date'])].mom_52w>0,'price_above_sma52w':lambda r: lookup[(r['kod'],r['panel_date'])].price_vs_sma52w>0,'broad_market_trend_positive':lambda r: lookup[(r['kod'],r['panel_date'])].market_regime_trend>0}
 f4={k:assess(current,gate=g) for k,g in gates.items()}; ref=current_metrics
 def risk_pass(m,r):
  a,b=m['portfolio'],r['portfolio']; return a['max_drawdown']>=b['max_drawdown']+.02 and a['sharpe_excess']>=b['sharpe_excess'] and a['cagr_net']>=b['cagr_net']-.02 and (a['leave_top3_out_cagr']-a['benchmark_cagr']) >= (b['leave_top3_out_cagr']-b['benchmark_cagr'])
 gw=next((k for k in gates if risk_pass(f4[k],ref)),'unchanged'); active_gate=None if gw=='unchanged' else gates[gw]; dump(OUT/'F4_gates.json',{'winner':gw,'classification':'risk_control_only','results':f4})
 f5={str(n):assess(current,n=n,gate=active_gate) for n in cfg['portfolio_sizes']}; r30=f5['30']; passing=[]
 for n in cfg['portfolio_sizes']:
  m=f5[str(n)]; a,b=m['portfolio'],r30['portfolio']; ok=m['ic']['mean_topN_ic52']>0 and a['sharpe_excess']>=b['sharpe_excess']-.10 and a['max_drawdown']>=b['max_drawdown']-.02 and (a['leave_top3_out_cagr']-a['benchmark_cagr']) >= (b['leave_top3_out_cagr']-b['benchmark_cagr'])-.01
  m['passes_diversification_rule']=ok
  if ok: passing.append(n)
 nw=max(passing) if passing else 30; dump(OUT/'F5_portfolio_size.json',{'winner':nw,'results':f5})
 f6={'2w':{'status':'EJ_TESTBART_PÅ_FRYST_4W_PANEL'},'4w':assess(current,n=nw,every=1,gate=active_gate),'8w':assess(current,n=nw,every=2,gate=active_gate)}; a,b=f6['8w']['portfolio'],f6['4w']['portfolio']; eight=a['cagr_net']>=b['cagr_net']-.02 and a['sharpe_excess']>=b['sharpe_excess']-.10 and a['max_drawdown']>=b['max_drawdown']-.02 and a['mean_turnover']<=b['mean_turnover']*.8; rw='8w' if eight else '4w'; every=2 if eight else 1; dump(OUT/'F6_rebalance.json',{'winner':rw,'results':f6})
 def both(g1,g2): return lambda r:(g1 is None or g1(r)) and g2(r)
 exit_gates={'momentum_loss':both(active_gate,gates['mom_52w_positive']),'absolute_trend_break':both(active_gate,gates['price_above_sma52w']),'drawdown_exit_25':both(active_gate,lambda r: lookup[(r['kod'],r['panel_date'])].drawdown_current_104w>=-.25)}
 exits={'rank_exit_45':assess(current,n=nw,every=every,gate=active_gate,buffer=45),**{k:assess(current,n=nw,every=every,gate=g) for k,g in exit_gates.items()}}; exit_ref=f6[rw]; ew=next((k for k in exits if risk_pass(exits[k],exit_ref)),'unchanged'); dump(OUT/'F7_entry_exit.json',{'winner':ew,'results':exits})
 registry=[]
 for stage,obj in [('F2',f2),('F3',f3),('F4',f4),('F5',f5),('F6',f6),('F7',exits)]:
  for k,v in obj.items(): registry.append({'stage':stage,'challenger':k,'status':'TESTED' if not (isinstance(v,dict) and v.get('status')) else v['status']})
 final_pass=robust(current_metrics,base); final_name=qw if qw!='unchanged' else (winner if winner!='champion' else 'mom_52w'); classification='A) ROBUST FÖRBÄTTRING AV MOMENTUM' if final_pass else ('B) MARGINELL FÖRBÄTTRING' if final_name!='mom_52w' else 'C) INGEN ROBUST FÖRBÄTTRING — 12M MOMENTUM KVARSTÅR')
 dump(OUT/'predictions_rankings.json',allrows); dump(OUT/'experiment_registry.json',{'total_registered':len(registry)+1,'entries':registry+[{'stage':'F3','challenger':'trend_consistency_52w','status':'EXCLUDED_DATA_INTEGRITY'}],'failed_variants_retained':True}); dump(OUT/'final_decision.json',{'status':'COMPLETE_AFTER_CLEAN_CONTINUATION','classification':classification,'champion':final_name,'signal_stage_winner':winner,'quality_stage_winner':qw,'gate':gw,'portfolio_n':nw,'rebalance':rw,'entry_exit':ew,'passes_replacement_rule_vs_F1':final_pass,'trend_consistency_excluded':True,'two_week_limitation':cfg['rebalance_weeks']['two_week_status']}); dump(OUT/'manifest.json',manifest_tree(OUT)); print(json.dumps({'status':'COMPLETE','challengers':len(registry)+1,'winner':final_name,'classification':classification},indent=2))
if __name__=='__main__':main()
