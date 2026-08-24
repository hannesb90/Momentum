"""Selection-skill audit strictly from already persisted broad-pool results."""
import json
from pathlib import Path
V=Path('/home/hannesb/momentum_v2');I=V/'research_k/h0_extratrees_broad_pool_top30_audit_results.json';O=V/'research_k/h0_extratrees_selection_skill_audit_results.json'
d=json.loads(I.read_text());out={'version':'H0_ET_SELECTION_SKILL_V1','source_file':I.name,'new_model_training':False,'pools':{},'limitation':'Source retains aggregated IN/OUT horizon means and medians, not per-stock/per-rebalance observations. Trimmed, LOO, bootstrap and randomization cannot be recomputed honestly under the no-new-results constraint.'}
for pool in ['40','50','60','100']:
 out['pools'][pool]={}
 for period,x in d['periods'].items():
  m=x[pool]['mechanism'];out['pools'][pool][period]={'selection_edge':m['in_minus_out'],'retention':m['retention'],'in_by_h0_rank':m['in_by_rank']}
signs=[]
for p in out['pools']:
 for y in ['2017','2018','2019']:
  signs.append(out['pools'][p][y]['selection_edge']['8w']['diff'])
out['classification']='SELECTION SKILL PROMISING-BUT-UNSTABLE' if any(v>0 for v in signs) and any(v<=0 for v in signs) else 'NO SELECTION SKILL'
O.write_text(json.dumps(out,indent=2));print('wrote',O)
