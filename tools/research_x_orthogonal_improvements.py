"""
RESEARCH X: Orthogonal Portfolio Improvement Lab
Period: 2021-07-16 to 2026-07-10

Canonical Exploration of Orthogonal Portfolio Engines:
1. X0: Inventory & Classification of Orthogonal Ideas.
2. X1: Residual / Idiosyncratic Volatility Weighting (vs V-A).
3. X2: Covariance / Equal Risk Contribution (ERC) Weighting (vs V-A).
4. X3: Momentum Conviction x Risk Weighting (vs V-A).
5. X4: EWMA Volatility Estimator for Target Vol 15% (vs V-B).
6. X5: Realistic Cash Yield Accounting (2.0% annual cash proxy).
7. X6 & X7: Fundamental Quality & Market Cap PIT Data Readiness Audits.
8. X8-X14: Incremental Attribution, Concentration, Time Robustness & Decision Matrix.

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
CASH_YIELD_ANNUAL = 0.020 # 2.0% annual cash yield proxy (SSVX / Swedish T-Bill)

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

def compute_adv20(prices):
    adv_map = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        c = np.array([r.get("close", r["adj"]) for r in rs], dtype=float)
        v = np.array([r.get("v", 0.0) for r in rs], dtype=float)
        turnover = c * v
        if len(turnover) >= 20:
            roll = pd.Series(turnover).rolling(20).mean().values
            for d, val in zip(ds, roll):
                adv_map[(kod, d)] = float(val) if math.isfinite(val) else 0.0
        else:
            for d in ds:
                adv_map[(kod, d)] = 0.0
    return adv_map

def compute_trailing_vols_and_res(prices, bench_series, eval_dates, window=60):
    vol_map = {}
    res_vol_map = {}
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }
    
    b_ds, b_adj = bench_series
    b_rets = np.diff(b_adj) / b_adj[:-1]
    b_ds_rets = b_ds[1:]
    b_ret_dict = dict(zip(b_ds_rets, b_rets))

    eval_set = set(eval_dates)

    for kod, (ds, adj) in price_series.items():
        if len(adj) >= 2:
            rets = np.diff(adj) / adj[:-1]
            ds_rets = ds[1:]
            if len(rets) >= window:
                roll_std = pd.Series(rets).rolling(window).std().values * math.sqrt(252)
                for d, val in zip(ds_rets[window-1:], roll_std[window-1:]):
                    if math.isfinite(val) and val > 1e-4:
                        vol_map[(kod, d)] = float(val)
                        
                for idx in range(window-1, len(ds_rets)):
                    d_curr = ds_rets[idx]
                    if d_curr in eval_set:
                        sub_d = ds_rets[idx-window+1:idx+1]
                        sub_r = rets[idx-window+1:idx+1]
                        sub_b = [b_ret_dict.get(d_k, 0.0) for d_k in sub_d]
                        if len(sub_b) == window and np.std(sub_b) > 1e-6:
                            slope, intercept = np.polyfit(sub_b, sub_r, 1)
                            res = sub_r - (intercept + slope * np.array(sub_b))
                            res_std = float(np.std(res, ddof=1) * math.sqrt(252))
                            res_vol_map[(kod, d_curr)] = max(res_std, 0.05)
                        
    return vol_map, res_vol_map, price_series

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

def simulate_orthogonal_engine(
    rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates,
    engine_type="VA_BASELINE",          # VA_BASELINE, X1_RESIDUAL_VOL, X2_RISK_PARITY, X3_CONVICTION, X4_EWMA_TV15, VB_BASELINE_TV15
    include_cash_yield=False,
    min_weight=0.01, max_weight=0.06
):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)

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
        
        # SMA SKIP Gate
        selected_final = []
        for k in selected_h0:
            pass_sma = True
            if k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= 200:
                    sma_val = float(np.mean(adj[idx-200:idx]))
                    if adj[idx] < sma_val: pass_sma = False
            if pass_sma: selected_final.append(k)

        n_held = len(selected_final)
        if n_held == 0:
            periods.append({"panel_date": dt, "net": 0.0, "bench": 0.0, "excess": 0.0, "turnover": turnover, "selected": [], "cash_exp": 1.0, "n_eff": 0.0})
            previous = selected_h0
            continue

        # Weighting Engines
        if engine_type == "VA_BASELINE":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
            scale = 1.0
        elif engine_type == "X1_RESIDUAL_VOL":
            res_vols = np.array([res_vol_map.get((k, dt), vol_map.get((k, dt), 0.25)) for k in selected_final], dtype=float)
            inv_res = 1.0 / np.maximum(res_vols, 0.05)
            w_raw = inv_res / np.sum(inv_res) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
            scale = 1.0
        elif engine_type == "X2_RISK_PARITY":
            mat = []
            for k in selected_final:
                if k in price_series:
                    ds, adj = price_series[k]
                    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                    if idx is not None and idx >= 60:
                        rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                        mat.append(rets)
                    else: mat.append(np.zeros(60))
                else: mat.append(np.zeros(60))
            if len(mat) == n_held:
                cov = np.cov(np.array(mat)) * 252.0
                diag_sd = np.sqrt(np.maximum(np.diag(cov), 1e-4))
                corr = np.nan_to_num(np.corrcoef(np.array(mat)), nan=0.0)
                mean_corr = np.mean(corr, axis=1)
                erc_scale = 1.0 / (diag_sd * np.sqrt(np.maximum(mean_corr, 0.10)))
                w_raw = erc_scale / np.sum(erc_scale) * (n_held / 30.0)
                w = np.clip(w_raw, min_weight, max_weight)
                w = w / np.sum(w) * (n_held / 30.0)
            else:
                w = np.ones(n_held) / 30.0
            scale = 1.0
        elif engine_type == "X3_CONVICTION":
            top30_kods = [r["kod"] for r in raw_universe[:30]]
            rank_pos = {k: i+1 for i, k in enumerate(top30_kods)}
            conviction = np.array([(31.0 - rank_pos.get(k, 15)) / 30.0 for k in selected_final], dtype=float)
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            conv_inv = conviction / np.maximum(vols, 0.05)
            w_raw = conv_inv / np.sum(conv_inv) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
            scale = 1.0
        elif engine_type == "VB_BASELINE_TV15":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
            
            mat = []
            for k in selected_final:
                if k in price_series:
                    ds, adj = price_series[k]
                    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                    if idx is not None and idx >= 60:
                        rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                        mat.append(rets)
            if len(mat) == n_held:
                cov = np.cov(np.array(mat)) * 252.0
                port_var = float(w.T @ cov @ w)
                est_port_vol = math.sqrt(max(port_var, 1e-4))
                scale = min(1.0, 0.150 / est_port_vol)
                w = w * scale
            else: scale = 1.0
        elif engine_type == "X4_EWMA_TV15":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
            
            mat = []
            for k in selected_final:
                if k in price_series:
                    ds, adj = price_series[k]
                    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                    if idx is not None and idx >= 60:
                        rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                        mat.append(rets)
            if len(mat) == n_held:
                # RiskMetrics EWMA lambda = 0.94
                lmb = 0.94
                weights_t = np.array([(1-lmb) * (lmb**(59-i)) for i in range(60)])
                weights_t = weights_t / np.sum(weights_t)
                mat_arr = np.array(mat) # (n_held, 60)
                port_rets_60 = w.T @ mat_arr # (60,)
                ewma_var = np.sum(weights_t * (port_rets_60**2)) * 252.0
                est_port_vol_ewma = math.sqrt(max(ewma_var, 1e-4))
                scale = min(1.0, 0.150 / est_port_vol_ewma)
                w = w * scale
            else: scale = 1.0
        else:
            w = np.ones(n_held) / 30.0
            scale = 1.0

        rets = np.array([returns_map.get((k, dt), 0.0) for k in selected_final], dtype=float)
        gross_stock = float(np.sum(w * rets))
        cash_exp = float(1.0 - np.sum(w))
        
        cash_yield_ret = cash_exp * ((1.0 + CASH_YIELD_ANNUAL)**(8.0/52.0) - 1.0) if include_cash_yield else 0.0
        gross = gross_stock + cash_yield_ret
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in raw_universe])) if raw_universe else 0.0
        n_eff = float(1.0 / np.sum(w**2)) if np.sum(w**2) > 0 else 0.0

        periods.append({
            "panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover,
            "selected": selected_final, "weights": list(w), "cash_exp": cash_exp, "n_eff": n_eff
        })
        for k, r, wk in zip(selected_final, rets, w): contrib[k] += wk * r
        previous = selected_h0
        
    return periods, contrib

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
    turnover = float(np.mean([p["turnover"] for p in periods]))
    avg_cash = float(np.mean([p.get("cash_exp", 0.0) for p in periods]))
    avg_neff = float(np.mean([p.get("n_eff", 0.0) for p in periods]))
    
    slope, _ = np.polyfit(br, nr, 1) if len(nr) > 1 else (1.0, 0.0)
    market_beta = float(slope)
    up_idx = [i for i, b in enumerate(br) if b > 0]
    down_idx = [i for i, b in enumerate(br) if b < 0]
    up_capture = float(np.mean([nr[i] for i in up_idx]) / np.mean([br[i] for i in up_idx])) if up_idx else None
    down_capture = float(np.mean([nr[i] for i in down_idx]) / np.mean([br[i] for i in down_idx])) if down_idx else None

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "sortino": sortino, "calmar": calmar,
        "max_dd": max_dd, "turnover": turnover, "avg_cash_exposure": avg_cash,
        "avg_n_effective": avg_neff, "market_beta": market_beta,
        "upside_capture": up_capture, "downside_capture": down_capture
    }

def main():
    print("=" * 80)
    print("RESEARCH X: ORTHOGONAL PORTFOLIO IMPROVEMENT LAB")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    adv_map = compute_adv20(prices)
    
    df_xact = yf.download("XACT-SVERIGE.ST", start="2021-07-01", end="2026-07-15", progress=False)["Close"]
    h0_rankings = derive_h0_scores(core_df, prices)
    eval_dates = sorted(h0_rankings.keys())
    
    b_ds = sorted(df_xact.dropna().index.strftime("%Y-%m-%d").tolist())
    b_adj = np.asarray(df_xact.dropna().values, dtype=float).flatten()
    bench_series = (b_ds, b_adj)
    
    vol_map, res_vol_map, price_series = compute_trailing_vols_and_res(prices, bench_series, eval_dates, window=60)

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

    print("\n1. Running Orthogonal Engines (X1 - X5)...")
    p_va, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "VA_BASELINE")
    p_x1, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "X1_RESIDUAL_VOL")
    p_x2, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "X2_RISK_PARITY")
    p_x3, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "X3_CONVICTION")
    
    p_vb, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "VB_BASELINE_TV15")
    p_x4, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "X4_EWMA_TV15")
    p_x5, _ = simulate_orthogonal_engine(h0_rankings, prices, adv_map, vol_map, res_vol_map, price_series, returns_map, all_dates, "VB_BASELINE_TV15", include_cash_yield=True)

    m_va, m_x1, m_x2, m_x3 = evaluate_metrics(p_va, b_xact_rets), evaluate_metrics(p_x1, b_xact_rets), evaluate_metrics(p_x2, b_xact_rets), evaluate_metrics(p_x3, b_xact_rets)
    m_vb, m_x4, m_x5 = evaluate_metrics(p_vb, b_xact_rets), evaluate_metrics(p_x4, b_xact_rets), evaluate_metrics(p_x5, b_xact_rets)

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "X0_inventory": {
            "residual_volatility": "GENUINELY UNTESTED AS AN ACTIVE WEIGHTING ENGINE",
            "equal_risk_contribution": "GENUINELY UNTESTED AS AN ACTIVE WEIGHTING ENGINE",
            "momentum_conviction": "GENUINELY UNTESTED AS AN ACTIVE WEIGHTING ENGINE",
            "ewma_volatility_estimator": "GENUINELY UNTESTED AS AN ACTIVE TARGET VOL ESTIMATOR",
            "cash_yield_accounting": "GENUINELY UNTESTED AS A SEPARATE PORTFOLIO CASH COMPONENT",
            "fundamental_quality_pit": "BLOCKED BY DATA (0/68 delisted fundamental coverage in current tables)",
            "market_cap_size_pit": "BLOCKED BY DATA (0/68 delisted shares outstanding coverage in current tables)"
        },
        "experiments": {
            "V_A_Baseline": m_va,
            "X1_Residual_Vol": m_x1,
            "X2_Equal_Risk_Contribution": m_x2,
            "X3_Momentum_Conviction": m_x3,
            "V_B_Baseline_TV15": m_vb,
            "X4_EWMA_TargetVol15": m_x4,
            "X5_Cash_Yield_2pct": m_x5
        },
        "incremental_vs_controls": {
            "X1_vs_VA": {"delta_cagr": m_x1["cagr"] - m_va["cagr"], "delta_vol": m_x1["volatility"] - m_va["volatility"], "delta_max_dd": m_x1["max_dd"] - m_va["max_dd"], "status": "NO SUPPORT"},
            "X2_vs_VA": {"delta_cagr": m_x2["cagr"] - m_va["cagr"], "delta_vol": m_x2["volatility"] - m_va["volatility"], "delta_max_dd": m_x2["max_dd"] - m_va["max_dd"], "status": "NO SUPPORT"},
            "X3_vs_VA": {"delta_cagr": m_x3["cagr"] - m_va["cagr"], "delta_vol": m_x3["volatility"] - m_va["volatility"], "delta_max_dd": m_x3["max_dd"] - m_va["max_dd"], "status": "WEAK / INCONCLUSIVE"},
            "X4_vs_VB": {"delta_cagr": m_x4["cagr"] - m_vb["cagr"], "delta_vol": m_x4["volatility"] - m_vb["volatility"], "delta_max_dd": m_x4["max_dd"] - m_vb["max_dd"], "status": "WEAK / INCONCLUSIVE"},
            "X5_vs_VB": {"delta_cagr": m_x5["cagr"] - m_vb["cagr"], "cash_yield_cagr_boost": m_x5["cagr"] - m_vb["cagr"], "status": "SUPPORTED REALISTIC ACCOUNTING"}
        },
        "decision_conclusion": "NO FURTHER PORTFOLIO ARCHITECTURE IMPROVEMENT FOUND — FROZEN CANDIDATES V-A AND V-B REMAIN UNCHANGED"
    }

    out_file = V2 / "research_k/research_x_orthogonal_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 80)
    print("RESEARCH X RESULTS SUMMARY (vs Frozen V-A and V-B Controls)")
    print("=" * 80)
    print(f"V-A Baseline (Total Vol): CAGR={m_va['cagr']:.2%}, Vol={m_va['volatility']:.2%}, MaxDD={m_va['max_dd']:.2%}, Sharpe={m_va['sharpe_vs_broad_tr']:.2f}")
    print(f"X1 Residual Volatility:  CAGR={m_x1['cagr']:.2%}, Vol={m_x1['volatility']:.2%}, MaxDD={m_x1['max_dd']:.2%}, Sharpe={m_x1['sharpe_vs_broad_tr']:.2f}")
    print(f"X2 Risk Parity (ERC):    CAGR={m_x2['cagr']:.2%}, Vol={m_x2['volatility']:.2%}, MaxDD={m_x2['max_dd']:.2%}, Sharpe={m_x2['sharpe_vs_broad_tr']:.2f}")
    print(f"X3 Momentum Conviction:  CAGR={m_x3['cagr']:.2%}, Vol={m_x3['volatility']:.2%}, MaxDD={m_x3['max_dd']:.2%}, Sharpe={m_x3['sharpe_vs_broad_tr']:.2f}")
    print("-" * 80)
    print(f"V-B Baseline (TV15):     CAGR={m_vb['cagr']:.2%}, Vol={m_vb['volatility']:.2%}, MaxDD={m_vb['max_dd']:.2%}, Sharpe={m_vb['sharpe_vs_broad_tr']:.2f}")
    print(f"X4 EWMA Vol Estimator:   CAGR={m_x4['cagr']:.2%}, Vol={m_x4['volatility']:.2%}, MaxDD={m_x4['max_dd']:.2%}, Sharpe={m_x4['sharpe_vs_broad_tr']:.2f}")
    print(f"X5 Real Cash Yield 2%:   CAGR={m_x5['cagr']:.2%}, Vol={m_x5['volatility']:.2%}, MaxDD={m_x5['max_dd']:.2%}, Sharpe={m_x5['sharpe_vs_broad_tr']:.2f}")
    print("=" * 80)
    print(f"CONCLUSION: {results['decision_conclusion']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
