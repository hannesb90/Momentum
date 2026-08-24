from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np
import pandas as pd
from decision_portfolio_v2 import V2,sha,dump,manifest,load_decision,evaluation,splits,ic_metrics
from decision_portfolio_v3_execution import build_portfolio

OUT=V2/'repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT'; COST=.002
def derive(df):
 prices=json.loads((V2/'validated/prices/prices_validated.json').read_text());series={k:(np.array([np.datetime64(r['d']) for r in rs]),np.array([r['adj'] for r in rs],float)) for k,rs in prices.items()}
 def val(k,dt,w):
  ds,vs=series[k];t=np.datetime64(dt);goal=t-np.timedelta64(7*w,'D');i=np.searchsorted(ds,t,'right')-1;j=np.searchsorted(ds,goal,'right')-1
  return np.nan if i<0 or j<0 or int((goal-ds[j])/np.timedelta64(1,'D'))>10 else vs[i]/vs[j]-1
 for w,n in ((26,'6m'),(39,'9m'),(52,'12m'),(78,'18m')):
  a=[val(k,d,w) for k,d in zip(df.kod,df.panel_date)];b=[val(k,d,4) for k,d in zip(df.kod,df.panel_date)];df['mom_'+n]=a;df['mom_'+n+'_skip1m']=[(1+x)/(1+y)-1 if pd.notna(x) and pd.notna(y) and y>-1 else np.nan for x,y in zip(a,b)]
 assert np.nanmax(np.abs(df.mom_12m-df.mom_52w))<1e-12
 for a,b,n in [('mom_6m','mom_12m','combo_6m_12m'),('mom_9m','mom_12m','combo_9m_12m'),('mom_12m','mom_18m','combo_12m_18m')]:df[n]=(df.groupby('panel_date')[a].rank(pct=True)+df.groupby('panel_date')[b].rank(pct=True))/2
 df['mom_52w_over_downside_vol']=df.mom_52w/df.downside_vol_52w.replace(0,np.nan);return df
def scores(df,col):
 out=[]
 for s in splits(df):
  z=df[(df.panel_date>=s['eval_from'])&(df.panel_date<=s['eval_to'])][['kod','panel_date',col]].copy();z['score']=z[col].fillna(z.groupby('panel_date')[col].transform('median'));z['role']=s['role'];z['split']=s['name'];out.append(z[['kod','panel_date','score','role','split']])
 return pd.concat(out,ignore_index=True)
def robust(a,b):
 i,j=a['ic'],b['ic'];pa,pb=a['portfolio'],b['portfolio'];return i['mean_ic52']>=j['mean_ic52']+.01 and i['median_ic52']>=j['median_ic52'] and i['mean_topN_ic52']>=j['mean_topN_ic52'] and i['positive_ic_share']>=j['positive_ic_share'] and all(v['mean_ic52']>0 for v in i['calendar_year'].values()) and (pa['leave_top3_out_cagr']-pa['benchmark_cagr']) >= (pb['leave_top3_out_cagr']-pb['benchmark_cagr'])
def main():
 cfg=json.loads((V2/'sparf/preregistration.json').read_text());assert sha(V2/'panels/core_panel.json')==cfg['inputs']['core_panel.json'];cols=['mom_4w','mom_26w','mom_52w','mom_12_1','vol_52w','downside_vol_52w','risk_adj_momentum_52w','trend_consistency_52w','price_vs_sma52w','residual_momentum_52w','market_regime_trend','drawdown_current_104w'];dec=derive(load_decision('core_panel.json',cols));tar=evaluation(dec);test_dates=[];artall={'rankings':[],'holdings':[],'trades':[],'returns':[]};registry=[]
 def assess(sf,name,n=30,every=1,eligible=None,buffer=None):
  t=sf[sf.role=='test'][['kod','panel_date','score']].copy()
  if eligible is not None:t=t.merge(eligible,on=['kod','panel_date'],how='left',validate='one_to_one')
  ic=ic_metrics(t[['kod','panel_date','score']],tar,n=n);pm,art=build_portfolio(t,n=n,every=every,cost=COST,model=name,eligible_col='eligible' if eligible is not None else None,buffer=buffer)
  for k in artall:artall[k].extend(art[k])
  return {'ic':ic,'portfolio':pm}
 allscores={};base_sf=scores(dec,'mom_52w');allscores['F1_mom_52w']=base_sf.to_dict('records');base=assess(base_sf,'F1_mom_52w');dump(OUT/'F1.json',base)
 sig=cfg['signal_challengers'];f2={}
 for x in sig:
  sf=scores(dec,x);allscores[x]=sf.to_dict('records');m=assess(sf,'F2_'+x);m['passes']=robust(m,base);f2[x]=m;registry.append({'stage':'F2','id':x,'status':'TESTED'})
 winner=next((x for x in sig if f2[x]['passes']),'F1_mom_52w');current_sf=base_sf if winner=='F1_mom_52w' else pd.DataFrame(allscores[winner]);current=base if winner=='F1_mom_52w' else f2[winner];dump(OUT/'F2.json',{'winner':winner,'results':f2})
 quality=[x for x in cfg['quality_challengers'] if x!='trend_consistency_52w'];f3={}
 for x in quality:
  sf=scores(dec,x);allscores[x]=sf.to_dict('records');m=assess(sf,'F3_'+x);m['passes']=robust(m,current);f3[x]=m;registry.append({'stage':'F3','id':x,'status':'TESTED'})
 registry.append({'stage':'F3','id':'trend_consistency_52w','status':'EXCLUDED_DATA_INTEGRITY'});qw=next((x for x in quality if f3[x]['passes']),'unchanged')
 if qw!='unchanged':current_sf=pd.DataFrame(allscores[qw]);current=f3[qw]
 dump(OUT/'F3.json',{'winner':qw,'results':f3})
 lookup=dec.set_index(['kod','panel_date']);gate_expr={'mom_52w_positive':lookup.mom_52w>0,'price_above_sma52w':lookup.price_vs_sma52w>0,'broad_market_trend_positive':lookup.market_regime_trend>0}
 def eligibility(series):return pd.DataFrame([{'kod':k,'panel_date':d,'eligible':bool(v) if pd.notna(v) else False} for (k,d),v in series.items()])
 def riskpass(m,r):
  a,b=m['portfolio'],r['portfolio'];return a['max_drawdown']>=b['max_drawdown']+.02 and a['sharpe_excess']>=b['sharpe_excess'] and a['cagr_net']>=b['cagr_net']-.02 and (a['leave_top3_out_cagr']-a['benchmark_cagr']) >= (b['leave_top3_out_cagr']-b['benchmark_cagr'])
 f4={k:assess(current_sf,'F4_'+k,eligible=eligibility(v)) for k,v in gate_expr.items()};gw=next((k for k in gate_expr if riskpass(f4[k],current)),'unchanged');active=None if gw=='unchanged' else eligibility(gate_expr[gw]);dump(OUT/'F4.json',{'winner':gw,'results':f4});registry += [{'stage':'F4','id':k,'status':'TESTED'} for k in f4]
 f5={str(n):assess(current_sf,'F5_N'+str(n),n=n,eligible=active) for n in cfg['portfolio_sizes']};r30=f5['30'];passing=[]
 for n in cfg['portfolio_sizes']:
  m=f5[str(n)];a,b=m['portfolio'],r30['portfolio'];ok=m['ic']['mean_topN_ic52']>0 and a['sharpe_excess']>=b['sharpe_excess']-.10 and a['max_drawdown']>=b['max_drawdown']-.02 and (a['leave_top3_out_cagr']-a['benchmark_cagr']) >= (b['leave_top3_out_cagr']-b['benchmark_cagr'])-.01;m['passes']=ok
  if ok:passing.append(n)
 nw=max(passing) if passing else 30;dump(OUT/'F5.json',{'winner':nw,'results':f5});registry += [{'stage':'F5','id':str(n),'status':'TESTED'} for n in cfg['portfolio_sizes']]
 f6={'2w':{'status':'EJ_TESTBART_PÅ_FRYST_4W_PANEL'},'4w':assess(current_sf,'F6_4w',n=nw,every=1,eligible=active),'8w':assess(current_sf,'F6_8w',n=nw,every=2,eligible=active)};a,b=f6['8w']['portfolio'],f6['4w']['portfolio'];eight=a['cagr_net']>=b['cagr_net']-.02 and a['sharpe_excess']>=b['sharpe_excess']-.10 and a['max_drawdown']>=b['max_drawdown']-.02 and a['mean_turnover']<=b['mean_turnover']*.8;rw='8w' if eight else '4w';every=2 if eight else 1;dump(OUT/'F6.json',{'winner':rw,'results':f6});registry += [{'stage':'F6','id':x,'status':('TESTED' if x!='2w' else 'EJ_TESTBART')} for x in f6]
 def combine(a,b):
  if a is None:return b
  z=a.merge(b,on=['kod','panel_date'],suffixes=('_a','_b'));z['eligible']=z.eligible_a&z.eligible_b;return z[['kod','panel_date','eligible']]
 exits={'rank_exit_45':assess(current_sf,'F7_rank_exit_45',n=nw,every=every,eligible=active,buffer=45),'momentum_loss':assess(current_sf,'F7_momentum_loss',n=nw,every=every,eligible=combine(active,eligibility(gate_expr['mom_52w_positive']))),'absolute_trend_break':assess(current_sf,'F7_absolute_trend_break',n=nw,every=every,eligible=combine(active,eligibility(gate_expr['price_above_sma52w']))),'drawdown_exit_25':assess(current_sf,'F7_drawdown_exit_25',n=nw,every=every,eligible=combine(active,eligibility(lookup.drawdown_current_104w>=-.25)))};ref=f6[rw];ew=next((k for k in exits if riskpass(exits[k],ref)),'unchanged');dump(OUT/'F7.json',{'winner':ew,'results':exits});registry += [{'stage':'F7','id':k,'status':'TESTED'} for k in exits]
 final_name=qw if qw!='unchanged' else winner;classification='A) ROBUST FÖRBÄTTRING AV MOMENTUM' if robust(current,base) else ('B) MARGINELL FÖRBÄTTRING' if final_name!='F1_mom_52w' else 'C) INGEN ROBUST FÖRBÄTTRING — 12M MOMENTUM KVARSTÅR');dump(OUT/'scores.json',allscores);dump(OUT/'experiment_registry.json',{'total':len(registry),'entries':registry});
 for k,v in artall.items():dump(OUT/(k+'.json'),v)
 dump(OUT/'final_decision.json',{'classification':classification,'signal':final_name,'quality':qw,'gate':gw,'n':nw,'rebalance':rw,'entry_exit':ew});dump(OUT/'manifest.json',manifest(OUT));print(json.dumps({'status':'COMPLETE','classification':classification,'decision':json.loads((OUT/'final_decision.json').read_text())},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
