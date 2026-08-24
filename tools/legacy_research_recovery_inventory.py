"""Mechanical, non-empirical recovery inventory from the authoritative master ledger."""
from __future__ import annotations
import csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
V2=Path('/home/hannesb/momentum_v2');OUT=V2/'research_k/legacy_research_recovery_inventory';LED=V2/'research_inventory/master_test_ledger.json'
REAUDIT=V2/'research_k/global_reaudit/research_test_inventory.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clean(x):return ' '.join((x or '').lower().replace('_',' ').replace('-',' ').split())
RULES=[
 (('rebalance','4w'),'CLOSED_REPLACED_BY_CLEANER_TEST','Clean later cadence audit'),
 (('selective','swap'),'CLOSED_REPLACED_BY_CLEANER_TEST','Clean selective-swap audit'),
 (('dd20','drawdown exit'),'CLOSED_REPLACED_BY_CLEANER_TEST','Corrected drawdown closure'),
 (('reentry','re entry'),'CLOSED_REPLACED_BY_CLEANER_TEST','Later clean reentry closure'),
 (('risk off','market regime'),'CLOSED_REPLACED_BY_CLEANER_TEST','Later clean market-regime closure'),
 (('early momentum','acceleration'),'CLOSED_REPLACED_BY_CLEANER_TEST','Later early-momentum closure'),
 (('information exit','no progress','time stop'),'CLOSED_REPLACED_BY_CLEANER_TEST','Later exit-family closure'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);d=json.loads(LED.read_text());raw=d['rows']; rea={r['TEST_ID']:r for r in json.loads(REAUDIT.read_text())['entries']}; inv=[]; groups=defaultdict(list)
 for r in raw:
  g=rea.get(r['test_id'],{})
  text=' '.join(map(str,[r.get('test_family',''),r.get('test_name',''),r.get('hypothesis',''),r.get('legacy_registry_family','')]))
  # The re-audit hypothesis is the most granular existing, pre-result family label.
  canon=(g.get('HYPOTHESIS') or r.get('legacy_registry_family') or r.get('test_family') or 'UNCLASSIFIED').upper().replace(' ','_')
  status='PENDING_EXISTING_AUDIT'; reason='No machine-readable final closure or clean-replacement link; requires evidence review, not automatic closure.'
  for terms,s,why in RULES:
   if any(t in clean(text) for t in terms):status,reason=s,why;break
  if r.get('hardcoded_result_suspect') or r.get('flags',{}).get('uses_terminal_ex_post'):status,reason='CLOSED_INVALID_DATA','Known hardcoded/ex-post data-risk flag.'
  if 'tune ' in clean(r.get('test_name')) or 'sweep' in clean(r.get('test_name')):status,reason='CLOSED_PARAMETER_SWEEP_ONLY','Tuning/sweep member, not an independently frozen mechanism.'
  if r.get('flags',{}).get('uses_static_sector'): reason+=' Static sector use prevents PIT sector comparability.'
  row={'canonical_mechanism_id':canon,'test_id':r['test_id'],'test_name':r.get('test_name'),'test_family':r.get('test_family'),'track':r.get('track'),'modelgeneration':r.get('baseline_refs'),'independent_windows':r.get('independent_windows'),'prereg_status':bool(r.get('preregistration_files')),'parameter_sweep':r.get('entry_class')=='A_COMPUTED_TEST' and r.get('has_resampling')==False,'pit_correctness':g.get('PIT_STATUS','UNKNOWN_FROM_LEDGER'),'universe_correctness':g.get('UNIVERSE_STATUS','UNKNOWN_FROM_LEDGER'),'revalidation_priority':g.get('revalidation_priority'),'reaudit_gating':g.get('gating_status'),'survivorship_status':'UNKNOWN_FROM_LEDGER','data_quality_status':'FLAGGED' if status=='CLOSED_INVALID_DATA' else 'NOT_YET_MANUALLY_REVIEWED','original_verdict':g.get('OLD_VERDICT',r.get('verdict_bucket')),'later_clean_replacement':status=='CLOSED_REPLACED_BY_CLEANER_TEST','pit_size_audited':False,'pit_sector_audited':False,'current_final_status':status,'status_reason':reason,'source_script':r.get('source_script'),'result_artifacts':' | '.join(r.get('result_artifact') or [])}
  inv.append(row);groups[canon].append(row)
 def write(name,rows):
  with (OUT/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 write('legacy_research_recovery_inventory.csv',inv)
 cmap=[]
 for c,rs in groups.items():
  sts=Counter(r['current_final_status'] for r in rs); primary='CLOSED_REPLACED_BY_CLEANER_TEST' if sts['CLOSED_REPLACED_BY_CLEANER_TEST'] else ('CLOSED_INVALID_DATA' if sts['CLOSED_INVALID_DATA'] else 'PENDING_EXISTING_AUDIT')
  cmap.append({'canonical_mechanism_id':c,'original_test_ids':'|'.join(r['test_id'] for r in rs),'n_raw_tests':len(rs),'primary_status':primary,'status_counts':json.dumps(sts,ensure_ascii=False)})
 write('canonical_mechanism_map.csv',cmap)
 for filename,status in [('closed_mechanisms.csv','CLOSED_REPLACED_BY_CLEANER_TEST'),('blocked_data_mechanisms.csv','BLOCKED_DATA'),('forward_only_mechanisms.csv','FORWARD_ONLY')]:write(filename,[r for r in cmap if r['primary_status']==status] or [dict.fromkeys(cmap[0],'')])
 res={'study':'LEGACY_RESEARCH_RECOVERY_INVENTORY','run_utc':datetime.now(timezone.utc).isoformat(),'raw_tests':len(inv),'canonical_mechanisms':len(cmap),'status_counts':Counter(r['current_final_status'] for r in inv),'prereg_sha256':sha(OUT/'PREREGISTRATION.json'),'canonical_map_sha256':sha(OUT/'canonical_mechanism_map.csv'),'note':'This mechanical pass deliberately leaves unresolved mechanisms PENDING_EXISTING_AUDIT; it creates no recovery candidates and no empirical reruns.'}
 (OUT/'RESULT.json').write_text(json.dumps(res,ensure_ascii=False,indent=2));print(json.dumps(res,ensure_ascii=False))
if __name__=='__main__':main()
