"""One-time reconciliation after direct recovery runs N3-30..32."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import nightly_master_queue_2026_08_01 as q
from niva3_stage_control import verify_manifest

ROOT=Path(__file__).resolve().parents[1]
ITEMS={
 'conditional_risk_adjusted_momentum':'results/niva3_stages/30_conditional_riskadj_screen.json',
 'ranker_uncertainty_switch':'results/niva3_stages/31_ranker_uncertainty_switch_screen.json',
 'cause_specific_reentry':'results/niva3_stages/32_cause_specific_reentry_gate.json'}
def main():
 state=q.load_state()
 for name,rel in ITEMS.items():
  m=verify_manifest(ROOT/rel)
  state['items'][name]={'status':'PASS','finished_at':datetime.now().astimezone().isoformat(timespec='seconds'),
   'duration_seconds':None,'returncode':0,'log':rel,'detail':'direct technical-recovery run; frozen current-contract stage',
   'chain_after':{'n3_stage':m['stage'],'n3_hash':m['manifest_sha256'],'n2_hash':'bdfb0811721e22a9a43242a108106bfe362c98326c752ab0bdaa38471ee5cde1'}}
 state.pop('finished_at',None);state.pop('final_chain',None);state.pop('production_hashes_at_end',None)
 q.atomic_json(q.STATE,state)
 print(json.dumps({k:state['items'][k]['chain_after'] for k in ITEMS},indent=2))
if __name__=='__main__':main()
