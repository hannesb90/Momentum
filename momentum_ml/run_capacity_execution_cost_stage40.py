"""N3-40 / SR14+SR41+SR42: AUM-scaled liquidity and execution audit."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage,verify_manifest
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/39_rank_calibration.json';SIG=ROOT/'results/niva3_canonical_signals_stage36.csv';PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';OUT=ROOT/'results/niva3_capacity_execution_stage40.json';ARMS=ROOT/'results/niva3_capacity_execution_arms_stage40.csv';DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md');AUM=(100_000,1_000_000,10_000_000,100_000_000)
def pct(x):return float(str(x).replace('%',''))/100
class AuditBT(MomentumBacktester):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cap_calls=0;self.cap_binding=0;self.requested=0.;self.filled=0.;self.cost_rates=[]
 def _correlation_filter(self,w,date):return w
 def _liquidity_cap(self,ticker,date,trade_value):
  filled=super()._liquidity_cap(ticker,date,trade_value);self.cap_calls+=1;self.requested+=abs(trade_value);self.filled+=abs(filled);self.cap_binding+=int(abs(filled)+1e-8<abs(trade_value));return filled
 def _execution_cost_rate(self,ticker,date,trade_value):
  r=super()._execution_cost_rate(ticker,date,trade_value);self.cost_rates.append(r);return r
def main():
 p=verify_manifest(PARENT);sig=pd.read_csv(SIG,parse_dates=['Date']).set_index('Date').sort_index();prices=pd.read_pickle(PRICE);_,sec,cap,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']);config.SECTOR_MAP.update(sec);config.CAP_TIER_MAP.update(cap);config.NAME_MAP.update(names);config.REBALANCE_WEEKS=52;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
 rows=[]
 for aum in AUM:
  b=AuditBT(sig,prices,initial_capital=aum);b.run();s=b.statistics();rows.append({'initial_aum_sek':aum,'CAGR':pct(s['CAGR']),'Sharpe':float(s['Sharpe']),'MaxDD':pct(s['Max Drawdown']),'EndCapital':float(str(s['End Capital']).replace(',','')),'liquidity_cap_calls':b.cap_calls,'binding_orders':b.cap_binding,'binding_share':b.cap_binding/max(b.cap_calls,1),'requested_trade_value':b.requested,'filled_trade_value':b.filled,'fill_ratio':b.filled/max(b.requested,1),'mean_cost_rate':sum(b.cost_rates)/max(len(b.cost_rates),1),'max_cost_rate':max(b.cost_rates) if b.cost_rates else None});print(f'AUM {aum:,} done',flush=True)
 t=pd.DataFrame(rows);t.to_csv(ARMS,index=False);user=t.iloc[0];million=t.iloc[1];user_gate=bool(user.binding_orders==0 and user.fill_ratio>=.999 and user.mean_cost_rate<.01);scale_gate=bool((t.CAGR>=t.iloc[0].CAGR-.01).all() and (t.fill_ratio>=.95).all())
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-SR14-capacity-execution','aum_levels_sek':list(AUM),'participation_cap_adv':config.LIQUIDITY_MAX_ADV_FRACTION,'impact_model':'commission + slippage + ADV half-spread + 0.10*sqrt(trade/ADV), capped 5%','user_100k_gate':'PASS' if user_gate else 'FAIL','tested_scale_gate':'PASS' if scale_gate else 'FAIL','user_100k_metrics':user.to_dict(),'one_million_metrics':million.to_dict(),'daily_next_day_execution_available':False,'successive_fill_backtest_run':False,'limitation':'Frozen source is weekly OHLCV. Exact next-day and within-week staged fills require canonical daily PIT OHLCV; weekly liquidity caps are reported but not relabeled as daily execution.','decision':'Implementation/capacity diagnostic only; no model-alpha adoption.','holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8');sec=f"\n## 2026-08-02 – N3-40: SR14 kapacitet/exekvering\n\nAUM {list(AUM)} SEK testades med ADV-tak, spread och sqrt-impact. 100k-grind `{report['user_100k_gate']}`, skalgrind `{report['tested_scale_gate']}`. Daglig nästa-dag/successiv fill är fail-closed eftersom den frysta panelen är veckovis. Ingen holdout eller produktion användes.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('40_capacity_execution_cost',[OUT,ARMS,Path(__file__).resolve(),SIG,PRICE],{'test':'N3-SR14-SR41-SR42','user_100k_gate':report['user_100k_gate'],'tested_scale_gate':report['tested_scale_gate'],'production':False},parent=PARENT);print(t.to_string(index=False));print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(stage)
if __name__=='__main__':main()
