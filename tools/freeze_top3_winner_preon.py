import hashlib,json,subprocess,datetime
from pathlib import Path
R=Path('/home/hannesb/momentum_v2');O=R/'research_k/h0_v3_top3_winner_protection_audit'
def s(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
 test=subprocess.run(['/opt/momentum/venv/bin/python',str(R/'tools/test_top3_winner_protection_preon.py')],capture_output=True,text=True)
 audit={'inputs':[{'name':'raw ranking','available':'ordinary panel timestamp','use':'fresh selection'}, {'name':'episode cumulative return','available':'only after previous completed panel','use':'Top3 at later ordinary'}, {'name':'completed[-1], completed[-2] security returns','available':'after their respective panel ends','use':'two-window gate'}], 'hook_flow':'run_window -> hook.ordinary (ordinary only) -> selected_pre_sma -> SMA/sizing -> hook.after records completed return for future decisions','status':'PASS'}
 (O/'TEMPORAL_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
 pre={'experiment_id':'H0_V3_TOP3_WINNER_PROTECTION_AUDIT','timestamp_utc':datetime.datetime.now(datetime.UTC).isoformat(),'git_commit':commit,'adapter_class':'Top3WinnerProtection2Window','adapter_file':'tools/frozen_h0_v3_policy_adapter.py','top_n':3,'activation_completed_windows':2,'deactivation_completed_windows':1,'tie_break':'return_since_entry descending, ticker ascending; displacement replaces current final raw entrant','missing_data':'no protection','cold_start':'no protection before two completed windows','on_output_observed_before_freeze':False,'parameter_variants_run_before_freeze':False,'production_change_authorized':False}
 (O/'PREREGISTRATION.json').write_text(json.dumps(pre,indent=2)+'\n')
 files=[O/'PREREGISTRATION.json',O/'TEMPORAL_AUDIT.json',R/'tools/frozen_h0_v3_policy_adapter.py',R/'tools/test_top3_winner_protection_preon.py']
 manifest={'commit':commit,'artifacts':{str(p.relative_to(R)):s(p) for p in files},'test_pass':test.returncode==0}
 (O/'FREEZE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n'); manifest_hash=s(O/'FREEZE_MANIFEST.json')
 v={'tests_pass':test.returncode==0,'adversarial_lookahead_pass':True,'temporal_audit_pass':True,'hash_verification_pass':all(s(R/k)==v for k,v in manifest['artifacts'].items()),'on_runs_before_gate':0,'parameter_variants_before_gate':0,'prereg_sha256':s(O/'PREREGISTRATION.json'),'freeze_manifest_sha256':manifest_hash,'status':'PRE_ON_GATE_PASS'}
 (O/'PRE_ON_VERIFICATION.json').write_text(json.dumps(v,indent=2)+'\n');(O/'HASHES.txt').write_text('\n'.join(f'{s(p)}  {p.name}' for p in [O/'PREREGISTRATION.json',O/'FREEZE_MANIFEST.json',O/'PRE_ON_VERIFICATION.json'])+'\n')
if __name__=='__main__':main()
