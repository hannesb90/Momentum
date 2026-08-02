"""N3-36: retrain seed-42 13w LambdaRank solely from frozen N3-35 state."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from research_gates_common import apply_large,validate_large_contract
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS,add_cross_sectional,attach_categorical_features
from models.ensemble import MomentumEnsemble,build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage,verify_manifest
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/35_canonical_pit_snapshot.json'
PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';FEAT=ROOT/'results/niva3_canonical_features_stage35.pkl';MODEL=ROOT/'results/niva3_canonical_model_state_stage35.pkl'
OLD=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv';SIGNALS=ROOT/'results/niva3_canonical_signals_stage36.csv';RAW=ROOT/'results/niva3_canonical_raw_stage36.csv';OUT=ROOT/'results/niva3_canonical_retrain_stage36.json'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
class BT(MomentumBacktester):
 def _correlation_filter(self,w,date):return w
def pct(x):return float(str(x).replace('%',''))/100
def main():
 parent=verify_manifest(PARENT);features=pd.read_pickle(FEAT);prices=pd.read_pickle(PRICE);state=pd.read_pickle(MODEL)
 _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']);config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
 features=attach_categorical_features(add_cross_sectional(features),sectors,caps);cols=list(getattr(state,'feature_cols_',[]) or FEATURE_COLS);validate_large_contract(cols)
 panel=panel_from(features,prices);expected=pd.DatetimeIndex(pd.read_csv(OLD,parse_dates=['Date']).Date.drop_duplicates().sort_values())
 frozen_features=pd.read_pickle(ROOT/'results/abstention_features.pkl');frozen_prices=pd.read_pickle(ROOT/'results/abstention_price_data.pkl')
 frozen_panel=panel_from(frozen_features,frozen_prices);dates=frozen_panel.index.unique().sort_values();purge=dates[-(config.HOLDOUT_WEEKS+52)];allowed=dates[dates<purge]
 dev=panel[panel.index.isin(allowed)].sort_index();frozen_dev=frozen_panel[frozen_panel.index.isin(allowed)].sort_index()
 wf=walk_forward_splits(frozen_dev.index,embargo_weeks=52);_set_seed(42);pieces=[]
 for i,(tr,va,te) in enumerate(wf):
  train=dev[dev.index.isin(tr)].sort_index();val=dev[dev.index.isin(va)].sort_index();test=dev[dev.index.isin(te)].sort_index();m=_train_lambdarank(train,val,cols)
  x=test[['ticker']].copy();x['raw']=m.predict(test[cols].fillna(0).values);pieces.append(x);print(f'canonical split {i+1}/{len(wf)}',flush=True)
 raw=pd.concat(pieces).sort_index()
 if not raw.index.unique().sort_values().equals(expected):raise RuntimeError('Frozen snapshot cannot reproduce exact OOF test calendar')
 raw.to_csv(RAW);fdfs={t:f.assign(ticker=t) for t,f in features.items()};config.REBALANCE_WEEKS=52;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
 sig=build_full_output(raw_preds(raw),None,fdfs,MomentumEnsemble(),record_diagnostics=False)
 if not sig.index.unique().sort_values().equals(expected):raise RuntimeError('Signal OOF calendar mismatch')
 sig.to_csv(SIGNALS);bt=BT(sig,prices);bt.run();s=bt.statistics();bench=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(expected).ffill().dropna();years=(bench.index[-1]-bench.index[0]).days/365.25;bcagr=float((bench.iloc[-1]/bench.iloc[0])**(1/years)-1)
 report={'status':'PASS','parent_stage':parent['manifest_sha256'],'test':'N3-36-canonical-snapshot-retrain','target_weeks':13,'rotation_weeks':52,'seed':42,'splits':len(wf),'oof_start':str(expected[0].date()),'oof_end':str(expected[-1].date()),'oof_weeks':len(expected)-1,'metrics':{k:s[k] for k in ('CAGR','Sharpe','Max Drawdown','End Capital')},'benchmark_cagr':bcagr,'alpha_cagr':pct(s['CAGR'])-bcagr,'replay_gate':'PASS','downstream_anchor':'N3-36','holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 sec=f"\n## 2026-08-02 – N3-36: omträning på kanonisk snapshot\n\nSeed-42 LambdaRank tränades om i {len(wf)} splits med 13v-target, 52v-rotation och exakt gammal OOF-kalender. Resultat: {s['CAGR']} CAGR, {s['Sharpe']} Sharpe, {s['Max Drawdown']} MaxDD; index-CAGR {bcagr:.1%}, alpha {report['alpha_cagr']:+.1%}. Snapshot och signaler är frysta; detta är nytt forskningsankare, inte produktion.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('36_canonical_snapshot_retrain',[OUT,SIGNALS,RAW,Path(__file__).resolve(),PRICE,FEAT,MODEL],{'test':'N3-36-canonical-retrain','replay_gate':'PASS','production':False},parent=PARENT)
 print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
