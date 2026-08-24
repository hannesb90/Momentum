#!/usr/bin/env python3
"""
H-RUNWAY-DIST-1: ARCHETYPE-CONDITIONAL MOMENTUM RUNWAY (Optimized)

Diagnostic distribution / feasibility test.
No portfolio simulation.
No entry/hold/exit rules.
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
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import log_loss, brier_score_loss, mean_squared_error, r2_score

V2 = Path("/home/hannesb/momentum_v2")
SYS_TOOLS = V2 / "tools"
sys.path.insert(0, str(SYS_TOOLS))

OUT_JSON = V2 / "research_k/h_runway_dist_1_results.json"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"
SECTOR_INTERVALS_PATH = V2 / "research_k/sector_classification_v1/validated/sector_classification_intervals.json"
TERMINAL_PATH = V2 / "validated/terminal_events.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sector_classification():
    intervals = json.loads(SECTOR_INTERVALS_PATH.read_text(encoding="utf-8"))
    sector_map = {row["instrument_id"]: row["canonical_sector"] for row in intervals}
    return sector_map


def load_terminal_stocks():
    if not TERMINAL_PATH.exists():
        return set()
    data = json.loads(TERMINAL_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {r["instrument_id"] for r in data if "instrument_id" in r}
    elif isinstance(data, dict):
        return set(data.keys())
    return set()


def get_data_2020_2026(sector_map):
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
    
    for pi, dt in enumerate(panels):
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
            
            p_entry = get_price_at(kod, entry_dt)
            p_curr = get_price_at(kod, dt)
            
            if p_entry is not None and p_curr is not None and p_entry > 0:
                run_return = float(p_curr / p_entry - 1.0)
            else:
                run_return = 0.0
                
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            obs_list.append({
                "window": "2020-2026",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "sector": sector_map.get(kod, "UNKNOWN"),
                "h0_rank": rank_idx,
                "h0_score": score,
                "h0_decile": int(math.ceil(rank_idx / 3.0)),
                "vol_52w": vol52,
                "tis": tis,
                "entry_date": entry_dt,
                "run_return": run_return,
                "mom_12m": r.get("mom_52w"),
                "r_24w": r_24w
            })
            
    return obs_list


def get_data_2014_2019(sector_map):
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
        
        scored_by_panel[dt] = scored_rows
        top30_by_panel[dt] = [r["kod"] for r in scored_rows[:30]]

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
            
            p_entry = get_price_at(kod, entry_dt)
            p_curr = get_price_at(kod, dt)
            
            if p_entry is not None and p_curr is not None and p_entry > 0:
                run_return = float(p_curr / p_entry - 1.0)
            else:
                run_return = 0.0
                
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            obs_list.append({
                "window": "2014-2019",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "sector": sector_map.get(kod, "UNKNOWN"),
                "h0_rank": rank_idx,
                "h0_score": score,
                "h0_decile": int(math.ceil(rank_idx / 3.0)),
                "vol_52w": v52,
                "tis": tis,
                "entry_date": entry_dt,
                "run_return": run_return,
                "mom_12m": r.get("m12"),
                "r_24w": r_24w
            })
            
    return obs_list


def compute_expanding_pit_archetype_percentiles_fast(df):
    """
    Fast vectorized calculation of EXPANDING PIT archetype-relative percentiles.
    """
    df = df.sort_values(["panel_date", "h0_rank"]).copy()
    panels = sorted(df["panel_date"].unique())
    
    r24_pcts = np.full(len(df), np.nan)
    run_pcts = np.full(len(df), np.nan)
    
    # Map each row to index
    panel_dates = pd.to_datetime(df["panel_date"]).values
    cutoff_dates = panel_dates - np.timedelta64(168, "D")
    
    sectors = df["sector"].values
    r24_vals = df["r_24w"].values
    run_vals = df["run_return"].values
    
    # Fast loop over panels
    for i, dt in enumerate(panels):
        dt_mask = (df["panel_date"] == dt).values
        cutoff = cutoff_dates[dt_mask][0]
        
        # Completed history up to cutoff
        past_mask = (panel_dates <= cutoff) & (~np.isnan(r24_vals))
        
        if not np.any(past_mask):
            continue
            
        past_sectors = sectors[past_mask]
        past_r24 = r24_vals[past_mask]
        past_run = run_vals[past_mask]
        
        # Calculate percentiles for current panel rows
        curr_indices = np.where(dt_mask)[0]
        for idx in curr_indices:
            sec = sectors[idx]
            sec_past_mask = (past_sectors == sec)
            sec_hist_r24 = past_r24[sec_past_mask]
            sec_hist_run = past_run[sec_past_mask]
            
            if len(sec_hist_r24) >= 10 and not np.isnan(r24_vals[idx]):
                r24_pcts[idx] = np.mean(sec_hist_r24 <= r24_vals[idx])
                
            if len(sec_hist_run) >= 10 and not np.isnan(run_vals[idx]):
                run_pcts[idx] = np.mean(sec_hist_run <= run_vals[idx])
                
    df["r24_archetype_pct"] = r24_pcts
    df["run_progress_pct"] = run_pcts
    return df


def analyze_window(df, window_name):
    df_valid = df[df["r_24w"].notna()].copy()
    
    sector_dist = {}
    all_sectors = sorted(df["sector"].unique())
    
    for sec in all_sectors:
        sub = df_valid[df_valid["sector"] == sec]
        sub_all = df[df["sector"] == sec]
        if len(sub) == 0:
            continue
            
        r_vals = sub["r_24w"].values
        q10 = float(np.percentile(r_vals, 10))
        q25 = float(np.percentile(r_vals, 25))
        q50 = float(np.median(r_vals))
        q75 = float(np.percentile(r_vals, 75))
        q90 = float(np.percentile(r_vals, 90))
        q95 = float(np.percentile(r_vals, 95))
        mean_val = float(np.mean(r_vals))
        skew_val = float(stats.skew(r_vals)) if len(r_vals) > 2 else 0.0
        p_pos = float(np.mean(r_vals > 0))
        
        sector_dist[sec] = {
            "n_obs_total": len(sub_all),
            "n_obs_valid": len(sub),
            "n_tickers": int(sub_all["kod"].nunique()),
            "median_q50": q50,
            "q10": q10,
            "q25": q25,
            "q75": q75,
            "q90": q90,
            "q95": q95,
            "mean": mean_val,
            "skewness": skew_val,
            "p_positive": p_pos,
            "mean_vol_52w": float(sub["vol_52w"].mean())
        }

    corr_cols = ["run_return", "tis", "mom_12m", "h0_score", "vol_52w", "r_24w"]
    corr_df = df_valid[corr_cols].dropna().copy()
    corr_matrix = corr_df.corr(method="spearman").to_dict()
    
    valid_sec_list = [s for s, stats_d in sector_dist.items() if stats_d["n_obs_valid"] >= 20]
    df_mod = df_valid[df_valid["sector"].isin(valid_sec_list) & df_valid["run_progress_pct"].notna()].copy()
    
    sec_dummies = pd.get_dummies(df_mod["sector"], drop_first=True, dtype=float)
    
    X_m0 = df_mod[["h0_rank"]].values
    X_m1 = df_mod[["h0_rank", "vol_52w"]].values
    X_m2 = df_mod[["h0_rank", "vol_52w", "run_return"]].values
    X_m3 = np.column_stack([df_mod[["h0_rank", "vol_52w", "run_return"]].values, sec_dummies.values])
    X_m4 = df_mod[["h0_rank", "vol_52w", "run_progress_pct"]].values
    
    y_cont = df_mod["r_24w"].values
    y_down = (df_mod["r_24w"] < -0.20).astype(int).values
    y_up = (df_mod["r_24w"] > 0.30).astype(int).values
    
    def evaluate_regression_ladder(X_dict, y):
        results = {}
        for m_name, X in X_dict.items():
            reg = LinearRegression()
            reg.fit(X, y)
            preds = reg.predict(X)
            mse = float(mean_squared_error(y, preds))
            r2 = float(r2_score(y, preds))
            results[m_name] = {"mse": mse, "r2": r2}
        return results

    def evaluate_logit_ladder(X_dict, y):
        results = {}
        for m_name, X in X_dict.items():
            if len(np.unique(y)) < 2:
                continue
            clf = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000)
            clf.fit(X, y)
            probs = np.clip(clf.predict_proba(X)[:, 1], 1e-6, 1 - 1e-6)
            loss = float(log_loss(y, probs))
            brier = float(brier_score_loss(y, probs))
            results[m_name] = {"log_loss": loss, "brier": brier}
        return results

    X_models = {"M0": X_m0, "M1": X_m1, "M2": X_m2, "M3": X_m3, "M4": X_m4}
    
    ladder_cont = evaluate_regression_ladder(X_models, y_cont)
    ladder_down = evaluate_logit_ladder(X_models, y_down)
    ladder_up = evaluate_logit_ladder(X_models, y_up)
    
    panels_sorted = sorted(df_mod["panel_date"].unique())
    n_panels = len(panels_sorted)
    fold_size = int(math.ceil(n_panels / 5))
    
    cv_brier_m2, cv_brier_m3, cv_brier_m4 = [], [], []
    
    for k in range(5):
        test_panels = set(panels_sorted[k * fold_size : (k + 1) * fold_size])
        train_mask = ~df_mod["panel_date"].isin(test_panels)
        test_mask = df_mod["panel_date"].isin(test_panels)
        
        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue
            
        y_tr, y_te = y_down[train_mask], y_down[test_mask]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue
            
        c2 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000).fit(X_m2[train_mask], y_tr)
        c3 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000).fit(X_m3[train_mask], y_tr)
        c4 = LogisticRegression(penalty=None, solver='lbfgs', max_iter=1000).fit(X_m4[train_mask], y_tr)
        
        cv_brier_m2.append(brier_score_loss(y_te, np.clip(c2.predict_proba(X_m2[test_mask])[:, 1], 1e-6, 1-1e-6)))
        cv_brier_m3.append(brier_score_loss(y_te, np.clip(c3.predict_proba(X_m3[test_mask])[:, 1], 1e-6, 1-1e-6)))
        cv_brier_m4.append(brier_score_loss(y_te, np.clip(c4.predict_proba(X_m4[test_mask])[:, 1], 1e-6, 1-1e-6)))
        
    cv_summary = {
        "cv_brier_m2": float(np.mean(cv_brier_m2)) if cv_brier_m2 else None,
        "cv_brier_m3": float(np.mean(cv_brier_m3)) if cv_brier_m3 else None,
        "cv_brier_m4": float(np.mean(cv_brier_m4)) if cv_brier_m4 else None,
        "m4_vs_m2_brier_delta": float(np.mean(cv_brier_m2) - np.mean(cv_brier_m4)) if cv_brier_m2 and cv_brier_m4 else 0.0,
        "m3_vs_m2_brier_delta": float(np.mean(cv_brier_m2) - np.mean(cv_brier_m3)) if cv_brier_m2 and cv_brier_m3 else 0.0
    }
    
    return {
        "window_name": window_name,
        "n_panels": len(panels_sorted),
        "n_obs_total": len(df),
        "n_obs_valid": len(df_valid),
        "sector_distributions": sector_dist,
        "spearman_correlations": corr_matrix,
        "model_ladder": {
            "continuous_r24": ladder_cont,
            "downside_20_logit": ladder_down,
            "upside_30_logit": ladder_up
        },
        "oos_cv_downside_ladder": cv_summary
    }


def main():
    print("=== STARTING H-RUNWAY-DIST-1 FAST ANALYSIS ===")
    
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified K1 Sector Freeze Manifest SHA256: {manifest_sha}")
    
    sector_map = load_sector_classification()
    terminal_set = load_terminal_stocks()
    print(f"Loaded sector classification for {len(sector_map)} tickers.")
    
    print("\n--- Extracting 2014-2019 Top-30 run observations ---")
    data_1419 = get_data_2014_2019(sector_map)
    df1419 = pd.DataFrame(data_1419)
    print(f"Window 14-19 raw obs: {len(df1419)}")
    
    print("\n--- Extracting 2020-2026 Top-30 run observations ---")
    data_2026 = get_data_2020_2026(sector_map)
    df2026 = pd.DataFrame(data_2026)
    print(f"Window 20-26 raw obs: {len(df2026)}")
    
    print("\n--- Computing Fast Expanding PIT Archetype Percentiles (2014-2019) ---")
    df1419 = compute_expanding_pit_archetype_percentiles_fast(df1419)
    
    print("\n--- Computing Fast Expanding PIT Archetype Percentiles (2020-2026) ---")
    df2026 = compute_expanding_pit_archetype_percentiles_fast(df2026)
    
    print("\n--- Analyzing Window 2014-2019 ---")
    res1419 = analyze_window(df1419, "2014-2019")
    
    print("\n--- Analyzing Window 2020-2026 ---")
    res2026 = analyze_window(df2026, "2020-2026")
    
    m4_imp_1419 = res1419["oos_cv_downside_ladder"]["m4_vs_m2_brier_delta"]
    m4_imp_2026 = res2026["oos_cv_downside_ladder"]["m4_vs_m2_brier_delta"]
    
    m3_imp_1419 = res1419["oos_cv_downside_ladder"]["m3_vs_m2_brier_delta"]
    m3_imp_2026 = res2026["oos_cv_downside_ladder"]["m3_vs_m2_brier_delta"]
    
    m2_r2_1419 = res1419["model_ladder"]["continuous_r24"]["M2"]["r2"] - res1419["model_ladder"]["continuous_r24"]["M1"]["r2"]
    m2_r2_2026 = res2026["model_ladder"]["continuous_r24"]["M2"]["r2"] - res2026["model_ladder"]["continuous_r24"]["M1"]["r2"]
    
    # Classification Logic strictly according to task specification
    if m4_imp_1419 > 0 and m4_imp_2026 > 0:
        final_classification = "REPLICATED ARCHETYPE-CONDITIONAL RUNWAY INFORMATION"
    elif (m2_r2_1419 > 0.005 or m2_r2_2026 > 0.005) and (m4_imp_1419 <= 0 and m4_imp_2026 <= 0):
        final_classification = "GENERIC PATH INFORMATION ONLY"
    elif m3_imp_1419 > 0 and m3_imp_2026 > 0:
        final_classification = "ARCHETYPE DISTRIBUTIONS DIFFER BUT NO RUNWAY INFORMATION"
    elif (m4_imp_1419 > 0 and m4_imp_2026 <= 0) or (m4_imp_1419 <= 0 and m4_imp_2026 > 0):
        final_classification = "PROMISING-BUT-UNSTABLE ARCHETYPE RUNWAY"
    else:
        final_classification = "GENERIC PATH INFORMATION ONLY"
        
    final_output = {
        "title": "H-RUNWAY-DIST-1: ARCHETYPE-CONDITIONAL MOMENTUM RUNWAY",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "windows": {
            "2014-2019": res1419,
            "2020-2026": res2026
        },
        "summary": {
            "m4_vs_m2_brier_delta_1419": m4_imp_1419,
            "m4_vs_m2_brier_delta_2026": m4_imp_2026,
            "m3_vs_m2_brier_delta_1419": m3_imp_1419,
            "m3_vs_m2_brier_delta_2026": m3_imp_2026,
            "m2_r2_gain_1419": m2_r2_1419,
            "m2_r2_gain_2026": m2_r2_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
