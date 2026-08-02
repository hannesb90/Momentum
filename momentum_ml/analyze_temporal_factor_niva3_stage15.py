"""N3 stage 15 / SR52: temporal and factor attribution.

Uses the corrected Stage-12 portfolio. Factor mimicking returns are causal:
characteristics at t-1 sort returns from t-1 to t.  Missing PIT value and
historical size data fail closed; partial regression is labelled diagnostic.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_100k_implementability_niva3_stage13 import reconstructed_prices

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/14_operational_cutoff_lag.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_temporal_factor_attribution.json'
TEMP=ROOT/'results/niva3_temporal_attribution.csv'
FACT=ROOT/'results/niva3_factor_returns.csv'
COEF=ROOT/'results/niva3_factor_regression.csv'

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def ann(v):
    v=v.dropna().astype(float); r=v.pct_change().dropna(); years=(v.index[-1]-v.index[0]).days/365.25
    return float((v.iloc[-1]/v.iloc[0])**(1/years)-1),float(r.mean()/r.std(ddof=1)*np.sqrt(52))

def ls_factor(values,returns,min_n=20):
    x=pd.concat([values.rename('x'),returns.rename('r')],axis=1).dropna()
    if len(x)<min_n: return np.nan,len(x)
    q=x.x.rank(pct=True); return float(x.loc[q>=.8,'r'].mean()-x.loc[q<=.2,'r'].mean()),len(x)

def ols(y,X,label):
    z=pd.concat([y.rename('y'),X],axis=1).dropna(); A=np.column_stack([np.ones(len(z)),z[X.columns].to_numpy()]); b=np.linalg.lstsq(A,z.y.to_numpy(),rcond=None)[0]; resid=z.y.to_numpy()-A@b
    dof=max(len(z)-A.shape[1],1); cov=np.linalg.pinv(A.T@A)*(resid@resid/dof); se=np.sqrt(np.diag(cov)); names=['intercept',*X.columns]
    return [{'model':label,'term':n,'coef_weekly':float(v),'coef_annualized':float(v*52),'t_stat':float(v/s) if s>0 else np.nan,'observations':len(z)} for n,v,s in zip(names,b,se)]

def main():
    parent=verify_manifest(PARENT); sig=pd.read_csv(SIGNALS,parse_dates=['Date']).set_index('Date').sort_index(); prices=reconstructed_prices(); features,_,_,_=_load_state()
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']); config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names); config.REBALANCE_WEEKS=52
    bt=NoCorrelationBacktester(sig,prices); frame=bt.run(); stats=bt.statistics()
    if stats['CAGR']!='22.2%': raise RuntimeError(f'Stage-12 portfolio parity failed: {stats}')
    dates=sig.index.unique().sort_values(); pret=frame.portfolio_value.pct_change(); market=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().pct_change()

    temporal=[]
    both=pd.concat([frame.portfolio_value.rename('p'),prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().rename('b')],axis=1).dropna()
    for year,g in both.groupby(both.index.year):
        if len(g)<13: continue
        pc,_=ann(g.p); bc,_=ann(g.b); temporal.append({'kind':'calendar_year','label':str(year),'start':g.index[0],'end':g.index[-1],'weeks':len(g)-1,'portfolio_cagr':pc,'benchmark_cagr':bc,'alpha_cagr':pc-bc})
    for w,label in ((156,'rolling_3y'),(260,'rolling_5y')):
        for end in range(w,len(both)):
            g=both.iloc[end-w:end+1]; pc,_=ann(g.p); bc,_=ann(g.b); temporal.append({'kind':label,'label':str(g.index[-1].date()),'start':g.index[0],'end':g.index[-1],'weeks':w,'portfolio_cagr':pc,'benchmark_cagr':bc,'alpha_cagr':pc-bc})
    temporal_df=pd.DataFrame(temporal); temporal_df.to_csv(TEMP,index=False)

    ret_panel=pd.DataFrame({t:p.Close.reindex(dates).ffill().pct_change() for t,p in prices.items() if t in features})
    factor_rows=[]; quality_coverage=[]
    for i,date in enumerate(dates[1:],1):
        prev=dates[i-1]; vals=[]
        for ticker,f in features.items():
            if ticker not in ret_panel or prev not in f.index: continue
            row=f.loc[prev]
            if isinstance(row,pd.DataFrame): row=row.iloc[-1]
            vals.append({'ticker':ticker,'mom':row.get('mom_12_1',np.nan),'f_score':row.get('f_score',np.nan),'roa':row.get('roa',np.nan),'fcf_margin':row.get('fcf_margin',np.nan),'cap':caps.get(ticker),'sector':sectors.get(ticker,'Unknown')})
        v=pd.DataFrame(vals).set_index('ticker'); rr=ret_panel.loc[date]
        mom,nm=ls_factor(v.mom,rr)
        qp=pd.concat([v.f_score.rank(pct=True),v.roa.rank(pct=True),v.fcf_margin.rank(pct=True)],axis=1).mean(axis=1,skipna=True); quality,nq=ls_factor(qp,rr)
        size_values=v['cap'].map({'Mid Cap':1.0,'Large Cap':0.0}); size,ns=ls_factor(size_values,rr)
        row={'date':date,'market':market.loc[date],'momentum':mom,'quality':quality,'size_proxy_mid_minus_large':size,'n_momentum':nm,'n_quality':nq,'n_size':ns}
        for sector,g in v.groupby('sector'):
            tickers=g.index.intersection(rr.dropna().index)
            if len(tickers)>=3: row['sector_'+str(sector).replace(' ','_')]=float(rr.loc[tickers].mean()-market.loc[date])
        factor_rows.append(row); quality_coverage.append(nq/max(len(v),1))
    factors=pd.DataFrame(factor_rows).set_index('date').sort_index(); factors.to_csv(FACT)
    core=factors[['market','momentum','quality','size_proxy_mid_minus_large']]
    sector_cols=[c for c in factors if c.startswith('sector_')]
    # Keep only the five most complete sector-relative series to avoid an
    # underdetermined/high-collinearity regression on 272 observations.
    sector_cols=sorted(sector_cols,key=lambda c:factors[c].notna().sum(),reverse=True)[:5]
    coeff=ols(pret,core,'market_momentum_quality_size_proxy')+ols(pret,pd.concat([core,factors[sector_cols]],axis=1),'plus_top5_sector_relative')
    pd.DataFrame(coeff).to_csv(COEF,index=False)
    full=[x for x in coeff if x['model']=='plus_top5_sector_relative' and x['term']=='intercept'][0]
    yearly=temporal_df[temporal_df.kind.eq('calendar_year')]; roll5=temporal_df[temporal_df.kind.eq('rolling_5y')]
    temporal_gate=bool(len(yearly) and (yearly.alpha_cagr>0).mean()>=.60 and (roll5.empty or roll5.alpha_cagr.min()>0))
    coverage={'market':'PIT_COMPLETE','momentum':'PIT_TECHNICAL','quality':f"PIT_PARTIAL_median_cross_section_{np.median(quality_coverage):.1%}",'size':'STATIC_CURRENT_TIER_NOT_PIT','value':'UNAVAILABLE_NO_PIT_VALUATION_FACTOR','sector':'STATIC_MAP_NOT_FULL_PIT'}
    factor_complete=False; factor_gate=False
    report={'status':'PASS','test':'N3-SR52','parent_stage':parent['manifest_sha256'],'portfolio_parity':stats,'temporal':{'calendar_years':len(yearly),'positive_alpha_year_share':float((yearly.alpha_cagr>0).mean()),'worst_calendar_year_alpha':float(yearly.alpha_cagr.min()),'rolling_3y_windows':int(temporal_df.kind.eq('rolling_3y').sum()),'worst_rolling_3y_alpha':float(temporal_df.loc[temporal_df.kind.eq('rolling_3y'),'alpha_cagr'].min()),'rolling_5y_windows':len(roll5),'worst_rolling_5y_alpha':None if roll5.empty else float(roll5.alpha_cagr.min()),'temporal_gate':'PASS' if temporal_gate else 'FAIL'},'factor_coverage':coverage,'partial_factor_regression':{'annualized_intercept':full['coef_annualized'],'intercept_t_stat':full['t_stat'],'sector_factors':sector_cols},'full_factor_attribution_identified':factor_complete,'factor_attribution_gate':'PASS' if factor_gate else 'FAIL','overall_sr52_gate':'PASS' if temporal_gate and factor_gate else 'FAIL','decision_rule':'positive alpha in >=60% calendar years and every rolling 5y window; full PIT market/sector/size/value/quality/momentum coverage; positive residual intercept','production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('15_temporal_factor_attribution',[OUT,TEMP,FACT,COEF,Path(__file__).resolve()],{'test':'N3-SR52','temporal_gate':report['temporal']['temporal_gate'],'factor_attribution_gate':report['factor_attribution_gate'],'overall_gate':report['overall_sr52_gate'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
