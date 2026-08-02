"""N3-34: invalidate SR5 because reconstructed price inputs were not frozen."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from niva3_stage_control import freeze_stage,verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import NoCorrelationBacktester
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/33_drawdown_rank_confirmed_exit.json'
SIG=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv';PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';OUT=ROOT/'results/niva3_sr5_price_state_remediation.json'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
def main():
 p=verify_manifest(PARENT);_,prices,_=reconstructed_state();pd.to_pickle(prices,PRICE)
 sig=pd.read_csv(SIG,parse_dates=['Date']).set_index('Date').sort_index();config.REBALANCE_WEEKS=52;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
 b=NoCorrelationBacktester(sig,prices);b.run();now=b.statistics();expected=json.loads((ROOT/'results/niva3_reconstructed_price_retrain_corrected.json').read_text())['reconstructed_metrics']
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-34-SR5-price-state-remediation','stage33_decision_weight':'INVALID',
 'expected_stage12_metrics':expected,'replay_with_current_reconstructed_prices':{k:now[k] for k in ('CAGR','Sharpe','Max Drawdown','End Capital')},
 'parity_gate':'FAIL','root_cause':'Stage12 froze signals and patches but not the complete price dictionary/cache inputs; reconstructed_state now resolves a different mutable Börsdata-backed price state.',
 'required_fix':'Choose and rebuild one canonical PIT total-return price snapshot, freeze every ticker series and its vendor/corporate-action provenance, retrain/replay baseline, then rerun SR5.',
 'production':False,'holdout_used':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 sec=("\n## 2026-08-02 – N3-34: SR5 prisstate-remediering\n\nN3-33 ogiltigförklaras. Exakt frysta signaler gav tidigare 22,2% CAGR men 9,3% mot nu upplöst prisstate. Kompletta prisserier/cacheinputs saknades i N3-12-manifestet. `parity_gate=FAIL`; ingen SR5-arm har beslutskraft. Nuvarande prisdictionary är sparad och hashfryst för reproducerbar felsökning. Ingen produktion ändrades.\n")
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('34_sr5_price_state_remediation',[OUT,PRICE,Path(__file__).resolve(),SIG],{'test':'N3-34-remediation','stage33_decision_weight':'INVALID','parity_gate':'FAIL','production':False},parent=PARENT)
 print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
