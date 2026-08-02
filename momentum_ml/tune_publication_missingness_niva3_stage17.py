"""N3 stage 17 / SR53: publication lag and technical missingness selection impact."""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large, validate_large_contract
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS, build_features, add_cross_sectional, attach_categorical_features
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds
from tune_reconstructed_prices_niva3_stage11 import IDS, cached_dividends, weekly, splice, pct
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/16_factor_regression_remediation.json'
EVENTS=ROOT/'results/niva3_fallback_instrument_events.csv'
BASE_SIG=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_publication_missingness.json'
CSV=ROOT/'results/niva3_publication_missingness_arms.csv'
MEMBERS=ROOT/'results/niva3_publication_missingness_members.csv'
FUND=['rev_growth_yoy','eps_growth_yoy','report_reaction_abn','div_growth_yoy','days_since_report','f_score','rev_growth','rev_accel','margin_delta','ni_growth','fcf_margin','roa','attention_gap','interact_report_reaction']

class BT(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def reconstructed_state():
    features,prices,state,_=_load_state(); features={t:f.copy() for t,f in features.items()}; prices={t:p.copy() for t,p in prices.items()}
    from altdata import borsdata
    splits=borsdata.split_events_map(json.loads((ROOT/'momentum_ml/cache/borsdata/stocksplits_from2000.json').read_text())); divs=cached_dividends(); events=pd.read_csv(EVENTS,parse_dates=['borsdata_week']); conflicts=events[events.classification.eq('VENDOR_CONFLICT')]
    for ticker,iid in IDS.items():
        w=weekly(iid,divs,splits).loc[lambda x:x.index>=pd.Timestamp(config.START_DATE)].copy()
        if ticker=='SAVE.ST': w=w.loc[w.index>=pd.Timestamp('2020-11-23')].copy()
        else:
            ref=prices[ticker].Close.pct_change()
            for row in conflicts[conflicts.ticker.eq(ticker)].itertuples(): splice(w,pd.Timestamp(row.borsdata_week),float(ref.loc[pd.Timestamp(row.borsdata_week)]))
        prices[ticker]=w; tech=build_features(w); old=features[ticker]
        for col in tech: old[col]=tech[col].reindex(old.index)
        features[ticker]=old
    return features,prices,state

def members(sig): return {d:set(g.loc[g.pred_signal.eq(1),'ticker']) for d,g in sig.groupby(level=0)}
def jac(a,b):
    v=[]
    for d in a:
        u=a[d]|b[d]; v.append(len(a[d]&b[d])/len(u) if u else 1.)
    return float(np.median(v)),float(np.quantile(v,.1)),float(np.min(v))

def main():
    parent=verify_manifest(PARENT); features,prices,state=reconstructed_state(); _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']); config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    features=attach_categorical_features(add_cross_sectional(features),sectors,caps); cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS); validate_large_contract(cols)
    frozen_features,frozen_prices,_,_=_load_state(); frozen_panel=panel_from(frozen_features,frozen_prices); fd=frozen_panel.index.unique().sort_values(); purge=fd[-(config.HOLDOUT_WEEKS+52)]; allowed=fd[fd<purge]; frozen_dev=frozen_panel[frozen_panel.index.isin(allowed)]
    base_panel=panel_from(features,prices); base_panel=base_panel[base_panel.index.isin(allowed)].sort_index(); splits=walk_forward_splits(frozen_dev.index,embargo_weeks=52)
    technical=[c for c in cols if c not in FUND and c not in ('sector_code','cap_tier_code')]
    arms={'baseline':base_panel.copy()}
    lag_features={}
    for t,f in features.items():
        x=f.copy(); present=[c for c in FUND if c in x]
        for c in present:
            shifted=x[c].shift(1)
            x[c]=(shifted+7).clip(upper=365) if c=='days_since_report' else shifted
        lag_features[t]=x
    arms['fundamental_lag_1w']=panel_from(lag_features,prices).loc[lambda x:x.index.isin(allowed)].sort_index()
    median_panel=base_panel.copy()
    for c in technical:
        median_panel[c]=median_panel[c].fillna(median_panel.groupby(level=0)[c].transform('median'))
    arms['technical_weekly_median_impute']=median_panel

    feature_dfs={t:f.assign(ticker=t) for t,f in features.items()}; config.REBALANCE_WEEKS=52; config.SIZING_MODE='inverse_vol'; config.CONVICTION_BLEND=.75; _set_seed(42)
    signals={}; rows=[]; baseline_members=None
    bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(pd.read_csv(BASE_SIG,parse_dates=['Date']).Date.drop_duplicates().sort_values()).ffill().dropna(); years=(bench.index[-1]-bench.index[0]).days/365.25; bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/years)-1)
    finalize_only=os.environ.get('SR53_FINALIZE_ONLY')=='1'
    if finalize_only:
        if not CSV.exists(): raise RuntimeError('Finalize requested but arm table is missing')
        table=pd.read_csv(CSV); rows=table.to_dict('records')
        for arm in arms:
            path=ROOT/f'results/niva3_sr53_{arm}_signals.csv'
            if not path.exists(): raise RuntimeError(f'Finalize requested but {path} is missing')
            signals[arm]=pd.read_csv(path,parse_dates=['Date']).set_index('Date').sort_index()
        baseline_members=members(signals['baseline'])
    for arm,panel in (() if finalize_only else arms.items()):
        raw=[]
        for i,(tr,va,te) in enumerate(splits):
            train=panel[panel.index.isin(tr)].sort_index(); val=panel[panel.index.isin(va)].sort_index(); test=panel[panel.index.isin(te)].sort_index(); model=_train_lambdarank(train,val,cols)
            piece=test[['ticker']].copy(); piece['raw']=model.predict(test[cols].fillna(0).values); raw.append(piece); print(f'{arm} split {i+1}/{len(splits)}',flush=True)
        sig=build_full_output(raw_preds(pd.concat(raw).sort_index()),None,feature_dfs,MomentumEnsemble(),record_diagnostics=False); signals[arm]=sig; bt=BT(sig,prices); bt.run(); stats=bt.statistics(); mem=members(sig)
        if arm=='baseline':
            expected=json.loads((ROOT/'results/niva3_reconstructed_price_retrain_corrected.json').read_text())['reconstructed_metrics']; mismatch={k:(stats[k],expected[k]) for k in ('CAGR','Sharpe','Max Drawdown') if stats[k]!=expected[k]}
            if mismatch: raise RuntimeError(f'Baseline parity failed {mismatch}')
            baseline_members=mem
        j=(1.,1.,1.) if arm=='baseline' else jac(baseline_members,mem)
        rows.append({'arm':arm,**stats,'cagr_numeric':pct(stats['CAGR']),'alpha_cagr':pct(stats['CAGR'])-bcagr,'median_top15_jaccard':j[0],'p10_top15_jaccard':j[1],'worst_top15_jaccard':j[2]})
        sig.to_csv(ROOT/f'results/niva3_sr53_{arm}_signals.csv'); print(arm,rows[-1],flush=True)
    table=pd.DataFrame(rows); table.to_csv(CSV,index=False)
    member_rows=[]
    for arm,sig in signals.items():
        for d,g in sig[sig.pred_signal.eq(1)].groupby(level=0):
            for t in g.ticker: member_rows.append({'arm':arm,'date':d,'ticker':t})
    pd.DataFrame(member_rows).to_csv(MEMBERS,index=False)
    base=table.iloc[0]; challengers=table.iloc[1:]; gate=bool((challengers.alpha_cagr>0).all() and ((challengers.cagr_numeric-base.cagr_numeric)>=-.03).all() and (challengers.median_top15_jaccard>=.60).all())
    selected=signals['baseline']; key=pd.MultiIndex.from_arrays([selected.index,selected.ticker]); raw_base=base_panel.set_index('ticker',append=True); chosen=selected.pred_signal.eq(1).to_numpy(); aligned=raw_base.reindex(key); selected_missing_tech=float(aligned.iloc[chosen][technical].isna().any(axis=1).mean()); selected_missing_fund=float(aligned.iloc[chosen][FUND].isna().any(axis=1).mean())
    report={'status':'PASS','test':'N3-SR53','parent_stage':parent['manifest_sha256'],'baseline_parity':'EXACT_ROUNDED','benchmark_cagr':bcagr,'selected_rows_missing_any_technical':selected_missing_tech,'selected_rows_missing_any_fundamental':selected_missing_fund,'selection_stability_gate':'PASS' if gate else 'FAIL','decision_rule':'every perturbation positive index alpha; CAGR loss <=3pp; median top15 Jaccard >=0.60','arms':len(table),'splits':len(splits),'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); artifacts=[OUT,CSV,MEMBERS,Path(__file__).resolve(),*[ROOT/f'results/niva3_sr53_{a}_signals.csv' for a in arms]]
    stage=freeze_stage('17_publication_missingness_selection',[*artifacts],{'test':'N3-SR53','selection_stability_gate':report['selection_stability_gate'],'production':False},parent=PARENT); print(json.dumps(report,indent=2)); print(stage)

if __name__=='__main__': main()
