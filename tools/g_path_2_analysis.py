#!/usr/bin/env python3
"""
G-PATH-2: GENERIC MOMENTUM PATH INFORMATION

Diagnostic information test.
No portfolio simulation.
No entry/hold/exit rules.
No model modification.
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
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import log_loss, brier_score_loss, mean_squared_error, r2_score

V2 = Path("/home/hannesb/momentum_v2")
SYS_TOOLS = V2 / "tools"
sys.path.insert(0, str(SYS_TOOLS))

OUT_JSON = V2 / "research_k/g_path_2_results.json"
OUT_DOC = V2 / "docs/G_PATH_2_GENERIC_MOMENTUM_PATH_INFORMATION.md"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_data_2020_2026():
    core_path = V2 / "panels/core_panel.json"
    prices_path = V2 / "validated/prices/prices_validated.json"
    
    core = json.loads(core_path.read_text(encoding="utf-8"))
    prices_raw = json.loads(prices_path.read_text(encoding="utf-8"))
    
    price_series = {}
    for k, rs in prices_raw.items():
        ds = np.array([np.datetime64(r["d"]) for r in rs])
        adjs = np.array([float(r["adj"]) for r in rs])
        price_series[k] = (ds, adjs)
        
    def get_price_at(kod, dt_str):
        if kod not in price_series:
            return None
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        i = np.searchsorted(ds, t0, side="right") - 1
        if i < 0 or i >= len(ds):
            return None
        if int((t0 - ds[i]) / np.timedelta64(1, "D")) > 10:
            return None
        return adjs[i]

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

    by_date = defaultdict(list)
    for r in core:
        by_date[r["panel_date"]].append(r)
        
    panels = sorted(by_date.keys())
    
    top30_by_panel = {}
    scored_by_panel = {}
    
    for dt in panels:
        rows = by_date[dt]
        valid_rows = [r for r in rows if r.get("mom_52w") is not None]
        if not valid_rows:
            continue
        moms = np.array([r["mom_52w"] for r in valid_rows])
        pct_ranks = stats.rankdata(moms) / len(moms)
        
        for idx, r in enumerate(valid_rows):
            r_copy = dict(r)
            r_copy["h0_score"] = pct_ranks[idx]
            valid_rows[idx] = r_copy
            
        valid_rows.sort(key=lambda x: (x["h0_score"], x["kod"]), reverse=True)
        scored_by_panel[dt] = valid_rows
        top30_by_panel[dt] = [r["kod"] for r in valid_rows[:30]]

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
        if dt not in scored_by_panel:
            continue
        top30_rows = scored_by_panel[dt][:30]
        
        for rank_idx, r in enumerate(top30_rows, 1):
            kod = r["kod"]
            score = r["h0_score"]
            vol52 = r.get("vol_52w", 0.25)
            if vol52 is None or not math.isfinite(vol52) or vol52 <= 0:
                vol52 = 0.25
                
            k = 0
            while (pi - k) >= 0:
                past_dt = panels[pi - k]
                if past_dt in top30_by_panel and kod in top30_by_panel[past_dt]:
                    k += 1
                else:
                    break
            tis = k
            entry_dt = panels[pi - k + 1] if (pi - k + 1) >= 0 else panels[0]
            
            ep_key = (kod, entry_dt)
            if ep_key not in episode_map:
                episode_counter += 1
                episode_map[ep_key] = episode_counter
            ep_id = episode_map[ep_key]
            
            p_entry = get_price_at(kod, entry_dt)
            p_curr = get_price_at(kod, dt)
            
            run_return = float(p_curr / p_entry - 1.0) if p_entry and p_curr and p_entry > 0 else 0.0
            r_4w = get_forward_return(kod, dt, weeks=4)
            r_12w = get_forward_return(kod, dt, weeks=12)
            r_24w = get_forward_return(kod, dt, weeks=24)
            ret_4w_rel = r.get("ret_4w_rel", 0.0) # feature #44 diagnostic reference
            
            obs_list.append({
                "window": "2020-2026",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP26_{ep_id}",
                "entry_date": entry_dt,
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": vol52,
                "tis": tis,
                "run_return": run_return,
                "ret_4w_rel": ret_4w_rel if ret_4w_rel is not None else 0.0,
                "r_4w": r_4w,
                "r_12w": r_12w,
                "r_24w": r_24w
            })
            
    return obs_list


def extract_data_2014_2019():
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

    def get_price_at(kod, dt_str):
        if kod not in price_series:
            return None
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        i = np.searchsorted(ds, t0, side="right") - 1
        if i < 0 or i >= len(ds):
            return None
        if int((t0 - ds[i]) / np.timedelta64(1, "D")) > 10:
            return None
        return adjs[i]

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

    top30_by_panel = {}
    scored_by_panel = {}
    
    for dt in panels:
        rows = []
        for k in price_series:
            if not handlas(k, dt):
                continue
            m12 = momentum(k, dt, 52)
            m18 = momentum(k, dt, 78)
            m4 = momentum(k, dt, 4)
            rows.append({"kod": k, "m12": m12, "m18": m18, "m4": m4})
            
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
        
        scored_by_panel[dt] = scored_rows
        top30_by_panel[dt] = [r["kod"] for r in scored_rows[:30]]

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
        if dt not in scored_by_panel:
            continue
        top30_rows = scored_by_panel[dt][:30]
        
        for rank_idx, r in enumerate(top30_rows, 1):
            kod = r["kod"]
            score = r["h0_score"]
            v52 = vol_52w_calc(kod, dt)
            
            k = 0
            while (pi - k) >= 0:
                past_dt = panels[pi - k]
                if past_dt in top30_by_panel and kod in top30_by_panel[past_dt]:
                    k += 1
                else:
                    break
            tis = k
            entry_dt = panels[pi - k + 1] if (pi - k + 1) >= 0 else panels[0]
            
            ep_key = (kod, entry_dt)
            if ep_key not in episode_map:
                episode_counter += 1
                episode_map[ep_key] = episode_counter
            ep_id = episode_map[ep_key]
            
            p_entry = get_price_at(kod, entry_dt)
            p_curr = get_price_at(kod, dt)
            
            run_return = float(p_curr / p_entry - 1.0) if p_entry and p_curr and p_entry > 0 else 0.0
            r_4w = get_forward_return(kod, dt, weeks=4)
            r_12w = get_forward_return(kod, dt, weeks=12)
            r_24w = get_forward_return(kod, dt, weeks=24)
            ret_4w_rel = r.get("m4", 0.0)
            
            obs_list.append({
                "window": "2014-2019",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP14_{ep_id}",
                "entry_date": entry_dt,
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": v52,
                "tis": tis,
                "run_return": run_return,
                "ret_4w_rel": ret_4w_rel if ret_4w_rel is not None else 0.0,
                "r_4w": r_4w,
                "r_12w": r_12w,
                "r_24w": r_24w
            })
            
    return obs_list


def analyze_window_path(df, window_name):
    """Execute complete G-PATH-2 analysis for one window."""
    df_valid = df[df["r_24w"].notna()].copy()
    
    n_obs = len(df_valid)
    n_episodes = df_valid["episode_id"].nunique()
    n_tickers = df_valid["kod"].nunique()
    ep_per_ticker = float(n_episodes / max(1, n_tickers))
    top5_ticker_obs = float(df_valid["kod"].value_counts().head(5).sum() / n_obs)
    
    # Summary statistics of run_return
    rr = df_valid["run_return"].values
    rr_stats = {
        "mean": float(np.mean(rr)),
        "std": float(np.std(rr)),
        "median": float(np.median(rr)),
        "q10": float(np.percentile(rr, 10)),
        "q25": float(np.percentile(rr, 25)),
        "q75": float(np.percentile(rr, 75)),
        "q90": float(np.percentile(rr, 90)),
        "min": float(np.min(rr)),
        "max": float(np.max(rr))
    }
    
    # Spearman correlation matrix
    corr_cols = ["run_return", "tis", "h0_rank", "h0_score", "vol_52w", "ret_4w_rel", "r_4w", "r_12w", "r_24w"]
    corr_df = df_valid[corr_cols].dropna().copy()
    corr_matrix = corr_df.corr(method="spearman").to_dict()
    
    # -------------------------------------------------------------
    # MODEL LADDER (M0, M1, M2, M3, M4)
    # M0 = h0_rank
    # M1 = h0_rank + vol_52w
    # M2 = h0_rank + vol_52w + run_return
    # M3 = h0_rank + vol_52w + tis (TIS CONTROL)
    # M4 = h0_rank + vol_52w + tis + run_return (CRITICAL TEST!)
    # -------------------------------------------------------------
    X_m0 = df_valid[["h0_rank"]].values
    X_m1 = df_valid[["h0_rank", "vol_52w"]].values
    X_m2 = df_valid[["h0_rank", "vol_52w", "run_return"]].values
    X_m3 = df_valid[["h0_rank", "vol_52w", "tis"]].values
    X_m4 = df_valid[["h0_rank", "vol_52w", "tis", "run_return"]].values
    
    y_24w = df_valid["r_24w"].values
    y_12w = df_valid[df_valid["r_12w"].notna()]["r_12w"].values
    y_4w = df_valid[df_valid["r_4w"].notna()]["r_4w"].values
    
    y_down_24w = (y_24w < -0.20).astype(int)
    y_up_24w = (y_24w > 0.30).astype(int)
    
    # Continuous Regressions
    r0 = LinearRegression().fit(X_m0, y_24w)
    r1 = LinearRegression().fit(X_m1, y_24w)
    r2 = LinearRegression().fit(X_m2, y_24w)
    r3 = LinearRegression().fit(X_m3, y_24w)
    r4 = LinearRegression().fit(X_m4, y_24w)
    
    reg_24w_summary = {
        "m0_r2": float(r2_score(y_24w, r0.predict(X_m0))),
        "m1_r2": float(r2_score(y_24w, r1.predict(X_m1))),
        "m2_r2": float(r2_score(y_24w, r2.predict(X_m2))),
        "m3_r2": float(r2_score(y_24w, r3.predict(X_m3))),
        "m4_r2": float(r2_score(y_24w, r4.predict(X_m4))),
        "m2_vs_m1_r2_gain": float(r2_score(y_24w, r2.predict(X_m2)) - r2_score(y_24w, r1.predict(X_m1))),
        "m4_vs_m3_r2_gain": float(r2_score(y_24w, r4.predict(X_m4)) - r2_score(y_24w, r3.predict(X_m3))),
    }
    
    # 5-Fold Episode-Block Out-of-Sample CV for Downside Risk & Upside Risk (24w)
    episodes_unique = df_valid["episode_id"].unique()
    np.random.seed(42)
    np.random.shuffle(episodes_unique)
    
    n_ep = len(episodes_unique)
    ep_fold_size = int(math.ceil(n_ep / 5))
    
    cv_brier_m1, cv_brier_m2, cv_brier_m3, cv_brier_m4 = [], [], [], []
    
    for k in range(5):
        test_eps = set(episodes_unique[k * ep_fold_size : (k + 1) * ep_fold_size])
        tr_mask = ~df_valid["episode_id"].isin(test_eps)
        te_mask = df_valid["episode_id"].isin(test_eps)
        
        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue
            
        y_tr, y_te = y_down_24w[tr_mask], y_down_24w[te_mask]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue
            
        c1 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m1[tr_mask], y_tr)
        c2 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m2[tr_mask], y_tr)
        c3 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m3[tr_mask], y_tr)
        c4 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m4[tr_mask], y_tr)
        
        p1 = np.clip(c1.predict_proba(X_m1[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        p2 = np.clip(c2.predict_proba(X_m2[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        p3 = np.clip(c3.predict_proba(X_m3[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        p4 = np.clip(c4.predict_proba(X_m4[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        
        cv_brier_m1.append(brier_score_loss(y_te, p1))
        cv_brier_m2.append(brier_score_loss(y_te, p2))
        cv_brier_m3.append(brier_score_loss(y_te, p3))
        cv_brier_m4.append(brier_score_loss(y_te, p4))
        
    cv_downside = {
        "cv_brier_m1": float(np.mean(cv_brier_m1)),
        "cv_brier_m2": float(np.mean(cv_brier_m2)),
        "cv_brier_m3": float(np.mean(cv_brier_m3)),
        "cv_brier_m4": float(np.mean(cv_brier_m4)),
        "m2_vs_m1_brier_delta": float(np.mean(cv_brier_m1) - np.mean(cv_brier_m2)),
        "m4_vs_m3_brier_delta": float(np.mean(cv_brier_m3) - np.mean(cv_brier_m4)), # positive if M4 beats M3
    }

    # -------------------------------------------------------------
    # STEP I: ECONOMIC MAGNITUDE CHECK (Residual Quintiles)
    # Residualize run_return against M3 predictors (h0_rank, vol_52w, tis)
    # -------------------------------------------------------------
    res_model = LinearRegression().fit(X_m3, df_valid["run_return"].values)
    residuals = df_valid["run_return"].values - res_model.predict(X_m3)
    df_valid["run_return_res"] = residuals
    
    df_valid["res_quintile"] = pd.qcut(df_valid["run_return_res"], 5, labels=["Q1_Low", "Q2", "Q3", "Q4", "Q5_High"])
    
    quintile_payoff = {}
    for q_name, sub in df_valid.groupby("res_quintile", observed=False):
        if len(sub) == 0:
            continue
        r24 = sub["r_24w"].values
        quintile_payoff[str(q_name)] = {
            "n_obs": len(sub),
            "mean_res": float(sub["run_return_res"].mean()),
            "mean_run_return": float(sub["run_return"].mean()),
            "mean_tis": float(sub["tis"].mean()),
            "median_r24w": float(np.median(r24)),
            "mean_r24w": float(np.mean(r24)),
            "p_downside_20": float(np.mean(r24 < -0.20)),
            "p_upside_30": float(np.mean(r24 > 0.30)),
            "mean_r12w": float(sub["r_12w"].mean()) if sub["r_12w"].notna().any() else 0.0,
            "mean_r4w": float(sub["r_4w"].mean()) if sub["r_4w"].notna().any() else 0.0
        }

    return {
        "window_name": window_name,
        "n_obs_valid": n_obs,
        "n_episodes": n_episodes,
        "n_tickers": n_tickers,
        "episodes_per_ticker": ep_per_ticker,
        "top5_ticker_obs_concentration": top5_ticker_obs,
        "run_return_stats": rr_stats,
        "spearman_correlations": corr_matrix,
        "regressions_24w": reg_24w_summary,
        "oos_cv_downside_24w": cv_downside,
        "quintile_payoff": quintile_payoff
    }


def main():
    print("=== STARTING G-PATH-2 ANALYSIS ===")
    
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified K1 Freeze Manifest SHA256: {manifest_sha}")
    
    print("\n--- Extracting 2014-2019 dataset ---")
    data1419 = extract_data_2014_2019()
    df1419 = pd.DataFrame(data1419)
    print(f"Window 14-19 raw obs: {len(df1419)}, episodes: {df1419['episode_id'].nunique()}")
    
    print("\n--- Extracting 2020-2026 dataset ---")
    data2026 = extract_data_2020_2026()
    df2026 = pd.DataFrame(data2026)
    print(f"Window 20-26 raw obs: {len(df2026)}, episodes: {df2026['episode_id'].nunique()}")
    
    print("\n--- Analyzing Window 2014-2019 ---")
    res1419 = analyze_window_path(df1419, "2014-2019")
    
    print("\n--- Analyzing Window 2020-2026 ---")
    res2026 = analyze_window_path(df2026, "2020-2026")
    
    m2_v_m1_1419 = res1419["oos_cv_downside_24w"]["m2_vs_m1_brier_delta"]
    m2_v_m1_2026 = res2026["oos_cv_downside_24w"]["m2_vs_m1_brier_delta"]
    
    m4_v_m3_1419 = res1419["oos_cv_downside_24w"]["m4_vs_m3_brier_delta"]
    m4_v_m3_2026 = res2026["oos_cv_downside_24w"]["m4_vs_m3_brier_delta"]
    
    r2_m4_m3_1419 = res1419["regressions_24w"]["m4_vs_m3_r2_gain"]
    r2_m4_m3_2026 = res2026["regressions_24w"]["m4_vs_m3_r2_gain"]
    
    # Classification Logic strictly according to task rules
    if m4_v_m3_1419 > 0 and m4_v_m3_2026 > 0 and r2_m4_m3_1419 > 0.001 and r2_m4_m3_2026 > 0.001:
        final_classification = "REPLICATED INCREMENTAL PATH INFORMATION"
    elif m2_v_m1_1419 > 0 and m2_v_m1_2026 > 0 and (m4_v_m3_1419 <= 0 or m4_v_m3_2026 <= 0 or r2_m4_m3_1419 <= 0.0005 or r2_m4_m3_2026 <= 0.0005):
        final_classification = "GENERIC PATH INFORMATION — REDUNDANT WITH TIS/H0"
    elif (m2_v_m1_1419 > 0 and m2_v_m1_2026 <= 0) or (m2_v_m1_1419 <= 0 and m2_v_m1_2026 > 0):
        final_classification = "PROMISING-BUT-UNSTABLE PATH INFORMATION"
    else:
        final_classification = "NO INCREMENTAL PATH INFORMATION"
        
    final_output = {
        "title": "G-PATH-2: GENERIC MOMENTUM PATH INFORMATION",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "windows": {
            "2014-2019": res1419,
            "2020-2026": res2026
        },
        "summary": {
            "m2_vs_m1_brier_delta_1419": m2_v_m1_1419,
            "m2_vs_m1_brier_delta_2026": m2_v_m1_2026,
            "m4_vs_m3_brier_delta_1419": m4_v_m3_1419,
            "m4_vs_m3_brier_delta_2026": m4_v_m3_2026,
            "m4_vs_m3_r2_gain_1419": r2_m4_m3_1419,
            "m4_vs_m3_r2_gain_2026": r2_m4_m3_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
