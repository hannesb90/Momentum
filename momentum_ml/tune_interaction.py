"""
tune_interaction.py – Utvärderar om interaktionsfeatures (t.ex. Attention Gap × Earnings Reaction)
tillför edge i stock-pickingen under den nya baslinjen.
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


def calculate_interaction_features(feats: dict, raw_data: dict, segment: str) -> dict:
    """Beräknar och lägger till Attention Gap x Earnings Reaction i feats-dicten."""
    print("[interaction] Beräknar interaktionsfeatures...")
    
    # 1. Läs in rapportdatum för att veta när rapporterna publicerades
    from features.feature_engineering import _load_fundamentals_growth
    fund_df = _load_fundamentals_growth(segment, prices=raw_data)
    if fund_df.empty:
        return feats
        
    px = pd.DataFrame({t: d["Close"] for t, d in raw_data.items() if "Close" in d}).sort_index()
    dvol = pd.DataFrame({t: (d["Close"] * d["Volume"]) for t, d in raw_data.items()
                          if "Close" in d and "Volume" in d}).sort_index()
    dvol_normal = dvol.rolling(13).mean().shift(1)
    
    # Beräkna vol_ratio per rapport-event
    rows = []
    for _, row in fund_df.iterrows():
        t = row["ticker"]
        pub = pd.Timestamp(row["published"])
        if t not in px.columns or t not in dvol.columns:
            continue
            
        pos = px.index.searchsorted(pub, side="left")
        if pos >= len(px.index):
            continue
        wk = px.index[pos]
        
        vol_wk = dvol.at[wk, t]
        vol_norm = dvol_normal.at[wk, t]
        reaction = row["report_reaction_abn"]
        
        if pd.isna(vol_wk) or pd.isna(vol_norm) or vol_norm == 0 or pd.isna(reaction):
            continue
            
        vol_ratio = vol_wk / vol_norm
        attention_gap = 1.0 / (vol_ratio + 1e-5)
        interact = attention_gap * reaction
        
        rows.append({"ticker": t, "published": pub, "attention_gap": attention_gap, "interact": interact})
        
    interact_df = pd.DataFrame(rows)
    if interact_df.empty:
        return feats
        
    # Sätt samman och merga backward (ffill) för varje ticker
    by_ticker = {t: g.sort_values("published") for t, g in interact_df.groupby("ticker")}
    
    updated_feats = {}
    for t, feat_df in feats.items():
        g = by_ticker.get(t)
        if g is None or g.empty:
            feat_df["attention_gap"] = 0.0
            feat_df["interact_report_reaction"] = 0.0
        else:
            left = feat_df.index.to_frame(index=False, name="Date").sort_values("Date")
            left["Date"] = left["Date"].astype("datetime64[us]")
            g["published"] = g["published"].astype("datetime64[us]")
            joined = pd.merge_asof(left, g[["published", "attention_gap", "interact"]],
                                    left_on="Date", right_on="published", direction="backward")
            joined = joined.set_index("Date")
            feat_df["attention_gap"] = joined["attention_gap"].reindex(feat_df.index).fillna(0.0)
            feat_df["interact_report_reaction"] = joined["interact"].reindex(feat_df.index).fillna(0.0)
        updated_feats[t] = feat_df
        
    return updated_feats


def run_experiment(segment: str, tickers: list, raw_data: pd.DataFrame, model_df: pd.DataFrame, all_dates: pd.Index, purge_start: pd.Timestamp):
    print(f"\n[interaction] Kör experiment för segment: {segment.upper()}")
    
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    
    test_preds_baseline = []
    test_preds_interact = []
    
    last_model_base = None
    last_model_int = None
    
    # Skapa kolumnlistor
    baseline_cols = FEATURE_COLS.copy()
    interact_cols = FEATURE_COLS.copy() + ["attention_gap", "interact_report_reaction"]
    
    # Patcha träningsmetoden för att stödja olika kolumner
    def _train_fit(train_sub, val_sub, cols):
        """production_params() (samma som tune_lambdarank_common.py) i stället
        för de tidigare hårdkodade ad-hoc-parametrarna - annars samma
        confound-mönster som Test 5/6/7. FEATURE_COLS byts ut mot `cols` i
        params-dicten hämtas oförändrad, valet av kolumner påverkar inte
        hyperparametrarna."""
        X_tr = train_sub[cols].values
        X_va = val_sub[cols].values
        train_groups = train_sub.groupby(level=0).size().values
        val_groups = val_sub.groupby(level=0).size().values
        y_tr_rel = _relevance_labels(train_sub)
        y_va_rel = _relevance_labels(val_sub)
        w_tr = _date_weights(train_sub)
        ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
        ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)
        return lgb.train(production_params(), ds_tr, num_boost_round=500, valid_sets=[ds_va],
                          callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)])

    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = model_df.loc[model_df.index.isin(train_d)]
        val_sub = model_df.loc[model_df.index.isin(val_d)]
        test_sub = model_df.loc[model_df.index.isin(test_d)]
        
        if len(test_sub) < 5:
            continue
            
        m_base = _train_fit(train_sub, val_sub, baseline_cols)
        m_int = _train_fit(train_sub, val_sub, interact_cols)
        
        last_model_base = m_base
        last_model_int = m_int
        
        # Prediktera baseline
        sdf_base = test_sub[["ticker"]].copy()
        sdf_base["_raw"] = m_base.predict(test_sub[baseline_cols].values)
        test_preds_baseline.append(sdf_base)
        
        # Prediktera interact
        sdf_int = test_sub[["ticker"]].copy()
        sdf_int["_raw"] = m_int.predict(test_sub[interact_cols].values)
        test_preds_interact.append(sdf_int)
        
    # Holdout-prediktioner
    holdout_dates = all_dates[all_dates >= purge_start]
    if len(holdout_dates) and last_model_base is not None and last_model_int is not None:
        ho_sub = model_df.loc[model_df.index.isin(holdout_dates)]
        
        sdf_hb = ho_sub[["ticker"]].copy()
        sdf_hb["_raw"] = last_model_base.predict(ho_sub[baseline_cols].values)
        test_preds_baseline.append(sdf_hb)
        
        sdf_hi = ho_sub[["ticker"]].copy()
        sdf_hi["_raw"] = last_model_int.predict(ho_sub[interact_cols].values)
        test_preds_interact.append(sdf_hi)
        
    # Sammanställ signaler och kör backtests
    n_pos = 10 if segment == "large" else 20
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
    
    print("-" * 90)
    for name, pred_list in [("Baseline", test_preds_baseline), ("With Interaction Features", test_preds_interact)]:
        full_preds = pd.concat(pred_list)
        signals = _build_signals_for_backtest(full_preds, n_pos)
        stats = _run_backtest(signals, raw_data, holdout_start)
        
        dev_res = stats["dev"]
        ho_res = stats["holdout"]
        
        print(f"  {name:<25}: dev CAGR={_pct(dev_res, 'CAGR'):+.2%} Sharpe={float(dev_res['Sharpe']):.2f} | "
              f"holdout CAGR={_pct(ho_res, 'CAGR'):+.2%} Sharpe={float(ho_res['Sharpe']) if ho_res else 0.0:.2f}")
    print("-" * 90)


def main():
    print("[interaction] Startar interaktionsfeatures-tuning...")
    
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
    
    # Lägg till interaktionsfeatures
    feats = calculate_interaction_features(feats, raw_data, segment="large")
    
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
