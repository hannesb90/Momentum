"""
tune_universe.py – Utvärderar om Large/Mid och Small/Micro bör tränas i separata modeller
eller om en gemensam LambdaRank-modell ger bättre urval.
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
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from tune_abstention_gate import _run_backtest, _pct
from tune_objective_comparison import _slice_sorted, _eval_on_test, _rank_stability, _build_signals_for_backtest
from tune_lambdarank_common import production_params, _relevance_labels


def _date_weights(sub: pd.DataFrame) -> np.ndarray:
    """Tidsutjämning (1/n per datum) för förlustfunktionen."""
    sizes = sub.groupby(level=0).size()
    return (1.0 / sizes.reindex(sub.index)).values.astype(np.float32)


def _train_lambdarank(train_sub: pd.DataFrame, val_sub: pd.DataFrame) -> lgb.Booster:
    """Tränar en LambdaRank-modell med produktionens EXAKTA hyperparametrar
    (production_params(), samma som tune_lambdarank_common.py använder för
    Test 5/6/7) - de tidigare hårdkodade ad-hoc-parametrarna (learning_rate=
    0.01, min_data_in_leaf=100, ...) gav en orättvis jämförelse mot vad
    produktionen faktiskt kör, samma confound-mönster som Test 5/6/7."""
    X_tr = train_sub[FEATURE_COLS].values
    X_va = val_sub[FEATURE_COLS].values

    train_groups = train_sub.groupby(level=0).size().values
    val_groups = val_sub.groupby(level=0).size().values

    y_tr_rel = _relevance_labels(train_sub)
    y_va_rel = _relevance_labels(val_sub)

    w_tr = _date_weights(train_sub)

    ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
    ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

    model = lgb.train(
        production_params(),
        ds_tr,
        num_boost_round=500,
        valid_sets=[ds_va],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)]
    )
    return model


def main():
    # 1. Hämta universum för Large/Mid samt Small/Micro
    print("[universe] Laddar universum...")
    tickers_large, _, cap_tier_large, _ = load_sweden_universe(min_market_cap=["Large Cap", "Mid Cap"])
    tickers_small, _, cap_tier_small, _ = load_sweden_universe(min_market_cap=["Small Cap", "Micro Cap"])

    # (Tidigare skars tickerlistorna ned till 100 st vardera pga fortytwolocals
    # 1.8GB RAM-tak - körs nu på momentum.local med ~4x mer minne, så hela
    # universumet används för ett representativt resultat.)
    all_tickers = list(set(tickers_large + tickers_small))
    
    # 2. Hämta data och bygg features (båda segmenten använder nu 52v horisont)
    config.FORWARD_WEEKS = 52
    config.REBALANCE_WEEKS = 52
    config.EMBARGO_WEEKS = 52
    
    raw_data = fetch_weekly_data(all_tickers, start="2010-01-01", end=None, use_cache=True)
    raw_data = filter_active_universe(raw_data)
    raw_data = filter_liquid_universe(raw_data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    
    # Bygg features
    feats = build_all_features(raw_data)
    # Kombinerad kategorisk mappning
    large_sec, _, _, _ = load_sweden_universe(min_market_cap=["Large Cap", "Mid Cap"])
    small_sec, _, _, _ = load_sweden_universe(min_market_cap=["Small Cap", "Micro Cap"])
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
    
    # Separera dataseten för utvärdering
    large_tickers = set(tickers_large)
    small_tickers = set(tickers_small)
    
    large_df = model_df[model_df["ticker"].isin(large_tickers)]
    small_df = model_df[model_df["ticker"].isin(small_tickers)]
    
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    
    print(f"\n[universe] Tränar {len(splits)} splits med 3 modellarkitekturer:")
    print("  1. Modell Large (enbart Large/Mid)")
    print("  2. Modell Small (enbart Small/Micro)")
    print("  3. Modell Joint (Combined universum)")
    
    scores = {
        "large_sep": [],
        "large_joint": [],
        "small_sep": [],
        "small_joint": []
    }
    
    last_large_model = None
    last_small_model = None
    last_joint_model = None
    
    for i, (train_d, val_d, test_d) in enumerate(splits):
        # Träningsdata per variant
        train_large = _slice_sorted(large_df, train_d)
        val_large = _slice_sorted(large_df, val_d)
        
        train_small = _slice_sorted(small_df, train_d)
        val_small = _slice_sorted(small_df, val_d)
        
        train_joint = _slice_sorted(model_df, train_d)
        val_joint = _slice_sorted(model_df, val_d)
        
        test_large = _slice_sorted(large_df, test_d)
        test_small = _slice_sorted(small_df, test_d)
        
        if len(test_large) < 10 or len(test_small) < 10:
            continue
            
        # Träna
        m_large = _train_lambdarank(train_large, val_large)
        m_small = _train_lambdarank(train_small, val_small)
        m_joint = _train_lambdarank(train_joint, val_joint)
        
        last_large_model = m_large
        last_small_model = m_small
        last_joint_model = m_joint
        
        # Utvärdera på Large testdata
        X_te_large = test_large[FEATURE_COLS].values
        p_large_sep = m_large.predict(X_te_large)
        p_large_joint = m_joint.predict(X_te_large)
        
        sdf_l_sep = test_large[["ticker"]].copy()
        sdf_l_sep["_raw"] = p_large_sep
        scores["large_sep"].append(sdf_l_sep)
        
        sdf_l_j = test_large[["ticker"]].copy()
        sdf_l_j["_raw"] = p_large_joint
        scores["large_joint"].append(sdf_l_j)
        
        # Utvärdera på Small testdata
        X_te_small = test_small[FEATURE_COLS].values
        p_small_sep = m_small.predict(X_te_small)
        p_small_joint = m_joint.predict(X_te_small)
        
        sdf_s_sep = test_small[["ticker"]].copy()
        sdf_s_sep["_raw"] = p_small_sep
        scores["small_sep"].append(sdf_s_sep)
        
        sdf_s_j = test_small[["ticker"]].copy()
        sdf_s_j["_raw"] = p_small_joint
        scores["small_joint"].append(sdf_s_j)
        
        print(f"  Split {i+1}/{len(splits)} klar.")
        
    # Extrapolera till holdout
    holdout_dates = all_dates[all_dates >= purge_start]
    if len(holdout_dates):
        print("\n[universe] Extrapolerar modeller till holdout...")
        ho_large = _slice_sorted(large_df, holdout_dates)
        ho_small = _slice_sorted(small_df, holdout_dates)
        
        X_ho_large = ho_large[FEATURE_COLS].values
        X_ho_small = ho_small[FEATURE_COLS].values
        
        # Large holdout
        sdf_hl_sep = ho_large[["ticker"]].copy()
        sdf_hl_sep["_raw"] = last_large_model.predict(X_ho_large)
        scores["large_sep"].append(sdf_hl_sep)
        
        sdf_hl_j = ho_large[["ticker"]].copy()
        sdf_hl_j["_raw"] = last_joint_model.predict(X_ho_large)
        scores["large_joint"].append(sdf_hl_j)
        
        # Small holdout
        sdf_hs_sep = ho_small[["ticker"]].copy()
        sdf_hs_sep["_raw"] = last_small_model.predict(X_ho_small)
        scores["small_sep"].append(sdf_hs_sep)
        
        sdf_hs_j = ho_small[["ticker"]].copy()
        sdf_hs_j["_raw"] = last_joint_model.predict(X_ho_small)
        scores["small_joint"].append(sdf_hs_j)

    # 4. Kör backtester
    print("\n" + "=" * 100)
    print("BACKTEST-RESULTAT: SEPARATA MODELLES VS GEGEMENSAM (JOINT) MODELL")
    print("=" * 100)
    
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
    
    for key in scores:
        signals = _build_signals_for_backtest(pd.concat(scores[key]), 10 if "large" in key else 20)
        stats = _run_backtest(signals, raw_data, holdout_start)
        dev_res = stats["dev"]
        ho_res = stats["holdout"]
        print(f"  {key:<15}: dev CAGR={_pct(dev_res, 'CAGR'):+.2%} Sharpe={float(dev_res['Sharpe']):.2f} | "
              f"holdout CAGR={_pct(ho_res, 'CAGR'):+.2%} Sharpe={float(ho_res['Sharpe']) if ho_res else 0.0:.2f}")

    print("\n[universe] Klart.")


if __name__ == "__main__":
    main()
