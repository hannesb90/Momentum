from __future__ import annotations
import math
from collections import Counter,defaultdict
from datetime import date
import numpy as np

from decision_portfolio_v2 import V2,COST,finite,annualized,sector_map
import json

def execution_returns():
 """Return and execution metadata using first close strictly after each boundary."""
 core=json.loads((V2/'panels/core_panel.json').read_text());prices=json.loads((V2/'validated/prices/prices_validated.json').read_text());terminal=json.loads((V2/'validated/terminal_events.json').read_text())
 dates=sorted({r['panel_date'] for r in core});nxt=dict(zip(dates,dates[1:]));out={};meta={}
 for k,rs in prices.items():
  ds=[r['d'] for r in rs];adj={r['d']:r['adj'] for r in rs}
  def first_after(boundary):
   return next((x for x in ds if x>boundary),None)
  for dt in dates:
   nd=nxt.get(dt);entry=first_after(dt)
   base={'decision_date':dt,'entry_execution_date':entry,'entry_price_adjusted':adj.get(entry) if entry else None,'entry_strictly_after_decision':bool(entry and entry>dt),'next_panel_date':nd}
   if not nd:
    meta[(k,dt)]={**base,'status':'NO_NEXT_PANEL_BOUNDARY','exit_valuation_date':None};continue
   if not entry or entry>nd:
    out[(k,dt)]=0.0;meta[(k,dt)]={**base,'status':'UNFILLED_BEFORE_NEXT_BOUNDARY','exit_valuation_date':None};continue
   exitd=first_after(nd);ev=terminal.get(k)
   if exitd:
    out[(k,dt)]=adj[exitd]/adj[entry]-1;status='EXECUTED_MARK_TO_NEXT_POST_DECISION_CLOSE'
   elif ev and entry<=ev['event_date']<=nd:
    exitd=ds[-1];out[(k,dt)]=adj[exitd]/adj[entry]-1;status='EXECUTED_VERIFIED_TERMINAL_EXIT'
   else:
    out[(k,dt)]=0.0;status='EXECUTED_NO_VERIFIABLE_EXIT_CASH_RETURN_ZERO'
   meta[(k,dt)]={**base,'status':status,'entry_price_adjusted':adj[entry],'exit_valuation_date':exitd,'exit_price_adjusted':adj.get(exitd) if exitd else None,'terminal_event_date':ev.get('event_date') if ev else None}
 return out,meta

def build_portfolio(scores,n=30,every=1,cost=COST,model='model',eligible_col=None,buffer=None,returns_map=None,execution_meta=None):
 forbidden=[c for c in scores.columns if c.startswith('target') or c=='y'];assert not forbidden,f'DECISION LEAK: {forbidden}'
 if returns_map is None or execution_meta is None:pret,emeta=execution_returns()
 else:pret,emeta=returns_map,execution_meta
 sec=sector_map();dates=sorted(scores.panel_date.unique());prev=[];prev_dt=None;hold=[];trades=[];periods=[];rankings=[];contrib=defaultdict(float);secs=Counter()
 for ix,dt in enumerate(dates):
  g=scores[scores.panel_date==dt].sort_values(['score','kod'],ascending=[False,False]);rankings.extend({'model':model,'panel_date':dt,'rank':i+1,'kod':r.kod,'score':float(r.score)} for i,(_,r) in enumerate(g.iterrows()));ge=g if eligible_col is None else g[g[eligible_col].fillna(False)]
  reb=ix%every==0 or not prev
  if reb and buffer and prev:
   ranks={k:i+1 for i,k in enumerate(g.kod)};keep=[k for k in prev if ranks.get(k,10**9)<=buffer and k in set(ge.kod)];ids=keep+[k for k in ge.kod if k not in keep][:n-len(keep)]
  elif reb:ids=list(ge.head(n).kod)
  else:ids=[k for k in prev if k in set(ge.kod)]
  if not reb and len(ids)<n:ids+=[k for k in ge.kod if k not in ids][:n-len(ids)]
  buys=sorted(set(ids)-set(prev));sells=sorted(set(prev)-set(ids));executed_buys=[k for k in buys if emeta.get((k,dt),{}).get('entry_strictly_after_decision')]
  for k in ids:
   m=emeta.get((k,dt),{});hold.append({'model':model,'panel_date':dt,'kod':k,'weight':1/n,'rebalance':reb,'period_start_execution_date':m.get('entry_execution_date'),'execution_status':m.get('status')})
  for k in buys:
   m=emeta.get((k,dt),{});trades.append({'model':model,'panel_date':dt,'decision_date':dt,'kod':k,'side':'BUY','weight':1/n,'execution_price_date':m.get('entry_execution_date'),'execution_price_adjusted':m.get('entry_price_adjusted'),'execution_status':m.get('status')})
  for k in sells:
   m=emeta.get((k,prev_dt),{}) if prev_dt else {};forced=m.get('status')=='EXECUTED_VERIFIED_TERMINAL_EXIT';decision=prev_dt if forced else dt;trades.append({'model':model,'panel_date':decision,'decision_date':decision,'recognized_by_panel_date':dt,'kod':k,'side':'TERMINAL_EXIT' if forced else 'SELL','weight':1/n,'execution_price_date':m.get('exit_valuation_date'),'execution_price_adjusted':m.get('exit_price_adjusted'),'execution_status':m.get('status')})
  # The last ranking/decision is retained but has no next frozen panel boundary.
  evaluable=any(emeta.get((k,dt),{}).get('next_panel_date') for k in g.kod)
  if evaluable:
   turn=len(executed_buys)/n if prev else len(executed_buys)/n;gross=sum(pret.get((k,dt),0) for k in ids)/n;net=gross-cost*turn;bench=float(np.mean([pret.get((k,dt),0) for k in g.kod]));periods.append({'model':model,'panel_date':dt,'gross_return':gross,'net_return':net,'benchmark_return':bench,'turnover':turn,'transaction_cost':cost*turn,'n_holdings':len(ids),'rebalance':reb,'execution_rule':'FIRST_CLOSE_STRICTLY_AFTER_DECISION'})
   for k in ids:contrib[k]+=pret.get((k,dt),0)/n
  for k in ids:secs[str(sec.get(k)or'UNKNOWN')]+=1
  prev=ids;prev_dt=dt
 nr=[p['net_return'] for p in periods];gr=[p['gross_return'] for p in periods];br=[p['benchmark_return'] for p in periods];ex=np.array(nr)-np.array(br);w=np.cumprod(1+np.array(nr));dd=w/np.maximum.accumulate(w)-1;ranked=sorted(contrib.items(),key=lambda x:x[1],reverse=True)
 def leave(excluded):
  rr=[];old=[]
  for p in periods:
   dt=p['panel_date'];ids=[h['kod'] for h in hold if h['panel_date']==dt and h['kod'] not in excluded];buys=[k for k in ids if k not in old and emeta.get((k,dt),{}).get('entry_strictly_after_decision')];rr.append(sum(pret.get((k,dt),0) for k in ids)/n-cost*len(buys)/n);old=ids
  return annualized(rr)
 top3=[k for k,_ in ranked[:3]];metrics={'cagr_net':annualized(nr),'cagr_gross':annualized(gr),'benchmark_cagr':annualized(br),'annualized_excess':annualized(nr)-annualized(br),'sharpe_excess':finite(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if len(ex)>1 and ex.std(ddof=1)>0 else None,'max_drawdown':finite(dd.min()),'mean_turnover':finite(np.mean([p['turnover'] for p in periods])),'hit_rate':finite(np.mean(ex>0)),'top3_tickers':top3,'leave_top3_out_cagr':leave(set(top3)),'best_ticker':ranked[0] if ranked else None,'worst_ticker':ranked[-1] if ranked else None,'sector_selection_share':{k:v/sum(secs.values()) for k,v in secs.items()},'n_return_periods':len(periods),'execution_rule':'FIRST_CLOSE_STRICTLY_AFTER_DECISION'}
 return metrics,{'rankings':rankings,'holdings':hold,'trades':trades,'returns':periods}
