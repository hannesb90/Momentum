"""Source-level compatibility audit; deliberately performs no empirical rerun."""
import csv, hashlib, json
from pathlib import Path

V=Path('/home/hannesb/momentum_v2'); O=V/'research_k/h0_v3_architecture_compatibility_audit'; O.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
YES,NO,NA='YES','NO','NOT_APPLICABLE'
def row(i,script,artifact,mech,level,status,verdict,ev,*,direct=NO,gate=NO,signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,mismatch='',mat='NON_MATERIAL',aff='NO',usable='VALID',rerun='NO',priority='NONE',confidence='HIGH'):
 return dict(test_id=i,script=script,artifact=artifact,canonical_mechanism=mech,estimand_level=level,uses_frozen_h0_directly=direct,has_base_reproduction_gate=gate,signal_match=signal,cadence_match=cad,intermediate_retain_refill_match=retain,sma_order_match=sma,post_sma_refill_match=post,sizing_match=size,clip_normalization_match=clip,turnover_match=turn,cost_match=cost,overall_architecture_status=status,mismatch_description=mismatch,mismatch_materiality=mat,old_verdict=verdict,architecture_affects_estimand=aff,verdict_can_still_be_used=usable,needs_rerun=rerun,rerun_priority=priority,confidence=confidence,evidence_source=ev)
def main():
 O.mkdir(exist_ok=True)
 frozen=sha(V/'tools/h0_v3_kor.py')
 ref=f'''# Frozen H0 V3 architecture reference\n\nFrozen source: `tools/h0_v3_kor.py` SHA-256 `{frozen}`.\n\n- Signal: 52/78 week adjusted-price momentum, component percentile ranks, 50/50 score; missing combined scores receive the cross-sectional median; descending `(score, kod)`.\n- Cadence: 28-day panels; ordinary panels fresh-select Top-30; intermediate panels retain prior `selected_pre_SMA` if PIT eligible and refill vacancies from current rank.\n- SMA: applied after `selected_pre_SMA`; no refill after removal.\n- Sizing: inverse volatility exponent 1.5 × confirmation 1/0.75; clip once to 1–6%; then normalize.\n- Turnover: first panel 0; otherwise `1 - overlap(current_pre_SMA, previous_pre_SMA)/len(current_pre_SMA)`. Cost is `0.002 × turnover` after gross return.\n\nThis audit classifies source and existing gates only. It does not rerun any policy.\n'''
 (O/'ARCHITECTURE_REFERENCE.md').write_text(ref)
 common='tools/rebalance_cadence_4w_vs_8w_audit.py:95-132; base gate:140-145'
 r=[]
 # Reproducing portfolio engine / direct transitive consumers.
 r += [
 row('REBALANCE_CADENCE_4W_VS_8W','tools/rebalance_cadence_4w_vs_8w_audit.py','research_k/rebalance_cadence_4w_vs_8w_audit/RESULT.json','REBALANCE_CADENCE_4W_VS_8W','PORTFOLIO','REPRODUCTION_VERIFIED','CLOSED_CLEAN_NEGATIVE',common,gate=YES,signal=YES,cad=YES,retain=YES,sma=YES,post=YES,size=YES,clip=YES,turn=YES,cost=YES),
 row('INDEX_QUOTA_PORTFOLIO_V2','tools/index_quota_portfolio_audit_v2.py','research_k/index_quota_portfolio_audit_v2/RESULT.json','OMXS30_MINIMUM_PORTFOLIO_QUOTA','PORTFOLIO','REPRODUCTION_VERIFIED','CLOSED_NONREPLICATION','tools/index_quota_portfolio_audit_v2.py:9,33-50; transitive '+common,gate=YES,signal=YES,cad=YES,retain=YES,sma=YES,post=YES,size=YES,clip=YES,turn=YES,cost=YES),
 row('MONTHLY_CASH_SELECTIVE_4W','tools/monthly_cash_and_selective_4w_audit.py','research_k/monthly_cash_and_selective_4w_audit/RESULT.json','MONTHLY_CASH_NEW_NAME__SELECTIVE_4W_SWAP','PORTFOLIO','NEEDS_ARCHITECTURE_REVALIDATION','MIXED','tools/monthly_cash_and_selective_4w_audit.py:8,30-67; core uses '+common,direct=NO,gate=YES,signal=YES,cad=YES,retain=YES,sma=YES,post=YES,size=YES,clip=NO,turn=YES,cost=YES,mismatch='External-cash sleeve enforces a hard 6% final-position cap (`cap=max(0,.06*total-cur)`), unlike frozen clip-then-normalize semantics.',mat='POTENTIALLY_MATERIAL',aff='YES',usable='UNCLEAR',rerun='YES',priority='P1',confidence='HIGH'),
 row('MONTHLY_CASH_EARLY_TOPUP','tools/monthly_cash_early_topup_vs_next_rebalance_audit.py','research_k/monthly_cash_early_topup_vs_next_rebalance_audit/RESULT.json','EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER','PORTFOLIO','NEEDS_ARCHITECTURE_REVALIDATION','SUPPORTED_POST_LOCK','tools/monthly_cash_early_topup_vs_next_rebalance_audit.py:10-31; inherits the hard-cap sleeve from monthly_cash_and_selective_4w_audit.py:54-59.',direct=NO,gate=YES,signal=YES,cad=YES,retain=YES,sma=YES,post=YES,size=YES,clip=NO,turn=YES,cost=YES,mismatch='The matched cash sleeve inherits a hard 6% final-position cap, not frozen H0 clip-then-normalize cap semantics.',mat='POTENTIALLY_MATERIAL',aff='YES',usable='UNCLEAR',rerun='YES',priority='P0',confidence='HIGH'),
 row('H0_V3_PORTFOLIO_FACTORIAL','tools/h0_v3_portfolio_factorial_kor.py','research_k/h0_v3_portfolio_factorial/results.json','PORTFOLIO_LAYER_FACTORS','PORTFOLIO','SAFE_BY_CONSTRUCTION','DESCRIPTIVE','tools/h0_v3_portfolio_factorial_kor.py:36-107,120-142; source SHA guard',direct=YES,gate=YES,signal=YES,cad=YES,retain=YES,sma=YES,post=YES,size=YES,clip=YES,turn=YES,cost=YES),
 ]
 # Explicitly legacy simplified portfolio loops: no frozen base reproduction.
 legacy=[
 ('H0_REENTRY_SCORE_IMPROVEMENT','tools/h0_reentry_score_improvement.py','research_k/h0_reentry_score_improvement_results.json','REENTRY_SCORE_IMPROVEMENT','CLEAN_W1W2_MIXED','28-61'),
 ('H0_TEMPORARY_EXIT_GUARD','tools/h0_temporary_exit_guard.py','research_k/h0_temporary_exit_guard_results.json','TEMPORARY_EXIT_GUARD','CLOSED_CLEAN_NEGATIVE','39-85'),
 ('H0_EXIT_MODEL_TIME_SPLIT','tools/h0_exit_model_time_split.py','research_k/h0_exit_model_time_split_results.json','MODELLED_EXIT_GUARD','CLOSED_CLEAN_NEGATIVE','103-127'),
 ('H0_CORE_META_EXIT','tools/h0_core_meta_exit.py','research_k/h0_core_meta_exit_results.json','MODELLED_EXIT_GUARD','CLOSED_CLEAN_NEGATIVE','80-112'),
 ('H0_LGBM_CONSENSUS_EXIT','tools/h0_lgbm_consensus_exit.py','research_k/h0_lgbm_consensus_exit_results.json','MODELLED_EXIT_GUARD','CLOSED_CLEAN_NEGATIVE','69-101'),
 ('PORTFOLIO_LAYER_FAIRNESS','tools/portfolio_layer_fairness_kor.py','research_k/portfolio_layer_fairness/results.json','SIZING_RISK_ARCHITECTURE','MIXED','42-105'),
 ('GLOBAL_ML_FULL_PIT_FEATURE_RACE','tools/rep_model_race_h0v3_kor.py','research_k/global_ml_full_pit_race/results.json','MODEL_REPLACEMENT','CLOSED_NONREPLICATION','tools/rep_model_race_h0v3_kor.py:163-181'),
 ('CROSS_MODEL_ARCH_B','tools/cross_model_arch_b_kor.py','research_k/cross_model_arch_b/results.json','H0_POOL_ML_RERANK','CLOSED_NONREPLICATION','tools/cross_model_arch_b_kor.py:68,105-117; inherited R.simulate'),
 ('CANDIDATE_GENERATION_ARCHITECTURE','tools/candidate_generation_architecture_kor.py','research_k/candidate_generation_architecture/results.json','ML_CANDIDATE_GENERATION','CLOSED_NONREPLICATION','tools/candidate_generation_architecture_kor.py:104-129'),
 ('DYNAMIC_ROUTING_ARCHITECTURE','tools/dynamic_routing_architecture_kor.py','research_k/dynamic_routing_architecture/results.json','DYNAMIC_ROUTING','CLOSED_NONREPLICATION','tools/dynamic_routing_architecture_kor.py:145-176'),
 ('INFORMATION_EXIT_PORTFOLIO','tools/information_exit_kor.py','research_k/information_exit/results_W1_2014_2019.json','SMA_TRANSITION_PORTFOLIO_EXIT__TOPN_RANK_PORTFOLIO_EXIT','SEQUENTIAL_GATE_CLOSED','tools/information_exit_kor.py:30-80,100-125; inherited R.simulate'),
 ('EXIT_ARCHITECTURE_FACTORIAL_DD','tools/exit_architecture_factorial_kor.py','research_k/exit_architecture_factorial/results_W1_2014_2019.json','CORRECTED_DRAWDOWN_EXIT','CLEAN_MECHANISM_NOT_PREDICTIVE','tools/exit_architecture_factorial_kor.py:125-170; baseline gate compares R.simulate'),
 ]
 for i,s,a,m,v,ln in legacy:
  p='P0' if m in ('REENTRY_SCORE_IMPROVEMENT','TEMPORARY_EXIT_GUARD','MODELLED_EXIT_GUARD','SMA_TRANSITION_PORTFOLIO_EXIT__TOPN_RANK_PORTFOLIO_EXIT','CORRECTED_DRAWDOWN_EXIT') else 'P1'
  r.append(row(i,s,a,m,'PORTFOLIO','INVALID_BASE_ARCHITECTURE',v,ln,signal='PARTIAL',cad=NO,retain=NO,sma=NO,post=NO,size=NO,clip=NO,turn=NO,cost=NO,mismatch='Own simplified portfolio loop / R.simulate: every-other-panel full hold, equal weights, no frozen intermediate retain/refill, post-selection SMA sizing or pre-SMA set turnover.',mat='MATERIAL',aff='YES',usable='NOT_VALID_UNDER_FROZEN_H0',rerun='YES',priority=p,confidence='HIGH'))
 # A modern direct engine test with a repro gate but its custom exit sleeve deliberately changes state; base comparison itself is verified only inside simplified R.simulate.
 r += [
 row('INFORMATION_EXIT_FORWARD_DIAGNOSTIC','tools/information_exit_kor.py','research_k/information_exit/results_W1_2014_2019.json','SMA_TRANSITION_FORWARD_INFORMATION__TOPN_RANK_FORWARD_INFORMATION','DIAGNOSTIC','SAFE_BY_CONSTRUCTION','NO_COMPARABLE_W1W2_EVIDENCE','information_exit_kor.py event labels; diagnostic question distinct from policy.',signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,aff='NO',usable='VALID'),
 row('HOLDING_PATH_AUDIT','tools/holding_path_kor.py','research_k/holding_path_audit/SLUTDOM.json','NO_PROGRESS_TIME_EXIT','DIAGNOSTIC','SAFE_BY_CONSTRUCTION','CLEAN_FORWARD_ESTIMAND_NULL','tools/holding_path_kor.py:112-132; event/path data, not a portfolio simulator.',signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,aff='NO',usable='VALID'),
 row('DRAWDOWN_HETEROGENEITY_DIAGNOSTIC','tools/dd_heterogeneity_kor.py','research_k/dd_heterogeneity_closure/datalager.json','DRAWDOWN_RESILIENCE_SELECTION','DIAGNOSTIC','SAFE_BY_CONSTRUCTION','DIAGNOSTIC','tools/dd_heterogeneity_kor.py:122-145; holdings-event data, no alternate portfolio simulation.',signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,aff='NO',usable='VALID'),
 row('DELAYED_ENTRY_DIAGNOSTIC','tools/delayed_entry_kor.py','research_k/delayed_entry/datalager.json','DELAYED_ENTRY','DIAGNOSTIC','SAFE_BY_CONSTRUCTION','CLOSED_CLEAN_NEGATIVE','tools/delayed_entry_kor.py:86 onward; descriptive entry timing, no portfolio loop.',signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,aff='NO',usable='VALID'),
 row('WINNER_PATH_DIAGNOSTIC','tools/winner_path_kor.py','research_k/winner_path/datalager.json','WINNER_PATH','DIAGNOSTIC','SAFE_BY_CONSTRUCTION','CLOSED_NONREPLICATION','tools/winner_path_kor.py:106 onward; event data only.',signal=NA,cad=NA,retain=NA,sma=NA,post=NA,size=NA,clip=NA,turn=NA,cost=NA,aff='NO',usable='VALID'),
 ]
 fields=list(r[0]);
 with open(O/'ARCHITECTURE_COMPATIBILITY_MATRIX.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(r)
 with open(O/'TEST_INVENTORY.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=['test_id','script','artifact','canonical_mechanism','estimand_level','old_verdict']);w.writeheader();w.writerows([{k:x[k] for k in w.fieldnames} for x in r])
 c=[x for x in r if x['needs_rerun']=='YES']
 with open(O/'ARCHITECTURE_REVALIDATION_CANDIDATES.csv','w',newline='') as f:
  fs=['test_id','canonical_mechanism','old_verdict','mismatch','why_material','exact_frozen_component_violated','expected_information_gain','priority'];w=csv.DictWriter(f,fieldnames=fs);w.writeheader()
  for x in c:w.writerow({'test_id':x['test_id'],'canonical_mechanism':x['canonical_mechanism'],'old_verdict':x['old_verdict'],'mismatch':x['mismatch_description'],'why_material':'The policy intervention is measured against a different portfolio state, selection/SMA/sizing/cost path.','exact_frozen_component_violated':'cadence; intermediate retain/refill; SMA-after-selection; sizing/clip-normalization; selected_pre_SMA turnover','expected_information_gain':'Restores whether the old policy verdict holds against the actual frozen H0 V3 base.','priority':x['rerun_priority']})
 # Proposed impact only: do not modify canonical artifacts.
 impacts=[]
 for x in c:
  impacts.append({'canonical_mechanism':x['canonical_mechanism'],'at_risk_test_id':x['test_id'],'prior_canonical_status':x['old_verdict'],'proposed_compatibility_impact':'PENDING_ARCHITECTURE_REVALIDATION','reason':'MATERIAL frozen-base mismatch in a portfolio-policy test used as evidence.','canonical_artifact_modified':False})
 with open(O/'CANONICAL_STATUS_IMPACT.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(impacts[0]));w.writeheader();w.writerows(impacts)
 counts={s:sum(x['overall_architecture_status']==s for x in r) for s in ['SAFE_BY_CONSTRUCTION','REPRODUCTION_VERIFIED','NEEDS_ARCHITECTURE_REVALIDATION','INVALID_BASE_ARCHITECTURE']}
 dims={k:sum(x[k]=='NO' for x in r) for k in ['cadence_match','intermediate_retain_refill_match','sma_order_match','post_sma_refill_match','sizing_match','clip_normalization_match','turnover_match','cost_match']}
 res={'study':'H0_V3_ARCHITECTURE_COMPATIBILITY_AUDIT','frozen_h0_v3_source_sha256':frozen,'no_empirical_reruns':True,'tests_reviewed':len(r),'status_counts':counts,'mismatch_counts':dims,'canonical_verdicts_fully_usable':sum(x['verdict_can_still_be_used'] in ('VALID','LIKELY_VALID') for x in r),'canonical_verdicts_requiring_architecture_revalidation':len(c),'rerun_candidates_by_priority':{p:sum(x['rerun_priority']==p for x in c) for p in ['P0','P1','P2']},'matrix_sha256':sha(O/'ARCHITECTURE_COMPATIBILITY_MATRIX.csv'),'candidate_list_sha256':sha(O/'ARCHITECTURE_REVALIDATION_CANDIDATES.csv')}
 (O/'RESULT.json').write_text(json.dumps(res,indent=2)+'\n')
 (O/'SUMMARY.md').write_text(f'''# H0 V3 architecture compatibility audit

Reviewed {len(r)} records: {sum(x['estimand_level']=='PORTFOLIO' for x in r)} portfolio/policy tests and {sum(x['estimand_level']=='DIAGNOSTIC' for x in r)} pure diagnostics. No empirical reruns were run.

## Compatible portfolio baselines

- `REBALANCE_CADENCE_4W_VS_8W` — reproduction verified.
- `INDEX_QUOTA_PORTFOLIO_V2` — reproduction verified through the same base engine.
- `H0_V3_PORTFOLIO_FACTORIAL` — safe by construction with a frozen-source SHA guard.

## Not compatible with the frozen portfolio base

The legacy exit and ML harnesses use full selection every other panel, equal weights, and their own membership turnover. They omit frozen intermediate retain/refill, post-selection SMA and frozen pre-SMA turnover. Their portfolio verdicts are therefore not valid under frozen H0 V3 without revalidation.

The two cash-sleeve tests reproduce the core engine but impose a hard final 6% position cap. This differs from frozen clip-then-normalize semantics and is marked `NEEDS_ARCHITECTURE_REVALIDATION`, not invalid.

Material base mismatches are proposed as `PENDING_ARCHITECTURE_REVALIDATION` in the separate impact file only; canonical artifacts were not edited.

- Matrix SHA-256: `{res['matrix_sha256']}`
- Candidate-list SHA-256: `{res['candidate_list_sha256']}`
''')
if __name__=='__main__':main()
