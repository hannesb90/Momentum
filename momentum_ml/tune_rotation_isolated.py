"""Nivå-2 step 2: rotation only, consuming frozen 13-week-target signals."""
from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large,validate_large_contract
apply_large()
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva2_stage_control import verify_manifest,freeze_stage

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"results/rotation_isolated.json"
PARENT=ROOT/"results/niva2_stages/01_target_isolation.json"

def offsets_for(k):
    if k not in (4,13):raise ValueError(k)
    return [i*(52//k) for i in range(k)]

class StaggeredBacktester(MomentumBacktester):
    def __init__(self,signals,prices,k):super().__init__(signals,prices);self.k=k
    def _day_target(self,date):
        d=self.signals.loc[[date]];d=d[d.position_size>0]
        return dict(zip(d.ticker,d.position_size.astype(float)))
    def run(self):
        dates=self.signals.index.unique().sort_values();cash=self.capital;peak=self.capital;pv=[];rows=[]
        self._build_close_panel(dates);self._build_atr_panel(dates);self._build_stress_series(dates)
        if self.market_filter and self._regimes is None:
            try:
                from backtest.regime import classify_regimes
                self._regimes=classify_regimes(self.prices)
            except Exception:self._regimes=pd.Series(dtype=object)
        sleeves=[self._day_target(dates[0]) for _ in range(self.k)];offsets=offsets_for(self.k)
        for i,date in enumerate(dates):
            value=cash+self._portfolio_value(date);peak=max(peak,value);dd=value/peak-1
            market=self._market_exposure_factor(date);guard=self._drawdown_guard_factor(dd);pv.append(value);vol=self._vol_target_factor(pv)
            changed=i==0
            for j,offset in enumerate(offsets):
                if i>0 and i>=offset and (i-offset)%52==0:sleeves[j]=self._day_target(date);changed=True
            if changed:
                target={}
                for sleeve in sleeves:
                    for t,w in sleeve.items():target[t]=target.get(t,0)+w/self.k
                target=self._correlation_filter(target,date);target=self._sector_exposure_filter(target)
                total=sum(target.values())
                if total>1:target={t:w/total for t,w in target.items()}
                target={t:w*market*guard*vol for t,w in target.items()};cash=self._rebalance(date,target,value,cash)
            else:
                cash=self._derisk_to_cap(date,market*guard*vol,value,cash);cash=self._trend_exit(date,cash);cash=self._atr_stop_exit(date,cash)
            self._update_peak_prices(date)
            rows.append({"Date":date,"portfolio_value":cash+self._portfolio_value(date),"cash":cash,
                         "n_positions":len(self._portfolio),"drawdown_guard":guard,"market_exposure":market,"vol_exposure":vol})
        self._results=pd.DataFrame(rows).set_index("Date");return self._results

def run_calendar(signals,prices,weeks):
    config.REBALANCE_WEEKS=weeks;bt=MomentumBacktester(signals,prices);bt.run();return bt.statistics()

def main():
    parent=verify_manifest(PARENT);validate_large_contract(parent["metadata"].get("feature_cols") or ["locked"])
    signals=pd.read_csv(ROOT/"results/niva2_target_13_signals.csv",parse_dates=["Date"]).set_index("Date").sort_index()
    prices=pd.read_pickle(ROOT/"results/abstention_price_data.pkl");_,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    variants={"calendar_13":run_calendar(signals,prices,13),"calendar_52":run_calendar(signals,prices,52)}
    config.REBALANCE_WEEKS=52
    for k in (4,13):
        bt=StaggeredBacktester(signals,prices,k);bt.run();variants[f"staggered_{k}_cohorts"]=bt.statistics()
    def number(s,key):return float(str(s[key]).replace("%",""))
    winner=max(variants,key=lambda n:(number(variants[n],"CAGR"),float(variants[n]["Sharpe"])))
    report={"status":"PASS","parent_stage":parent["manifest_sha256"],"target":"binary_13v_frozen",
            "variants":variants,"winner":winner,"holdout_used":False,"multiple_arms":4,
            "note":"winner must feed the next objective stage; no production adoption"}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    stage=freeze_stage("02_rotation_isolation",[OUT,Path(__file__).resolve()],
        {"winner":winner,"target":"binary_13v","holdout_used":False,"arms":4},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False));print(OUT);print(stage)

if __name__=="__main__":main()
