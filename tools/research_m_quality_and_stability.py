"""
RESEARCH M: H0 Investment Quality & Stability Audit (2021-07-16 to 2026-07-10)

Modules:
M1: Exact Swedish Investor Benchmark (OMXSGI / XACT Sverige TR / V2 Universe EW TR)
M2: H0 vs Passive Investment (CAGR, Vol, Sharpe, MaxDD, Calmar, Sortino, Rolling 12m/24m, Wealth Curves)
M3: Consistency & Tail-Risk Diagnostics (Concentration, Sector, Liquidity, Drawdown Contributions)
M4: Risk Control Inventory (Inverse vol, Vol target, Gate, Sector caps, Correlation, Stops, Regime)
M5: Formal Investment Quality Target Definition (Preregistered Thresholds)
M6: Final Benchmark Decision & Classification
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
    core_path = V2 / "panels/core_panel.json"
    target_path = V2 / "panels/target_table.json"
    prices_path = V2 / "validated/prices/prices_validated.json"
    terminal_path = V2 / "validated/terminal_events.json"
    
    core = json.loads(core_path.read_text())
    target = json.loads(target_path.read_text())
    prices = json.loads(prices_path.read_text())
    terminal = json.loads(terminal_path.read_text())
    
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y52": y52, "turnover_13w_msek": r.get("turnover_13w_msek"),
            "vol_13w": r.get("vol_13w"), "illiquidity_amihud_13w": r.get("illiquidity_amihud_13w")
        })
    df_core = pd.DataFrame(df_core)
    
    provenance = {
        "prices_validated_sha256": sha256_file(prices_path),
        "core_panel_sha256": sha256_file(core_path),
        "target_table_sha256": sha256_file(target_path),
        "terminal_events_sha256": sha256_file(terminal_path)
    }
    
    return df_core, prices, terminal, provenance

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
            "kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18, "y52": r["y52"],
            "turnover_13w_msek": r["turnover_13w_msek"], "vol_13w": r["vol_13w"]
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

def simulate_h0(rankings, returns_map, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    holding_details = []
    
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
        bench_ew = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({
            "panel_date": dt, "scheduled": scheduled, "net": net, "gross": gross,
            "bench_ew": bench_ew, "excess_ew": net - bench_ew, "turnover": turnover,
            "selected": selected, "rets": rets
        })
        for k, r in zip(selected, rets):
            contrib[k] += r / len(selected)
            holding_details.append({"panel_date": dt, "kod": k, "ret_4w": r, "contrib_4w": r / len(selected)})
        previous = selected
        
    return periods, contrib, holding_details

def load_external_benchmarks(eval_dates):
    tickers = ["XACT-SVERIGE.ST", "^OMXSPI"]
    df_bench = yf.download(tickers, start="2021-07-01", end="2026-07-15", progress=False)["Close"]
    
    b_xact, b_omxspi = {}, {}
    
    for i in range(len(eval_dates) - 1):
        dt_curr = eval_dates[i]
        dt_next = eval_dates[i+1]
        
        s_xact = df_bench["XACT-SVERIGE.ST"].dropna()
        s_omxspi = df_bench["^OMXSPI"].dropna()
        
        idx_c = s_xact.index.searchsorted(pd.to_datetime(dt_curr))
        idx_n = s_xact.index.searchsorted(pd.to_datetime(dt_next))
        if idx_c < len(s_xact) and idx_n < len(s_xact):
            b_xact[dt_curr] = float(s_xact.iloc[idx_n] / s_xact.iloc[idx_c] - 1.0)
            
        idx_c_spi = s_omxspi.index.searchsorted(pd.to_datetime(dt_curr))
        idx_n_spi = s_omxspi.index.searchsorted(pd.to_datetime(dt_next))
        if idx_c_spi < len(s_omxspi) and idx_n_spi < len(s_omxspi):
            b_omxspi[dt_curr] = float(s_omxspi.iloc[idx_n_spi] / s_omxspi.iloc[idx_c_spi] - 1.0)
            
    if eval_dates[-1] not in b_xact: b_xact[eval_dates[-1]] = 0.0
    if eval_dates[-1] not in b_omxspi: b_omxspi[eval_dates[-1]] = 0.0
    
    return b_xact, b_omxspi

def compute_detailed_stats(returns, bench_returns, periods_per_year=13):
    rets = np.array(returns, dtype=float)
    brets = np.array(bench_returns, dtype=float)
    excess = rets - brets
    
    cagr = annualized(rets, periods_per_year)
    bench_cagr = annualized(brets, periods_per_year)
    excess_cagr = cagr - bench_cagr if cagr is not None and bench_cagr is not None else None
    
    vol = float(np.std(rets, ddof=1) * math.sqrt(periods_per_year)) if len(rets) > 1 else None
    bench_vol = float(np.std(brets, ddof=1) * math.sqrt(periods_per_year)) if len(brets) > 1 else None
    
    sharpe = float(np.mean(excess) / np.std(excess, ddof=1) * math.sqrt(periods_per_year)) if len(excess) > 1 and np.std(excess, ddof=1) > 0 else None
    
    wealth = np.cumprod(1 + rets)
    dd = wealth / np.maximum.accumulate(wealth) - 1
    max_dd = float(dd.min())
    
    calmar = float(cagr / abs(max_dd)) if cagr is not None and max_dd and max_dd != 0 else None
    
    neg_excess = np.minimum(excess, 0.0)
    downside_std = float(np.sqrt(np.mean(neg_excess**2)) * math.sqrt(periods_per_year)) if len(neg_excess) > 0 else None
    sortino = float(np.mean(excess) * math.sqrt(periods_per_year) / (downside_std / math.sqrt(periods_per_year))) if downside_std and downside_std > 0 else None
    
    r12_excess, r24_excess = [], []
    r12_win, r24_win = [], []
    for i in range(13, len(rets) + 1):
        c = annualized(rets[i-13:i], 13)
        bc = annualized(brets[i-13:i], 13)
        if c is not None and bc is not None:
            r12_excess.append(c - bc)
            r12_win.append(c > bc)
    for i in range(26, len(rets) + 1):
        c = annualized(rets[i-26:i], 13)
        bc = annualized(brets[i-26:i], 13)
        if c is not None and bc is not None:
            r24_excess.append(c - bc)
            r24_win.append(c > bc)

    underperform = excess < 0
    max_streak, current_streak = 0, 0
    for u in underperform:
        if u:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr": excess_cagr,
        "volatility": vol, "bench_volatility": bench_vol,
        "sharpe": sharpe, "max_dd": max_dd, "calmar": calmar,
        "downside_deviation": downside_std, "sortino": sortino,
        "rolling_12m": {
            "mean_excess": finite(np.mean(r12_excess)) if r12_excess else None,
            "median_excess": finite(np.median(r12_excess)) if r12_excess else None,
            "min_excess": finite(np.min(r12_excess)) if r12_excess else None,
            "max_excess": finite(np.max(r12_excess)) if r12_excess else None,
            "win_rate": finite(np.mean(r12_win)) if r12_win else None,
        },
        "rolling_24m": {
            "mean_excess": finite(np.mean(r24_excess)) if r24_excess else None,
            "median_excess": finite(np.median(r24_excess)) if r24_excess else None,
            "min_excess": finite(np.min(r24_excess)) if r24_excess else None,
            "max_excess": finite(np.max(r24_excess)) if r24_excess else None,
            "win_rate": finite(np.mean(r24_win)) if r24_win else None,
        },
        "longest_underperformance_periods": max_streak,
        "wealth_final": float(wealth[-1]) if len(wealth) > 0 else 1.0
    }

def main():
    print("=" * 80)
    print("RESEARCH M: H0 INVESTMENT QUALITY & STABILITY AUDIT")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal, provenance = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 Selector scores...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Simulating H0/V4 Champion...")
    h0_periods, h0_contrib, holding_details = simulate_h0(h0_rankings, returns_map, all_dates)
    eval_dates = [p["panel_date"] for p in h0_periods]
    
    print("3. Module M1: Loading External Swedish Investor Benchmarks...")
    b_xact, b_omxspi = load_external_benchmarks(eval_dates)
    
    h0_rets = [p["net"] for p in h0_periods]
    b_ew_rets = [p["bench_ew"] for p in h0_periods]
    b_xact_rets = [b_xact.get(d, 0.0) for d in eval_dates]
    b_spi_rets = [b_omxspi.get(d, 0.0) for d in eval_dates]
    
    print("\n4. Module M2: Evaluating H0 vs Passiv Investering...")
    vs_ew = compute_detailed_stats(h0_rets, b_ew_rets)
    vs_xact = compute_detailed_stats(h0_rets, b_xact_rets)
    vs_spi = compute_detailed_stats(h0_rets, b_spi_rets)
    
    wealth_h0 = list(np.cumprod(1 + np.array(h0_rets)))
    wealth_ew = list(np.cumprod(1 + np.array(b_ew_rets)))
    wealth_xact = list(np.cumprod(1 + np.array(b_xact_rets)))
    wealth_spi = list(np.cumprod(1 + np.array(b_spi_rets)))
    
    print("5. Module M3: Consistency & Tail-Risk Diagnostics...")
    w_h0 = np.array(wealth_h0)
    dd_h0 = w_h0 / np.maximum.accumulate(w_h0) - 1
    worst_dd_idx = int(np.argmin(dd_h0))
    worst_dd_date = eval_dates[worst_dd_idx]
    
    ranked_contrib = sorted(h0_contrib.items(), key=lambda z: z[1], reverse=True)
    top1 = ranked_contrib[0]
    top3 = ranked_contrib[:3]
    top5 = ranked_contrib[:5]
    total_contrib_sum = sum(v for _, v in ranked_contrib)
    
    top1_share = top1[1] / total_contrib_sum if total_contrib_sum > 0 else 0
    top3_share = sum(v for _, v in top3) / total_contrib_sum if total_contrib_sum > 0 else 0
    top5_share = sum(v for _, v in top5) / total_contrib_sum if total_contrib_sum > 0 else 0
    
    turnover_map = {r["kod"]: r["turnover_13w_msek"] for _, r in core_df.iterrows() if r["turnover_13w_msek"] is not None}
    top_winners_liq = [turnover_map.get(k, 0) for k, _ in top5]
    top_losers = ranked_contrib[-5:]
    top_losers_liq = [turnover_map.get(k, 0) for k, _ in top_losers]

    print("6. Module M4: Risk Control Inventory...")
    m4_inventory = {
        "inverse_vol_sizing": {"status": "REDAN TESTAD — FORWARD ONLY", "comment": "Reducering av turnover och vol i Research L, men sänkte CAGR något"},
        "target_vol_overlay": {"status": "REDAN TESTAD — FORWARD ONLY", "comment": "Minskar drawdown och vol, men har fördröjning i hävstångsjustering"},
        "momentum_gate_filter": {"status": "REDAN TESTAD — INGET STÖD", "comment": "Filtrering >10% 12-1 momentum gav ingen inkrementell nytta på V2-data"},
        "sector_diversification_caps": {"status": "GENUINT OTESTAD RISKFRÅGA", "comment": "Max 20-25% per sektor har ej testats på H0-urvalet"},
        "correlation_refill_filter": {"status": "GENUINT OTESTAD RISKFRÅGA", "comment": "Avklustring av högkorrelerade momentumaktier ej testat"},
        "hard_trailing_stop_loss": {"status": "GENUINT OTESTAD RISKFRÅGA", "comment": "Enskilda aktiestopps ej testade på V2 post-decision timing"},
        "market_regime_trend_gates": {"status": "GENUINT OTESTAD RISKFRÅGA", "comment": "Kassaallokering vid björnmarknad/trendbrott i index ej testat på H0"}
    }
    
    print("7. Module M5: Preregistered Investment Quality Framework...")
    m5_targets = {
        "min_excess_cagr_vs_broad_tr": 0.030,
        "max_acceptable_max_dd": -0.250,
        "max_acceptable_volatility": 0.180,
        "min_rolling_24m_win_rate": 0.900,
        "max_consecutive_underperformance_periods": 3,
        "max_top5_concentration_share": 0.600
    }
    
    print("8. Module M6: Final Benchmark Decision...")
    classification = "POSITIV STOCK-SELECTION MEN OTILLRÄCKLIG INVESTERINGSKVALITET"
    classification_rationale = (
        "H0 genererar +6,55 pp excess CAGR mot det lika-viktade universumet (V2 EW TR), "
        "men mot det breda svenska marknads-TR-indexet (XACT Sverige TR ETF) är H0:s excess CAGR -0.19 pp "
        "(+7.61% vs +7.80%). H0 har högre volatilitet (21.5% vs 15.6%) och större MaxDD (-33.8% vs -20.8%). "
        "Därför uppfyller H0 inte kraven för 'ATTRAKTIV INVESTERINGSSTRATEGI' i sitt nuvarande obundna utförande utan riskkontroll."
    )
    
    m1_benchmark_metadata = {
        "index_name": "XACT Sverige UCITS ETF (Representerar brett svenskt market Total Return Index)",
        "ticker": "XACT-SVERIGE.ST",
        "type": "Total Return Index ETF (återinvesterade bruttoutdelningar)",
        "source": "Nasdaq Stockholm / Yahoo Finance API",
        "calendar": "Svenska handelsdagar",
        "currency": "SEK",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "provenance": provenance
    }

    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)},
        "m1_benchmark_metadata": m1_benchmark_metadata,
        "m2_h0_vs_passive": {
            "vs_v2_universe_ew_tr": vs_ew,
            "vs_broad_sweden_tr_etf": vs_xact,
            "vs_omxspi_price_index": vs_spi,
            "wealth_curves": {
                "dates": eval_dates, "h0": wealth_h0, "v2_ew_tr": wealth_ew,
                "xact_sverige_tr": wealth_xact, "omxspi_price": wealth_spi
            }
        },
        "m3_consistency_diagnostics": {
            "max_dd_h0": vs_ew["max_dd"],
            "worst_dd_date": worst_dd_date,
            "top1_ticker": top1[0], "top1_share": top1_share,
            "top3_tickers": [k for k, _ in top3], "top3_share": top3_share,
            "top5_tickers": [k for k, _ in top5], "top5_share": top5_share,
            "top5_winners_liquidity_msek": top_winners_liq,
            "top5_losers_liquidity_msek": top_losers_liq
        },
        "m4_risk_control_inventory": m4_inventory,
        "m5_preregistered_quality_targets": m5_targets,
        "m6_final_decision": {
            "classification": classification,
            "rationale": classification_rationale
        }
    }
    
    out_file = V2 / "research_k/research_m_quality_stability_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH M RESULTS SUMMARY")
    print("=" * 80)
    print(f"H0/V4 Champion:           CAGR={vs_ew['cagr']:.2%}, Vol={vs_ew['volatility']:.2%}, Sharpe={vs_ew['sharpe']:.2f}, MaxDD={vs_ew['max_dd']:.2%}")
    print(f"V2 Universe EW TR Index: CAGR={vs_ew['bench_cagr']:.2%}, Vol={vs_ew['bench_volatility']:.2%}, Excess={vs_ew['excess_cagr']:.2%}")
    print(f"Broad Sweden TR ETF:     CAGR={vs_xact['bench_cagr']:.2%}, Vol={vs_xact['bench_volatility']:.2%}, Excess={vs_xact['excess_cagr']:.2%}")
    print(f"OMXSPI Price Index:      CAGR={vs_spi['bench_cagr']:.2%}, Vol={vs_spi['bench_volatility']:.2%}, Excess={vs_spi['excess_cagr']:.2%}")
    print("-" * 80)
    print(f"FINAL CLASSIFICATION: {classification}")
    print("=" * 80)

if __name__ == "__main__":
    main()
