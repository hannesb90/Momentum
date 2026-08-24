#!/usr/bin/env python3
"""
G-HET-1: CONDITIONAL STOCK POPULATION HETEROGENEITY

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

OUT_JSON = V2 / "research_k/g_het_1_results.json"
OUT_DOC = V2 / "docs/G_HET_1_CONDITIONAL_STOCK_POPULATION_HETEROGENEITY.md"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata():
    # K1 Sector
    sec_data = json.loads((V2 / "research_k/sector_classification_v1/validated/sector_classification_intervals.json").read_text(encoding="utf-8"))
    sector_map = {x["instrument_id"]: x["canonical_sector"] for x in sec_data}
    
    # List Segment
    qa = json.loads((V2 / "research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json").read_text(encoding="utf-8"))
    list_map = {}
    terminal_map = {}
    for r in qa:
        kod = r["instrument_id"]
        ml = r.get("market_list")
        if ml == "Large Cap Stockholm":
            list_map[kod] = "Large Cap"
        elif ml == "Mid Cap Stockholm":
            list_map[kod] = "Mid Cap"
        elif ml == "Small Cap Stockholm":
            list_map[kod] = "Small Cap"
        elif r.get("terminal") is True:
            list_map[kod] = "Terminal/Avnoterad"
        else:
            list_map[kod] = "Övriga"
        terminal_map[kod] = r.get("terminal", False)
        
    return sector_map, list_map, terminal_map


def extract_window_data_2020_2026(sector_map, list_map, terminal_map):
    core_path = V2 / "panels/core_panel.json"
    prices_path = V2 / "validated/prices/prices_validated.json"
    
    core = json.loads(core_path.read_text(encoding="utf-8"))
    prices_raw = json.loads(prices_path.read_text(encoding="utf-8"))
    
    price_series = {}
    for k, rs in prices_raw.items():
        ds = np.array([np.datetime64(r["d"]) for r in rs])
        adjs = np.array([float(r["adj"]) for r in rs])
        price_series[k] = (ds, adjs)
        
    def get_forward_return(kod, dt_str, weeks):
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
        
    all_dates = sorted(by_date.keys())
    
    top30_by_panel = {}
    scored_by_panel = {}
    
    for dt in all_dates:
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

    panels = sorted(scored_by_panel.keys())

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
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
            entry_dt = panels[pi - k + 1] if (pi - k + 1) >= 0 else panels[0]
            
            ep_key = (kod, entry_dt)
            if ep_key not in episode_map:
                episode_counter += 1
                episode_map[ep_key] = episode_counter
            ep_id = episode_map[ep_key]
            
            r_4w = get_forward_return(kod, dt, weeks=4)
            r_12w = get_forward_return(kod, dt, weeks=12)
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            sec = sector_map.get(kod, "UNKNOWN")
            list_seg = list_map.get(kod, "Övriga")
            is_term = terminal_map.get(kod, False)
            
            obs_list.append({
                "window": "2020-2026",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP26_{ep_id}",
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": vol52,
                "sector": sec,
                "list_segment": list_seg,
                "is_terminal": is_term,
                "sector_x_list": f"{list_seg} {sec}",
                "r_4w": r_4w,
                "r_12w": r_12w,
                "r_24w": r_24w
            })
            
    return obs_list


def extract_window_data_2014_2019(sector_map, list_map, terminal_map):
    prices_path = V2 / "validated/prices_h1419/prices_h1419_universum_v2.json"
    if not prices_path.exists():
        prices_path = V2 / "validated/prices_h1419/prices_h1419_universum.json"
        
    prices_raw = json.loads(prices_path.read_text(encoding="utf-8"))
    
    price_series = {}
    for k, rs in prices_raw.items():
        ds = np.array([np.datetime64(r["d"]) for r in rs])
        adjs = np.array([float(r["adj"]) for r in rs])
        price_series[k] = (ds, adjs)
        
    all_dates = []
    cur = date(2014, 1, 1)
    end = date(2019, 12, 31)
    while cur <= end:
        all_dates.append(cur.isoformat())
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

    def get_forward_return(kod, dt_str, weeks):
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
    
    for dt in all_dates:
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

    panels = sorted(scored_by_panel.keys())

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
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
            entry_dt = panels[pi - k + 1] if (pi - k + 1) >= 0 else panels[0]
            
            ep_key = (kod, entry_dt)
            if ep_key not in episode_map:
                episode_counter += 1
                episode_map[ep_key] = episode_counter
            ep_id = episode_map[ep_key]
            
            r_4w = get_forward_return(kod, dt, weeks=4)
            r_12w = get_forward_return(kod, dt, weeks=12)
            r_24w = get_forward_return(kod, dt, weeks=24)
            
            sec = sector_map.get(kod, "UNKNOWN")
            list_seg = list_map.get(kod, "Övriga")
            is_term = terminal_map.get(kod, False)
            
            obs_list.append({
                "window": "2014-2019",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP14_{ep_id}",
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": v52,
                "sector": sec,
                "list_segment": list_seg,
                "is_terminal": is_term,
                "sector_x_list": f"{list_seg} {sec}",
                "r_4w": r_4w,
                "r_12w": r_12w,
                "r_24w": r_24w
            })
            
    return obs_list


def compute_group_distributions(df, group_col):
    res = {}
    for grp_val, sub in df.groupby(group_col, observed=False):
        if len(sub) == 0:
            continue
        r24 = sub["r_24w"].dropna().values
        if len(r24) == 0:
            continue
        res[str(grp_val)] = {
            "n_obs": len(sub),
            "n_tickers": sub["kod"].nunique(),
            "mean_r24w": float(np.mean(r24)),
            "median_r24w": float(np.median(r24)),
            "std_r24w": float(np.std(r24, ddof=1)),
            "q10_r24w": float(np.percentile(r24, 10)),
            "q25_r24w": float(np.percentile(r24, 25)),
            "q75_r24w": float(np.percentile(r24, 75)),
            "q90_r24w": float(np.percentile(r24, 90)),
            "p_downside_20": float(np.mean(r24 < -0.20)),
            "p_upside_30": float(np.mean(r24 > 0.30))
        }
    return res


def evaluate_models_m0_to_m4(df):
    """
    Evaluates M0 to M4 using 5-fold episode-blocked CV for downside, upside, and linear R2 for location.
    
    M0: h0_rank
    M1: h0_rank + vol_52w
    M2: M1 + sector_dummies
    M3: M1 + list_segment_dummies
    M4: M1 + sector_dummies + list_segment_dummies
    """
    df_valid = df[df["r_24w"].notna()].copy()
    
    # One-hot encode sector and list_segment
    sec_dummies = pd.get_dummies(df_valid["sector"], prefix="sec", drop_first=True, dtype=float)
    list_dummies = pd.get_dummies(df_valid["list_segment"], prefix="list", drop_first=True, dtype=float)
    
    base_m0 = df_valid[["h0_rank"]].values
    base_m1 = df_valid[["h0_rank", "vol_52w"]].values
    
    X_m0 = base_m0
    X_m1 = base_m1
    X_m2 = np.hstack([base_m1, sec_dummies.values])
    X_m3 = np.hstack([base_m1, list_dummies.values])
    X_m4 = np.hstack([base_m1, sec_dummies.values, list_dummies.values])
    
    y_24w = df_valid["r_24w"].values
    y_down_20 = (y_24w < -0.20).astype(int)
    y_up_30 = (y_24w > 0.30).astype(int)
    
    # In-sample R2 for location
    r2_m0 = float(r2_score(y_24w, LinearRegression().fit(X_m0, y_24w).predict(X_m0)))
    r2_m1 = float(r2_score(y_24w, LinearRegression().fit(X_m1, y_24w).predict(X_m1)))
    r2_m2 = float(r2_score(y_24w, LinearRegression().fit(X_m2, y_24w).predict(X_m2)))
    r2_m3 = float(r2_score(y_24w, LinearRegression().fit(X_m3, y_24w).predict(X_m3)))
    r2_m4 = float(r2_score(y_24w, LinearRegression().fit(X_m4, y_24w).predict(X_m4)))
    
    # 5-fold Episode-Block CV for Downside (R24w < -20%) and Upside (R24w > +30%)
    episodes_unique = df_valid["episode_id"].unique()
    np.random.seed(42)
    np.random.shuffle(episodes_unique)
    
    n_ep = len(episodes_unique)
    ep_fold_size = int(math.ceil(n_ep / 5))
    
    cv_down = {m: [] for m in ("m0", "m1", "m2", "m3", "m4")}
    cv_up = {m: [] for m in ("m0", "m1", "m2", "m3", "m4")}
    
    models = {"m0": X_m0, "m1": X_m1, "m2": X_m2, "m3": X_m3, "m4": X_m4}
    
    for k in range(5):
        test_eps = set(episodes_unique[k * ep_fold_size : (k + 1) * ep_fold_size])
        tr_mask = ~df_valid["episode_id"].isin(test_eps)
        te_mask = df_valid["episode_id"].isin(test_eps)
        
        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue
            
        y_tr_down, y_te_down = y_down_20[tr_mask], y_down_20[te_mask]
        y_tr_up, y_te_up = y_up_30[tr_mask], y_up_30[te_mask]
        
        if len(np.unique(y_tr_down)) < 2 or len(np.unique(y_te_down)) < 2:
            continue
        if len(np.unique(y_tr_up)) < 2 or len(np.unique(y_te_up)) < 2:
            continue
            
        for m_name, X_mat in models.items():
            # Downside fit
            c_d = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_mat[tr_mask], y_tr_down)
            p_d = np.clip(c_d.predict_proba(X_mat[te_mask])[:, 1], 1e-6, 1 - 1e-6)
            cv_down[m_name].append(brier_score_loss(y_te_down, p_d))
            
            # Upside fit
            c_u = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_mat[tr_mask], y_tr_up)
            p_u = np.clip(c_u.predict_proba(X_mat[te_mask])[:, 1], 1e-6, 1 - 1e-6)
            cv_up[m_name].append(brier_score_loss(y_te_up, p_u))
            
    downside_cv_brier = {m: float(np.mean(vals)) for m, vals in cv_down.items()}
    upside_cv_brier = {m: float(np.mean(vals)) for m, vals in cv_up.items()}
    
    return {
        "location_r2": {
            "m0": r2_m0, "m1": r2_m1, "m2": r2_m2, "m3": r2_m3, "m4": r2_m4,
            "gain_m2_vs_m1": r2_m2 - r2_m1,
            "gain_m3_vs_m1": r2_m3 - r2_m1,
            "gain_m4_vs_m1": r2_m4 - r2_m1
        },
        "downside_cv_brier": downside_cv_brier,
        "downside_brier_deltas_vs_m1": {
            "m2_vs_m1": downside_cv_brier["m1"] - downside_cv_brier["m2"], # positive if M2 beats M1
            "m3_vs_m1": downside_cv_brier["m1"] - downside_cv_brier["m3"],
            "m4_vs_m1": downside_cv_brier["m1"] - downside_cv_brier["m4"]
        },
        "upside_cv_brier": upside_cv_brier,
        "upside_brier_deltas_vs_m1": {
            "m2_vs_m1": upside_cv_brier["m1"] - upside_cv_brier["m2"],
            "m3_vs_m1": upside_cv_brier["m1"] - upside_cv_brier["m3"],
            "m4_vs_m1": upside_cv_brier["m1"] - upside_cv_brier["m4"]
        }
    }


def analyze_sector_x_list_interaction(df):
    """
    Tests Sector x List Segment interaction ONLY where cell size N >= 30.
    """
    res = {}
    for cell_val, sub in df.groupby("sector_x_list", observed=False):
        r24 = sub["r_24w"].dropna().values
        n_obs = len(sub)
        if n_obs < 30:
            res[str(cell_val)] = {
                "status": "DATA INSUFFICIENT",
                "n_obs": n_obs,
                "n_tickers": sub["kod"].nunique()
            }
        else:
            res[str(cell_val)] = {
                "status": "VALID",
                "n_obs": n_obs,
                "n_tickers": sub["kod"].nunique(),
                "mean_r24w": float(np.mean(r24)),
                "median_r24w": float(np.median(r24)),
                "std_r24w": float(np.std(r24, ddof=1)),
                "p_downside_20": float(np.mean(r24 < -0.20)),
                "p_upside_30": float(np.mean(r24 > 0.30))
            }
    return res


def main():
    print("=== STARTING G-HET-1 ANALYSIS ===")
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified K1 Freeze Manifest SHA256: {manifest_sha}")
    
    sector_map, list_map, terminal_map = load_metadata()
    
    print("\n--- Extracting 2014-2019 dataset ---")
    data1419 = extract_window_data_2014_2019(sector_map, list_map, terminal_map)
    df1419 = pd.DataFrame(data1419)
    print(f"Window 14-19 obs: {len(df1419)}, tickers: {df1419['kod'].nunique()}")
    
    print("\n--- Extracting 2020-2026 dataset ---")
    data2026 = extract_window_data_2020_2026(sector_map, list_map, terminal_map)
    df2026 = pd.DataFrame(data2026)
    print(f"Window 20-26 obs: {len(df2026)}, tickers: {df2026['kod'].nunique()}")
    
    print("\n--- Analyzing Group Distributions ---")
    sec_dist_1419 = compute_group_distributions(df1419, "sector")
    sec_dist_2026 = compute_group_distributions(df2026, "sector")
    
    list_dist_1419 = compute_group_distributions(df1419, "list_segment")
    list_dist_2026 = compute_group_distributions(df2026, "list_segment")
    
    print("\n--- Evaluating Models M0 to M4 ---")
    m_eval_1419 = evaluate_models_m0_to_m4(df1419)
    m_eval_2026 = evaluate_models_m0_to_m4(df2026)
    
    print("\n--- Analyzing Sector x List Interactions ---")
    cell_eval_1419 = analyze_sector_x_list_interaction(df1419)
    cell_eval_2026 = analyze_sector_x_list_interaction(df2026)
    
    # Determine Final Classification according to preregistered rules:
    # Check Downside Brier Deltas for M2 (Sector) & M3 (List Segment)
    m2_down_1419 = m_eval_1419["downside_brier_deltas_vs_m1"]["m2_vs_m1"]
    m2_down_2026 = m_eval_2026["downside_brier_deltas_vs_m1"]["m2_vs_m1"]
    
    m3_down_1419 = m_eval_1419["downside_brier_deltas_vs_m1"]["m3_vs_m1"]
    m3_down_2026 = m_eval_2026["downside_brier_deltas_vs_m1"]["m3_vs_m1"]
    
    # Check Location R2 gains for M2 & M3
    m2_r2_1419 = m_eval_1419["location_r2"]["gain_m2_vs_m1"]
    m2_r2_2026 = m_eval_2026["location_r2"]["gain_m2_vs_m1"]
    
    # Rule 8 threshold check
    replicated_downside_sector = (m2_down_1419 > 0 and m2_down_2026 > 0)
    replicated_downside_list = (m3_down_1419 > 0 and m3_down_2026 > 0)
    
    replicated_payoff_sector = (m2_r2_1419 > 0.001 and m2_r2_2026 > 0.001)
    
    if (replicated_downside_sector or replicated_downside_list) and replicated_payoff_sector:
        final_classification = "4. BROAD STRUCTURAL HETEROGENEITY"
    elif replicated_payoff_sector and not (replicated_downside_sector or replicated_downside_list):
        final_classification = "3. PAYOFF HETEROGENEITY"
    elif (replicated_downside_sector or replicated_downside_list) and not replicated_payoff_sector:
        final_classification = "2. RISK HETEROGENEITY ONLY"
    elif (m2_down_1419 > 0 and m2_down_2026 <= 0) or (m2_down_1419 <= 0 and m2_down_2026 > 0):
        final_classification = "5. REGIME-DEPENDENT / UNSTABLE"
    else:
        final_classification = "1. CONDITIONAL HOMOGENEITY SUPPORTED"

    final_output = {
        "title": "G-HET-1: CONDITIONAL STOCK POPULATION HETEROGENEITY",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "windows": {
            "2014-2019": {
                "n_obs": len(df1419),
                "n_tickers": df1419["kod"].nunique(),
                "n_episodes": df1419["episode_id"].nunique(),
                "sector_distributions": sec_dist_1419,
                "list_segment_distributions": list_dist_1419,
                "model_evaluations": m_eval_1419,
                "sector_x_list": cell_eval_1419
            },
            "2020-2026": {
                "n_obs": len(df2026),
                "n_tickers": df2026["kod"].nunique(),
                "n_episodes": df2026["episode_id"].nunique(),
                "sector_distributions": sec_dist_2026,
                "list_segment_distributions": list_dist_2026,
                "model_evaluations": m_eval_2026,
                "sector_x_list": cell_eval_2026
            }
        },
        "summary": {
            "m2_sector_downside_brier_delta_1419": m2_down_1419,
            "m2_sector_downside_brier_delta_2026": m2_down_2026,
            "m3_list_downside_brier_delta_1419": m3_down_1419,
            "m3_list_downside_brier_delta_2026": m3_down_2026,
            "m2_sector_r2_gain_1419": m2_r2_1419,
            "m2_sector_r2_gain_2026": m2_r2_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
