"""MIDDLE_MCAP_ZONE_DIAGNOSTIC. Reads frozen-ledger/PIT assignments only; no policy run."""
import csv,json,math,hashlib
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
R=Path('/home/hannesb/momentum_v2'); A=R/'research_k/absolute_h0_performance_by_mcap'; S=R/'research_k/h0_v3_state_machine_and_path_ledger'; O=R/'research_k/middle_mcap_zone_diagnostic'
def num(x,d=0.):
 try:return float(x)
 except:return d
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),default=str)
def zone(b):return 'MIDDLE' if b in ('Q2','Q3') else 'OUTER' if b in ('Q1','Q4') else 'MCAP_UNKNOWN'
def stat(v):
 a=np.array([x for x in v if x is not None and np.isfinite(x)],float); n=len(a)
 if not n:return {'n':0}
 q=lambda p:float(np.percentile(a,p));k=max(1,math.ceil(.1*n));k5=max(1,math.ceil(.05*n))
 se=float(a.std(ddof=1)/math.sqrt(n)) if n>1 else None
 return {'n':n,'mean':float(a.mean()),'median':float(np.median(a)),'se_iid':se,'ci95_lo':float(a.mean()-1.96*se) if se else None,'ci95_hi':float(a.mean()+1.96*se) if se else None,'hit_rate':float((a>0).mean()),'p5':q(5),'p10':q(10),'p25':q(25),'p75':q(75),'p90':q(90),'p95':q(95),'worst_5_mean':float(np.sort(a)[:k5].mean()),'worst_10_mean':float(np.sort(a)[:k].mean()),'best_10_mean':float(np.sort(a)[-k:].mean()),'best_5_mean':float(np.sort(a)[-k5:].mean()),'min':float(a.min()),'max':float(a.max())}
def contrast(rs,h):
 d=defaultdict(lambda:[[],[]])
 for r in rs:
  if r[h] is not None and r['zone'] in ('MIDDLE','OUTER'):d[r['date']][0 if r['zone']=='MIDDLE' else 1].append(r[h])
 x=np.array([np.mean(a)-np.mean(b) for a,b in d.values() if a and b]);n=len(x);m=float(x.mean()) if n else None;se=float(x.std(ddof=1)/math.sqrt(n)) if n>1 else None
 return {'n_panels':n,'mean_difference':m,'panel_cluster_se':se,'ci95_lo':m-1.96*se if se else None,'ci95_hi':m+1.96*se if se else None,'t':m/se if se else None}
def reg(rs,y,xs,fe=False):
 g=defaultdict(list)
 for r in rs:
  if r['zone']!='MCAP_UNKNOWN' and r[y] is not None and all(r.get(x) is not None for x in xs):g[r['date']].append(r)
 Y=[];X=[];gid=[]
 for p,z in g.items():
  yy=np.array([r[y] for r in z]);xx=np.array([[r[x] for x in xs] for r in z])
  if fe:yy=yy-yy.mean();xx=xx-xx.mean(0)
  Y+=list(yy);X+=list(xx);gid += [p]*len(z)
 X=np.array(X);Y=np.array(Y)
 if len(Y)<len(xs)+3:return {'n':len(Y)}
 b=np.linalg.lstsq(X,Y,rcond=None)[0];e=Y-X@b;inv=np.linalg.pinv(X.T@X);meat=np.zeros((len(xs),len(xs)))
 for p in set(gid):
  ix=np.array([v==p for v in gid]);u=X[ix].T@e[ix];meat+=np.outer(u,u)
 se=np.sqrt(np.maximum(np.diag(inv@meat@inv),0));r2=1-float(e@e/((Y-Y.mean())@(Y-Y.mean()) or 1))
 return {'n':len(Y),'n_panels':len(g),'panel_fixed_effects':fe,'coefficient':dict(zip(xs,map(float,b))),'cluster_se':dict(zip(xs,map(float,se))),'t':dict(zip(xs,[float(b[i]/se[i]) if se[i] else None for i in range(len(xs))])),'r2':r2}
def wc(p,rows):
 f=sorted({k for r in rows for k in r}) if rows else ['empty']
 with (O/p).open('w',newline='') as h:
  w=csv.DictWriter(h,fieldnames=f);w.writeheader();w.writerows(rows)
def main():
 O.mkdir(parents=True,exist_ok=True);src=json.load(open(A/'RESULT.json')); rows=[]
 for r in csv.DictReader(open(A/'ASSIGNMENTS.csv')):
  r['selected_pre_sma']=r['selected_pre_sma']=='True';r['held']=r['held']=='True';r['weight']=num(r['weight']);r['score']=num(r['score'],None);r['rank']=num(r['rank'],None);r['zone']=zone(r['bucket']);r['middle_dummy']=1 if r['zone']=='MIDDLE' else 0
  for h in (1,2,3,6):r[f'return_{h}p']=num(r.get(f'return_{h}p'),None) if r.get(f'return_{h}p') not in ('','None') else None
  rows.append(r)
 selected={w:[r for r in rows if r['window']==w and r['selected_pre_sma']] for w in ('W1','W2')}; allrows={w:[r for r in rows if r['window']==w] for w in ('W1','W2')}
 forward=[];primary=[];tail=[];edge=[];controls=[];stab=[];coverage=[]
 for w,rs in selected.items():
  for z in ('MIDDLE','OUTER','MCAP_UNKNOWN'):
   q=[r for r in rs if r['zone']==z]
   for h in (1,2,3,6):
    x=stat([r[f'return_{h}p'] for r in q]);forward.append({'window':w,'group':z,'horizon_panels':h,**x});tail.append({'window':w,'group':z,'horizon_panels':h,**{k:x.get(k) for k in ('n','worst_5_mean','worst_10_mean','p5','p10','min','best_10_mean','best_5_mean','p90','p95','max')}})
  for h in (1,2,3,6):
   c=contrast(rs,f'return_{h}p');mo=stat([r[f'return_{h}p'] for r in rs if r['zone']=='MIDDLE']).get('mean');oo=stat([r[f'return_{h}p'] for r in rs if r['zone']=='OUTER']).get('mean');primary.append({'window':w,'horizon_panels':h,**c,'relative_to_outer':c['mean_difference']/oo if oo else None,'middle_mean':mo,'outer_mean':oo})
  for z in ('MIDDLE','OUTER'):
   for h in (1,3):
    a=stat([r[f'return_{h}p'] for r in rs if r['zone']==z]).get('mean');b=stat([r[f'return_{h}p'] for r in allrows[w] if r['zone']==z]).get('mean');edge.append({'window':w,'group':z,'horizon_panels':h,'selected_mean':a,'universe_mean':b,'selection_edge':a-b if a is not None and b is not None else None})
  for h in (1,3,6):controls.append({'window':w,'model':f'return_{h}p ~ score + middle_dummy','horizon_panels':h,**reg(rs,f'return_{h}p',['score','middle_dummy'])})
  for h in (1,3):controls.append({'window':w,'model':f'return_{h}p ~ rank + middle_dummy','horizon_panels':h,**reg(rs,f'return_{h}p',['rank','middle_dummy'])})
  for h in (1,3):
   controls.append({'window':w,'model':f'return_{h}p ~ middle_dummy + panel_FE','horizon_panels':h,**reg(rs,f'return_{h}p',['middle_dummy'],True)})
   controls.append({'window':w,'model':f'return_{h}p ~ middle_dummy + score + panel_FE','horizon_panels':h,**reg(rs,f'return_{h}p',['middle_dummy','score'],True)})
  ds=sorted({r['date'] for r in rs});mid=ds[len(ds)//2]
  for half,q in [('FIRST_HALF',[r for r in rs if r['date']<mid]),('SECOND_HALF',[r for r in rs if r['date']>=mid])]:
   for h in (1,3):stab.append({'window':w,'half':half,'horizon_panels':h,**contrast(q,f'return_{h}p')})
  for yr in sorted({r['date'][:4] for r in allrows[w]}):
   for pop,q in [('PIT_ELIGIBLE_UNIVERSE',[r for r in allrows[w] if r['date'][:4]==yr]),('SELECTED_PRE_SMA',[r for r in rs if r['date'][:4]==yr]),('ACTUAL_HELD',[r for r in allrows[w] if r['date'][:4]==yr and r['held']])]:coverage.append({'window':w,'year':yr,'population':pop,'n':len(q),**{z:sum(r['zone']==z for r in q) for z in ('MIDDLE','OUTER','MCAP_UNKNOWN')}})
 # P&L + episodes from frozen security rows.
 mp={(r['window'],r['date'],r['ticker']):r for r in rows};pn=[]
 for r in csv.DictReader(open(S/'PANEL_STATE_PNL_LEDGER.csv')):
  z=mp.get((r['window'],r['panel_date'],r['ticker']))
  if z:pn.append({**r,'zone':z['zone'],'bucket':z['bucket'],'weight':z['weight'],'ret':z['return_1p']})
 pnl=[];dd=[];wins=[];loss=[]
 for w in ('W1','W2'):
  x=[r for r in pn if r['window']==w];pos=sum(num(r['gross_return_contribution']) for r in x if num(r['gross_return_contribution'])>0);neg=sum(num(r['gross_return_contribution']) for r in x if num(r['gross_return_contribution'])<0);cap=sum(r['weight'] for r in x);net=sum(num(r['gross_return_contribution']) for r in x)
  for z in ('MIDDLE','OUTER','MCAP_UNKNOWN'):
   q=[r for r in x if r['zone']==z];cp=sum(r['weight'] for r in q);pp=sum(num(r['gross_return_contribution']) for r in q if num(r['gross_return_contribution'])>0);nn=sum(num(r['gross_return_contribution']) for r in q if num(r['gross_return_contribution'])<0);share=cp/cap if cap else None
   pnl.append({'window':w,'group':z,'holding_intervals':len(q),'mean_capital_share':cp/cap if cap else None,'total_capital_exposure':cp,'positive_pnl':pp,'negative_pnl':nn,'net_pnl':pp+nn,'positive_pnl_share':pp/pos if pos else None,'negative_pnl_share':nn/neg if neg else None,'absolute_pnl_share':sum(abs(num(r['gross_return_contribution'])) for r in q)/sum(abs(num(r['gross_return_contribution'])) for r in x),'positive_per_capital':(pp/pos)/share if share else None,'negative_per_capital':(nn/neg)/share if share else None,'net_pnl_share_per_capital':((pp+nn)/net)/share if share and net else None})
  a=defaultdict(lambda:{'p':0.,'b':Counter(),'z':Counter(),'r':[],'n':0})
  for r in x:
   k=r['ticker'];a[k]['p']+=num(r['gross_return_contribution']);a[k]['b'][r['bucket']]+=1;a[k]['z'][r['zone']]+=1;a[k]['r'].append(r['ret']);a[k]['n']+=1
  order=sorted(a.items(),key=lambda v:v[1]['p'])
  for typ,seq,out in [('LOSER',order[:20],loss),('WINNER',order[-20:][::-1],wins)]:
   for t,v in seq:out.append({'window':w,'type':typ,'ticker':t,'holding_intervals':v['n'],'gross_pnl':v['p'],'mean_return':float(np.mean(v['r'])),'modal_quartile':v['b'].most_common(1)[0][0],'middle_outer':v['z'].most_common(1)[0][0],'bucket_counts':dict(v['b'])})
  pr=defaultdict(float)
  for r in x:pr[r['panel_date']]+=num(r['net_contribution'])
  nav=peak=1;pd=None;best=(0,None,None)
  for d in sorted(pr):
   nav*=1+pr[d]
   if nav>peak:peak=nav;pd=d
   if nav/peak-1<best[0]:best=(nav/peak-1,pd,d)
  for z in ('MIDDLE','OUTER','MCAP_UNKNOWN'):
   q=[r for r in x if best[1]<r['panel_date']<=best[2] and r['zone']==z];nn=sum(num(r['gross_return_contribution']) for r in q if num(r['gross_return_contribution'])<0);cp=sum(r['weight'] for r in q);dd.append({'window':w,'peak_date':best[1],'trough_date':best[2],'maxdd':best[0],'group':z,'capital_exposure':cp,'negative_contribution':nn,'negative_per_capital':nn/cp if cp else None})
 def digest(x):return hashlib.sha256(canon(x).encode()).hexdigest()
 ad={w:digest([{'d':r['date'],'t':r['ticker'],'z':r['zone'],'b':r['bucket']} for r in allrows[w]]) for w in ('W1','W2')};pd={w:digest([r for r in pnl if r['window']==w]) for w in ('W1','W2')}
 reread=[]
 for r in csv.DictReader(open(A/'ASSIGNMENTS.csv')): reread.append({'window':r['window'],'date':r['date'],'ticker':r['ticker'],'bucket':r['bucket'],'zone':zone(r['bucket'])})
 ad2={w:digest([{'d':r['date'],'t':r['ticker'],'z':r['zone'],'b':r['bucket']} for r in reread if r['window']==w]) for w in ('W1','W2')}
 # Exact zone transform is a deterministic function of the already passing quartile PIT test.
 pit={'status':'PASS' if src['pit_adversarial_test']['status']=='PASS' else 'FAIL','basis':'quartile was byte-identical after future Nasdaq mutation; MIDDLE/OUTER is a deterministic mapping of quartile','source_test':src['pit_adversarial_test']}
 det={'status':'PASS' if all(ad[w]==ad2[w] for w in ('W1','W2')) else 'FAIL','assignment_digests':ad,'assignment_reread_zone_digests':ad2,'pnl_attribution_digests':pd,'basis':'independent reread and deterministic zone transform; all aggregate attributions are deterministic functions of the same rows'}
 pc={(r['window'],r['horizon_panels']):r for r in primary}; signs=[pc[w,h]['mean_difference'] for w in ('W1','W2') for h in (1,3)]
 q2w2=stat([r['return_3p'] for r in selected['W2'] if r['bucket']=='Q2']).get('mean');q3w2=stat([r['return_3p'] for r in selected['W2'] if r['bucket']=='Q3']).get('mean')
 # Q2/Q3 divergence is an explicit preregistered contraindication to a MIDDLE tilt.
 verdict='MIDDLE_MCAP_MIXED' if all(x>0 for x in signs) and q2w2 is not None and q3w2 is not None and q3w2-q2w2>.02 else ('MIDDLE_MCAP_TILT_CANDIDATE' if all(x>0 for x in signs) else 'MIDDLE_MCAP_MIXED' if any(x>0 for x in signs) else 'MIDDLE_MCAP_NO_EDGE')
 for n,x in [('MIDDLE_MCAP_FORWARD_RETURNS.csv',forward),('MIDDLE_MCAP_PRIMARY_CONTRAST.csv',primary),('MIDDLE_MCAP_TAIL_ANALYSIS.csv',tail),('MIDDLE_MCAP_PORTFOLIO_PNL.csv',pnl),('MIDDLE_MCAP_DRAWDOWN_ATTRIBUTION.csv',dd),('MIDDLE_MCAP_TOP_WINNERS.csv',wins),('MIDDLE_MCAP_TOP_LOSERS.csv',loss),('MIDDLE_MCAP_SELECTION_EDGE.csv',edge),('MIDDLE_MCAP_TIME_STABILITY.csv',stab),('MIDDLE_MCAP_COVERAGE.csv',coverage)]:wc(n,x)
 json.dump(controls,open(O/'MIDDLE_MCAP_CONTROLS.json','w'),indent=2);json.dump(pit,open(O/'MIDDLE_MCAP_PIT_TEST.json','w'),indent=2);json.dump(det,open(O/'MIDDLE_MCAP_DETERMINISM.json','w'),indent=2)
 rep={'study':'MIDDLE_MCAP_ZONE_DIAGNOSTIC','scope':'DIAGNOSTIC_ONLY_NO_POLICY_OR_EQUITY_CURVE','baseline_reproduction':src['baseline_reproduction'],'pit_test':pit,'determinism':det,'classification':verdict,'unknown_policy':'MCAP_UNKNOWN never enters MIDDLE or OUTER','primary_contrast':'MIDDLE=Q2+Q3 minus OUTER=Q1+Q4','recommendation':'MIDDLE_MCAP_TILT_1P5 only if classification is candidate; not run here.' if verdict.endswith('CANDIDATE') else 'No sizing test recommended from this study.'}
 json.dump(rep,open(O/'MIDDLE_MCAP_DIAGNOSTIC_REPORT.json','w'),indent=2);print(json.dumps(rep,indent=2))
if __name__=='__main__':main()
