#!/usr/bin/env python3
"""
G-PROP-1: STOCK-SPECIFIC MOMENTUM PROPENSITY

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

OUT_JSON = V2 / "research_k/g_prop_1_results.json"
OUT_DOC = V2 / "docs/G_PROP_1_STOCK_SPECIFIC_MOMENTUM_PROPENSITY.md"
MANIFEST_K1 = V2 / "research_k/sector_classification_v1/manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_expanding_pit_propensity(panels, scored_by_panel, top30_by_panel):
    """
    Compute EXPANDING PIT Stock-Specific Momentum Propensity for all tickers at each panel T.
    At panel date T, only historical panel dates < T are used!
    """
    hist_eligible_counts = defaultdict(int)
    hist_top30_counts = defaultdict(int)
    
    total_hist_eligible = 0
    total_hist_top30 = 0
    
    propensity_map = {}
    
    for pi, dt in enumerate(panels):
        if total_hist_eligible > 0:
            pop_prior = float(total_hist_top30 / total_hist_eligible)
        else:
            pop_prior = 30.0 / 300.0
            
        rows = scored_by_panel[dt]
        top30_set = set(top30_by_panel[dt])
        
        for r in rows:
            kod = r["kod"]
            n_elig = hist_eligible_counts[kod]
            n_t30 = hist_top30_counts[kod]
            
            raw_prop = float(n_t30 / max(1, n_elig)) if n_elig > 0 else 0.0
            eb_prop = float((n_t30 + 15.0 * pop_prior) / (n_elig + 15.0))
            
            propensity_map[(dt, kod)] = {
                "n_elig_hist": n_elig,
                "n_t30_hist": n_t30,
                "pop_prior": pop_prior,
                "propensity_raw": raw_prop,
                "propensity_eb": eb_prop
            }
            
        for r in rows:
            kod = r["kod"]
            hist_eligible_counts[kod] += 1
            if kod in top30_set:
                hist_top30_counts[kod] += 1
                
        total_hist_eligible += len(rows)
        total_hist_top30 += len(top30_set)
        
    return propensity_map


def extract_window_data_2020_2026():
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

    # Compute expanding PIT propensity
    prop_map = compute_expanding_pit_propensity(panels, scored_by_panel, top30_by_panel)
    
    remaining_tis_map = {}
    for pi, dt in enumerate(panels):
        top30_curr = top30_by_panel[dt]
        for kod in top30_curr:
            rem = 0
            for k_fw in range(pi + 1, len(panels)):
                dt_fw = panels[k_fw]
                if kod in top30_by_panel[dt_fw]:
                    rem += 1
                else:
                    break
            remaining_tis_map[(dt, kod)] = rem

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
        top30_rows = scored_by_panel[dt][:30]
        next_dt = panels[pi + 1] if pi + 1 < len(panels) else None
        next_top30_set = set(top30_by_panel[next_dt]) if next_dt else set()
        
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
            p_info = prop_map[(dt, kod)]
            
            is_continuation = 1 if kod in next_top30_set else 0
            rem_tis = remaining_tis_map.get((dt, kod), 0)
            
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
                "n_elig_hist": p_info["n_elig_hist"],
                "n_t30_hist": p_info["n_t30_hist"],
                "propensity_raw": p_info["propensity_raw"],
                "propensity_eb": p_info["propensity_eb"],
                "is_continuation": is_continuation,
                "remaining_tis": rem_tis,
                "r_24w": r_24w
            })
            
    return obs_list


def extract_window_data_2014_2019():
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

    # Compute expanding PIT propensity
    prop_map = compute_expanding_pit_propensity(panels, scored_by_panel, top30_by_panel)
    
    remaining_tis_map = {}
    for pi, dt in enumerate(panels):
        top30_curr = top30_by_panel[dt]
        for kod in top30_curr:
            rem = 0
            for k_fw in range(pi + 1, len(panels)):
                dt_fw = panels[k_fw]
                if kod in top30_by_panel[dt_fw]:
                    rem += 1
                else:
                    break
            remaining_tis_map[(dt, kod)] = rem

    episode_map = {}
    episode_counter = 0
    obs_list = []
    
    for pi, dt in enumerate(panels):
        top30_rows = scored_by_panel[dt][:30]
        next_dt = panels[pi + 1] if pi + 1 < len(panels) else None
        next_top30_set = set(top30_by_panel[next_dt]) if next_dt else set()
        
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
            p_info = prop_map[(dt, kod)]
            
            is_continuation = 1 if kod in next_top30_set else 0
            rem_tis = remaining_tis_map.get((dt, kod), 0)
            
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
                "n_elig_hist": p_info["n_elig_hist"],
                "n_t30_hist": p_info["n_t30_hist"],
                "propensity_raw": p_info["propensity_raw"],
                "propensity_eb": p_info["propensity_eb"],
                "is_continuation": is_continuation,
                "remaining_tis": rem_tis,
                "r_24w": r_24w
            })
            
    return obs_list


def analyze_propensity_window(df, window_name):
    """Execute complete G-PROP-1 analysis for one window."""
    df_valid = df[df["r_24w"].notna()].copy()
    
    n_obs = len(df_valid)
    n_episodes = df_valid["episode_id"].nunique()
    n_tickers = df_valid["kod"].nunique()
    
    corr_cols = ["propensity_eb", "propensity_raw", "n_elig_hist", "h0_rank", "h0_score", "vol_52w", "tis", "run_return", "r_24w"]
    corr_df = df_valid[corr_cols].dropna().copy()
    corr_matrix = corr_df.corr(method="spearman").to_dict()
    
    X_m0 = df_valid[["h0_rank"]].values
    X_m1 = df_valid[["h0_rank", "vol_52w", "tis"]].values
    X_m2 = df_valid[["h0_rank", "vol_52w", "tis", "propensity_eb"]].values
    
    # 1. Continuation Outcome
    y_cont = df_valid["is_continuation"].values
    c0_cont = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m0, y_cont)
    c1_cont = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m1, y_cont)
    c2_cont = LogisticRegression(penalty=None, solver="lbfgs", max_iter=1000).fit(X_m2, y_cont)
    
    p0_c = np.clip(c0_cont.predict_proba(X_m0)[:, 1], 1e-6, 1 - 1e-6)
    p1_c = np.clip(c1_cont.predict_proba(X_m1)[:, 1], 1e-6, 1 - 1e-6)
    p2_c = np.clip(c2_cont.predict_proba(X_m2)[:, 1], 1e-6, 1 - 1e-6)
    
    continuation_eval = {
        "brier_m0": float(brier_score_loss(y_cont, p0_c)),
        "brier_m1": float(brier_score_loss(y_cont, p1_c)),
        "brier_m2": float(brier_score_loss(y_cont, p2_c)),
        "brier_delta_m2_m1": float(brier_score_loss(y_cont, p1_c) - brier_score_loss(y_cont, p2_c))
    }
    
    # 2. Persistence Outcome (Remaining TIS)
    y_rem_tis = df_valid["remaining_tis"].values
    r0_tis = LinearRegression().fit(X_m0, y_rem_tis)
    r1_tis = LinearRegression().fit(X_m1, y_rem_tis)
    r2_tis = LinearRegression().fit(X_m2, y_rem_tis)
    
    persistence_eval = {
        "m0_r2": float(r2_score(y_rem_tis, r0_tis.predict(X_m0))),
        "m1_r2": float(r2_score(y_rem_tis, r1_tis.predict(X_m1))),
        "m2_r2": float(r2_score(y_rem_tis, r2_tis.predict(X_m2))),
        "r2_gain_m2_m1": float(r2_score(y_rem_tis, r2_tis.predict(X_m2)) - r2_score(y_rem_tis, r1_tis.predict(X_m1)))
    }
    
    # 3. Forward 24w Return
    y_24w = df_valid["r_24w"].values
    r0_24 = LinearRegression().fit(X_m0, y_24w)
    r1_24 = LinearRegression().fit(X_m1, y_24w)
    r2_24 = LinearRegression().fit(X_m2, y_24w)
    
    return_eval = {
        "m0_r2": float(r2_score(y_24w, r0_24.predict(X_m0))),
        "m1_r2": float(r2_score(y_24w, r1_24.predict(X_m1))),
        "m2_r2": float(r2_score(y_24w, r2_24.predict(X_m2))),
        "r2_gain_m2_m1": float(r2_score(y_24w, r2_24.predict(X_m2)) - r2_score(y_24w, r1_24.predict(X_m1)))
    }
    
    # 4. Downside Risk (R24w < -20%) 5-Fold Episode-Block Out-of-Sample CV
    y_down_24w = (y_24w < -0.20).astype(int)
    
    episodes_unique = df_valid["episode_id"].unique()
    np.random.seed(42)
    np.random.shuffle(episodes_unique)
    
    n_ep = len(episodes_unique)
    ep_fold_size = int(math.ceil(n_ep / 5))
    
    cv_brier_m0, cv_brier_m1, cv_brier_m2 = [], [], []
    
    for k in range(5):
        test_eps = set(episodes_unique[k * ep_fold_size : (k + 1) * ep_fold_size])
        tr_mask = ~df_valid["episode_id"].isin(test_eps)
        te_mask = df_valid["episode_id"].isin(test_eps)
        
        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue
            
        y_tr, y_te = y_down_24w[tr_mask], y_down_24w[te_mask]
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
        
    cv_downside = {
        "cv_brier_m0": float(np.mean(cv_brier_m0)),
        "cv_brier_m1": float(np.mean(cv_brier_m1)),
        "cv_brier_m2": float(np.mean(cv_brier_m2)),
        "m2_vs_m1_brier_delta": float(np.mean(cv_brier_m1) - np.mean(cv_brier_m2))
    }
    
    res_m1 = LinearRegression().fit(X_m1, df_valid["propensity_eb"].values)
    df_valid["prop_res"] = df_valid["propensity_eb"].values - res_m1.predict(X_m1)
    df_valid["prop_quintile"] = pd.qcut(df_valid["prop_res"], 5, labels=["Q1_Low", "Q2", "Q3", "Q4", "Q5_High"])
    
    quintile_payoff = {}
    for q_name, sub in df_valid.groupby("prop_quintile", observed=False):
        if len(sub) == 0:
            continue
        r24 = sub["r_24w"].values
        quintile_payoff[str(q_name)] = {
            "n_obs": len(sub),
            "mean_prop_eb": float(sub["propensity_eb"].mean()),
            "mean_prop_res": float(sub["prop_res"].mean()),
            "mean_n_elig_hist": float(sub["n_elig_hist"].mean()),
            "median_r24w": float(np.median(r24)),
            "mean_r24w": float(np.mean(r24)),
            "p_downside_20": float(np.mean(r24 < -0.20)),
            "p_upside_30": float(np.mean(r24 > 0.30)),
            "continuation_rate": float(sub["is_continuation"].mean()),
            "mean_remaining_tis": float(sub["remaining_tis"].mean())
        }

    return {
        "window_name": window_name,
        "n_obs_valid": n_obs,
        "n_episodes": n_episodes,
        "n_tickers": n_tickers,
        "spearman_correlations": corr_matrix,
        "continuation_eval": continuation_eval,
        "persistence_eval": persistence_eval,
        "return_24w_eval": return_eval,
        "oos_cv_downside_24w": cv_downside,
        "quintile_payoff": quintile_payoff
    }


def main():
    print("=== STARTING G-PROP-1 ANALYSIS ===")
    manifest_sha = sha256_file(MANIFEST_K1)
    print(f"Verified K1 Freeze Manifest SHA256: {manifest_sha}")
    
    print("\n--- Extracting 2014-2019 dataset & PIT propensity ---")
    data1419 = extract_window_data_2014_2019()
    df1419 = pd.DataFrame(data1419)
    print(f"Window 14-19 raw obs: {len(df1419)}, episodes: {df1419['episode_id'].nunique()}")
    
    print("\n--- Extracting 2020-2026 dataset & PIT propensity ---")
    data2026 = extract_window_data_2020_2026()
    df2026 = pd.DataFrame(data2026)
    print(f"Window 20-26 raw obs: {len(df2026)}, episodes: {df2026['episode_id'].nunique()}")
    
    print("\n--- Analyzing Window 2014-2019 ---")
    res1419 = analyze_propensity_window(df1419, "2014-2019")
    
    print("\n--- Analyzing Window 2020-2026 ---")
    res2026 = analyze_propensity_window(df2026, "2020-2026")
    
    brier_m2_m1_1419 = res1419["oos_cv_downside_24w"]["m2_vs_m1_brier_delta"]
    brier_m2_m1_2026 = res2026["oos_cv_downside_24w"]["m2_vs_m1_brier_delta"]
    
    r2_ret_1419 = res1419["return_24w_eval"]["r2_gain_m2_m1"]
    r2_ret_2026 = res2026["return_24w_eval"]["r2_gain_m2_m1"]
    
    r2_pers_1419 = res1419["persistence_eval"]["r2_gain_m2_m1"]
    r2_pers_2026 = res2026["persistence_eval"]["r2_gain_m2_m1"]
    
    brier_cont_1419 = res1419["continuation_eval"]["brier_delta_m2_m1"]
    brier_cont_2026 = res2026["continuation_eval"]["brier_delta_m2_m1"]
    
    if brier_m2_m1_1419 > 0 and brier_m2_m1_2026 > 0 and r2_ret_1419 > 0.001 and r2_ret_2026 > 0.001:
        final_classification = "REPLICATED INCREMENTAL PROPENSITY INFORMATION"
    elif brier_cont_1419 > 0 and brier_cont_2026 > 0 and (r2_ret_1419 <= 0.0005 or r2_ret_2026 <= 0.0005):
        final_classification = "GENERIC BASELINE INFORMATION — REDUNDANT WITH RANK/VOL/TIS"
    elif (brier_m2_m1_1419 > 0 and brier_m2_m1_2026 <= 0) or (brier_m2_m1_1419 <= 0 and brier_m2_m1_2026 > 0):
        final_classification = "PROMISING-BUT-UNSTABLE PROPENSITY INFORMATION"
    else:
        final_classification = "NO INCREMENTAL PROPENSITY INFORMATION"
        
    final_output = {
        "title": "G-PROP-1: STOCK-SPECIFIC MOMENTUM PROPENSITY",
        "date": datetime.now().isoformat(),
        "final_classification": final_classification,
        "windows": {
            "2014-2019": res1419,
            "2020-2026": res2026
        },
        "summary": {
            "brier_downside_m2_m1_1419": brier_m2_m1_1419,
            "brier_downside_m2_m1_2026": brier_m2_m1_2026,
            "r2_return24w_m2_m1_1419": r2_ret_1419,
            "r2_return24w_m2_m1_2026": r2_ret_2026,
            "r2_persistence_m2_m1_1419": r2_pers_1419,
            "r2_persistence_m2_m1_2026": r2_pers_2026,
            "brier_continuation_m2_m1_1419": brier_cont_1419,
            "brier_continuation_m2_m1_2026": brier_cont_2026
        }
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== ANALYSIS COMPLETE ===")
    print(f"Final Track Classification: {final_classification}")
    print(f"Results saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
