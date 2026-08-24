"""Frozen V2 panel-level PIT feasibility gate.  No quota return is calculated."""
from __future__ import annotations
import csv, json, sys
from datetime import datetime, timezone
from pathlib import Path
V2=Path('/home/hannesb/momentum_v2'); OUT=V2/'research_k/index_quota_portfolio_audit_v2';sys.path.insert(0,str(V2/'tools'))
from rebalance_cadence_4w_vs_8w_audit import run_window
SRC=Path('/home/hannesb/momentum_prod_work/momentum_ml/data/omx30_membership_pit.csv')
def norm(x):return ''.join(c for c in x.upper() if c.isalnum())
ALIAS={'LUNE':'LUPE','NOKIASEK':'NOKIA'}
def member_set(rows,dt):
 s=set()
 for r in rows:
  if r['member_from']<=dt<=r['member_to']:
   s.add(norm(r['ticker']));s.add(norm(r['nasdaq_symbol']))
 return s
def main():
 members=list(csv.DictReader(SRC.open())); rows=[]
 for tag in ('W1','W2'):
  x=run_window(tag); panels=x['panel_calendar']; ranks=x['internal_context']['rankings']; base=x['internal_context']['base']
  for i,(dt,b) in enumerate(zip(panels,base)):
   if i%2:continue
   active=member_set(members,dt); elig=[r['kod'] for r in ranks[dt]]
   hit=[k for k in elig if ALIAS.get(norm(k),norm(k)) in active]
   selected=b['selected_pre_sma']; natural=[k for k in selected if k in hit]
   rows.append({'window':tag,'panel':i,'date':dt,'active_source_members':len(active),'eligible_pit_members':len(hit),'base_natural_members':len(natural),'q8_feasible':len(hit)>=8,'q15_feasible':len(hit)>=15,'q20_feasible':len(hit)>=20})
 out={'study':'INDEX_QUOTA_PORTFOLIO_AUDIT_V2','stage':'PANEL_ELIGIBILITY_FEASIBILITY_GATE','run_utc':datetime.now(timezone.utc).isoformat(),'return_calculations_performed':False,'rows':rows,'minimum_eligible_by_window':{w:min(r['eligible_pit_members'] for r in rows if r['window']==w) for w in ('W1','W2')},'pass_all_q8_q15_q20':all(r['q20_feasible'] for r in rows)}
 (OUT/'PIT_PANEL_ELIGIBILITY_GATE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
