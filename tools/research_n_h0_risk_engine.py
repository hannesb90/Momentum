"""
RESEARCH N: H0 Risk Engine & Portfolio Architecture (No Selector Alteration)
Period: 2021-07-16 to 2026-07-10

Tests genuinely untested risk controls around the frozen H0 selector:
N0: Control H0 (Unconstrained Top 30 Equal Weight, 8w rebalance)
N1: Sector Diversification Cap (Max 25% per sector)
N2: Trailing Stop Loss (15% trailing stop per holding)
N3: Market Regime Trend Gate (Reduce exposure to 50% cash when OMXSPI is below 200-day SMA)
N4: Combined Risk Engine (Sector Cap + Market Regime Trend Gate)
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
    
    insts = json.loads((V2 / "docs/probes/instruments_live.json").read_text())
    sector_map = {i.get("ticker"): i.get("sectorId") for i in insts if isinstance(i, dict)}
    
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y52": y52, "sector_id": sector_map.get(r["kod"], 0)
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
            "kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18,
            "y52": r["y52"], "sector_id": r["sector_id"]
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

def load_omxspi_trend(eval_dates):
    df = yf.download("^OMXSPI", start="2020-01-01", end="2026-07-15", progress=False)["Close"]
    sma200 = df.rolling(200).mean()
    trend_map = {}
    for dt in eval_dates:
        dt_pd = pd.to_datetime(dt)
        idx = df.index.searchsorted(dt_pd)
        if idx < len(df):
            p = float(df.iloc[idx].iloc[0]) if hasattr(df.iloc[idx], "iloc") else float(df.iloc[idx])
            s = float(sma200.iloc[idx].iloc[0]) if hasattr(sma200.iloc[idx], "iloc") else float(sma200.iloc[idx])
            trend_map[dt] = (p >= s)
        else:
            trend_map[dt] = True
    return trend_map

# N0: Control H0
def run_N0(rankings, returns_map, all_dates):
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
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r in zip(selected, rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

# N1: Sector Diversification Cap (Max 25% per sector -> max 7.5 stocks per sector, i.e. max 7 stocks)
def run_N1(rankings, returns_map, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        if scheduled or not previous:
            selected = []
            sector_counts = defaultdict(int)
            for r in universe:
                sec = r.get("sector_id", 0)
                if sec == 0 or sector_counts[sec] < 7:
                    selected.append(r["kod"])
                    if sec != 0: sector_counts[sec] += 1
                if len(selected) == 30: break
        else:
            universe_codes = {r["kod"] for r in universe}
            selected = [k for k in previous if k in universe_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in universe if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gross = float(np.mean(rets)) if rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r in zip(selected, rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

# N2: Trailing Stop Loss (15% max loss per position within holding period)
def run_N2(rankings, returns_map, all_dates):
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
        raw_rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gated_rets = [max(r, -0.15) for r in raw_rets]
        
        gross = float(np.mean(gated_rets)) if gated_rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r in zip(selected, gated_rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

# N3: Market Regime Trend Gate (50% Cash allocation when OMXSPI < 200-day SMA)
def run_N3(rankings, returns_map, all_dates, trend_map):
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
        raw_gross = float(np.mean(rets)) if rets else 0.0
        
        is_bull = trend_map.get(dt, True)
        exposure = 1.0 if is_bull else 0.5
        gross = raw_gross * exposure
        
        net = gross - COST_ONEWAY * turnover * exposure
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "is_bull": is_bull})
        for k, r in zip(selected, rets): contrib[k] += r * exposure / len(selected)
        previous = selected
        
    return periods, contrib

# N4: Combined Risk Engine (Sector Cap + Market Regime Trend Gate)
def run_N4(rankings, returns_map, all_dates, trend_map):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        if scheduled or not previous:
            selected = []
            sector_counts = defaultdict(int)
            for r in universe:
                sec = r.get("sector_id", 0)
                if sec == 0 or sector_counts[sec] < 7:
                    selected.append(r["kod"])
                    if sec != 0: sector_counts[sec] += 1
                if len(selected) == 30: break
        else:
            universe_codes = {r["kod"] for r in universe}
            selected = [k for k in previous if k in universe_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in universe if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        raw_gross = float(np.mean(rets)) if rets else 0.0
        
        is_bull = trend_map.get(dt, True)
        exposure = 1.0 if is_bull else 0.5
        gross = raw_gross * exposure
        
        net = gross - COST_ONEWAY * turnover * exposure
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "is_bull": is_bull})
        for k, r in zip(selected, rets): contrib[k] += r * exposure / len(selected)
        previous = selected
        
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
    
    wealth = np.cumprod(1 + np.array(nr))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    max_dd = float(dd.min())
    turnover = float(np.mean([p["turnover"] for p in periods]))
    
    r24_win = []
    for i in range(26, len(nr) + 1):
        c = annualized(nr[i-26:i], 13)
        bc = annualized(br[i-26:i], 13)
        if c is not None and bc is not None:
            r24_win.append(c > bc)
            
    underperform = ex < 0
    max_streak, current_streak = 0, 0
    for u in underperform:
        if u:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "max_dd": max_dd,
        "turnover": turnover, "rolling_24m_win_rate": finite(np.mean(r24_win)) if r24_win else None,
        "longest_underperformance_periods": max_streak,
        "passes_quality_framework": bool(
            excess_cagr is not None and excess_cagr >= 0.030 and
            max_dd >= -0.250 and vol <= 0.180 and
            (np.mean(r24_win) if r24_win else 0) >= 0.900 and
            max_streak <= 3
        )
    }

def main():
    print("=" * 80)
    print("RESEARCH N: H0 RISK ENGINE & PORTFOLIO ARCHITECTURE")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Loading OMXSPI Trend & External Benchmarks...")
    eval_dates = sorted(h0_rankings.keys())
    trend_map = load_omxspi_trend(eval_dates)
    
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

    print("3. Executing Risk Engine Variants...")
    pN0, cN0 = run_N0(h0_rankings, returns_map, all_dates)
    pN1, cN1 = run_N1(h0_rankings, returns_map, all_dates)
    pN2, cN2 = run_N2(h0_rankings, returns_map, all_dates)
    pN3, cN3 = run_N3(h0_rankings, returns_map, all_dates, trend_map)
    pN4, cN4 = run_N4(h0_rankings, returns_map, all_dates, trend_map)
    
    mN0 = evaluate_metrics(pN0, b_xact_rets)
    mN1 = evaluate_metrics(pN1, b_xact_rets)
    mN2 = evaluate_metrics(pN2, b_xact_rets)
    mN3 = evaluate_metrics(pN3, b_xact_rets)
    mN4 = evaluate_metrics(pN4, b_xact_rets)
    
    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "N0_Control_H0": mN0,
        "N1_Sector_Cap_25pct": mN1,
        "N2_Trailing_Stop_15pct": mN2,
        "N3_Market_Regime_Trend_Gate": mN3,
        "N4_Combined_Sector_and_Trend_Gate": mN4
    }
    
    out_file = V2 / "research_k/research_n_risk_engine_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH N RESULTS SUMMARY (vs Broad Sweden TR ETF)")
    print("=" * 80)
    print(f"N0 (Control H0):        CAGR={mN0['cagr']:.2%}, Excess={mN0['excess_cagr_vs_broad_tr']:.2%}, Vol={mN0['volatility']:.2%}, MaxDD={mN0['max_dd']:.2%}, Sharpe={mN0['sharpe_vs_broad_tr']:.2f}")
    print(f"N1 (Sector Cap 25%):    CAGR={mN1['cagr']:.2%}, Excess={mN1['excess_cagr_vs_broad_tr']:.2%}, Vol={mN1['volatility']:.2%}, MaxDD={mN1['max_dd']:.2%}, Sharpe={mN1['sharpe_vs_broad_tr']:.2f}")
    print(f"N2 (Trailing Stop 15%): CAGR={mN2['cagr']:.2%}, Excess={mN2['excess_cagr_vs_broad_tr']:.2%}, Vol={mN2['volatility']:.2%}, MaxDD={mN2['max_dd']:.2%}, Sharpe={mN2['sharpe_vs_broad_tr']:.2f}")
    print(f"N3 (Market Trend Gate): CAGR={mN3['cagr']:.2%}, Excess={mN3['excess_cagr_vs_broad_tr']:.2%}, Vol={mN3['volatility']:.2%}, MaxDD={mN3['max_dd']:.2%}, Sharpe={mN3['sharpe_vs_broad_tr']:.2f}")
    print(f"N4 (Combined N1+N3):    CAGR={mN4['cagr']:.2%}, Excess={mN4['excess_cagr_vs_broad_tr']:.2%}, Vol={mN4['volatility']:.2%}, MaxDD={mN4['max_dd']:.2%}, Sharpe={mN4['sharpe_vs_broad_tr']:.2f}")
    print("=" * 80)

if __name__ == "__main__":
    main()
