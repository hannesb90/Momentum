"""N3 stage 11: isolated retrain on reconstructed fallback price histories.

Six vendor-conflict jumps are backward-spliced to the frozen reference return.
SAVE is restarted at its 2020 re-listing because the old issuer was acquired,
delisted and squeezed out.  Technical/cross-sectional features and targets are
then rebuilt before the unchanged seed42 OOF training protocol.  Production
caches and models are never mutated.
"""
from __future__ import annotations
import glob, json
from pathlib import Path
import numpy as np
import pandas as pd

import config
from altdata import borsdata
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

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/10_fallback_instrument_audit.json'
EVENTS=ROOT/'results/niva3_fallback_instrument_events.csv'
OUT=ROOT/'results/niva3_reconstructed_price_retrain.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals.csv'
PATCHES=ROOT/'results/niva3_reconstructed_price_patches.csv'
IDS={"INTRUM.ST":112,"KEOC.ST":1354,"LAGR-B.ST":124,"MTG-B.ST":148,"SAGA-A.ST":194,
     "SAVE.ST":161,"SBB-B.ST":438,"TRUE-B.ST":2275,"VISC.ST":312,"VPLAY-B.ST":1794}

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def cached_dividends():
    values={}
    for path in glob.glob(str(ROOT/'momentum_ml/cache/borsdata/dividend_calendar_*.json')):
        try: payload=json.loads(Path(path).read_text())
        except Exception: continue
        for item in payload.get('list',[]):
            iid=item.get('insId')
            for row in item.get('values',[]):
                d=pd.to_datetime(row.get('excludingDate'),errors='coerce'); a=pd.to_numeric(row.get('amountPaid'),errors='coerce')
                if iid and pd.notna(d) and pd.notna(a) and a>0: values.setdefault(int(iid),[]).append((d.normalize(),float(a)))
    return {i:(pd.DataFrame(v,columns=['ex_date','amount']).drop_duplicates().groupby('ex_date',as_index=False).amount.sum()) for i,v in values.items()}

def weekly(iid,divs,splits):
    d=borsdata.stockprices_ohlcv(iid,True)
    ev=borsdata.normalize_dividends_for_splits(divs.get(iid),splits.get(iid,[]))
    d=borsdata.adjust_ohlc_for_dividends(d,ev)
    w=d.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna(subset=['Open','High','Low','Close'])
    w.index-=pd.Timedelta(days=4)
    return w

def splice(frame,date,target_return):
    date=pd.Timestamp(date); prior=frame.index[frame.index<date]
    if not len(prior) or date not in frame.index: raise RuntimeError(f'Cannot splice {date}')
    p=prior[-1]; desired_prev=float(frame.at[date,'Close'])/(1+float(target_return))
    factor=desired_prev/float(frame.at[p,'Close'])
    frame.loc[frame.index<date,['Open','High','Low','Close']]*=factor
    return factor

def pct(s): return float(str(s).replace('%',''))/100

def main():
    parent=verify_manifest(PARENT)
    audit=json.loads((ROOT/'results/niva3_fallback_instrument_audit.json').read_text())
    if audit['borsdata_reinstatement_gate']!='FAIL': raise RuntimeError('Expected failed source audit')
    features,prices,state,_=_load_state(); features={t:f.copy() for t,f in features.items()}; prices={t:p.copy() for t,p in prices.items()}
    splits=borsdata.split_events_map(json.loads((ROOT/'momentum_ml/cache/borsdata/stocksplits_from2000.json').read_text())); divs=cached_dividends()
    events=pd.read_csv(EVENTS,parse_dates=['borsdata_week','fallback_week']); conflicts=events[events.classification.eq('VENDOR_CONFLICT')]
    patch_rows=[]
    for ticker,iid in IDS.items():
        w=weekly(iid,divs,splits)
        # Research/feature contract begins at the same configured boundary.
        w=w.loc[w.index>=pd.Timestamp(config.START_DATE)].copy()
        if ticker=='SAVE.ST':
            listing=pd.Timestamp('2020-11-23'); removed=int((w.index<listing).sum()); w=w.loc[w.index>=listing].copy()
            patch_rows.append({'ticker':ticker,'week':listing.date(),'method':'restart_at_verified_relisting','factor':np.nan,'reference_return':np.nan,'rows_removed':removed})
        else:
            for row in conflicts[conflicts.ticker.eq(ticker)].itertuples():
                # Use the reference return on the identical economic week.  The
                # audit's +/-1 bar value was only for classification.
                ref=prices[ticker].Close.pct_change(); date=pd.Timestamp(row.borsdata_week)
                if date not in ref.index or pd.isna(ref.loc[date]): raise RuntimeError(f'Missing exact reference {ticker} {date}')
                factor=splice(w,date,float(ref.loc[date])); patch_rows.append({'ticker':ticker,'week':date.date(),'method':'backward_splice_exact_week_total_return','factor':factor,'reference_return':float(ref.loc[date]),'rows_removed':0})
        prices[ticker]=w
        tech=build_features(w)
        old=features[ticker]
        for col in tech.columns: old[col]=tech[col].reindex(old.index)
        features[ticker]=old
    pd.DataFrame(patch_rows).to_csv(PATCHES,index=False)

    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap'])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    features=attach_categorical_features(add_cross_sectional(features),sectors,caps)
    cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS); validate_large_contract(cols)
    base=to_model_df(features).sort_index(); base.index.name='Date'
    t13=targets_from_prices(base,prices,13).reset_index().rename(columns={'target_return':'ret13','target_signal':'sig13'})
    t52=targets_from_prices(base,prices,52).reset_index().rename(columns={'target_return':'ret52','target_signal':'sig52'})
    fb=base.drop(columns=[c for c in base if c.startswith('target_')],errors='ignore')
    panel=(fb.reset_index().merge(t13,on=['Date','ticker']).merge(t52,on=['Date','ticker']).dropna(subset=['ret13','sig13','ret52','sig52']).set_index('Date').sort_index())
    panel['target_return']=panel.ret13; panel['target_signal']=panel.sig13
    dates=panel.index.unique().sort_values(); purge=dates[-(config.HOLDOUT_WEEKS+52)]; dev=panel[panel.index<purge]
    wf=walk_forward_splits(dev.index,embargo_weeks=52); _set_seed(42); raw=[]
    for i,(tr,va,te) in enumerate(wf):
        train=dev[dev.index.isin(tr)].sort_index(); val=dev[dev.index.isin(va)].sort_index(); test=dev[dev.index.isin(te)].sort_index()
        model=_train_lambdarank(train,val,cols); piece=test[['ticker']].copy(); piece['raw']=model.predict(test[cols].fillna(0).values); raw.append(piece)
        print(f'reconstructed split {i+1}/{len(wf)}',flush=True)
    fdfs={t:f.assign(ticker=t) for t,f in features.items()}; config.REBALANCE_WEEKS=52; config.SIZING_MODE='inverse_vol'; config.CONVICTION_BLEND=.75
    sig=build_full_output(raw_preds(pd.concat(raw).sort_index()),None,fdfs,MomentumEnsemble(),record_diagnostics=False)
    bt=NoCorrelationBacktester(sig,prices); bt.run(); stats=bt.statistics(); sig.to_csv(SIGNALS)
    bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(sig.index.unique().sort_values()).ffill().dropna(); years=(bench.index[-1]-bench.index[0]).days/365.25; bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/years)-1)
    baseline=json.loads((ROOT/'results/retraining_staleness_niva2.json').read_text())['retrain_13w_parity']; cagr=pct(stats['CAGR']); delta=cagr-pct(baseline['CAGR']); alpha=cagr-bcagr
    gate=alpha>0 and delta>=-.03
    report={'status':'PASS','test':'N3-SR49-remediation-B','parent_stage':parent['manifest_sha256'],'patches':len(patch_rows),'retrained_splits':len(wf),'baseline':baseline,'reconstructed_metrics':{k:stats[k] for k in ('CAGR','Sharpe','Max Drawdown','End Capital')},'benchmark_cagr':bcagr,'alpha_cagr':alpha,'cagr_change_vs_baseline':delta,'sensitivity_gate':'PASS' if gate else 'FAIL','decision_rule':'positive index alpha and no more than 3pp CAGR loss versus frozen baseline','holdout_used':False,'production':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('11_reconstructed_price_retrain',[OUT,SIGNALS,PATCHES,Path(__file__).resolve()],{'test':'N3-SR49-remediation-B','sensitivity_gate':report['sensitivity_gate'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
