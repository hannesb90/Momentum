"""
tune_catboost_vs_lambdarank.py – Standalone CatBoostRanker vs LightGBM LambdaRank Experiment

Utvärderar om CatBoostRanker (med YetiRank/PairLogit loss) ger bättre eller mer
robust rankingprestanda än LightGBM LambdaRank på samma dataset.

Körs via:
    /opt/momentum/venv/bin/python tune_catboost_vs_lambdarank.py
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
FORWARD_WEEKS = config.FORWARD_WEEKS  # 13v
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

# Ranking-utvärderingsfunktioner (NumPy 2.0-kompatibla)
def dcg_at_k(r, k):
    r = np.asarray(r, dtype=float)[:k]
    if r.size:
        return np.sum(r / np.log2(np.arange(2, r.size + 2)))
    return 0.0

def ndcg_at_k(r, k):
    dcg_max = dcg_at_k(sorted(r, reverse=True), k)
    if not dcg_max:
        return 0.0
    return dcg_at_k(r, k) / dcg_max

def precision_at_k(actual_ranks, k, threshold=3):
    top_k = actual_ranks[:k]
    return np.mean([1 if x >= threshold else 0 for x in top_k])

def evaluate_predictions(df_test: pd.DataFrame, score_col: str):
    ndcgs_10, ndcgs_20 = [], []
    precs_10, precs_20 = [], []
    
    for date, group in df_test.groupby(level=0):
        if len(group) < 20:
            continue
        # BUGFIX 2026-07-30: se tune_lambdarank_vs_baseline.py - relevance
        # måste sättas FÖRE sortering, annars pandas duplicerat-index-
        # justeringsfel -> alla score_col ger identisk NDCG/Precision.
        group = group.copy()
        group["relevance"] = pd.qcut(group["target_return"], 5, labels=False, duplicates='drop')
        sorted_group = group.sort_values(by=score_col, ascending=False)
        actual_relevance = sorted_group["relevance"].values
        
        ndcgs_10.append(ndcg_at_k(actual_relevance, 10))
        ndcgs_20.append(ndcg_at_k(actual_relevance, 20))
        precs_10.append(precision_at_k(actual_relevance, 10, threshold=3))
        precs_20.append(precision_at_k(actual_relevance, 20, threshold=3))
        
    return {
        "ndcg_10": np.mean(ndcgs_10) if ndcgs_10 else 0.0,
        "ndcg_20": np.mean(ndcgs_20) if ndcgs_20 else 0.0,
        "precision_10": np.mean(precs_10) if precs_10 else 0.0,
        "precision_20": np.mean(precs_20) if precs_20 else 0.0,
    }

def main():
    import lightgbm as lgb
    from catboost import CatBoostRanker, Pool
    
    df = load_cached_data()
    print(f"Dataset laddat: {df.shape[0]} rader, {df.shape[1]} kolumner.")
    
    splits = get_splits(df.index)
    print(f"Walk-forward splits: {len(splits)} folds.")
    
    oos_preds = []
    
    # YetiRank är bäst lämpad eftersom den minimerar en mjuk approximation av NDCG-förlusten
    # tvärsnittsbaserat och inte kräver explicita par.
    print("[Choice] YetiRank loss-funktion har valts för CatBoostRanker då den")
    print("optimerar NDCG-baserad avkastning direkt på finansiell point-in-time ranking.")

    for fold_i, (train_dates, val_dates, test_dates) in enumerate(splits):
        print(f"\n--- FOLD {fold_i+1}/{len(splits)} ---")
        
        train_df = df.loc[train_dates].copy()
        val_df = df.loc[val_dates].copy()
        test_df = df.loc[test_dates].copy()
        
        train_df = train_df.sort_index()
        val_df = val_df.sort_index()
        test_df = test_df.sort_index()
        
        # Konvertera DatetimeIndex-nivå 0 till heltals-grupp
        train_dates_unique = train_df.index.unique()
        date_to_group = {d: i for i, d in enumerate(train_dates_unique)}
        train_group_ids = train_df.index.map(date_to_group).values
        
        val_dates_unique = val_df.index.unique()
        vdate_to_group = {d: i for i, d in enumerate(val_dates_unique)}
        val_group_ids = val_df.index.map(vdate_to_group).values
        
        X_tr = train_df[FEATURE_COLS].fillna(0)
        X_va = val_df[FEATURE_COLS].fillna(0)
        X_te = test_df[FEATURE_COLS].fillna(0)
        
        # Relevans 0-4
        train_df["rel"] = train_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        val_df["rel"] = val_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        
        y_tr_rel = train_df["rel"].values
        y_va_rel = val_df["rel"].values
        
        # ── 1. LightGBM LambdaRank ──
        train_groups_lgb = train_df.groupby(level=0).size().values
        val_groups_lgb = val_df.groupby(level=0).size().values
        
        train_ds_lgb = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups_lgb)
        val_ds_lgb = lgb.Dataset(X_va, label=y_va_rel, group=val_groups_lgb, reference=train_ds_lgb)
        
        lgb_params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "ndcg_eval_at": [10, 20],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 30,
            "verbose": -1,
            "seed": 42
        }
        
        lgb_model = lgb.train(
            lgb_params,
            train_ds_lgb,
            num_boost_round=500,
            valid_sets=[val_ds_lgb],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        
        test_df["lgb_score"] = lgb_model.predict(X_te)
        
        # ── 2. CatBoostRanker ──
        train_pool = Pool(data=X_tr, label=y_tr_rel, group_id=train_group_ids)
        val_pool = Pool(data=X_va, label=y_va_rel, group_id=val_group_ids)
        
        cb_model = CatBoostRanker(
            iterations=500,
            learning_rate=0.05,
            loss_function="YetiRank",
            random_seed=42,
            verbose=False
        )
        
        cb_model.fit(
            train_pool,
            eval_set=val_pool,
            early_stopping_rounds=50
        )
        
        test_df["cb_score"] = cb_model.predict(X_te)
        
        oos_preds.append(test_df)
        
        print("Fold utvärdering:")
        for name, score_col in [("LGBM LambdaRank", "lgb_score"), ("CatBoost YetiRank", "cb_score")]:
            metrics = evaluate_predictions(test_df, score_col)
            print(f"  {name:<20} | NDCG@10: {metrics['ndcg_10']:.4f} | NDCG@20: {metrics['ndcg_20']:.4f} | Prec@10: {metrics['precision_10']:.2%} | Prec@20: {metrics['precision_20']:.2%}")
            
    oos_df = pd.concat(oos_preds)
    
    # ── Ranking Metrics ──
    print("\n" + "=" * 70)
    print("  POOLADE RANKING METRICS (OUT-OF-SAMPLE)")
    print("=" * 70)
    print(f"  {'Modell':<20} | {'NDCG@10':<8} | {'NDCG@20':<8} | {'Prec@10':<8} | {'Prec@20':<8} | {'Spearman-IC':<11}")
    print("-" * 70)
    
    for name, score_col in [("LGBM LambdaRank", "lgb_score"), ("CatBoost YetiRank", "cb_score")]:
        metrics = evaluate_predictions(oos_df, score_col)
        mask = oos_df[score_col].notna() & oos_df["target_return"].notna()
        rho, _ = spearmanr(oos_df.loc[mask, score_col], oos_df.loc[mask, "target_return"])
        print(f"  {name:<20} | {metrics['ndcg_10']:.4f}  | {metrics['ndcg_20']:.4f}  | {metrics['precision_10']:.2%}   | {metrics['precision_20']:.2%}   | {rho:+.4f}")
        
    # ── Portföljsimulering ──
    print("\n" + "=" * 70)
    print("  PORTFÖLJSIMULERING (Top 10% Long, 13v Hållperiod)")
    print("=" * 70)
    print(f"  {'Modell':<20} | {'CAGR':<8} | {'Sharpe':<7} | {'MaxDD':<8} | {'Hit%':<6}")
    print("-" * 70)
    
    for name, score_col in [("LGBM LambdaRank", "lgb_score"), ("CatBoost YetiRank", "cb_score")]:
        results = []
        for date, group in oos_df.groupby(level=0):
            if len(group) < 10:
                continue
            k = max(1, int(len(group) * 0.1))
            top_k = group.sort_values(by=score_col, ascending=False).head(k)
            ret = top_k["target_return"].mean()
            results.append({"Date": date, "ret": ret})
            
        res_df = pd.DataFrame(results).set_index("Date").sort_index()
        
        n_periods = len(res_df)
        total_ret = (1 + res_df["ret"]).prod() - 1
        cagr = (1 + total_ret) ** (4 / n_periods) - 1
        std = res_df["ret"].std()
        sharpe = (res_df["ret"].mean() / std) * np.sqrt(4) if std > 0 else 0
        cum = (1 + res_df["ret"]).cumprod()
        roll_max = cum.cummax()
        max_dd = ((cum - roll_max) / roll_max).min()
        hit_rate = (res_df["ret"] > 0).mean()
        
        print(f"  {name:<20} | {cagr:+.1%}  | {sharpe:.3f} | {max_dd:+.1%}  | {hit_rate:.0%}")
        
    print("=" * 70)
    
    # ── Överlapp ──
    overlaps = []
    for date, group in oos_df.groupby(level=0):
        if len(group) < 10:
            continue
        k = max(1, int(len(group) * 0.1))
        lgb_top = set(group.sort_values(by="lgb_score", ascending=False).head(k)["ticker"])
        cb_top = set(group.sort_values(by="cb_score", ascending=False).head(k)["ticker"])
        if lgb_top and cb_top:
            overlaps.append(len(lgb_top.intersection(cb_top)) / len(lgb_top))
            
    print(f"\nGenomsnittligt överlapp i portföljval mellan LGBM och CatBoost: {np.mean(overlaps):.1%}")

if __name__ == "__main__":
    main()
