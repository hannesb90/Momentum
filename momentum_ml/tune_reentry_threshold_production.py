"""
tune_reentry_threshold_production.py – [SCN-REBAL-4] Test 11:s re-entry-
tröskel (docs/MOMENTUM_ROTATION_TESTPLAN.md, UTVECKLINGSLOGG #102) omskriven
mot PRODUKTIONENS faktiska kalenderbaserade `MomentumBacktester`/
`_rebalance()`, i stället för testplanens egen förenklade `TrackedBacktester`
(rå veckovis baslinje, uttryckligen INTE produktionens kalenderbaslinje).
Detta ÄR den brygga SCN-REBAL-4 (EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #18)
efterfrågar: Test 11 var den mest konsekventa SHADOW-kandidaten av hela
Test 9-12-batchen (modern/holdout-förbättring utan overfitting-tecken) men
har aldrig körts mot den riktiga produktionsmekaniken.

Mekanik (samma koncept som ReentryThresholdBacktester, ombyggd för
REBALANCE_WEEKS=52-kalendern): en aktie som lämnar topp-N vid en
ombalansering får sin `selection_rank` VID EXIT sparad. Vid en SENARE
ombalansering blockeras återköp av samma aktie tills dess aktuella
`selection_rank` >= exit-rank + threshold (percentilenheter, 0-1-skala).
Ingen påfyllnad av blockerad plats (samma konservativa val som #127/#139).

Trösklar: 0 (kontroll, = dagens beteende exakt), 0.05, 0.10 (matchar
originaltestets threshold_5pp/threshold_10pp).

    /opt/momentum/venv/bin/python3 tune_reentry_threshold_production.py
"""
import sys
sys.path.insert(0, ".")
import config
import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

THRESHOLDS = [0.0, 0.05, 0.10]


class ReentryThresholdBacktester(MomentumBacktester):
    def __init__(self, *args, threshold: float, **kwargs):
        super().__init__(*args, **kwargs)
        self.threshold = threshold
        self._exit_rank: dict = {}
        self.n_blocked = 0

    def _rank_of(self, date, ticker):
        if date not in self.signals.index:
            return None
        day = self.signals.loc[[date]] if isinstance(self.signals.loc[date], pd.Series) else self.signals.loc[date]
        row = day[day["ticker"] == ticker]
        if row.empty or "selection_rank" not in row.columns:
            return None
        return float(row["selection_rank"].iloc[0])

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        held_before = set(self._portfolio.keys())
        core = set(target_weights.keys())

        if self.threshold > 0:
            filtered = {}
            for t, w in target_weights.items():
                if t in held_before or t not in self._exit_rank:
                    filtered[t] = w
                    continue
                cur_rank = self._rank_of(date, t)
                if cur_rank is not None and cur_rank >= self._exit_rank[t] + self.threshold:
                    filtered[t] = w
                    self._exit_rank.pop(t, None)
                else:
                    self.n_blocked += 1
            target_weights = filtered

        for t in held_before - core:
            r = self._rank_of(date, t)
            if r is not None:
                self._exit_rank[t] = r

        return super()._rebalance(date, target_weights, portfolio_value, cash)


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
    for th in THRESHOLDS:
        print(f"[reentry] threshold={th:.0%}...")
        bt = ReentryThresholdBacktester(sig, data, threshold=th)
        bt.run()
        results[th] = bt

    print("\n" + "=" * 90)
    print("Full backtest (large) – Test 11 re-entry-tröskel mot produktionens kalenderombalansering")
    print("=" * 90)
    for th, bt in results.items():
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  threshold={th:>5.0%}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%} | blockerade återköp={bt.n_blocked}")

    print("\n[reentry] Klart.")


if __name__ == "__main__":
    main()
