"""Backtest capital deployment for SEK 100k start + SEK 10k/month.

The frozen rank signal is unchanged. This isolates how new cash is deployed:
annual_only, underweight, equal_top15, or best_rank. Results include flow-adjusted
TWR (strategy quality) and XIRR/final wealth (investor experience).
"""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import brentq
import config
from backtest.backtester import MomentumBacktester

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/monthly_contribution_backtest.json"
START_CAPITAL = 100_000.0
MONTHLY = 10_000.0
N = 15
POLICIES = ("annual_only", "underweight", "equal_top15", "best_rank")


class ContributionSimulator(MomentumBacktester):
    def __init__(self, signals, prices, policy, start):
        super().__init__(signals[signals.index >= pd.Timestamp(start)], prices,
                         initial_capital=START_CAPITAL)
        self.policy = policy

    def _targets(self, date):
        if date not in self.signals.index: return []
        day = self.signals.loc[[date]]
        eligible = day[day.selection_eligible.astype(bool)]
        return list(eligible.sort_values("selection_rank", ascending=False).ticker.head(N))

    def _buy_value(self, ticker, date, gross_value, cash):
        price = self._get_price(ticker, date)
        if price is None or gross_value <= 0: return cash
        gross_value = min(float(gross_value), cash)
        gross_value = self._liquidity_cap(ticker, date, gross_value)
        rate = self._execution_cost_rate(ticker, date, gross_value)
        net = gross_value / (1.0 + rate)
        self._portfolio[ticker] = self._portfolio.get(ticker, 0.0) + net / price
        return cash - gross_value

    def _deploy(self, date, cash, portfolio_value):
        targets = self._targets(date)
        if not targets or cash <= 0 or self.policy == "annual_only": return cash
        if self.policy == "best_rank":
            return self._buy_value(targets[0], date, cash, cash)
        if self.policy == "equal_top15":
            per = cash / len(targets)
            for ticker in targets: cash = self._buy_value(ticker, date, per, cash)
            return cash
        desired = portfolio_value / len(targets)
        gaps = {}
        for ticker in targets:
            price = self._get_price(ticker, date)
            current = self._portfolio.get(ticker, 0.0) * price if price else 0.0
            gaps[ticker] = max(desired - current, 0.0)
        total = sum(gaps.values())
        if total <= 0: return cash
        available = cash
        for ticker, gap in gaps.items():
            cash = self._buy_value(ticker, date, available * gap / total, cash)
        return cash

    def run_with_flows(self):
        dates = self.signals.index.unique().sort_values(); cash = self.capital
        self._build_close_panel(dates); rows=[]; previous_month=None
        for i,date in enumerate(dates):
            flow = 0.0
            month=(date.year,date.month)
            if previous_month is not None and month != previous_month:
                cash += MONTHLY; flow = MONTHLY
            previous_month=month
            value_before = cash + self._portfolio_value(date)
            if i % int(config.REBALANCE_WEEKS) == 0:
                targets=self._targets(date)
                weights={t:1.0/len(targets) for t in targets} if targets else {}
                cash=self._rebalance(date,weights,value_before,cash)
            elif flow > 0:
                cash=self._deploy(date,cash,value_before)
            value=cash+self._portfolio_value(date)
            rows.append({"Date":date,"portfolio_value":value,"external_flow":flow,
                         "cash":cash,"n_positions":len(self._portfolio)})
        self._results=pd.DataFrame(rows).set_index("Date"); return self._results


def xirr(flows):
    d0=flows[0][0]
    def npv(r): return sum(v/(1+r)**((d-d0).days/365.25) for d,v in flows)
    try: return float(brentq(npv,-0.999,20.0))
    except ValueError: return float("nan")


def stats(frame):
    prev=frame.portfolio_value.shift(1)
    twr=((frame.portfolio_value-frame.external_flow)/prev-1).dropna()
    years=max((frame.index[-1]-frame.index[0]).days/365.25,1/52)
    nav=(1+twr).cumprod(); dd=nav/nav.cummax()-1
    flows=[(frame.index[0],-START_CAPITAL)]
    flows += [(d,-float(v)) for d,v in frame.external_flow.items() if v>0]
    flows += [(frame.index[-1],float(frame.portfolio_value.iloc[-1]))]
    volatility = float(twr.std())
    sharpe = float(twr.mean() / volatility * np.sqrt(52)) if volatility > 0 else float("nan")
    return {"TWR_CAGR":float((1+twr).prod()**(1/years)-1),
            "TWR_Sharpe":sharpe,
            "MaxDD":float(dd.min()),"XIRR":xirr(flows),
            "final_value":float(frame.portfolio_value.iloc[-1]),
            "contributed":float(START_CAPITAL+frame.external_flow.sum()),
            "mean_cash_pct":float((frame.cash/frame.portfolio_value).mean()),
            "weeks":len(frame)}


def benchmark(prices, dates):
    px=prices[config.INDEX_BENCHMARK_TICKER]["Close"].reindex(dates).ffill()
    cash=START_CAPITAL; units=0.0; rows=[]; prev_month=None
    cost=float(config.COMMISSION+config.SLIPPAGE)
    for i,(date,price) in enumerate(px.items()):
        flow=0.0; month=(date.year,date.month)
        if prev_month is not None and month!=prev_month: cash+=MONTHLY;flow=MONTHLY
        prev_month=month
        if cash>0 and pd.notna(price): units += cash*(1-cost)/price; cash=0.0
        rows.append({"Date":date,"portfolio_value":cash+units*price,"external_flow":flow,
                     "cash":cash,"n_positions":1})
    return pd.DataFrame(rows).set_index("Date")


def main():
    seg=config.SEGMENTS["large"]; config.REBALANCE_WEEKS=seg["rebalance_weeks"]
    config.MAX_POSITIONS=seg["max_positions"]
    signals=pd.read_csv(ROOT/"results/signals.csv",
                        usecols=["Date","ticker","selection_rank","selection_eligible"],
                        parse_dates=["Date"]).set_index("Date").sort_index()
    prices=pd.read_pickle(ROOT/"results/abstention_price_data.pkl")
    one_policy=os.environ.get("MC_POLICY"); one_start=os.environ.get("MC_START")
    part=ROOT/"results/monthly_contribution_parts"
    if os.environ.get("MC_AGGREGATE") == "1":
        results={}
        for start in ("2016-01-01","2022-01-01"):
            results[start]={}
            for policy in (*POLICIES,"benchmark"):
                path=part/f"{start}_{policy}.json"
                results[start]["xact_sverige_monthly" if policy == "benchmark" else policy] = json.loads(path.read_text())
        OUT.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps(results,indent=2,ensure_ascii=False)); print(OUT); return
    if one_policy == "benchmark" and one_start:
        dates=signals[signals.index>=pd.Timestamp(one_start)].index.unique().sort_values()
        result=stats(benchmark(prices,dates)); part.mkdir(parents=True,exist_ok=True)
        path=part/f"{one_start}_benchmark.json"; path.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2)); print(path); return
    if one_policy and one_start:
        sim=ContributionSimulator(signals,prices,one_policy,one_start)
        result=stats(sim.run_with_flows())
        part.mkdir(parents=True,exist_ok=True)
        path=part/f"{one_start}_{one_policy}.json"; path.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2)); print(path); return
    results={}
    for start in ("2016-01-01","2022-01-01"):
        results[start]={}
        for policy in POLICIES:
            print(f"[{start}] {policy}...",flush=True)
            sim=ContributionSimulator(signals,prices,policy,start)
            frame=sim.run_with_flows(); results[start][policy]=stats(frame)
        dates=signals[signals.index>=pd.Timestamp(start)].index.unique().sort_values()
        results[start]["xact_sverige_monthly"]=stats(benchmark(prices,dates))
    OUT.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(results,indent=2,ensure_ascii=False)); print(OUT)

if __name__=="__main__": main()
