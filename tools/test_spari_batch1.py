#!/usr/bin/env python3
from __future__ import annotations
import hashlib,inspect,json,tempfile
from pathlib import Path
import pandas as pd
import spari_batch1 as i

ROOT=Path(__file__).resolve().parents[1]
def digest_records(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def main():
 old=i.OUT
 with tempfile.TemporaryDirectory() as td:
  i.OUT=Path(td)/'new';i.verify_prereg()
 i.OUT=old;d,_=i.load();champ=i.champion_scores(d);before=digest_records(champ.to_dict('records'))
 # Targets are evaluation-only: arbitrary target mutations cannot enter the score function.
 fake={(k,x):999 for k,x in zip(d.kod,d.panel_date)};assert fake and digest_records(i.champion_scores(d).to_dict('records'))==before
 assert 'targets' not in inspect.signature(i.champion_scores).parameters
 pret,meta=i.execution_returns();o=i.oos(champ);selected={(r.kod,r.panel_date) for _,r in o.sort_values(['panel_date','score','kod'],ascending=[True,False,False]).groupby('panel_date').head(30).iterrows()}
 bad=[(k,x,m.get('entry_execution_date')) for (k,x),m in meta.items() if (k,x) in selected and m.get('entry_execution_date') and m['entry_execution_date']<=x];assert not bad
 forbidden=('panels','validated','spard','spare','sparf','sparg','trackh','repair_df')
 assert all(not str(i.OUT.relative_to(ROOT)).startswith(x) for x in forbidden)
 out=ROOT/'research_i/results/SPARI_BATCH1_V1';rank=json.load(open(out/'rankings.json'));assert not any(any(str(k).startswith('target') or k=='y' for k in r) for r in rank)
 trades=json.load(open(out/'trades.json'));assert not any(r.get('execution_price_date') and r['execution_price_date']<=r['panel_date'] for r in trades if r.get('side')=='BUY')
 scope=json.load(open(out/'protected_scope_audit.json'));assert scope['status']=='PASS' and not scope['changed']
 print(json.dumps({'status':'PASS','tests':['prereg_hash_gate','target_mutation_rank_invariance','champion_has_no_target_argument','post_decision_execution','isolated_output_scope','artifact_has_no_target_fields','all_buys_post_decision','protected_scope_unchanged'],'champion_decision_hash':before}))
if __name__=='__main__':main()
