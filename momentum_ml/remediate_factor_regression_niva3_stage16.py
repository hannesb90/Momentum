"""N3 stage 16: repair SR52 partial factor regression.

Stage 15's generic quintile helper cannot form tails from a binary Large/Mid
indicator, yielding zero common observations.  This remediation builds the
size proxy directly as Mid-minus-Large and refuses regressions with <100 rows.
The full PIT factor gate remains fail-closed regardless of partial estimates.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_100k_implementability_niva3_stage13 import reconstructed_prices
from analyze_temporal_factor_niva3_stage15 import ols

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/15_temporal_factor_attribution.json'
FACT_IN=ROOT/'results/niva3_factor_returns.csv'
OUT=ROOT/'results/niva3_factor_regression_corrected.json'
FACT_OUT=ROOT/'results/niva3_factor_returns_corrected.csv'
COEF=ROOT/'results/niva3_factor_regression_corrected.csv'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'

def main():
    parent=verify_manifest(PARENT); old=json.loads((ROOT/'results/niva3_temporal_factor_attribution.json').read_text())
    factors=pd.read_csv(FACT_IN,parse_dates=['date']).set_index('date'); prices=reconstructed_prices(); features,_,_,_=_load_state()
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap'])
    dates=factors.index; returns=pd.DataFrame({t:p.Close.reindex(dates).ffill().pct_change() for t,p in prices.items() if t in features})
    size=[]
    for date in dates:
        r=returns.loc[date]; mid=[t for t in r.dropna().index if caps.get(t)=='Mid Cap']; large=[t for t in r.dropna().index if caps.get(t)=='Large Cap']
        size.append(float(r.loc[mid].mean()-r.loc[large].mean()) if mid and large else float('nan'))
    factors['size_proxy_mid_minus_large']=size; factors.to_csv(FACT_OUT)
    # Recreate the corrected portfolio return from the frozen output path.
    sig=pd.read_csv(SIGNALS,parse_dates=['Date']).set_index('Date').sort_index()
    from backtest.backtester import MomentumBacktester
    class BT(MomentumBacktester):
        def _correlation_filter(self,target_weights,date): return target_weights
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names); config.REBALANCE_WEEKS=52
    frame=BT(sig,prices).run(); y=frame.portfolio_value.pct_change()
    core=factors[['market','momentum','quality','size_proxy_mid_minus_large']]
    sector_cols=sorted([c for c in factors if c.startswith('sector_')],key=lambda c:factors[c].notna().sum(),reverse=True)[:5]
    rows=ols(y,core,'market_momentum_quality_size_proxy')+ols(y,pd.concat([core,factors[sector_cols]],axis=1),'plus_top5_sector_relative')
    coef=pd.DataFrame(rows); coef.to_csv(COEF,index=False)
    intercept=coef[(coef.model=='plus_top5_sector_relative')&(coef.term=='intercept')].iloc[0]
    if int(intercept.observations)<100: raise RuntimeError(f'Partial factor regression still underidentified: {intercept.observations}')
    report={'status':'PASS','test':'N3-SR52-factor-regression-remediation','parent_stage':parent['manifest_sha256'],'invalidates_stage15_partial_regression':'binary size proxy produced zero tail observations','temporal_gate':old['temporal']['temporal_gate'],'regression_observations':int(intercept.observations),'partial_annualized_intercept':float(intercept.coef_annualized),'partial_intercept_t_stat':float(intercept.t_stat),'factor_coverage':old['factor_coverage'],'full_factor_attribution_identified':False,'factor_attribution_gate':'FAIL','overall_sr52_gate':'FAIL','reason':'PIT value unavailable; size and sector are current/static proxies, so partial intercept is diagnostic only','production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('16_factor_regression_remediation',[OUT,FACT_OUT,COEF,Path(__file__).resolve()],{'test':'N3-SR52-remediation','temporal_gate':report['temporal_gate'],'factor_attribution_gate':'FAIL','overall_gate':'FAIL','production':False},parent=PARENT)
    print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
