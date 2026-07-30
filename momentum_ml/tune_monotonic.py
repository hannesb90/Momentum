"""
tune_monotonic.py – Utvärderar om monotona restriktioner på fundamentala features
minskar överanpassning och förbättrar holdout-alfa för det nya LambdaRank-systemet.
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
from tune_universe import _train_lambdarank, _date_weights
from tune_objective_comparison import _build_signals_for_backtest
from tune_lambdarank_common import production_params, _relevance_labels


# Monotona restriktioner för fundamentala features
# +1 innebär att högre värde på featuren måste ge högre (eller lika) predikterad ranking.
MONOTONE_MAP = {
    "f_score": 1,
    "roa": 1,
    "fcf_margin": 1,
    "margin_delta": 1,
    "rev_growth_yoy": 1,
    "eps_growth_yoy": 1,
    "rev_growth": 1,
    "rev_accel": 1,
    "ni_growth": 1,
    "div_growth_yoy": 1,
}


def _train_lambdarank_monotonic(train_sub: pd.DataFrame, val_sub: pd.DataFrame, use_constraints: bool) -> lgb.Booster:
    """Tränar en LambdaRank-modell, valfritt med monotona restriktioner.
    production_params() (samma som tune_lambdarank_common.py) i stället för
    de tidigare hårdkodade ad-hoc-parametrarna - annars samma confound-
    mönster som Test 5/6/7. monotone_constraints läggs till separat ovanpå,
    påverkar inga andra hyperparametrar."""
    X_tr = train_sub[FEATURE_COLS].values
    X_va = val_sub[FEATURE_COLS].values

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    y_tr_rel = _relevance_labels(train_sub)
    y_va_rel = _relevance_labels(val_sub)

    w_tr = _date_weights(train_sub)

    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

    params = production_params()
    if use_constraints:
        # Skapa en lista med restriktioner i samma ordning som FEATURE_COLS
        constraints = [MONOTONE_MAP.get(col, 0) for col in FEATURE_COLS]
        params = {**params, "monotone_constraints": constraints}

    model = lgb.train(
        params,
        ds_tr,
        num_boost_round=500,
        valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)]
    )
    return model


def run_experiment(segment: str, tickers: list, raw_data: pd.DataFrame, model_df: pd.DataFrame, all_dates: pd.Index, purge_start: pd.Timestamp):
    print(f"\n[monotonic] Kör experiment för segment: {segment.upper()}")
    
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    
    test_preds_baseline = []
    test_preds_monotone = []
    
    last_model_base = None
    last_model_mono = None
    
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = model_df.loc[model_df.index.isin(train_d)]
        val_sub = model_df.loc[model_df.index.isin(val_d)]
        test_sub = model_df.loc[model_df.index.isin(test_d)]
        
        if len(test_sub) < 5:
            continue
            
        # Träna båda varianterna
        m_base = _train_lambdarank_monotonic(train_sub, val_sub, use_constraints=False)
        m_mono = _train_lambdarank_monotonic(train_sub, val_sub, use_constraints=True)
        
        last_model_base = m_base
        last_model_mono = m_mono
        
        X_te = test_sub[FEATURE_COLS].values
        
        # Spara prediktioner för baseline
        sdf_base = test_sub[["ticker"]].copy()
        sdf_base["_raw"] = m_base.predict(X_te)
        test_preds_baseline.append(sdf_base)
        
        # Spara prediktioner för monotone
        sdf_mono = test_sub[["ticker"]].copy()
        sdf_mono["_raw"] = m_mono.predict(X_te)
        test_preds_monotone.append(sdf_mono)
        
    # Holdout-prediktioner
    holdout_dates = all_dates[all_dates >= purge_start]
    if len(holdout_dates) and last_model_base is not None and last_model_mono is not None:
        ho_sub = model_df.loc[model_df.index.isin(holdout_dates)]
        X_ho = ho_sub[FEATURE_COLS].values
        
        sdf_hb = ho_sub[["ticker"]].copy()
        sdf_hb["_raw"] = last_model_base.predict(X_ho)
        test_preds_baseline.append(sdf_hb)
        
        sdf_hm = ho_sub[["ticker"]].copy()
        sdf_hm["_raw"] = last_model_mono.predict(X_ho)
        test_preds_monotone.append(sdf_hm)
        
    # Sammanställ signaler och kör backtests
    n_pos = 10 if segment == "large" else 20
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
    
    print("-" * 90)
    for name, pred_list in [("Baseline", test_preds_baseline), ("Monotonic Constraints", test_preds_monotone)]:
        full_preds = pd.concat(pred_list)
        signals = _build_signals_for_backtest(full_preds, n_pos)
        stats = _run_backtest(signals, raw_data, holdout_start)
        
        dev_res = stats["dev"]
        ho_res = stats["holdout"]
        
        print(f"  {name:<25}: dev CAGR={_pct(dev_res, 'CAGR'):+.2%} Sharpe={float(dev_res['Sharpe']):.2f} | "
              f"holdout CAGR={_pct(ho_res, 'CAGR'):+.2%} Sharpe={float(ho_res['Sharpe']) if ho_res else 0.0:.2f}")
    print("-" * 90)


def main():
    print("[monotonic] Startar monotona restriktioner-tuning...")
    
    # Hämta universum
    tickers_large, _, cap_tier_large, _ = load_sweden_universe(min_market_cap=["Large Cap", "Mid Cap"])
    tickers_small, _, cap_tier_small, _ = load_sweden_universe(min_market_cap=["Small Cap", "Micro Cap"])

    # (Tidigare skars till 120 st/segment pga fortytwolocals 1.8GB-tak - körs
    # nu på momentum.local med ~4x mer minne, hela universumet används.)
    all_tickers = list(set(tickers_large + tickers_small))
    
    # Konfigurera för 52v horisont
    config.FORWARD_WEEKS = 52
    config.REBALANCE_WEEKS = 52
    config.EMBARGO_WEEKS = 52
    
    raw_data = fetch_weekly_data(all_tickers, start="2010-01-01", end=None, use_cache=True)
    raw_data = filter_active_universe(raw_data)
    raw_data = filter_liquid_universe(raw_data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    
    # Bygg features
    feats = build_all_features(raw_data)
    
    # Kombinerad kategorisk mappning
    combined_sector_map = {}
    combined_cap_map = {}
    for cap_grp in (["Large Cap", "Mid Cap"], ["Small Cap", "Micro Cap"]):
        _, smap, cmap, _ = load_sweden_universe(min_market_cap=cap_grp)
        combined_sector_map.update(smap)
        combined_cap_map.update(cmap)
    config.SECTOR_MAP.update(combined_sector_map)
    config.CAP_TIER_MAP.update(combined_cap_map)
    
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=combined_cap_map)
    feats = attach_fundamentals_features(feats, segment="large", prices=raw_data)
    
    model_features = {t: f for t, f in feats.items() if config.CAP_TIER_MAP.get(t, "") != "Fond"}
    model_df = to_model_df(model_features)
    
    # Sortera ut datum
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    
    # Separera dataseten
    large_df = model_df[model_df["ticker"].isin(set(tickers_large))]
    small_df = model_df[model_df["ticker"].isin(set(tickers_small))]
    
    # Kör experimenten
    run_experiment("large", tickers_large, raw_data, large_df, all_dates, purge_start)
    run_experiment("small", tickers_small, raw_data, small_df, all_dates, purge_start)


if __name__ == "__main__":
    main()
