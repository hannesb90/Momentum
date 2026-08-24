"""Coverage-first OTQ2 HARD builder; no return is read or used by this tool."""
from __future__ import annotations
import hashlib, json, os, sys
from datetime import UTC, datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import h0_v3_production as PROD
OUT=Path(os.environ.get('OTQ2_OUTPUT_DIR', str(ROOT/'research_k/h0_v3_otq2_coverage_first_quality_model')))
R12=ROOT/'validated/fundamentals/fundamentals_r12_validated.json'
CHECKPOINT=ROOT/'research_k/h0_v3_canonical_production_implementation/PRODUCTION_CHECKPOINT_FINALIZATION.json'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def ratio(a,b): return a/b if pd.notna(a) and pd.notna(b) and b!=0 else np.nan
def pct(s,ascending=True):
    """Cross-sectional 1/99 winsorization fixed before any return is read."""
    if not s.notna().any(): return s
    lo,hi=s.quantile(.01),s.quantile(.99)
    return s.clip(lo,hi).rank(pct=True,ascending=ascending)

METRICS={
 'operating_margin':('PROFITABILITY','operating_Income / revenues',True),
 'fcf_margin':('PROFITABILITY','free_Cash_Flow / revenues',True),
 'revenue_growth_yoy':('GROWTH_AND_SCALABILITY','sign-safe (revenue_t - revenue_t-1) / max(abs(revenue_t-1), 1)',True),
 'margin_improvement':('GROWTH_AND_SCALABILITY','operating_margin_t - operating_margin_t-1',True),
 'equity_ratio':('BALANCE_SHEET','total_Equity / total_Assets',True),
 'net_debt_to_revenue':('BALANCE_SHEET','-net_Debt / abs(revenues)',True),
 'cfo_profit_conversion':('CASH_AND_CAPITAL_DISCIPLINE','cash_Flow_From_Operating_Activities / profit_To_Equity_Holders, only positive profit',True),
 'fcf_cfo_conversion':('CASH_AND_CAPITAL_DISCIPLINE','free_Cash_Flow / abs(cash_Flow_From_Operating_Activities)',True),
 'valuation':('VALUATION','market-cap/EV dependent; intentionally UNKNOWN in historical core',False),
}

def write_parquet(df,path):
    try:
        df.to_parquet(path,index=False)
        return 'PARQUET'
    except ImportError:
        csv_path=path.with_suffix('.csv')
        df.to_csv(csv_path,index=False)
        path.with_suffix(path.suffix+'.NOT_CREATED').write_text(
            f'Parquet engine unavailable in the execution environment. Identical rows written to {csv_path.name}; no non-Parquet bytes were written under this filename.\n')
        return 'CSV_FALLBACK'

def latest_asof(fund,date):
    x=fund[fund.report_date<=date].sort_values(['kod','report_date']).groupby('kod',as_index=False).tail(1).copy()
    prev=fund[fund.report_date<=date-pd.Timedelta(days=300)].sort_values(['kod','report_date']).groupby('kod',as_index=False).tail(1)
    prev=prev.set_index('kod')
    x['operating_margin']=x.apply(lambda r:ratio(r.operating_Income,r.revenues),axis=1)
    x['fcf_margin']=x.apply(lambda r:ratio(r.free_Cash_Flow,r.revenues),axis=1)
    x['equity_ratio']=x.apply(lambda r:ratio(r.total_Equity,r.total_Assets),axis=1)
    x['net_debt_to_revenue']=x.apply(lambda r: -ratio(r.net_Debt,abs(r.revenues) if pd.notna(r.revenues) else np.nan),axis=1)
    x['cfo_profit_conversion']=x.apply(lambda r:ratio(r.cash_Flow_From_Operating_Activities,r.profit_To_Equity_Holders) if pd.notna(r.profit_To_Equity_Holders) and r.profit_To_Equity_Holders>0 else np.nan,axis=1)
    x['fcf_cfo_conversion']=x.apply(lambda r:ratio(r.free_Cash_Flow,abs(r.cash_Flow_From_Operating_Activities) if pd.notna(r.cash_Flow_From_Operating_Activities) else np.nan),axis=1)
    x['revenue_growth_yoy']=[ratio(r.revenues-prev.loc[r.kod,'revenues'],max(abs(prev.loc[r.kod,'revenues']),1)) if r.kod in prev.index and pd.notna(prev.loc[r.kod,'revenues']) else np.nan for _,r in x.iterrows()]
    x['margin_improvement']=[r.operating_margin-ratio(prev.loc[r.kod,'operating_Income'],prev.loc[r.kod,'revenues']) if r.kod in prev.index else np.nan for _,r in x.iterrows()]
    return x

def score_frame(x,date,window):
    out=x[['kod','report_date']+[m for m in METRICS if m!='valuation']].copy()
    out['panel_date']=date; out['window']=window
    out['VALUATION']=np.nan
    dims={}
    for metric,(dim,_,valid) in METRICS.items():
        if valid: out[metric+'_pct']=pct(out[metric]); dims.setdefault(dim,[]).append(metric+'_pct')
    for dim,cols in dims.items(): out[dim]=out[cols].mean(axis=1,skipna=True); out[dim+'_n']=out[cols].notna().sum(axis=1)
    dcols=list(dims)
    out['n_dimensions_available']=out[dcols].notna().sum(axis=1)
    out['OTQ2_HARD']=out[dcols].mean(axis=1,skipna=True).where(out.n_dimensions_available>=3)
    out['coverage_fraction']=out.n_dimensions_available/5
    out['confidence']=pd.cut(out.coverage_fraction,[-.01,.59,.79,1.01],labels=['LOW','MEDIUM','HIGH']).astype(str)
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cp=json.loads(CHECKPOINT.read_text()); assert cp['all_gates_pass']
    fund=pd.DataFrame(json.loads(R12.read_text())); fund['report_date']=pd.to_datetime(fund.report_date)
    # Currency-invariant ratios deliberately do not use currency_ratio; share/market-cap dependent fields are excluded.
    provenance=[]
    for m,(dim,formula,usable) in METRICS.items():
        provenance.append({'metric_name':m,'quality_dimension':dim,'current_source':str(R12) if usable else None,'historical_source':str(R12) if usable else None,'producer_script':'tools/build_validated_fundamentals_final.py','source_hash':sha(R12) if usable else None,'field_name':formula,'unit':'ratio/percentile' if usable else 'UNKNOWN','currency_semantics':'currency-invariant numerator/denominator ratio; no currency conversion' if usable else 'market cap/EV unavailable','PIT_status':'PIT_VALID' if usable else 'UNKNOWN','status':'AVAILABLE_WITH_LIMITATION' if usable else 'UNKNOWN','known_limitations':'report_date validation R1-R5; delisted coverage incomplete' if usable else 'no defensible PIT market cap/EV in all windows'})
    (OUT/'OTQ2_METRIC_PROVENANCE.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    spec={'study':'H0_V3_OTQ2_COVERAGE_FIRST_QUALITY_MODEL','version':'1.0','economic_returns_read':False,'minimum_dimensions':3,'dimensions':['PROFITABILITY','GROWTH_AND_SCALABILITY','BALANCE_SHEET','CASH_AND_CAPITAL_DISCIPLINE','VALUATION'],'metrics':METRICS,'ranking':'cross-sectional percentile; equal weighted available metrics per dimension and equal weighted available dimensions','outliers':'winsorize each raw metric cross-section at 1st/99th percentile before percentile ranking','unknown':'missing/unsupported metric remains UNKNOWN; no imputation','historical_primary':'currency-invariant report-date-aligned metrics only; valuation/share-dependent metrics UNKNOWN','overlay_rule':'if separately justified after diagnostics: momentum + 0.05*(2*OTQ2_HARD-1); UNKNOWN adjustment 0'}
    (OUT/'OTQ2_MODEL_SPEC.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    (OUT/'OTQ2_MODEL_FREEZE.json').write_text(json.dumps({'model_spec_sha256':sha(OUT/'OTQ2_MODEL_SPEC.json'),'input_sha256':sha(R12),'frozen_utc':datetime.now(UTC).isoformat(),'before_return_access':True},indent=2)+'\n')
    # Current: the most recent report per company, no qualitative score fabricated.
    current=latest_asof(fund,pd.Timestamp('2026-08-23')); cur=score_frame(current,'2026-08-23','CURRENT'); cur['OTQ2_QUAL']='UNKNOWN'
    write_parquet(cur,OUT/'OTQ2_CURRENT_SCORES.parquet')
    cards=[]
    for _,r in cur.sort_values('OTQ2_HARD',ascending=False).iterrows(): cards.append({'ticker':r.kod,'hard_score':None if pd.isna(r.OTQ2_HARD) else float(r.OTQ2_HARD),'dimensions':{d:(None if pd.isna(r[d]) else float(r[d])) for d in spec['dimensions']},'coverage_fraction':float(r.coverage_fraction),'confidence':r.confidence,'qualitative_layer':'UNKNOWN_NOT_GENERATED_NO_SOURCED_TEXT_SNAPSHOT'})
    (OUT/'OTQ2_CURRENT_CARDS.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n')
    # Historical score matrix: no returns accessed.
    PROD.load_engine(); frames=[]; coverage=[]
    for w in ('W1','W2'):
        for p in PROD.V2.CTX[w]['panels']:
            x=score_frame(latest_asof(fund,pd.Timestamp(p)),p,w); frames.append(x)
            coverage.append({'window':w,'panel_date':p,'n_scored':int(x.OTQ2_HARD.notna().sum()),'n_total_reports':len(x),'coverage':float(x.OTQ2_HARD.notna().mean()) if len(x) else 0.0})
    hist=pd.concat(frames,ignore_index=True); write_parquet(hist,OUT/'OTQ2_HISTORICAL_FEATURE_MATRIX.parquet'); write_parquet(hist,OUT/'OTQ2_HISTORICAL_SCORES.parquet')
    pd.DataFrame(coverage).to_csv(OUT/'OTQ2_HISTORICAL_SOURCE_COVERAGE.csv',index=False)
    pd.DataFrame([{'source':'validated/fundamentals/r12','codes':fund.kod.nunique(),'latest_report_date':str(fund.report_date.max().date()),'current_hard_scores':int(cur.OTQ2_HARD.notna().sum()),'current_coverage':float(cur.OTQ2_HARD.notna().mean())}]).to_csv(OUT/'OTQ2_CURRENT_SOURCE_COVERAGE.csv',index=False)
    pit={'historical_future_mutation':'NOT_YET_RUN','earliest_otq2_historical_date':str(hist.panel_date.min()),'w1_mean_coverage':float(pd.DataFrame(coverage).query("window=='W1'").coverage.mean()),'w2_mean_coverage':float(pd.DataFrame(coverage).query("window=='W2'").coverage.mean()),'note':'No return data read; next stage is frozen conditional diagnostics.'}
    (OUT/'OTQ2_HISTORICAL_PIT_AUDIT.json').write_text(json.dumps(pit,indent=2)+'\n')
    (OUT/'OTQ2_SURVIVORSHIP_IMPACT.json').write_text(json.dumps({'status':'LIMITED_PENDING_CANONICAL_UNIVERSE_INTERSECTION','known_missing_delisted_fundamentals':67,'effect':'does not invalidate currency-invariant metric scores for rows with reports; requires intersection measurement before economic inference'},indent=2)+'\n')
    print(json.dumps({'current_scores':int(cur.OTQ2_HARD.notna().sum()),'historical_rows':len(hist),'w1w2_panels':len(coverage),'score_csv_sha256':sha(OUT/'OTQ2_HISTORICAL_SCORES.csv'),'model_freeze':sha(OUT/'OTQ2_MODEL_FREEZE.json')},indent=2))
if __name__=='__main__': main()
