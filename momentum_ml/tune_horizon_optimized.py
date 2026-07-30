"""
tune_horizon_optimized.py – Utvärderar om 13 veckors holdingperiod fortfarande är optimal
mot den nya produktionsbaslinjen genom att testa 4, 8, 13, 26 och 52 veckor.
"""
import sys
import gc
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features, to_model_df, FEATURE_COLS
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report

HORIZONS = [4, 8, 13, 26, 52]


def main():
    seg = config.SEGMENTS["large"]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    if "drop_features" in seg:
        config.DROP_FEATURES = seg["drop_features"]
        _dropped = set(seg["drop_features"])
        FEATURE_COLS[:] = [c for c in FEATURE_COLS if c not in _dropped]

    # 1. Hämta universum och rådata
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)
    raw_data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    raw_data = filter_active_universe(raw_data)
    raw_data = filter_liquid_universe(raw_data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    print("\n" + "=" * 80)
    print("  UTVÄRDERING AV INNEHAVSTID (HOLDING PERIOD SWEEP) ")
    print("=" * 80)
    print(f"  {'Innehav (v)':<12} {'dev CAGR':<10} {'dev Sharpe':<10} {'holdout CAGR':<14} {'holdout Sharpe':<14}")
    print("-" * 80)

    for fw in HORIZONS:
        # Uppdatera konfigurationer för denna horisont
        config.FORWARD_WEEKS = fw
        config.REBALANCE_WEEKS = fw
        config.EMBARGO_WEEKS = fw

        # Re-engineera features eftersom target (forward return) förändras med horisonten
        feats = build_all_features(raw_data)
        feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
        feats = attach_fundamentals_features(feats, segment="large", prices=raw_data)
        # Exkludera ETF/fonder
        model_features = {t: f for t, f in feats.items() if config.CAP_TIER_MAP.get(t, "") != "Fond"}
        mdf = to_model_df(model_features)
        
        all_dates = mdf.index.unique().sort_values()
        holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
        dev_df = mdf[mdf.index < holdout_start] if holdout_start is not None else mdf

        # Skapa och träna vår nya produktions-LambdaRank modell
        lgbm = MomentumLGBM()
        lgbm.fit_walk_forward(dev_df)

        # Generera prediktioner (utan fillna(0) eller dropna eftersom vi kör native NaN)
        preds = {t: lgbm.predict(f) for t, f in feats.items() if len(f) > 0}
        
        sig = build_full_output(
            preds, None, {t: f.assign(ticker=t) for t, f in feats.items()},
            MomentumEnsemble(), ta_filter="score"
        )
        
        # Kör backtest (inkluderar marknadsskydd baserat på inställningar)
        bt = MomentumBacktester(sig, raw_data, market_filter=True)
        bt.run()
        
        overall = bt.statistics()
        dev_stats = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        ho_stats = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None

        ho_cagr = ho_stats.get("CAGR", "–") if ho_stats else "–"
        ho_sharpe = ho_stats.get("Sharpe", "–") if ho_stats else "–"

        print(f"  {fw:<12d} {dev_stats['CAGR']:<10} {dev_stats['Sharpe']:<10} {ho_cagr:<14} {ho_sharpe:<14}")
        
        # Rensa minne
        del feats, mdf, dev_df, lgbm, preds, sig, bt
        gc.collect()

    print("-" * 80)
    print("[horizon] Svep klart.")


if __name__ == "__main__":
    main()
