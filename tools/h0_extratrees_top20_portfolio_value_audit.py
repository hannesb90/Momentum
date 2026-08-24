"""Direct apples-to-apples fixed H0 Top30 vs H0->ET Top20 portfolio audit."""
import json, math, sys
from pathlib import Path
import numpy as np
V=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
import stack_h_repaired_h012 as S
OUT=V/'research_k/h0_extratrees_top20_portfolio_value_audit_results.json'
C=.002
def run(d,cut,start,end):
 rows,ds,ret,sched,ser,obs=d;m,med=R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<=cut]);a=[];b=[];ra=[];rb=[];turna=[];turnb=[];priora=[];priorb=[];detail=[]
 for i,day in enumerate(ds):
  if not priora or sched(i,day):
   base=[r['kod'] for r in rows[day][:30]];rr,x=R.state(d,day);p=dict(zip([r['kod'] for r in rr],R.pred(m,med,[x[r['kod']] for r in rr])));et=sorted(base,key=lambda k:(-p[k],k))[:20];ta=len(set(base)-set(priora))/30 if priora else 0;tb=len(set(et)-set(priorb))/20 if priorb else 0;priora=base;priorb=et
   if start<=day<=end: detail.append({'date':day,'h0':base,'et':et,'turn_h0':ta,'turn_et':tb})
  else:ta=tb=0
  if start<=day<=end:a.append(sum(ret.get((k,day),0) for k in priora)/30-C*ta);b.append(sum(ret.get((k,day),0) for k in priorb)/20-C*tb);turna.append(ta);turnb.append(tb)
 # rebalance blocks generated from daily returns
 marks=[i for i,x in enumerate(detail)]
 def blocks(v):
  out=[];last=0
  # use recorded schedule dates matched to date indices
  ix=[j for j,day in enumerate([x for x in ds if start<=x<=end]) if day in {q['date'] for q in detail}]+[len(v)]
  for z in ix:
   if z>last:out.append(float(np.prod(1+np.asarray(v[last:z]))-1));last=z
  return out
 def stat(v,t,bl):
  q=S.stat(np.asarray(v));q.update({'total_return':float(np.prod(1+np.asarray(v))-1),'turnover':float(sum(t)),'transaction_cost':float(C*sum(t)),'hit_rate_rebalance':float(np.mean(np.asarray(bl)>0)),'mean_rebalance_return':float(np.mean(bl)),'median_rebalance_return':float(np.median(bl))});return q
 ba,bb=blocks(a),blocks(b);return {'a':stat(a,turna,ba),'b':stat(b,turnb,bb),'delta':{k:float(stat(b,turnb,bb).get(k,0)-stat(a,turna,ba).get(k,0)) for k in set(stat(a,turna,ba))&set(stat(b,turnb,bb))},'daily_delta':list(np.asarray(b)-np.asarray(a)),'details':detail,'rebalance_delta':[x-y for x,y in zip(bb,ba)]}
def robust(x):
 z=np.asarray(x['daily_delta']);lo,hi=np.quantile(z,[.01,.99]);trim=z[(z>=lo)&(z<=hi)];return {'mean_daily_delta':float(z.mean()),'median_daily_delta':float(np.median(z)),'trimmed_mean_daily_delta':float(trim.mean()),'top_1pct_share':float(z[z>=hi].sum()/z.sum()) if z.sum() else None,'worst_1pct_share':float(z[z<=lo].sum()/z.sum()) if z.sum() else None,'positive_day_share':float(np.mean(z>0))}
def main():
 d=T.data();o=json.loads(OUT.read_text()) if OUT.exists() else {'version':'H0_ET_TOP20_PORTFOLIO_VALUE_V1','exposed_data':True,'cost_per_one_way_turnover':C,'periods':{}}
 specs=[('2017','2016-12-28','2017-01-25','2017-12-27'),('2018','2017-12-27','2018-01-24','2018-12-26'),('2019','2017-12-27','2019-01-02','2019-12-25'),('2018_2019','2017-12-27','2018-01-24','2019-12-25'),('all_2017_2019','2016-12-28','2017-01-25','2019-12-25')]
 sel=sys.argv[1] if len(sys.argv)>1 else 'all'
 for n,c,s,e in specs:
  if sel not in ('all',n):continue
  x=run(d,c,s,e);o['periods'][n]={k:v for k,v in x.items() if k not in ('daily_delta','details','rebalance_delta')};o['periods'][n]['robustness']=robust(x);print('done',n,flush=True);OUT.write_text(json.dumps(o,indent=2))
 print('wrote',OUT)
if __name__=='__main__':main()
