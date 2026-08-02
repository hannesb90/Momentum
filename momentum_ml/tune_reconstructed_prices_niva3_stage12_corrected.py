"""N3 stage 12: corrected reconstructed-price retrain on exact frozen calendar.

Stage 11 shifted the OOF window by one week after rebuilding the panel.  This
rerun derives the admissible date calendar from the untouched frozen state,
requires exact OOF-date equality with Stage-06, and gives Stage-11 zero
decision weight while preserving it as an immutable audit artifact.
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
from features.feature_engineering import FEATURE_COLS, build_features, add_cross_sectional, attach_categorical_features, to_model_df
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds, targets_from_prices
from tune_reconstructed_prices_niva3_stage11 import IDS, cached_dividends, weekly, splice, pct

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/11_reconstructed_price_retrain.json'
EVENTS=ROOT/'results/niva3_fallback_instrument_events.csv'
OUT=ROOT/'results/niva3_reconstructed_price_retrain_corrected.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
PATCHES=ROOT/'results/niva3_reconstructed_price_patches_corrected.csv'
FROZEN_SIGNALS=ROOT/'results/niva2_stage6_winner_signals.csv'

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def panel_from(features,prices):
    base=to_model_df(features).sort_index(); base.index.name='Date'
    t13=targets_from_prices(base,prices,13).reset_index().rename(columns={'target_return':'ret13','target_signal':'sig13'})
    t52=targets_from_prices(base,prices,52).reset_index().rename(columns={'target_return':'ret52','target_signal':'sig52'})
    fb=base.drop(columns=[c for c in base if c.startswith('target_')],errors='ignore')
    p=(fb.reset_index().merge(t13,on=['Date','ticker']).merge(t52,on=['Date','ticker'])
       .dropna(subset=['ret13','sig13','ret52','sig52']).set_index('Date').sort_index())
    p['target_return']=p.ret13; p['target_signal']=p.sig13
    return p

def main():
    parent=verify_manifest(PARENT)
    if parent['metadata'].get('sensitivity_gate')!='FAIL': raise RuntimeError('Expected Stage-11 diagnostic FAIL')
    frozen_features,frozen_prices,state,_=_load_state()
    # This untouched calendar is the controlling experimental variable.
    frozen_panel=panel_from(frozen_features,frozen_prices)
    frozen_dates=frozen_panel.index.unique().sort_values(); frozen_purge=frozen_dates[-(config.HOLDOUT_WEEKS+52)]
    allowed_dev_dates=frozen_dates[frozen_dates<frozen_purge]

    features={t:f.copy() for t,f in frozen_features.items()}; prices={t:p.copy() for t,p in frozen_prices.items()}
    from altdata import borsdata
    splits=borsdata.split_events_map(json.loads((ROOT/'momentum_ml/cache/borsdata/stocksplits_from2000.json').read_text())); divs=cached_dividends()
    events=pd.read_csv(EVENTS,parse_dates=['borsdata_week','fallback_week']); conflicts=events[events.classification.eq('VENDOR_CONFLICT')]
    patch_rows=[]
    for ticker,iid in IDS.items():
        w=weekly(iid,divs,splits).loc[lambda x:x.index>=pd.Timestamp(config.START_DATE)].copy()
        if ticker=='SAVE.ST':
            listing=pd.Timestamp('2020-11-23'); removed=int((w.index<listing).sum()); w=w.loc[w.index>=listing].copy()
            patch_rows.append({'ticker':ticker,'week':listing.date(),'method':'restart_at_verified_relisting','factor':np.nan,'reference_return':np.nan,'rows_removed':removed})
        else:
            for row in conflicts[conflicts.ticker.eq(ticker)].itertuples():
                ref=frozen_prices[ticker].Close.pct_change(); date=pd.Timestamp(row.borsdata_week)
                if date not in ref.index or pd.isna(ref.loc[date]): raise RuntimeError(f'Missing exact reference {ticker} {date}')
                factor=splice(w,date,float(ref.loc[date])); patch_rows.append({'ticker':ticker,'week':date.date(),'method':'backward_splice_exact_week_total_return','factor':factor,'reference_return':float(ref.loc[date]),'rows_removed':0})
        prices[ticker]=w; tech=build_features(w); old=features[ticker]
        for col in tech: old[col]=tech[col].reindex(old.index)
        features[ticker]=old
    pd.DataFrame(patch_rows).to_csv(PATCHES,index=False)
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap'])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    features=attach_categorical_features(add_cross_sectional(features),sectors,caps)
    cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS); validate_large_contract(cols)
    rebuilt=panel_from(features,prices)
    dev=rebuilt[rebuilt.index.isin(allowed_dev_dates)].sort_index()
    # Generate split boundaries from the untouched panel, never from rebuilt
    # row availability.  This preserves the exact historical OOF schedule.
    frozen_dev=frozen_panel[frozen_panel.index.isin(allowed_dev_dates)].sort_index()
    wf=walk_forward_splits(frozen_dev.index,embargo_weeks=52); _set_seed(42); raw=[]
    for i,(tr,va,te) in enumerate(wf):
        train=dev[dev.index.isin(tr)].sort_index(); val=dev[dev.index.isin(va)].sort_index(); test=dev[dev.index.isin(te)].sort_index()
        model=_train_lambdarank(train,val,cols); piece=test[['ticker']].copy(); piece['raw']=model.predict(test[cols].fillna(0).values); raw.append(piece)
        print(f'corrected reconstructed split {i+1}/{len(wf)}',flush=True)
    fdfs={t:f.assign(ticker=t) for t,f in features.items()}; config.REBALANCE_WEEKS=52; config.SIZING_MODE='inverse_vol'; config.CONVICTION_BLEND=.75
    sig=build_full_output(raw_preds(pd.concat(raw).sort_index()),None,fdfs,MomentumEnsemble(),record_diagnostics=False)
    expected=pd.read_csv(FROZEN_SIGNALS,parse_dates=['Date']).Date.drop_duplicates().sort_values().tolist()
    actual=list(sig.index.unique().sort_values())
    if actual!=expected: raise RuntimeError(f'OOF date parity failed: actual {actual[0]}..{actual[-1]} n={len(actual)} expected {expected[0]}..{expected[-1]} n={len(expected)}')
    bt=NoCorrelationBacktester(sig,prices); bt.run(); stats=bt.statistics(); sig.to_csv(SIGNALS)
    bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(pd.DatetimeIndex(expected)).ffill().dropna(); years=(bench.index[-1]-bench.index[0]).days/365.25; bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/years)-1)
    baseline=json.loads((ROOT/'results/retraining_staleness_niva2.json').read_text())['retrain_13w_parity']; cagr=pct(stats['CAGR']); delta=cagr-pct(baseline['CAGR']); alpha=cagr-bcagr; gate=alpha>0 and delta>=-.03
    report={'status':'PASS','test':'N3-SR49-remediation-B-corrected-calendar','parent_stage':parent['manifest_sha256'],'invalidates_stage11_decision_weight':'OOF calendar shifted one week','oof_date_parity':'EXACT','oof_window':{'start':str(expected[0].date()),'end':str(expected[-1].date()),'weeks':len(expected)-1},'patches':len(patch_rows),'retrained_splits':len(wf),'baseline':baseline,'reconstructed_metrics':{k:stats[k] for k in ('CAGR','Sharpe','Max Drawdown','End Capital')},'benchmark_cagr':bcagr,'alpha_cagr':alpha,'cagr_change_vs_baseline':delta,'sensitivity_gate':'PASS' if gate else 'FAIL','decision_rule':'positive index alpha and no more than 3pp CAGR loss versus frozen baseline','holdout_used':False,'production':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('12_reconstructed_price_retrain_corrected',[OUT,SIGNALS,PATCHES,Path(__file__).resolve()],{'test':'N3-SR49-remediation-B-corrected','sensitivity_gate':report['sensitivity_gate'],'stage11_decision_weight':'INVALID_CALENDAR','production':False},parent=PARENT)
    print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
