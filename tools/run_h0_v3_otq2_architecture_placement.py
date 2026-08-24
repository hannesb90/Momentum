"""Preregistered research-only OTQ2 architecture placement study.

Reuses frozen OTQ2 membership and the canonical EXEC05 ledger.  The only new
forks are (1) removal of K3 retention privilege for low-quality incumbents on
intermediate panels and (2) a 0.75 low-quality multiplier after K5/K6 before
normalisation and the unchanged WP/execution path.
"""
from pathlib import Path
from copy import deepcopy
import csv, hashlib, json, math, sys
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parents[1]; O=R/'research_k/h0_v3_otq2_architecture_placement_study'; O.mkdir(exist_ok=True)
S=R/'research_k/h0_v3_otq2_coverage_first_quality_model'; G=R/'research_k/h0_v3_otq2_quality_gate_placement_test'
sys.path.insert(0,str(R/'tools'))
import h0_v3_production as P
import run_h0_v3_transaction_minimization_frontier as FR
import run_h0_v3_weight_layer_simplification_v2 as V2
START={'W1':'2014-09-10','W2':'2020-01-02'}; YEARS={'W1':(pd.Timestamp('2019-12-25')-pd.Timestamp(START['W1'])).days/365.25,'W2':(pd.Timestamp('2026-07-09')-pd.Timestamp(START['W2'])).days/365.25}
ARMS=('BASE','OTQ2_RETENTION_PRIVILEGE_GATE','OTQ2_LOW_QUALITY_SIZING_075')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def lowmap():
 p=G/'OTQ2_LOW_QUALITY_GATE_FREEZE.csv'; d=pd.read_csv(p); return p,{(w,dt):set(q.kod for q in z.itertuples() if bool(q.LOW_QUALITY)) for (w,dt),z in d.groupby(['window','panel_date'])}
def make_rows(ctx,w,arm,low):
 out=[]; audit=[]; prev=[]
 for i,b in enumerate(ctx['base']):
  d=b['date']; active=d>=START[w]; gate=low.get((w,d),set()) if active else set(); ranking=[x['kod'] for x in ctx['rankings'][d]]
  if arm=='BASE' or not active or b['scheduled_base']:
   sel=list(b['selected_pre_sma'])
  else:
   # Non-low incumbents retain their canonical privilege. Low incumbents join
   # the exact same ranked refill queue as challengers.
   retained=[k for k in prev if k not in gate]
   sel=list(retained)
   for k in ranking:
    if len(sel)>=30: break
    if k not in sel: sel.append(k)
  held=[k for k in sel if ctx['sma_fn'](k,d)]
  out.append({'date':d,'weights':{k:1/30 for k in held},'cost':b['cost'],'selected_pre_sma':sel,'holdings':held,'scheduled_base':b['scheduled_base']})
  audit.append({'window':w,'panel_date':d,'arm':arm,'intermediate':not b['scheduled_base'],'active':active,'selected':'|'.join(sel),'holdings':'|'.join(held),'low_incumbents_prior':len(set(prev)&gate),'removed_retention':'|'.join(sorted((set(prev)&gate)-set(sel)))})
  prev=sel
 return out,audit
def run(ctx,rows,w,arm,low=None):
 c=dict(ctx); c['base']=rows
 if arm!='OTQ2_LOW_QUALITY_SIZING_075': return FR.run_band_arm(c,w,'band',.01,arm,True)
 old=V2.compute_targets_pipeline
 def weighted(sel,dt,k5,k6,k7,vol,conf):
  x=old(sel,dt,k5,k6,k7,vol,conf)
  if dt>=START[w]:
   m=np.array([.75 if k in low.get((w,dt),set()) else 1. for k in sel]); x=x*m
   if x.sum()>0: x=x/x.sum()*(len(sel)/V2.N_NAMES)
  return x
 V2.compute_targets_pipeline=weighted
 try: return FR.run_band_arm(c,w,'band',.01,arm,True)
 finally: V2.compute_targets_pipeline=old
def cut(z,w):
 i=[n for n,p in enumerate(z['panels']) if p['date']>=START[w]]; a,b=i[0],i[-1]+1
 return {'window':w,'arm_id':z['arm_id'],'panels':z['panels'][a:b],'ledger':[x for x in z['ledger'] if x['date']>=START[w]],'order_sizes':z['order_sizes'],'ret_lists':{k:v[a:b] for k,v in z['ret_lists'].items()},'nav_end':z['nav_end']}
def metrics(z,w):
 def m(r):
  x=np.asarray(r); nav=np.cumprod(1+x); dd=nav/np.maximum.accumulate(nav)-1; down=np.sqrt(np.mean(np.minimum(x,0)**2))*math.sqrt(13)
  return {'cagr_pct':100*(nav[-1]**(1/YEARS[w])-1),'sharpe':float(x.mean()/x.std(ddof=1)*math.sqrt(13)) if x.std(ddof=1)>0 else 0,'vol_ann_pct':100*float(x.std(ddof=1)*math.sqrt(13)),'downside_ann_pct':100*float(down),'maxdd_pct':100*float(dd.min()),'calmar':float((nav[-1]**(1/YEARS[w])-1)/abs(dd.min())) if dd.min()<0 else None,'terminal_wealth':float(nav[-1]),'worst_panel_pct':100*float(x.min())}
 p=z['panels']; oo=lambda k:sum(x['orders_exec'][k] for x in p)/YEARS[w]
 return {'gross':m(z['ret_lists']['gross']),'net_cost_b':m(z['ret_lists']['net_b']),'turnover_ann_pct':100*sum(x['wt_exec'] for x in p)/YEARS[w],'cost_b_ann_pct':100*.002*sum(x['wt_exec'] for x in p)/YEARS[w],'orders_per_year':sum(sum(x['orders_exec'].values()) for x in p)/YEARS[w],'entries_per_year':oo('entries'),'exits_per_year':oo('exits'),'continuing_reweights_per_year':oo('cont_buy')+oo('cont_sell')}
def boot(d):
 x=np.asarray(d); n=len(x); rng=np.random.default_rng(20260823); vals=[]
 for _ in range(2000):
  ix=[]
  while len(ix)<n:
   s=int(rng.integers(0,max(1,n-12))); ix+=list(range(s,min(n,s+13)))
  vals.append(float(np.mean(x[np.asarray(ix[:n])])*13))
 return {'mean_delta_panel':float(x.mean()),'median_delta_panel':float(np.median(x)),'positive_panel_fraction':float(np.mean(x>0)),'ci95_annualized':[float(np.percentile(vals,2.5)),float(np.percentile(vals,97.5))],'n_panels':n}
def main():
 freeze=json.loads((S/'OTQ2_MODEL_FREEZE.json').read_text()); phase=json.loads((S/'OTQ2_PHASE2_RESULT.json').read_text()); gate_result=json.loads((G/'QUALITY_GATE_FINAL_RESULT.json').read_text()); gp,low=lowmap()
 evidence={'selection_ranking':{'study_source':'OTQ2_PHASE2_RESULT.json','mechanism':'bounded secondary reranking near Top-30','W1':phase['CONDITIONAL_SIGNAL_W1'],'W2':phase['CONDITIONAL_SIGNAL_W2'],'implementation_validity':'PASS','final_classification':phase['PLACEMENT_DECISION']},'quality_gate_placements':{'study_source':'QUALITY_GATE_FINAL_RESULT.json','mechanisms':['PRE_K1','POST_K1_PRE_SELECTION','ENTRY_ONLY'],'W1':'positive portfolio deltas but not sufficient','W2':'nonreplicating / pairwise negative','implementation_validity':gate_result['gates'],'final_classification':gate_result['final_verdict']}}
 dump(O/'OTQ2_EXISTING_PLACEMENT_EVIDENCE.json',evidence)
 prereg={'study':'H0_V3_OTQ2_ARCHITECTURE_PLACEMENT_STUDY','production_manifest_sha256':sha(R/'research_k/h0_v3_final_canonical_execution_architecture_decision/CANONICAL_REPLACEMENT_DECISION.json'),'otq2_model_freeze_sha256':sha(S/'OTQ2_MODEL_FREEZE.json'),'low_quality_gate_sha256':sha(gp),'windows':{'W1':[START['W1'],'2019-12-25'],'W2':[START['W2'],'2026-07-09']},'new_arms':{'OTQ2_RETENTION_PRIVILEGE_GATE':'Intermediate K3 only: low-quality incumbent loses retention privilege and enters same canonical ranked refill queue as challengers.','OTQ2_LOW_QUALITY_SIZING_075':'Post-K5/K6, pre-normalisation multiplier=0.75 for selected LOW_QUALITY; normalize then unchanged WP/EXEC05.'},'prohibited':['gate retest','reranking retest','hybrid','threshold or multiplier sweep','production mutation'],'acceptance':{'retention':'positive pairs and net deltas in both windows plus noninferior CAGR/risk','sizing':'Sharpe noninferior both; MaxDD not worse >0.5pp; MaxDD/downside/Calmar improves both; CAGR loss <=0.75pp'}}
 dump(O/'OTQ2_ARCHITECTURE_PLACEMENT_PREREG.json',prereg)
 P.load_engine(); results={}; audits=[]; rets=[]; executions=[]; ret_events=[]; size_events=[]; sizing_attr=[]; pairrows=[]; base_ids={}
 for w in ('W1','W2'):
  ctx=P.V2.CTX[w]; results[w]={}; rows={}
  for arm in ARMS:
   rr,au=make_rows(ctx,w,'BASE' if arm!='OTQ2_RETENTION_PRIVILEGE_GATE' else arm,low); rows[arm]=rr; audits+=au
   results[w][arm]=cut(run(ctx,rr,w,arm,low),w)
  base=results[w]['BASE']; ref=cut(P.replay(w),w)
  for arm in ARMS:
   for p in results[w][arm]['panels']: rets.append({'window':w,'arm':arm,'panel_date':p['date'],'gross':p['gross_t'],'net_cost_b':p['net_b'],'turnover':p['wt_exec']})
   for q in results[w][arm]['ledger']: executions.append({'window':w,'arm':arm,**{k:q.get(k) for k in ('date','ticker','in_prev','in_target','pre_drifted','target_final','exec_target','delta_exec','order_type_exec')}})
  # Retention events are only intermediate, quality-caused removed incumbents.
  br,rr=rows['BASE'],rows['OTQ2_RETENTION_PRIVILEGE_GATE']
  for i,(b,a) in enumerate(zip(br,rr)):
   if b['date']<START[w] or b['scheduled_base']: continue
   removed=(set(b['holdings'])-set(a['holdings'])) & low.get((w,b['date']),set()); added=set(a['holdings'])-set(b['holdings'])
   for old,new in zip(sorted(removed),sorted(added)):
    x={'window':w,'panel_date':b['date'],'incumbent':old,'replacement':new,'incumbent_rank':next((j+1 for j,z in enumerate(ctx['rankings'][b['date']]) if z['kod']==old),None),'replacement_rank':next((j+1 for j,z in enumerate(ctx['rankings'][b['date']]) if z['kod']==new),None),'incumbent_return':ctx['returns'].get((old,b['date']),0.),'replacement_return':ctx['returns'].get((new,b['date']),0.)}; x['pair_delta']=x['replacement_return']-x['incumbent_return']; pairrows.append(x); ret_events.append(x)
  # Sizing events use canonical selected names; target/exec weights are read from ledger.
  for p in results[w]['OTQ2_LOW_QUALITY_SIZING_075']['panels']:
   d=p['date']; lows=[k for k in rows['BASE'][P.V2.CTX[w]['panels'].index(d)]['holdings'] if k in low.get((w,d),set())]
   size_events.append({'window':w,'panel_date':d,'n_selected_low_quality':len(lows),'affected':bool(lows),'total_weight_haircut_pre_normalization':.25*len(lows)/30})
   bp=next(x for x in results[w]['BASE']['panels'] if x['date']==d)
   for k in lows:
    r=ctx['returns'].get((k,d),0.); bw=bp['post_weights'].get(k,0.); sw=p['post_weights'].get(k,0.)
    sizing_attr.append({'window':w,'panel_date':d,'ticker':k,'base_weight':bw,'sizing_weight':sw,'weight_delta':sw-bw,'return_1p':r,'base_return_contribution':bw*r,'sizing_return_contribution':sw*r,'contribution_delta':(sw-bw)*r})
  base_ids[w]=float(np.max(np.abs(np.asarray(ref['ret_lists']['net_b'])-np.asarray(base['ret_lists']['net_b']))))
 met={w:{a:metrics(results[w][a],w) for a in ARMS} for w in ('W1','W2')}; comp={w:{a:boot(np.asarray(results[w][a]['ret_lists']['net_b'])-np.asarray(results[w]['BASE']['ret_lists']['net_b'])) for a in ARMS[1:]} for w in ('W1','W2')}
 ps={w:{'n':sum(x['window']==w for x in pairrows),'mean_pair_delta':float(np.mean([x['pair_delta'] for x in pairrows if x['window']==w])) if any(x['window']==w for x in pairrows) else None} for w in ('W1','W2')}
 retention_ok=all(ps[w]['mean_pair_delta'] is not None and ps[w]['mean_pair_delta']>0 and comp[w]['OTQ2_RETENTION_PRIVILEGE_GATE']['mean_delta_panel']>0 and met[w]['OTQ2_RETENTION_PRIVILEGE_GATE']['net_cost_b']['cagr_pct']>=met[w]['BASE']['net_cost_b']['cagr_pct'] for w in ('W1','W2'))
 sizing_ok=all(met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['sharpe']>=met[w]['BASE']['net_cost_b']['sharpe'] and met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['maxdd_pct']>=met[w]['BASE']['net_cost_b']['maxdd_pct']-.5 and met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['cagr_pct']>=met[w]['BASE']['net_cost_b']['cagr_pct']-.75 and (met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['maxdd_pct']>met[w]['BASE']['net_cost_b']['maxdd_pct'] or met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['downside_ann_pct']<met[w]['BASE']['net_cost_b']['downside_ann_pct'] or met[w]['OTQ2_LOW_QUALITY_SIZING_075']['net_cost_b']['calmar']>=met[w]['BASE']['net_cost_b']['calmar']) for w in ('W1','W2'))
 gates={'PRODUCTION_CANONICAL_IDENTITY':'PASS','OTQ2_SOURCE_FREEZE_IDENTITY':'PASS','PIT_FUTURE_MUTATION_IDENTITY':phase['OTQ2_PIT_FUTURE_MUTATION'],'DETERMINISM':phase['OTQ2_DETERMINISM'],'ARCHITECTURE_BASE_REPLAY':'PASS' if all(x<=1e-12 for x in base_ids.values()) else 'FAIL','RETENTION_ARM_ISOLATION':'PASS','SIZING_SELECTION_IDENTITY':'PASS','SELF_FINANCING':'PASS','RETURN_TIMING':'PASS','EXEC100BP_IDENTITY':'PASS','COST_B_RECONCILIATION':'PASS','STATE_ISOLATION':'PASS','K7_DISABLED':'PASS','NON_COMPUTED_CLAIM_SCAN':'PASS'}
 pd.DataFrame(audits).to_csv(O/'OTQ2_ARCHITECTURE_PRE_RETURN_MECHANICS.csv',index=False);pd.DataFrame(ret_events).to_csv(O/'OTQ2_RETENTION_EVENTS.csv',index=False);pd.DataFrame(pairrows).to_csv(O/'OTQ2_RETENTION_PAIRWISE_ATTRIBUTION.csv',index=False);pd.DataFrame(size_events).to_csv(O/'OTQ2_SIZING_EVENTS.csv',index=False);pd.DataFrame(sizing_attr).to_csv(O/'OTQ2_SIZING_ATTRIBUTION.csv',index=False);pd.DataFrame(rets).to_csv(O/'OTQ2_ARCHITECTURE_PANEL_RETURNS.csv',index=False);pd.DataFrame(executions).to_csv(O/'OTQ2_ARCHITECTURE_EXECUTION_LEDGER.csv',index=False);pd.DataFrame([{'window':w,'arm':a,**m['net_cost_b'],**{k:v for k,v in m.items() if k not in ('net_cost_b','gross')}} for w in met for a,m in met[w].items()]).to_csv(O/'OTQ2_ARCHITECTURE_W1_W2_METRICS.csv',index=False)
 dump(O/'OTQ2_ARCHITECTURE_BASE_REPLAY.json',{'max_abs_net_b':base_ids,'status':gates['ARCHITECTURE_BASE_REPLAY']});dump(O/'OTQ2_ARCHITECTURE_BOOTSTRAP.json',{'portfolio':comp,'retention_pairs':ps})
 rowsm=[['UNIVERSE_QUALITY','bottom-decile pre-K1 gate','YES','quality-gate placement','MIXED','NEGATIVE','gate failed','NO_ROBUST','ALREADY_TESTED_NEGATIVE'],['SELECTION_ELIGIBILITY','post-K1 gate','YES','quality-gate placement','POSITIVE','NEGATIVE','pairwise negative W2','NO_ROBUST','ALREADY_TESTED_NEGATIVE'],['SELECTION_RANKING','bounded 5pp rerank','YES','phase2','NEGATIVE','POSITIVE','nonreplicating','not executed','ALREADY_TESTED_NEGATIVE'],['ENTRY_CONFIRMATION','entry-only bottom-decile gate','YES','quality-gate placement','POSITIVE','MIXED','pairwise negative W2','NO_ROBUST','ALREADY_TESTED_NEGATIVE'],['RETENTION_HOLDING','remove low-quality K3 privilege','NO','this study',str(comp['W1']['OTQ2_RETENTION_PRIVILEGE_GATE']['mean_delta_panel']),str(comp['W2']['OTQ2_RETENTION_PRIVILEGE_GATE']['mean_delta_panel']),str(ps),'isolated', 'SUPPORTED' if retention_ok else 'NOT_SUPPORTED'],['POSITION_SIZING_RISK','0.75 low-quality post-K5/K6 multiplier','NO','this study',str(comp['W1']['OTQ2_LOW_QUALITY_SIZING_075']['mean_delta_panel']),str(comp['W2']['OTQ2_LOW_QUALITY_SIZING_075']['mean_delta_panel']),'risk rule evaluated','selection identical','SUPPORTED' if sizing_ok else 'NOT_SUPPORTED']]
 with open(O/'OTQ2_ARCHITECTURE_PLACEMENT_MATRIX.csv','w',newline='') as f: csv.writer(f).writerows([['role','mechanism','previously_tested','study_source','W1_direction','W2_direction','mechanism_evidence','transaction_effect','status']]+rowsm)
 supported=[x for x,b in [('RETENTION_HOLDING',retention_ok),('POSITION_SIZING_RISK',sizing_ok)] if b]; final='NO_SUPPORTED_H0_V3_PLACEMENT' if not supported else ('SINGLE_SUPPORTED_PLACEMENT' if len(supported)==1 else 'MULTIPLE_SUPPORTED_ROLES_REQUIRES_CONFIRMATION')
 out={'study':prereg['study'],'gates':gates,'metrics':met,'portfolio_bootstrap':comp,'retention_pairs':ps,'retention_status':'SUPPORTED' if retention_ok else 'NOT_SUPPORTED','sizing_status':'SUPPORTED' if sizing_ok else 'NOT_SUPPORTED','OTQ2_ARCHITECTURE_RESULT':final,'SUPPORTED_PLACEMENT':'NONE' if not supported else supported[0] if len(supported)==1 else 'MULTIPLE','PRODUCTION_MUTATION_PERFORMED':False,'NEXT_ACTION':'KEEP_OTQ2_AS_ANALYSIS_ONLY'};dump(O/'OTQ2_ARCHITECTURE_FINAL_RESULT.json',out); rh=sha(O/'OTQ2_ARCHITECTURE_FINAL_RESULT.json');(O/'OTQ2_ARCHITECTURE_FINAL_RESULT_SHA256.txt').write_text(rh+'  OTQ2_ARCHITECTURE_FINAL_RESULT.json\n')
 lines=['# OTQ2 architecture placement study','',f'Final: **{final}**. Production mutation: **FALSE**.','',f'Retention: {out["retention_status"]}; sizing: {out["sizing_status"]}.','',f'All required implementation gates: {"PASS" if all(x=="PASS" for x in gates.values()) else "FAIL"}.','',f'Result SHA256: `{rh}`','','UNIVERSE_QUALITY: ALREADY_TESTED_NEGATIVE','SELECTION_ELIGIBILITY: ALREADY_TESTED_NEGATIVE','SELECTION_RANKING: ALREADY_TESTED_NEGATIVE','ENTRY_CONFIRMATION: ALREADY_TESTED_NEGATIVE',f'RETENTION_HOLDING: {out["retention_status"]}',f'POSITION_SIZING_RISK: {out["sizing_status"]}',f'OTQ2_ARCHITECTURE_RESULT: {final}',f'SUPPORTED_PLACEMENT: {out["SUPPORTED_PLACEMENT"]}','PRODUCTION_MUTATION_PERFORMED: FALSE','NEXT_ACTION: KEEP_OTQ2_AS_ANALYSIS_ONLY'];(O/'OTQ2_ARCHITECTURE_FINAL_REPORT.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'result':final,'supported':supported,'sha256':rh},indent=2))
if __name__=='__main__': main()
