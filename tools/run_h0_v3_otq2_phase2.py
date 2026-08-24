"""Frozen OTQ2 phase 2: PIT gates then conditional, non-overlay diagnostics."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'tools'))
import h0_v3_production as PROD
import build_h0_v3_otq2_coverage_first as B
OUT=ROOT/'research_k/h0_v3_otq2_coverage_first_quality_model'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sp(x,y): return pd.Series(x).corr(pd.Series(y),method='spearman')
def residual(x,z):
 a=np.c_[np.ones(len(z)),z]; return x-a@np.linalg.lstsq(a,x,rcond=None)[0]
def main():
 freeze=json.loads((OUT/'OTQ2_MODEL_FREEZE.json').read_text()); freeze_ok=freeze['model_spec_sha256']==sha(OUT/'OTQ2_MODEL_SPEC.json') and freeze['input_sha256']==sha(B.R12)
 if not freeze_ok: raise SystemExit('OTQ2_PRE_RETURN_FREEZE_INVALID')
 # Deterministic pre-return future-mutation test; report values after t are changed by 1e9.
 fund=pd.DataFrame(json.loads(B.R12.read_text())); fund.report_date=pd.to_datetime(fund.report_date)
 samples=['2014-09-10','2016-12-14','2020-01-02','2023-07-06','2026-01-07']; mut=[]
 for d in samples:
  base=B.score_frame(B.latest_asof(fund,pd.Timestamp(d)),d,'TEST').sort_values('kod').reset_index(drop=True)
  fm=fund.copy(); future=fm.report_date>pd.Timestamp(d)
  for c in ['revenues','operating_Income','free_Cash_Flow','cash_Flow_From_Operating_Activities','total_Equity','total_Assets','net_Debt','profit_To_Equity_Holders']: fm.loc[future,c]=fm.loc[future,c].fillna(0)+1e9
  changed=B.score_frame(B.latest_asof(fm,pd.Timestamp(d)),d,'TEST').sort_values('kod').reset_index(drop=True)
  cols=['kod','OTQ2_HARD','PROFITABILITY','GROWTH_AND_SCALABILITY','BALANCE_SHEET','CASH_AND_CAPITAL_DISCIPLINE','n_dimensions_available']
  mut.append({'panel_date':d,'same':base[cols].equals(changed[cols]),'n':len(base)})
 mutation_pass=all(x['same'] for x in mut)
 # Determinism is proven from two independent fresh-process historical rebuilds.
 # These builds use the frozen model and inputs, but write outside the canonical
 # artifact directory so the frozen score matrix cannot be overwritten.
 hist=pd.read_csv(OUT/'OTQ2_HISTORICAL_SCORES.csv')
 det_paths=[OUT/'determinism_run1'/'OTQ2_HISTORICAL_SCORES.csv',OUT/'determinism_run2'/'OTQ2_HISTORICAL_SCORES.csv']
 if not all(p.exists() for p in det_paths): raise SystemExit('OTQ2_HISTORICAL_DETERMINISM_MISSING_FRESH_REBUILDS')
 h1,h2=[sha(p) for p in det_paths]; det=h1==h2
 (OUT/'OTQ2_PIT_FUTURE_MUTATION.json').write_text(json.dumps({'sample_rule':'fixed dates spanning W1/W2','tests':mut,'status':'PASS' if mutation_pass else 'FAIL'},indent=2)+'\n')
 (OUT/'OTQ2_DETERMINISM.json').write_text(json.dumps({'method':'two independent fresh-process full historical rebuilds','historical_score_csv_sha256_run1':h1,'historical_score_csv_sha256_run2':h2,'status':'PASS' if det else 'FAIL'},indent=2)+'\n')
 common={'W1_OTQ2_COMMON':{'start':'2014-09-10','end':'2019-12-25'},'W2':{'start':'2020-01-02','end':'2026-07-09'},'frontier':'canonical momentum ranks 16-60 inclusive, frozen before return access','valuation_historical':'UNKNOWN; no valuation metric participates in OTQ2_HARD'}
 (OUT/'OTQ2_COMMON_WINDOW_DEFINITION.json').write_text(json.dumps(common,indent=2)+'\n')
 # Returns are first accessed below, only after gates are persisted.
 PROD.load_engine(); cov=[]; data=[]
 for w in ('W1','W2'):
  ctx=PROD.V2.CTX[w]; panels=ctx['panels']; start='2014-09-10' if w=='W1' else '2020-01-02'
  for i,d in enumerate(panels[:-1]):
   if d<start: continue
   ranks=ctx['rankings'][d]; rmap={r['kod']:(j+1,r['score']) for j,r in enumerate(ranks)}
   s=hist[(hist.window==w)&(hist.panel_date==d)].copy(); s['rank']=s.kod.map(lambda k:rmap.get(k,(np.nan,np.nan))[0]); s['momentum_score']=s.kod.map(lambda k:rmap.get(k,(np.nan,np.nan))[1]); s['future_return']=s.kod.map(lambda k:ctx['returns'].get((k,d),np.nan)); s=s.dropna(subset=['rank'])
   for pop,mask in [('FULL_UNIVERSE',pd.Series(True,index=s.index)),('MOMENTUM_FRONTIER',(s['rank']>=16)&(s['rank']<=60)),('CANONICAL_TOP30',s['rank']<=30)]:
    q=s[mask]; cov.append({'window':w,'panel_date':d,'population':pop,'n':len(q),'score_coverage':q.OTQ2_HARD.notna().mean() if len(q) else np.nan,'unknown':int(q.OTQ2_HARD.isna().sum()),'mean_dimensions':q.n_dimensions_available.mean() if len(q) else np.nan})
   q=s[(s['rank']>=16)&(s['rank']<=60)&s.OTQ2_HARD.notna()&s.future_return.notna()].copy(); q['window']=w;q['panel_date']=d; data.append(q)
 covdf=pd.DataFrame(cov); covdf.to_csv(OUT/'OTQ2_COVERAGE_BIAS_AUDIT.csv',index=False)
 allx=pd.concat(data,ignore_index=True)
 dep=allx.groupby(['window','n_dimensions_available']).OTQ2_HARD.agg(['count','mean','median','min','max']).reset_index(); dep.to_csv(OUT/'OTQ2_SCORE_BY_DIMENSION_COVERAGE.csv',index=False)
 rows=[]; bands=[]
 for w,g in allx.groupby('window'):
  raw=sp(g.OTQ2_HARD,g.future_return); rr=[]; panel_sp=[]; highlow=[]
  for d,x in g.groupby('panel_date'):
   if len(x)>=8:
    rr.append(sp(residual(x.OTQ2_HARD.values,x.momentum_score.values),residual(x.future_return.values,x.momentum_score.values)))
    panel_sp.append(sp(x.OTQ2_HARD,x.future_return))
   for lo,hi in [(16,30),(31,45),(46,60)]:
    z=x[(x['rank']>=lo)&(x['rank']<=hi)]
    if len(z)>=6:
     c=pd.qcut(z.OTQ2_HARD,3,labels=False,duplicates='drop'); diff=z[c==c.max()].future_return.mean()-z[c==c.min()].future_return.mean(); highlow.append(diff); bands.append({'window':w,'panel_date':d,'momentum_band':f'{lo}-{hi}','high_minus_low_return':diff,'n':len(z)})
  rows.append({'window':w,'population':'MOMENTUM_FRONTIER','n_obs':len(g),'n_panels':g.panel_date.nunique(),'raw_spearman':raw,'mean_panel_spearman':np.nanmean(panel_sp),'partial_spearman_after_momentum':np.nanmean(rr),'within_band_high_minus_low':np.nanmean(highlow),'positive_band_fraction':np.mean(np.array(highlow)>0) if highlow else np.nan})
 diag=pd.DataFrame(rows);diag.to_csv(OUT/'OTQ2_CONDITIONAL_DIAGNOSTICS.csv',index=False);diag.to_csv(OUT/'OTQ2_RESIDUAL_DIAGNOSTICS.csv',index=False);pd.DataFrame(bands).to_csv(OUT/'OTQ2_WITHIN_MOMENTUM_BANDS.csv',index=False)
 signs={r.window:(r.partial_spearman_after_momentum>0 and r.within_band_high_minus_low>0) for _,r in diag.iterrows()}; allowed=mutation_pass and det and signs.get('W1',False) and signs.get('W2',False)
 decision={'decision':'BOUNDED_SELECTION_RERANK_ALLOWED' if allowed else 'NO_BOUNDED_OVERLAY_IN_THIS_RUN','rule':'positive primary partial association and positive within-band spread in W1 and W2, with PIT/determinism pass','inputs':diag.to_dict('records'),'overlay_executed':False}
 (OUT/'OTQ2_FRONTIER_FREEZE.json').write_text(json.dumps({'definition':common['frontier'],'pre_return_freeze_sha256':sha(OUT/'OTQ2_MODEL_FREEZE.json')},indent=2)+'\n');(OUT/'OTQ2_PLACEMENT_DECISION.json').write_text(json.dumps(decision,indent=2)+'\n')
 result={'OTQ2_FREEZE_INTEGRITY':'PASS','OTQ2_PIT_FUTURE_MUTATION':'PASS' if mutation_pass else 'FAIL','OTQ2_DETERMINISM':'PASS' if det else 'FAIL','W1_FRONTIER_COVERAGE':float(covdf[(covdf.window=='W1')&(covdf.population=='MOMENTUM_FRONTIER')].score_coverage.mean()),'W2_FRONTIER_COVERAGE':float(covdf[(covdf.window=='W2')&(covdf.population=='MOMENTUM_FRONTIER')].score_coverage.mean()),'CONDITIONAL_SIGNAL_W1':'POSITIVE' if signs.get('W1') else 'NEGATIVE','CONDITIONAL_SIGNAL_W2':'POSITIVE' if signs.get('W2') else 'NEGATIVE','PLACEMENT_DECISION':decision['decision'],'OVERLAY_EXECUTED':False,'ECONOMIC_RESULT':'NOT_RUN','PRODUCTION_MUTATION_PERFORMED':False,'NEXT_ACTION':'FREEZE_OTQ2_RESEARCH_CANDIDATE' if allowed else 'KEEP_OTQ2_AS_ANALYSIS_ONLY'}
 (OUT/'OTQ2_PHASE2_RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'OTQ2_PHASE2_REPORT.md').write_text('# OTQ2 phase 2\n\n'+json.dumps(result,indent=2)+'\n\nNo portfolio overlay was executed in this phase.\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__': main()
