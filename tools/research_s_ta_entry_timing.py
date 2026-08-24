"""
RESEARCH S: TA Entry / Timing Gate for Frozen H0
Period: 2021-07-16 to 2026-07-10

Audits and evaluates TA entry gates for stocks selected by frozen H0 (Top 30 equal weight):
S0: Control H0 (No TA Entry Gate, 100% Invested in Top 30)
S1: SMA200 Entry Gate (Close(T) >= SMA200(T))
S2: 13w Momentum Entry Gate (P(T)/P(T-65d) - 1 >= 0.0)
S3: Donchian20 Low Entry Gate (Close(T) >= min of preceding 20 trading days [T-20d, T-1d])
S4: EMA 12/26 Cross Entry Gate (EMA12(T) >= EMA26(T))

Tested separately in two pre-defined modes:
- Mode A (SKIP): Failed stock is skipped for the 8w period; 1/30th weight stays in cash.
- Mode B (DELAY): Failed stock is checked daily; bought at T+1 close on the first day TA condition becomes PASS.

All TA indicators calculated on total-return corporate-action-adjusted close ('adj').
Includes conditional forward returns (PASS vs FAIL) for 1v, 4v, 8v horizons.
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

# S0: Control H0
def run_S0(rankings, returns_map, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        universe_codes = {r["kod"] for r in universe}
        if scheduled:
            selected = [r["kod"] for r in universe[:30]]
        elif previous:
            selected = [k for k in previous if k in universe_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in universe if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
        else:
            selected = [r["kod"] for r in universe[:30]]
            
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gross = float(np.mean(rets)) if rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": rets})
        for k, r in zip(selected, rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

def check_ta_condition(adj, idx, rule_type):
    if rule_type == "S1_SMA200":
        if idx >= 200:
            sma200 = float(np.mean(adj[idx-200:idx]))
            return adj[idx] >= sma200
    elif rule_type == "S2_Mom13w":
        if idx >= 65:
            mom13w = float(adj[idx] / adj[idx-65] - 1.0)
            return mom13w >= 0.0
    elif rule_type == "S3_Donchian20":
        if idx >= 20:
            donch20 = float(np.min(adj[idx-20:idx]))
            return adj[idx] >= donch20
    elif rule_type == "S4_EMACross":
        if idx >= 26:
            series_adj = pd.Series(adj[:idx+1])
            ema12 = float(series_adj.ewm(span=12, adjust=False).mean().iloc[-1])
            ema26 = float(series_adj.ewm(span=26, adjust=False).mean().iloc[-1])
            return ema12 >= ema26
    return True

# Simulation of TA Entry Gate in Mode A (SKIP) or Mode B (DELAY)
def run_entry_gate_variant(rankings, prices, terminal, returns_map, all_dates, rule_type="S1_SMA200", mode="SKIP"):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    entry_logs = []
    
    dates_all = sorted(set(all_dates))
    next_date = dict(zip(dates_all, dates_all[1:]))

    price_series = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = [r["adj"] for r in rs]
        price_series[kod] = (ds, adj)

    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        universe_codes = {r["kod"] for r in universe}
        if scheduled:
            selected = [r["kod"] for r in universe[:30]]
        elif previous:
            selected = [k for k in previous if k in universe_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in universe if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
        else:
            selected = [r["kod"] for r in universe[:30]]
            
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        nd = next_date.get(dt)
        
        period_rets = []
        cash_slots = 0
        
        for k in selected:
            n0_ret = returns_map.get((k, dt), 0.0)
            if k not in price_series:
                period_rets.append(0.0)
                cash_slots += 1
                continue
            ds, adj = price_series[k]
            
            # Ordinarie decision date index in prices
            dec_idx = next((i for i, d in enumerate(ds) if d <= dt), None)
            if dec_idx is None:
                period_rets.append(0.0)
                cash_slots += 1
                continue
            # Handle searchsorted for exact decision index
            dec_idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), dec_idx)
            
            entry_idx = next((i for i, d in enumerate(ds) if d > dt), None)
            if entry_idx is None or not nd:
                period_rets.append(0.0)
                cash_slots += 1
                continue
                
            entry_d = ds[entry_idx]
            entry_p = adj[entry_idx]
            sched_exit_idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= nd), entry_idx)
            sched_exit_p = adj[sched_exit_idx]
            
            # Check TA condition at decision date T (dec_idx)
            condition_pass = check_ta_condition(adj, dec_idx, rule_type)
            
            if condition_pass:
                # Normal H0 entry at T+1
                r_trade = (sched_exit_p / entry_p - 1.0) if entry_p > 0 else 0.0
                period_rets.append(r_trade)
            else:
                # TA Entry Condition Failed!
                if mode == "SKIP":
                    # Fully skip trade, weight stays in cash (0% return)
                    period_rets.append(0.0)
                    cash_slots += 1
                    entry_logs.append({
                        "panel_date": dt, "kod": k, "mode": "SKIP", "condition": "FAIL",
                        "ordinary_entry_date": entry_d, "ordinary_entry_price": entry_p,
                        "n0_realized_ret": n0_ret, "realized_ret": 0.0,
                        "avoided_loss": n0_ret < 0, "missed_gain": n0_ret > 0,
                        "delay_days": None
                    })
                elif mode == "DELAY":
                    # Check daily during period [entry_idx .. sched_exit_idx]
                    delayed_entry_idx = None
                    for check_i in range(dec_idx + 1, sched_exit_idx):
                        if check_ta_condition(adj, check_i, rule_type):
                            delayed_entry_idx = check_i + 1 # Execute next day close
                            break
                            
                    if delayed_entry_idx is not None and delayed_entry_idx <= sched_exit_idx:
                        del_entry_d = ds[delayed_entry_idx]
                        del_entry_p = adj[delayed_entry_idx]
                        # Realized return from delayed entry to scheduled exit
                        r_trade = ((sched_exit_p / del_entry_p - 1.0) - COST_ONEWAY) if del_entry_p > 0 else 0.0
                        delay_days = (date.fromisoformat(del_entry_d) - date.fromisoformat(entry_d)).days
                        
                        period_rets.append(r_trade)
                        entry_logs.append({
                            "panel_date": dt, "kod": k, "mode": "DELAY", "condition": "DELAYED_BUY",
                            "ordinary_entry_date": entry_d, "ordinary_entry_price": entry_p,
                            "delayed_entry_date": del_entry_d, "delayed_entry_price": del_entry_p,
                            "n0_realized_ret": n0_ret, "realized_ret": r_trade,
                            "avoided_loss": r_trade > n0_ret, "missed_gain": r_trade < n0_ret,
                            "delay_days": delay_days
                        })
                    else:
                        # Never passed condition before scheduled rebalance
                        period_rets.append(0.0)
                        cash_slots += 1
                        entry_logs.append({
                            "panel_date": dt, "kod": k, "mode": "DELAY", "condition": "NEVER_BOUGHT",
                            "ordinary_entry_date": entry_d, "ordinary_entry_price": entry_p,
                            "n0_realized_ret": n0_ret, "realized_ret": 0.0,
                            "avoided_loss": n0_ret < 0, "missed_gain": n0_ret > 0,
                            "delay_days": None
                        })
                        
        gross = float(np.mean(period_rets)) if period_rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        cash_exp = cash_slots / 30.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": period_rets, "cash_exp": cash_exp})
        for k, r in zip(selected, period_rets): contrib[k] += r / 30.0
        previous = selected
        
    return periods, contrib, entry_logs

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

def concentration_analysis(contrib, returns_map, periods):
    ranked = sorted(contrib.items(), key=lambda z: z[1], reverse=True)
    top1 = [k for k, _ in ranked[:1]]
    top3 = [k for k, _ in ranked[:3]]
    top5 = [k for k, _ in ranked[:5]]
    
    def leave_out(excluded):
        rr = []
        for p in periods:
            ch = [k for k in p["selected"] if k not in excluded]
            if ch:
                rets = [returns_map.get((k, p["panel_date"]), 0.0) for k in ch]
                rr.append(np.mean(rets) - COST_ONEWAY * p["turnover"])
            else:
                rr.append(0.0)
        return annualized(rr, 13)

    return {
        "top1_tickers": top1, "top3_tickers": top3, "top5_tickers": top5,
        "cagr_leave_top5": leave_out(set(top5)),
        "top1_contrib_share": finite(ranked[0][1] / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
        "top3_contrib_share": finite(sum(v for _, v in ranked[:3]) / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
        "top5_contrib_share": finite(sum(v for _, v in ranked[:5]) / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
    }

def audit_conditional_forward_returns(rankings, prices, rule_type):
    pass_rets_1v, fail_rets_1v = [], []
    pass_rets_4v, fail_rets_4v = [], []
    pass_rets_8v, fail_rets_8v = [], []
    
    price_series = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = [r["adj"] for r in rs]
        price_series[kod] = (ds, adj)

    for dt, rows in sorted(rankings.items()):
        if dt < START_DATE or dt > END_DATE: continue
        top30 = rows[:30]
        for r in top30:
            k = r["kod"]
            if k not in price_series: continue
            ds, adj = price_series[k]
            dec_idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
            if dec_idx is None: continue
            
            cond_pass = check_ta_condition(adj, dec_idx, rule_type)
            
            p_entry = adj[dec_idx + 1] if dec_idx + 1 < len(ds) else adj[dec_idx]
            p_1v = adj[dec_idx + 5] if dec_idx + 5 < len(ds) else None
            p_4v = adj[dec_idx + 20] if dec_idx + 20 < len(ds) else None
            p_8v = adj[dec_idx + 40] if dec_idx + 40 < len(ds) else None
            
            r1 = (p_1v / p_entry - 1.0) if p_1v else None
            r4 = (p_4v / p_entry - 1.0) if p_4v else None
            r8 = (p_8v / p_entry - 1.0) if p_8v else None
            
            if cond_pass:
                if r1 is not None: pass_rets_1v.append(r1)
                if r4 is not None: pass_rets_4v.append(r4)
                if r8 is not None: pass_rets_8v.append(r8)
            else:
                if r1 is not None: fail_rets_1v.append(r1)
                if r4 is not None: fail_rets_4v.append(r4)
                if r8 is not None: fail_rets_8v.append(r8)

    def stats(arr):
        if not arr: return {"n": 0, "mean": None, "median": None, "win_rate": None}
        return {
            "n": len(arr), "mean": finite(np.mean(arr)), "median": finite(np.median(arr)),
            "win_rate": finite(np.mean(np.array(arr) > 0))
        }

    return {
        "1v_forward": {"pass": stats(pass_rets_1v), "fail": stats(fail_rets_1v)},
        "4v_forward": {"pass": stats(pass_rets_4v), "fail": stats(fail_rets_4v)},
        "8v_forward": {"pass": stats(pass_rets_8v), "fail": stats(fail_rets_8v)},
    }

def main():
    print("=" * 80)
    print("RESEARCH S: TA ENTRY / TIMING GATE FOR FROZEN H0")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Simulating Control S0 (Frozen H0, 100% Invested)...")
    pS0, cS0 = run_S0(h0_rankings, returns_map, all_dates)
    
    rules = ["S1_SMA200", "S2_Mom13w", "S3_Donchian20", "S4_EMACross"]
    modes = ["SKIP", "DELAY"]
    
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

    mS0 = evaluate_metrics(pS0, b_xact_rets)
    cS0_stats = concentration_analysis(cS0, returns_map, pS0)
    
    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "S0_Control_H0": {"metrics": mS0, "concentration": cS0_stats}
    }

    def classify(m_var, m_ctrl):
        if (m_var["sharpe_vs_broad_tr"] or 0) > (m_ctrl["sharpe_vs_broad_tr"] or 0) + 0.10 and (m_var["max_dd"] or -1) >= (m_ctrl["max_dd"] or -1) + 0.03 and (m_var["cagr"] or 0) >= (m_ctrl["cagr"] or 0):
            return "SUPPORTED"
        elif (m_var["sharpe_vs_broad_tr"] or 0) > (m_ctrl["sharpe_vs_broad_tr"] or 0) or (m_var["max_dd"] or -1) > (m_ctrl["max_dd"] or -1):
            return "WEAK-INCONCLUSIVE"
        else:
            return "NO SUPPORT"

    for r_type in rules:
        results[r_type] = {}
        for md in modes:
            print(f"Executing {r_type} Mode={md}...")
            p_var, c_var, logs_var = run_entry_gate_variant(h0_rankings, prices, terminal, returns_map, all_dates, r_type, md)
            m_var = evaluate_metrics(p_var, b_xact_rets)
            c_stats = concentration_analysis(c_var, returns_map, p_var)
            
            avoided = [l for l in logs_var if l["avoided_loss"]]
            missed = [l for l in logs_var if l["missed_gain"]]
            delay_days = [l["delay_days"] for l in logs_var if l["delay_days"] is not None]
            
            h0_top5 = cS0_stats["top5_tickers"]
            top5_logs = [l for l in logs_var if l["kod"] in h0_top5]
            
            results[r_type][md] = {
                "metrics": m_var,
                "concentration": c_stats,
                "entry_gate_stats": {
                    "total_blocked_entries": len(logs_var),
                    "avoided_loss_count": len(avoided),
                    "missed_gain_count": len(missed),
                    "net_timing_effect": finite(sum(l["realized_ret"] - l["n0_realized_ret"] for l in logs_var)),
                    "mean_delay_days": finite(np.mean(delay_days)) if delay_days else None,
                    "median_delay_days": finite(np.median(delay_days)) if delay_days else None,
                    "top5_winner_blocked_count": len(top5_logs),
                    "top5_winner_blocked_tickers": list(set(l["kod"] for l in top5_logs))
                },
                "classification": classify(m_var, mS0)
            }
            
        print(f"Auditing Conditional Forward Returns for {r_type}...")
        results[r_type]["conditional_forward_returns"] = audit_conditional_forward_returns(h0_rankings, prices, r_type)

    # Time Blocks Analysis
    years = sorted({p["panel_date"][:4] for p in pS0})
    blocks = {}
    for yr in years:
        blocks[yr] = {"S0_cagr": annualized([p["net"] for p in pS0 if p["panel_date"].startswith(yr)], 13)}

    results["time_blocks"] = blocks
    
    out_file = V2 / "research_k/research_s_ta_entry_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH S RESULTS SUMMARY (vs Broad Sweden TR ETF)")
    print("=" * 80)
    print(f"S0 (Control H0):        CAGR={mS0['cagr']:.2%}, Excess={mS0['excess_cagr_vs_broad_tr']:.2%}, Vol={mS0['volatility']:.2%}, MaxDD={mS0['max_dd']:.2%}, Sharpe={mS0['sharpe_vs_broad_tr']:.2f}")
    for r_type in rules:
        for md in modes:
            m = results[r_type][md]["metrics"]
            cls = results[r_type][md]["classification"]
            c_exp = m["avg_cash_exposure"]
            print(f"{r_type:15s} [{md:5s}] | CAGR={m['cagr']:.2%} | Excess={m['excess_cagr_vs_broad_tr']:.2%} | Vol={m['volatility']:.2%} | MaxDD={m['max_dd']:.2%} | Cash={c_exp:.1%} | Sharpe={m['sharpe_vs_broad_tr']:.2f} [{cls}]")
    print("=" * 80)

if __name__ == "__main__":
    main()
