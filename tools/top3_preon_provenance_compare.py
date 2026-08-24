import hashlib,json,subprocess
from pathlib import Path
R=Path('/home/hannesb/momentum_v2');O=R/'research_k/h0_v3_top3_winner_protection_audit'
files=['tools/frozen_h0_v3_policy_adapter.py','tools/rebalance_cadence_4w_vs_8w_audit.py','tools/h0_v3_kor.py','tools/h0_v3_eligibility.py','tools/test_top3_winner_protection_preon.py']
repos=[Path('/home/hannesb/momentum_prod_work'),Path('/home/hannesb/momentum_exports_2026-08-02/github_repo')]
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=[]
 for f in files:
  q={'momentum_v2_path':f,'momentum_v2_sha256':h(R/f),'candidates':[]}
  for repo in repos:
   p=repo/f; tracked=subprocess.run(['git','-C',str(repo),'ls-files','--error-unmatch',f],capture_output=True).returncode==0
   q['candidates'].append({'repo_root':str(repo),'candidate_path':f if p.exists() else None,'working_sha256':h(p) if p.exists() else None,'tracked':tracked,'modified':bool(subprocess.run(['git','-C',str(repo),'diff','--quiet','--',f]).returncode),'byte_identical_to_worktree':p.exists() and h(p)==h(R/f)})
  out.append(q)
 (O/'REPOSITORY_PROVENANCE_COMPARISON.json').write_text(json.dumps({'provenance_mode':'content_addressed_snapshot','reason':'Top3 hook/test files are local additions and no checkout represents complete actual state.','files':out},indent=2)+'\n')
if __name__=='__main__':main()
