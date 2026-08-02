"""
tune_regime_exposure.py – Utvärderar olika marknadsfilter-inställningar (Nivå 2)
på det nya LambdaRank-baserade stock-picking-systemet (Nivå 1) med 52 veckors innehavstid.
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
from features.feature_engineering import build_all_features, attach_categorical_features, attach_fundamentals_features, to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from backtest.backtester import MomentumBacktester
from tune_abstention_gate import _run_backtest, _pct
from tune_universe import _train_lambdarank
from tune_objective_comparison import _build_signals_for_backtest


def run_experiment(segment: str, tickers: list, raw_data: pd.DataFrame, model_df: pd.DataFrame, all_dates: pd.Index, purge_start: pd.Timestamp):
    print(f"\n[regime] Kör experiment för segment: {segment.upper()}")
    
    # 1. Träna walk-forward modeller för att få testprediktioner
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    
    test_preds = []
    last_model = None
    
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = model_df.loc[model_df.index.isin(train_d)]
        val_sub = model_df.loc[model_df.index.isin(val_d)]
        test_sub = model_df.loc[model_df.index.isin(test_d)]
        
        if len(test_sub) < 5:
            continue
            
        m = _train_lambdarank(train_sub, val_sub)
        last_model = m
        
        X_te = test_sub[FEATURE_COLS].values
        preds = m.predict(X_te)
        
        sdf = test_sub[["ticker"]].copy()
        sdf["_raw"] = preds
        test_preds.append(sdf)
        
    # Holdout-prediktioner
    holdout_dates = all_dates[all_dates >= purge_start]
    if len(holdout_dates) and last_model is not None:
        ho_sub = model_df.loc[model_df.index.isin(holdout_dates)]
        X_ho = ho_sub[FEATURE_COLS].values
        preds_ho = last_model.predict(X_ho)
        
        sdf_ho = ho_sub[["ticker"]].copy()
        sdf_ho["_raw"] = preds_ho
        test_preds.append(sdf_ho)
        
    full_preds = pd.concat(test_preds)
    
    # Skapa signaler
    n_pos = 10 if segment == "large" else 20
    signals = _build_signals_for_backtest(full_preds, n_pos)
    
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
    
    # Utvärdera olika marknadsfilter-scenarier
    scenarios = {
        "1. No Filter (100% exp)": {"market_filter": False, "exposure": {"bull": 1.0, "sideways": 1.0, "bear": 1.0}},
        "2. Bear 0.50 (Soft protection)": {"market_filter": True, "exposure": {"bull": 1.0, "sideways": 1.0, "bear": 0.50}},
        "3. Bear 0.25 (Standard prod)": {"market_filter": True, "exposure": {"bull": 1.0, "sideways": 1.0, "bear": 0.25}},
        "4. Bear 0.00 (Full Bear Exit)": {"market_filter": True, "exposure": {"bull": 1.0, "sideways": 1.0, "bear": 0.00}},
        "5. Bear 0.25, Sideways 0.50": {"market_filter": True, "exposure": {"bull": 1.0, "sideways": 0.50, "bear": 0.25}},
    }
    
    print("-" * 90)
    print(f"{'Scenario':<30} | {'Dev CAGR':<10} {'Dev Sharpe':<10} | {'Holdout CAGR':<12} {'Holdout Sharpe':<12}")
    print("-" * 90)
    
    for name, params in scenarios.items():
        # Sätt tillfälligt i config
        config.MARKET_FILTER_EXPOSURE = params["exposure"]
        
        # Kör backtester
        bt = MomentumBacktester(signals, raw_data, market_filter=params["market_filter"])
        res = bt.run()
        
        # Dela upp i dev/holdout
        dev_res = res[res.index < holdout_start]
        ho_res = res[res.index >= holdout_start]
        
        def stats(sub_df):
            if len(sub_df) < 10:
                return 0.0, 0.0
            ret = sub_df["portfolio_value"].pct_change().dropna()
            if len(ret) == 0:
                return 0.0, 0.0
            cagr = (sub_df["portfolio_value"].iloc[-1] / sub_df["portfolio_value"].iloc[0]) ** (52.0 / len(sub_df)) - 1
            std = ret.std() * np.sqrt(52)
            sharpe = (cagr - 0.02) / std if std > 0 else 0.0
            return cagr, sharpe
            
        c_dev, s_dev = stats(dev_res)
        c_ho, s_ho = stats(ho_res)
        
        print(f"{name:<30} | {c_dev:+10.2%} {s_dev:10.2f} | {c_ho:+12.2%} {s_ho:12.2f}")
    print("-" * 90)


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg = config.SEGMENTS.get(segment, config.SEGMENTS[config.DEFAULT_SEGMENT])

    # ── Applicera ALLA segment-overrides ─────────────────────────────────────
    config.RESULTS_DIR      = seg["results_dir"]
    config.MAX_POSITIONS    = seg.get("max_positions",    config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "index_ticker"     in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
    if "gate_enabled"     in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
    if "gate_min"         in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
    if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "forward_weeks"    in seg:
        config.FORWARD_WEEKS   = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
        config.EMBARGO_WEEKS   = seg["embargo_weeks"]
    if "drop_features"    in seg:
        config.DROP_FEATURES = seg["drop_features"]
        dropped = set(seg["drop_features"])
        filtered = [c for c in FEATURE_COLS if c not in dropped]
        FEATURE_COLS.clear()
        FEATURE_COLS.extend(filtered)
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]

    print(f"[regime] Startar marknadsfilter-tuning för segment={segment}")
    print(f"  forward_weeks={config.FORWARD_WEEKS}, max_positions={config.MAX_POSITIONS}, "
          f"atr_stop={config.ATR_STOP_ENABLED}, drop_features={len(getattr(config,'DROP_FEATURES',[]))} st")

    # Hämta universum för valt segment
    tickers, _, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])

    raw_data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    raw_data = filter_active_universe(raw_data)
    raw_data = filter_liquid_universe(raw_data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    # Bygg features
    feats = build_all_features(raw_data)

    _, smap, cmap, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(smap)
    config.CAP_TIER_MAP.update(cmap)

    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cmap)
    feats = attach_fundamentals_features(feats, segment=segment, prices=raw_data)

    model_features = {t: f for t, f in feats.items()
                      if config.CAP_TIER_MAP.get(t, "") != "Fond"}
    model_df = to_model_df(model_features)

    all_dates  = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]

    run_experiment(segment, tickers, raw_data, model_df, all_dates, purge_start)


if __name__ == "__main__":
    main()
