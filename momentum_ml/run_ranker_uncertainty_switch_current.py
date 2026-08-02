"""N3-31 / SR2+SR20: screen seed uncertainty as a rotation-deferral signal."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from niva3_stage_control import freeze_stage, verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/30_conditional_riskadj_screen.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
RAW=ROOT/'results/niva3_seed_consensus_raw_scores.csv'
OUT=ROOT/'results/niva3_ranker_uncertainty_switch_screen.json'
EVENTS=ROOT/'results/niva3_ranker_uncertainty_rotation_events.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')

def forward_return(prices,ticker,date,weeks=13):
    if ticker not in prices:return np.nan
    s=prices[ticker].Close.dropna(); i=s.index.searchsorted(date)
    if i>=len(s) or i+weeks>=len(s):return np.nan
    return float(s.iloc[i+weeks]/s.iloc[i]-1)

def main():
    parent=verify_manifest(PARENT); _,prices,_=reconstructed_state()
    sig=pd.read_csv(SIGNALS,parse_dates=['Date']); raw=pd.read_csv(RAW,parse_dates=['Date'])
    raw=raw[raw.Date.isin(sig.Date.unique())].copy()
    cols=['raw_7','raw_42','raw_97']
    for c in cols: raw[c+'_rank']=raw.groupby('Date')[c].rank(pct=True)
    raw['uncertainty']=raw[[c+'_rank' for c in cols]].std(axis=1)
    umap=raw.set_index(['Date','ticker']).uncertainty
    dates=pd.DatetimeIndex(sig.Date.drop_duplicates().sort_values())[::52]
    rows=[]; previous=set(); rng=np.random.default_rng(42)
    for date in dates:
        day=sig[sig.Date.eq(date)]; current=set(day.loc[day.pred_signal.eq(1),'ticker'])
        if previous:
            entrants=sorted(current-previous); outgoing=sorted(previous-current)
            vals=pd.Series({t:umap.get((date,t),np.nan) for t in entrants}).dropna()
            n=max(1,int(np.ceil(.20*len(vals)))) if len(vals) else 0
            uncertain=set(vals.nlargest(n).index); controls=set(rng.choice(list(vals.index),size=n,replace=False)) if n else set()
            for kind,names in [('uncertain_entry',uncertain),('random_entry',controls),('outgoing_incumbent',set(outgoing))]:
                for ticker in names: rows.append({'Date':date,'ticker':ticker,'group':kind,'ret13':forward_return(prices,ticker,date),'uncertainty':umap.get((date,ticker),np.nan)})
        previous=current
    e=pd.DataFrame(rows); e.to_csv(EVENTS,index=False)
    means=e.groupby('group').ret13.mean(); counts=e.groupby('group').ret13.count()
    u=means.get('uncertain_entry',np.nan); r=means.get('random_entry',np.nan); o=means.get('outgoing_incumbent',np.nan)
    # The mechanism only merits a portfolio state-machine if uncertain entries
    # lose to both a matched random entry and the names they would replace.
    gate=bool(counts.get('uncertain_entry',0)>=20 and u<r and u<o)
    report={'status':'PASS','parent_stage':parent['manifest_sha256'],'test':'N3-SR2-SR20-ranker-uncertainty-switch-screen',
            'architecture_correction':'Current anchor is already a 13w target ranker; a 13w tie-break is therefore not a distinct arm.',
            'tested_mechanism':'defer annual rotation when entering stock is top-quintile seed-rank disagreement',
            'matched_control':'same number of random entrants per rebalance date, seed 42','event_counts':{str(k):int(v) for k,v in counts.items()},
            'mean_forward_13w':{str(k):float(v) for k,v in means.dropna().items()},'screen_gate':'PASS' if gate else 'FAIL',
            'full_state_machine_backtest_authorized':gate,'decision_rule':'at least 20 uncertain entries and their mean ret13 below both matched random entrants and displaced incumbents',
            'selection_allowed':False,'holdout_used':False,'production':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    section=("\n## 2026-08-02 – N3-31: SR2/SR20 rankerosäker rotationsväxel\n\n"
             f"Seed-oenighet screenades som signal att behålla befintligt innehav. Antal osäkra inträden: {counts.get('uncertain_entry',0)}; "
             f"13v-medel {u:+.2%}, slumpkontroll {r:+.2%}, utgående innehav {o:+.2%}. `screen_gate={'PASS' if gate else 'FAIL'}`. "
             "13v tie-break utgick som duplicerad arm eftersom ankaret redan är en 13v-targetmodell. Ingen holdout eller produktion användes.\n")
    for d in DOCS:
        with d.open('a',encoding='utf-8') as f:f.write(section)
    stage=freeze_stage('31_ranker_uncertainty_switch_screen',[OUT,EVENTS,Path(__file__).resolve(),SIGNALS,RAW],
        {'test':'N3-SR2-SR20','screen_gate':report['screen_gate'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
