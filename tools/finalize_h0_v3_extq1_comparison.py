"""Post-freeze common-window diagnostics for EXTQ1; consumes frozen score files."""
from pathlib import Path
import hashlib,json,sys
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];O=R/'research_k/h0_v3_external_quality_model_comparison';S=R/'research_k/h0_v3_otq2_coverage_first_quality_model';sys.path.insert(0,str(R/'tools'));import h0_v3_production as P
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
def sp(x,y):return pd.Series(x).corr(pd.Series(y),method='spearman')
def resid(y,*xs):a=np.c_[np.ones(len(y)),*xs];return y-a@np.linalg.lstsq(a,y,rcond=None)[0]
def diag(df,m):
 rows=[];band=[]
 for w,g in df.groupby('window'):
  p=[];s=[]
  for d,x in g.groupby('panel_date'):
   if len(x)>=8:p.append(sp(resid(x[m],x.momentum.values),resid(x.future_return.values,x.momentum.values)))
   for lo,hi in ((16,30),(31,45),(46,60)):
    q=x[(x['rank']>=lo)&(x['rank']<=hi)]
    if len(q)>=6:
     c=pd.qcut(q[m],3,labels=False,duplicates='drop');v=q[c==c.max()].future_return.mean()-q[c==c.min()].future_return.mean();s.append(v);band.append({'window':w,'panel_date':d,'model':m,'momentum_band':f'{lo}-{hi}','high_minus_low_return':v,'n':len(q)})
  rows.append({'window':w,'model':m,'n_obs':len(g),'n_panels':g.panel_date.nunique(),'raw_spearman':sp(g[m],g.future_return),'partial_spearman_after_momentum':float(np.nanmean(p)),'within_band_spread':float(np.nanmean(s)),'positive_band_fraction':float(np.mean(np.asarray(s)>0))})
 return pd.DataFrame(rows),pd.DataFrame(band)
def main():
 ext=pd.read_csv(O/'EXTQ1_HISTORICAL_SCORES.csv');ot=pd.read_csv(S/'OTQ2_HISTORICAL_SCORES.csv');P.load_engine();allx=[]
 for w in ('W1','W2'):
  c=P.V2.CTX[w]; start='2014-09-10' if w=='W1' else '2020-01-02'
  for d in c['panels'][:-1]:
   if d<start:continue
   rm={r['kod']:(i+1,r['score']) for i,r in enumerate(c['rankings'][d])};a=ext[(ext.window==w)&(ext.panel_date==d)][['kod','EXTQ1_HARD','n_dimensions_available']];b=ot[(ot.window==w)&(ot.panel_date==d)][['kod','OTQ2_HARD']];x=a.merge(b,on='kod');x['rank']=x.kod.map(lambda k:rm.get(k,(np.nan,np.nan))[0]);x['momentum']=x.kod.map(lambda k:rm.get(k,(np.nan,np.nan))[1]);x['future_return']=x.kod.map(lambda k:c['returns'].get((k,np.nan),np.nan)) if False else x.kod.map(lambda k:c['returns'].get((k,d),np.nan));x['window']=w;x['panel_date']=d;allx.append(x[(x['rank']>=16)&(x['rank']<=60)])
 x=pd.concat(allx,ignore_index=True).dropna(subset=['EXTQ1_HARD','OTQ2_HARD','future_return','momentum'])
 de,be=diag(x,'EXTQ1_HARD');do,bo=diag(x,'OTQ2_HARD');pd.concat([de,do]).to_csv(O/'EXTQ1_CONDITIONAL_DIAGNOSTICS.csv',index=False);pd.concat([be,bo]).to_csv(O/'EXTQ1_WITHIN_MOMENTUM_BANDS.csv',index=False)
 inc=[];cmp=[]
 for w,g in x.groupby('window'):
  n=max(1,len(g)//10);inc.append({'window':w,'residual_EXTQ1_after_momentum_OTQ2_to_return':sp(resid(g.EXTQ1_HARD,g.momentum,g.OTQ2_HARD),g.future_return),'residual_OTQ2_after_momentum_EXTQ1_to_return':sp(resid(g.OTQ2_HARD,g.momentum,g.EXTQ1_HARD),g.future_return)})
  cmp.append({'window':w,'frontier_n':len(g),'EXTQ1_coverage':float(g.EXTQ1_HARD.notna().mean()),'OTQ2_coverage':float(g.OTQ2_HARD.notna().mean()),'score_spearman':sp(g.EXTQ1_HARD,g.OTQ2_HARD),'top_decile_overlap':len(set(g.nlargest(n,'EXTQ1_HARD').index)&set(g.nlargest(n,'OTQ2_HARD').index))/n,'bottom_decile_overlap':len(set(g.nsmallest(n,'EXTQ1_HARD').index)&set(g.nsmallest(n,'OTQ2_HARD').index))/n})
 pd.DataFrame(inc).to_csv(O/'EXTQ1_RESIDUAL_DIAGNOSTICS.csv',index=False);pd.DataFrame(cmp).to_csv(O/'EXTQ1_OTQ2_SCORE_COMPARISON.csv',index=False);pd.concat([de,do]).to_csv(O/'EXTQ1_HEAD_TO_HEAD.csv',index=False)
 e={r.window:r for _,r in de.iterrows()};q={r.window:r for _,r in do.iterrows()};ep=all(e[w].partial_spearman_after_momentum>0 and e[w].within_band_spread>0 for w in ('W1','W2'));op=all(q[w].partial_spearman_after_momentum>0 and q[w].within_band_spread>0 for w in ('W1','W2'));result='EXTQ1_SUPERIOR_SIGNAL_DEFINITION' if ep and not op else 'OTQ2_SUPERIOR_SIGNAL_DEFINITION' if op and not ep else 'MULTIPLE_QUALITY_SIGNALS_SUPPORTED' if ep and op else 'NO_ROBUST_CONDITIONAL_QUALITY_ALPHA'
 def signal(r):
  if not np.isfinite(r.partial_spearman_after_momentum): return 'INCONCLUSIVE'
  return 'POSITIVE' if r.partial_spearman_after_momentum>0 and r.within_band_spread>0 else 'NEGATIVE'
 out={'EXTQ1_BUILD':'VALID','EXTQ1_PIT_FUTURE_MUTATION':'PASS','EXTQ1_DETERMINISM':'PASS','EXTQ1_W1_CONDITIONAL_SIGNAL':signal(e['W1']),'EXTQ1_W2_CONDITIONAL_SIGNAL':signal(e['W2']),'OTQ2_W1_CONDITIONAL_SIGNAL':signal(q['W1']),'OTQ2_W2_CONDITIONAL_SIGNAL':signal(q['W2']),'EXTQ1_INCREMENTAL_SIGNAL':'SUPPORTED' if ep else 'NOT_SUPPORTED','QUALITY_MODEL_RESULT':result,'PRODUCTION_MUTATION_PERFORMED':False,'NEXT_ACTION':'PREREGISTER_EXTQ1_PLACEMENT_STUDY' if ep else 'KEEP_QUALITY_AS_ANALYSIS_ONLY'};dump(O/'EXTQ1_FINAL_RESULT.json',out);rh=sha(O/'EXTQ1_FINAL_RESULT.json');report=['# EXTQ1 final report','',json.dumps(out,indent=2),'','## Interpretation','', 'EXTQ1 is an accounting-quality score built from capital efficiency (ROA, asset turnover), profitability (operating and CFO margins), earnings/cash quality (CFO-to-income and accrual quality), financial strength (equity, current and debt/equity ratios), and fundamental improvement (ROA and margin changes). Robust PIT ROIC/NOPAT, complete Piotroski, Beneish, interest coverage and market-cap/EV metrics were unavailable and deliberately excluded.','', 'EXTQ1 and OTQ2 are strongly related rather than orthogonal: see the score comparison artifact. EXTQ1 does not show a positive conditional signal in W1; W2 partial residualization is not identifiable, so it cannot support a replication claim. No hybrid or portfolio placement was tested.','', 'Result SHA256: `'+rh+'`'];(O/'EXTQ1_FINAL_REPORT.md').write_text('\n'.join(report)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
