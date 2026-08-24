"""No-backtest semantic resolution of the 803-row master ledger."""
from __future__ import annotations
import csv,hashlib,json,re
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
V=Path('/home/hannesb/momentum_v2');O=V/'research_k/canonical_mechanism_resolution_audit'
L=json.loads((V/'research_inventory/master_test_ledger.json').read_text())['rows']; G={x['TEST_ID']:x for x in json.loads((V/'research_k/global_reaudit/research_test_inventory.json').read_text())['entries']}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text(r,g):return ' '.join(str(x) for x in [r.get('test_name',''),r.get('test_family',''),r.get('hypothesis',''),g.get('HYPOTHESIS',''),r.get('source_script','')]).lower().replace('_',' ')
def clean(x):return ' '.join((x or '').lower().replace('_',' ').replace('-',' ').split())
RULES=[
 ('EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER',['topup','existing winner','early topup'],'external capital is deployed into an owned winner','SUPPORTED_CLEAN','HIGH','YES'),
 ('MONTHLY_CASH_NEW_NAME',['cash','new name','cash deployment'],'external-capital allocation into a new candidate','CLOSED_CLEAN_NULL','HIGH','NO'),
 ('OMXS30_MINIMUM_PORTFOLIO_QUOTA',['index quota','omxs30'],'minimum historical index-member portfolio quota','CLOSED_CLEAN_NEGATIVE','HIGH','NO'),
 ('REBALANCE_CADENCE_4W',['rebalance','rebalansfrekvens','cadence'],'full portfolio decision cadence','CLOSED_CLEAN_NEGATIVE','HIGH','NO'),
 ('SELECTIVE_INTERMEDIATE_SWAP',['selective swap','opportunity cost swap'],'intermediate weak-to-strong replacement','CLOSED_CLEAN_NEGATIVE','HIGH','NO'),
 ('DRAWDOWN_EXIT',['dd20','drawdown exit','drawdown'],'sell after holding drawdown','REPLACED_BY_CLEANER_SAME_ESTIMAND','MEDIUM','NO'),
 ('INFORMATION_EXIT',['information exit','meta exit'],'sell from new holding information','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('NO_PROGRESS_TIME_EXIT',['no progress','time stop','holding period'],'sell after insufficient progress / elapsed time','REPLACED_BY_CLEANER_SAME_ESTIMAND','MEDIUM','NO'),
 ('REENTRY_BLOCK',['reentry','re entry'],'block re-entry after exit','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('RANK_EXIT',['rank exit','ranknivå','rankförändring'],'sell from rank deterioration','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('SMA_EXIT',['sma exit','sma200 exit'],'sell from moving-average state','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('STREAK_HOLD_BREAK',['streak','hold break'],'holding-state streak/break policy','PENDING_EXISTING_AUDIT','LOW','UNCLEAR'),
 ('MOMENTUM_HORIZON_BLEND',['12m','18m','lookback','momentumkurvan'],'momentum horizon or horizon blend','FORWARD_ONLY','MEDIUM','UNCLEAR'),
 ('EARLY_MOMENTUM_ACCELERATION',['early momentum','acceleration'],'early acceleration ranking modification','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('DELAYED_MOMENTUM_DETECTION',['delayed','detection'],'delayed momentum-entry/detection mechanism','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('WINNER_PATH_TRAJECTORY',['winner path','trajectory','path','banans form'],'path/trajectory state mechanism','PENDING_EXISTING_AUDIT','LOW','UNCLEAR'),
 ('BREADTH_DISPERSION',['breadth','dispersion'],'cross-sectional breadth or score dispersion','LEGACY_POSITIVE_NO_CLEAN_REPLICATION','MEDIUM','YES'),
 ('DIVIDEND_SIGNAL',['dividend','utdelning'],'dividend-related alpha signal','BLOCKED_DATA','MEDIUM','NO'),
 ('ATTENTION_SIGNAL',['attention','report','pead','insider'],'attention/event-information signal','BLOCKED_DATA','MEDIUM','NO'),
 ('EXTRATREES_RERANK',['extratrees','extra trees'],'ExtraTrees selection/reranking architecture','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('XGBOOST_RERANK',['xgboost'],'XGBoost selection/reranking architecture','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('LIGHTGBM_RERANK',['lightgbm','lgbm'],'LightGBM selection/reranking architecture','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('ML_ROUTING_ENSEMBLE',['routing','ensemble','cross model'],'model routing/ensemble intervention','PENDING_EXISTING_AUDIT','LOW','UNCLEAR'),
 ('VOLATILITY_SIZING',['inverse vol','riskvikt','volatility weighting','vol targeting'],'position/portfolio volatility sizing','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('WEIGHT_CAP_CONCENTRATION',['concentration','weight cap','portfolio size','effective bets'],'position cap or concentration policy','PENDING_EXISTING_AUDIT','MEDIUM','UNCLEAR'),
 ('MARKET_RISK_OFF',['risk off','market regime','portfolio drawdown'],'market/portfolio-level risk gate','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('CORRELATION_FILTER',['correlation'],'correlation-constrained selection','REPLACED_BY_CLEANER_SAME_ESTIMAND','HIGH','NO'),
 ('SIZE_ROUTING',['size conditional','size routing','storbolag'],'size-conditioned policy','PENDING_EXISTING_AUDIT','LOW','UNCLEAR'),
 ('SECTOR_ROUTING',['sector','icb'],'sector-conditioned policy','PENDING_EXISTING_AUDIT','LOW','UNCLEAR')]
def match(t):
 for a,ks,e,s,c,d in RULES:
  if any(k in t for k in ks):return a,e,s,c,d
 return 'UNRESOLVED_'+re.sub('[^A-Z0-9]+','_',t[:32].upper()).strip('_'),'unresolved estimand from available metadata','AMBIGUOUS_ESTIMAND_RESOLUTION','LOW','UNCLEAR'
def main():
 O.mkdir(parents=True,exist_ok=True); rows=[]
 for r in L:
  g=G.get(r['test_id'],{});t=text(r,g); cid,eco,status,conf,debt=match(t); n=clean(r.get('test_name')); sweep='YES' if (n.startswith('tune ') or 'parameter sweep' in t or 'grid search' in t) else 'NO'
  if sweep=='YES' and status not in ('SUPPORTED_CLEAN','BLOCKED_DATA'):status='CLOSED_PARAMETER_RESULT_ONLY';debt='UNCLEAR'
  repl='';same='NO';reason='No verified same-estimand clean replacement linked in this resolution pass.'
  if status=='REPLACED_BY_CLEANER_SAME_ESTIMAND':same='PARTIAL';repl='later clean family closure (artifact verification queued)';reason='Mechanism-level link identified; exact intervention/replacement artifact must be manually verified.'
  if cid=='REBALANCE_CADENCE_4W':same='YES';repl='research_k/rebalance_cadence_4w_vs_8w_audit/RESULT.json'
  if cid=='SELECTIVE_INTERMEDIATE_SWAP':same='YES';repl='research_k/monthly_cash_and_selective_4w_audit/RESULT.json'
  if cid=='EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER':same='YES';repl='research_k/monthly_cash_early_topup_vs_next_rebalance_audit/RESULT.json'
  if cid=='OMXS30_MINIMUM_PORTFOLIO_QUOTA':same='YES';repl='research_k/index_quota_portfolio_audit_v2/RESULT.json'
  rows.append({'raw_test_id':r['test_id'],'raw_test_name':r.get('test_name'),'source_file':r.get('source_script'),'source_ledger':'master_test_ledger','original_family':r.get('test_family'),'original_subfamily':g.get('HYPOTHESIS'),'original_model_generation':' | '.join(r.get('baseline_refs') or []),'original_engine':r.get('track'),'original_window_structure':r.get('independent_windows'),'original_period':' | '.join(r.get('years_referenced') or []),'independent_windows':r.get('independent_windows'),'PIT_status':g.get('PIT_STATUS'),'universe_status':g.get('UNIVERSE_STATUS'),'survivorship_status':'UNKNOWN','data_quality_status':'FLAGGED' if r.get('hardcoded_result_suspect') or r.get('flags',{}).get('uses_terminal_ex_post') else 'UNRESOLVED','revalidation_priority':g.get('revalidation_priority'),'gating_status':g.get('gating_status'),'tuning_or_sweep':sweep,'prereg_status':bool(r.get('preregistration_files')),'original_metric':' | '.join(r.get('metrics') or []),'original_effect':'NOT_MACHINE_READABLE','original_verdict':g.get('OLD_VERDICT',r.get('verdict_bucket')),'canonical_mechanism_id':cid,'canonical_mechanism_name':cid.replace('_',' '),'estimand':eco,'economic_mechanism':eco,'implementation_variant':r.get('test_name'),'parameter_variant':'SWEEP_OR_TUNE' if sweep=='YES' else 'NOT_IDENTIFIED','duplicate_group_id':cid,'later_clean_replacement':bool(repl),'replacement_artifact':repl,'replacement_same_estimand_yes_no':same,'replacement_reason':reason,'current_evidence_status':status,'resolution_confidence':conf,'manual_review_required':conf=='LOW' or same=='PARTIAL','manual_review_note':'Resolve exact estimand/replacement before any recovery decision.' if conf=='LOW' or same=='PARTIAL' else '','possible_research_debt':debt,'PIT_size_tested':False,'PIT_size3_tested':False,'PIT_smallmid_vs_large_tested':False,'PIT_sector_tested':False,'size_interaction_tested':False,'sector_interaction_tested':False,'size_standardization_tested':False,'sector_standardization_tested':False})
 fields=list(rows[0]);
 with (O/'canonical_mechanism_map.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 groups=defaultdict(list)
 for r in rows:groups[r['canonical_mechanism_id']].append(r)
 mechs=[]
 for k,v in groups.items():mechs.append({'canonical_mechanism_id':k,'n_raw_tests':len(v),'raw_test_ids':'|'.join(x['raw_test_id'] for x in v),'current_evidence_status':Counter(x['current_evidence_status'] for x in v).most_common(1)[0][0],'possible_research_debt':Counter(x['possible_research_debt'] for x in v).most_common(1)[0][0],'resolution_confidence':Counter(x['resolution_confidence'] for x in v).most_common(1)[0][0]})
 with (O/'canonical_mechanisms.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(mechs[0]));w.writeheader();w.writerows(mechs)
 review=[r for r in rows if r['manual_review_required']]
 with (O/'canonical_manual_review_queue.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(review)
 rep=[r for r in rows if r['later_clean_replacement']]
 with (O/'replacement_map.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rep)
 res={'study':'CANONICAL_MECHANISM_RESOLUTION_AUDIT','raw_tests':len(rows),'canonical_mechanisms':len(mechs),'status_counts':Counter(x['current_evidence_status'] for x in rows),'confidence_counts':Counter(x['resolution_confidence'] for x in rows),'possible_research_debt':Counter(x['possible_research_debt'] for x in rows),'manual_review_queue':len(review),'prereg_sha256':sha(O/'PREREGISTRATION.json'),'canonical_map_sha256':sha(O/'canonical_mechanism_map.csv'),'replacement_map_sha256':sha(O/'replacement_map.csv'),'run_utc':datetime.now(timezone.utc).isoformat(),'candidate_freeze_created':False}
 (O/'RESULT.json').write_text(json.dumps(res,ensure_ascii=False,indent=2));print(json.dumps(res,ensure_ascii=False))
if __name__=='__main__':main()
