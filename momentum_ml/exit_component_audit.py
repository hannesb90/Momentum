"""Isolate point-in-time entry and exit overlays on the frozen holdout."""
from __future__ import annotations

import argparse

import pandas as pd

import config
from backtest.backtester import MomentumBacktester
from backtest.integrated_backtest import IntegratedBacktester
from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe,
    load_sweden_universe,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("segment", choices=["large", "small"], default="large")
    args = ap.parse_args()
    seg = config.SEGMENTS[args.segment]
    signals = pd.read_csv(
        f"{config.anchor(seg['results_dir'])}/signals.csv",
        parse_dates=["Date"]).set_index("Date")
    tickers, sector_map, _, _ = load_sweden_universe(
        min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(
        tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(
        data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    dates = signals.index.unique().sort_values()
    holdout_start = dates[-config.HOLDOUT_WEEKS]
    variants = [
        ("baseline", False, False, False),
        ("hardiness", True, False, False),
        ("insider", False, True, False),
        ("sellwatch", False, False, True),
        ("all", True, True, True),
    ]
    print("variant,CAGR,Sharpe,Sortino,Max Drawdown,Win Rate")
    for name, hardiness, insider, sellwatch in variants:
        if name == "baseline":
            bt = MomentumBacktester(signals, data)
        else:
            bt = IntegratedBacktester(
                signals, data, hold_fund_enabled=hardiness,
                insider_enabled=insider, sellwatch_enabled=sellwatch)
        bt.run()
        stats = bt.statistics_for_period(start=holdout_start)
        print(name + "," + ",".join(str(stats[k]) for k in (
            "CAGR", "Sharpe", "Sortino", "Max Drawdown", "Win Rate")))


if __name__ == "__main__":
    main()
