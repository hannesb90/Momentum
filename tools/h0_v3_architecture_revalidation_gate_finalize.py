import csv,hashlib,json
from pathlib import Path
V=Path('/home/hannesb/momentum_v2');O=V/'research_k/h0_v3_architecture_revalidation_gate';R=O/'P0_FIRST_RERUN'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 x=json.loads((R/'RESULT.json').read_text());g=json.loads((O/'GATE_RESULT.json').read_text())
 old=json.loads((V/'research_k/h0_reentry_score_improvement_results.json').read_text())
 # Existing source reports old results under 2014_2019 / 2021_2026; preserve exact artifact rather than recalculate it.
 with open(O/'ARCHITECTURE_REVALIDATION_CANONICAL_UPDATE_PROPOSAL.csv','w',newline='') as f:
  cols=['mechanism','old_canonical_status','new_revalidation_evidence','proposed_new_status','reason','canonical_map_modified'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerow({'mechanism':'REENTRY_SCORE_IMPROVEMENT','old_canonical_status':'CLOSED (clean W1/W2 mixed in existing resolution)','new_revalidation_evidence':'Frozen H0 V3: W1 -1.092pp CAGR; W2 +1.025pp; base reproduction PASS both windows.','proposed_new_status':'CLOSED_NONREPLICATION','reason':'Architecture-correct result remains mixed and fails the prespecified positive-both-windows screen; no support for the intervention.','canonical_map_modified':'FALSE'})
 g.update({'first_p0_rerun_completed':True,'first_p0_result_sha256':sha(R/'RESULT.json'),'first_p0_verdict':x['verdict'],'first_p0_base_reproduction_pass':all(v['BASE_ARCHITECTURE_REPRODUCTION_PASS'] for v in x['base_reproduction'].values()),'canonical_update_proposal_sha256':sha(O/'ARCHITECTURE_REVALIDATION_CANONICAL_UPDATE_PROPOSAL.csv')})
 (O/'GATE_RESULT.json').write_text(json.dumps(g,indent=2)+'\n')
 (O/'SUMMARY.md').write_text(f'''# H0 V3 architecture revalidation gate

Compatibility inputs verified. The P0 freeze contains six architecture-dependent mechanisms; only the first was run.

## First rerun: REENTRY_SCORE_IMPROVEMENT

Frozen H0 V3 base reproduction passed for W1 and W2. The unchanged +0.10 reentry-score threshold produced **{x['windows']['W1']['effect_cagr_pp']:+.3f} pp** W1 and **{x['windows']['W2']['effect_cagr_pp']:+.3f} pp** W2 CAGR relative to frozen BASE. Turnover fell by {x['windows']['W1']['turnover_delta']:+.3f} / {x['windows']['W2']['turnover_delta']:+.3f}; cost fell by {x['windows']['W1']['cost_delta']:+.6f} / {x['windows']['W2']['cost_delta']:+.6f}. Verdict: `{x['verdict']}`.

This preserves the practical canonical conclusion—no robust reentry-policy improvement—but records it as architecture-revalidated evidence. No global canonical artifact was changed, no other P0 candidate was run, and no recovery candidate freeze was created.
''')
if __name__=='__main__':main()
