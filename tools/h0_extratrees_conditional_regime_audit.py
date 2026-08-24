"""Preregistered univariate regime audit; fixed H0/ET only."""
import json,math
from pathlib import Path
import numpy as np
from scipy.stats import norm
V=Path('/home/hannesb/momentum_v2');import sys;sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
O=V/'research_k/h0_extratrees_conditional_regime_audit_results.json';P=V/'research_k/H0_EXTRATREES_CONDITIONAL_REGIME_AUDIT_PREREGISTRATION.json'
def nw(x):
 x=np.array(x);u=x-x.mean();g=np.mean(u*u)
 for l in range(1,min(3,len(x)-1)+1):g+=2*(1-l/4)*np.mean(u[l:]*u[:-l])
 se=math.sqrt(max(g,0)/len(x));t=x.mean()/se if se else 0;return {'se':float(se),'t':float(t),'p':float(2*norm.sf(abs(t)))}
def main():
 d=T.data();rank,ds,ret,sched,ser,obs=d; rows=[]
 for yr,cut,st,en in [('2017','2016-12-28','2017-01-25','2017-12-27'),('2018','2017-12-27','2018-01-24','2018-12-26'),('2019','2017-12-27','2019-01-02','2019-12-25')]:
  m,med=R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<=cut]); reb=[]
  for i,day in enumerate(ds):
   if not(st<=day<=en and sched(i,day)):continue
   rr,x=R.state(d,day);top=rr[:30];base=[r['kod'] for r in top];p=dict(zip([r['kod'] for r in rr],R.pred(m,med,[x[r['kod']] for r in rr])));et=sorted(base,key=lambda k:(-p[k],k))[:20]
   j=next((q for q in range(i+1,len(ds)) if sched(q,ds[q])),min(i+2,len(ds)))
   def comp(a):
    z=1
    for q in range(i,j):z*=1+sum(ret.get((k,ds[q]),0) for k in a)/len(a)
    return z-1
   sc=np.array([r['score'] for r in top],float);xx=np.array([x[k] for k in base],float); vals={'market_breadth':float(xx[0,22]),'market_volatility':float(np.nanmean(xx[:,11])),'cross_sectional_dispersion':float(np.nanstd(xx[:,6])),'h0_top30_score_dispersion':float(np.nanstd(sc)),'h0_top20_bottom10_score_spread':float(np.nanmean(sc[:20])-np.nanmean(sc[20:])),'cross_sectional_momentum_dispersion':float(np.nanstd(xx[:,6])),'top30_positive_trend_share':float(np.nanmean(xx[:,13]>0)),'market_index_trend':float(xx[0,21])}
   reb.append({'year':yr,'delta':comp(et)-comp(base),'regime':vals,'et_gt_h0':comp(et)>comp(base,'') if False else comp(et)>comp(base),'stocks':{'keep':et,'drop':[k for k in base if k not in et]}})
  rows+=reb
 out={'version':'H0_ET_CONDITIONAL_REGIME_V1','preregistration':json.loads(P.read_text()),'rows':len(rows),'variables':{}}
 for v in rows[0]['regime']:
  cuts=np.quantile([r['regime'][v] for r in rows],[1/3,2/3]);out['variables'][v]={}
  for y in ['2017','2018','2019']:
   z=[r for r in rows if r['year']==y]
   out['variables'][v][y]={}
   for n,(lo,hi) in {'LOW':(-np.inf,cuts[0]),'MID':(cuts[0],cuts[1]),'HIGH':(cuts[1],np.inf)}.items():
    q=[r['delta'] for r in z if lo<=r['regime'][v]<(hi if n!='HIGH' else np.inf)]
    if q: out['variables'][v][y][n]={'n':len(q),'mean':float(np.mean(q)),'median':float(np.median(q)),'hit':float(np.mean(np.array(q)>0)),'trimmed_mean':float(np.mean(np.sort(q)[1:-1])) if len(q)>2 else float(np.mean(q)),**nw(q)}
 O.write_text(json.dumps(out,indent=2));print('wrote',O)
if __name__=='__main__':main()
