"""
tune_lambdarank_vs_baseline.py – Standalone LambdaRank vs Classification/Regression Experiment

Utvärderar om en rankingmodell (LightGBM LambdaRank) är bättre lämpad än
nuvarande klassificerings- och regressionsmodeller för Momentum-pipelinen.

Körs via:
    /opt/momentum/venv/bin/python tune_lambdarank_vs_baseline.py
"""
import sys
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
import warnings
from scipy.stats import spearmanr
from sklearn.preprocessing import StandardScaler

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

# Importera listan över features (EFTER DROP_FEATURES satt ovan, buggmönster 1)
from features.feature_engineering import (
    FEATURE_COLS, build_all_features, attach_categorical_features,
    attach_fundamentals_features, to_model_df,
)
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

def load_cached_data() -> pd.DataFrame:
    """Bygger färska features via sandlådans normala pipeline (buggmönster 4 -
    den ursprungliga versionen läste en FRUST cache från 2026-07-27,
    /opt/momentum/momentum_ml/results/_features_cache_4ca3ee808051ab63.pkl,
    daterad FÖRE senare feature-ändringar i sandlådan)."""
    print("Bygger färska features (large-segmentet, sandlådans pipeline)...")
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=sector_map, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment="large", prices=data)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}
    full_df = pd.concat(feature_dfs.values()).sort_index()
    full_df = full_df.dropna(subset=["target_signal", "target_return"])
    if "roa" in full_df.columns:
        full_df["fund_roe"] = full_df["roa"]  # roe fanns i gamla cachen, roa närmast tillgängliga proxy nu
    else:
        full_df["fund_roe"] = 0.0
    return full_df

def get_splits(dates: pd.DatetimeIndex):
    """Genererar splits enligt walk_forward_splits-logiken i lgbm_model.py."""
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

# Beräkning av NDCG och Precision (justerad för NumPy 2.0)
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
    """Utvärderar ranking-prestanda per datum."""
    ndcgs_10, ndcgs_20 = [], []
    precs_10, precs_20 = [], []
    
    for date, group in df_test.groupby(level=0):
        if len(group) < 20:
            continue
        # BUGFIX 2026-07-30: relevance måste beräknas och tilldelas INNAN
        # sortering, inte efteråt - `group`/`sorted_group` delar samma
        # (duplicerade, datumbaserade) index, så
        # `sorted_group["relevance"] = ret_quantiles` gjorde en pandas
        # many-to-many indexjustering som INTE respekterade
        # sorteringsordningen -> alla score_col gav identisk "relevance"-
        # ordning oavsett modell (bit-identiska NDCG/Precision för alla
        # fyra modeller, upptäckt vid omkörning). Fixat genom att sätta
        # kolumnen på `group` FÖRE sortering - sort_values för då med sig
        # relevance-kolumnen korrekt per rad.
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
    df = load_cached_data()
    print(f"Dataset laddat: {df.shape[0]} rader, {df.shape[1]} kolumner.")
    
    splits = get_splits(df.index)
    print(f"Walk-forward splits genererade: {len(splits)} folds.")
    
    oos_preds = []
    
    # Kör walk-forward
    for fold_i, (train_dates, val_dates, test_dates) in enumerate(splits):
        print(f"\n--- FOLD {fold_i+1}/{len(splits)} ---")
        
        # Dela upp data
        train_df = df.loc[train_dates].copy()
        val_df = df.loc[val_dates].copy()
        test_df = df.loc[test_dates].copy()
        
        # Sortera kronologiskt för gruppering per datum
        train_df = train_df.sort_index()
        val_df = val_df.sort_index()
        test_df = test_df.sort_index()
        
        # Bygg grupper (antal observationer per datum)
        train_groups = train_df.groupby(level=0).size().values
        val_groups = val_df.groupby(level=0).size().values
        
        # Förberedd features
        X_tr = train_df[FEATURE_COLS].fillna(0)
        X_va = val_df[FEATURE_COLS].fillna(0)
        X_te = test_df[FEATURE_COLS].fillna(0)
        
        # Förbered relevans labels (0-4) per datum för träning
        train_df["rel"] = train_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        val_df["rel"] = val_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        )
        
        y_tr_rel = train_df["rel"].values
        y_va_rel = val_df["rel"].values
        
        # ── 1. LambdaRank ──
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
        
        # ── 2. Baseline: Standard Binary Classification ──
        y_tr_cls = train_df["target_signal"].values
        y_va_cls = val_df["target_signal"].values
        
        train_ds_cls = lgb.Dataset(X_tr, label=y_tr_cls)
        val_ds_cls = lgb.Dataset(X_va, label=y_va_cls, reference=train_ds_cls)
        
        cls_params = {
            "objective": "binary",
            "metric": "auc",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 30,
            "verbose": -1,
            "seed": 42
        }
        
        cls_model = lgb.train(
            cls_params,
            train_ds_cls,
            num_boost_round=500,
            valid_sets=[val_ds_cls],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        
        test_df["cls_score"] = cls_model.predict(X_te)
        
        # ── 3. Baseline: Standard Regression ──
        y_tr_reg = train_df["target_return"].values
        y_va_reg = val_df["target_return"].values
        
        train_ds_reg = lgb.Dataset(X_tr, label=y_tr_reg)
        val_ds_reg = lgb.Dataset(X_va, label=y_va_reg, reference=train_ds_reg)
        
        reg_params = {
            "objective": "regression",
            "metric": "rmse",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 30,
            "verbose": -1,
            "seed": 42
        }
        
        reg_model = lgb.train(
            reg_params,
            train_ds_reg,
            num_boost_round=500,
            valid_sets=[val_ds_reg],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        
        test_df["reg_score"] = reg_model.predict(X_te)
        
        # Combo
        test_df["combo_score"] = test_df["cls_score"] * 0.6 + test_df["reg_score"] * 0.4
        
        # ── 4. Baseline: Enkel ROE Ranking (fund_roe) ──
        test_df["roe_score"] = test_df["fund_roe"].fillna(0)
        
        oos_preds.append(test_df)
        
        # Utvärdera ranking per fold
        print("Fold utvärdering:")
        for model_name, score_col in [("LambdaRank", "lambdarank_score"), ("Classification", "cls_score"), ("Regression", "reg_score"), ("ROE Baseline", "roe_score")]:
            metrics = evaluate_predictions(test_df, score_col)
            print(f"  {model_name:<16} | NDCG@10: {metrics['ndcg_10']:.4f} | NDCG@20: {metrics['ndcg_20']:.4f} | Prec@10: {metrics['precision_10']:.2%} | Prec@20: {metrics['precision_20']:.2%}")
            
    oos_df = pd.concat(oos_preds)
    
    # ── Slutlig Poolad Utvärdering ──
    print("\n" + "=" * 70)
    print("  POOLADE RANKING METRICS (OUT-OF-SAMPLE)")
    print("=" * 70)
    print(f"  {'Modell':<16} | {'NDCG@10':<8} | {'NDCG@20':<8} | {'Prec@10':<8} | {'Prec@20':<8} | {'Spearman-IC':<11}")
    print("-" * 70)
    
    for model_name, score_col in [
        ("LambdaRank", "lambdarank_score"),
        ("Classification", "cls_score"),
        ("Regression", "reg_score"),
        ("Combo (Cls+Reg)", "combo_score"),
        ("ROE Baseline", "roe_score")
    ]:
        metrics = evaluate_predictions(oos_df, score_col)
        mask = oos_df[score_col].notna() & oos_df["target_return"].notna()
        rho, _ = spearmanr(oos_df.loc[mask, score_col], oos_df.loc[mask, "target_return"])
        
        print(f"  {model_name:<16} | {metrics['ndcg_10']:.4f}  | {metrics['ndcg_20']:.4f}  | {metrics['precision_10']:.2%}   | {metrics['precision_20']:.2%}   | {rho:+.4f}")
    
    # ── Portföljsimulering (Top 10% Long per vecka) ──
    print("\n" + "=" * 70)
    print("  PORTFÖLJSIMULERING (Top 10% Long, 13v Hållperiod)")
    print("=" * 70)
    print(f"  {'Modell':<16} | {'CAGR':<8} | {'Sharpe':<7} | {'MaxDD':<8} | {'Hit%':<6}")
    print("-" * 70)
    
    for model_name, score_col in [
        ("LambdaRank", "lambdarank_score"),
        ("Classification", "cls_score"),
        ("Regression", "reg_score"),
        ("Combo (Cls+Reg)", "combo_score"),
        ("ROE Baseline", "roe_score")
    ]:
        results = []
        for date, group in oos_df.groupby(level=0):
            if len(group) < 10:
                continue
            k = max(1, int(len(group) * 0.1))
            top_k = group.sort_values(by=score_col, ascending=False).head(k)
            ret = top_k["target_return"].mean()
            results.append({"Date": date, "ret": ret})
            
        res_df = pd.DataFrame(results).set_index("Date").sort_index()
        if res_df.empty:
            continue
            
        n_periods = len(res_df)
        total_ret = (1 + res_df["ret"]).prod() - 1
        cagr = (1 + total_ret) ** (4 / n_periods) - 1
        
        std = res_df["ret"].std()
        sharpe = (res_df["ret"].mean() / std) * np.sqrt(4) if std > 0 else 0
        
        cum = (1 + res_df["ret"]).cumprod()
        roll_max = cum.cummax()
        max_dd = ((cum - roll_max) / roll_max).min()
        
        hit_rate = (res_df["ret"] > 0).mean()
        
        print(f"  {model_name:<16} | {cagr:+.1%}  | {sharpe:.3f} | {max_dd:+.1%}  | {hit_rate:.0%}")
        
    print("=" * 70)
    
    # ── Jämförelse av valda aktier ──
    overlaps = []
    for date, group in oos_df.groupby(level=0):
        if len(group) < 10:
            continue
        k = max(1, int(len(group) * 0.1))
        lr_top = set(group.sort_values(by="lambdarank_score", ascending=False).head(k)["ticker"])
        combo_top = set(group.sort_values(by="combo_score", ascending=False).head(k)["ticker"])
        if lr_top and combo_top:
            overlaps.append(len(lr_top.intersection(combo_top)) / len(lr_top))
            
    print(f"\nGenomsnittligt överlapp i portföljval mellan LambdaRank och Combo: {np.mean(overlaps):.1%}")

if __name__ == "__main__":
    main()
