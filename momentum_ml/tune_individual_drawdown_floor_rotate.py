"""
tune_individual_drawdown_floor_rotate.py – [SCN-HÅLL-4] steg 2: en
cash-drag-medveten variant av individ-drawdown-golvet (uppföljning på #141,
användarens uttryckliga begäran 2026-07-30). #141 kvantifierade en verklig
risk (28/383 hållperioder, 7,3%, med individuell drawdown ≤-40%, 68% av dem
osynliga för portföljnivåns Drawdown Guard) men #130 visade samtidigt att
en enkel "sälj till kontanter"-stop (ATR-baserad) NETTO FÖRSÄMRADE resultatet
via cash-drag (~27 veckors kontantperiod per exit i ett segment där
benchmarken steg 72% av gångerna under just den tiden).

Den här varianten testar om PROBLEMET (cash-drag) går att undvika genom att
ROTERA i stället för att gå till kontanter: när en hållen position faller
>= DD_THRESHOLD (default -40%, samma tröskel som #141) från sin egen peak,
sälj den och köp OMEDELBART den bäst rankade kandidaten som INTE redan
hålls (samma vecka, samma vikt) - i stället för att låta kapitalet stå
kontant till nästa schemalagda ombalansering.

Tre varianter jämförs:
  baseline    – ingen golv-mekanism alls (dagens produktionsbeteende).
  cash_exit   – golvet säljer till KONTANTER (replikerar #130:s redan kända
                cash-drag-problem som en kontrollpunkt, inte ett nytt förslag).
  rotate_exit – golvet säljer och ROTERAR OMEDELBART in nästa bästa
                kandidat (den nya, cash-drag-medvetna varianten).

    /opt/momentum/venv/bin/python3 tune_individual_drawdown_floor_rotate.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

DD_THRESHOLD = -0.40


class DrawdownFloorBacktester(MomentumBacktester):
    """mode: None (av), 'cash' (sälj till kontanter), 'rotate' (rotera in nästa kandidat)."""

    def __init__(self, *args, mode=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self._dd_peak: dict = {}
        self.n_triggers = 0

    def _update_dd_peaks(self, date):
        for t in self._portfolio:
            price = self._get_price(t, date)
            if price is None:
                continue
            self._dd_peak[t] = max(self._dd_peak.get(t, price), price)
        for t in list(self._dd_peak):
            if t not in self._portfolio:
                self._dd_peak.pop(t, None)

    def _apply_drawdown_floor(self, date, cash):
        if self.mode is None or not self._portfolio:
            return cash
        self._update_dd_peaks(date)
        for t in list(self._portfolio.keys()):
            price = self._get_price(t, date)
            peak = self._dd_peak.get(t)
            if price is None or not peak:
                continue
            dd = price / peak - 1
            if dd > DD_THRESHOLD:
                continue
            self.n_triggers += 1
            shares = self._portfolio.pop(t)
            trade_value = shares * price
            cost_rate = self._execution_cost_rate(t, date, trade_value)
            proceeds = trade_value * (1 - cost_rate)
            self._dd_peak.pop(t, None)

            if self.mode == "cash":
                cash += proceeds
                continue

            # rotate: köp bäst rankade kandidat som INTE redan hålls, denna vecka
            if date not in self.signals.index:
                cash += proceeds
                continue
            day = self.signals.loc[[date]] if isinstance(self.signals.loc[date], pd.Series) else self.signals.loc[date]
            cand = day[(day["selection_eligible"] == 1) & (~day["ticker"].isin(self._portfolio.keys())) & (day["ticker"] != t)]
            if cand.empty:
                cash += proceeds
                continue
            best = cand.sort_values("selection_rank", ascending=False).iloc[0]
            buy_ticker = best["ticker"]
            buy_price = self._get_price(buy_ticker, date)
            if not buy_price:
                cash += proceeds
                continue
            buy_cost_rate = self._execution_cost_rate(buy_ticker, date, proceeds)
            buy_value = proceeds / (1 + buy_cost_rate)
            self._portfolio[buy_ticker] = self._portfolio.get(buy_ticker, 0.0) + buy_value / buy_price
        return cash

    def _trend_exit(self, date, cash):
        cash = self._apply_drawdown_floor(date, cash)
        return super()._trend_exit(date, cash)

    def _atr_stop_exit(self, date, cash):
        cash = super()._atr_stop_exit(date, cash)
        return cash


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    holdout_start = sig.index.unique().sort_values()[-config.HOLDOUT_WEEKS] \
        if len(sig.index.unique()) > config.HOLDOUT_WEEKS else None

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    results = {}
    for name, mode in (("baseline", None), ("cash_exit", "cash"), ("rotate_exit", "rotate")):
        print(f"[dd_rotate] Kör variant: {name}...")
        bt = DrawdownFloorBacktester(sig, data, mode=mode)
        bt.run()
        results[name] = bt

    print("\n" + "=" * 90)
    print(f"Full backtest (large) – individ-drawdown-golv ({DD_THRESHOLD:.0%}): kontant-exit vs rotation")
    print("=" * 90)
    for name, bt in results.items():
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  {name:<14}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%} | triggers={bt.n_triggers}")

    print("\n[dd_rotate] Klart.")


if __name__ == "__main__":
    main()
