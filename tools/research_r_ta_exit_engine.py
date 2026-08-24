"""
RESEARCH R: Technical Exit / Holding Engine for Frozen H0 (Refined Preregistration)
Period: 2021-07-16 to 2026-07-10

Audits and evaluates 4 genuinely untested trend-break TA exit rules around frozen H0:
R0: Control H0 (No TA exit)
R1: SMA200 Trend Break (Exit if daily adj close < 200-day SMA)
R2: 13-Week Momentum Deterioration (Exit if P(t)/P(t-65 trading days) - 1 < 0.0)
R3: Donchian 20-Day Low Break (Exit if daily adj close < min of preceding 20 trading days [t-20d, t-1d])
R4: EMA 12/26 Trend Cross (Exit if 12-day EMA < 26-day EMA)

QA & Execution Rules:
- All TA indicators calculated on total-return corporate-action-adjusted close ('adj').
- Strict entry/exit spärr: TA exit evaluation begins strictly AFTER position is established (t >= entry_idx + 1).
- Execution occurs at T+1 close (with gap-throughs & 20 bp fee).
- Released capital held in Cash Ledger (0% return) until next scheduled 8w rebalance.
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

# R0: Control H0
def run_R0(rankings, returns_map, all_dates):
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

# Daily PIT TA Exit Engine for R1..R4 with Strict Entry Spärr and Corporate Action Adjusted Prices ('adj')
def run_TA_exit_variant(rankings, prices, terminal, returns_map, all_dates, rule_type="R1_SMA200"):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    exit_logs = []
    
    dates_all = sorted(set(all_dates))
    next_date = dict(zip(dates_all, dates_all[1:]))

    price_series = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        # Use total-return corporate-action-adjusted close ('adj') for all TA indicators
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
        for k in selected:
            if k not in price_series:
                period_rets.append(0.0)
                continue
            ds, adj = price_series[k]
            
            entry_idx = next((i for i, d in enumerate(ds) if d > dt), None)
            if entry_idx is None or not nd:
                period_rets.append(0.0)
                continue
                
            entry_d = ds[entry_idx]
            entry_p = adj[entry_idx]
            
            # Find scheduled exit index (last price date <= nd)
            sched_exit_idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= nd), entry_idx)
            sched_exit_p = adj[sched_exit_idx]
            
            # Entry spärr: TA exit evaluation begins strictly AFTER position is established (entry_idx + 1)
            eval_indices = [i for i in range(entry_idx + 1, len(ds)) if ds[i] <= nd]
            
            exit_triggered = False
            trigger_d, trigger_p = None, None
            exec_d, exec_p = None, None
            exec_idx = None
            
            for idx in eval_indices:
                d_curr = ds[idx]
                p_curr = adj[idx]
                
                # Evaluate TA Exit Condition using PIT adjusted prices up to d_curr (idx)
                triggered = False
                if rule_type == "R1_SMA200":
                    if idx >= 200:
                        sma200 = float(np.mean(adj[idx-200:idx]))
                        if p_curr < sma200: triggered = True
                elif rule_type == "R2_Mom13w":
                    if idx >= 65:
                        # 65 trading days
                        mom13w = float(p_curr / adj[idx-65] - 1.0)
                        if mom13w < 0.0: triggered = True
                elif rule_type == "R3_Donchian20":
                    if idx >= 20:
                        # Preceding 20 trading days [idx-20 : idx], NOT including today's close (idx)
                        donch20 = float(np.min(adj[idx-20:idx]))
                        if p_curr < donch20: triggered = True
                elif rule_type == "R4_EMACross":
                    if idx >= 26:
                        # EMA12 and EMA26 up to idx
                        series_adj = pd.Series(adj[:idx+1])
                        ema12 = float(series_adj.ewm(span=12, adjust=False).mean().iloc[-1])
                        ema26 = float(series_adj.ewm(span=26, adjust=False).mean().iloc[-1])
                        if ema12 < ema26: triggered = True
                        
                if triggered:
                    exit_triggered = True
                    trigger_d = d_curr
                    trigger_p = p_curr
                    
                    if idx + 1 < len(ds):
                        exec_idx = idx + 1
                        exec_d = ds[exec_idx]
                        exec_p = adj[exec_idx]
                    else:
                        exec_idx = idx
                        exec_d = d_curr
                        exec_p = p_curr
                    break
                    
            n0_ret = returns_map.get((k, dt), 0.0)
            if exit_triggered:
                # Realized return with exit on exec_d (T+1 close)
                r_trade = (exec_p / entry_p - 1.0) - COST_ONEWAY
                # Post-exit return from exec_p to scheduled exit date
                post_exit_ret = (sched_exit_p / exec_p - 1.0) if exec_p > 0 else 0.0
                
                holding_days = (date.fromisoformat(exec_d) - date.fromisoformat(entry_d)).days
                
                exit_logs.append({
                    "panel_date": dt, "kod": k, "entry_date": entry_d, "entry_price": entry_p,
                    "trigger_date": trigger_d, "trigger_price": trigger_p,
                    "exec_date": exec_d, "exec_price": exec_p,
                    "sched_exit_price": sched_exit_p,
                    "realized_ret": r_trade, "n0_realized_ret": n0_ret,
                    "post_exit_ret": post_exit_ret,
                    "avoided_loss": post_exit_ret < 0,
                    "missed_recovery": post_exit_ret > 0,
                    "improved": r_trade > n0_ret,
                    "holding_days": holding_days
                })
            else:
                r_trade = (sched_exit_p / entry_p - 1.0)
                
            period_rets.append(r_trade)
            
        gross = float(np.mean(period_rets)) if period_rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": period_rets})
        for k, r in zip(selected, period_rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib, exit_logs

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
        "max_dd": max_dd, "worst_12m": worst_12m, "turnover": turnover,
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

def audit_exit_quality_and_winner_damage(exit_logs, h0_top5_tickers):
    if not exit_logs:
        return {
            "total_exits": 0, "improved_count": 0, "hurt_count": 0, "improved_share": None,
            "avoided_loss_count": 0, "missed_recovery_count": 0,
            "avoided_loss_sum": 0.0, "missed_recovery_sum": 0.0, "net_exit_effect": 0.0,
            "median_holding_days": None, "mean_holding_days": None,
            "top5_winner_exits_count": 0, "top5_winner_exits_tickers": []
        }
    
    total_exits = len(exit_logs)
    improved_count = sum(1 for e in exit_logs if e["improved"])
    hurt_count = total_exits - improved_count
    
    avoided = [e for e in exit_logs if e["avoided_loss"]]
    missed = [e for e in exit_logs if e["missed_recovery"]]
    
    avoided_sum = sum(e["realized_ret"] - e["n0_realized_ret"] for e in avoided)
    missed_sum = sum(e["n0_realized_ret"] - e["realized_ret"] for e in missed)
    net_effect = sum(e["realized_ret"] - e["n0_realized_ret"] for e in exit_logs)
    
    holding_days = [e["holding_days"] for e in exit_logs]
    top5_exits = [e for e in exit_logs if e["kod"] in h0_top5_tickers]
    
    return {
        "total_exits_count": total_exits,
        "improved_count": improved_count,
        "hurt_count": hurt_count,
        "improved_share": finite(improved_count / total_exits),
        "avoided_loss_count": len(avoided),
        "missed_recovery_count": len(missed),
        "avoided_loss_sum": finite(avoided_sum),
        "missed_recovery_sum": finite(missed_sum),
        "net_exit_effect": finite(net_effect),
        "median_holding_days": finite(np.median(holding_days)),
        "mean_holding_days": finite(np.mean(holding_days)),
        "top5_winner_exits_count": len(top5_exits),
        "top5_winner_exits_tickers": list(set(e["kod"] for e in top5_exits))
    }

def main():
    print("=" * 80)
    print("RESEARCH R: TECHNICAL EXIT / HOLDING ENGINE FOR FROZEN H0")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Simulating Control R0 (Frozen H0, No TA Exit)...")
    pR0, cR0 = run_R0(h0_rankings, returns_map, all_dates)
    
    print("3. Simulating R1 (SMA200 Moving Average Trend Break)...")
    pR1, cR1, logsR1 = run_TA_exit_variant(h0_rankings, prices, terminal, returns_map, all_dates, "R1_SMA200")
    
    print("4. Simulating R2 (13-Week Momentum Deterioration P(t)/P(t-65) - 1 < 0)...")
    pR2, cR2, logsR2 = run_TA_exit_variant(h0_rankings, prices, terminal, returns_map, all_dates, "R2_Mom13w")
    
    print("5. Simulating R3 (Donchian 20-Day Low Break)...")
    pR3, cR3, logsR3 = run_TA_exit_variant(h0_rankings, prices, terminal, returns_map, all_dates, "R3_Donchian20")
    
    print("6. Simulating R4 (EMA 12/26 Trend Cross)...")
    pR4, cR4, logsR4 = run_TA_exit_variant(h0_rankings, prices, terminal, returns_map, all_dates, "R4_EMACross")
    
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

    mR0 = evaluate_metrics(pR0, b_xact_rets)
    mR1 = evaluate_metrics(pR1, b_xact_rets)
    mR2 = evaluate_metrics(pR2, b_xact_rets)
    mR3 = evaluate_metrics(pR3, b_xact_rets)
    mR4 = evaluate_metrics(pR4, b_xact_rets)
    
    cR0_stats = concentration_analysis(cR0, returns_map, pR0)
    cR1_stats = concentration_analysis(cR1, returns_map, pR1)
    cR2_stats = concentration_analysis(cR2, returns_map, pR2)
    cR3_stats = concentration_analysis(cR3, returns_map, pR3)
    cR4_stats = concentration_analysis(cR4, returns_map, pR4)
    
    h0_top5 = cR0_stats["top5_tickers"]
    qR1 = audit_exit_quality_and_winner_damage(logsR1, h0_top5)
    qR2 = audit_exit_quality_and_winner_damage(logsR2, h0_top5)
    qR3 = audit_exit_quality_and_winner_damage(logsR3, h0_top5)
    qR4 = audit_exit_quality_and_winner_damage(logsR4, h0_top5)
    
    # Time Blocks
    years = sorted({p["panel_date"][:4] for p in pR0})
    blocks = {}
    for yr in years:
        subR0 = [p["net"] for p in pR0 if p["panel_date"].startswith(yr)]
        subR1 = [p["net"] for p in pR1 if p["panel_date"].startswith(yr)]
        subR2 = [p["net"] for p in pR2 if p["panel_date"].startswith(yr)]
        subR3 = [p["net"] for p in pR3 if p["panel_date"].startswith(yr)]
        subR4 = [p["net"] for p in pR4 if p["panel_date"].startswith(yr)]
        subTr = [b_xact_rets[i] for i, p in enumerate(pR0) if p["panel_date"].startswith(yr)]
        
        blocks[yr] = {
            "R0_cagr": annualized(subR0, 13),
            "R1_cagr": annualized(subR1, 13),
            "R2_cagr": annualized(subR2, 13),
            "R3_cagr": annualized(subR3, 13),
            "R4_cagr": annualized(subR4, 13),
            "broad_tr_cagr": annualized(subTr, 13)
        }

    def classify(m_variant, m_control):
        if (m_variant["sharpe_vs_broad_tr"] or 0) > (m_control["sharpe_vs_broad_tr"] or 0) + 0.10 and (m_variant["max_dd"] or -1) >= (m_control["max_dd"] or -1) + 0.03 and (m_variant["cagr"] or 0) >= (m_control["cagr"] or 0):
            return "SUPPORTED"
        elif (m_variant["sharpe_vs_broad_tr"] or 0) > (m_control["sharpe_vs_broad_tr"] or 0) or (m_variant["max_dd"] or -1) > (m_control["max_dd"] or -1):
            return "WEAK/INCONCLUSIVE"
        else:
            return "NO SUPPORT"

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "R0_Control_H0": {"metrics": mR0, "concentration": cR0_stats},
        "R1_SMA200_Trend_Break": {"metrics": mR1, "concentration": cR1_stats, "exit_quality": qR1, "classification": classify(mR1, mR0)},
        "R2_Mom13w_Deterioration": {"metrics": mR2, "concentration": cR2_stats, "exit_quality": qR2, "classification": classify(mR2, mR0)},
        "R3_Donchian20_Low_Break": {"metrics": mR3, "concentration": cR3_stats, "exit_quality": qR3, "classification": classify(mR3, mR0)},
        "R4_EMA12_26_Cross": {"metrics": mR4, "concentration": cR4_stats, "exit_quality": qR4, "classification": classify(mR4, mR0)},
        "time_blocks": blocks
    }
    
    out_file = V2 / "research_k/research_r_ta_exit_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH R RESULTS SUMMARY (vs Broad Sweden TR ETF)")
    print("=" * 80)
    print(f"R0 (Control H0):        CAGR={mR0['cagr']:.2%}, Excess={mR0['excess_cagr_vs_broad_tr']:.2%}, Vol={mR0['volatility']:.2%}, MaxDD={mR0['max_dd']:.2%}, Sharpe={mR0['sharpe_vs_broad_tr']:.2f}")
    print(f"R1 (SMA200 Break):      CAGR={mR1['cagr']:.2%}, Excess={mR1['excess_cagr_vs_broad_tr']:.2%}, Vol={mR1['volatility']:.2%}, MaxDD={mR1['max_dd']:.2%}, Sharpe={mR1['sharpe_vs_broad_tr']:.2f} [{results['R1_SMA200_Trend_Break']['classification']}]")
    print(f"R2 (Mom13w < 0):        CAGR={mR2['cagr']:.2%}, Excess={mR2['excess_cagr_vs_broad_tr']:.2%}, Vol={mR2['volatility']:.2%}, MaxDD={mR2['max_dd']:.2%}, Sharpe={mR2['sharpe_vs_broad_tr']:.2f} [{results['R2_Mom13w_Deterioration']['classification']}]")
    print(f"R3 (Donchian20 Low):    CAGR={mR3['cagr']:.2%}, Excess={mR3['excess_cagr_vs_broad_tr']:.2%}, Vol={mR3['volatility']:.2%}, MaxDD={mR3['max_dd']:.2%}, Sharpe={mR3['sharpe_vs_broad_tr']:.2f} [{results['R3_Donchian20_Low_Break']['classification']}]")
    print(f"R4 (EMA12/26 Cross):    CAGR={mR4['cagr']:.2%}, Excess={mR4['excess_cagr_vs_broad_tr']:.2%}, Vol={mR4['volatility']:.2%}, MaxDD={mR4['max_dd']:.2%}, Sharpe={mR4['sharpe_vs_broad_tr']:.2f} [{results['R4_EMA12_26_Cross']['classification']}]")
    print("=" * 80)

if __name__ == "__main__":
    main()
