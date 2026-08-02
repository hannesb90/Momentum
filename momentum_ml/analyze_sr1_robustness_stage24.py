"""N3 stage 24: independent temporal/multiple-test robustness for SR1 arms."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import config
from research_gates_common import apply_large
apply_large()
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from
from tune_abstention_gate import _load_state

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/23_sr1_corrected_overlay.json'
MEMBERS=ROOT/'results/niva3_sr1_corrected_overlay_members.csv'
OUT=ROOT/'results/niva3_sr1_robustness.json'
ARMS=ROOT/'results/niva3_sr1_robustness_arms.csv'
SPLITS=ROOT/'results/niva3_sr1_robustness_splits.csv'
YEARS=ROOT/'results/niva3_sr1_robustness_years.csv'
BASE='baseline_13_target'
CHALLENGERS=('agreement_80_20','top_13_quintile_52_tiebreak')

def block_ci(delta,block=13,reps=5000,seed=42):
    x=np.asarray(delta,float); rng=np.random.default_rng(seed); n=len(x); starts=np.arange(max(n-block+1,1)); means=[]
    for _ in range(reps):
        pieces=[]
        while sum(len(z) for z in pieces)<n:
            s=int(rng.choice(starts)); pieces.append(x[s:min(s+block,n)])
        means.append(np.concatenate(pieces)[:n].mean())
    return float(np.quantile(means,.025)),float(np.quantile(means,.975))

def main():
    parent=verify_manifest(PARENT); features,prices,_=reconstructed_state(); panel=panel_from(features,prices)
    frozen_features,frozen_prices,_,_=_load_state(); frozen=panel_from(frozen_features,frozen_prices)
    dates=frozen.index.unique().sort_values(); purge=dates[-(config.HOLDOUT_WEEKS+52)]; allowed=dates[dates<purge]
    dev=panel[panel.index.isin(allowed)][['ticker','ret13']].reset_index()
    members=pd.read_csv(MEMBERS,parse_dates=['date']).rename(columns={'date':'Date'})
    selected=members.merge(dev,on=['Date','ticker'],how='left')
    if selected.ret13.isna().any(): raise RuntimeError('Selected member lacks exact ret13 target')
    basket=selected.groupby(['arm','Date']).ret13.mean().unstack(0).sort_index()
    expected=pd.DatetimeIndex(members.loc[members.arm.eq(BASE),'Date'].drop_duplicates().sort_values())
    if not basket.index.equals(expected): raise RuntimeError('Basket calendar differs from frozen OOF signal calendar')
    wf=walk_forward_splits(frozen[frozen.index.isin(allowed)].index,embargo_weeks=52)
    split_rows=[]
    for i,(_,_,te) in enumerate(wf,1):
        d=pd.DatetimeIndex(te); g=basket.reindex(d).dropna()
        for arm in CHALLENGERS:
            split_rows.append({'split':i,'arm':arm,'start':g.index.min(),'end':g.index.max(),'weeks':len(g),
                               'baseline_mean_ret13':g[BASE].mean(),'challenger_mean_ret13':g[arm].mean(),
                               'paired_delta':(g[arm]-g[BASE]).mean()})
    split_table=pd.DataFrame(split_rows); split_table.to_csv(SPLITS,index=False)
    year_rows=[]
    for year,g in basket.groupby(basket.index.year):
        for arm in CHALLENGERS:
            year_rows.append({'year':year,'arm':arm,'weeks':len(g),'paired_delta':(g[arm]-g[BASE]).mean()})
    year_table=pd.DataFrame(year_rows); year_table.to_csv(YEARS,index=False)
    rows=[]
    for arm in CHALLENGERS:
        delta=(basket[arm]-basket[BASE]).dropna(); lo,hi=block_ci(delta); t,p=stats.ttest_1samp(delta,0.0,alternative='greater')
        ss=split_table[split_table.arm.eq(arm)]; yy=year_table[year_table.arm.eq(arm)]
        # Actual calendar52 membership turnover, measured only on execution dates.
        exec_dates=basket.index[::52]; sets={a:{d:set(members[(members.arm.eq(a))&(members.Date.eq(d))].ticker) for d in exec_dates} for a in (BASE,arm)}
        turns=[]
        for a in (BASE,arm):
            ds=list(exec_dates); vals=[1-len(sets[a][ds[i]]&sets[a][ds[i-1]])/15 for i in range(1,len(ds))]; turns.append(float(np.mean(vals)))
        rows.append({'arm':arm,'mean_paired_ret13_delta':delta.mean(),'block_bootstrap_ci_low':lo,'block_bootstrap_ci_high':hi,
                     'one_sided_t_pvalue':float(p),'positive_split_share':float((ss.paired_delta>0).mean()),
                     'positive_year_share':float((yy.paired_delta>0).mean()),'worst_year_delta':float(yy.paired_delta.min()),
                     'baseline_rotation_turnover':turns[0],'challenger_rotation_turnover':turns[1],
                     'incremental_rotation_turnover':turns[1]-turns[0]})
    table=pd.DataFrame(rows); table['holm_threshold']=np.array([.025,.05])[np.argsort(np.argsort(table.one_sided_t_pvalue.values))]
    table['holm_pass']=table.one_sided_t_pvalue<=table.holm_threshold
    table['robustness_pass']=(table.positive_split_share>=.55)&(table.positive_year_share>=.60)&(table.block_bootstrap_ci_low>=0)&table.holm_pass&(table.incremental_rotation_turnover<=.20)
    table.to_csv(ARMS,index=False)
    passed=table.loc[table.robustness_pass,'arm'].tolist()
    report={'status':'PASS','test':'N3-SR1-robustness','parent_stage':parent['manifest_sha256'],
            'evaluation':'paired top15 forward-13v basket returns on exact frozen OOF dates; no family averaging',
            'splits':len(wf),'calendar_years':int(basket.index.year.nunique()),'bootstrap_block_weeks':13,'bootstrap_repetitions':5000,
            'multiple_testing':'Holm one-sided alpha 0.05 across two challengers','passed_challengers':passed,
            'robustness_gate':'PASS' if passed else 'FAIL',
            'seed_retrain_authorized':bool(passed),'decision_rule':'positive >=55% splits and >=60% years; block-bootstrap lower 95% CI >=0; Holm pass; incremental annual-rotation turnover <=20pp',
            'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('24_sr1_robustness',[OUT,ARMS,SPLITS,YEARS,Path(__file__).resolve()],
                       {'test':'N3-SR1-robustness','robustness_gate':report['robustness_gate'],'passed_challengers':passed,'production':False},parent=PARENT)
    print(table.to_string(index=False)); print(json.dumps(report,indent=2,ensure_ascii=False)); print(stage)

if __name__=='__main__': main()
