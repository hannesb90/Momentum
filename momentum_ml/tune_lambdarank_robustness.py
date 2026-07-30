"""
tune_lambdarank_robustness.py – Robustness Tests for LightGBM LambdaRank

Utvärderar robustheten hos LightGBM LambdaRank över olika kombinationer av:
  - Portföljselektivitet (topp 5%, 10%, 20%)
  - Innehavstid (4, 13, 26 veckor)
Samt redovisar per-år och per-regim nedbrytning.

Körs via:
    /opt/momentum/venv/bin/python tune_lambdarank_robustness.py
"""
import sys
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
import warnings
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
import config
seg = config.SEGMENTS["large"]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

# Parametrar för walk-forward
TRAIN_WINDOW_WEEKS = config.TRAIN_WINDOW_WEEKS  # 260v
VAL_WINDOW_WEEKS = config.VAL_WINDOW_WEEKS  # 52v
TEST_STEP_WEEKS = config.TEST_STEP_WEEKS  # 13v
EMBARGO_WEEKS = config.EMBARGO_WEEKS  # 13v

from features.feature_engineering import (
    FEATURE_COLS, build_all_features, attach_categorical_features,
    attach_fundamentals_features,
)
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

def load_cached_data() -> pd.DataFrame:
    """Bygger färska features via sandlådans normala pipeline (buggmönster 4 -
    den ursprungliga versionen läste en FRUST cache från 2026-07-27)."""
    print("Bygger färska features (large-segmentet, sandlådans pipeline)...")
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=sector_map, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment="large", prices=data)
    frames = []
    for ticker, df in feats.items():
        if "target_signal" not in df.columns or "target_return" not in df.columns:
            continue
        tmp = df.copy()
        tmp["ticker"] = ticker
        frames.append(tmp)

    full_df = pd.concat(frames).sort_index()
    full_df = full_df.dropna(subset=["target_signal", "target_return"])
    return full_df

def get_splits(dates: pd.DatetimeIndex):
    unique_dates = dates.unique().sort_values()
    n = len(unique_dates)
    emb = max(int(EMBARGO_WEEKS), 0)
    splits = []
    
    start = 0
    while start + TRAIN_WINDOW_WEEKS + VAL_WINDOW_WEEKS + TEST_STEP_WEEKS <= n:
        train_end = start + TRAIN_WINDOW_WEEKS
        val_end   = train_end + VAL_WINDOW_WEEKS
        test_end  = val_end + TEST_STEP_WEEKS
        
        train_cut = max(train_end - emb, start + 1)
        val_cut   = max(val_end - emb, train_end + 1)
        
        train_d = unique_dates[start:train_cut]
        val_d   = unique_dates[train_end:val_cut]
        test_d  = unique_dates[val_end:test_end]
        
        splits.append((train_d, val_d, test_d))
        start += TEST_STEP_WEEKS
        
    return splits

def main():
    import lightgbm as lgb
    df = load_cached_data()
    splits = get_splits(df.index)
    
    oos_preds = []
    
    # 1. Kör Walk-Forward och generera prediktioner (LambdaRank)
    for fold_i, (train_dates, val_dates, test_dates) in enumerate(splits):
        train_df = df.loc[train_dates].copy().sort_index()
        val_df = df.loc[val_dates].copy().sort_index()
        test_df = df.loc[test_dates].copy().sort_index()
        
        train_groups = train_df.groupby(level=0).size().values
        val_groups = val_df.groupby(level=0).size().values
        
        X_tr = train_df[FEATURE_COLS].fillna(0)
        X_va = val_df[FEATURE_COLS].fillna(0)
        X_te = test_df[FEATURE_COLS].fillna(0)
        
        train_df["rel"] = train_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        val_df["rel"] = val_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        
        y_tr_rel = train_df["rel"].values
        y_va_rel = val_df["rel"].values
        
        train_ds_rank = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups)
        val_ds_rank = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=train_ds_rank)
        
        rank_params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "ndcg_eval_at": [10, 20],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 30,
            "verbose": -1,
            "seed": 42
        }
        
        rank_model = lgb.train(
            rank_params,
            train_ds_rank,
            num_boost_round=500,
            valid_sets=[val_ds_rank],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        
        test_df["lambdarank_score"] = rank_model.predict(X_te)
        oos_preds.append(test_df)
        
    oos_df = pd.concat(oos_preds)
    
    # Spearman IC
    mask = oos_df["lambdarank_score"].notna() & oos_df["target_return"].notna()
    rho, _ = spearmanr(oos_df.loc[mask, "lambdarank_score"], oos_df.loc[mask, "target_return"])
    print(f"\nGenerell Spearman-IC: {rho:+.4f}")
    
    # 2. Portföljsimulering över parameterrutnät
    px_data = fetch_weekly_data(sorted(oos_df["ticker"].unique()), start="2015-01-01", end=None, use_cache=True)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in px_data.items() if d is not None and "Close" in d}
    ).sort_index()
    px.index = pd.to_datetime(px.index)
    
    selectivities = [0.05, 0.10, 0.20]
    holding_periods = [4, 13, 26]
    
    print("\n" + "=" * 75)
    print("  ROBUSTHETSTEST – PARAMETERRUTNÄT")
    print("=" * 75)
    print(f"  {'Hålltid':<8} | {'Topp-Q':<7} | {'CAGR':<8} | {'Sharpe':<7} | {'MaxDD':<8} | {'Hit%':<6} | {'Turnover/r':<10}")
    print("-" * 75)
    
    grid_results = {}
    
    for hp in holding_periods:
        for sel in selectivities:
            results = []
            prev_longs = set()
            turnovers = []
            
            # Gruppera veckovis
            dates = oos_df.index.unique().sort_values()
            
            # Simulera steg med hp-veckors hålltid
            for idx, date in enumerate(dates):
                if idx % hp != 0:
                    continue
                group = oos_df.loc[date] if date in oos_df.index else pd.DataFrame()
                if len(group) < 10:
                    continue
                
                k = max(1, int(len(group) * sel))
                top_k = group.sort_values(by="lambdarank_score", ascending=False).head(k)
                longs = set(top_k["ticker"])
                
                # Beräkna faktisk avkastning över hp veckor
                period_rets = []
                for tk in longs:
                    if tk not in px.columns:
                        continue
                    s = px[tk].dropna()
                    i0 = s.index.searchsorted(date)
                    i1 = s.index.searchsorted(date + pd.Timedelta(weeks=hp))
                    if i0 < len(s) and i1 < len(s) and i1 > i0:
                        period_rets.append(s.iloc[i1] / s.iloc[i0] - 1)
                        
                if period_rets:
                    ret = np.mean(period_rets)
                    results.append({"Date": date, "ret": ret})
                    
                # Beräkna turnover (andel nya positioner)
                if prev_longs:
                    new_pos = longs - prev_longs
                    turnovers.append(len(new_pos) / len(longs))
                prev_longs = longs
                
            res_df = pd.DataFrame(results).set_index("Date").sort_index()
            if res_df.empty:
                continue
                
            # CAGR
            periods_per_year = 52 / hp
            n_periods = len(res_df)
            total_ret = (1 + res_df["ret"]).prod() - 1
            cagr = (1 + total_ret) ** (periods_per_year / n_periods) - 1
            
            # Sharpe
            std = res_df["ret"].std()
            sharpe = (res_df["ret"].mean() / std) * np.sqrt(periods_per_year) if std > 0 else 0
            
            # MaxDD
            cum = (1 + res_df["ret"]).cumprod()
            roll_max = cum.cummax()
            max_dd = ((cum - roll_max) / roll_max).min()
            
            # Hit rate
            hit_rate = (res_df["ret"] > 0).mean()
            mean_turnover = np.mean(turnovers) if turnovers else 0.0
            
            print(f"  {hp:<2} veckor | {sel:<6.0%} | {cagr:+.1%}  | {sharpe:.3f} | {max_dd:+.1%}  | {hit_rate:.0%}  | {mean_turnover:.1%}")
            grid_results[(hp, sel)] = res_df
            
    print("=" * 75)
    
    # 3. Årsvis nedbrytning (för 13v / Topp 10%)
    best_df = grid_results[(13, 0.10)]
    best_df["year"] = best_df.index.year
    print("\n  ÅRSVIS PRESTANDA (13v / Topp 10%):")
    print(f"  {'År':<6} | {'Perioder':<8} | {'Avkastning':<10}")
    print("-" * 30)
    for yr, group in best_df.groupby("year"):
        yr_ret = (1 + group["ret"]).prod() - 1
        print(f"  {yr:<6} | {len(group):<8} | {yr_ret:+.1%}")
    print("-" * 30)

from data.data_loader import fetch_weekly_data
if __name__ == "__main__":
    main()
