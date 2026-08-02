"""Walk-forward-liknande viktgrid mellan Large- och Small-sleeves.

Använder sparade, historiska signaler/modeller; ändrar aldrig produktionens
segmentvikter. Resultatet är en *svensk aktiesleeve* som veckovis återställs
till vald Large/Small-vikt.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config
from backtest.backtester import MomentumBacktester
from data.data_loader import (fetch_weekly_data, filter_active_universe,
                              filter_liquid_universe, load_sweden_universe)

ROOT = Path(__file__).parent.parent
OUT = ROOT / "results" / "large_small_allocation_grid.csv"


def _apply_segment(name: str) -> dict:
    seg = config.SEGMENTS[name]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    config.MOMENTUM_GATE_ENABLED = seg.get("gate_enabled", config.MOMENTUM_GATE_ENABLED)
    config.MOMENTUM_GATE_MIN = seg.get("gate_min", config.MOMENTUM_GATE_MIN)
    config.ATR_STOP_ENABLED = seg.get("atr_stop_enabled", config.ATR_STOP_ENABLED)
    config.MARKET_FILTER_EXPOSURE = seg.get("market_filter_exposure", config.MARKET_FILTER_EXPOSURE)
    config.FORWARD_WEEKS = seg.get("forward_weeks", config.FORWARD_WEEKS)
    config.REBALANCE_WEEKS = seg.get("rebalance_weeks", config.REBALANCE_WEEKS)
    config.EMBARGO_WEEKS = seg.get("embargo_weeks", config.EMBARGO_WEEKS)
    return seg


def _price_data(seg: dict) -> dict:
    tickers, sectors, caps, names = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sectors)
    config.CAP_TIER_MAP.update(caps)
    config.NAME_MAP.update(names)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    return filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)


def _sleeve_large() -> pd.Series:
    seg = _apply_segment("large")
    signals = pd.read_csv(ROOT / "results" / "signals.csv", index_col=0, parse_dates=True)
    bt = MomentumBacktester(signals, _price_data(seg), market_filter=True)
    return bt.run()["portfolio_value"].rename("large")


def _sleeve_small() -> pd.Series:
    _apply_segment("small")
    from tune_entry_policy_backtest import _load_state
    from models.ensemble import MomentumEnsemble, build_full_output
    from features.feature_engineering import FEATURE_COLS

    features, data, lgbm, _ = _load_state()
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5]))
             for t, f in features.items() if len(f.dropna(subset=FEATURE_COLS[:5]))}
    feature_dfs = {t: f.assign(ticker=t) for t, f in features.items()}
    signals = build_full_output(preds, None, feature_dfs, MomentumEnsemble())
    bt = MomentumBacktester(signals, data, market_filter=True)
    return bt.run()["portfolio_value"].rename("small")


def _metrics(values: pd.Series) -> dict:
    r = values.pct_change().dropna()
    years = len(r) / 52
    cagr = (values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1
    sharpe = r.mean() / r.std(ddof=0) * np.sqrt(52) if r.std(ddof=0) else np.nan
    max_dd = (values / values.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": max_dd}


def main() -> None:
    large, small = _sleeve_large(), _sleeve_small()
    rets = pd.concat([large.pct_change(), small.pct_change()], axis=1, join="inner").dropna()
    if len(rets) < 104:
        raise RuntimeError(f"För kort gemensam historik: {len(rets)} veckor")
    rows = []
    for small_w in (0.0, 0.25, 0.50, 0.75, 1.0):
        sleeve = (1 + (1 - small_w) * rets["large"] + small_w * rets["small"]).cumprod()
        holdout = sleeve.iloc[-104:]
        m, h = _metrics(sleeve), _metrics(holdout)
        rows.append({"large_weight": 1-small_w, "small_weight": small_w,
                     "start": sleeve.index.min().date(), "end": sleeve.index.max().date(),
                     "weeks": len(sleeve), **m,
                     "holdout_cagr": h["cagr"], "holdout_sharpe": h["sharpe"],
                     "holdout_max_drawdown": h["max_drawdown"],
                     "sweden_15pct_annualized_return_contribution": 0.15 * m["cagr"]})
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False, float_format=lambda x: f"{x:.2%}"))
    print(f"\nSparat: {OUT}")


if __name__ == "__main__":
    main()
