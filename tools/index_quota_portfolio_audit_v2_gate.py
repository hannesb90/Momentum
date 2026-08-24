"""V2 PIT data/mapping gate only.  It deliberately computes no quota returns."""
from __future__ import annotations
import csv,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
V2=Path('/home/hannesb/momentum_v2'); OUT=V2/'research_k/index_quota_portfolio_audit_v2'
SRC=Path('/home/hannesb/momentum_prod_work/momentum_ml/data/omx30_membership_pit.csv')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return x.upper().replace('-','').replace(' ','').replace('_','')
def main():
 pre=json.loads((OUT/'preregistration.json').read_text()); rows=list(csv.DictReader(SRC.open()))
 required={'member_from','member_to'}
 if not rows or not required.issubset(rows[0]):raise SystemExit('INDEX_MEMBERSHIP_DATA_NOT_PIT_COMPLETE: required date fields absent')
 # Column name is intentionally discovered, but must be unambiguous.
 candidates=[c for c in rows[0] if c.lower() in {'ticker','symbol','instrument','security'}]
 if len(candidates)!=1:raise SystemExit('INDEX_MEMBERSHIP_DATA_NOT_PIT_COMPLETE: ambiguous ticker column')
 tc=candidates[0]; intervals=[]; bad=[]
 for r in rows:
  if not r['member_from'] or not r['member_to'] or not r[tc]:bad.append(r);continue
  intervals.append((r['member_from'],r['member_to'],norm(r[tc])))
 if bad:raise SystemExit('INDEX_MEMBERSHIP_DATA_NOT_PIT_COMPLETE: incomplete interval rows')
 # Weekly PIT source must have no future interval used for any date. Coverage is source-level here;
 # portfolio-level eligibility is a separate mandatory run gate in the execution harness.
 lo=min(x[0] for x in intervals);hi=max(x[1] for x in intervals)
 result={'study':'INDEX_QUOTA_PORTFOLIO_AUDIT_V2','run_utc':datetime.now(timezone.utc).isoformat(),'stage':'PIT_SOURCE_AND_MAPPING_GATE','return_calculations_performed':False,'source':str(SRC),'source_sha256':sha(SRC),'ticker_column':tc,'n_intervals':len(intervals),'coverage':[lo,hi],'status':'SOURCE_INTERVALS_VALID__PORTFOLIO_PANEL_ELIGIBILITY_GATE_PENDING','arms':pre['arms'],'aliases_frozen':{'LUNE':'LUPE','NOKIASEK':'NOKIA'}}
 (OUT/'PIT_SOURCE_GATE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
