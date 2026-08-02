"""
tune_refill_discount.py – [SCN-SÄLJ-4] REFILL_DISCOUNT=0,10 aldrig svept/
validerad (EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #20). portfolio.py::
_refill_candidates() är ren rådgivning (köper inget, mäts aldrig historiskt)
– testar här den prisbaserade KÄRNAN av regeln kausalt i en riktig backtest:
efter en säljvaktens nivå-2-trim (delförsäljning, redan implementerad i
backtest/integrated_backtest.py::_apply_sellwatch) vid pris P, köp TILLBAKA
upp till pre-trim-storleken om kursen sedan faller >= REFILL_DISCOUNT under P
och positionen fortfarande hålls.

FÖRENKLING mot originalregeln (samma typ av begränsning som #135/SCN-HÅLL-1):
"caset håller fortfarande" (röda flaggor/värderingszon/ROE-bar) kräver
_load_scores()-ögonblicksbilder utan historik - inte kausalt testbart här.
Testar bara den prisbaserade kärnmekaniken (steg 1-3 i portfolio.py:s egen
numrering), inte steg 4.

Sveper 5/10/15/20% mot en baslinje UTAN påfyllnad (bara nivå-2-trim, ingen
återköp).

    /opt/momentum/venv/bin/python3 tune_refill_discount.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from backtest.integrated_backtest import IntegratedBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

DISCOUNTS = [0.05, 0.10, 0.15, 0.20]


class RefillBacktester(IntegratedBacktester):
    def __init__(self, *args, discount: float, **kwargs):
        super().__init__(*args, hold_fund_enabled=False, insider_enabled=False,
                          sellwatch_enabled=True, **kwargs)
        self.discount = discount
        self._trim_price: dict = {}      # ticker -> pris vid nivå-2-trim
        self._trim_shares: dict = {}     # ticker -> antal sålda aktier vid trimmen
        self.n_refills = 0

    def _apply_sellwatch(self, date, cash):
        before = dict(self._portfolio)
        cash = super()._apply_sellwatch(date, cash)
        for t, shares_before in before.items():
            shares_after = self._portfolio.get(t, 0.0)
            if t in self._level2_done and shares_after < shares_before and t not in self._trim_price:
                price = self._get_price(t, date)
                if price:
                    self._trim_price[t] = price
                    self._trim_shares[t] = shares_before - shares_after
        for t in list(self._trim_price):
            if t not in self._portfolio:
                self._trim_price.pop(t, None)
                self._trim_shares.pop(t, None)
        return cash

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        for t in list(self._trim_price):
            if t not in self._portfolio or t not in target_weights:
                continue   # sålt helt, eller inte längre en kärnkandidat - ingen påfyllnad
            price = self._get_price(t, date)
            if not price:
                continue
            if price <= self._trim_price[t] * (1 - self.discount):
                buy_shares = self._trim_shares[t]
                cost = buy_shares * price
                cost_rate = self._execution_cost_rate(t, date, cost)
                total_cost = cost * (1 + cost_rate)
                if cash >= total_cost:
                    self._portfolio[t] = self._portfolio.get(t, 0.0) + buy_shares
                    cash -= total_cost
                    self.n_refills += 1
                self._trim_price.pop(t, None)
                self._trim_shares.pop(t, None)
        return super()._rebalance(date, target_weights, portfolio_value, cash)


def main():
    seg = config.SEGMENTS["large"]
    config.RESULTS_DIR = seg["results_dir"]
    if "max_positions" in seg:
        config.MAX_POSITIONS = seg["max_positions"]
    if "forward_weeks" in seg:
        config.FORWARD_WEEKS = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    if "atr_stop_enabled" in seg:
        config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    holdout_start = sig.index.unique().sort_values()[-config.HOLDOUT_WEEKS] \
        if len(sig.index.unique()) > config.HOLDOUT_WEEKS else None

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("[refill] Baslinje (sellwatch PÅ, ingen påfyllnad)...")
    bt_base = IntegratedBacktester(sig, data, hold_fund_enabled=False, insider_enabled=False, sellwatch_enabled=True)
    bt_base.run()

    results = {}
    for d in DISCOUNTS:
        print(f"[refill] Discount={d:.0%}...")
        bt = RefillBacktester(sig, data, discount=d)
        bt.run()
        results[d] = bt

    print("\n" + "=" * 90)
    print("Full backtest (large) – ingen påfyllnad vs REFILL_DISCOUNT-svep")
    print("=" * 90)
    for name, bt in [("baslinje (ingen påfyllnad)", bt_base)] + [(f"discount={d:.0%}", results[d]) for d in DISCOUNTS]:
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        n_refills = getattr(bt, "n_refills", None)
        print(f"  {name:<28}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}"
              + (f" | påfyllnader={n_refills}" if n_refills is not None else ""))

    print("\n[refill] Klart.")


if __name__ == "__main__":
    main()
