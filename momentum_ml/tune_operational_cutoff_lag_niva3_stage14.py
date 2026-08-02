"""N3 stage 14 / SR51: operational information cutoff lag at annual rotation.

The corrected Stage-12 score/weight panel is fixed.  At each execution week,
the portfolio receives the panel that was observable 0/1/2/4 weeks earlier.
All arms use the same common execution window and no lag is selected.
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
from tune_100k_implementability_niva3_stage13 import reconstructed_prices

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/13_100k_implementability.json'
SOURCE=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_operational_cutoff_lag.json'
CSV=ROOT/'results/niva3_operational_cutoff_lag_arms.csv'
MEMBERS=ROOT/'results/niva3_operational_cutoff_lag_members.csv'
LAGS=(0,1,2,4)

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def shifted(base,dates,exec_dates,lag):
    pieces=[]; pos={d:i for i,d in enumerate(dates)}
    for d in exec_dates:
        source=dates[pos[d]-lag]; x=base.loc[[source]].copy(); x.index=pd.DatetimeIndex([d]*len(x),name='Date'); pieces.append(x)
    return pd.concat(pieces).sort_index()

def metrics(frame):
    v=frame.portfolio_value.astype(float); r=v.pct_change().dropna(); years=(v.index[-1]-v.index[0]).days/365.25
    return {'cagr':float((v.iloc[-1]/v.iloc[0])**(1/years)-1),'sharpe':float(r.mean()/r.std(ddof=1)*np.sqrt(52)),
            'max_drawdown':float((v/v.cummax()-1).min())}

def members(sig,rotation_dates):
    return {d:set(sig.loc[[d]].loc[lambda x:x.pred_signal.eq(1),'ticker']) for d in rotation_dates}

def jac(a,b):
    vals=[]
    for d in a:
        u=a[d]|b[d]; vals.append(len(a[d]&b[d])/len(u) if u else 1.0)
    return float(np.median(vals)),float(np.min(vals))

def main():
    parent=verify_manifest(PARENT); base=pd.read_csv(SOURCE,parse_dates=['Date']).set_index('Date').sort_index(); prices=reconstructed_prices()
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']); config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    dates=base.index.unique().sort_values(); exec_dates=dates[52:]; rotation_dates=exec_dates[::52]; config.REBALANCE_WEEKS=52
    bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(exec_dates).ffill().dropna(); byears=(bench.index[-1]-bench.index[0]).days/365.25; bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/byears)-1)
    rows=[]; memberships={}; member_rows=[]
    for lag in LAGS:
        sig=shifted(base,dates,exec_dates,lag); bt=NoCorrelationBacktester(sig,prices); frame=bt.run(); met=metrics(frame); memberships[lag]=members(sig,rotation_dates)
        for d,nameset in memberships[lag].items():
            for ticker in sorted(nameset): member_rows.append({'lag_weeks':lag,'rotation_date':d,'ticker':ticker})
        rows.append({'lag_weeks':lag,**met,'benchmark_cagr':bcagr,'alpha_cagr':met['cagr']-bcagr})
        print(lag,rows[-1],flush=True)
    for row in rows:
        med,worst=jac(memberships[0],memberships[row['lag_weeks']]); row['median_rotation_jaccard_vs_lag0']=med; row['worst_rotation_jaccard_vs_lag0']=worst
    table=pd.DataFrame(rows); table.to_csv(CSV,index=False); pd.DataFrame(member_rows).to_csv(MEMBERS,index=False)
    spread=float(table.cagr.max()-table.cagr.min()); worst_alpha=float(table.alpha_cagr.min()); worst_med=float(table.median_rotation_jaccard_vs_lag0.min())
    gate=spread<=.03 and worst_alpha>0 and worst_med>=.60
    report={'status':'PASS','test':'N3-SR51','parent_stage':parent['manifest_sha256'],'lags_weeks':list(LAGS),'common_window':{'start':str(exec_dates[0].date()),'end':str(exec_dates[-1].date()),'weeks':len(exec_dates)-1,'rotations':len(rotation_dates)},'benchmark_cagr':bcagr,'cagr_spread':spread,'worst_alpha_cagr':worst_alpha,'worst_median_rotation_jaccard':worst_med,'operational_cutoff_gate':'PASS' if gate else 'FAIL','decision_rule':'CAGR spread <=3pp; every lag positive index alpha; every lag median rotation Jaccard vs lag0 >=0.60','lag_selection_allowed':False,'retrained':False,'holdout_used':False,'production':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('14_operational_cutoff_lag',[OUT,CSV,MEMBERS,Path(__file__).resolve()],{'test':'N3-SR51','operational_cutoff_gate':report['operational_cutoff_gate'],'selection':False,'production':False},parent=PARENT)
    print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
