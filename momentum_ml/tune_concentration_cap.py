"""
tune_concentration_cap.py – TESTKATALOG_INFOR_KORNING_2026-07-30.md A7:
koncentrationstak mellan årsrebalanseringar. #161 kvantifierade verklig
viktdrift (spridning dubblas i snitt över en cykel, enskilda positioner
upp mot 28-35% i volatila år som 2020/2022) - ingen befintlig mekanism
trimmar det mellan schemalagda ombalanseringar. Testar en enkel veckovis
trimregel: om en positions vikt överstiger taket, sälj ner till taket
(kapitalet blir kassa - enklaste, mest konservativa varianten, samma
"gå till kassa"-princip som redan testade trend_exit/atr_stop, INTE en ny
rotationsmekanism).

Beslutskriterium (samma som #161/A7 anger): får INTE kapa netto-CAGR.
Trösklar: 20% och 25%.

    /opt/momentum/venv/bin/python3 tune_concentration_cap.py
"""
import sys
sys.path.insert(0, ".")
import config
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

import pandas as pd
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe, fetch_weekly_data, filter_active_universe, filter_liquid_universe

CAPS = [0.20, 0.25]


class ConcentrationCapBacktester(MomentumBacktester):
    def __init__(self, *a, cap=None, **k):
        super().__init__(*a, **k)
        self.cap = cap
        self.n_trims = 0

    def _apply_cap(self, date, cash):
        if self.cap is None or not self._portfolio:
            return cash
        pv = cash + self._portfolio_value(date)
        if pv <= 0:
            return cash
        for t in list(self._portfolio.keys()):
            price = self._get_price(t, date)
            if not price:
                continue
            shares = self._portfolio[t]
            weight = shares * price / pv
            if weight > self.cap:
                self.n_trims += 1
                target_value = pv * self.cap
                target_shares = target_value / price
                sell_shares = shares - target_shares
                trade_value = sell_shares * price
                cost_rate = self._execution_cost_rate(t, date, trade_value)
                proceeds = trade_value * (1 - cost_rate)
                self._portfolio[t] = target_shares
                cash += proceeds
        return cash

    def _trend_exit(self, date, cash):
        cash = self._apply_cap(date, cash)
        return super()._trend_exit(date, cash)


def main():
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

    print("[cap] Baslinje (inget tak)...")
    bt_base = MomentumBacktester(sig, data)
    bt_base.run()
    results = {"baseline (inget tak)": bt_base}
    for cap in CAPS:
        print(f"[cap] Tak={cap:.0%}...")
        bt = ConcentrationCapBacktester(sig, data, cap=cap)
        bt.run()
        results[f"tak={cap:.0%}"] = bt

    print("\n" + "=" * 90)
    print("Full backtest (large) - koncentrationstak mellan ombalanseringar")
    print("=" * 90)
    for name, bt in results.items():
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        n_trims = getattr(bt, "n_trims", None)
        print(f"  {name:<20}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}"
              + (f" | trimningar={n_trims}" if n_trims is not None else ""))

    print("\n[cap] Klart.")


if __name__ == "__main__":
    main()
