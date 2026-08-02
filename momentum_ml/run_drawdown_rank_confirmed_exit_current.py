"""N3-33 / SR5+SR37: drawdown exit requiring rank deterioration and refill."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from niva3_stage_control import freeze_stage,verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state

ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/32_cause_specific_reentry_gate.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv';OUT=ROOT/'results/niva3_drawdown_rank_exit.json'
EVENTS=ROOT/'results/niva3_drawdown_rank_exit_events.csv';LOO=ROOT/'results/niva3_drawdown_rank_exit_loo.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
ARMS=((-.30,.70),(-.30,.50),(-.40,.70),(-.40,.50))
def pct(x):return float(str(x).replace('%',''))/100

class BT(MomentumBacktester):
 def __init__(self,*a,dd=None,rank_floor=None,skip=None,**kw):
  super().__init__(*a,**kw);self.dd=dd;self.rank_floor=rank_floor;self.skip=skip or set();self.peaks={};self.events=[]
 def _correlation_filter(self,w,date):return w
 def _apply(self,date,cash):
  if self.dd is None:return cash
  for t in list(self._portfolio):
   price=self._get_price(t,date)
   if price:self.peaks[t]=max(self.peaks.get(t,price),price)
  for t in list(self._portfolio):
   price=self._get_price(t,date);peak=self.peaks.get(t)
   if not price or not peak or price/peak-1>self.dd or (date,t) in self.skip:continue
   day=self.signals.loc[[date]];row=day[day.ticker.eq(t)]
   rank=float(row.selection_rank.iloc[0]) if len(row) else 1.0
   if rank>=self.rank_floor:continue
   held=set(self._portfolio);cand=day[(day.selection_eligible.eq(1))&(~day.ticker.isin(held))&(~day.ticker.eq(t))]
   if cand.empty:continue
   best=cand.sort_values('selection_rank',ascending=False).iloc[0];bt=best.ticker;bp=self._get_price(bt,date)
   if not bp:continue
   shares=self._portfolio.pop(t);gross=shares*price;proceeds=gross*(1-self._execution_cost_rate(t,date,gross))
   buyval=proceeds/(1+self._execution_cost_rate(bt,date,proceeds));self._portfolio[bt]=self._portfolio.get(bt,0)+buyval/bp
   self.peaks.pop(t,None);self.peaks[bt]=bp;self.events.append({'Date':date,'sold':t,'replacement':bt,'drawdown':price/peak-1,'rank':rank})
  return cash
 def _trend_exit(self,date,cash):return super()._trend_exit(date,self._apply(date,cash))

def stats(sig,prices,dd=None,rank=None,skip=None):
 b=BT(sig,prices,dd=dd,rank_floor=rank,skip=skip);b.run();return b,b.statistics()
def main():
 parent=verify_manifest(PARENT);_,prices,_=reconstructed_state();sig=pd.read_csv(SIGNALS,parse_dates=['Date']).set_index('Date').sort_index()
 config.REBALANCE_WEEKS=52;config.ATR_STOP_ENABLED=False
 base,bs=stats(sig,prices);rows=[];models={}
 for dd,rank in ARMS:
  b,s=stats(sig,prices,dd,rank);name=f'dd{abs(int(dd*100))}_rank{int(rank*100)}';models[name]=(b,s,dd,rank)
  rows.append({'arm':name,'CAGR':pct(s['CAGR']),'Sharpe':float(s['Sharpe']),'MaxDD':pct(s['Max Drawdown']),'events':len(b.events)})
 table=pd.DataFrame(rows);eligible=table[table.events.ge(10)].copy()
 if len(eligible):
  eligible['score']=(eligible.Sharpe-float(bs['Sharpe']))+(eligible.MaxDD-pct(bs['Max Drawdown']))
  best=eligible.sort_values('score',ascending=False).iloc[0].arm
 else:best=None
 loo=[]
 if best:
  b,s,dd,rank=models[best]
  for ev in b.events:
   _,ls=stats(sig,prices,dd,rank,{(pd.Timestamp(ev['Date']),ev['sold'])})
   loo.append({'arm':best,'skipped_date':ev['Date'],'skipped_ticker':ev['sold'],'CAGR':pct(ls['CAGR']),'Sharpe':float(ls['Sharpe']),'MaxDD':pct(ls['Max Drawdown'])})
 pd.concat([pd.DataFrame([dict(e,arm=n) for e in b.events]) for n,(b,_,_,_) in models.items()],ignore_index=True).to_csv(EVENTS,index=False)
 ld=pd.DataFrame(loo);ld.to_csv(LOO,index=False)
 winner=models[best][1] if best else None;loo_ok=bool(len(ld) and (ld.Sharpe>float(bs['Sharpe'])).mean()>=.8)
 gate=bool(best and pct(winner['CAGR'])>=pct(bs['CAGR'])-.01 and float(winner['Sharpe'])>=float(bs['Sharpe'])+.05 and pct(winner['Max Drawdown'])>=pct(bs['Max Drawdown'])+.01 and loo_ok)
 report={'status':'PASS','parent_stage':parent['manifest_sha256'],'test':'N3-SR5-SR37-drawdown-rank-confirmed-exit','arms':rows,
 'baseline':{k:bs[k] for k in ('CAGR','Sharpe','Max Drawdown')},'best_diagnostic_arm':best,'best_metrics':winner,'loo_runs':len(ld),'loo_sharpe_better_share':float((ld.Sharpe>float(bs['Sharpe'])).mean()) if len(ld) else None,
 'adoption_gate':'PASS' if gate else 'FAIL','decision_rule':'events>=10; CAGR loss<=1pp; Sharpe +0.05; MaxDD +1pp; >=80% leave-one-event-out Sharpe above baseline',
 'selection_allowed':False,'holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
 section=f"\n## 2026-08-02 – N3-33: SR5 drawdown + rankbekräftad exit\n\nFyra förregistrerade kombinationer (-30/-40%, rank under 70/50-percentil) kördes med omedelbar ersättare. Baslinje {bs['CAGR']} CAGR/{bs['Sharpe']} Sharpe/{bs['Max Drawdown']} MaxDD. Bästa diagnostiska arm `{best}`; `adoption_gate={'PASS' if gate else 'FAIL'}`, {len(ld)} leave-one-event-out-körningar. Ingen holdout eller produktion användes.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(section)
 stage=freeze_stage('33_drawdown_rank_confirmed_exit',[OUT,EVENTS,LOO,Path(__file__).resolve(),SIGNALS],{'test':'N3-SR5-SR37','adoption_gate':report['adoption_gate'],'production':False},parent=PARENT)
 print(table.to_string(index=False));print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(stage)
if __name__=='__main__':main()
