"""
RESEARCH Q: Investable Universe & Quality Filter Falsification
Period: 2021-07-16 to 2026-07-10

Audits and evaluates:
1. Control A: Original Frozen H0 (Unconstrained Top 30 Equal Weight)
2. Variant B: H0 + Investability Gate (Trailing 20-day Average Daily Volume / SEK Turnover >= 1.0 MSEK)
3. Quality Gate & Size Gate: Formally BLOCKED based on Q0 Audit (0/68 delisted fundamental coverage, no PIT market cap).
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

def compute_adv20(prices):
    # Compute trailing 20-day Average Daily Volume in SEK (close * volume) for all tickers and dates
    adv_map = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        c = np.array([r.get("close", r["adj"]) for r in rs], dtype=float)
        v = np.array([r.get("v", 0.0) for r in rs], dtype=float)
        turnover = c * v
        
        # 20-day rolling mean
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

# Run Control A (Original H0)
def run_Control_A(rankings, returns_map, all_dates):
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

# Run Variant B (H0 + Investability Gate >= 1.0 MSEK ADV20)
def run_Variant_B(rankings, adv_map, returns_map, all_dates, min_adv=1000000.0):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    filter_logs = []
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        
        eligible = []
        filtered_out = []
        for r in universe:
            adv = adv_map.get((r["kod"], r.get("price_date", dt)), 0.0)
            if adv >= min_adv:
                eligible.append(r)
            else:
                filtered_out.append(r["kod"])
                
        filter_logs.append({
            "panel_date": dt, "total_universe": len(universe),
            "eligible_count": len(eligible), "filtered_out_count": len(filtered_out),
            "filtered_h0_top30": [r["kod"] for r in universe[:30] if r["kod"] in filtered_out]
        })
        
        eligible_codes = {r["kod"] for r in eligible}
        if scheduled or not previous:
            selected = [r["kod"] for r in eligible[:30]]
        else:
            selected = [k for k in previous if k in eligible_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in eligible if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gross = float(np.mean(rets)) if rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in eligible])) if eligible else 0.0
        
        periods.append({"panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected, "rets": rets})
        for k, r in zip(selected, rets): contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib, filter_logs

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

def main():
    print("=" * 80)
    print("RESEARCH Q: INVESTABLE UNIVERSE & QUALITY FILTER FALSIFICATION")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Computing Trailing 20-day Turnover (ADV20) for all tickers...")
    adv_map = compute_adv20(prices)
    
    print("2. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("3. Executing Control A (Original Frozen H0)...")
    pA, cA = run_Control_A(h0_rankings, returns_map, all_dates)
    
    print("4. Executing Variant B (H0 + Investability Gate >= 1.0 MSEK ADV20)...")
    pB, cB, filter_logs_B = run_Variant_B(h0_rankings, adv_map, returns_map, all_dates, min_adv=1000000.0)
    
    # Load Broad Sweden TR ETF
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

    mA = evaluate_metrics(pA, b_xact_rets)
    mB = evaluate_metrics(pB, b_xact_rets)
    
    cA_stats = concentration_analysis(cA, returns_map, pA)
    cB_stats = concentration_analysis(cB, returns_map, pB)
    
    years = sorted({p["panel_date"][:4] for p in pA})
    blocks = {}
    for yr in years:
        subA = [p["net"] for p in pA if p["panel_date"].startswith(yr)]
        subB = [p["net"] for p in pB if p["panel_date"].startswith(yr)]
        subTr = [b_xact_rets[i] for i, p in enumerate(pA) if p["panel_date"].startswith(yr)]
        blocks[yr] = {
            "h0_cagr": annualized(subA, 13),
            "investability_cagr": annualized(subB, 13),
            "broad_tr_cagr": annualized(subTr, 13),
            "excess_investability_vs_h0": (annualized(subB, 13) or 0) - (annualized(subA, 13) or 0)
        }
        
    total_h0_top30_filtered = sum(len(f["filtered_h0_top30"]) for f in filter_logs_B)
    filtered_ticker_counts = Counter()
    for f in filter_logs_B:
        filtered_ticker_counts.update(f["filtered_h0_top30"])

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "audit": {
            "size_gate_status": "SIZE TEST BLOCKED — NO PIT MARKET CAP CLASSIFICATION",
            "quality_gate_status": "QUALITY FILTER BLOCKED — 0/68 DELISTED FUNDAMENTAL COVERAGE (NOT SURVIVORSHIP SAFE)",
            "investability_gate_status": "INVESTABILITY FILTER TESTED (PIT ADV20 >= 1.0 MSEK)"
        },
        "Control_A_Original_H0": {
            "metrics": mA, "concentration": cA_stats
        },
        "Variant_B_Investability_Gate": {
            "metrics": mB, "concentration": cB_stats,
            "filter_impact": {
                "avg_eligible_count": finite(np.mean([f["eligible_count"] for f in filter_logs_B])),
                "total_h0_top30_filtered_events": total_h0_top30_filtered,
                "most_filtered_h0_tickers": filtered_ticker_counts.most_common(10)
            }
        },
        "time_blocks": blocks,
        "classification": "INVESTABILITY FILTER SUPPORTED" if (mB["sharpe_vs_broad_tr"] or 0) > (mA["sharpe_vs_broad_tr"] or 0) and (mB["max_dd"] or -1) >= (mA["max_dd"] or -1) else "INVESTABILITY FILTER NO SUPPORT"
    }
    
    out_file = V2 / "research_k/research_q_investability_quality_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH Q RESULTS SUMMARY")
    print("=" * 80)
    print(f"Control A (Original H0):     CAGR={mA['cagr']:.2%}, Excess={mA['excess_cagr_vs_broad_tr']:.2%}, Vol={mA['volatility']:.2%}, MaxDD={mA['max_dd']:.2%}, Sharpe={mA['sharpe_vs_broad_tr']:.2f}")
    print(f"Variant B (Investability):   CAGR={mB['cagr']:.2%}, Excess={mB['excess_cagr_vs_broad_tr']:.2%}, Vol={mB['volatility']:.2%}, MaxDD={mB['max_dd']:.2%}, Sharpe={mB['sharpe_vs_broad_tr']:.2f}")
    print("-" * 80)
    print(f"Total H0 Top30 Filtered Events: {total_h0_top30_filtered}")
    print(f"Most Filtered Tickers: {filtered_ticker_counts.most_common(5)}")
    print(f"CLASSIFICATION: {results['classification']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
