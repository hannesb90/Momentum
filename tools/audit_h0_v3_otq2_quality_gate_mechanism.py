"""Pre-return mechanical audit of the frozen OTQ2 bottom-decile gate."""
import json,sys
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];O=R/'research_k/h0_v3_otq2_quality_gate_placement_test';sys.path.insert(0,str(R/'tools'))
import h0_v3_production as P
g=pd.read_csv(O/'OTQ2_LOW_QUALITY_GATE_FREEZE.csv');P.load_engine();rows=[]
for w in ('W1','W2'):
 start='2014-09-10' if w=='W1' else '2020-01-02';ctx=P.V2.CTX[w]
 for d in ctx['panels'][:-1]:
  if d<start:continue
  x=g[(g['window']==w)&(g['panel_date']==d)].copy(); ranks={z['kod']:i+1 for i,z in enumerate(ctx['rankings'][d])}
  xrank=x['kod'].map(ranks); q=x[x['LOW_QUALITY'].fillna(False)].copy(); qrank=q['kod'].map(ranks)
  top60=int((qrank<=60).sum()); top30=int((qrank<=30).sum())
  rows.append({'window':w,'panel_date':d,'n_universe':int(xrank.notna().sum()),'gated_n':len(q),'gated_share':len(q)/int(xrank.notna().sum()) if xrank.notna().sum() else None,'top60_gated':top60,'top30_gated':top30,'any_top30':bool(top30),'median_gated_rank':qrank.median(),'max_gated_top30':top30,'unknown_frequency':float(x['UNKNOWN'].mean()),'mean_dimensions_gated':q['n_dimensions_available'].mean()})
df=pd.DataFrame(rows);df.to_csv(O/'QUALITY_GATE_MECHANISM_PRE_RETURN.csv',index=False)
summary=df.groupby('window').agg(panels=('panel_date','count'),gated_share=('gated_share','mean'),top60_gated=('top60_gated','mean'),top30_gated=('top30_gated','mean'),panels_with_top30=('any_top30','mean'),median_gated_rank=('median_gated_rank','median'),unknown_frequency=('unknown_frequency','mean')).reset_index()
(O/'QUALITY_GATE_MECHANISM_SUMMARY.json').write_text(summary.to_json(orient='records',indent=2)+'\n');print(summary.to_string(index=False))
