#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'research_i/forward_challengers'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ts=dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).isoformat();common=['tools/spari_forward_challengers.py','research_i/FREEZE_MANIFEST_BATCH1.json','trackh/H0_LOCK.json','research_i/docs/TREND_CONSISTENCY_DEFINITION_MISMATCH.md']
 specs={'H1_DRAW_RESILIENCE':{'id':'H1','factor':'drawdown_resilience = -abs(trailing 52-calendar-week maximum drawdown from PIT adjusted closes)','historical':{'mean_ic52':0.1948,'top30_ic':0.1217,'cagr':0.2385,'sharpe':1.318,'maxdd':-0.0454,'leave_top3_cagr':0.1598,'leave_top5_cagr':0.1318}},'H2_TREND_STRENGTH':{'id':'H2','factor':'trend_strength = OLS t-stat of log adjusted close on daily observation index over trailing 52 calendar weeks, minimum 200 observations','historical':{'mean_ic52':0.1678,'top30_ic':0.0096,'cagr':0.2698,'sharpe':1.576,'maxdd':-0.0268,'leave_top3_cagr':0.1742,'leave_top5_cagr':0.1324}}}
 for name,s in specs.items():
  d=BASE/name;(d/'journal').mkdir(parents=True,exist_ok=True);idx=d/'journal/INDEX.jsonl'
  if not idx.exists():idx.write_text('');os.chmod(idx,0o644)
  files=[]
  for rel in common:
   p=ROOT/rel;files.append({'path':rel,'sha256':sha(p),'bytes':p.stat().st_size})
  lock={'lock_id':f"SPARI_{s['id']}_FORWARD_V1_IMMUTABLE_2026-08-09",'challenger':s['id'],'freeze_timestamp':ts,'first_forward_eligible_panel':'2026-09-04','forward_start_policy':'Only panels strictly after freeze timestamp; historical metrics are background, never untouched forward.','definition':{'score':f"0.5*rank(H0 frozen champion score)+0.5*rank({s['id']} factor)",'factor':s['factor'],'selection':'Top30 equal weight','rebalance':'same H0 8-week cycle and phase','execution':'V4 first observed close strictly after decision','cost_bps':20,'universe':'same target-free PIT H0 universe','missing_tie':'factor missing gets within-date median factor-rank; score-desc/kod-desc deterministic tie break'},'historical_background_not_forward':s['historical'],'h0_lock_sha256':sha(ROOT/'trackh/H0_LOCK.json'),'batch1_freeze_sha256':sha(ROOT/'research_i/FREEZE_MANIFEST_BATCH1.json'),'locked_files':files,'journal_path':str(idx.relative_to(ROOT)),'immutable':True,'forbidden':['rewrite H0','parameter changes','H1+H2 combination','historical relabeling']}
  p=d/'LOCK.json';p.write_text(json.dumps(lock,ensure_ascii=False,sort_keys=True,indent=2)+'\n');os.chmod(p,0o444);(d/'LOCK.sha256').write_text(sha(p)+'  LOCK.json\n')
if __name__=='__main__':main()
