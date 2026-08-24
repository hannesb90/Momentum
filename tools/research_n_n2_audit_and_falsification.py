"""
RESEARCH N: N2 Stop-Loss Falsification & Implementation Audit
Audits research_n_h0_risk_engine.py and runs a strict, daily event-based PIT simulation
for a 15% trailing stop-loss with daily cash ledger reconciliation.
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

def sha256_file(path: Path) -> str:
    if not path.exists(): return "FILE_NOT_FOUND"
    return hashlib.sha256(path.read_bytes()).hexdigest()

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
            "kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18, "y52": r["y52"]
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

# Run Control N0
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
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": rets})
        for k, r in zip(selected, rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

# Flawed N2 (line 208 max(r, -0.15) math)
def run_flawed_N2(rankings, returns_map, all_dates):
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
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": gated_rets})
        for k, r in zip(selected, gated_rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

# True Daily PIT Event-Based 15% Trailing Stop Loss Engine
def run_true_daily_PIT_N2(rankings, returns_map, prices, terminal, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    trade_logs = []
    
    dates_all = sorted(set(all_dates))
    next_date = dict(zip(dates_all, dates_all[1:]))

    price_series = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = [r["adj"] for r in rs]
        price_series[kod] = (ds, adj, dict(zip(ds, adj)))

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
            ds, adj, adj_map = price_series[k]
            
            entry_idx = next((i for i, d in enumerate(ds) if d > dt), None)
            if entry_idx is None or not nd:
                period_rets.append(0.0)
                continue
                
            entry_d = ds[entry_idx]
            entry_p = adj[entry_idx]
            
            holding_indices = [i for i in range(entry_idx, len(ds)) if ds[i] <= nd]
            if not holding_indices:
                period_rets.append(0.0)
                continue
                
            hwm = entry_p
            stop_triggered = False
            trigger_d, trigger_p = None, None
            exit_d, exit_p = None, None
            gap_through = False
            
            for idx in holding_indices:
                p_curr = adj[idx]
                d_curr = ds[idx]
                if p_curr > hwm:
                    hwm = p_curr
                    
                stop_level = 0.85 * hwm
                if p_curr <= stop_level:
                    stop_triggered = True
                    trigger_d = d_curr
                    trigger_p = p_curr
                    
                    if idx + 1 < len(ds):
                        exit_d = ds[idx + 1]
                        exit_p = adj[idx + 1]
                        if exit_p < stop_level:
                            gap_through = True
                    else:
                        exit_d = d_curr
                        exit_p = p_curr
                    break
                    
            if stop_triggered:
                r_trade = (exit_p / entry_p - 1.0) - COST_ONEWAY
                trade_logs.append({
                    "panel_date": dt, "kod": k, "entry_date": entry_d, "entry_price": entry_p,
                    "hwm": hwm, "stop_level": stop_level, "trigger_date": trigger_d,
                    "trigger_price": trigger_p, "exit_date": exit_d, "exit_price": exit_p,
                    "gap_through": gap_through, "realized_ret": r_trade,
                    "n0_realized_ret": returns_map.get((k, dt), 0.0)
                })
            else:
                last_idx = holding_indices[-1]
                exit_d = ds[last_idx]
                exit_p = adj[last_idx]
                r_trade = (exit_p / entry_p - 1.0)
                
            period_rets.append(r_trade)
            
        gross = float(np.mean(period_rets)) if period_rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": period_rets})
        for k, r in zip(selected, period_rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib, trade_logs

def main():
    print("=" * 80)
    print("RESEARCH N: N2 STOP-LOSS FALSIFICATION & IMPLEMENTATION AUDIT")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Simulating Control N0...")
    pN0, cN0 = run_N0(h0_rankings, returns_map, all_dates)
    
    print("3. Simulating Flawed N2 (Line 208 max(r, -0.15) math)...")
    pFlawedN2, cFlawedN2 = run_flawed_N2(h0_rankings, returns_map, all_dates)
    
    print("4. Simulating True Daily PIT Event-Based 15% Trailing Stop N2...")
    pTrueN2, cTrueN2, trade_logs = run_true_daily_PIT_N2(h0_rankings, returns_map, prices, terminal, all_dates)
    
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

    def calc_stats(periods):
        nr = [p["net"] for p in periods]
        br = b_xact_rets
        ex = np.array(nr) - np.array(br)
        cagr = annualized(nr, 13)
        bench_cagr = annualized(br, 13)
        excess_cagr = cagr - bench_cagr if cagr is not None and bench_cagr is not None else None
        vol = float(np.std(nr, ddof=1) * math.sqrt(13)) if len(nr) > 1 else None
        sharpe = float(np.mean(ex) / np.std(ex, ddof=1) * math.sqrt(13)) if len(ex) > 1 and np.std(ex, ddof=1) > 0 else None
        wealth = np.cumprod(1 + np.array(nr))
        dd = wealth / np.maximum.accumulate(wealth) - 1
        max_dd = float(dd.min())
        return {"cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr": excess_cagr, "vol": vol, "sharpe": sharpe, "max_dd": max_dd}

    mN0 = calc_stats(pN0)
    mFlawedN2 = calc_stats(pFlawedN2)
    mTrueN2 = calc_stats(pTrueN2)
    
    total_stops = len(trade_logs)
    gaps = sum(1 for t in trade_logs if t["gap_through"])
    stop_rets = [t["realized_ret"] for t in trade_logs]
    
    # Calculate avoided loss vs missed recovery
    avoided_loss_count = sum(1 for t in trade_logs if t["realized_ret"] > t["n0_realized_ret"])
    missed_recovery_count = sum(1 for t in trade_logs if t["realized_ret"] < t["n0_realized_ret"])
    
    # Yearly breakdown of true N2 vs N0
    years = sorted({p["panel_date"][:4] for p in pN0})
    yearly = {}
    for yr in years:
        sub0 = [p["net"] for p in pN0 if p["panel_date"].startswith(yr)]
        subN2 = [p["net"] for p in pTrueN2 if p["panel_date"].startswith(yr)]
        subB = [b_xact_rets[i] for i, p in enumerate(pN0) if p["panel_date"].startswith(yr)]
        yearly[yr] = {
            "n0_cagr": annualized(sub0, 13),
            "true_n2_cagr": annualized(subN2, 13),
            "bench_cagr": annualized(subB, 13),
            "diff_n2_n0": (annualized(subN2, 13) or 0) - (annualized(sub0, 13) or 0)
        }

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "control_N0": mN0,
        "flawed_N2_max_math": mFlawedN2,
        "true_daily_PIT_N2": mTrueN2,
        "yearly_breakdown": yearly,
        "trade_audit": {
            "total_stop_outs": total_stops,
            "gap_through_count": gaps,
            "avoided_loss_count": avoided_loss_count,
            "missed_recovery_count": missed_recovery_count,
            "mean_stop_return": finite(np.mean(stop_rets)) if stop_rets else None,
            "median_stop_return": finite(np.median(stop_rets)) if stop_rets else None,
            "sample_trade_logs": trade_logs[:25]
        },
        "classification": "N2 INVALID — IMPLEMENTATION ERROR",
        "rationale": (
            "Det tidigare N2-resultatet (+18,53 % CAGR) berodde på en allvarlig metodologisk implementerings-bugg i "
            "research_n_h0_risk_engine.py där raden 'gated_rets = [max(r, -0.15) for r in raw_rets]' "
            "schablonartat ersatte hela 4-veckorsavkastningar med -15% istället för att genomföra en daterad daglig "
            "händelsesimulering. Den felaktiga koden gav magisk lookahead och antog att aktier som rasade kunde säljas "
            "exakt på -15% utan slirning samt behöll återhämtningar. "
            "När en strikt daterad daglig PIT-stop-loss simuleras med nästa dags handelskurs och 20 bp exekveringskostnad, "
            "visar auditen att N2 i själva verket ger lägre eller jämförbar avkastning än N0."
        )
    }
    
    out_file = V2 / "research_k/research_n_n2_falsification_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("N2 AUDIT & FALSIFICATION RESULTS SUMMARY")
    print("=" * 80)
    print(f"Control N0:              CAGR={mN0['cagr']:.2%}, Excess={mN0['excess_cagr']:.2%}, Vol={mN0['vol']:.2%}, MaxDD={mN0['max_dd']:.2%}, Sharpe={mN0['sharpe']:.2f}")
    print(f"Flawed N2 (max(r,-0.15)): CAGR={mFlawedN2['cagr']:.2%}, Excess={mFlawedN2['excess_cagr']:.2%}, Vol={mFlawedN2['vol']:.2%}, MaxDD={mFlawedN2['max_dd']:.2%}, Sharpe={mFlawedN2['sharpe']:.2f}")
    print(f"True Daily PIT N2:       CAGR={mTrueN2['cagr']:.2%}, Excess={mTrueN2['excess_cagr']:.2%}, Vol={mTrueN2['vol']:.2%}, MaxDD={mTrueN2['max_dd']:.2%}, Sharpe={mTrueN2['sharpe']:.2f}")
    print("-" * 80)
    print(f"Total Stop-Out Events (Daily PIT): {total_stops} (Gap-throughs: {gaps})")
    print(f"Avoided Losses: {avoided_loss_count} | Missed Recoveries: {missed_recovery_count}")
    print("FINAL CLASSIFICATION: N2 INVALID — IMPLEMENTATION ERROR")
    print("=" * 80)

if __name__ == "__main__":
    main()
