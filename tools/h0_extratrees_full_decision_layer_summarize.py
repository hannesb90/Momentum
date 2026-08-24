"""Summarise persisted fixed-model decision ledger; no model training."""
import json,math
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
V=Path('/home/hannesb/momentum_v2');R=V/'research_k/h0_extratrees_full_decision_layer_events.json';O=V/'research_k/h0_extratrees_full_decision_layer_audit_results.json'
e=json.loads(R.read_text());H=['4w','8w','13w','26w','52w']
def stats(z,h):
 z=[x for x in z if x.get('forward',{}).get(h) is not None and np.isfinite(x.get('et_score',np.nan))];y=np.array([x['forward'][h] for x in z]);s=np.array([x['et_score'] for x in z]);ic=float(spearmanr(s,y).statistic) if len(z)>2 and s.std() and y.std() else None;q=np.quantile(s,[.2,.8]) if len(z)>4 else [0,0];lo=y[s<=q[0]];hi=y[s>=q[1]]
 return {'n':len(z),'rank_ic':ic,'mean_return':float(y.mean()) if len(y) else None,'median_return':float(np.median(y)) if len(y) else None,'top_minus_bottom':float(hi.mean()-lo.mean()) if len(lo) and len(hi) else None,'hit':float(np.mean(y>0)) if len(y) else None}
out={'version':'H0_ET_FULL_DECISION_LAYER_AUDIT_V1','event_count':len(e),'states':{},'exit_opportunity_cost':{},'swap':{}}
for st in ['ENTRY','HOLD','RE_ENTRY','EXIT']:
 out['states'][st]={}
 for p,z in [('2017',[x for x in e if x['state']==st and x['date'][:4]=='2017']),('2018',[x for x in e if x['state']==st and x['date'][:4]=='2018']),('2019',[x for x in e if x['state']==st and x['date'][:4]=='2019']),('all',[x for x in e if x['state']==st])]:out['states'][st][p]={h:stats(z,h) for h in H}
 # Existing-score quintiles and score-change diagnostic; no action threshold inferred.
 z=[x for x in e if x['state']==st and x.get('forward',{}).get('8w') is not None and np.isfinite(x.get('et_score',np.nan))]
 if len(z)>=5:
  s=np.array([x['et_score'] for x in z]);y=np.array([x['forward']['8w'] for x in z]);cuts=np.quantile(s,[.2,.4,.6,.8]);bins=[y[s<=cuts[0]],y[(s>cuts[0])&(s<=cuts[1])],y[(s>cuts[1])&(s<=cuts[2])],y[(s>cuts[2])&(s<=cuts[3])],y[s>cuts[3]]];out['states'][st]['score_quintiles_8w']=[{'n':len(a),'mean':float(a.mean()),'median':float(np.median(a))} for a in bins]
z=[x for x in e if x['state']=='EXIT' and x.get('replacement')]
for h in H:
 q=[x for x in z if x['forward'].get(h) is not None and x.get('replacement_forward',{}).get(h) is not None and np.isfinite(x.get('et_score',np.nan))];oc=np.array([x['forward'][h]-x['replacement_forward'][h] for x in q]);s=np.array([x['et_score'] for x in q]);out['exit_opportunity_cost'][h]={'n':len(q),'mean_retained_minus_replacement':float(oc.mean()) if len(q) else None,'median':float(np.median(oc)) if len(q) else None,'et_score_ic':float(spearmanr(s,oc).statistic) if len(q)>2 and s.std() and oc.std() else None,'premature_exit_share':float(np.mean(oc>0)) if len(q) else None}
 # fixed-seed bootstrap plus exact leave-one-stock/date-out for economic opportunity cost
 rng=np.random.default_rng(20260816); bs=[]
 for _ in range(1000): bs.append(float(np.mean(rng.choice(oc,len(oc),replace=True))))
 by_stock=[];by_date=[]
 for key,arr in [('ticker',by_stock),('date',by_date)]:
  for val in sorted({x[key] for x in q}):
   w=[x['forward'][h]-x['replacement_forward'][h] for x in q if x[key]!=val]
   if w:arr.append(float(np.mean(w)))
 out['exit_opportunity_cost'][h].update({'bootstrap_ci_95':[float(np.quantile(bs,.025)),float(np.quantile(bs,.975))],'trimmed_mean':float(np.mean(oc[(oc>=np.quantile(oc,.01))&(oc<=np.quantile(oc,.99))])),'leave_one_stock_out':{'median':float(np.median(by_stock)),'min':float(np.min(by_stock)),'max':float(np.max(by_stock))},'leave_one_rebalance_out':{'median':float(np.median(by_date)),'min':float(np.min(by_date)),'max':float(np.max(by_date))},'top1_share':float(np.max(oc)/np.sum(oc)) if np.sum(oc) else None})
race=json.loads((V/'research_k/h0_validator_model_race_1419_results.json').read_text())['models']['extra_trees']
out['existing_portfolio_validator_results']={'exit':{p:race[p]['exit_delta'] for p in race},'entry':{p:race[p]['entry_delta'] for p in race}}
out['limitations']=['No separately persisted event-level portfolio ledger exists for the historical entry/exit validator simulations; their saved CAGR deltas are reported, but event-level error-asymmetry and turnover decomposition cannot be reconstructed without rerunning the implementation.','DEMOTION is represented by EXIT in the existing H0 Top-30 transition ledger; no distinct state exists in the source implementation.']
out['classification']='PROMISING-BUT-UNPROVEN';O.write_text(json.dumps(out,indent=2));print('wrote',O)
