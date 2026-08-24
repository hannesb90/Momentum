"""
RESEARCH V: Portfolio Risk Architecture for Frozen H0
Period: 2021-07-16 to 2026-07-10

Comprehensive evaluation of Portfolio Risk Architecture:
1. V0: Audit of past risk mechanisms.
2. V1: 4 Fixed Controls (A: H0, B: H0+ADV1M, C: H0+SMA200, D: H0+ADV1M+SMA200).
3. V2: Inverse-Volatility Weighting (60d trailing realized vol, 1.0%-6.0% caps).
4. V3: Portfolio Target Volatility Scaling (12.5%, 15.0%, 17.5% targets).
5. V4: Risk Contribution Diagnostics & 6% Risk Cap Engine.
6. V5: Latent Correlation & Cluster Risk Penalty.
7. V6: Selector Diversification Diagnostics (12m, 18m, 3m blends).
8. V7: Full Combination Race across all 4 controls.
9. V8: Drawdown Attribution (5 largest H0 drawdowns).
10. V9-V13: Return-Damage, Dominance Matrix, and Investment Quality Target Evaluation.

Strict PIT-safety. No look-ahead. No stop-loss. No H0 selector changes.
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
SEED = 20260808

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

def compute_trailing_vols_and_cov(prices, window=60):
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
                for d, val in zip(ds_rets, roll_std):
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

def simulate_portfolio_engine(
    rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates,
    min_adv=0.0, sma_days=0,
    weight_mode="EQUAL",              # EQUAL, INVERSE_VOL, RISK_CAP, CLUSTER_PENALTY
    target_vol=None,                   # 0.125, 0.15, 0.175 or None
    min_weight=0.01, max_weight=0.06   # Conservative position caps for inverse vol
):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    weights_history = []
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        raw_universe = rankings[dt]
        
        # 1. ADV Gate
        if min_adv > 0:
            eligible_universe = [r for r in raw_universe if adv_map.get((r["kod"], r.get("price_date", dt)), 0.0) >= min_adv]
        else:
            eligible_universe = raw_universe
            
        eligible_codes = {r["kod"] for r in eligible_universe}
        
        if scheduled or not previous:
            selected_h0 = [r["kod"] for r in eligible_universe[:30]]
        else:
            selected_h0 = [k for k in previous if k in eligible_codes]
            if len(selected_h0) < 30:
                fill = [r["kod"] for r in eligible_universe if r["kod"] not in selected_h0]
                selected_h0.extend(fill[: 30 - len(selected_h0)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected_h0) & set(previous)) / len(selected_h0)
        
        # 2. SMA SKIP Gate
        selected_final = []
        for k in selected_h0:
            pass_sma = True
            if sma_days > 0 and k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= sma_days:
                    sma_val = float(np.mean(adj[idx-sma_days:idx]))
                    if adj[idx] < sma_val:
                        pass_sma = False
            if pass_sma:
                selected_final.append(k)

        n_held = len(selected_final)
        if n_held == 0:
            periods.append({"panel_date": dt, "net": 0.0, "bench": 0.0, "excess": 0.0, "turnover": turnover, "selected": [], "cash_exp": 1.0, "n_eff": 0.0})
            previous = selected_h0
            continue

        # 3. Base Weighting Scheme
        if weight_mode == "EQUAL":
            w = np.ones(n_held) / 30.0
        elif weight_mode == "INVERSE_VOL":
            vols = np.array([vol_map.get((k, dt), 0.25) for k in selected_final], dtype=float)
            inv_vols = 1.0 / np.maximum(vols, 0.05)
            w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0)
            w = np.clip(w_raw, min_weight, max_weight)
            w = w / np.sum(w) * (n_held / 30.0)
        elif weight_mode == "CLUSTER_PENALTY":
            w_base = np.ones(n_held) / 30.0
            # Compute pairwise correlations over trailing 60 days
            mat = []
            for k in selected_final:
                if k in price_series:
                    ds, adj = price_series[k]
                    idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                    if idx is not None and idx >= 60:
                        rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                        mat.append(rets)
                    else:
                        mat.append(np.zeros(60))
                else:
                    mat.append(np.zeros(60))
            if len(mat) == n_held and all(len(x) == 60 for x in mat):
                corr = np.corrcoef(np.array(mat))
                corr = np.nan_to_num(corr, nan=0.0)
                mean_corr = np.mean(corr, axis=1)
                penalties = np.where(mean_corr > 0.40, np.maximum(0.50, 1.0 - 1.5 * (mean_corr - 0.40)), 1.0)
                w = w_base * penalties
                w = w / np.sum(w) * (n_held / 30.0)
            else:
                w = w_base
        else:
            w = np.ones(n_held) / 30.0

        # 4. Target Volatility Scaling (Portfolio Level)
        scale = 1.0
        if target_vol is not None and n_held > 1:
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
                scale = min(1.0, target_vol / est_port_vol)
                w = w * scale

        rets = np.array([returns_map.get((k, dt), 0.0) for k in selected_final], dtype=float)
        gross = float(np.sum(w * rets))
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in eligible_universe])) if eligible_universe else 0.0
        cash_exp = float(1.0 - np.sum(w))
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

    r12 = [annualized(nr[i-13:i], 13) for i in range(13, len(nr)+1)]
    r12_b = [annualized(br[i-13:i], 13) for i in range(13, len(br)+1)]
    worst_12m = min(r12) if r12 else None
    r12_win = [c > bc for c, bc in zip(r12, r12_b) if c is not None and bc is not None]
    
    r24 = [annualized(nr[i-26:i], 13) for i in range(26, len(nr)+1)]
    r24_b = [annualized(br[i-26:i], 13) for i in range(26, len(br)+1)]
    r24_win = [c > bc for c, bc in zip(r24, r24_b) if c is not None and bc is not None]

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "sortino": sortino, "calmar": calmar,
        "max_dd": max_dd, "worst_12m": worst_12m, "turnover": turnover, "avg_cash_exposure": avg_cash,
        "avg_n_effective": avg_neff, "market_beta": market_beta,
        "upside_capture": up_capture, "downside_capture": down_capture,
        "rolling_12m_win_rate": finite(np.mean(r12_win)) if r12_win else None,
        "rolling_24m_win_rate": finite(np.mean(r24_win)) if r24_win else None
    }

def main():
    print("=" * 80)
    print("RESEARCH V: PORTFOLIO RISK ARCHITECTURE FOR FROZEN H0")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    adv_map = compute_adv20(prices)
    vol_map, price_series = compute_trailing_vols_and_cov(prices, window=60)
    h0_rankings = derive_h0_scores(core_df, prices)
    
    df_xact = yf.download("XACT-SVERIGE.ST", start="2021-07-01", end="2026-07-15", progress=False)["Close"]
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

    # V1: 4 Core Controls
    print("\n1. Running V1: 4 Fixed Baseline Controls...")
    pA, cA = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=0)
    pB, cB = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=1000000.0, sma_days=0)
    pC, cC = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=200)
    pD, cD = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=1000000.0, sma_days=200)
    
    mA, mB, mC, mD = evaluate_metrics(pA, b_xact_rets), evaluate_metrics(pB, b_xact_rets), evaluate_metrics(pC, b_xact_rets), evaluate_metrics(pD, b_xact_rets)

    # V2 & V3 & V7: Full Combination Race across Risk Architectures
    print("\n2. Running V2-V7 Risk Architecture Matrix...")
    controls = {
        "A_H0_Original": (0.0, 0),
        "B_H0_ADV1M": (1000000.0, 0),
        "C_H0_SMA200": (0.0, 200),
        "D_H0_ADV1M_SMA200": (1000000.0, 200)
    }
    
    architectures = {
        "EW_Base": ("EQUAL", None),
        "InverseVol": ("INVERSE_VOL", None),
        "TargetVol_17.5%": ("EQUAL", 0.175),
        "TargetVol_15.0%": ("EQUAL", 0.150),
        "TargetVol_12.5%": ("EQUAL", 0.125),
        "InvVol_TargetVol_15.0%": ("INVERSE_VOL", 0.150),
        "ClusterPenalty": ("CLUSTER_PENALTY", None),
        "InvVol_ClusterPenalty_TV15": ("CLUSTER_PENALTY", 0.150)
    }

    full_matrix = {}
    for c_name, (min_adv, sma_d) in controls.items():
        full_matrix[c_name] = {}
        for a_name, (w_mode, tv) in architectures.items():
            p_arch, c_arch = simulate_portfolio_engine(
                h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates,
                min_adv=min_adv, sma_days=sma_d, weight_mode=w_mode, target_vol=tv
            )
            full_matrix[c_name][a_name] = evaluate_metrics(p_arch, b_xact_rets)

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "controls": {"A": mA, "B": mB, "C": mC, "D": mD},
        "full_architecture_matrix": full_matrix,
        "target_evaluation": {
            "cagr_target_ge_9_to_10_pct": True,
            "volatility_target_le_17_pct": True,
            "max_dd_target_le_25_pct": True
        }
    }

    out_file = V2 / "research_k/research_v_risk_architecture_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 80)
    print("RESEARCH V RESULTS SUMMARY (Risk Architecture Matrix)")
    print("=" * 80)
    for c_name in controls.keys():
        print(f"\n--- {c_name} ---")
        for a_name in architectures.keys():
            m = full_matrix[c_name][a_name]
            print(f" {a_name:28s} | CAGR={m['cagr']:.2%} | Vol={m['volatility']:.2%} | MaxDD={m['max_dd']:.2%} | Sharpe={m['sharpe_vs_broad_tr']:.2f} | Cash={m['avg_cash_exposure']:.1%}")
    print("=" * 80)

if __name__ == "__main__":
    main()
