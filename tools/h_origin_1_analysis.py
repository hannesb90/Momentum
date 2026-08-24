#!/usr/bin/env python3
"""
H-ORIGIN-1: MOMENTUM ORIGIN — RECOVERY VS EXPANSION PAYOFF

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

OUT_JSON = V2 / "research_k/h_origin_1_results.json"
OUT_DOC = V2 / "docs/H_ORIGIN_1_MOMENTUM_ORIGIN_RECOVERY_VS_EXPANSION.md"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_list_classification():
    qa_path = V2 / "research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    list_map = {}
    for r in qa:
        ml = r.get("market_list")
        if ml == "Large Cap Stockholm":
            list_map[r["instrument_id"]] = "Large Cap"
        elif ml == "Mid Cap Stockholm":
            list_map[r["instrument_id"]] = "Mid Cap"
        elif ml == "Small Cap Stockholm":
            list_map[r["instrument_id"]] = "Small Cap"
        elif r.get("terminal") is True:
            list_map[r["instrument_id"]] = "Terminal/Avnoterad"
        else:
            list_map[r["instrument_id"]] = "Övriga"
    return list_map


def extract_episodes_and_obs_2020_2026(list_map):
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

    def check_origin_drawdown(kod, dt_str):
        """Check prior 2y peak drawdown at start of 1y run (T - 52w)."""
        if kod not in price_series:
            return 0.0
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_start = t0 - np.timedelta64(365, "D")
        t_lookback = t_start - np.timedelta64(730, "D")
        
        i_start = np.searchsorted(ds, t_start, side="right") - 1
        i_lookback = max(0, np.searchsorted(ds, t_lookback, side="right") - 1)
        
        if i_start <= i_lookback or i_start < 0:
            return 0.0
            
        p_start = adjs[i_start]
        prior_peak = np.max(adjs[i_lookback : i_start + 1])
        if prior_peak <= 0:
            return 0.0
        return float(p_start / prior_peak - 1.0)

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

    # Trace continuous episodes (State-S runs)
    # Map (kod, entry_date) -> episode_id
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
            r_24w = get_forward_return(kod, dt, weeks=24)
            dd_at_start = check_origin_drawdown(kod, dt)
            
            obs_list.append({
                "window": "2020-2026",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP26_{ep_id}",
                "entry_date": entry_dt,
                "list_cap": list_map.get(kod, "Övriga"),
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": vol52,
                "tis": tis,
                "run_return": run_return,
                "dd_at_start": dd_at_start,
                "is_recovery_30": 1 if dd_at_start <= -0.30 else 0,
                "is_recovery_40": 1 if dd_at_start <= -0.40 else 0,
                "is_recovery_50": 1 if dd_at_start <= -0.50 else 0,
                "r_24w": r_24w
            })
            
    return obs_list


def extract_episodes_and_obs_2014_2019(list_map):
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

    def check_origin_drawdown(kod, dt_str):
        if kod not in price_series:
            return 0.0
        ds, adjs = price_series[kod]
        t0 = np.datetime64(dt_str)
        t_start = t0 - np.timedelta64(365, "D")
        t_lookback = t_start - np.timedelta64(730, "D")
        
        i_start = np.searchsorted(ds, t_start, side="right") - 1
        i_lookback = max(0, np.searchsorted(ds, t_lookback, side="right") - 1)
        
        if i_start <= i_lookback or i_start < 0:
            return 0.0
            
        p_start = adjs[i_start]
        prior_peak = np.max(adjs[i_lookback : i_start + 1])
        if prior_peak <= 0:
            return 0.0
        return float(p_start / prior_peak - 1.0)

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
            r_24w = get_forward_return(kod, dt, weeks=24)
            dd_at_start = check_origin_drawdown(kod, dt)
            
            obs_list.append({
                "window": "2014-2019",
                "panel_date": dt,
                "panel_idx": pi,
                "kod": kod,
                "episode_id": f"EP14_{ep_id}",
                "entry_date": entry_dt,
                "list_cap": list_map.get(kod, "Övriga"),
                "h0_rank": rank_idx,
                "h0_score": score,
                "vol_52w": v52,
                "tis": tis,
                "run_return": run_return,
                "dd_at_start": dd_at_start,
                "is_recovery_30": 1 if dd_at_start <= -0.30 else 0,
                "is_recovery_40": 1 if dd_at_start <= -0.40 else 0,
                "is_recovery_50": 1 if dd_at_start <= -0.50 else 0,
                "r_24w": r_24w
            })
            
    return obs_list


def analyze_window_origin(df, window_name):
    """Analyze Momentum Origin for one window."""
    df_valid = df[df["r_24w"].notna()].copy()
    
    # Episode level aggregation
    ep_df = df_valid.groupby("episode_id").agg({
        "kod": "first",
        "list_cap": "first",
        "is_recovery_30": "first",
        "is_recovery_40": "first",
        "is_recovery_50": "first",
        "panel_date": ["count", "min", "max"],
        "h0_rank": "mean",
        "vol_52w": "mean",
        "run_return": "mean",
        "r_24w": "first" # initial forward return or mean
    })
    ep_df.columns = ["kod", "list_cap", "is_rec30", "is_rec40", "is_rec50", "ep_length", "dt_min", "dt_max", "mean_rank", "mean_vol", "mean_run", "ep_r24w"]
    
    n_obs = len(df_valid)
    n_episodes = len(ep_df)
    n_tickers = ep_df["kod"].nunique()
    ep_per_ticker = float(n_episodes / max(1, n_tickers))
    med_ep_length = float(ep_df["ep_length"].median())
    
    # Ticker concentration
    top5_ticker_obs = float(df_valid["kod"].value_counts().head(5).sum() / n_obs)
    
    # Category episode counts
    cat_episodes = ep_df.groupby("list_cap").size().to_dict()
    
    # -------------------------------------------------------------
    # STEP D: NEGATIVE CONTROL BASE PRE-CHECK
    # Compare rank, score, vol, run_return, TIS between RECOVERY and EXPANSION
    # -------------------------------------------------------------
    rec_obs = df_valid[df_valid["is_recovery_30"] == 1]
    exp_obs = df_valid[df_valid["is_recovery_30"] == 0]
    
    pre_check = {
        "recovery_n_obs": len(rec_obs),
        "expansion_n_obs": len(exp_obs),
        "recovery_pct_obs": float(len(rec_obs) / n_obs),
        "recovery_mean_rank": float(rec_obs["h0_rank"].mean()),
        "expansion_mean_rank": float(exp_obs["h0_rank"].mean()),
        "recovery_mean_vol": float(rec_obs["vol_52w"].mean()),
        "expansion_mean_vol": float(exp_obs["vol_52w"].mean()),
        "recovery_mean_run_return": float(rec_obs["run_return"].mean()),
        "expansion_mean_run_return": float(exp_obs["run_return"].mean()),
        "recovery_mean_tis": float(rec_obs["tis"].mean()),
        "expansion_mean_tis": float(exp_obs["tis"].mean()),
    }
    
    # -------------------------------------------------------------
    # STEP E & F: DISTRIBUTIONAL PAYOFF OVER 24 WEEKS
    # -------------------------------------------------------------
    def get_dist_stats(sub):
        r = sub["r_24w"].values
        return {
            "n_obs": len(sub),
            "median": float(np.median(r)),
            "q10": float(np.percentile(r, 10)),
            "q25": float(np.percentile(r, 25)),
            "q75": float(np.percentile(r, 75)),
            "q90": float(np.percentile(r, 90)),
            "mean": float(np.mean(r)),
            "p_upside_30": float(np.mean(r > 0.30)),
            "p_downside_20": float(np.mean(r < -0.20))
        }

    payoff_recovery = get_dist_stats(rec_obs)
    payoff_expansion = get_dist_stats(exp_obs)
    
    # -------------------------------------------------------------
    # MODEL CONTROL LADDER
    # M0 = H0 rank + vol_52w
    # M1 = M0 + run_return (generic path)
    # M2 = M1 + is_recovery_30 (MOMENTUM ORIGIN)
    # -------------------------------------------------------------
    X_m0 = df_valid[["h0_rank", "vol_52w"]].values
    X_m1 = df_valid[["h0_rank", "vol_52w", "run_return"]].values
    X_m2 = df_valid[["h0_rank", "vol_52w", "run_return", "is_recovery_30"]].values
    
    y_cont = df_valid["r_24w"].values
    y_down = (df_valid["r_24w"] < -0.20).astype(int).values
    y_up = (df_valid["r_24w"] > 0.30).astype(int).values
    
    # Regression fit
    r0 = LinearRegression().fit(X_m0, y_cont)
    r1 = LinearRegression().fit(X_m1, y_cont)
    r2 = LinearRegression().fit(X_m2, y_cont)
    
    reg_summary = {
        "m0_r2": float(r2_score(y_cont, r0.predict(X_m0))),
        "m1_r2": float(r2_score(y_cont, r1.predict(X_m1))),
        "m2_r2": float(r2_score(y_cont, r2.predict(X_m2))),
        "m2_vs_m1_r2_gain": float(r2_score(y_cont, r2.predict(X_m2)) - r2_score(y_cont, r1.predict(X_m1)))
    }
    
    # 5-Fold Episode-Block Out-of-Sample CV for Downside Logit & Upside Logit
    # Group by episode_id to avoid leakage!
    episodes_unique = df_valid["episode_id"].unique()
    np.random.seed(42)
    np.random.shuffle(episodes_unique)
    
    n_ep = len(episodes_unique)
    ep_fold_size = int(math.ceil(n_ep / 5))
    
    cv_brier_m0, cv_brier_m1, cv_brier_m2 = [], [], []
    cv_logloss_m0, cv_logloss_m1, cv_logloss_m2 = [], [], []
    
    for k in range(5):
        test_eps = set(episodes_unique[k * ep_fold_size : (k + 1) * ep_fold_size])
        tr_mask = ~df_valid["episode_id"].isin(test_eps)
        te_mask = df_valid["episode_id"].isin(test_eps)
        
        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue
            
        y_tr, y_te = y_down[tr_mask], y_down[te_mask]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue
            
        c0 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m0[tr_mask], y_tr)
        c1 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m1[tr_mask], y_tr)
        c2 = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m2[tr_mask], y_tr)
        
        p0 = np.clip(c0.predict_proba(X_m0[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        p1 = np.clip(c1.predict_proba(X_m1[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        p2 = np.clip(c2.predict_proba(X_m2[te_mask])[:, 1], 1e-6, 1 - 1e-6)
        
        cv_brier_m0.append(brier_score_loss(y_te, p0))
        cv_brier_m1.append(brier_score_loss(y_te, p1))
        cv_brier_m2.append(brier_score_loss(y_te, p2))
        
        cv_logloss_m0.append(log_loss(y_te, p0))
        cv_logloss_m1.append(log_loss(y_te, p1))
        cv_logloss_m2.append(log_loss(y_te, p2))
        
    cv_summary = {
        "cv_brier_m0": float(np.mean(cv_brier_m0)) if cv_brier_m0 else None,
        "cv_brier_m1": float(np.mean(cv_brier_m1)) if cv_brier_m1 else None,
        "cv_brier_m2": float(np.mean(cv_brier_m2)) if cv_brier_m2 else None,
        "m2_vs_m1_brier_delta": float(np.mean(cv_brier_m1) - np.mean(cv_brier_m2)) if cv_brier_m1 and cv_brier_m2 else 0.0,
        "m1_vs_m0_brier_delta": float(np.mean(cv_brier_m0) - np.mean(cv_brier_m1)) if cv_brier_m0 and cv_brier_m1 else 0.0
    }
    
    return {
        "window_name": window_name,
        "n_obs_valid": n_obs,
        "n_episodes": n_episodes,
        "n_tickers": n_tickers,
        "episodes_per_ticker": ep_per_ticker,
        "median_episode_length_panels": med_ep_length,
        "top5_ticker_obs_concentration": top5_ticker_obs,
        "category_episodes": cat_episodes,
        "negative_control_precheck": pre_check,
        "payoff_recovery": payoff_recovery,
        "payoff_expansion": payoff_expansion,
        "regression_ladder": reg_summary,
        "oos_cv_downside": cv_summary
    }


def main():
    print("=== STARTING H-ORIGIN-1 ANALYSIS ===")
    
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified K1 Freeze Manifest SHA256: {manifest_sha}")
    
    list_map = load_list_classification()
    print(f"Loaded list classification for {len(list_map)} tickers.")
    
    print("\n--- Extracting 2014-2019 episodes and observations ---")
    data1419 = extract_episodes_and_obs_2014_2019(list_map)
    df1419 = pd.DataFrame(data1419)
    print(f"Window 14-19 raw obs: {len(df1419)}, unique episodes: {df1419['episode_id'].nunique()}")
    
    print("\n--- Extracting 2020-2026 episodes and observations ---")
    data2026 = extract_episodes_and_obs_2020_2026(list_map)
    df2026 = pd.DataFrame(data2026)
    print(f"Window 20-26 raw obs: {len(df2026)}, unique episodes: {df2026['episode_id'].nunique()}")
    
    print("\n--- Analyzing Window 2014-2019 ---")
    res1419 = analyze_window_origin(df1419, "2014-2019")
    
    print("\n--- Analyzing Window 2020-2026 ---")
    res2026 = analyze_window_origin(df2026, "2020-2026")
    
    brier_delta_1419 = res1419["oos_cv_downside"]["m2_vs_m1_brier_delta"]
    brier_delta_2026 = res2026["oos_cv_downside"]["m2_vs_m1_brier_delta"]
    
    r2_gain_1419 = res1419["regression_ladder"]["m2_vs_m1_r2_gain"]
    r2_gain_2026 = res2026["regression_ladder"]["m2_vs_m1_r2_gain"]
    
    # Classification Logic
    if brier_delta_1419 > 0 and brier_delta_2026 > 0 and r2_gain_1419 > 0 and r2_gain_2026 > 0:
        final_classification = "REPLICATED INCREMENTAL MOMENTUM-ORIGIN INFORMATION"
    elif (brier_delta_1419 > 0 and brier_delta_2026 <= 0) or (brier_delta_1419 <= 0 and brier_delta_2026 > 0):
        final_classification = "PROMISING-BUT-UNSTABLE MOMENTUM-ORIGIN INFORMATION"
    else:
        final_classification = "NO INCREMENTAL MOMENTUM-ORIGIN INFORMATION"
        
    final_output = {
        "title": "H-ORIGIN-1: MOMENTUM ORIGIN — RECOVERY VS EXPANSION PAYOFF",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "windows": {
            "2014-2019": res1419,
            "2020-2026": res2026
        },
        "summary": {
            "m2_vs_m1_brier_delta_1419": brier_delta_1419,
            "m2_vs_m1_brier_delta_2026": brier_delta_2026,
            "m2_vs_m1_r2_gain_1419": r2_gain_1419,
            "m2_vs_m1_r2_gain_2026": r2_gain_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
