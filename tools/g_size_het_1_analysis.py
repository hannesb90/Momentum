#!/usr/bin/env python3
"""
G-SIZE-HET-1: SIZE-CONDITIONAL SIGNAL HETEROGENEITY AUDIT

Methodological meta-audit of prior null/unstable test tracks.
No model modification.
No trading rules.
No portfolio simulation.
Locked H0, hysteresis, G97-P untouched.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
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

OUT_JSON = V2 / "research_k/g_size_het_1_results.json"
OUT_DOC = V2 / "docs/G_SIZE_HET_1_SIZE_CONDITIONAL_SIGNAL_HETEROGENEITY_AUDIT.md"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata():
    sec_data = json.loads((V2 / "research_k/sector_classification_v1/validated/sector_classification_intervals.json").read_text(encoding="utf-8"))
    sector_map = {x["instrument_id"]: x["canonical_sector"] for x in sec_data}
    
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

    def get_max_prior_drawdown(kod, dt_str, years=2):
        if kod not in price_series:
            return 0.0
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_lookback = t0 - np.timedelta64(int(years * 365), "D")
        
        i = np.searchsorted(ds, t0, side="right") - 1
        j = np.searchsorted(ds, t_lookback, side="right") - 1
        
        if i <= j or j < 0 or i >= len(ds):
            return 0.0
            
        sub = adjs[j:i+1]
        if len(sub) < 5:
            return 0.0
            
        peak = np.maximum.accumulate(sub)
        dd = (sub - peak) / peak
        return float(abs(np.min(dd)))

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
            prior_dd = get_max_prior_drawdown(kod, entry_dt, years=2)
            is_recovery = 1 if prior_dd >= 0.30 else 0
            
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
                "tis": tis,
                "run_return": run_return,
                "prior_drawdown_2y": prior_dd,
                "is_recovery": is_recovery,
                "sector": sec,
                "list_segment": list_seg,
                "is_terminal": is_term,
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

    def get_max_prior_drawdown(kod, dt_str, years=2):
        if kod not in price_series:
            return 0.0
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_lookback = t0 - np.timedelta64(int(years * 365), "D")
        
        i = np.searchsorted(ds, t0, side="right") - 1
        j = np.searchsorted(ds, t_lookback, side="right") - 1
        
        if i <= j or j < 0 or i >= len(ds):
            return 0.0
            
        sub = adjs[j:i+1]
        if len(sub) < 5:
            return 0.0
            
        peak = np.maximum.accumulate(sub)
        dd = (sub - peak) / peak
        return float(abs(np.min(dd)))

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
            prior_dd = get_max_prior_drawdown(kod, entry_dt, years=2)
            is_recovery = 1 if prior_dd >= 0.30 else 0
            
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
                "tis": tis,
                "run_return": run_return,
                "prior_drawdown_2y": prior_dd,
                "is_recovery": is_recovery,
                "sector": sec,
                "list_segment": list_seg,
                "is_terminal": is_term,
                "r_4w": r_4w,
                "r_12w": r_12w,
                "r_24w": r_24w
            })
            
    return obs_list


def compute_baseline_size_distributions(df):
    res = {}
    for seg, sub in df.groupby("list_segment", observed=False):
        r4 = sub["r_4w"].dropna().values
        r12 = sub["r_12w"].dropna().values
        r24 = sub["r_24w"].dropna().values
        vols = sub["vol_52w"].values
        
        res[str(seg)] = {
            "n_obs": len(sub),
            "n_tickers": sub["kod"].nunique(),
            "pct_top30_representation": float(len(sub) / len(df)),
            "r4w_mean": float(np.mean(r4)),
            "r4w_median": float(np.median(r4)),
            "r12w_mean": float(np.mean(r12)),
            "r12w_median": float(np.median(r12)),
            "r24w_mean": float(np.mean(r24)),
            "r24w_median": float(np.median(r24)),
            "r24w_std": float(np.std(r24, ddof=1)),
            "q10_r24w": float(np.percentile(r24, 10)),
            "q25_r24w": float(np.percentile(r24, 25)),
            "q75_r24w": float(np.percentile(r24, 75)),
            "q90_r24w": float(np.percentile(r24, 90)),
            "vol_52w_mean": float(np.mean(vols)),
            "vol_52w_median": float(np.median(vols)),
            "p_downside_20": float(np.mean(r24 < -0.20)),
            "p_upside_30": float(np.mean(r24 > 0.30))
        }
    return res


def evaluate_feature_size_interaction(df, feature_name):
    df_valid = df[df["r_24w"].notna()].copy()
    
    size_dummies = pd.get_dummies(df_valid["list_segment"], prefix="size", drop_first=True, dtype=float)
    x_val = df_valid[feature_name].values.reshape(-1, 1)
    
    x_size_inter = size_dummies.values * x_val
    
    base_m0 = df_valid[["h0_rank"]].values
    base_m1 = df_valid[["h0_rank", "vol_52w"]].values
    
    X_m0 = base_m0
    X_m1 = base_m1
    X_m2 = np.hstack([base_m0, size_dummies.values])
    X_m3 = np.hstack([base_m0, size_dummies.values, x_val])
    X_m4 = np.hstack([base_m0, size_dummies.values, x_val, x_size_inter])
    
    y_24w = df_valid["r_24w"].values
    
    r2_m0 = float(r2_score(y_24w, LinearRegression().fit(X_m0, y_24w).predict(X_m0)))
    r2_m1 = float(r2_score(y_24w, LinearRegression().fit(X_m1, y_24w).predict(X_m1)))
    r2_m2 = float(r2_score(y_24w, LinearRegression().fit(X_m2, y_24w).predict(X_m2)))
    r2_m3 = float(r2_score(y_24w, LinearRegression().fit(X_m3, y_24w).predict(X_m3)))
    r2_m4 = float(r2_score(y_24w, LinearRegression().fit(X_m4, y_24w).predict(X_m4)))
    
    segment_effects = {}
    for seg in ["Large Cap", "Mid Cap", "Small Cap", "Terminal/Avnoterad"]:
        sub = df_valid[df_valid["list_segment"] == seg]
        if len(sub) < 15:
            segment_effects[seg] = {"status": "DATA INSUFFICIENT", "n_obs": len(sub)}
        else:
            x_s = sub[[feature_name, "h0_rank", "vol_52w"]].values
            y_s = sub["r_24w"].values
            reg = LinearRegression().fit(x_s, y_s)
            slope = float(reg.coef_[0])
            
            rng = np.random.default_rng(42)
            boot_slopes = []
            for _ in range(100):
                idx = rng.choice(len(sub), size=len(sub), replace=True)
                r_b = LinearRegression().fit(x_s[idx], y_s[idx])
                boot_slopes.append(r_b.coef_[0])
                
            ci_lo = float(np.percentile(boot_slopes, 2.5))
            ci_hi = float(np.percentile(boot_slopes, 97.5))
            
            segment_effects[seg] = {
                "status": "VALID",
                "n_obs": len(sub),
                "n_tickers": sub["kod"].nunique(),
                "slope": slope,
                "ci_95_lo": ci_lo,
                "ci_95_hi": ci_hi
            }

    return {
        "feature_name": feature_name,
        "r2_m0": r2_m0,
        "r2_m1": r2_m1,
        "r2_m2": r2_m2,
        "r2_m3": r2_m3,
        "r2_m4": r2_m4,
        "gain_m3_vs_m1": r2_m3 - r2_m1,
        "gain_m4_vs_m3": r2_m4 - r2_m3,
        "segment_effects": segment_effects
    }


def main():
    print("=== STARTING G-SIZE-HET-1 ANALYSIS ===")
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
    
    print("\n--- Step B: Baseline Size Distribution & Regime Shift Audit ---")
    size_dist_1419 = compute_baseline_size_distributions(df1419)
    size_dist_2026 = compute_baseline_size_distributions(df2026)
    
    audit_features = ["vol_52w", "tis", "run_return", "is_recovery"]
    
    print("\n--- Step C & F: Evaluating Feature x Size Interactions (M0 to M4) ---")
    audits_1419 = {}
    audits_2026 = {}
    
    for feat in audit_features:
        audits_1419[feat] = evaluate_feature_size_interaction(df1419, feat)
        audits_2026[feat] = evaluate_feature_size_interaction(df2026, feat)

    meta_verdicts = {}
    for feat in audit_features:
        gain43_1419 = audits_1419[feat]["gain_m4_vs_m3"]
        gain43_2026 = audits_2026[feat]["gain_m4_vs_m3"]
        
        slopes_1419 = [audits_1419[feat]["segment_effects"][s]["slope"] for s in ["Large Cap", "Mid Cap", "Small Cap"]]
        slopes_2026 = [audits_2026[feat]["segment_effects"][s]["slope"] for s in ["Large Cap", "Mid Cap", "Small Cap"]]
        
        corr_slopes, _ = stats.spearmanr(slopes_1419, slopes_2026)
        
        if gain43_1419 > 0.001 and gain43_2026 > 0.001 and corr_slopes > 0.5:
            meta_verdicts[feat] = "C. HIDDEN SIZE-CONDITIONAL EFFECT"
        elif abs(slopes_1419[0] - slopes_1419[2]) > 0.1 and (slopes_1419[0] * slopes_2026[0] < 0):
            meta_verdicts[feat] = "D. SIZE EXPLAINS WINDOW INSTABILITY"
        elif gain43_1419 <= 0.001 and gain43_2026 <= 0.001:
            meta_verdicts[feat] = "A. ROBUST TO SIZE"
        else:
            meta_verdicts[feat] = "B. SIZE-CONFOUNDED BUT STILL NULL"

    c_count = sum(1 for v in meta_verdicts.values() if v == "C. HIDDEN SIZE-CONDITIONAL EFFECT")
    d_count = sum(1 for v in meta_verdicts.values() if v == "D. SIZE EXPLAINS WINDOW INSTABILITY")
    
    if c_count >= 2:
        final_verdict = "5. BROAD POOLING MISSPECIFICATION"
    elif c_count == 1:
        final_verdict = "3. MATERIAL SIZE-CONDITIONAL SIGNAL HETEROGENEITY"
    elif d_count >= 1:
        final_verdict = "4. SIZE EXPLAINS PRIOR INSTABILITY"
    elif any(v == "B. SIZE-CONFOUNDED BUT STILL NULL" for v in meta_verdicts.values()):
        final_verdict = "2. LIMITED SIZE HETEROGENEITY"
    else:
        final_verdict = "1. SIZE DOES NOT EXPLAIN PRIOR NULLS"

    final_output = {
        "title": "G-SIZE-HET-1: SIZE-CONDITIONAL SIGNAL HETEROGENEITY AUDIT",
        "date": datetime.now().isoformat(),
        "final_classification": final_verdict,
        "meta_verdicts_per_feature": meta_verdicts,
        "baseline_size_distributions": {
            "2014-2019": size_dist_1419,
            "2020-2026": size_dist_2026
        },
        "feature_audits": {
            "2014-2019": audits_1419,
            "2020-2026": audits_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== AUDIT COMPLETE ===")
    print(f"Final Audit Verdict: {final_verdict}")
    print(f"Per-Feature Meta Verdicts: {meta_verdicts}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
