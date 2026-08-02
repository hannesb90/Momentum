"""N3-38 / SR6: DEV event screen for an armed take-profit state machine."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage,verify_manifest
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/37_sr5_canonical_rerun.json'
SIG=ROOT/'results/niva3_canonical_signals_stage36.csv';PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';FEAT=ROOT/'results/niva3_canonical_features_stage35.pkl'
OUT=ROOT/'results/niva3_sr6_armed_takeprofit_screen.json';EVENTS=ROOT/'results/niva3_sr6_armed_takeprofit_events.csv';DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
class Tracker(MomentumBacktester):
 def __init__(self,*a,feature_lookup,sectors,**kw):super().__init__(*a,**kw);self.fl=feature_lookup;self.sectors=sectors;self.peaks={};self.armed=set();self.fired=set();self.events=[]
 def _correlation_filter(self,w,date):return w
 def _trend_exit(self,date,cash):
  held=set(self._portfolio)
  for t in held:
   px=self._get_price(t,date)
   if not px:continue
   self.peaks[t]=max(self.peaks.get(t,px),px);x=self.fl.get((date,t),{})
   if x.get('sector_roc_pct',0)>=.90:self.armed.add(t)
   rank=x.get('selection_rank',1.0);dd=px/self.peaks[t]-1
   if t in self.armed and t not in self.fired and dd<=-.20 and rank<.50:
    self.fired.add(t);self.events.append({'Date':date,'ticker':t,'sector':self.sectors.get(t,'Unknown'),'peak_drawdown':dd,'selection_rank':rank,'roc_52w':x.get('roc_52w'),'rvol_26w':x.get('rvol_26w')})
  for t in list(self.peaks):
   if t not in held:self.peaks.pop(t,None);self.armed.discard(t);self.fired.discard(t)
  return super()._trend_exit(date,cash)
def fwd(prices,t,date,h=13):
 if t not in prices:return np.nan
 s=prices[t].Close.dropna();i=s.index.searchsorted(date)
 return float(s.iloc[i+h]/s.iloc[i]-1) if i<len(s) and i+h<len(s) else np.nan
def main():
 p=verify_manifest(PARENT);sig=pd.read_csv(SIG,parse_dates=['Date']).set_index('Date').sort_index();prices=pd.read_pickle(PRICE);features=pd.read_pickle(FEAT)
 _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']);config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names);config.REBALANCE_WEEKS=52;config.SIZING_MODE='inverse_vol';config.CONVICTION_BLEND=.75
 rows=[]
 for t,f in features.items():
  if not {'roc_52w','rvol_26w'}.issubset(f.columns):continue
  x=f[['roc_52w','rvol_26w']].copy();x['ticker']=t;x['sector']=sectors.get(t,'Unknown');rows.append(x)
 panel=pd.concat(rows).reset_index().rename(columns={'index':'Date'});panel['sector_roc_pct']=panel.groupby(['Date','sector']).roc_52w.rank(pct=True)
 ranks=sig[['ticker','selection_rank']].reset_index();panel=panel.merge(ranks,on=['Date','ticker'],how='left');lookup={(r.Date,r.ticker):{'roc_52w':r.roc_52w,'rvol_26w':r.rvol_26w,'sector_roc_pct':r.sector_roc_pct,'selection_rank':r.selection_rank} for r in panel.itertuples()}
 bt=Tracker(sig,prices,feature_lookup=lookup,sectors=sectors);bt.run();ev=pd.DataFrame(bt.events);out=[]
 for r in ev.itertuples():
  pool=panel[(panel.Date.eq(r.Date))&(panel.sector.eq(r.sector))&(~panel.ticker.eq(r.ticker))].dropna(subset=['roc_52w','rvol_26w'])
  if pool.empty:pool=panel[(panel.Date.eq(r.Date))&(~panel.ticker.eq(r.ticker))].dropna(subset=['roc_52w','rvol_26w'])
  if pool.empty:continue
  z=((pool.roc_52w-r.roc_52w)/(pool.roc_52w.std() or 1)).abs()+((pool.rvol_26w-r.rvol_26w)/(pool.rvol_26w.std() or 1)).abs();m=pool.loc[z.idxmin()]
  out.append({**r._asdict(),'event_ret13':fwd(prices,r.ticker,r.Date),'control_ticker':m.ticker,'control_ret13':fwd(prices,m.ticker,r.Date)})
 e=pd.DataFrame(out);e.to_csv(EVENTS,index=False);n=len(e);delta=float((e.event_ret13-e.control_ret13).mean()) if n else None
 years=(e.assign(year=pd.to_datetime(e.Date).dt.year,event_minus_control=e.event_ret13-e.control_ret13).groupby('year').event_minus_control.mean()) if n else pd.Series(dtype=float)
 gate=bool(n>=20 and delta<=-.05 and (years<0).mean()>=.60)
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-SR6-armed-takeprofit-state-machine-screen','arming_rule':'held stock reaches top decile sector-relative roc_52w','confirmation_rule':'drawdown from holding peak <=-20% and selection_rank <0.50','matched_control':'same date/sector nearest roc_52w and rvol_26w','events':n,'mean_event_ret13':float(e.event_ret13.mean()) if n else None,'mean_control_ret13':float(e.control_ret13.mean()) if n else None,'event_minus_control':delta,'negative_year_share':float((years<0).mean()) if len(years) else None,'screen_gate':'PASS' if gate else 'FAIL','full_state_machine_authorized':gate,'decision_rule':'events>=20, event-control <=-5pp, negative in >=60% event years','holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');sec=f"\n## 2026-08-02 – N3-38: SR6 armerad vinsthemtagning\n\nTillståndsmaskinens eventstudie gav {n} event och event-minus-kontroll {delta if delta is not None else float('nan'):+.1%} över 13v. `screen_gate={'PASS' if gate else 'FAIL'}`; full exitmekanik körs endast vid PASS. Ingen holdout eller produktion användes.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('38_armed_takeprofit_screen',[OUT,EVENTS,Path(__file__).resolve(),SIG,PRICE,FEAT],{'test':'N3-SR6','screen_gate':report['screen_gate'],'production':False},parent=PARENT);print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
