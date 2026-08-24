import hashlib,json,subprocess
from pathlib import Path
R=Path('/home/hannesb/momentum_v2');O=R/'research_k/h0_v3_top3_winner_protection_audit';O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 test=subprocess.run(['/opt/momentum/venv/bin/python',str(R/'tools/test_top3_winner_protection_preon.py')],capture_output=True,text=True)
 (O/'TEMPORAL_AUDIT.md').write_text('# Temporal audit\n\nThe hook reads `completed[-1]` and `completed[-2]` only. Those states are appended in `after()` after the prior panel return is realised, and are used only at a later ordinary decision. However, the required adversarial full-run and missing/eligibility test suite is not yet complete.\n')
 pre={'experiment_id':'H0_V3_TOP3_WINNER_PROTECTION_AUDIT','on_output_observed_before_freeze':False,'parameter_variants_run_before_freeze':False,'status':'NOT_FROZEN__TEST_SUITE_INCOMPLETE','policy':'TOP3_WINNER_PROTECTION_2_WINDOW'}
 (O/'PREREGISTRATION.json').write_text(json.dumps(pre,indent=2)+'\n');(O/'PREREGISTRATION.md').write_text('# Pre-ON draft\n\nNot a valid freeze: mandatory adversarial and full replay tests remain incomplete.\n')
 v={'unit_test_basic':test.returncode==0,'adversarial_lookahead_test':False,'missing_nan_test':False,'eligibility_test':False,'full_replay_twice':False,'temporal_audit_clean':False,'on_runs_before_gate':0,'parameter_variants_before_gate':0,'status':'PRE_ON_GATE_BLOCKED','blocker':'Mandatory test coverage is incomplete; preregistration/freeze may not be finalized.'}
 (O/'PRE_ON_VERIFICATION.json').write_text(json.dumps(v,indent=2)+'\n')
 (O/'HASHES.txt').write_text('\n'.join(f'{sha(p)}  {p.name}' for p in [O/'PREREGISTRATION.json',O/'TEMPORAL_AUDIT.md',O/'PRE_ON_VERIFICATION.json',R/'tools/frozen_h0_v3_policy_adapter.py'])+'\n')
if __name__=='__main__':main()
