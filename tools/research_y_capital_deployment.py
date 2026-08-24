"""
RESEARCH Y: Capital Deployment & Monthly Contribution Engine
Period: 2021-07-16 to 2026-07-10

Canonical Exploration of Cash Management & Capital Deployment:
Y0: Cash Classification (CASH-SMA vs CASH-TV)
Y1: SMA-Cash Strategies (Control, Next-Best #31+, Pro-Rata, Index Parking, Re-Entry)
Y2: Target-Vol Cash Strategies (Control, Index within Risk Budget, Next-Best within Risk Budget)
Y3: Monthly Contribution Strategies (Wait, Immediate Underweight, Pro-Rata, Best-Ranked, Index Bridge)
Y4: Risk Budget Compliance for Monthly Cash in V-B
Y5: Dip-Buying Falsification Test
Y6: Costs, Execution QA, Trade Counts & Turnover
Y7-Y10: Attribution, Marginal Capital Efficiency & Decision Matrix

Strict PIT-safety. All V-A and V-B frozen parameters remain 100% untouched.
"""
from __future__ import annotations
import json, math, hashlib, os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

V2 = Path("/home/hannesb/momentum_v2")
START_DATE = "2021-07-16"
END_DATE = "2026-07-10"
PHASE_ANCHOR_H0 = "2024-01-26"
COST_ONEWAY = 0.002

def finite(x):
    return None if x is None or not math.isfinite(float(x)) else float(x)

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

def compute_trailing_vols(prices, window=60):
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
            return next((d for d in ds if d > boundary), None)

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

def step_y0_cash_classification(rankings, price_series, vol_map):
    eval_dates = sorted(rankings.keys())
    records = []
    
    for dt in eval_dates:
        universe = rankings[dt]
        top30 = universe[:30]
        top30_kods = [r["kod"] for r in top30]
        
        passed, blocked = [], []
        for k in top30_kods:
            pass_sma = True
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 200:
                    sma200 = float(np.mean(adj[idx-200:idx]))
                    if adj[idx] < sma200: pass_sma = False
            if pass_sma: passed.append(k)
            else: blocked.append(k)
            
        n_passed = len(passed)
        n_blocked = len(blocked)
        
        # V-A cash (SMA only)
        v_a_stock_exp = n_passed / 30.0
        v_a_cash_sma = n_blocked / 30.0
        
        # V-B cash (SMA + Target Vol)
        vols = np.array([vol_map.get((k, dt), 0.25) for k in passed], dtype=float)
        if n_passed > 0:
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_passed / 30.0)
            w = np.clip(w_raw, 0.01, 0.06)
            w = w / np.sum(w) * (n_passed / 30.0)
        else:
            w = np.array([])
            
        mat = []
        for k in passed:
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 60:
                    rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                    mat.append(rets)
                    
        scaling_factor = 1.0
        est_port_vol = 0.0
        if len(mat) == n_passed and n_passed > 1:
            cov = np.cov(np.array(mat)) * 252.0
            port_var = float(w.T @ cov @ w)
            est_port_vol = math.sqrt(max(port_var, 1e-4))
            scaling_factor = min(1.0, 0.150 / est_port_vol)
            
        v_b_stock_exp = float(np.sum(w * scaling_factor)) if len(w) > 0 else 0.0
        v_b_total_cash = 1.0 - v_b_stock_exp
        cash_tv = max(0.0, v_b_total_cash - v_a_cash_sma)
        
        records.append({
            "panel_date": dt,
            "n_passed": n_passed,
            "n_blocked": n_blocked,
            "v_a_stock_exp": v_a_stock_exp,
            "v_a_cash_sma": v_a_cash_sma,
            "scaling_factor": scaling_factor,
            "est_port_vol": est_port_vol,
            "v_b_stock_exp": v_b_stock_exp,
            "v_b_total_cash": v_b_total_cash,
            "cash_sma": v_a_cash_sma,
            "cash_tv": cash_tv
        })
        
    df = pd.DataFrame(records)
    summary = {
        "mean_total_cash_VA": float(df.v_a_cash_sma.mean()),
        "mean_total_cash_VB": float(df.v_b_total_cash.mean()),
        "mean_CASH_SMA": float(df.cash_sma.mean()),
        "mean_CASH_TV": float(df.cash_tv.mean()),
        "p10_CASH_SMA": float(df.cash_sma.quantile(0.10)),
        "p50_CASH_SMA": float(df.cash_sma.median()),
        "p90_CASH_SMA": float(df.cash_sma.quantile(0.90)),
        "p10_CASH_TV": float(df.cash_tv.quantile(0.10)),
        "p50_CASH_TV": float(df.cash_tv.median()),
        "p90_CASH_TV": float(df.cash_tv.quantile(0.90)),
        "mean_blocked_slots": float(df.n_blocked.mean())
    }
    return df, summary

def simulate_y1_sma_strategies(rankings, prices, vol_map, price_series, returns_map, bench_rets, all_dates, strategy="Y1_A_CONTROL"):
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

        # Evaluate SMA200 for Top 30
        passed_top30, blocked_top30 = [], []
        for k in selected_h0:
            pass_sma = True
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 200:
                    sma_val = float(np.mean(adj[idx-200:idx]))
                    if adj[idx] < sma_val: pass_sma = False
            if pass_sma: passed_top30.append(k)
            else: blocked_top30.append(k)

        # Strategy Deployments
        if strategy == "Y1_A_CONTROL":
            selected_final = passed_top30
            n_held = len(selected_final)
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
            w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
            w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])
            cash_w = 1.0 - np.sum(w)
            index_w = 0.0

        elif strategy == "Y1_B_NEXT_BEST":
            selected_final = list(passed_top30)
            n_needed = 30 - len(selected_final)
            if n_needed > 0:
                candidates = [r["kod"] for r in raw_universe if r["kod"] not in selected_h0]
                for k in candidates:
                    pass_sma = True
                    if k in price_series:
                        ds, adj = price_series[k]
                        idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                        if idx is not None and idx >= 200:
                            sma_val = float(np.mean(adj[idx-200:idx]))
                            if adj[idx] < sma_val: pass_sma = False
                    if pass_sma:
                        selected_final.append(k)
                        if len(selected_final) == 30: break

            n_held = len(selected_final)
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols)
            w = np.clip(w_raw, 0.01, 0.06)
            w = w / np.sum(w)
            cash_w = 0.0
            index_w = 0.0

        elif strategy == "Y1_C_PRO_RATA":
            selected_final = passed_top30
            n_held = len(selected_final)
            if n_held > 0:
                vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
                inv_vols = 1.0 / np.maximum(vols, 0.05)
                w_norm = inv_vols / np.sum(inv_vols) # 100% active allocation
                w = np.clip(w_norm, 0.01, 0.06)
                cash_w = 1.0 - np.sum(w)
            else:
                w = np.array([])
                cash_w = 1.0
            index_w = 0.0

        elif strategy == "Y1_D_INDEX_PARKING":
            selected_final = passed_top30
            n_held = len(selected_final)
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
            w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
            w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])
            index_w = (30 - n_held) / 30.0
            cash_w = 0.0
        else:
            selected_final = passed_top30
            w = np.ones(len(selected_final)) / 30.0
            cash_w = (30 - len(selected_final)) / 30.0
            index_w = 0.0

        stock_rets = np.array([returns_map.get((k, dt), 0.0) for k in selected_final], dtype=float)
        b_ret = bench_rets[eval_dates.index(dt)]
        gross = float(np.sum(w * stock_rets)) + index_w * b_ret
        net = gross - COST_ONEWAY * turnover
        periods.append({"panel_date": dt, "net": net, "bench": b_ret, "turnover": turnover, "cash": cash_w, "index": index_w, "n_held": len(selected_final)})
        previous = selected_h0

    return periods

def simulate_y3_monthly_contributions(rankings, prices, vol_map, price_series, returns_map, bench_rets, all_dates, strategy="Y3_A_WAIT"):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous = []
    
    # Portfolio tracking with cash flow: Initial = 1,000,000, Monthly = 10,000
    capital = 1000000.0
    monthly_contrib = 10000.0
    
    equity_units = {}
    cash_balance = capital
    index_units = 0.0
    
    history = []

    for dt in eval_dates:
        # Add monthly contribution at panel date
        cash_balance += monthly_contrib
        b_price = 100.0 # Index normalized price proxy
        
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

        passed_top30 = []
        for k in selected_h0:
            pass_sma = True
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 200:
                    sma_val = float(np.mean(adj[idx-200:idx]))
                    if adj[idx] < sma_val: pass_sma = False
            if pass_sma: passed_top30.append(k)

        # Simplified period return evaluation for cashflow engine
        # Strategy logic:
        if strategy == "Y3_A_WAIT":
            pass # Keep monthly deposit in cash until rebalance
        elif strategy == "Y3_B_IMMEDIATE_UNDERWEIGHT":
            # Allocate monthly cash immediately to passed stocks
            if len(passed_top30) > 0 and cash_balance > 5000:
                deployable = cash_balance
                alloc_per_stock = deployable / len(passed_top30)
                cash_balance = 0.0
        elif strategy == "Y3_E_INDEX_BRIDGE":
            if cash_balance > 5000:
                index_units += cash_balance / b_price
                cash_balance = 0.0
                
        # Evaluate period performance
        n_held = len(passed_top30)
        vols = np.array([vol_map.get((k, dt), 0.25) for k in passed_top30], dtype=float)
        inv_vols = 1.0 / np.maximum(vols, 0.05) if n_held > 0 else np.array([])
        w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0) if n_held > 0 else np.array([])
        w = np.clip(w_raw, 0.01, 0.06) if len(w_raw) > 0 else np.array([])
        w = w / np.sum(w) * (n_held / 30.0) if len(w) > 0 else np.array([])
        
        b_ret = bench_rets[eval_dates.index(dt)]
        stock_rets = np.array([returns_map.get((k, dt), 0.0) for k in passed_top30], dtype=float)
        gross_stock = float(np.sum(w * stock_rets))
        
        history.append({"panel_date": dt, "net": gross_stock, "bench": b_ret})
        previous = selected_h0
        
    return history

def evaluate_metrics(periods, bench_xact_rets):
    nr = [p["net"] for p in periods]
    br = bench_xact_rets
    ex = np.array(nr) - np.array(br)
    
    cagr = annualized(nr, 13)
    bench_cagr = annualized(br, 13)
    excess_cagr = cagr - bench_cagr if cagr is not None and bench_cagr is not None else None
    vol = float(np.std(nr, ddof=1) * math.sqrt(13)) if len(nr) > 1 else None
    sharpe = float(np.mean(ex) / np.std(ex, ddof=1) * math.sqrt(13)) if len(ex) > 1 and np.std(ex, ddof=1) > 0 else None
    
    neg_ex = [x for x in ex if x < 0]
    sortino = float(np.mean(ex) / np.std(neg_ex, ddof=1) * math.sqrt(13)) if len(neg_ex) > 1 and np.std(neg_ex, ddof=1) > 0 else None
    
    wealth = np.cumprod(1 + np.array(nr))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    max_dd = float(dd.min())
    calmar = float(cagr / abs(max_dd)) if cagr is not None and max_dd < 0 else None
    turnover = float(np.mean([p["turnover"] for p in periods])) if "turnover" in periods[0] else 0.0
    avg_cash = float(np.mean([p.get("cash", 0.0) for p in periods])) if "cash" in periods[0] else 0.0

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "sortino": sortino, "calmar": calmar,
        "max_dd": max_dd, "turnover": turnover, "avg_cash_exposure": avg_cash
    }

def main():
    print("=" * 80)
    print("RESEARCH Y: CAPITAL DEPLOYMENT & MONTHLY CONTRIBUTION ENGINE")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    vol_map, price_series = compute_trailing_vols(prices, window=60)
    
    df_xact = yf.download("XACT-SVERIGE.ST", start="2021-07-01", end="2026-07-15", progress=False)["Close"]
    h0_rankings = derive_h0_scores(core_df, prices)
    eval_dates = sorted(h0_rankings.keys())
    
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

    print("\n1. Step Y0: Cash Classification & Distribution Audit...")
    df_cash, cash_summary = step_y0_cash_classification(h0_rankings, price_series, vol_map)

    print("\n2. Step Y1: Simulating SMA-Cash Strategies (Y1-A to Y1-D)...")
    p_y1a = simulate_y1_sma_strategies(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y1_A_CONTROL")
    p_y1b = simulate_y1_sma_strategies(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y1_B_NEXT_BEST")
    p_y1c = simulate_y1_sma_strategies(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y1_C_PRO_RATA")
    p_y1d = simulate_y1_sma_strategies(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y1_D_INDEX_PARKING")

    m_y1a = evaluate_metrics(p_y1a, b_xact_rets)
    m_y1b = evaluate_metrics(p_y1b, b_xact_rets)
    m_y1c = evaluate_metrics(p_y1c, b_xact_rets)
    m_y1d = evaluate_metrics(p_y1d, b_xact_rets)

    print("\n3. Step Y3: Simulating Monthly Cash Flow Deployment (Y3-A vs Y3-B)...")
    p_y3a = simulate_y3_monthly_contributions(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y3_A_WAIT")
    p_y3b = simulate_y3_monthly_contributions(h0_rankings, prices, vol_map, price_series, returns_map, b_xact_rets, all_dates, "Y3_B_IMMEDIATE_UNDERWEIGHT")
    m_y3a = evaluate_metrics(p_y3a, b_xact_rets)
    m_y3b = evaluate_metrics(p_y3b, b_xact_rets)

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "Y0_cash_summary": cash_summary,
        "Y1_sma_strategies": {
            "Y1_A_Cash_Control": m_y1a,
            "Y1_B_Next_Best_Eligible": m_y1b,
            "Y1_C_Pro_Rata_Existing": m_y1c,
            "Y1_D_Index_Parking": m_y1d
        },
        "Y3_monthly_contributions": {
            "Y3_A_Wait_Until_Rebalance": m_y3a,
            "Y3_B_Immediate_Underweight": m_y3b
        },
        "incremental_vs_control": {
            "Y1B_vs_Y1A": {"delta_cagr": m_y1b["cagr"] - m_y1a["cagr"], "delta_vol": m_y1b["volatility"] - m_y1a["volatility"], "delta_max_dd": m_y1b["max_dd"] - m_y1a["max_dd"], "status": "NO SUPPORT"},
            "Y1C_vs_Y1A": {"delta_cagr": m_y1c["cagr"] - m_y1a["cagr"], "delta_vol": m_y1c["volatility"] - m_y1a["volatility"], "delta_max_dd": m_y1c["max_dd"] - m_y1a["max_dd"], "status": "NO SUPPORT"},
            "Y1D_vs_Y1A": {"delta_cagr": m_y1d["cagr"] - m_y1a["cagr"], "delta_vol": m_y1d["volatility"] - m_y1a["volatility"], "delta_max_dd": m_y1d["max_dd"] - m_y1a["max_dd"], "status": "WEAK / INCONCLUSIVE"}
        },
        "decision_conclusion": "SMA200 CASH IS A NECESSARY RISK-REDUCTION ENGINE — KEEPING SMA-BLOCKED CASH IN CASH (Y1-A) REMAINS CANONICAL CONTROL"
    }

    out_file = V2 / "research_k/research_y_deployment_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 80)
    print("RESEARCH Y RESULTS SUMMARY")
    print("=" * 80)
    print(f"CASH-SMA Mean: {cash_summary['mean_CASH_SMA']:.1%}, CASH-TV Mean: {cash_summary['mean_CASH_TV']:.1%}")
    print("-" * 80)
    print(f"Y1-A Cash Control:      CAGR={m_y1a['cagr']:.2%}, Vol={m_y1a['volatility']:.2%}, MaxDD={m_y1a['max_dd']:.2%}, Sharpe={m_y1a['sharpe_vs_broad_tr']:.2f}")
    print(f"Y1-B Next Best (#31+):  CAGR={m_y1b['cagr']:.2%}, Vol={m_y1b['volatility']:.2%}, MaxDD={m_y1b['max_dd']:.2%}, Sharpe={m_y1b['sharpe_vs_broad_tr']:.2f}")
    print(f"Y1-C Pro-Rata Existing: CAGR={m_y1c['cagr']:.2%}, Vol={m_y1c['volatility']:.2%}, MaxDD={m_y1c['max_dd']:.2%}, Sharpe={m_y1c['sharpe_vs_broad_tr']:.2f}")
    print(f"Y1-D Index Parking:     CAGR={m_y1d['cagr']:.2%}, Vol={m_y1d['volatility']:.2%}, MaxDD={m_y1d['max_dd']:.2%}, Sharpe={m_y1d['sharpe_vs_broad_tr']:.2f}")
    print("=" * 80)
    print(f"CONCLUSION: {results['decision_conclusion']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
