"""Fixed H0 candidate-pool expansion audit. No tuning or selection."""
import json,sys
from pathlib import Path
import numpy as np
V=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
import stack_h_repaired_h012 as S
OUT=V/'research_k/h0_extratrees_broad_pool_top30_audit_results.json'; POOLS=(40,50,60,100); COST=.002; H={1:'4w',2:'8w',3:'13w',6:'26w',13:'52w'}
def forward(ret,dates,i,k,h):
 if i+h-1>=len(dates):return None
 z=1.
 for j in range(h):z*=1+ret.get((k,dates[i+j]),0.)
 return z-1
def blocks(v,dates,start,end,sched):
 ix=[i for i,d in enumerate(dates) if start<=d<=end];cuts=[j for j,i in enumerate(ix) if sched(i,dates[i])]+[len(ix)];out=[];a=0
 for b in cuts:
  if b>a:out.append(float(np.prod(1+np.asarray(v[a:b]))-1));a=b
 return out
def metric(v,turn,bl):
 q=S.stat(np.asarray(v));q.update({'total_return':float(np.prod(1+np.asarray(v))-1),'turnover':float(sum(turn)),'transaction_cost':float(COST*sum(turn)),'mean_rebalance_return':float(np.mean(bl)),'median_rebalance_return':float(np.median(bl)),'hit_rate_rebalance':float(np.mean(np.asarray(bl)>0))});return q
def run(d,cut,start,end,pool):
 ranks,dates,ret,sched,ser,obs=d;m,med=R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<=cut]);ha=[];eb=[];ta=[];tb=[];pa=[];pb=[];ev=[];old=[];new=[]
 for i,day in enumerate(dates):
  if not old or sched(i,day):
   base=[r['kod'] for r in ranks[day][:30]];rr,x=R.state(d,day);cand=[r['kod'] for r in rr[:pool]];p=dict(zip([r['kod'] for r in rr],R.pred(m,med,[x[r['kod']] for r in rr])));cur=sorted(cand,key=lambda k:(-p[k],k))[:30];ca=len(set(base)-set(old))/30 if old else 0.;cb=len(set(cur)-set(new))/30 if new else 0.;old=base;new=cur
   if start<=day<=end:
    ins=[k for k in cur if k not in base];outs=[k for k in base if k not in cur];ev.append({'date':day,'keep_h0_top30':30-len(ins),'replaced':len(ins),'in_by_rank':{b:sum(1 for k in ins if next(j+1 for j,r in enumerate(rr) if r['kod']==k) in rng) for b,rng in {'31_40':range(31,41),'41_50':range(41,51),'51_60':range(51,61),'61_100':range(61,101)}.items()},'in_out':{hn:{'in':[forward(ret,dates,i,k,h) for k in ins if forward(ret,dates,i,k,h) is not None],'out':[forward(ret,dates,i,k,h) for k in outs if forward(ret,dates,i,k,h) is not None]} for h,hn in H.items()}})
  else:ca=cb=0.
  if start<=day<=end:ha.append(sum(ret.get((k,day),0.) for k in old)/30-COST*ca);eb.append(sum(ret.get((k,day),0.) for k in new)/30-COST*cb);ta.append(ca);tb.append(cb)
 ba,bb=blocks(ha,dates,start,end,sched),blocks(eb,dates,start,end,sched);z=np.asarray(eb)-np.asarray(ha);lo,hi=np.quantile(z,[.01,.99]);
 # stock LOO: compare replacement-event IN/OUT differences after excluding each stock
 pairs=[]
 for e in ev:
  for h in H.values():
   for a in e['in_out'][h]['in']:
    for b in e['in_out'][h]['out']:pairs.append((a-b,h))
 return {'h0_top30':metric(ha,ta,ba),'et_top30':metric(eb,tb,bb),'delta':{k:float(metric(eb,tb,bb)[k]-metric(ha,ta,ba)[k]) for k in metric(ha,ta,ba)},'robustness':{'mean_daily_delta':float(z.mean()),'median_daily_delta':float(np.median(z)),'trimmed_mean_daily_delta':float(z[(z>=lo)&(z<=hi)].mean()),'positive_day_share':float(np.mean(z>0))},'events':ev}
def summarize(x):
 ev=x['events'];out={'retention':{'mean_kept':float(np.mean([e['keep_h0_top30'] for e in ev])),'mean_replaced':float(np.mean([e['replaced'] for e in ev]))},'in_by_rank':{},'in_minus_out':{}}
 for b in ['31_40','41_50','51_60','61_100']:out['in_by_rank'][b]=float(np.mean([e['in_by_rank'][b] for e in ev]))
 for h in H.values():
  ins=[v for e in ev for v in e['in_out'][h]['in']];outs=[v for e in ev for v in e['in_out'][h]['out']];out['in_minus_out'][h]={'n_in':len(ins),'n_out':len(outs),'mean_in':float(np.mean(ins)) if ins else None,'mean_out':float(np.mean(outs)) if outs else None,'diff':float(np.mean(ins)-np.mean(outs)) if ins and outs else None,'median_diff':float(np.median(ins)-np.median(outs)) if ins and outs else None}
 return out
def main():
 d=T.data();sel=sys.argv[1] if len(sys.argv)>1 else 'all';o=json.loads(OUT.read_text()) if OUT.exists() else {'version':'H0_ET_BROAD_POOL_TOP30_V1','exposed_data':True,'pools':list(POOLS),'periods':{}}
 specs=[('2017','2016-12-28','2017-01-25','2017-12-27'),('2018','2017-12-27','2018-01-24','2018-12-26'),('2019','2017-12-27','2019-01-02','2019-12-25'),('2018_2019','2017-12-27','2018-01-24','2019-12-25'),('all_2017_2019','2016-12-28','2017-01-25','2019-12-25')]
 for n,c,s,e in specs:
  if sel not in ('all',n):continue
  o['periods'].setdefault(n,{})
  for p in POOLS:
   if str(p) in o['periods'][n]: continue
   x=run(d,c,s,e,p);o['periods'][n][str(p)]={k:v for k,v in x.items() if k!='events'};o['periods'][n][str(p)]['mechanism']=summarize(x);OUT.write_text(json.dumps(o,indent=2));print('done',n,p,flush=True)
if __name__=='__main__':main()
