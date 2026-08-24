"""Pre-return immutable setup for H0_V3_OTQ2_QUALITY_GATE_PLACEMENT_TEST."""
import hashlib,json
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1]; S=R/'research_k/h0_v3_otq2_coverage_first_quality_model'; O=R/'research_k/h0_v3_otq2_quality_gate_placement_test';O.mkdir(exist_ok=True)
def h(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
freeze=json.loads((S/'OTQ2_MODEL_FREEZE.json').read_text())
assert freeze['model_spec_sha256']==h(S/'OTQ2_MODEL_SPEC.json')
hist=pd.read_csv(S/'OTQ2_HISTORICAL_SCORES.csv'); out=[]
for (w,d),x in hist.groupby(['window','panel_date']):
 q=x[x.OTQ2_HARD.notna()].copy(); q['OTQ2_percentile']=q.OTQ2_HARD.rank(pct=True,method='average'); q['LOW_QUALITY']=q.OTQ2_percentile<=.10
 y=x[['window','panel_date','kod','OTQ2_HARD','n_dimensions_available']].merge(q[['kod','OTQ2_percentile','LOW_QUALITY']],on='kod',how='left');y['UNKNOWN']=y.OTQ2_HARD.isna();y['source_freeze_hash']=h(S/'OTQ2_MODEL_FREEZE.json');out.append(y)
g=pd.concat(out);p=O/'OTQ2_LOW_QUALITY_GATE_FREEZE.csv';g.to_csv(p,index=False)
(O/'OTQ2_LOW_QUALITY_GATE_FREEZE.parquet.NOT_CREATED').write_text('CSV is authoritative; parquet engine unavailable.\\n')
pre={'study':'H0_V3_OTQ2_QUALITY_GATE_PLACEMENT_TEST','source_model_freeze_sha256':h(S/'OTQ2_MODEL_FREEZE.json'),'source_model_spec_sha256':freeze['model_spec_sha256'],'gate':'bottom 10% OTQ2_HARD by canonical decision panel; UNKNOWN remains eligible','windows':{'W1_OTQ2_COMMON':['2014-09-10','2019-12-25'],'W2':['2020-01-02','2026-07-09']},'arms':['BASE_CURRENT_CANONICAL','PRE_K1_UNIVERSE_GATE','POST_K1_PRE_SELECTION_GATE','ENTRY_ONLY_QUALITY_GATE'],'status':'PRE_RETURN_FROZEN'}
(O/'QUALITY_GATE_PREREGISTRATION.json').write_text(json.dumps(pre,indent=2)+'\\n');pre['gate_csv_sha256']=h(p);(O/'QUALITY_GATE_FREEZE.json').write_text(json.dumps(pre,indent=2)+'\\n')
print(json.dumps({'OTQ2_SOURCE_FREEZE_IDENTITY':'PASS','LOW_QUALITY_GATE_FREEZE':'PASS','rows':len(g),'hash':h(p)},indent=2))
