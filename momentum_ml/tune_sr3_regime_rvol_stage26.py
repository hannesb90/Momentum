"""N3 stage 26 / SR3: bear-regime x rvol interaction with date-placebo."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large,validate_large_contract
apply_large()
from backtest.backtester import MomentumBacktester
from backtest.regime import classify_regimes
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS,add_cross_sectional,attach_categorical_features
from models.ensemble import MomentumEnsemble,build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage,verify_manifest
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from
from tune_reconstructed_prices_niva3_stage11 import pct
from tune_abstention_gate import _load_state

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/25_sr3_regime_interaction_screen.json'
BASE_SIG=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_sr3_regime_rvol.json'; ARMS=ROOT/'results/niva3_sr3_regime_rvol_arms.csv'
RAW=ROOT/'results/niva3_sr3_regime_rvol_raw.csv'

class BT(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

def jac(a,b):
    vals=[]
    for d in a:
        x=set(a[d]);y=set(b[d]);u=x|y;vals.append(len(x&y)/len(u) if u else 1.)
    return float(np.median(vals)),float(np.quantile(vals,.1))

def main():
    parent=verify_manifest(PARENT); screen=json.loads((ROOT/'results/niva3_sr3_regime_interaction_screen.json').read_text())
    if screen['passed_features']!=['rvol_26w']: raise RuntimeError('Unexpected SR3 screen result')
    features,prices,state=reconstructed_state(); _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap'])
    config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    regime=classify_regimes(prices).sort_index(); rng=np.random.default_rng(42); shuffled=pd.Series(rng.permutation(regime.values),index=regime.index)
    variants={}
    for arm,reg in [('bear_rvol_interaction',regime),('permuted_regime_placebo',shuffled)]:
        fs={}
        for t,f in features.items():
            x=f.copy(); bear=reg.reindex(x.index).ffill().eq('bear').astype(float)
            x['bear_x_rvol_26w']=x['rvol_26w']*bear; fs[t]=x
        variants[arm]=attach_categorical_features(add_cross_sectional(fs),sectors,caps)
    cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS);validate_large_contract(cols); test_cols=cols+['bear_x_rvol_26w']
    frozen_features,frozen_prices,_,_=_load_state(); frozen=panel_from(frozen_features,frozen_prices); dates=frozen.index.unique().sort_values(); purge=dates[-(config.HOLDOUT_WEEKS+52)];allowed=dates[dates<purge]
    wf=walk_forward_splits(frozen[frozen.index.isin(allowed)].index,embargo_weeks=52); pieces=[]; feature_dfs={}
    for arm,fs in variants.items():
        panel=panel_from(fs,prices);panel=panel[panel.index.isin(allowed)].sort_index();_set_seed(42); raw=[]
        for i,(tr,va,te) in enumerate(wf):
            d=panel.copy();d['target_return']=d.ret13;d['target_signal']=d.sig13
            train=d[d.index.isin(tr)].sort_index();val=d[d.index.isin(va)].sort_index();test=d[d.index.isin(te)].sort_index()
            m=_train_lambdarank(train,val,test_cols);p=test[['ticker']].copy();p['raw']=m.predict(test[test_cols].fillna(0).values);raw.append(p)
            print(f'{arm} split {i+1}/{len(wf)}',flush=True)
        r=pd.concat(raw).sort_index();r['arm']=arm;pieces.append(r.reset_index());feature_dfs[arm]={t:f.assign(ticker=t) for t,f in fs.items()}
    raw_all=pd.concat(pieces,ignore_index=True);raw_all.to_csv(RAW,index=False)
    base=pd.read_csv(BASE_SIG,parse_dates=['Date']).set_index('Date').sort_index(); expected=base.index.unique().sort_values();
    signals={'baseline':base}; rows=[]; baseline_members={d:set(g.loc[g.pred_signal.eq(1),'ticker']) for d,g in base.groupby(level=0)}
    config.REBALANCE_WEEKS=52;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
    for arm in ('baseline','bear_rvol_interaction','permuted_regime_placebo'):
        if arm=='baseline': sig=base
        else:
            r=raw_all[raw_all.arm.eq(arm)].drop(columns='arm').set_index('Date').sort_index()
            sig=build_full_output(raw_preds(r),None,feature_dfs[arm],MomentumEnsemble(),record_diagnostics=False);signals[arm]=sig
        if not sig.index.unique().sort_values().equals(expected):raise RuntimeError(f'{arm} OOF calendar mismatch')
        bt=BT(sig,prices);bt.run();s=bt.statistics();members={d:set(g.loc[g.pred_signal.eq(1),'ticker']) for d,g in sig.groupby(level=0)}
        j=(1.,1.) if arm=='baseline' else jac(baseline_members,members)
        # Paired OOF rank IC against the exact 13v target, split by test fold.
        panel0=panel_from(features,prices); target=panel0[['ticker','ret13']].reset_index()
        score=(sig[['ticker','prob_raw']].reset_index().merge(target,on=['Date','ticker']).set_index('Date'))
        ics=[]
        for _,_,te in wf:
            g=score[score.index.isin(te)];ics.append(g.groupby(level=0).apply(lambda z:z.prob_raw.rank().corr(z.ret13.rank())).mean())
        rows.append({'arm':arm,**s,'cagr_numeric':pct(s['CAGR']),'median_top15_jaccard':j[0],'p10_top15_jaccard':j[1],
                     'median_split_ic':float(np.nanmedian(ics)),'positive_split_ic_share':float((np.asarray(ics)>0).mean())})
        if arm!='baseline':sig.to_csv(ROOT/f'results/niva3_sr3_{arm}_signals.csv')
        print(arm,rows[-1],flush=True)
    table=pd.DataFrame(rows);table.to_csv(ARMS,index=False);b=table.iloc[0];c=table.iloc[1];p=table.iloc[2]
    gate=bool(c.cagr_numeric>b.cagr_numeric and c.Sharpe>b.Sharpe and c.median_top15_jaccard>=.60 and c.median_split_ic>p.median_split_ic and c.positive_split_ic_share>=.55)
    report={'status':'PASS','test':'N3-SR3-regime-rvol-fullmodel','parent_stage':parent['manifest_sha256'],'splits':len(wf),
            'interaction':'rvol_26w * I(causal regime == bear)','placebo':'same regime frequencies permuted across dates seed42',
            'fullmodel_gate':'PASS' if gate else 'FAIL','decision_rule':'challenger CAGR and Sharpe > exact anchor; median Jaccard >=0.60; median split IC > placebo; positive split IC >=55%',
            'eligible_challengers':['bear_rvol_interaction'] if gate else [],'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    artifacts=[OUT,ARMS,RAW,Path(__file__).resolve(),ROOT/'results/niva3_sr3_bear_rvol_interaction_signals.csv',ROOT/'results/niva3_sr3_permuted_regime_placebo_signals.csv']
    stage=freeze_stage('26_sr3_regime_rvol_fullmodel',artifacts,{'test':'N3-SR3-regime-rvol-fullmodel','fullmodel_gate':report['fullmodel_gate'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
