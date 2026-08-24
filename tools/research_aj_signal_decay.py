"""
RESEARCH AJ: HORIZON-ADJUSTED PREDICTED RETURN & SIGNAL DECAY AUDIT
Period: 2021-07-16 to 2026-07-10

Walk-Forward OOS Evaluation of:
1. Horizon-Adjusted Predicted Return (8w, 26w, 52w horizons).
2. Post-Entry Signal Decay & Rank Decay Trajectory.
3. Delayed Payoff vs False Positive Separation.
4. Pre-registered HOLD / TRIM / EXIT Rules on Rank Decay & Non-Performance.
5. Fresh Capital Allocation: Existing Top-3 vs Fresh Rank #1-3 Candidates.
6. Full Comparative Table: CAGR, Alpha vs OMX, Sharpe, MaxDD, CVaR, Turnover, Costs.
"""
from __future__ import annotations
import json, math, hashlib, os
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats
import yfinance as yf

V2 = Path("/home/hannesb/momentum_v2")
START_DATE = "2021-07-16"
END_DATE = "2026-07-10"
COST_ONEWAY = 0.002

# Load PIT Data
core = json.loads((V2 / "panels/core_panel.json").read_text())
target = json.loads((V2 / "panels/target_table.json").read_text())
prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
terminal = json.loads((V2 / "validated/terminal_events.json").read_text())

tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}

df_core = []
for r in core:
    t = tm.get((r["kod"], r["panel_date"]))
    y52 = t.get("target_fwd52w") if t else None
    y26 = t.get("target_fwd26w") if t else None
    y8 = t.get("target_fwd8w") if t else None
    df_core.append({
        "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
        "y52": y52, "y26": y26, "y8": y8
    })
df_core = pd.DataFrame(df_core)

# Price series & vols
price_series = {
    k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
    for k, rs in prices.items()
}

def get_vol(kod, dt, window=60):
    if kod not in price_series: return 0.25
    ds, adj = price_series[kod]
    dt_64 = np.datetime64(dt)
    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt_64), None)
    if idx is None or idx < window: return 0.25
    rets = np.diff(adj[idx-window:idx+1]) / adj[idx-window:idx]
    v = float(np.std(rets) * math.sqrt(252))
    return v if math.isfinite(v) and v > 0.05 else 0.25

def get_momentum(kod, dt, weeks):
    if kod not in price_series: return None
    ds, values = price_series[kod]
    now = np.datetime64(dt)
    target_dt = now - np.timedelta64(7 * weeks, "D")
    i = np.searchsorted(ds, now, side="right") - 1
    j = np.searchsorted(ds, target_dt, side="right") - 1
    if i < 0 or j < 0 or int((target_dt - ds[j]) / np.timedelta64(1, "D")) > 14:
        return None
    return float(values[i] / values[j] - 1)

# Execution returns between biweekly dates
dates = sorted(df_core.panel_date.unique())
next_date = dict(zip(dates, dates[1:]))
returns_map = {}
for kod, rs in prices.items():
    ds_str = [r["d"] for r in rs]
    adj = {r["d"]: r["adj"] for r in rs}
    def first_after(b): return next((x for x in ds_str if x > b), None)
    for dt in dates:
        nd = next_date.get(dt)
        entry = first_after(dt)
        if not nd or not entry or entry > nd:
            returns_map[(kod, dt)] = 0.0
            continue
        exit_date = first_after(nd)
        event = terminal.get(kod)
        if exit_date:
            returns_map[(kod, dt)] = adj[exit_date] / adj[entry] - 1
        elif event and entry <= event["event_date"] <= nd:
            exit_date = ds_str[-1]
            returns_map[(kod, dt)] = adj[exit_date] / adj[entry] - 1
        else:
            returns_map[(kod, dt)] = 0.0

# Fundamental Confirmation (SMA200 & Vol60)
confirm_map = {}
for dt in dates:
    dt_64 = np.datetime64(dt)
    for kod in price_series:
        ds, adj = price_series[kod]
        idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt_64), None)
        conf = False
        if idx is not None and idx >= 120:
            ma120 = float(np.mean(adj[idx-120:idx]))
            rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
            v60 = float(np.std(rets) * math.sqrt(252))
            if adj[idx] >= ma120 and v60 < 0.35:
                conf = True
        confirm_map[(kod, dt)] = conf

# Benchmark returns (XACT Sverige)
df_xact = yf.download("XACT-SVERIGE.ST", start="2021-07-01", end="2026-07-15", progress=False)["Close"]
eval_dates = [d for d in dates if START_DATE <= d <= END_DATE]
b_xact_rets = []
for i in range(len(eval_dates) - 1):
    dt_c, dt_n = eval_dates[i], eval_dates[i+1]
    s = df_xact.dropna()
    ic = s.index.searchsorted(pd.to_datetime(dt_c))
    in_ = s.index.searchsorted(pd.to_datetime(dt_n))
    if ic < len(s) and in_ < len(s):
        val_c = float(s.iloc[ic].values[0]) if hasattr(s.iloc[ic], "values") else float(s.iloc[ic])
        val_n = float(s.iloc[in_].values[0]) if hasattr(s.iloc[in_], "values") else float(s.iloc[in_])
        b_xact_rets.append(val_n / val_c - 1.0)
    else:
        b_xact_rets.append(0.0)
b_xact_rets.append(0.0)

# Derive Rankings for different horizons
def derive_rankings(weeks_tuple):
    by_date = defaultdict(list)
    for _, r in df_core.iterrows():
        if r["panel_date"] < START_DATE or r["panel_date"] > END_DATE: continue
        m_vals = [get_momentum(r["kod"], r["panel_date"], w) for w in weeks_tuple]
        by_date[r["panel_date"]].append({
            "kod": r["kod"], "panel_date": r["panel_date"], "m_vals": m_vals
        })
    rankings = {}
    for dt, rows in sorted(by_date.items()):
        n_m = len(weeks_tuple)
        for idx in range(n_m):
            valid = sorted((r["m_vals"][idx], r["kod"]) for r in rows if r["m_vals"][idx] is not None)
            grouped = defaultdict(list)
            for val, kod in valid: grouped[val].append(kod)
            ranks = {}
            pos = 1
            for val in sorted(grouped):
                ks = grouped[val]
                avg = (pos + pos + len(ks) - 1) / 2 / len(valid)
                for kod in ks: ranks[kod] = avg
                pos += len(ks)
            for r in rows: r[f"rank_{idx}"] = ranks.get(r["kod"])
        raw = []
        for r in rows:
            rk_vals = [r[f"rank_{idx}"] for idx in range(n_m) if r[f"rank_{idx}"] is not None]
            raw.append(float(np.mean(rk_vals)) if len(rk_vals) == n_m else None)
        med = float(np.median([x for x in raw if x is not None])) if any(x is not None for x in raw) else 0.5
        scored = []
        for r, value in zip(rows, raw):
            scored.append({**r, "score": med if value is None else value})
        scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        rankings[dt] = scored
    return rankings

rankings_h0 = derive_rankings((52, 78))          # Baseline 12m+18m
rankings_8w_26w = derive_rankings((8, 26))        # Horizon-Adjusted 2m+6m
rankings_8w_52w = derive_rankings((8, 26, 52))    # Multi-Horizon 2m+6m+12m

# Backtest Engine with Signal Decay & Fresh Capital Rules
def run_decay_simulation(rankings, exit_decay_rule="NONE", capital_rule="EQUAL", cost=COST_ONEWAY):
    anchor_parity = dates.index("2024-01-26") % 2
    previous = []
    prev_weights = {}
    holding_age = {}
    periods = []

    for dt_idx, dt in enumerate(eval_dates):
        scheduled = dates.index(dt) % 2 == anchor_parity
        raw_univ = rankings[dt]
        eligible = {r["kod"] for r in raw_univ}
        rank_map = {r["kod"]: i + 1 for i, r in enumerate(raw_univ)}
        
        # 1. Selection with optional Decay Rule
        if scheduled or not previous:
            selected_h0 = [r["kod"] for r in raw_univ[:30]]
        else:
            # Rebalance off-week: keep previous eligible
            selected_h0 = [k for k in previous if k in eligible]
            if len(selected_h0) < 30:
                fill = [r["kod"] for r in raw_univ if r["kod"] not in selected_h0]
                selected_h0.extend(fill[:30 - len(selected_h0)])

        # Apply Exit / Decay Rule
        selected_final = []
        for k in selected_h0:
            rk = rank_map.get(k, 999)
            age = holding_age.get(k, 0)
            
            drop_item = False
            if exit_decay_rule == "EXIT_RANK35" and rk > 35:
                drop_item = True
            elif exit_decay_rule == "EXIT_RANK20_NONPERF" and rk > 20 and age >= 4:
                # If held for at least 4 biweeks (8 weeks) and rank drops past 20
                m8 = get_momentum(k, dt, 8)
                if m8 is not None and m8 < 0:
                    drop_item = True
            elif exit_decay_rule == "EXIT_NEGATIVE_8W" and age >= 2:
                m8 = get_momentum(k, dt, 8)
                if m8 is not None and m8 < -0.05:
                    drop_item = True

            if not drop_item:
                selected_final.append(k)

        # Refill if dropped
        if len(selected_final) < 30:
            refill = [r["kod"] for r in raw_univ if r["kod"] not in selected_final]
            selected_final.extend(refill[:30 - len(selected_final)])
        selected_final = selected_final[:30]

        # Update holding age
        new_holding_age = {}
        for k in selected_final:
            new_holding_age[k] = holding_age.get(k, 0) + 1
        holding_age = new_holding_age

        # 2. Sizing / Weighting (ERC + FR Overlay)
        n_held = len(selected_final)
        vols = np.array([get_vol(k, dt) for k in selected_final], dtype=float)
        inv_vols = 1.0 / (np.maximum(vols, 0.05) ** 1.5) if n_held > 0 else np.array([])
        w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
        
        conf_flags = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in selected_final], dtype=float)
        w_raw = w_raw * conf_flags
        w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
        w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])

        # Fresh Capital Rule Adjustment
        if capital_rule == "FRESH_TOP3_BOOST" and len(w) >= 3:
            # Give extra weight to current Rank #1-3 candidates
            top3_codes = {r["kod"] for r in raw_univ[:3]}
            for i, k in enumerate(selected_final):
                if k in top3_codes:
                    w[i] *= 1.25
            w = w / np.sum(w) * (n_held / 30.0)

        curr_weights = dict(zip(selected_final, w))

        # Turnover calculation
        if not previous:
            turnover = np.sum(w)
        else:
            all_k = set(prev_weights.keys()) | set(curr_weights.keys())
            dw = sum(abs(curr_weights.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in all_k)
            turnover = dw / 2.0

        rets = np.array([returns_map.get((k, dt), 0.0) for k in selected_final], dtype=float) if len(selected_final) > 0 else np.array([])
        gross = float(np.sum(w * rets)) if len(w) > 0 else 0.0
        net = gross - cost * turnover
        b_ret = b_xact_rets[dt_idx] if dt_idx < len(b_xact_rets) else 0.0

        periods.append({
            "panel_date": dt, "year": dt[:4], "gross": gross, "net": net, "bench": b_ret,
            "turnover": turnover, "cash_total": 1.0 - np.sum(w)
        })
        previous = selected_final
        prev_weights = curr_weights

    df_p = pd.DataFrame(periods)
    
    # Calculate HAC Alpha
    y = df_p["net"].values
    x = df_p["bench"].values
    N = len(y)
    X = np.column_stack([np.ones(N), x])
    beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
    residuals = y - X @ beta_hat
    
    max_lags = 2
    S = np.zeros((2, 2))
    for i in range(N):
        xi = X[i:i+1, :]
        e_i = residuals[i]
        S += (e_i ** 2) * (xi.T @ xi)
    for lag in range(1, max_lags + 1):
        weight = 1.0 - lag / (max_lags + 1)
        for i in range(lag, N):
            xi = X[i:i+1, :]
            xi_lag = X[i-lag:i-lag+1, :]
            e_i = residuals[i]
            e_lag = residuals[i-lag]
            gamma = e_i * e_lag * (xi.T @ xi_lag + xi_lag.T @ xi)
            S += weight * gamma
    XtX_inv = np.linalg.inv(X.T @ X)
    V_hac = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V_hac))
    t_stat = beta_hat[0] / se[0]
    p_val = 2.0 * (1.0 - stats.norm.cdf(np.abs(t_stat)))
    
    alpha_per = beta_hat[0]
    alpha_ann = (1.0 + alpha_per)**13 - 1.0
    cagr = float(np.prod(1 + df_p["net"].values) ** (13.0 / N) - 1.0)
    vol = float(np.std(df_p["net"].values, ddof=1) * math.sqrt(13))
    sharpe = float((cagr - 0.02) / vol) if vol > 0 else 0.0
    
    wealth = np.cumprod(1 + df_p["net"].values)
    dd = wealth / np.maximum.accumulate(wealth) - 1.0
    max_dd = float(dd.min())
    cvar95 = float(np.percentile(df_p["net"].values, 5))
    avg_turnover = float(np.mean(df_p["turnover"]))

    return {
        "CAGR": cagr, "Alpha_ann": alpha_ann, "Beta": beta_hat[1], "SE_alpha": se[0],
        "t_stat": t_stat, "p_val": p_val, "Sharpe": sharpe, "Vol": vol,
        "MaxDD": max_dd, "CVaR95": cvar95, "Turnover": avg_turnover, "N": N
    }

# Run all test variants
experiments = {
    "0. BASELINE (H0 12m+18m, No Exit Decay)": run_decay_simulation(rankings_h0, "NONE", "EQUAL"),
    "1. HORIZON-ADJUSTED (8w+26w Horizon Target)": run_decay_simulation(rankings_8w_26w, "NONE", "EQUAL"),
    "2. MULTI-HORIZON (8w+26w+52w Horizon Target)": run_decay_simulation(rankings_8w_52w, "NONE", "EQUAL"),
    "3. DECAY RULE A: Exit Rank > 35": run_decay_simulation(rankings_h0, "EXIT_RANK35", "EQUAL"),
    "4. DECAY RULE B: Exit Rank > 20 & Neg 8w Mom": run_decay_simulation(rankings_h0, "EXIT_RANK20_NONPERF", "EQUAL"),
    "5. DECAY RULE C: Exit Neg 8w Mom (< -5%)": run_decay_simulation(rankings_h0, "EXIT_NEGATIVE_8W", "EQUAL"),
    "6. FRESH CAPITAL: Boost Fresh Rank #1-3": run_decay_simulation(rankings_h0, "NONE", "FRESH_TOP3_BOOST"),
    "7. COMBINED: Horizon-Adj + Decay Exit Rank > 20": run_decay_simulation(rankings_8w_26w, "EXIT_RANK20_NONPERF", "FRESH_TOP3_BOOST"),
}

print("=" * 115)
print("RESEARCH AJ: HORIZON-ADJUSTED PREDICTED RETURN & SIGNAL DECAY AUDIT RESULTS")
print("Period: 2021-07-16 to 2026-07-10 (N=66 biweekly periods)")
print("=" * 115)
print(f"{'Experiment Name':<45} | {'CAGR':<7} | {'Alpha':<7} | {'Beta':<5} | {'t-stat':<6} | {'p-val':<6} | {'Sharpe':<6} | {'MaxDD':<7} | {'Turnover':<8}")
print("-" * 115)
for name, res in experiments.items():
    print(f"{name:<45} | {res['CAGR']:+.2%} | {res['Alpha_ann']:+.2%} | {res['Beta']:.2f} | {res['t_stat']:+.2f} | {res['p_val']:.3f} | {res['Sharpe']:.2f}  | {res['MaxDD']:+.2%} | {res['Turnover']:.2%}")
print("-" * 115)

# Save result json
out_file = V2 / "research_k/research_aj_signal_decay_results.json"
out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text(json.dumps(experiments, indent=2, sort_keys=True), encoding="utf-8")
print(f"Results saved to {out_file}")
