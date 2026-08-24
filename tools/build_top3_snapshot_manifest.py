import hashlib,json,platform,sys
from pathlib import Path
R=Path('/home/hannesb/momentum_v2');O=R/'research_k/h0_v3_top3_winner_protection_audit'
F=['tools/frozen_h0_v3_policy_adapter.py','tools/rebalance_cadence_4w_vs_8w_audit.py','tools/h0_v3_kor.py','tools/test_top3_winner_protection_preon.py']
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 a=[]
 for x in sorted(F):
  p=R/x;a.append({'path':x,'size':p.stat().st_size,'sha256':h(p)})
 d={'canonical_absolute_project_path':str(R),'timestamp_utc':__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat(),'python_version':sys.version,'platform':platform.platform(),'git_commit':None,'provenance_mode':'content_addressed_snapshot','explanation':'Git metadata is absent; provenance is cryptographically content-addressed.','files':a}
 (O/'CODE_SNAPSHOT_MANIFEST.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':main()
