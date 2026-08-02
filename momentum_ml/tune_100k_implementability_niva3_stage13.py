"""N3 stage 13 / SR50: SEK 100k whole-share implementability.

The corrected Stage-12 signal is held fixed.  Fractional and whole-share
portfolios receive identical prices, overlays and rebalance dates.  Monthly
contributions are deliberately excluded by the method contract.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_reconstructed_prices_niva3_stage11 import IDS, cached_dividends, weekly, splice

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/12_reconstructed_price_retrain_corrected.json'
SIGNALS=ROOT/'results/niva3_reconstructed_price_signals_corrected.csv'
EVENTS=ROOT/'results/niva3_fallback_instrument_events.csv'
OUT=ROOT/'results/niva3_100k_implementability.json'
CSV=ROOT/'results/niva3_100k_implementability_arms.csv'
START=100_000.0
ARMS=(("whole_only",0.0,0.0),("min_order_500_min_fee_1",500.0,1.0),
      ("realistic_min_order_1000_min_fee_1",1000.0,1.0),
      ("conservative_min_order_2000_min_fee_39",2000.0,39.0))

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

class WholeShareBacktester(NoCorrelationBacktester):
    def __init__(self,*args,min_order=0.0,min_fee=0.0,**kwargs):
        super().__init__(*args,**kwargs); self.min_order=float(min_order); self.min_fee=float(min_fee)
        self.orders=0; self.skipped_min_order=0; self.skipped_cash=0; self.intended_positions=0; self.unfilled_positions=0

    def _cost(self,ticker,date,value):
        rate=self._execution_cost_rate(ticker,date,value)
        variable=max(abs(value)*self.commission,self.min_fee)
        return abs(value)*max(rate-self.commission,0.0)+variable

    def _rebalance(self,date,target_weights,portfolio_value,cash):
        current=set(self._portfolio); target=set(target_weights); self.intended_positions+=len(target)
        for ticker in current-target:
            price=self._get_price(ticker,date)
            if price is None: continue
            shares=int(math.floor(self._portfolio.pop(ticker)+1e-9)); gross=shares*price
            if shares>0: cash+=gross-self._cost(ticker,date,gross); self.orders+=1
            self._peak_price.pop(ticker,None)
        for ticker,weight in target_weights.items():
            price=self._get_price(ticker,date)
            if price is None: self.unfilled_positions+=1; continue
            current_shares=int(math.floor(self._portfolio.get(ticker,0)+1e-9))
            target_value=portfolio_value*weight
            target_shares=max(int(math.floor(target_value/price)),0)
            delta=target_shares-current_shares; gross=abs(delta)*price
            if delta==0:
                if current_shares==0: self.unfilled_positions+=1
                continue
            if gross<self.min_order:
                self.skipped_min_order+=1
                if current_shares==0: self.unfilled_positions+=1
                continue
            gross=abs(self._liquidity_cap(ticker,date,math.copysign(gross,delta)))
            shares=max(int(math.floor(gross/price)),0)
            if shares==0:
                self.unfilled_positions+=int(current_shares==0); continue
            if delta>0:
                shares=min(shares,max(target_shares-current_shares,0)); trade=shares*price; cost=self._cost(ticker,date,trade)
                while shares>0 and trade+cost>cash:
                    shares-=1; trade=shares*price; cost=self._cost(ticker,date,trade) if shares else 0
                if shares<=0:
                    self.skipped_cash+=1; self.unfilled_positions+=int(current_shares==0); continue
                self._portfolio[ticker]=current_shares+shares; cash-=trade+cost; self.orders+=1
            else:
                shares=min(shares,current_shares-target_shares); trade=shares*price
                self._portfolio[ticker]=current_shares-shares; cash+=trade-self._cost(ticker,date,trade); self.orders+=1
                if self._portfolio[ticker]<=0: self._portfolio.pop(ticker,None); self._peak_price.pop(ticker,None)
        return cash

def reconstructed_prices():
    _,prices,_,_=_load_state(); prices={t:p.copy() for t,p in prices.items()}
    from altdata import borsdata
    splits=borsdata.split_events_map(json.loads((ROOT/'momentum_ml/cache/borsdata/stocksplits_from2000.json').read_text())); divs=cached_dividends()
    events=pd.read_csv(EVENTS,parse_dates=['borsdata_week']); conflicts=events[events.classification.eq('VENDOR_CONFLICT')]
    for ticker,iid in IDS.items():
        w=weekly(iid,divs,splits).loc[lambda x:x.index>=pd.Timestamp(config.START_DATE)].copy()
        if ticker=='SAVE.ST': w=w.loc[w.index>=pd.Timestamp('2020-11-23')].copy()
        else:
            ref=prices[ticker].Close.pct_change()
            for row in conflicts[conflicts.ticker.eq(ticker)].itertuples(): splice(w,pd.Timestamp(row.borsdata_week),float(ref.loc[pd.Timestamp(row.borsdata_week)]))
        prices[ticker]=w
    return prices

def perf(frame):
    v=frame.portfolio_value.astype(float); r=v.pct_change().dropna(); years=(v.index[-1]-v.index[0]).days/365.25
    return {'cagr':float((v.iloc[-1]/v.iloc[0])**(1/years)-1),'sharpe':float(r.mean()/r.std(ddof=1)*np.sqrt(52)),
            'max_drawdown':float((v/v.cummax()-1).min()),'end_value':float(v.iloc[-1]),'mean_cash_pct':float((frame.cash/v).mean())}

def main():
    parent=verify_manifest(PARENT); sig=pd.read_csv(SIGNALS,parse_dates=['Date']).set_index('Date').sort_index(); prices=reconstructed_prices()
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS['large']['market_cap']); config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS=52
    ideal=NoCorrelationBacktester(sig,prices,initial_capital=START); ideal_frame=ideal.run(); ideal_perf=perf(ideal_frame)
    rows=[]
    for arm,min_order,min_fee in ARMS:
        sim=WholeShareBacktester(sig,prices,initial_capital=START,min_order=min_order,min_fee=min_fee); frame=sim.run(); met=perf(frame)
        joined=pd.concat([ideal_frame.portfolio_value.pct_change().rename('ideal'),frame.portfolio_value.pct_change().rename('actual')],axis=1).dropna()
        te=float((joined.actual-joined.ideal).std(ddof=1)*np.sqrt(52)); gap=float(frame.portfolio_value.iloc[-1]/ideal_frame.portfolio_value.iloc[-1]-1)
        rows.append({'arm':arm,'min_order_sek':min_order,'minimum_commission_sek':min_fee,**met,'tracking_error_annual':te,'terminal_wealth_gap':gap,
                     'orders':sim.orders,'skipped_min_order':sim.skipped_min_order,'skipped_cash':sim.skipped_cash,'intended_positions':sim.intended_positions,
                     'unfilled_positions':sim.unfilled_positions,'unfilled_share':sim.unfilled_positions/max(sim.intended_positions,1)})
        print(arm,rows[-1],flush=True)
    table=pd.DataFrame(rows); table.to_csv(CSV,index=False); real=table.set_index('arm').loc['realistic_min_order_1000_min_fee_1']
    gate=real.tracking_error_annual<=.02 and abs(real.terminal_wealth_gap)<=.05 and real.mean_cash_pct-ideal_perf['mean_cash_pct']<=.03 and real.unfilled_share<=.05
    report={'status':'PASS','test':'N3-SR50','parent_stage':parent['manifest_sha256'],'start_capital_sek':START,'monthly_contributions':False,'ideal_fractional':ideal_perf,
            'implementation_gate':'PASS' if gate else 'FAIL','voting_arm':'realistic_min_order_1000_min_fee_1','voting_metrics':real.to_dict(),
            'decision_rule':'annual tracking error <=2%; absolute terminal wealth gap <=5%; incremental mean cash <=3pp; unfilled intended positions <=5%',
            'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    stage=freeze_stage('13_100k_implementability',[OUT,CSV,Path(__file__).resolve()],{'test':'N3-SR50','implementation_gate':report['implementation_gate'],'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,default=str)); print(stage)

if __name__=='__main__': main()
