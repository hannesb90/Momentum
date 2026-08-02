"""N3 stage 25 / SR3: DEV-only screen for rank-capable regime interactions."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import config
from research_gates_common import apply_large
apply_large()
from backtest.regime import classify_regimes
from niva3_stage_control import freeze_stage, verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/24_sr1_robustness.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_sr3_regime_interaction_screen.json'
SUMMARY=ROOT/'results/niva3_sr3_regime_interaction_summary.csv'
DATES=ROOT/'results/niva3_sr3_regime_interaction_date_ic.csv'
FEATURES=('resid_mom','rvol_26w','liquidity_rank','rank_change_4w')

def holm(pvalues):
    order=np.argsort(pvalues); out=np.empty(len(pvalues),bool)
    active=True
    for rank,idx in enumerate(order):
        passed=bool(pvalues[idx] <= .05/(len(pvalues)-rank)) if active else False
        out[idx]=passed; active=active and passed
    return out

def main():
    parent=verify_manifest(PARENT); features,prices,_=reconstructed_state(); panel=panel_from(features,prices)
    oof=pd.DatetimeIndex(pd.read_csv(SIGNALS,parse_dates=['Date']).Date.drop_duplicates().sort_values())
    panel=panel[panel.index.isin(oof)].copy(); regime=classify_regimes(prices).reindex(oof).ffill()
    rows=[]
    for date,g in panel.groupby(level=0):
        for feature in FEATURES:
            x=g[[feature,'ret13']].dropna()
            if len(x)<20: continue
            rows.append({'date':date,'regime':regime.get(date),'feature':feature,'n':len(x),
                         'ic':float(x[feature].rank().corr(x.ret13.rank()))})
    date_table=pd.DataFrame(rows).dropna(subset=['regime']); date_table.to_csv(DATES,index=False)
    summaries=[]; pvals=[]
    for feature,g in date_table.groupby('feature'):
        groups=[x.ic.values for _,x in g.groupby('regime') if len(x)>=8]
        p=float(stats.kruskal(*groups).pvalue) if len(groups)>=2 else 1.0; pvals.append(p)
        means=g.groupby('regime').ic.mean(); counts=g.groupby('regime').size()
        yearly=g.assign(year=pd.to_datetime(g.date).dt.year).groupby(['regime','year']).ic.mean()
        best=str(means.abs().idxmax()); best_years=yearly.loc[best] if best in yearly.index.get_level_values(0) else pd.Series(dtype=float)
        summaries.append({'feature':feature,'overall_mean_ic':g.ic.mean(),'bull_mean_ic':means.get('bull',np.nan),
                          'sideways_mean_ic':means.get('sideways',np.nan),'bear_mean_ic':means.get('bear',np.nan),
                          'bull_weeks':counts.get('bull',0),'sideways_weeks':counts.get('sideways',0),'bear_weeks':counts.get('bear',0),
                          'max_regime_ic_spread':means.max()-means.min(),'strongest_regime':best,
                          'strongest_regime_abs_ic':abs(means.loc[best]),
                          'strongest_regime_year_sign_share':float((np.sign(best_years)==np.sign(means.loc[best])).mean()) if len(best_years) else 0,
                          'heterogeneity_pvalue':p})
    table=pd.DataFrame(summaries); table['holm_pass']=holm(np.asarray(pvals))
    table['screen_pass']=table.holm_pass&(table.max_regime_ic_spread>=.04)&(table.strongest_regime_abs_ic>=.03)&(table.strongest_regime_year_sign_share>=.60)
    table.to_csv(SUMMARY,index=False); passed=table.loc[table.screen_pass,'feature'].tolist()
    report={'status':'PASS','test':'N3-SR3-regime-interaction-screen','parent_stage':parent['manifest_sha256'],
            'oof_window':{'start':str(oof[0].date()),'end':str(oof[-1].date()),'weeks':len(oof)-1},
            'features':list(FEATURES),'regime_counts':{str(k):int(v) for k,v in regime.value_counts().items()},
            'passed_features':passed,'screen_gate':'PASS' if passed else 'FAIL',
            'decision_rule':'Holm-corrected Kruskal p<0.05; max regime IC spread >=0.04; strongest |IC|>=0.03; same sign >=60% regime-year cells',
            'full_model_retrain_authorized':bool(passed),'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('25_sr3_regime_interaction_screen',[OUT,SUMMARY,DATES,Path(__file__).resolve()],
                       {'test':'N3-SR3-regime-interaction-screen','screen_gate':report['screen_gate'],'passed_features':passed,'production':False},parent=PARENT)
    print(table.to_string(index=False)); print(json.dumps(report,indent=2,ensure_ascii=False)); print(stage)

if __name__=='__main__': main()
