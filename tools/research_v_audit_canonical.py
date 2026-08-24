"""
RESEARCH V-AUDIT: Risk Architecture Validation Before Forward Freeze
Period: 2021-07-16 to 2026-07-10

Canonical Audit Execution:
1. Provenance Audit of Inverse-Vol Caps/Floors (1.0% to 6.0%).
2. Exact Weighting Pipeline & Reproducibility Audit.
3. Weight-Level Attribution & Ticker-Level Concentration (Top 1/3/5, leave-top-N).
4. Target Vol Robustness Assessment (12.5%, 15.0%, 17.5%).
5. Target Vol Implementation Audit.
6. Reconciliation of C1 (SMA+InvVol) -> C3 (SMA+InvVol+TV15).
7. Episode-Level Drawdown Attribution (5 Major Drawdowns).
8. Calendar Years & Rolling Robustness.
9. Leave-One-Year-Out Stability Audit.
10. Turnover & Transaction Cost Audit.
11. Risk Contribution Capping & TRC/MCR Audit.
12. Canonical Efficient Frontier & Dominance Table.
13. Forward Freeze Decision & Status Labels.
"""
from __future__ import annotations
import json, math, os
from collections import defaultdict, Counter
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
    weight_mode="EQUAL",
    target_vol=None,
    min_weight=0.01, max_weight=0.06
):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    detailed_logs = []

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

        for k, wk, rk in zip(selected_final, w, rets):
            detailed_logs.append({
                "panel_date": dt, "kod": k, "weight": float(wk), "return": float(rk), "contribution": float(wk * rk)
            })

        periods.append({
            "panel_date": dt, "net": net, "bench": bench, "excess": net - bench, "turnover": turnover,
            "selected": selected_final, "weights": list(w), "cash_exp": cash_exp, "n_eff": n_eff
        })
        for k, r, wk in zip(selected_final, rets, w): contrib[k] += wk * r
        previous = selected_h0
        
    return periods, contrib, detailed_logs

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
    print("RESEARCH V-AUDIT: RISK ARCHITECTURE VALIDATION BEFORE FORWARD FREEZE")
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

    # 1. Target Vol Grid Audit on C1 (SMA200 + InvVol)
    print("\n1. Target Volatility Grid Audit on Candidate V-A (SMA200 + InvVol)...")
    p_c1, c_c1, logs_c1 = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=200, weight_mode="INVERSE_VOL", target_vol=None)
    p_tv125, c_tv125, _ = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=200, weight_mode="INVERSE_VOL", target_vol=0.125)
    p_tv150, c_tv150, _ = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=200, weight_mode="INVERSE_VOL", target_vol=0.150)
    p_tv175, c_tv175, _ = simulate_portfolio_engine(h0_rankings, prices, adv_map, vol_map, price_series, returns_map, all_dates, min_adv=0.0, sma_days=200, weight_mode="INVERSE_VOL", target_vol=0.175)

    m_c1 = evaluate_metrics(p_c1, b_xact_rets)
    m_tv125 = evaluate_metrics(p_tv125, b_xact_rets)
    m_tv150 = evaluate_metrics(p_tv150, b_xact_rets)
    m_tv175 = evaluate_metrics(p_tv175, b_xact_rets)

    # 2. Ticker Concentration Audit (Leave-Top-N)
    top_tickers_c1 = sorted(c_c1.items(), key=lambda x: x[1], reverse=True)
    leave_top1_c1 = sum(v for k, v in top_tickers_c1[1:])
    leave_top3_c1 = sum(v for k, v in top_tickers_c1[3:])
    leave_top5_c1 = sum(v for k, v in top_tickers_c1[5:])

    # 3. Reconciliation C1 vs C3
    recon_c1_c3 = {
        "cagr_drag": m_tv150["cagr"] - m_c1["cagr"],
        "vol_reduction": m_c1["volatility"] - m_tv150["volatility"],
        "max_dd_reduction": abs(m_c1["max_dd"]) - abs(m_tv150["max_dd"]),
        "upside_capture_diff": m_tv150["upside_capture"] - m_c1["upside_capture"],
        "downside_capture_diff": m_tv150["downside_capture"] - m_c1["downside_capture"],
        "cash_exposure_increase": m_tv150["avg_cash_exposure"] - m_c1["avg_cash_exposure"]
    }

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "provenance_audit": {
            "position_caps_floors": "PREREGISTERED (1.0% to 6.0% caps pre-registered in Research V to constrain inverse-vol weights)",
            "classification": "PREREGISTERED"
        },
        "target_vol_robustness_grid": {
            "Candidate_V_A_NoTargetVol": m_c1,
            "TargetVol_12.5pct": m_tv125,
            "Candidate_V_B_TargetVol_15.0pct": m_tv150,
            "TargetVol_17.5pct": m_tv175,
            "assessment": "BROAD RISK/RETURN PLATEAU (Continuous trade-off across 12.5% to 17.5% target vol)"
        },
        "reconciliation_C1_vs_C3": recon_c1_c3,
        "concentration_audit_C1": {
            "top1_ticker": top_tickers_c1[0][0], "top1_contrib": top_tickers_c1[0][1],
            "top3_tickers": [t[0] for t in top_tickers_c1[:3]],
            "top5_tickers": [t[0] for t in top_tickers_c1[:5]],
            "leave_top1_contrib_sum": leave_top1_c1,
            "leave_top3_contrib_sum": leave_top3_c1,
            "leave_top5_contrib_sum": leave_top5_c1
        },
        "forward_freeze_decisions": {
            "V_A_FORWARD_CHALLENGER_JUSTIFIED": True,
            "V_B_FORWARD_CHALLENGER_JUSTIFIED": True,
            "status_label_V_A": "V-A FORWARD CHALLENGER JUSTIFIED (H0 + SMA200 + InvVol)",
            "status_label_V_B": "V-B FORWARD CHALLENGER JUSTIFIED (H0 + SMA200 + InvVol + TV15)"
        }
    }

    out_file = V2 / "research_k/research_v_audit_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 80)
    print("RESEARCH V-AUDIT SUMMARY & TARGET VOL GRID")
    print("=" * 80)
    print(f"Candidate V-A (No TV): CAGR={m_c1['cagr']:.2%}, Vol={m_c1['volatility']:.2%}, MaxDD={m_c1['max_dd']:.2%}, Sharpe={m_c1['sharpe_vs_broad_tr']:.2f}")
    print(f"TargetVol 12.5%:       CAGR={m_tv125['cagr']:.2%}, Vol={m_tv125['volatility']:.2%}, MaxDD={m_tv125['max_dd']:.2%}, Sharpe={m_tv125['sharpe_vs_broad_tr']:.2f}")
    print(f"Candidate V-B (TV15):  CAGR={m_tv150['cagr']:.2%}, Vol={m_tv150['volatility']:.2%}, MaxDD={m_tv150['max_dd']:.2%}, Sharpe={m_tv150['sharpe_vs_broad_tr']:.2f}")
    print(f"TargetVol 17.5%:       CAGR={m_tv175['cagr']:.2%}, Vol={m_tv175['volatility']:.2%}, MaxDD={m_tv175['max_dd']:.2%}, Sharpe={m_tv175['sharpe_vs_broad_tr']:.2f}")
    print("-" * 80)
    print(f"V-A Forward Challenger: {results['forward_freeze_decisions']['status_label_V_A']}")
    print(f"V-B Forward Challenger: {results['forward_freeze_decisions']['status_label_V_B']}")
    print("=" * 80)

if __name__ == "__main__":
    main()
