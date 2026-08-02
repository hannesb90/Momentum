"""N3 remediation after SR45: phase-robust rotation architectures."""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large
apply_large()
from backtest.backtester import MomentumBacktester
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/"results/niva3_stages/01_calendar52_phase_robustness.json"
SOURCE=ROOT/"results/niva2_stage6_winner_signals.csv"
OUT=ROOT/"results/niva3_phase_robust_rotation.json"
CSV=ROOT/"results/niva3_phase_robust_rotation_arms.csv"

class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self,target_weights,date): return target_weights

class CohortBacktester(NoCorrelationBacktester):
    def __init__(self,signals,prices,k): super().__init__(signals,prices); self.k=k
    def _target(self,date):
        d=self.signals.loc[[date]]; d=d[(d.pred_signal==1)&(d.position_size>0)]
        return dict(zip(d.ticker,d.position_size.astype(float)))
    def run(self):
        dates=self.signals.index.unique().sort_values();cash=self.capital;peak=self.capital;rows=[];pv=[]
        self._build_close_panel(dates);self._build_atr_panel(dates);self._build_stress_series(dates)
        if self.market_filter and self._regimes is None:
            try:
                from backtest.regime import classify_regimes
                self._regimes=classify_regimes(self.prices)
            except Exception:self._regimes=pd.Series(dtype=object)
        offsets=[int(np.floor(i*52/self.k)) for i in range(self.k)]
        sleeves=[self._target(dates[0]) for _ in range(self.k)]
        for i,date in enumerate(dates):
            value=cash+self._portfolio_value(date);peak=max(peak,value);dd=value/peak-1
            market=self._market_exposure_factor(date);guard=self._drawdown_guard_factor(dd);pv.append(value);vol=self._vol_target_factor(pv)
            changed=i==0
            for j,offset in enumerate(offsets):
                if i>0 and i>=offset and (i-offset)%52==0:
                    sleeves[j]=self._target(date);changed=True
            if changed:
                target={}
                for sleeve in sleeves:
                    for ticker,w in sleeve.items():target[ticker]=target.get(ticker,0.0)+w/self.k
                target=self._sector_exposure_filter(target);total=sum(target.values())
                if total>1:target={t:w/total for t,w in target.items()}
                target={t:w*market*guard*vol for t,w in target.items()}
                cash=self._rebalance(date,target,value,cash)
            else:
                cash=self._derisk_to_cap(date,market*guard*vol,value,cash)
                cash=self._trend_exit(date,cash);cash=self._atr_stop_exit(date,cash)
            self._update_peak_prices(date)
            rows.append({"Date":date,"portfolio_value":cash+self._portfolio_value(date),"cash":cash,
                         "n_positions":len(self._portfolio)})
        self._results=pd.DataFrame(rows).set_index("Date");return self._results

def metrics(values):
    values=values.dropna().astype(float);r=values.pct_change().dropna();years=(values.index[-1]-values.index[0]).days/365.25
    return {"cagr":float((values.iloc[-1]/values.iloc[0])**(1/years)-1),
            "sharpe":float(r.mean()/r.std(ddof=1)*np.sqrt(52)),
            "max_drawdown":float((values/values.cummax()-1).min())}

def main():
    parent=verify_manifest(PARENT)
    if parent["metadata"].get("robustness_gate")!="FAIL":raise RuntimeError("Remediation only follows failed SR45")
    signals=pd.read_csv(SOURCE,parse_dates=["Date"]).set_index("Date").sort_index();_,prices,_,_=_load_state()
    dates=signals.index.unique().sort_values();common_start=dates[51];common_dates=dates[51:]
    close=prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(common_dates).ffill().dropna();bench=metrics(close/close.iloc[0])
    specs=[("calendar13",13,range(13)),("staggered4",4,range(13)),
           ("staggered13",13,range(4)),("staggered52",52,range(1))]
    rows=[]
    for architecture,k,phases in specs:
        for phase in phases:
            arm=signals[signals.index>=dates[phase]]
            if architecture=="calendar13":
                config.REBALANCE_WEEKS=13;bt=NoCorrelationBacktester(arm,prices)
            else:
                config.REBALANCE_WEEKS=52;bt=CohortBacktester(arm,prices,k)
            result=bt.run();m=metrics(result.loc[result.index>=common_start,"portfolio_value"])
            rows.append({"architecture":architecture,"phase":phase,**m,"benchmark_cagr":bench["cagr"],
                         "alpha_cagr":m["cagr"]-bench["cagr"]})
            print(f"{architecture} phase={phase:02d} CAGR={m['cagr']:.2%} alpha={m['cagr']-bench['cagr']:+.2%}",flush=True)
    table=pd.DataFrame(rows);table.to_csv(CSV,index=False)
    summary={}
    for name,g in table.groupby("architecture",sort=False):
        a=g.alpha_cagr;summary[name]={"phases":len(g),"median_alpha":float(a.median()),
          "worst_alpha":float(a.min()),"best_alpha":float(a.max()),"share_beating_index":float((a>0).mean()),
          "median_cagr":float(g.cagr.median()),"median_sharpe":float(g.sharpe.median())}
        summary[name]["robust"] = summary[name]["median_alpha"]>0 and summary[name]["share_beating_index"]>=.75
    robust=[n for n,s in summary.items() if s["robust"]]
    winner=max(robust,key=lambda n:(summary[n]["median_alpha"],summary[n]["worst_alpha"])) if robust else None
    report={"status":"PASS","parent_stage":parent["manifest_sha256"],"test":"N3-SR45-remediation",
      "common_window":{"start":str(common_start.date()),"end":str(common_dates[-1].date()),"weeks":len(common_dates)},
      "benchmark_metrics":bench,"architectures":summary,"winner":winner,
      "architecture_gate":"PASS" if winner else "FAIL","phase_selection_allowed":False,
      "holdout_used":False,"multiple_testing_arms":len(table)}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    stage=freeze_stage("02_phase_robust_rotation_remediation",[OUT,CSV,Path(__file__).resolve()],
      {"test":"N3-SR45-remediation","architecture_gate":report["architecture_gate"],"winner":winner,
       "phase_selection":False,"production":False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)

if __name__=="__main__":main()
