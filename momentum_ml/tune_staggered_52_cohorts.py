"""SR-35: 1, 4, or 13 overlapping sleeves with 52-week holding periods."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config
from backtest.backtester import MomentumBacktester

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/staggered_52_cohorts.json"
N=15


def offsets_for(k:int)->list[int]:
    if k not in (1,4,13): raise ValueError(k)
    return [i*(52//k) for i in range(k)]


class CohortSimulator(MomentumBacktester):
    def __init__(self,signals,prices,k):
        super().__init__(signals,prices,market_filter=False); self.k=k

    def _pick(self,date):
        d=self.signals.loc[[date]]
        d=d[d.selection_eligible.astype(bool)].sort_values("selection_rank",ascending=False)
        return list(d.ticker.head(N))

    def run(self):
        dates=self.signals.index.unique().sort_values(); cash=self.capital
        self._build_close_panel(dates); sleeves=[self._pick(dates[0]) for _ in range(self.k)]
        offsets=offsets_for(self.k); rows=[]
        for i,date in enumerate(dates):
            changed=False
            for j,offset in enumerate(offsets):
                if i>0 and i>=offset and (i-offset)%52==0:
                    sleeves[j]=self._pick(date); changed=True
            value=cash+self._portfolio_value(date)
            if i==0 or changed:
                weights={}
                for sleeve in sleeves:
                    for ticker in sleeve: weights[ticker]=weights.get(ticker,0)+1/(self.k*len(sleeve))
                cash=self._rebalance(date,weights,value,cash)
            rows.append({"Date":date,"portfolio_value":cash+self._portfolio_value(date),
                         "cash":cash,"n_positions":len(self._portfolio)})
        self._results=pd.DataFrame(rows).set_index("Date"); return self._results


def main():
    s=pd.read_csv(ROOT/"results/signals.csv",usecols=["Date","ticker","selection_rank","selection_eligible"],
                  parse_dates=["Date"]).set_index("Date").sort_index()
    dates=s.index.unique().sort_values(); cutoff=dates[-int(config.HOLDOUT_WEEKS)]
    s=s[s.index<cutoff]; prices=pd.read_pickle(ROOT/"results/abstention_price_data.pkl")
    results={"window":{"end_exclusive":str(cutoff.date()),"weeks":int(s.index.nunique())},"variants":{}}
    for k in (1,4,13):
        bt=CohortSimulator(s,prices,k); bt.run(); results["variants"][f"cohorts_{k}"]=bt.statistics()
        print(k,results["variants"][f"cohorts_{k}"],flush=True)
    OUT.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8"); print(OUT)

if __name__=="__main__": main()
