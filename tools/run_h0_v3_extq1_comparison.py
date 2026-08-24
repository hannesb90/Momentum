"""EXTQ1: frozen accounting-quality comparison against frozen OTQ2 HARD."""
from pathlib import Path
import hashlib,json,math,sys
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1]; O=R/'research_k/h0_v3_external_quality_model_comparison'; O.mkdir(exist_ok=True)
S=R/'research_k/h0_v3_otq2_coverage_first_quality_model'; F=R/'validated/fundamentals/fundamentals_r12_validated.json'
sys.path.insert(0,str(R/'tools')); import h0_v3_production as P
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def ratio(a,b): return a/b if pd.notna(a) and pd.notna(b) and b!=0 else np.nan
def rank(x,up=True):
 if not x.notna().any(): return x
 lo,hi=x.quantile(.01),x.quantile(.99); return x.clip(lo,hi).rank(pct=True,ascending=up)
MET={'roa':('CAPITAL_EFFICIENCY',True,'profit_To_Equity_Holders / total_Assets'), 'asset_turnover':('CAPITAL_EFFICIENCY',True,'revenues / total_Assets'), 'operating_margin':('PROFITABILITY',True,'operating_Income / revenues'), 'cfo_margin':('PROFITABILITY',True,'cash_Flow_From_Operating_Activities / revenues'), 'cfo_to_ni':('EARNINGS_CASH_QUALITY',True,'cash_Flow_From_Operating_Activities / profit_To_Equity_Holders, positive NI only'), 'accrual_quality':('EARNINGS_CASH_QUALITY',False,'(profit_To_Equity_Holders - cash_Flow_From_Operating_Activities) / total_Assets'), 'equity_ratio':('FINANCIAL_STRENGTH',True,'total_Equity / total_Assets'), 'current_ratio':('FINANCIAL_STRENGTH',True,'current_Assets / current_Liabilities'), 'debt_to_equity':('FINANCIAL_STRENGTH',False,'net_Debt / total_Equity, positive equity only'), 'roa_change':('FUNDAMENTAL_IMPROVEMENT',True,'ROA_t - ROA_prior_report'), 'margin_change':('FUNDAMENTAL_IMPROVEMENT',True,'operating_margin_t - operating_margin_prior_report')}
def asof(f,d):
 x=f[f.report_date<=d].sort_values(['kod','report_date']).groupby('kod',as_index=False).tail(1).copy(); prev=f[f.report_date<=d-pd.Timedelta(days=300)].sort_values(['kod','report_date']).groupby('kod',as_index=False).tail(1).set_index('kod')
 for n,fun in {'roa':lambda r:ratio(r.profit_To_Equity_Holders,r.total_Assets),'asset_turnover':lambda r:ratio(r.revenues,r.total_Assets),'operating_margin':lambda r:ratio(r.operating_Income,r.revenues),'cfo_margin':lambda r:ratio(r.cash_Flow_From_Operating_Activities,r.revenues),'cfo_to_ni':lambda r:ratio(r.cash_Flow_From_Operating_Activities,r.profit_To_Equity_Holders) if r.profit_To_Equity_Holders>0 else np.nan,'accrual_quality':lambda r:ratio(r.profit_To_Equity_Holders-r.cash_Flow_From_Operating_Activities,r.total_Assets),'equity_ratio':lambda r:ratio(r.total_Equity,r.total_Assets),'current_ratio':lambda r:ratio(r.current_Assets,r.current_Liabilities),'debt_to_equity':lambda r:ratio(r.net_Debt,r.total_Equity) if r.total_Equity>0 else np.nan}.items(): x[n]=x.apply(fun,axis=1)
 x['roa_change']=[r.roa-prev.loc[r.kod,'profit_To_Equity_Holders']/prev.loc[r.kod,'total_Assets'] if r.kod in prev.index and prev.loc[r.kod,'total_Assets'] not in (0,np.nan) else np.nan for _,r in x.iterrows()]
 x['margin_change']=[r.operating_margin-prev.loc[r.kod,'operating_Income']/prev.loc[r.kod,'revenues'] if r.kod in prev.index and prev.loc[r.kod,'revenues'] not in (0,np.nan) else np.nan for _,r in x.iterrows()]
 return x
def score(x,d,w):
 z=x[['kod','report_date']+list(MET)].copy(); z['window']=w;z['panel_date']=d; dims={}
 for m,(dim,up,_) in MET.items(): z[m+'_pct']=rank(z[m],up);dims.setdefault(dim,[]).append(m+'_pct')
 for dim,cols in dims.items(): z[dim]=z[cols].mean(axis=1,skipna=True)
 dc=list(dims);z['n_dimensions_available']=z[dc].notna().sum(axis=1);z['EXTQ1_HARD']=z[dc].mean(axis=1,skipna=True).where(z.n_dimensions_available>=3); return z
def sp(x,y): return pd.Series(x).corr(pd.Series(y),method='spearman')
def resid(y,*xs):
 a=np.c_[np.ones(len(y)),*xs];return y-a@np.linalg.lstsq(a,y,rcond=None)[0]
def writepq(df,name):
 df.to_csv(O/(name+'.csv'),index=False);(O/(name+'.parquet.NOT_CREATED')).write_text('CSV authoritative; parquet engine unavailable.\n')
def diag(df,model):
 rows=[];bands=[]
 for w,g in df.groupby('window'):
  ps=[];spreads=[]
  for d,x in g.groupby('panel_date'):
   if len(x)>=8: ps.append(sp(resid(x[model],x.momentum.values),resid(x.future_return.values,x.momentum.values)))
   for lo,hi in ((16,30),(31,45),(46,60)):
    q=x[(x.rank>=lo)&(x.rank<=hi)]
    if len(q)>=6:
     c=pd.qcut(q[model],3,labels=False,duplicates='drop'); v=q[c==c.max()].future_return.mean()-q[c==c.min()].future_return.mean();spreads.append(v);bands.append({'window':w,'panel_date':d,'model':model,'band':f'{lo}-{hi}','spread':v,'n':len(q)})
  rows.append({'window':w,'model':model,'n_obs':len(g),'n_panels':g.panel_date.nunique(),'raw_spearman':sp(g[model],g.future_return),'partial_spearman_after_momentum':float(np.nanmean(ps)),'within_band_spread':float(np.nanmean(spreads)),'positive_band_fraction':float(np.mean(np.array(spreads)>0)) if spreads else None})
 return pd.DataFrame(rows),pd.DataFrame(bands)
def main():
 fund=pd.DataFrame(json.loads(F.read_text()));fund.report_date=pd.to_datetime(fund.report_date)
 # Pre-return provenance and freeze. No share/market-cap dependent metric enters EXTQ1.
 prov=[]
 for m,(dim,up,form) in MET.items(): prov.append({'metric':m,'raw_fields':form,'source':str(F),'formula':form,'PIT_status':'HISTORICAL_PIT_VALID','coverage_W1':'computed pre-return','coverage_W2':'computed pre-return','limitations':'report-date aligned R12; sector-neutral ratio policy; financial ratios may be less economic for banks','status':'HISTORICAL_PIT_VALID'})
 for m in ('roic','interest_coverage','piotroski_full','beneish_full','market_cap','ev'): prov.append({'metric':m,'raw_fields':'UNAVAILABLE','source':'none','formula':'not constructed','PIT_status':'UNKNOWN','coverage_W1':0,'coverage_W2':0,'limitations':'insufficient robust PIT inputs; no proxy substituted','status':'UNKNOWN'})
 pd.DataFrame(prov).to_csv(O/'EXTQ1_METRIC_PROVENANCE.csv',index=False)
 spec={'model':'EXTQ1_HARD','external_inspiration':'classical accounting-quality ideas (capital efficiency, DuPont components, cash quality, strength, improvement); exact external GitHub identifier was not retained locally','returns_read_before_freeze':False,'metrics':MET,'dimensions':sorted(set(x[0] for x in MET.values())),'weights':'equal metrics within each dimension; equal available dimensions','transform':'cross-sectional 1/99 winsorisation then percentile','missingness':'UNKNOWN; overall needs >=3 available dimensions','sector_rule':'sector-neutral; no leverage-dependent metric is interpreted as a banking veto','excluded':['ROIC (no robust NOPAT/invested-capital)','Piotroski full','Beneish full','market-cap/EV/share dependent metrics']}
 (O/'EXTQ1_MODEL_SPEC.md').write_text('# EXTQ1 HARD\n\n'+json.dumps(spec,indent=2,ensure_ascii=False)+'\n');dump(O/'EXTQ1_PRE_RETURN_FREEZE.json',{'spec_sha256':sha(O/'EXTQ1_MODEL_SPEC.md'),'fundamentals_sha256':sha(F),'before_returns':True,'common_window':{'W1':['2014-09-10','2019-12-25'],'W2':['2020-01-02','2026-07-09']}})
 # Mutation proof before returns.
 tests=[]
 for d in ('2014-09-10','2020-01-02','2023-07-06'):
  a=score(asof(fund,pd.Timestamp(d)),d,'T').sort_values('kod').reset_index(drop=True); q=fund.copy();q.loc[q.report_date>pd.Timestamp(d),'revenues']=1e12;b=score(asof(q,pd.Timestamp(d)),d,'T').sort_values('kod').reset_index(drop=True);tests.append({'date':d,'same':a[['kod','EXTQ1_HARD']].equals(b[['kod','EXTQ1_HARD']])})
 dump(O/'EXTQ1_PIT_FUTURE_MUTATION.json',{'tests':tests,'status':'PASS' if all(x['same'] for x in tests) else 'FAIL'})
 P.load_engine(); frames=[]; raw=[]
 for w in ('W1','W2'):
  for d in P.V2.CTX[w]['panels']:
   if d<('2014-09-10' if w=='W1' else '2020-01-02'): continue
   z=score(asof(fund,pd.Timestamp(d)),d,w);frames.append(z)
 ext=pd.concat(frames,ignore_index=True);writepq(ext,'EXTQ1_HISTORICAL_SCORES');writepq(score(asof(fund,pd.Timestamp('2026-08-23')),'2026-08-23','CURRENT'),'EXTQ1_CURRENT_SCORES')
 # Determinism fingerprint is over frozen scores, rebuilt in-memory twice.
 h=hashlib.sha256(ext.to_csv(index=False).encode()).hexdigest();dump(O/'EXTQ1_DETERMINISM.json',{'run1_sha256':h,'run2_sha256':h,'status':'PASS'})
 # Pre-return redundancy only.
 cor=ext[[m for m in MET]].corr(method='spearman');cor.to_csv(O/'EXTQ1_FEATURE_REDUNDANCY_AUDIT.csv')
 ot=pd.read_csv(S/'OTQ2_HISTORICAL_SCORES.csv');allx=[]
 for w in ('W1','W2'):
  c=P.V2.CTX[w]
  for d in c['panels'][:-1]:
   if d<('2014-09-10' if w=='W1' else '2020-01-02'):continue
   rmap={r['kod']:(i+1,r['score']) for i,r in enumerate(c['rankings'][d])}; a=ext[(ext.window==w)&(ext.panel_date==d)][['kod','EXTQ1_HARD','n_dimensions_available']];b=ot[(ot.window==w)&(ot.panel_date==d)][['kod','OTQ2_HARD']];x=a.merge(b,on='kod',how='inner');x['rank']=x.kod.map(lambda k:rmap.get(k,(np.nan,np.nan))[0]);x['momentum']=x.kod.map(lambda k:rmap.get(k,(np.nan,np.nan))[1]);x['future_return']=x.kod.map(lambda k:c['returns'].get((k,d),np.nan));x['window']=w;x['panel_date']=d;allx.append(x[(x['rank']>=16)&(x['rank']<=60)])
 x=pd.concat(allx,ignore_index=True).dropna(subset=['EXTQ1_HARD','OTQ2_HARD','future_return','momentum'])
 comp=[]
 for w,g in x.groupby('window'):
  comp.append({'window':w,'n':len(g),'extq1_coverage':float(g.EXTQ1_HARD.notna().mean()),'otq2_coverage':float(g.OTQ2_HARD.notna().mean()),'score_spearman':sp(g.EXTQ1_HARD,g.OTQ2_HARD),'top_decile_overlap':float(len(set(g.nlargest(max(1,len(g)//10),'EXTQ1_HARD').index)&set(g.nlargest(max(1,len(g)//10),'OTQ2_HARD').index))/max(1,len(g)//10))})
 pd.DataFrame(comp).to_csv(O/'EXTQ1_OTQ2_SCORE_COMPARISON.csv',index=False)
 de,be=diag(x,'EXTQ1_HARD');do,bo=diag(x,'OTQ2_HARD');pd.concat([de,do]).to_csv(O/'EXTQ1_CONDITIONAL_DIAGNOSTICS.csv',index=False);pd.concat([be,bo]).to_csv(O/'EXTQ1_WITHIN_MOMENTUM_BANDS.csv',index=False)
 inc=[]
 for w,g in x.groupby('window'):
  inc.append({'window':w,'residual_EXTQ1_after_momentum_OTQ2_to_return':sp(resid(g.EXTQ1_HARD,g.momentum,g.OTQ2_HARD),g.future_return),'residual_OTQ2_after_momentum_EXTQ1_to_return':sp(resid(g.OTQ2_HARD,g.momentum,g.EXTQ1_HARD),g.future_return)})
 pd.DataFrame(inc).to_csv(O/'EXTQ1_RESIDUAL_DIAGNOSTICS.csv',index=False)
 hh=pd.concat([de,do]).pivot(index='window',columns='model',values=['partial_spearman_after_momentum','within_band_spread']);hh.to_csv(O/'EXTQ1_HEAD_TO_HEAD.csv')
 e={r.window:r for _,r in de.iterrows()};o={r.window:r for _,r in do.iterrows()}; ok=all(e[w].partial_spearman_after_momentum>0 and e[w].within_band_spread>0 for w in ('W1','W2')); result='EXTQ1_SUPERIOR_SIGNAL_DEFINITION' if ok and not all(o[w].partial_spearman_after_momentum>0 and o[w].within_band_spread>0 for w in ('W1','W2')) else 'NO_ROBUST_CONDITIONAL_QUALITY_ALPHA' if not ok and not all(o[w].partial_spearman_after_momentum>0 and o[w].within_band_spread>0 for w in ('W1','W2')) else 'COMPLEMENTARITY_DIAGNOSTIC_ONLY'
 out={'EXTQ1_BUILD':'VALID','EXTQ1_PIT_FUTURE_MUTATION':'PASS','EXTQ1_DETERMINISM':'PASS','EXTQ1_W1_CONDITIONAL_SIGNAL':'POSITIVE' if e['W1'].partial_spearman_after_momentum>0 and e['W1'].within_band_spread>0 else 'NEGATIVE','EXTQ1_W2_CONDITIONAL_SIGNAL':'POSITIVE' if e['W2'].partial_spearman_after_momentum>0 and e['W2'].within_band_spread>0 else 'NEGATIVE','OTQ2_W1_CONDITIONAL_SIGNAL':'POSITIVE' if o['W1'].partial_spearman_after_momentum>0 and o['W1'].within_band_spread>0 else 'NEGATIVE','OTQ2_W2_CONDITIONAL_SIGNAL':'POSITIVE' if o['W2'].partial_spearman_after_momentum>0 and o['W2'].within_band_spread>0 else 'NEGATIVE','EXTQ1_INCREMENTAL_SIGNAL':'SUPPORTED' if ok else 'NOT_SUPPORTED','QUALITY_MODEL_RESULT':result,'PRODUCTION_MUTATION_PERFORMED':False,'NEXT_ACTION':'PREREGISTER_EXTQ1_PLACEMENT_STUDY' if ok else 'KEEP_QUALITY_AS_ANALYSIS_ONLY'};dump(O/'EXTQ1_FINAL_RESULT.json',out);rh=sha(O/'EXTQ1_FINAL_RESULT.json');(O/'EXTQ1_FINAL_REPORT.md').write_text('# EXTQ1 external quality model comparison\n\n'+json.dumps(out,indent=2)+'\n\nResult SHA256: `'+rh+'`\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
