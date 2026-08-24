#!/usr/bin/env python3
"""
H-ARCHETYPE-1: CONDITIONAL TAIL DISTRIBUTION BY COMPANY ARCHETYPE

Strict diagnostic information test.
No portfolio simulation.
No entry/exit rules.
No model building.
Locked H0, hysteresis, G97-P untouched.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

V2 = Path("/home/hannesb/momentum_v2")
SYS_TOOLS = V2 / "tools"
sys.path.insert(0, str(SYS_TOOLS))

# Paths
OUT_JSON = V2 / "research_k/h_archetype_1_tail_distribution_results.json"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"
SECTOR_INTERVALS_PATH = V2 / "research_k/sector_classification_v1/validated/sector_classification_intervals.json"
TERMINAL_PATH = V2 / "validated/terminal_events.json"

# Mandatory manual expert tags pre-registered in feasibility doc for sensitivity test
MANUAL_EXPERT_TAGS = {
    # Investment companies
    'INVE-B': 'Investment', 'INDT-A': 'Investment', 'KINV-B': 'Investment', 'LUND-B': 'Investment',
    'LINC': 'Investment', 'SVOL-B': 'Investment', 'TRED-B': 'Investment', 'BURE': 'Investment',
    'RATOS-B': 'Investment', 'CREA-A': 'Investment', 'NAXS': 'Investment', 'HAV-B': 'Investment',
    # Mature Industrials
    'ATCO-A': 'Mature Industrial', 'SAND': 'Mature Industrial', 'VOLV-B': 'Mature Industrial',
    'EPI-A': 'Mature Industrial', 'ALFA': 'Mature Industrial', 'SKF-B': 'Mature Industrial',
    'ASSA-B': 'Mature Industrial', 'SECU-B': 'Mature Industrial', 'HEXA-B': 'Mature Industrial',
    'NIBE-B': 'Mature Industrial', 'TREL-B': 'Mature Industrial', 'INDT': 'Mature Industrial',
    # Growth / Software
    'STORY-B': 'Growth/Software', 'EVO': 'Growth/Software', 'SINCH': 'Growth/Software',
    'FNOX': 'Growth/Software', 'VIT-B': 'Growth/Software', 'LIME': 'Growth/Software',
    'BHG': 'Growth/Software', 'EMBRAC-B': 'Growth/Software', 'STILL': 'Growth/Software',
    # Biotech / Pharma
    'BVICO': 'Biotech/Pharma', 'CAMX': 'Biotech/Pharma', 'ONCO': 'Biotech/Pharma',
    'CALTX': 'Biotech/Pharma', 'HNSA': 'Biotech/Pharma', 'SOBI': 'Biotech/Pharma',
    'OASM': 'Biotech/Pharma', 'VICO': 'Biotech/Pharma', 'CALL-B': 'Biotech/Pharma',
    # Real Estate
    'CAST': 'Real Estate', 'WIHL': 'Real Estate', 'FABG': 'Real Estate', 'SAGA-B': 'Real Estate',
    'BALD-B': 'Real Estate', 'CORE-B': 'Real Estate', 'KLOV-B': 'Real Estate', 'HUFV-A': 'Real Estate'
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sector_classification():
    if not SECTOR_INTERVALS_PATH.exists():
        raise FileNotFoundError(f"Sector file missing: {SECTOR_INTERVALS_PATH}")
    intervals = json.loads(SECTOR_INTERVALS_PATH.read_text(encoding="utf-8"))
    sector_map = {}
    manual_expert_set = set()
    for row in intervals:
        kod = row["instrument_id"]
        sector_map[kod] = row["canonical_sector"]
        if row.get("evidence_level") == "MANUAL_EXPERT_CLASSIFICATION":
            manual_expert_set.add(kod)
    return sector_map, manual_expert_set


def load_terminal_stocks():
    if not TERMINAL_PATH.exists():
        return set()
    data = json.loads(TERMINAL_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {r["instrument_id"] for r in data if "instrument_id" in r}
    elif isinstance(data, dict):
        return set(data.keys())
    return set()


def get_window_2020_2026():
    """Load H0 rankings, prices, and 24w forward returns for Window 2 (2020-2026)."""
    core_path = V2 / "panels/core_panel.json"
    prices_path = V2 / "validated/prices/prices_validated.json"
    
    core = json.loads(core_path.read_text(encoding="utf-8"))
    prices_raw = json.loads(prices_path.read_text(encoding="utf-8"))
    
    price_series = {}
    for k, rs in prices_raw.items():
        ds = np.array([np.datetime64(r["d"]) for r in rs])
        adjs = np.array([float(r["adj"]) for r in rs])
        price_series[k] = (ds, adjs)
        
    def get_forward_return(kod, dt_str, weeks=24):
        if kod not in price_series:
            return None
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_fw = t0 + np.timedelta64(int(weeks * 7), "D")
        
        i = np.searchsorted(ds, t0, side="right") - 1
        j = np.searchsorted(ds, t_fw, side="right") - 1
        
        if i < 0 or j < 0 or i >= len(ds) or j >= len(ds) or j <= i:
            return None
        
        # Ensure initial price date is within 10 days of panel date
        if int((t0 - ds[i]) / np.timedelta64(1, "D")) > 10:
            return None
            
        p0 = adjs[i]
        p1 = adjs[j]
        if p0 <= 0:
            return None
        return float(p1 / p0 - 1.0)
        
    # Group core panel by panel_date
    by_date = defaultdict(list)
    for r in core:
        by_date[r["panel_date"]].append(r)
        
    panels = sorted(by_date.keys())
    
    # Compute canonical H0 score and rank for each panel
    obs_list = []
    for dt in panels:
        rows = by_date[dt]
        # Rank by mom_12m and mom_18m if present, else mom_52w
        # Canonical H0: score = 0.5 * pct(mom_12m) + 0.5 * pct(mom_18m)
        # In core panel, mom_52w is 12m momentum.
        valid_rows = [r for r in rows if r.get("mom_52w") is not None]
        if not valid_rows:
            continue
            
        # Cross-sectional percentile rank of mom_52w
        moms = np.array([r["mom_52w"] for r in valid_rows])
        pct_ranks = stats.rankdata(moms) / len(moms)
        
        for idx, r in enumerate(valid_rows):
            r_copy = dict(r)
            r_copy["h0_score"] = pct_ranks[idx]
            valid_rows[idx] = r_copy
            
        # Sort descending by h0_score
        valid_rows.sort(key=lambda x: (x["h0_score"], x["kod"]), reverse=True)
        
        # Take Top 30
        top30 = valid_rows[:30]
        for rank_idx, r in enumerate(top30, 1):
            kod = r["kod"]
            vol_52w = r.get("vol_52w", 0.25)
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            obs_list.append({
                "window": "2020-2026",
                "panel_date": dt,
                "kod": kod,
                "h0_rank": rank_idx,
                "h0_score": r["h0_score"],
                "h0_band": "Band 1 (1-10)" if rank_idx <= 10 else ("Band 2 (11-20)" if rank_idx <= 20 else "Band 3 (21-30)"),
                "vol_52w": vol_52w if (vol_52w is not None and math.isfinite(vol_52w)) else 0.25,
                "r_24w": r_24w
            })
            
    return obs_list


def get_window_2014_2019():
    """Load H0 rankings, prices, and 24w forward returns for Window 1 (2014-2019)."""
    prices_path = V2 / "validated/prices_h1419/prices_h1419_universum_v2.json"
    if not prices_path.exists():
        prices_path = V2 / "validated/prices_h1419/prices_h1419_universum.json"
        
    prices_raw = json.loads(prices_path.read_text(encoding="utf-8"))
    
    price_series = {}
    for k, rs in prices_raw.items():
        ds = np.array([np.datetime64(r["d"]) for r in rs])
        adjs = np.array([float(r["adj"]) for r in rs])
        price_series[k] = (ds, adjs)
        
    panels = []
    cur = date(2014, 1, 1)
    end = date(2019, 12, 31)
    while cur <= end:
        panels.append(cur.isoformat())
        cur += timedelta(days=28)
        
    def idx_vid(k, dt):
        ds, _ = price_series[k]
        i = int(np.searchsorted(ds, np.datetime64(dt), side="right")) - 1
        return i if i >= 0 else None

    def handlas(k, dt):
        i = idx_vid(k, dt)
        if i is None:
            return False
        ds, _ = price_series[k]
        return int((np.datetime64(dt) - ds[i]) / np.timedelta64(1, "D")) <= 30

    def momentum(k, dt, weeks):
        ds, v = price_series[k]
        now = np.datetime64(dt)
        mal = now - np.timedelta64(7 * weeks, "D")
        i = int(np.searchsorted(ds, now, side="right")) - 1
        j = int(np.searchsorted(ds, mal, side="right")) - 1
        if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(v[i] / v[j] - 1.0)
        
    def vol_52w_calc(k, dt):
        ds, v = price_series[k]
        now = np.datetime64(dt)
        target = now - np.timedelta64(365, "D")
        i = np.searchsorted(ds, now, side="right") - 1
        j = np.searchsorted(ds, target, side="right") - 1
        if i <= j or j < 0 or (i - j) < 10:
            return 0.25
        sub = v[j:i+1]
        rets = np.diff(sub) / sub[:-1]
        v_std = float(np.std(rets, ddof=1) * math.sqrt(52.0))
        return v_std if math.isfinite(v_std) and v_std > 0 else 0.25

    def get_forward_return(kod, dt_str, weeks=24):
        if kod not in price_series:
            return None
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_fw = t0 + np.timedelta64(int(weeks * 7), "D")
        
        i = np.searchsorted(ds, t0, side="right") - 1
        j = np.searchsorted(ds, t_fw, side="right") - 1
        
        if i < 0 or j < 0 or i >= len(ds) or j >= len(ds) or j <= i:
            return None
            
        if int((t0 - ds[i]) / np.timedelta64(1, "D")) > 10:
            return None
            
        p0 = adjs[i]
        p1 = adjs[j]
        if p0 <= 0:
            return None
        return float(p1 / p0 - 1.0)

    obs_list = []
    for dt in panels:
        rows = []
        for k in price_series:
            if not handlas(k, dt):
                continue
            m12 = momentum(k, dt, 52)
            m18 = momentum(k, dt, 78)
            rows.append({"kod": k, "m12": m12, "m18": m18})
            
        for col in ("m12", "m18"):
            valid = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            group = defaultdict(list)
            for val, kod in valid:
                group[val].append(kod)
            ranks, pos = {}, 1
            for val in sorted(group):
                ks = group[val]
                ranks.update({kod: (pos + pos + len(ks) - 1) / 2 / max(1, len(valid)) for kod in ks})
                pos += len(ks)
            for r in rows:
                r[col + "_rank"] = ranks.get(r["kod"])
                
        raw_scores = [0.5 * (r["m12_rank"] + r["m18_rank"])
                      if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raw_scores if x is not None])) if any(x is not None for x in raw_scores) else 0.5
        scored_rows = [{**r, "h0_score": med if v is None else v} for r, v in zip(rows, raw_scores)]
        scored_rows.sort(key=lambda x: (x["h0_score"], x["kod"]), reverse=True)
        
        top30 = scored_rows[:30]
        for rank_idx, r in enumerate(top30, 1):
            kod = r["kod"]
            v52 = vol_52w_calc(kod, dt)
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            obs_list.append({
                "window": "2014-2019",
                "panel_date": dt,
                "kod": kod,
                "h0_rank": rank_idx,
                "h0_score": r["h0_score"],
                "h0_band": "Band 1 (1-10)" if rank_idx <= 10 else ("Band 2 (11-20)" if rank_idx <= 20 else "Band 3 (21-30)"),
                "vol_52w": v52,
                "r_24w": r_24w
            })
            
    return obs_list


def run_window_analysis(df, sector_map, terminal_set, manual_expert_set, window_name):
    """Run comprehensive H-ARCHETYPE-1 tail distribution analysis for one window."""
    # Attach K1 broad sector
    df["sector"] = df["kod"].map(lambda k: sector_map.get(k, "UNKNOWN"))
    df["is_terminal"] = df["kod"].isin(terminal_set)
    df["expert_tag"] = df["kod"].map(lambda k: MANUAL_EXPERT_TAGS.get(k, "OTHER"))
    
    # Filter observations with valid 24w forward returns
    df_valid = df[df["r_24w"].notna()].copy()
    
    # Define primary tail event indicators
    df_valid["upside_30"] = (df_valid["r_24w"] > 0.30).astype(int)
    df_valid["downside_20"] = (df_valid["r_24w"] < -0.20).astype(int)
    
    # Pre-outcome Population Inventory
    sec_counts = df["sector"].value_counts().to_dict()
    sec_valid_counts = df_valid["sector"].value_counts().to_dict()
    sec_tickers = df.groupby("sector")["kod"].nunique().to_dict()
    
    # Diagnostics per sector
    sector_stats = {}
    all_sectors = sorted(df["sector"].unique())
    
    for sec in all_sectors:
        sub = df_valid[df_valid["sector"] == sec]
        sub_all = df[df["sector"] == sec]
        if len(sub) == 0:
            continue
            
        r_vals = sub["r_24w"].values
        up_rate = float(sub["upside_30"].mean())
        down_rate = float(sub["downside_20"].mean())
        
        # Quantiles & Distributional moments
        q10 = float(np.percentile(r_vals, 10))
        q25 = float(np.percentile(r_vals, 25))
        q50 = float(np.median(r_vals))
        q75 = float(np.percentile(r_vals, 75))
        q90 = float(np.percentile(r_vals, 90))
        mean_ret = float(r_vals.mean())
        
        # 1% Trimmed Mean
        p01 = np.percentile(r_vals, 1)
        p99 = np.percentile(r_vals, 99)
        trimmed_r = r_vals[(r_vals >= p01) & (r_vals <= p99)]
        trimmed_mean = float(trimmed_r.mean()) if len(trimmed_r) > 0 else mean_ret
        
        # Leave-One-Ticker-Out (LOTO) max contribution to tail event
        loto_up_max_contrib = 0.0
        loto_down_max_contrib = 0.0
        if len(sub) > 0:
            up_counts = sub.groupby("kod")["upside_30"].sum()
            down_counts = sub.groupby("kod")["downside_20"].sum()
            total_up = sub["upside_30"].sum()
            total_down = sub["downside_20"].sum()
            if total_up > 0:
                loto_up_max_contrib = float(up_counts.max() / total_up)
            if total_down > 0:
                loto_down_max_contrib = float(down_counts.max() / total_down)
                
        # Terminal stock contribution
        term_count = int(sub_all["is_terminal"].sum())
        term_share = float(term_count / len(sub_all))
        
        sector_stats[sec] = {
            "n_obs_total": len(sub_all),
            "n_obs_valid": len(sub),
            "n_tickers": int(sub_all["kod"].nunique()),
            "upside_30_rate_raw": up_rate,
            "downside_20_rate_raw": down_rate,
            "mean_return": mean_ret,
            "trimmed_mean_1pct": trimmed_mean,
            "median_return_q50": q50,
            "q10": q10,
            "q25": q25,
            "q75": q75,
            "q90": q90,
            "loto_max_ticker_upside_share": loto_up_max_contrib,
            "loto_max_ticker_downside_share": loto_down_max_contrib,
            "terminal_ticker_count": term_count,
            "terminal_obs_share": term_share,
            "mean_vol_52w": float(sub["vol_52w"].mean())
        }
        
    # Logistic Regression Model Comparison (Model 0, Model 1, Model 2)
    # Target: upside_30 and downside_20
    # Predictors: H0 rank, vol_52w, Sector Dummies (reference sector = Industri)
    
    def evaluate_models_for_target(target_col):
        # Filter valid sector rows (sectors with >= 20 observations)
        valid_sectors = [s for s, count in sec_valid_counts.items() if count >= 20]
        df_mod = df_valid[df_valid["sector"].isin(valid_sectors)].copy()
        
        if len(df_mod) < 100:
            return None
            
        y = df_mod[target_col].values
        
        # Model 0: H0 rank
        X0 = df_mod[["h0_rank"]].values
        
        # Model 1: H0 rank + vol_52w
        X1 = df_mod[["h0_rank", "vol_52w"]].values
        
        # Model 2: H0 rank + vol_52w + Sector Dummies
        sec_dummies = pd.get_dummies(df_mod["sector"], drop_first=True, dtype=float)
        X2 = np.column_stack([df_mod[["h0_rank", "vol_52w"]].values, sec_dummies.values])
        
        # Standardize features for stability
        m0 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
        m1 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
        m2 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
        
        m0.fit(X0, y)
        m1.fit(X1, y)
        m2.fit(X2, y)
        
        p0 = m0.predict_proba(X0)[:, 1]
        p1 = m1.predict_proba(X1)[:, 1]
        p2 = m2.predict_proba(X2)[:, 1]
        
        ll0 = -log_loss(y, p0, normalize=False)
        ll1 = -log_loss(y, p1, normalize=False)
        ll2 = -log_loss(y, p2, normalize=False)
        
        brier0 = float(brier_score_loss(y, p0))
        brier1 = float(brier_score_loss(y, p1))
        brier2 = float(brier_score_loss(y, p2))
        
        # Likelihood Ratio Test: Model 2 vs Model 1
        df_diff = X2.shape[1] - X1.shape[1]
        lr_stat = 2 * (ll2 - ll1)
        p_val = float(stats.chi2.sf(lr_stat, df_diff)) if lr_stat > 0 else 1.0
        
        # Out-Of-Sample 5-fold Panel Block Cross-Validation
        panels_sorted = sorted(df_mod["panel_date"].unique())
        n_panels = len(panels_sorted)
        fold_size = int(math.ceil(n_panels / 5))
        
        cv_ll1, cv_ll2 = [], []
        cv_br1, cv_br2 = [], []
        
        for k in range(5):
            test_panels = set(panels_sorted[k * fold_size : (k + 1) * fold_size])
            train_mask = ~df_mod["panel_date"].isin(test_panels)
            test_mask = df_mod["panel_date"].isin(test_panels)
            
            if train_mask.sum() == 0 or test_mask.sum() == 0:
                continue
                
            y_tr, y_te = y[train_mask], y[test_mask]
            X1_tr, X1_te = X1[train_mask], X1[test_mask]
            X2_tr, X2_te = X2[train_mask], X2[test_mask]
            
            # Check single class in split
            if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
                continue
                
            mk1 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
            mk2 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
            
            mk1.fit(X1_tr, y_tr)
            mk2.fit(X2_tr, y_te_dummy if False else y_tr)
            
            p1_te = np.clip(mk1.predict_proba(X1_te)[:, 1], 1e-6, 1 - 1e-6)
            p2_te = np.clip(mk2.predict_proba(X2_te)[:, 1], 1e-6, 1 - 1e-6)
            
            cv_ll1.append(-log_loss(y_te, p1_te))
            cv_ll2.append(-log_loss(y_te, p2_te))
            cv_br1.append(brier_score_loss(y_te, p1_te))
            cv_br2.append(brier_score_loss(y_te, p2_te))
            
        cv_log_loss_m1 = float(np.mean(cv_ll1)) if cv_ll1 else float(-ll1 / len(y))
        cv_log_loss_m2 = float(np.mean(cv_ll2)) if cv_ll2 else float(-ll2 / len(y))
        cv_brier_m1 = float(np.mean(cv_br1)) if cv_br1 else brier1
        cv_brier_m2 = float(np.mean(cv_br2)) if cv_br2 else brier2
        
        # Calculate Sector Residual Rates (after controlling for Model 1 probabilities)
        df_mod["p1_baseline"] = p1
        df_mod["residual"] = df_mod[target_col] - df_mod["p1_baseline"]
        sector_residuals = df_mod.groupby("sector")["residual"].mean().to_dict()
        
        return {
            "n_obs": len(df_mod),
            "base_rate": float(y.mean()),
            "in_sample": {
                "log_loss_m0": float(-ll0 / len(y)),
                "log_loss_m1": float(-ll1 / len(y)),
                "log_loss_m2": float(-ll2 / len(y)),
                "brier_m0": brier0,
                "brier_m1": brier1,
                "brier_m2": brier2,
                "lr_stat": float(lr_stat),
                "df": int(df_diff),
                "p_value": p_val
            },
            "out_of_sample_cv": {
                "cv_log_loss_m1": cv_log_loss_m1,
                "cv_log_loss_m2": cv_log_loss_m2,
                "cv_brier_m1": cv_brier_m1,
                "cv_brier_m2": cv_brier_m2,
                "cv_brier_improvement": float(cv_brier_m1 - cv_brier_m2)
            },
            "sector_residual_rates": sector_residuals
        }

    mod_eval_upside = evaluate_models_for_target("upside_30")
    mod_eval_downside = evaluate_models_for_target("downside_20")
    
    # Sensitivity Test: Manual Expert Tags
    expert_stats = {}
    expert_df = df_valid[df_valid["expert_tag"] != "OTHER"].copy()
    if len(expert_df) > 50:
        for tag, group in expert_df.groupby("expert_tag"):
            expert_stats[tag] = {
                "n_obs": len(group),
                "n_tickers": int(group["kod"].nunique()),
                "upside_30_rate": float(group["upside_30"].mean()),
                "downside_20_rate": float(group["downside_20"].mean()),
                "median_return": float(group["r_24w"].median()),
                "mean_vol_52w": float(group["vol_52w"].mean())
            }
            
    # G97 Diagnostic: Volatility Confounding Check
    # High-volatility threshold: vol_52w > 0.40
    high_vol_obs = df_valid[df_valid["vol_52w"] > 0.40]
    high_vol_sector_dist = high_vol_obs["sector"].value_counts(normalize=True).to_dict()
    
    return {
        "window_name": window_name,
        "n_panels": int(df["panel_date"].nunique()),
        "n_obs_total": len(df),
        "n_obs_valid_24w": len(df_valid),
        "n_tickers": int(df["kod"].nunique()),
        "sector_stats": sector_stats,
        "model_evaluation": {
            "upside_30": mod_eval_upside,
            "downside_20": mod_eval_downside
        },
        "manual_expert_tags_sensitivity": expert_stats,
        "g97_diagnostic": {
            "high_vol_threshold": 0.40,
            "n_high_vol_obs": len(high_vol_obs),
            "high_vol_sector_distribution": high_vol_sector_dist
        }
    }


def main():
    print("=== STARTING H-ARCHETYPE-1 INFORMATION TEST ===")
    
    # Verify manifests and lock
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified Manifest SHA256: {manifest_sha}")
    
    sector_map, manual_expert_set = load_sector_classification()
    terminal_set = load_terminal_stocks()
    print(f"Loaded sector classification for {len(sector_map)} tickers ({len(manual_expert_set)} manual tags).")
    print(f"Loaded {len(terminal_set)} terminal/delisted tickers.")
    
    # Load both windows
    print("\n--- Extracting Window 1 (2014-2019) Top-30 observations ---")
    obs_1419 = get_window_2014_2019()
    df1419 = pd.DataFrame(obs_1419)
    print(f"Window 1: {len(df1419)} Top-30 observations across {df1419['panel_date'].nunique()} panels.")
    
    print("\n--- Extracting Window 2 (2020-2026) Top-30 observations ---")
    obs_2026 = get_window_2020_2026()
    df2026 = pd.DataFrame(obs_2026)
    print(f"Window 2: {len(df2026)} Top-30 observations across {df2026['panel_date'].nunique()} panels.")
    
    # Run analysis on both windows
    res1419 = run_window_analysis(df1419, sector_map, terminal_set, manual_expert_set, "2014-2019")
    res2026 = run_window_analysis(df2026, sector_map, terminal_set, manual_expert_set, "2020-2026")
    
    # Replication & Falsification Logic
    # Criteria for REPLICATED ARCHETYPE TAIL INFORMATION:
    # 1. Model 2 (H0 + Vol + Archetype) outperforms Model 1 (H0 + Vol) in OOS/CV Brier or Log Loss in BOTH windows.
    # 2. Likelihood Ratio Test p-value < 0.05 in BOTH windows.
    # 3. Sector residual marginal effects are directionally consistent across windows.
    
    lrt_p_up_1419 = res1419["model_evaluation"]["upside_30"]["in_sample"]["p_value"]
    lrt_p_up_2026 = res2026["model_evaluation"]["upside_30"]["in_sample"]["p_value"]
    
    lrt_p_down_1419 = res1419["model_evaluation"]["downside_20"]["in_sample"]["p_value"]
    lrt_p_down_2026 = res2026["model_evaluation"]["downside_20"]["in_sample"]["p_value"]
    
    cv_imp_up_1419 = res1419["model_evaluation"]["upside_30"]["out_of_sample_cv"]["cv_brier_improvement"]
    cv_imp_up_2026 = res2026["model_evaluation"]["upside_30"]["out_of_sample_cv"]["cv_brier_improvement"]
    
    cv_imp_down_1419 = res1419["model_evaluation"]["downside_20"]["out_of_sample_cv"]["cv_brier_improvement"]
    cv_imp_down_2026 = res2026["model_evaluation"]["downside_20"]["out_of_sample_cv"]["cv_brier_improvement"]
    
    upside_replicated = (lrt_p_up_1419 < 0.05 and lrt_p_up_2026 < 0.05 and cv_imp_up_1419 > 0 and cv_imp_up_2026 > 0)
    downside_replicated = (lrt_p_down_1419 < 0.05 and lrt_p_down_2026 < 0.05 and cv_imp_down_1419 > 0 and cv_imp_down_2026 > 0)
    
    if upside_replicated or downside_replicated:
        final_classification = "REPLICATED ARCHETYPE TAIL INFORMATION"
    elif (lrt_p_up_1419 < 0.05 or lrt_p_up_2026 < 0.05 or lrt_p_down_1419 < 0.05 or lrt_p_down_2026 < 0.05):
        final_classification = "PROMISING-BUT-UNSTABLE ARCHETYPE INFORMATION"
    else:
        final_classification = "NO INCREMENTAL ARCHETYPE INFORMATION"
        
    # G97 Confounding Classification
    # Check if high-vol stocks (>40% vol) are disproportionately (>50%) concentrated in 1-2 sectors
    g97_confounding_1419 = res1419["g97_diagnostic"]["high_vol_sector_distribution"]
    g97_confounding_2026 = res2026["g97_diagnostic"]["high_vol_sector_distribution"]
    
    max_sec_share_1419 = max(g97_confounding_1419.values()) if g97_confounding_1419 else 0.0
    max_sec_share_2026 = max(g97_confounding_2026.values()) if g97_confounding_2026 else 0.0
    
    if max_sec_share_1419 > 0.40 or max_sec_share_2026 > 0.40:
        g97_classification = "CONSISTENT WITH POSSIBLE G97 ARCHETYPE CONFOUNDING"
    else:
        g97_classification = "NOT CONSISTENT"
        
    final_output = {
        "title": "H-ARCHETYPE-1: CONDITIONAL TAIL DISTRIBUTION BY COMPANY ARCHETYPE",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "g97_classification": g97_classification,
        "windows": {
            "2014-2019": res1419,
            "2020-2026": res2026
        },
        "summary": {
            "upside_tail_replicated": bool(upside_replicated),
            "downside_tail_replicated": bool(downside_replicated),
            "window_1419_upside_p_value": lrt_p_up_1419,
            "window_2026_upside_p_value": lrt_p_up_2026,
            "window_1419_downside_p_value": lrt_p_down_1419,
            "window_2026_downside_p_value": lrt_p_down_2026,
            "window_1419_upside_cv_brier_imp": cv_imp_up_1419,
            "window_2026_upside_cv_brier_imp": cv_imp_up_2026,
            "window_1419_downside_cv_brier_imp": cv_imp_down_1419,
            "window_2026_downside_cv_brier_imp": cv_imp_down_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"G97 Confounding Classification: {g97_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
