from __future__ import annotations
import hashlib,json,math
from collections import defaultdict,Counter
from datetime import date,timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

V2=Path('/home/hannesb/momentum_v2'); COST=.002
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=1,sort_keys=True)+'\n')
def manifest(root):
 root=Path(root);fs=[]
 for p in sorted(root.rglob('*')):
  if p.is_file() and p.name!='manifest.json':fs.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 return {'files':fs,'aggregate_sha256':hashlib.sha256(json.dumps(fs,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
def load_decision(panel_name,features):
 panel=json.loads((V2/'panels'/panel_name).read_text()); rows=[]
 for r in panel: rows.append({'kod':r['kod'],'panel_date':r['panel_date'],'price_date':r['price_date'],'has_fundamenta':r.get('has_fundamenta'),**{f:r.get(f) for f in features}})
 d=pd.DataFrame(rows); assert not any(c.startswith('target') or c=='y' for c in d.columns); return d
def target_map():
 x=json.loads((V2/'panels/target_table.json').read_text());return {(k,r['panel_date']):r.get('target_fwd52w') for k,rs in x.items() for r in rs}
def evaluation(decision):
 tm=target_map(); z=decision[['kod','panel_date']].copy();z['y']=[tm[(k,d)] for k,d in zip(z.kod,z.panel_date)];return z[z.y.notna()].copy()
def splits(decision):
 specs=[('validation_2023','validation','2023-01-01','2023-12-31'),('oos_2024','test','2024-01-01','2024-12-31'),('oos_2025','test','2025-01-01','2025-12-31')];out=[]
 for name,role,lo,hi in specs:
  cutoff=(date.fromisoformat(lo)-timedelta(weeks=52)).isoformat();ev=decision[(decision.panel_date>=lo)&(decision.panel_date<=hi)]
  out.append({'name':name,'role':role,'eval_from':lo,'eval_to':hi,'train_to':cutoff,'n_decision_eval':len(ev),'decision_eval_dates':ev.panel_date.nunique()})
 return out
def finite(x):return None if x is None or not math.isfinite(float(x)) else float(x)
def ic_metrics(scores,targets,n=30):
 x=scores.merge(targets,on=['kod','panel_date'],how='inner',validate='one_to_one');per=[]
 for dt,g in x.groupby('panel_date',sort=True):
  ic=finite(spearmanr(g.score,g.y).statistic) if g.score.nunique()>1 else None;top=g.sort_values(['score','kod'],ascending=[False,False]).head(n);ti=finite(spearmanr(top.score,top.y).statistic) if top.score.nunique()>1 else None
  per.append({'panel_date':dt,'n':len(g),'ic52':ic,'topN_ic52':ti,'distinct_scores':g.score.nunique(),'tie_share':1-g.score.nunique()/len(g)})
 vals=[r['ic52'] for r in per if r['ic52'] is not None];tv=[r['topN_ic52'] for r in per if r['topN_ic52'] is not None];years={}
 for y in sorted({r['panel_date'][:4] for r in per}):
  v=[r['ic52'] for r in per if r['panel_date'].startswith(y)];years[y]={'n_dates':len(v),'mean_ic52':finite(np.mean(v)),'median_ic52':finite(np.median(v)),'positive_share':finite(np.mean(np.array(v)>0))}
 return {'n_obs':len(x),'n_dates':len(per),'mean_ic52':finite(np.mean(vals)),'median_ic52':finite(np.median(vals)),'positive_ic_share':finite(np.mean(np.array(vals)>0)),'mean_topN_ic52':finite(np.mean(tv)),'median_topN_ic52':finite(np.median(tv)),'calendar_year':years,'score_quality':{'min_distinct':min(r['distinct_scores'] for r in per),'max_tie_share':max(r['tie_share'] for r in per)},'per_date':per}
def price_returns():
 core=json.loads((V2/'panels/core_panel.json').read_text());prices=json.loads((V2/'validated/prices/prices_validated.json').read_text());terminal=json.loads((V2/'validated/terminal_events.json').read_text());by=defaultdict(dict)
 for r in core:by[r['kod']][r['panel_date']]=r['price_date']
 dates=sorted({r['panel_date'] for r in core});nxt=dict(zip(dates,dates[1:]));adj={k:{r['d']:r['adj'] for r in rs} for k,rs in prices.items()};last={k:rs[-1]['d'] for k,rs in prices.items()};out={}
 for k,ds in by.items():
  for dt,p0d in ds.items():
   nd=nxt.get(dt)
   if not nd:continue
   p1d=ds.get(nd)
   if p1d:out[(k,dt)]=adj[k][p1d]/adj[k][p0d]-1
   elif k in terminal and dt<terminal[k]['event_date']<=nd:out[(k,dt)]=adj[k][last[k]]/adj[k][p0d]-1
   else:out[(k,dt)]=0.0
 return out
def sector_map():
 live=json.loads((V2/'docs/probes/instruments_live.json').read_text());bi={(r.get('isin')or'').upper():r.get('sectorId') for r in live};master=json.loads((V2/'docs/probes/instrument_master.json').read_text());out={}
 for r in master:
  e=r.get('eodhd')or{};k=e.get('code');isin=(e.get('isin')or'').upper()
  if k and k not in out:out[k]=bi.get(isin)
 return out
def annualized(rs):
 if not rs:return None
 w=np.prod(1+np.array(rs));return finite(w**(13/len(rs))-1) if w>0 else -1.0
def build_portfolio(scores,n=30,every=1,cost=COST,model='model',eligible_col=None,buffer=None,returns_map=None):
 forbidden=[c for c in scores.columns if c.startswith('target') or c=='y'];assert not forbidden,f'DECISION LEAK: {forbidden}'
 pret=price_returns() if returns_map is None else returns_map;sec=sector_map();dates=sorted(scores.panel_date.unique());prev=[];hold=[];trades=[];periods=[];rankings=[];contrib=defaultdict(float);secs=Counter()
 for ix,dt in enumerate(dates):
  g=scores[scores.panel_date==dt].sort_values(['score','kod'],ascending=[False,False]); rankings.extend({'model':model,'panel_date':dt,'rank':i+1,'kod':r.kod,'score':float(r.score)} for i,(_,r) in enumerate(g.iterrows()));ge=g if eligible_col is None else g[g[eligible_col].fillna(False)]
  reb=ix%every==0 or not prev
  if reb and buffer and prev:
   ranks={k:i+1 for i,k in enumerate(g.kod)};keep=[k for k in prev if ranks.get(k,10**9)<=buffer and k in set(ge.kod)];ids=keep+[k for k in ge.kod if k not in keep][:n-len(keep)]
  elif reb:ids=list(ge.head(n).kod)
  else:ids=[k for k in prev if k in set(ge.kod)]
  if not reb and len(ids)<n:ids+= [k for k in ge.kod if k not in ids][:n-len(ids)]
  buys=sorted(set(ids)-set(prev));sells=sorted(set(prev)-set(ids));turn=len(buys)/n if prev else len(ids)/n;gross=sum(pret.get((k,dt),0) for k in ids)/n;net=gross-cost*turn;bench=float(np.mean([pret.get((k,dt),0) for k in g.kod]))
  hold.extend({'model':model,'panel_date':dt,'kod':k,'weight':1/n,'rebalance':reb} for k in ids);trades.extend([{'model':model,'panel_date':dt,'kod':k,'side':'BUY','weight':1/n} for k in buys]+[{'model':model,'panel_date':dt,'kod':k,'side':'SELL','weight':1/n} for k in sells]);periods.append({'model':model,'panel_date':dt,'gross_return':gross,'net_return':net,'benchmark_return':bench,'turnover':turn,'transaction_cost':cost*turn,'n_holdings':len(ids),'rebalance':reb})
  for k in ids:contrib[k]+=pret.get((k,dt),0)/n;secs[str(sec.get(k)or'UNKNOWN')]+=1
  prev=ids
 nr=[p['net_return'] for p in periods];gr=[p['gross_return'] for p in periods];br=[p['benchmark_return'] for p in periods];ex=np.array(nr)-np.array(br);w=np.cumprod(1+np.array(nr));dd=w/np.maximum.accumulate(w)-1;ranked=sorted(contrib.items(),key=lambda x:x[1],reverse=True)
 def leave(excluded):
  rr=[];old=[]
  for p in periods:
   ids=[h['kod'] for h in hold if h['panel_date']==p['panel_date'] and h['kod'] not in excluded];buys=set(ids)-set(old);rr.append(sum(pret.get((k,p['panel_date']),0) for k in ids)/n-cost*len(buys)/n);old=ids
  return annualized(rr)
 top3=[k for k,_ in ranked[:3]];metrics={'cagr_net':annualized(nr),'cagr_gross':annualized(gr),'benchmark_cagr':annualized(br),'annualized_excess':annualized(nr)-annualized(br),'sharpe_excess':finite(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if len(ex)>1 and ex.std(ddof=1)>0 else None,'max_drawdown':finite(dd.min()),'mean_turnover':finite(np.mean([p['turnover'] for p in periods])),'hit_rate':finite(np.mean(ex>0)),'top3_tickers':top3,'leave_top3_out_cagr':leave(set(top3)),'best_ticker':ranked[0] if ranked else None,'worst_ticker':ranked[-1] if ranked else None,'sector_selection_share':{k:v/sum(secs.values()) for k,v in secs.items()}}
 return metrics,{'rankings':rankings,'holdings':hold,'trades':trades,'returns':periods}
