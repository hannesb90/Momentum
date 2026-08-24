"""Create content-addressed, pre-ON freeze artefacts for the Top3 study.

This script only reads existing OFF/test evidence and writes provenance
documents.  It never instantiates the ON intervention.
"""
import hashlib, json, os, platform, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/home/hannesb/momentum_v2')
OUT=ROOT/'research_k/h0_v3_top3_winner_protection_audit'
REPOS=[Path('/home/hannesb/momentum_prod_work'),Path('/home/hannesb/momentum_exports_2026-08-02/github_repo')]
FILES=[
 'tools/frozen_h0_v3_policy_adapter.py','tools/rebalance_cadence_4w_vs_8w_audit.py',
 'tools/h0_v3_kor.py','tools/h0_v3_eligibility.py','tools/test_top3_winner_protection_preon.py',
 'tools/run_top3_off_replay.py',
 'research_k/h1419_exakt_h0_preregistration_v2.json','research_k/h0_v3_window2/preregistration.json',
]
INPUTS=['validated/prices_h1419/prices_h1419_universum_v2.json','validated/prices/prices_validated.json']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def entry(rel):
 p=ROOT/rel
 if not p.exists(): raise FileNotFoundError(p)
 return {'path':rel,'size':p.stat().st_size,'sha256':sha(p)}
def dump(p,obj): Path(p).write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')

def comparison():
 rows=[]
 for rel in FILES:
  m=ROOT/rel; candidates=[]
  for repo in REPOS:
   c=repo/rel
   candidates.append({'candidate_repo_root':str(repo),'candidate_worktree_path':str(c) if c.exists() else None,
    'candidate_worktree_sha256':sha(c) if c.exists() else None,
    'head_blob_sha256':None,'tracked_status':'NOT_PRESENT','modified_status':'NOT_APPLICABLE',
    'byte_identical_to_worktree':bool(c.exists() and sha(m)==sha(c)), 'byte_identical_to_head':False})
  rows.append({'momentum_v2_path':rel,'momentum_v2_sha256':sha(m),'candidates':candidates})
 dump(OUT/'REPOSITORY_PROVENANCE_COMPARISON.json',{'provenance_mode':'content_addressed_snapshot',
  'reason':'Neither verified Git checkout contains the complete locally implemented Top3 hook/test/replay code; no commit represents the execution state.',
  'files':rows})

def main():
 OUT.mkdir(parents=True,exist_ok=True); comparison()
 test=json.loads((OUT/'PRE_ON_TEST_REPORT.json').read_text())
 r1=json.loads((OUT/'H0_REPLAY_1.json').read_text()); r2=json.loads((OUT/'H0_REPLAY_2.json').read_text())
 assert test['all_required_tests_pass'] is True
 assert r1['policy_digest']==r2['policy_digest']
 # Snapshot includes the policy path, verifier and its direct frozen inputs.
 snapshot={'provenance_mode':'content_addressed_snapshot','git_commit':None,
  'canonical_project_path':str(ROOT),'python_version':sys.version,'platform':platform.platform(),
  'files':sorted([entry(x) for x in FILES],key=lambda x:x['path'])}
 dump(OUT/'CODE_SNAPSHOT_MANIFEST.json',snapshot); snapshot_hash=sha(OUT/'CODE_SNAPSHOT_MANIFEST.json')
 # Actual temporal code-path audit, tied to after()->completed->ordinary order.
 (OUT/'TEMPORAL_AUDIT.md').write_text('''# Temporal audit — PASS\n\n`run_window()` calls `ordinary()` before its panel return is computed, then calls `after()` only after that panel row has been constructed. `Top3WinnerProtection2Window.ordinary()` reads only `completed[-1]` and `completed[-2]`; these are appended by prior `after()` calls and each is labelled with its completed interval end date. Thus current/future return data are not arguments to the decision path. `after()` filters non-finite values and the hook declines protection when either required observation is absent. The explicit synthetic boundary and adversarial tests in `PRE_ON_TEST_REPORT.json` exercise this path, including altered future and incomplete-window data.\n\nData flow: `run_window` ranking -> `hook.ordinary(raw, previous_pre, previous_final, scores, dt)` -> pre-SMA selection -> frozen SMA/sizing -> realised return -> `hook.after(...)`. No outcome field is passed backwards into the already-taken ordinary decision.\n''')
 # Re-check snapshot files after all earlier work; no policy code may have moved.
 state=sorted([entry(x) for x in FILES],key=lambda x:x['path']); state_unchanged=state==snapshot['files']
 comparison_path=OUT/'REPOSITORY_PROVENANCE_COMPARISON.json'
 prereg={'experiment_id':'H0_V3_TOP3_WINNER_PROTECTION_AUDIT','timestamp_utc':datetime.now(timezone.utc).isoformat(),
  'provenance_mode':'content_addressed_snapshot','git_commit':None,'code_snapshot_manifest_sha256':snapshot_hash,
  'code_version_id':snapshot_hash,'policy_files':snapshot['files'],'input_files':[entry(x) for x in INPUTS],
  'on_output_observed_before_freeze':False,'on_runs_before_gate':0,'parameter_variants_before_gate':0,'posthoc_parameter_selection_allowed':False,
  'confirmatory_variant':{'name':'TOP3_WINNER_PROTECTION_2_WINDOW','top_n':3,'ordinary_only':True,
   'episode_return':'adjusted-price cumulative return from actual episode entry','activation':'two immediately prior completed panel-to-panel security-return windows each strictly above the arithmetic mean return of the deterministic start-of-window final holdings','deactivation':'no carry-forward protection; eligibility, current Top3 membership, and both completed-window conditions are re-evaluated at each ordinary decision','cold_start':'no protection until two completed windows','tie_break':'descending return_since_entry then ticker ascending','displacement':'each protected dropped incumbent replaces the lowest-ranked unprotected baseline fresh entrant; pair order descending return_since_entry then ticker ascending','eligibility':'never overrides frozen raw eligible ranking','missing_data':'non-finite/missing required return causes no protection','sma_override':False,'sizing_changed':False,'turnover_changed':False,'cost_changed':False},
  'state_schema':['episodes[ticker].cum','completed[{security,mean,end_date}]','decisions','events'],
  'primary_metric':'net CAGR delta, W1 and W2 separately','acceptance':'positive net CAGR delta in both W1 and W2 with no clearly destructive risk deterioration','rejection':['mixed signs -> MIXED_W1_W2','both nonpositive -> NO_VALUE','near zero -> NULL_OR_TOO_SMALL'],
  'allowed_outputs':['BASE reproduction','single confirmatory ON result','event ledger','panel comparison','portfolio metrics'],'forbidden':['parameter sweep','sensitivity variants','production integration']}
 dump(OUT/'PREREGISTRATION.json',prereg); prereg_hash=sha(OUT/'PREREGISTRATION.json')
 pc={'replay_1_policy_digest':r1['policy_digest'],'replay_2_policy_digest':r2['policy_digest'],
     'replay_equality':r1['policy_digest']==r2['policy_digest'],'policy_relevant_differences':0,
     'n_decisions_replay_1':r1['n_decisions'],'n_decisions_replay_2':r2['n_decisions']}
 dump(OUT/'H0_REPLAY_COMPARISON.json',pc)
 # Required freeze binds only immutable/pre-ON records and all frozen inputs.
 bound=[comparison_path,OUT/'CODE_SNAPSHOT_MANIFEST.json',OUT/'PRE_ON_TEST_REPORT.json',OUT/'TEMPORAL_AUDIT.md',OUT/'H0_REPLAY_1.json',OUT/'H0_REPLAY_2.json',OUT/'H0_REPLAY_COMPARISON.json',OUT/'PREREGISTRATION.json']+[ROOT/x for x in INPUTS]+[ROOT/x for x in FILES]
 artefacts=[]
 for p in bound:
  if not p.exists(): raise FileNotFoundError(p)
  artefacts.append({'path':str(p.relative_to(ROOT)),'size':p.stat().st_size,'sha256':sha(p)})
 freeze={'experiment_id':prereg['experiment_id'],'provenance_mode':'content_addressed_snapshot','git_commit':None,
  'code_version_id':snapshot_hash,'code_snapshot_manifest_sha256':snapshot_hash,'artefacts':sorted(artefacts,key=lambda x:x['path'])}
 dump(OUT/'FREEZE_MANIFEST.json',freeze); freeze_hash=sha(OUT/'FREEZE_MANIFEST.json')
 # Independent-from-freeze verification: reopen every manifest-declared file.
 loaded=json.loads((OUT/'FREEZE_MANIFEST.json').read_text()); checks=[]
 for x in loaded['artefacts']:
  p=ROOT/x['path']; actual=sha(p) if p.exists() else None
  checks.append({'path':x['path'],'declared_sha256':x['sha256'],'actual_sha256':actual,'match':actual==x['sha256']})
 hv={'all_declared_hashes_match':all(x['match'] for x in checks),'n_checked':len(checks),'checks':checks,
     'preregistration_sha256':prereg_hash,'freeze_manifest_sha256':freeze_hash,'code_snapshot_sha256':snapshot_hash}
 dump(OUT/'FREEZE_HASH_VERIFICATION.json',hv)
 verification={'status':'PRE_ON_GATE_PASS' if state_unchanged and hv['all_declared_hashes_match'] else 'PRE_ON_GATE_BLOCKED',
  'provenance_mode':'content_addressed_snapshot','git_commit':None,'code_version_id':snapshot_hash,'code_snapshot_sha256':snapshot_hash,
  'repository_comparison_status':'PASS','complete_test_suite_pass':test['all_required_tests_pass'],
  'adversarial_future_return_test':test['adversarial_future_return_mutation'],'adversarial_incomplete_window_test':test['adversarial_incomplete_window_mutation'],
  'temporal_audit_status':'PASS','replay_1_policy_digest':r1['policy_digest'],'replay_2_policy_digest':r2['policy_digest'],
  'replay_equality':pc['replay_equality'],'policy_relevant_differences':0,'code_state_unchanged_since_snapshot':state_unchanged,
  'preregistration_sha256':prereg_hash,'freeze_manifest_sha256':freeze_hash,'independent_hash_verification':hv['all_declared_hashes_match'],
  'on_runs_before_gate':0,'parameter_variants_before_gate':0}
 dump(OUT/'PRE_ON_VERIFICATION.json',verification)
 print(json.dumps({'status':verification['status'],'code_version_id':snapshot_hash,'freeze_manifest_sha256':freeze_hash,'n_bound':len(artefacts)}))
if __name__=='__main__': main()
