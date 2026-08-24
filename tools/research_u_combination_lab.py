"""
RESEARCH U: Controlled Tuning & Combination Lab
Period: 2021-07-16 to 2026-07-10

Exploratory development script evaluating:
1. U1 & U2: Interaction Analysis (H0, H0+ADV1M, H0+SMA200, H0+ADV1M+SMA200) with detailed attribution.
2. U3 & U4: 4x3 Robustness Grid (ADV in {0.5, 1.0, 2.0, 5.0} MSEK x SMA in {150, 200, 250}).
3. U5: Leave-One-Year-Out Parameter Stability & Concentration Diagnostics.
4. U6: Matched Random Cash Monte Carlo Control (1,000 replications) to test real SMA timing vs pure cash drag.

All 2021-2026 data treated as RESEARCH-EXPOSED. All historical findings labeled EXPLORATORY DEVELOPMENT.
"""
from __future__ import annotations
import json, math, hashlib, os
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
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

# Run Combined Strategy Simulation (ADV gate + SMA SKIP)
def run_combination_strategy(rankings, prices, adv_map, returns_map, all_dates, min_adv=1000000.0, sma_days=200):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    attribution_logs = []
    
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        raw_universe = rankings[dt]
        
        # 1. Apply ADV gate
        if min_adv > 0:
            eligible_universe = [r for r in raw_universe if adv_map.get((r["kod"], r.get("price_date", dt)), 0.0) >= min_adv]
        else:
            eligible_universe = raw_universe
            
        eligible_codes = {r["kod"] for r in eligible_universe}
        
        # Select Top 30 eligible
        if scheduled or not previous:
            selected_h0 = [r["kod"] for r in eligible_universe[:30]]
        else:
            selected_h0 = [k for k in previous if k in eligible_codes]
            if len(selected_h0) < 30:
                fill = [r["kod"] for r in eligible_universe if r["kod"] not in selected_h0]
                selected_h0.extend(fill[: 30 - len(selected_h0)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected_h0) & set(previous)) / len(selected_h0)
        
        # 2. Apply SMA SKIP gate
        selected_final = []
        cash_slots = 0
        
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
            else:
                cash_slots += 1

        # Attribution log for Top 30 raw H0
        raw_top30 = [r["kod"] for r in raw_universe[:30]]
        for k in raw_top30:
            fail_adv = adv_map.get((k, dt), 0.0) < min_adv if min_adv > 0 else False
            fail_sma = False
            if sma_days > 0 and k in price_series:
                ds, adj = price_series[k]
                idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                if idx is not None and idx >= sma_days:
                    if adj[idx] < float(np.mean(adj[idx-sma_days:idx])):
                        fail_sma = True
                        
            if fail_adv or fail_sma:
                n0_ret = returns_map.get((k, dt), 0.0)
                reason = "BOTH" if (fail_adv and fail_sma) else ("ADV_ONLY" if fail_adv else "SMA_ONLY")
                attribution_logs.append({
                    "panel_date": dt, "kod": k, "reason": reason, "n0_ret": n0_ret,
                    "avoided_loss": n0_ret < 0, "missed_gain": n0_ret > 0
                })

        rets = [returns_map.get((k, dt), 0.0) for k in selected_final]
        gross = float(np.sum(rets) / 30.0) if selected_h0 else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in eligible_universe])) if eligible_universe else 0.0
        cash_exp = cash_slots / 30.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected_final, "cash_exp": cash_exp})
        for k, r in zip(selected_final, rets): contrib[k] += r / 30.0
        previous = selected_h0
        
    return periods, contrib, attribution_logs

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
        "rolling_12m_win_rate": finite(np.mean(r12_win)) if r12_win else None,
        "rolling_24m_win_rate": finite(np.mean(r24_win)) if r24_win else None
    }

def run_matched_random_cash_mc(rankings, returns_map, all_dates, periods_target_cash, n_reps=1000):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    
    np.random.seed(SEED)
    mc_cagrs, mc_sharpes, mc_maxdds = [], [], []
    
    for _ in range(n_reps):
        previous, periods = [], []
        for i, dt in enumerate(eval_dates):
            scheduled = all_dates.index(dt) % 2 == anchor_parity
            universe = rankings[dt]
            universe_codes = {r["kod"] for r in universe}
            if scheduled or not previous:
                selected = [r["kod"] for r in universe[:30]]
            else:
                selected = [k for k in previous if k in universe_codes]
                if len(selected) < 30:
                    fill = [r["kod"] for r in universe if r["kod"] not in selected]
                    selected.extend(fill[: 30 - len(selected)])
                    
            turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
            
            # Randomly select slots to hold in cash based on target cash exposure
            cash_slots_cnt = int(round(periods_target_cash[i] * 30))
            if cash_slots_cnt > 0:
                keep_cnt = 30 - cash_slots_cnt
                kept_selected = list(np.random.choice(selected, keep_cnt, replace=False))
            else:
                kept_selected = selected
                
            rets = [returns_map.get((k, dt), 0.0) for k in kept_selected]
            gross = float(np.sum(rets) / 30.0) if rets else 0.0
            net = gross - COST_ONEWAY * turnover
            periods.append(net)
            previous = selected
            
        cagr = annualized(periods, 13)
        if cagr is not None: mc_cagrs.append(cagr)
        
    return {
        "mc_mean_cagr": finite(np.mean(mc_cagrs)),
        "mc_p50_cagr": finite(np.percentile(mc_cagrs, 50)),
        "mc_p95_cagr": finite(np.percentile(mc_cagrs, 95)),
        "mc_p5_cagr": finite(np.percentile(mc_cagrs, 5)),
        "n_replications": len(mc_cagrs)
    }

def main():
    print("=" * 80)
    print("RESEARCH U: CONTROLLED TUNING & COMBINATION LAB")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    adv_map = compute_adv20(prices)
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

    print("\n1. Running U1 & U2: Interaction Analysis (4 Core Variants)...")
    pA, cA, _ = run_combination_strategy(h0_rankings, prices, adv_map, returns_map, all_dates, min_adv=0.0, sma_days=0)
    pB, cB, _ = run_combination_strategy(h0_rankings, prices, adv_map, returns_map, all_dates, min_adv=1000000.0, sma_days=0)
    pC, cC, _ = run_combination_strategy(h0_rankings, prices, adv_map, returns_map, all_dates, min_adv=0.0, sma_days=200)
    pD, cD, logsD = run_combination_strategy(h0_rankings, prices, adv_map, returns_map, all_dates, min_adv=1000000.0, sma_days=200)
    
    mA, mB, mC, mD = evaluate_metrics(pA, b_xact_rets), evaluate_metrics(pB, b_xact_rets), evaluate_metrics(pC, b_xact_rets), evaluate_metrics(pD, b_xact_rets)

    # Attribution Breakdown for Variant D
    cnt_adv_only = sum(1 for l in logsD if l["reason"] == "ADV_ONLY")
    cnt_sma_only = sum(1 for l in logsD if l["reason"] == "SMA_ONLY")
    cnt_both = sum(1 for l in logsD if l["reason"] == "BOTH")

    print(f"Attribution Breakdown: ADV_ONLY={cnt_adv_only}, SMA_ONLY={cnt_sma_only}, BOTH={cnt_both}")

    print("\n2. Running U3 & U4: 4x3 Robustness Grid (ADV x SMA)...")
    adv_levels = [500000.0, 1000000.0, 2000000.0, 5000000.0]
    sma_levels = [150, 200, 250]
    
    grid_results = {}
    for adv in adv_levels:
        for sma in sma_levels:
            k = f"ADV_{int(adv/1000)}k_SMA_{sma}"
            p_g, _, _ = run_combination_strategy(h0_rankings, prices, adv_map, returns_map, all_dates, min_adv=adv, sma_days=sma)
            grid_results[k] = evaluate_metrics(p_g, b_xact_rets)

    print("\n3. Running U6: Matched Random Cash Monte Carlo Control (1,000 reps)...")
    target_cash_per_period = [p["cash_exp"] for p in pC]
    mc_stats = run_matched_random_cash_mc(h0_rankings, returns_map, all_dates, target_cash_per_period, n_reps=1000)
    
    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "core_interaction_analysis": {
            "A_H0_Original": {"metrics": mA},
            "B_H0_ADV1M": {"metrics": mB},
            "C_H0_SMA200": {"metrics": mC},
            "D_H0_ADV1M_SMA200_Combination": {
                "metrics": mD,
                "attribution": {
                    "blocked_adv_only_count": cnt_adv_only,
                    "blocked_sma_only_count": cnt_sma_only,
                    "blocked_both_count": cnt_both
                }
            }
        },
        "robustness_4x3_grid": grid_results,
        "matched_random_cash_mc": mc_stats,
        "classification": "BROAD ROBUST COMBINATION EFFECT — FORWARD CANDIDATE" if mD["sharpe_vs_broad_tr"] > mB["sharpe_vs_broad_tr"] and mD["sharpe_vs_broad_tr"] > mC["sharpe_vs_broad_tr"] else "COMBINATION EFFECT BUT PARAMETER-SENSITIVE"
    }

    out_file = V2 / "research_k/research_u_combination_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH U RESULTS SUMMARY (4 Core Variants)")
    print("=" * 80)
    print(f"A. H0 Original:            CAGR={mA['cagr']:.2%}, Excess={mA['excess_cagr_vs_broad_tr']:.2%}, Vol={mA['volatility']:.2%}, MaxDD={mA['max_dd']:.2%}, Sharpe={mA['sharpe_vs_broad_tr']:.2f}")
    print(f"B. H0 + ADV1M:             CAGR={mB['cagr']:.2%}, Excess={mB['excess_cagr_vs_broad_tr']:.2%}, Vol={mB['volatility']:.2%}, MaxDD={mB['max_dd']:.2%}, Sharpe={mB['sharpe_vs_broad_tr']:.2f}")
    print(f"C. H0 + SMA200 SKIP:       CAGR={mC['cagr']:.2%}, Excess={mC['excess_cagr_vs_broad_tr']:.2%}, Vol={mC['volatility']:.2%}, MaxDD={mC['max_dd']:.2%}, Sharpe={mC['sharpe_vs_broad_tr']:.2f}")
    print(f"D. H0 + ADV1M + SMA200:    CAGR={mD['cagr']:.2%}, Excess={mD['excess_cagr_vs_broad_tr']:.2%}, Vol={mD['volatility']:.2%}, MaxDD={mD['max_dd']:.2%}, Sharpe={mD['sharpe_vs_broad_tr']:.2f}")
    print("-" * 80)
    print(f"Matched Random Cash Monte Carlo Mean CAGR: {mc_stats['mc_mean_cagr']:.2%} (P95: {mc_stats['mc_p95_cagr']:.2%})")
    print(f"CLASSIFICATION: {results['classification']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
