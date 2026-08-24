"""Fixed-model event ledger for final H0/ET decision-layer audit."""
import json,sys
from pathlib import Path
import numpy as np
V=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
OUT=V/'research_k/h0_extratrees_full_decision_layer_audit_results.json';RAW=V/'research_k/h0_extratrees_full_decision_layer_events.json';H={1:'4w',2:'8w',3:'13w',6:'26w',13:'52w'}
def fwd(ret,ds,i,k,h):
 if i+h-1>=len(ds):return None
 z=1.
 for j in range(h):z*=1+ret.get((k,ds[i+j]),0.)
 return z-1
def main():
 d=T.data();ranks,ds,ret,sched,ser,obs=d;events=[];held=[];ever=set();lastscore={};models={'early':R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<='2016-12-28']),'late':R.fit('extra_trees',[r for r in obs if r['y'] is not None and r['date']<='2017-12-27'])}
 for i,day in enumerate(ds):
  if not sched(i,day):continue
  m,med=models['early' if day<='2017-12-27' else 'late'];rr,x=R.state(d,day);top=[r['kod'] for r in rr[:30]];p=dict(zip([r['kod'] for r in rr],R.pred(m,med,[x[r['kod']] for r in rr])));ins=[k for k in top if k not in held];outs=[k for k in held if k not in top]
  if '2017-01-25'<=day<='2019-12-25':
   for rank,k in enumerate(rr and top,1):
    state='HOLD' if k in held else ('RE_ENTRY' if k in ever else 'ENTRY');events.append({'date':day,'ticker':k,'state':state,'h0_rank':rank,'h0_score':rr[rank-1]['score'],'et_score':float(p[k]),'et_score_change':None if k not in lastscore else float(p[k]-lastscore[k]),'forward':{hn:fwd(ret,ds,i,k,h) for h,hn in H.items()}})
   # exits paired with actual same-rebalance H0 entrants, ordered by H0 ranks.
   for j,k in enumerate(outs):
    repl=ins[j] if j<len(ins) else None;events.append({'date':day,'ticker':k,'state':'EXIT','h0_rank':next((q+1 for q,r in enumerate(rr) if r['kod']==k),None),'h0_score':None,'et_score':float(p.get(k,np.nan)),'replacement':repl,'replacement_et_score':None if repl is None else float(p[repl]),'forward':{hn:fwd(ret,ds,i,k,h) for h,hn in H.items()},'replacement_forward':None if repl is None else {hn:fwd(ret,ds,i,repl,h) for h,hn in H.items()}})
  lastscore=p;ever.update(held);held=top
 RAW.write_text(json.dumps(events,default=float));OUT.write_text(json.dumps({'version':'H0_ET_FULL_DECISION_LAYER_AUDIT_V1','event_file':RAW.name,'event_count':len(events),'status':'EVENT_LEDGER_COMPLETE; diagnostics pending'},indent=2));print('wrote',len(events))
if __name__=='__main__':main()
