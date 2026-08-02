"""N3 stage 23 / corrected SR1: 13v-target anchor plus conditional 52v ranker.

Stage 22 proved that the frozen architecture uses a 13-week target and a
52-week execution cadence.  This test therefore reverses the stale SR1 label:
the separately trained 52-week target ranker is the overlay, never the anchor.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large, validate_large_contract
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS, add_cross_sectional, attach_categorical_features
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from
from tune_reconstructed_prices_niva3_stage11 import pct
from tune_abstention_gate import _load_state

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/22_sr1_anchor_contract.json'
BASE_SIG=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
RAW52=ROOT/'results/niva3_sr1_raw52.csv'
OUT=ROOT/'results/niva3_sr1_corrected_overlay.json'
ARMS=ROOT/'results/niva3_sr1_corrected_overlay_arms.csv'
MEMBERS=ROOT/'results/niva3_sr1_corrected_overlay_members.csv'

class BT(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def metrics(sig,prices):
    bt=BT(sig,prices); bt.run(); s=bt.statistics()
    return {**s,'cagr_numeric':pct(s['CAGR'])}

def member_map(sig): return {d:set(g.loc[g.pred_signal.eq(1),'ticker']) for d,g in sig.groupby(level=0)}
def stability(a,b):
    vals=[]
    for d in a:
        u=a[d]|b[d]; vals.append(len(a[d]&b[d])/len(u) if u else 1.)
    return {'median_top15_jaccard':float(np.median(vals)),'p10_top15_jaccard':float(np.quantile(vals,.1))}

def main():
    parent=verify_manifest(PARENT); features,prices,state=reconstructed_state()
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap'])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    features=attach_categorical_features(add_cross_sectional(features),sectors,caps)
    cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS); validate_large_contract(cols)
    frozen_features,frozen_prices,_,_=_load_state(); frozen_panel=panel_from(frozen_features,frozen_prices)
    dates=frozen_panel.index.unique().sort_values(); purge=dates[-(config.HOLDOUT_WEEKS+52)]; allowed=dates[dates<purge]
    panel=panel_from(features,prices); panel=panel[panel.index.isin(allowed)].sort_index()
    frozen_dev=frozen_panel[frozen_panel.index.isin(allowed)].sort_index(); splits=walk_forward_splits(frozen_dev.index,embargo_weeks=52)
    if RAW52.exists():
        raw52=pd.read_csv(RAW52,parse_dates=['Date']).set_index('Date').sort_index()
    else:
        pieces=[]; _set_seed(42)
        for i,(tr,va,te) in enumerate(splits):
            d=panel.copy(); d['target_return']=d.ret52; d['target_signal']=d.sig52
            train=d[d.index.isin(tr)].sort_index(); val=d[d.index.isin(va)].sort_index(); test=d[d.index.isin(te)].sort_index()
            model=_train_lambdarank(train,val,cols); p=test[['ticker']].copy(); p['raw']=model.predict(test[cols].fillna(0).values); pieces.append(p)
            print(f'52v overlay split {i+1}/{len(splits)}',flush=True)
        raw52=pd.concat(pieces).sort_index(); raw52.to_csv(RAW52)
    base=pd.read_csv(BASE_SIG,parse_dates=['Date']).set_index('Date').sort_index()
    base=base[['ticker','prob_raw']].rename(columns={'prob_raw':'raw13'})
    joined=base.reset_index().merge(raw52.reset_index(),on=['Date','ticker'],how='inner').set_index('Date').sort_index()
    actual=joined.index.unique().sort_values()
    expected=pd.DatetimeIndex(pd.read_csv(BASE_SIG,parse_dates=['Date']).Date.drop_duplicates().sort_values())
    if not actual.equals(expected): raise RuntimeError('13v/52v exact OOF-date parity failed')
    joined['r13']=joined.groupby(level=0).raw13.rank(pct=True); joined['r52']=joined.groupby(level=0).raw.rank(pct=True)
    joined['delta13']=joined.groupby('ticker').r13.diff()
    scores={'baseline_13_target':joined.r13,
            'agreement_80_20':joined.r13.where(((joined.r13-.5)*(joined.r52-.5)<=0),.8*joined.r13+.2*joined.r52),
            'positive_13_rank_acceleration_80_20':joined.r13.where(joined.delta13.le(0)|joined.delta13.isna(),.8*joined.r13+.2*joined.r52),
            'top_13_quintile_52_tiebreak':joined.r13.where(joined.r13.lt(.8),1+joined.r52)}
    fdfs={t:f.assign(ticker=t) for t,f in features.items()}; config.REBALANCE_WEEKS=52; config.SIZING_MODE='inverse_vol'; config.CONVICTION_BLEND=.75
    rows=[]; signals={}; baseline_members=None
    bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(expected).ffill().dropna(); years=(bench.index[-1]-bench.index[0]).days/365.25; bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/years)-1)
    for arm,score in scores.items():
        raw=joined[['ticker']].copy(); raw['raw']=score
        sig=build_full_output(raw_preds(raw),None,fdfs,MomentumEnsemble(),record_diagnostics=False); signals[arm]=sig
        met=metrics(sig,prices); mem=member_map(sig)
        if arm=='baseline_13_target':
            expected_met=json.loads((ROOT/'results/niva3_reconstructed_price_retrain_corrected.json').read_text())['reconstructed_metrics']
            for k in ('CAGR','Sharpe','Max Drawdown'):
                if met[k]!=expected_met[k]: raise RuntimeError(f'Baseline parity failed {k}: {met[k]} != {expected_met[k]}')
            baseline_members=mem; stab={'median_top15_jaccard':1.,'p10_top15_jaccard':1.}
        else: stab=stability(baseline_members,mem)
        rows.append({'arm':arm,**met,'alpha_cagr':met['cagr_numeric']-bcagr,**stab}); print(arm,rows[-1],flush=True)
    table=pd.DataFrame(rows); table.to_csv(ARMS,index=False)
    mr=[]
    for arm,sig in signals.items():
        for d,g in sig[sig.pred_signal.eq(1)].groupby(level=0):
            for t in g.ticker: mr.append({'arm':arm,'date':d,'ticker':t})
    pd.DataFrame(mr).to_csv(MEMBERS,index=False)
    b=table.iloc[0]; ch=table.iloc[1:]
    eligible=ch[(ch.alpha_cagr>0)&(ch.cagr_numeric>b.cagr_numeric)&(ch.median_top15_jaccard>=.60)]
    report={'status':'PASS','test':'N3-SR1-corrected','parent_stage':parent['manifest_sha256'],
            'anchor_target_weeks':13,'overlay_target_weeks':52,'execution_rotation_weeks':52,
            'oof_window':{'start':str(expected[0].date()),'end':str(expected[-1].date()),'weeks':len(expected)-1},
            'splits':len(splits),'benchmark_cagr':bcagr,'baseline_parity':'EXACT_ROUNDED',
            'arms':len(table),'eligible_challengers':eligible.arm.tolist(),
            'family_gate':'PASS' if len(eligible) else 'FAIL',
            'decision_rule':'each arm separately: positive ETF alpha, CAGR strictly above anchor, median top15 Jaccard >=0.60; no family averaging',
            'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('23_sr1_corrected_overlay',[OUT,ARMS,MEMBERS,RAW52,Path(__file__).resolve()],
                       {'test':'N3-SR1-corrected','family_gate':report['family_gate'],'eligible_challengers':report['eligible_challengers'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False)); print(stage)

if __name__=='__main__': main()
