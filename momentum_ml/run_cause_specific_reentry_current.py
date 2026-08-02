"""N3-32 / SR4+SR36: fail-closed observability gate for cause-specific re-entry."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from niva3_stage_control import freeze_stage,verify_manifest
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/31_ranker_uncertainty_switch_screen.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
OUT=ROOT/'results/niva3_cause_specific_reentry_gate.json'
SCHEMA=ROOT/'results/niva3_cause_specific_reentry_schema.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
CAUSES=('scheduled_rank_rotation','trend_exit','drawdown_exit','liquidity_or_data_stop')
def main():
 p=verify_manifest(PARENT);s=pd.read_csv(SIGNALS,nrows=5)
 observed=[c for c in ('exit_reason','exit_date','sell_reason','trade_id') if c in s.columns]
 pd.DataFrame({'required_exit_cause':CAUSES,'available':[False]*len(CAUSES)}).to_csv(SCHEMA,index=False)
 gate=len(observed)>0 and 'exit_reason' in observed
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-SR4-SR36-cause-specific-reentry',
 'required_cohorts':list(CAUSES),'observed_cause_columns':observed,'causal_event_ledger_gate':'PASS' if gate else 'FAIL',
 'cooldowns_preregistered_weeks':[4,13],'alternative_unlock_rule':'improved rank versus exit rank',
 'economic_backtest_run':False,'decision':'DEFER_OBSERVABILITY_GATE',
 'reason':'Frozen signals contain desired holdings, not executed exit events with mutually exclusive causes. Reconstructing causes after the fact would mix scheduled rotations with risk exits.',
 'unlock_condition':'Backtester must emit PIT trade_id, exit_date, exit_reason and exit_rank; then compare 4/13w cooldown and rank recovery by cause on DEV.',
 'holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 section=("\n## 2026-08-02 – N3-32: SR4/SR36 orsaksstyrd re-entry\n\n"
 "Observability-grinden föll: den frysta signalpanelen saknar exekverade exit-event med entydig orsak. Därför kördes ingen generell cooldown under fel etiketter. "
 "`DEFER_OBSERVABILITY_GATE`; nästa implementation måste logga `trade_id`, exitdatum, exitorsak och exitrank innan 4/13v testas per kohort. Ingen holdout eller produktion användes.\n")
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(section)
 stage=freeze_stage('32_cause_specific_reentry_gate',[OUT,SCHEMA,Path(__file__).resolve(),SIGNALS],
 {'test':'N3-SR4-SR36','causal_event_ledger_gate':'FAIL','production':False},parent=PARENT)
 print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
