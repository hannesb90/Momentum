"""Exposed-data falsification of fixed H0->ET->Top20; no selection search."""
import json, math, sys
from pathlib import Path
import numpy as np
from scipy.stats import norm
V=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
OUT=V/'research_k/h0_extratrees_ablation_residual_audit_results.json'
H={1:'4w',2:'8w',3:'13w',6:'26w',13:'52w'}
F={'h0_score_rank':[0,1],'momentum_12m':[2,3,4,5,6,7,8,9],'high52_drawdown':[17,18],'trend_ma':[13,14,15,16],'market_regime':[21,22],'volatility_risk':[10,11,12,19,20],'size_beta':'NOT_AVAILABLE_PIT'}
def fwd(ret,ds,i,k,h):
 if i+h-1>=len(ds): return None
 x=1.
 for j in range(h): x*=1+ret.get((k,ds[i+j]),0.)
 return x-1
def fit(obs,cut,drop=[]):
 ix=[i for i in range(len(R.NAMES)) if i not in drop];tr=[r for r in obs if r['y'] is not None and r['date']<=cut];x=np.asarray([r['x'] for r in tr],float)[:,ix];med=np.nanmedian(x,0);x=np.where(np.isnan(x),med,x);return R.make('extra_trees').fit(x,[r['y'] for r in tr]),med,ix
def pred(m,med,x,ix):
 z=np.asarray(x,float)[ix];return float(m.predict(np.where(np.isnan(z),med,z)[None,:])[0])
def records(d,cut,start,end,drop=[]):
 rows,ds,ret,sched,ser,obs=d;m,med,ix=fit(obs,cut,drop);out=[]
 for i,day in enumerate(ds):
  if not(start<=day<=end and sched(i,day)):continue
  rr,x=R.state(d,day);top=rr[:30];p={r['kod']:pred(m,med,x[r['kod']],ix) for r in top};keep=set(sorted(p,key=lambda k:(-p[k],k))[:20])
  for r in top:
   for h,n in H.items():
    y=fwd(ret,ds,i,r['kod'],h)
    if y is not None:out.append({'date':day,'kod':r['kod'],'group':'KEEP20' if r['kod'] in keep else 'DROP10','h':n,'y':y,'x':x[r['kod']],'et':p[r['kod']]})
 return out
def kd(z,key='y'):
 a=[r[key] for r in z if r['group']=='KEEP20'];b=[r[key] for r in z if r['group']=='DROP10'];return {'keep_mean':float(np.mean(a)),'drop_mean':float(np.mean(b)),'diff_mean':float(np.mean(a)-np.mean(b)),'keep_median':float(np.median(a)),'drop_median':float(np.median(b)),'diff_median':float(np.median(a)-np.median(b)),'n_keep':len(a),'n_drop':len(b)}
def nw(v,L=3):
 v=np.asarray(v);u=v-v.mean();g0=np.mean(u*u);lr=g0
 for l in range(1,min(L,len(v)-1)+1):lr+=2*(1-l/(L+1))*np.mean(u[l:]*u[:-l])
 se=math.sqrt(max(0.,lr)/len(v));t=v.mean()/se if se else 0.;return {'mean':float(v.mean()),'hac_se':float(se),'t':float(t),'p_value':float(2*norm.sf(abs(t))),'n_rebalances':len(v)}
def residual(d,cut,start,end):
 base=records(d,cut,start,end);obs=d[-1];out={}
 # Controls are all fixed ET inputs; OLS is trained only before evaluation cutoff.
 for hh in H.values():
  tr=[]; rows,ds,ret,sched,ser,_=d
  for i,day in enumerate(ds):
   if day>cut:break
   if not sched(i,day):continue
   rr,x=R.state(d,day)
   for r in rr:
    y=fwd(ret,ds,i,r['kod'],list(H.keys())[list(H.values()).index(hh)])
    if y is not None:tr.append((x[r['kod']],y))
  X=np.asarray([a for a,b in tr],float);med=np.nanmedian(X,0);X=np.where(np.isnan(X),med,X);X=np.c_[np.ones(len(X)),X];y=np.asarray([b for a,b in tr]);coef=np.linalg.lstsq(X,y,rcond=None)[0]
  z=[dict(r) for r in base if r['h']==hh]
  for r in z:
   q=np.where(np.isnan(r['x']),med,r['x']);r['resid']=r['y']-float(np.r_[1,q]@coef)
  dates=sorted({r['date'] for r in z});per=[]
  for day in dates:per.append(kd([r for r in z if r['date']==day],'resid')['diff_mean'])
  raw=kd(z);rz=kd(z,'resid');vals=np.asarray([r['resid'] for r in z]);lo,hi=np.quantile(vals,[.01,.99]);trim=[r for r in z if lo<=r['resid']<=hi]
  loo=[]
  for k in {r['kod'] for r in z}:loo.append(kd([r for r in z if r['kod']!=k],'resid')['diff_mean'])
  out[hh]={'raw':raw,'residual':rz,'hac':nw(per),'trimmed_residual':kd(trim,'resid'),'leave_one_stock_out':{'median':float(np.median(loo)),'min':float(np.min(loo)),'max':float(np.max(loo))},'residual_share_of_raw':float(rz['diff_mean']/raw['diff_mean']) if raw['diff_mean'] else None}
 return out
def main():
 d=T.data();mode=sys.argv[1] if len(sys.argv)>1 else 'all';o=json.loads(OUT.read_text()) if OUT.exists() else {'version':'H0_ET_ABLATION_RESIDUAL_V1','exposed_data':True,'families':{k:v for k,v in F.items()},'periods':{}}
 # Persistent, one-unit phases keep this audit reproducible under job limits.
 if mode.startswith('base:'):
  name=mode.split(':')[1]; spec={'2017':('2016-12-28','2017-01-25','2017-12-27'),'2018':('2017-12-27','2018-01-24','2018-12-26'),'2019':('2017-12-27','2019-01-02','2019-12-25'),'2018_2019':('2017-12-27','2018-01-24','2019-12-25')}[name]
  print('building base',name,flush=True);z=records(d,*spec);print('writing base',name,flush=True);(V/'research_k'/f'h0_et_ablation_records_{name}.json').write_text(json.dumps(z,default=float));print('base checkpoint',name);return
 if mode.startswith('abl:'):
  _,name,fam=mode.split(':');spec={'2017':('2016-12-28','2017-01-25','2017-12-27'),'2018':('2017-12-27','2018-01-24','2018-12-26'),'2019':('2017-12-27','2019-01-02','2019-12-25'),'2018_2019':('2017-12-27','2018-01-24','2019-12-25')}[name];p=V/'research_k'/f'h0_et_ablation_records_{name}.json';full=json.loads(p.read_text());o['periods'].setdefault(name,{'full':{h:kd([r for r in full if r['h']==h]) for h in H.values()},'ablation':{},'residual':None});idx=F[fam];q=records(d,*spec,idx);o['periods'][name]['ablation'][fam]={h:kd([r for r in q if r['h']==h]) for h in H.values()};OUT.write_text(json.dumps(o,indent=2));print('ablation checkpoint',name,fam);return
 if mode.startswith('res:'):
  _,name=mode.split(':');spec={'2017':('2016-12-28','2017-01-25','2017-12-27'),'2018':('2017-12-27','2018-01-24','2018-12-26'),'2019':('2017-12-27','2019-01-02','2019-12-25'),'2018_2019':('2017-12-27','2018-01-24','2019-12-25')}[name];o['periods'].setdefault(name,{});o['periods'][name]['residual']=residual(d,*spec);OUT.write_text(json.dumps(o,indent=2));print('residual checkpoint',name);return
 for name,cut,st,en in [('2017','2016-12-28','2017-01-25','2017-12-27'),('2018_2019','2017-12-27','2018-01-24','2019-12-25')]:
  if mode not in ('all',name):continue
  full=records(d,cut,st,en);ab={};o['periods'].setdefault(name,{'full':{h:kd([r for r in full if r['h']==h]) for h in H.values()},'ablation':{},'residual':None})
  for fam,idx in F.items():
   if isinstance(idx,str):ab[fam]=idx;continue
   q=records(d,cut,st,en,idx);ab[fam]={h:kd([r for r in q if r['h']==h]) for h in H.values()}
   o['periods'][name]['ablation']=ab;O.write_text(json.dumps(o,indent=2));print('checkpoint',name,fam,flush=True)
  o['periods'][name]['ablation']=ab;o['periods'][name]['residual']=residual(d,cut,st,en);O.write_text(json.dumps(o,indent=2));print('wrote',name,flush=True)
if __name__=='__main__':main()
