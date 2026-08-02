"""N3-37: valid SR5 rerun on the immutable N3-36 canonical anchor."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from niva3_stage_control import freeze_stage,verify_manifest
from run_drawdown_rank_confirmed_exit_current import BT,ARMS,pct
from data.data_loader import load_sweden_universe
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/36_canonical_snapshot_retrain.json'
SIG=ROOT/'results/niva3_canonical_signals_stage36.csv';PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';OUT=ROOT/'results/niva3_sr5_canonical_stage37.json';EVENTS=ROOT/'results/niva3_sr5_canonical_events_stage37.csv';LOO=ROOT/'results/niva3_sr5_canonical_loo_stage37.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
def run(sig,prices,dd=None,rank=None,skip=None):
 b=BT(sig,prices,dd=dd,rank_floor=rank,skip=skip);b.run();return b,b.statistics()
def main():
 p=verify_manifest(PARENT);sig=pd.read_csv(SIG,parse_dates=['Date']).set_index('Date').sort_index();prices=pd.read_pickle(PRICE);config.REBALANCE_WEEKS=52;config.ATR_STOP_ENABLED=False;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
 _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']);config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
 base,bs=run(sig,prices)
 expected=json.loads((ROOT/'results/niva3_canonical_retrain_stage36.json').read_text())['metrics'];m={k:(bs[k],expected[k]) for k in ('CAGR','Sharpe','Max Drawdown') if bs[k]!=expected[k]}
 if m:raise RuntimeError(f'N3-36 parity failed: {m}')
 rows=[];models={}
 for dd,rank in ARMS:
  b,s=run(sig,prices,dd,rank);name=f'dd{abs(int(dd*100))}_rank{int(rank*100)}';models[name]=(b,s,dd,rank);rows.append({'arm':name,'CAGR':pct(s['CAGR']),'Sharpe':float(s['Sharpe']),'MaxDD':pct(s['Max Drawdown']),'events':len(b.events)})
 table=pd.DataFrame(rows);e=table[table.events.ge(10)].copy();best=None
 if len(e):e['score']=(e.Sharpe-float(bs['Sharpe']))+(e.MaxDD-pct(bs['Max Drawdown']));best=e.sort_values('score',ascending=False).iloc[0].arm
 loo=[]
 if best:
  b,w,dd,rank=models[best]
  for ev in b.events:
   _,s=run(sig,prices,dd,rank,{(pd.Timestamp(ev['Date']),ev['sold'])});loo.append({'arm':best,'skipped_date':ev['Date'],'skipped_ticker':ev['sold'],'CAGR':pct(s['CAGR']),'Sharpe':float(s['Sharpe']),'MaxDD':pct(s['Max Drawdown'])})
 frames=[pd.DataFrame([dict(x,arm=n) for x in b.events]) for n,(b,_,_,_) in models.items()];pd.concat(frames,ignore_index=True).to_csv(EVENTS,index=False);ld=pd.DataFrame(loo);ld.to_csv(LOO,index=False)
 w=models[best][1] if best else None;loo_share=float((ld.Sharpe>float(bs['Sharpe'])).mean()) if len(ld) else None
 gate=bool(best and pct(w['CAGR'])>=pct(bs['CAGR'])-.01 and float(w['Sharpe'])>=float(bs['Sharpe'])+.05 and pct(w['Max Drawdown'])>=pct(bs['Max Drawdown'])+.01 and loo_share>=.8)
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-SR5-canonical-rerun','baseline':{k:bs[k] for k in ('CAGR','Sharpe','Max Drawdown')},'arms':rows,'best_diagnostic_arm':best,'best_metrics':w,'loo_runs':len(ld),'loo_sharpe_better_share':loo_share,'adoption_gate':'PASS' if gate else 'FAIL','decision_rule':'events>=10; CAGR loss<=1pp; Sharpe +0.05; MaxDD +1pp; >=80% LOO Sharpe above baseline','holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
 sec=f"\n## 2026-08-02 – N3-37: giltig SR5-omkörning\n\nN3-36-baslinjen reproducerades exakt före test. Fyra drawdown/rank-armar kördes; bästa diagnostiska `{best}`, `adoption_gate={'PASS' if gate else 'FAIL'}`, {len(ld)} leave-one-out. Ingen holdout eller produktion användes.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('37_sr5_canonical_rerun',[OUT,EVENTS,LOO,Path(__file__).resolve(),SIG,PRICE],{'test':'N3-SR5-canonical','adoption_gate':report['adoption_gate'],'production':False},parent=PARENT)
 print(table.to_string(index=False));print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(stage)
if __name__=='__main__':main()
