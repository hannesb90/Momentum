"""
HEAD-TO-HEAD COMPARISON: ALL 6 FROZEN MODELS
Period: 2021-07-16 to 2026-07-10

Models Evaluated:
1. T0_A_CONTROL_H0 (Equal-Weight H0 Momentum)
2. CONTROL_C_SMA200 (Control C: H0 + SMA200 SKIP)
3. VA_RETURN_CHALLENGER (V-A: Return-Optimized Challenger)
4. VB_CAPITAL_PRESERVATION_CHALLENGER (V-B: Capital Preservation Challenger)
5. SHADOW_ERC_X2 (Shadow ERC: Equal Risk Contribution)
6. SHADOW_FUNDAMENTAL_RISK_OVERLAY (Shadow V-A-FR: 0.75x Unconfirmed Risk Overlay)

Strict PIT-safety. Returns & risk metrics calculated synchronously across all 66 panels.
"""
from __future__ import annotations
import json, math, os
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

V2 = Path("/home/hannesb/momentum_v2")
START_DATE = "2021-07-16"
END_DATE = "2026-07-10"
PHASE_ANCHOR_H0 = "2024-01-26"
COST_ONEWAY = 0.002

def annualized(values, periods_per_year=13):
    if values is None or len(values) == 0:
        return None
    wealth = float(np.prod(1 + np.asarray(values, dtype=float)))
    return -1.0 if wealth <= 0 else wealth ** (periods_per_year / len(values)) - 1

def load_data():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    target = json.loads((V2 / "panels/target_table.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y52": y52
        })
    df_core = pd.DataFrame(df_core)
    return df_core, prices, terminal

def compute_vols(prices, window=60):
    vol_map = {}
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }
    for kod, (ds, adj) in price_series.items():
        if len(adj) >= 2:
            rets = np.diff(adj) / adj[:-1]
            ds_rets = ds[1:]
            if len(rets) >= window:
                roll_std = pd.Series(rets).rolling(window).std().values * math.sqrt(252)
                for d, val in zip(ds_rets[window-1:], roll_std[window-1:]):
                    if math.isfinite(val) and val > 1e-4:
                        vol_map[(kod, d)] = float(val)
    return vol_map, price_series

def derive_h0_scores(core_df, prices):
    series = {
        k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    def momentum(k, dt, weeks):
        if k not in series: return None
        ds, values = series[k]
        now = np.datetime64(dt)
        target_dt = now - np.timedelta64(7 * weeks, "D")
        i = np.searchsorted(ds, now, side="right") - 1
        j = np.searchsorted(ds, target_dt, side="right") - 1
        if i < 0 or j < 0 or int((target_dt - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(values[i] / values[j] - 1)

    by_date = defaultdict(list)
    for _, r in core_df.iterrows():
        if r["panel_date"] < START_DATE or r["panel_date"] > END_DATE:
            continue
        m12 = momentum(r["kod"], r["panel_date"], 52)
        m18 = momentum(r["kod"], r["panel_date"], 78)
        by_date[r["panel_date"]].append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "mom_12m": m12, "mom_18m": m18, "y52": r["y52"]
        })

    rankings = {}
    for dt, rows in sorted(by_date.items()):
        for col in ("mom_12m", "mom_18m"):
            valid = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            grouped = defaultdict(list)
            for val, kod in valid: grouped[val].append(kod)
            ranks = {}
            pos = 1
            for val in sorted(grouped):
                ks = grouped[val]
                avg = (pos + pos + len(ks) - 1) / 2 / len(valid)
                for kod in ks: ranks[kod] = avg
                pos += len(ks)
            for r in rows: r[col + "_rank"] = ranks.get(r["kod"])
        raw = [0.5 * (r["mom_12m_rank"] + r["mom_18m_rank"]) if r["mom_12m_rank"] is not None and r["mom_18m_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raw if x is not None])) if any(x is not None for x in raw) else 0.5
        scored = []
        for r, value in zip(rows, raw):
            scored.append({**r, "score": med if value is None else value})
        scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        rankings[dt] = scored
    return rankings

def execution_engine(core_df, prices, terminal):
    dates = sorted(core_df.panel_date.unique())
    next_date = dict(zip(dates, dates[1:]))
    returns = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = {r["d"]: r["adj"] for r in rs}

        def first_after(boundary):
            return next((x for x in ds if x>boundary), None)

        for dt in dates:
            nd = next_date.get(dt)
            entry = first_after(dt)
            if not nd or not entry or entry > nd:
                returns[(kod, dt)] = 0.0
                continue
            exit_date = first_after(nd)
            event = terminal.get(kod)
            if exit_date:
                returns[(kod, dt)] = adj[exit_date] / adj[entry] - 1
            elif event and entry <= event["event_date"] <= nd:
                exit_date = ds[-1]
                returns[(kod, dt)] = adj[exit_date] / adj[entry] - 1
            else:
                returns[(kod, dt)] = 0.0
    return returns, dates

def fetch_fundamental_confirmations(rankings, prices):
    confirm_map = {}
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }
    for dt, rows in rankings.items():
        for r in rows:
            k = r["kod"]
            is_confirmed = False
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 120:
                    ma120 = float(np.mean(adj[idx-120:idx]))
                    rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                    vol60 = float(np.std(rets) * math.sqrt(252))
                    if adj[idx] >= ma120 and vol60 < 0.35:
                        is_confirmed = True
            confirm_map[(k, dt)] = is_confirmed
    return confirm_map

def run_simulation(model_key, rankings, prices, vol_map, price_series, returns_map, confirm_map, b_rets, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods = [], []

    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        raw_universe = rankings[dt]
        eligible_codes = {r["kod"] for r in raw_universe}
        
        if scheduled or not previous:
            selected_h0 = [r["kod"] for r in raw_universe[:30]]
        else:
            selected_h0 = [k for k in previous if k in eligible_codes]
            if len(selected_h0) < 30:
                fill = [r["kod"] for r in raw_universe if r["kod"] not in selected_h0]
                selected_h0.extend(fill[: 30 - len(selected_h0)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected_h0) & set(previous)) / len(selected_h0)

        # Apply SMA200 SKIP entry gate for all models except T0_A_CONTROL_H0
        selected_final = []
        for k in selected_h0:
            pass_sma = True
            if model_key != "T0_A_CONTROL_H0":
                if k in price_series:
                    ds, adj = price_series[k]
                    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                    if idx is not None and idx >= 200:
                        sma_val = float(np.mean(adj[idx-200:idx]))
                        if adj[idx] < sma_val: pass_sma = False
            if pass_sma: selected_final.append(k)

        n_held = len(selected_final)
        
        # Calculate Weights
        if model_key in ("T0_A_CONTROL_H0", "CONTROL_C_SMA200"):
            w = np.full(n_held, 1.0 / 30.0) if n_held > 0 else np.array([])
        elif model_key in ("VA_RETURN_CHALLENGER", "VB_CAPITAL_PRESERVATION_CHALLENGER"):
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05) if n_held > 0 else np.array([])
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
            w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
            w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])
        elif model_key == "SHADOW_ERC_X2":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / (np.maximum(vols, 0.05) ** 1.5) if n_held > 0 else np.array([])
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
            w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
            w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])
        elif model_key == "SHADOW_FUNDAMENTAL_RISK_OVERLAY":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05) if n_held > 0 else np.array([])
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
            w_base = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
            w_base = w_base / np.sum(w_base) * (n_held / 30.0) if len(w_base) > 0 else np.array([])
            
            conf_flags = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in selected_final], dtype=float)
            w_fr_raw = w_base * conf_flags
            w = np.clip(w_fr_raw, 0.01, 0.06) if len(w_fr_raw) > 0 else np.array([])
            w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])

        # Target Vol 15% Scaling for V-B
        if model_key == "VB_CAPITAL_PRESERVATION_CHALLENGER" and len(w) > 0:
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            p_vol = float(np.sqrt(np.sum((w * vols)**2))) if len(w) > 0 else 0.15
            scale = min(1.0, 0.15 / max(p_vol, 0.05))
            w = w * scale

        rets = np.array([returns_map.get((k, dt), 0.0) for k in selected_final], dtype=float) if len(selected_final) > 0 else np.array([])
        gross = float(np.sum(w * rets)) if len(w) > 0 else 0.0
        net = gross - COST_ONEWAY * turnover
        b_ret = b_rets[eval_dates.index(dt)]
        periods.append({"panel_date": dt, "net": net, "bench": b_ret, "turnover": turnover, "cash": 1.0 - np.sum(w) if len(w) > 0 else 1.0})
        previous = selected_h0

    # Calculate Metrics
    nr = [p["net"] for p in periods]
    br = b_rets
    ex = np.array(nr) - np.array(br)
    
    cagr = annualized(nr, 13)
    bench_cagr = annualized(br, 13)
    excess_cagr = cagr - bench_cagr if cagr is not None and bench_cagr is not None else None
    vol = float(np.std(nr, ddof=1) * math.sqrt(13)) if len(nr) > 1 else None
    sharpe = float(np.mean(ex) / np.std(ex, ddof=1) * math.sqrt(13)) if len(ex) > 1 and np.std(ex, ddof=1) > 0 else None
    
    wealth = np.cumprod(1 + np.array(nr))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    max_dd = float(dd.min())
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    cvar95 = float(np.percentile(nr, 5))
    mean_turnover = float(np.mean([p["turnover"] for p in periods]))

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr": excess_cagr,
        "volatility": vol, "sharpe": sharpe, "max_dd": max_dd, "ulcer_index": ulcer,
        "cvar95": cvar95, "mean_turnover": mean_turnover
    }

def main():
    print("=" * 80)
    print("HEAD-TO-HEAD COMPARISON: ALL 6 FROZEN MODELS")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    vol_map, price_series = compute_vols(prices, window=60)
    h0_rankings = derive_h0_scores(core_df, prices)
    confirm_map = fetch_fundamental_confirmations(h0_rankings, prices)
    eval_dates = sorted(h0_rankings.keys())

    df_xact = yf.download("XACT-SVERIGE.ST", start="2021-07-01", end="2026-07-15", progress=False)["Close"]
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

    model_keys = [
        "T0_A_CONTROL_H0",
        "CONTROL_C_SMA200",
        "VA_RETURN_CHALLENGER",
        "VB_CAPITAL_PRESERVATION_CHALLENGER",
        "SHADOW_ERC_X2",
        "SHADOW_FUNDAMENTAL_RISK_OVERLAY"
    ]

    results = {}
    for mk in model_keys:
        res = run_simulation(mk, h0_rankings, prices, vol_map, price_series, returns_map, confirm_map, b_xact_rets, all_dates)
        results[mk] = res

    out_file = V2 / "research_k/head_to_head_6_models_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 105)
    print(f"{'Modell Key':<35} | {'CAGR':<8} | {'Vol':<8} | {'MaxDD':<9} | {'Sharpe':<7} | {'Ulcer':<7} | {'CVaR95':<8}")
    print("=" * 105)
    for mk, r in results.items():
        print(f"{mk:<35} | {r['cagr']:.2%}  | {r['volatility']:.2%}  | {r['max_dd']:.2%}  | {r['sharpe']:+.2f}   | {r['ulcer_index']:.3f}   | {r['cvar95']:.2%}")
    print("=" * 105)

if __name__ == "__main__":
    main()
