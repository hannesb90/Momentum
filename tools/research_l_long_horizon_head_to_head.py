"""
RESEARCH L: Long-Horizon Head-to-Head (2021-07-16 to 2026-07-10).
Simulates H0/V4 Champion vs V1 LambdaRank Engine & V1 Full Architecture
on clean, validated V2 data over the maximum common historical period.
"""
from __future__ import annotations
import json, math, hashlib
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import lightgbm as lgb
from sklearn.impute import SimpleImputer

V2 = Path("/home/hannesb/momentum_v2")
START_DATE = "2021-07-16"
END_DATE = "2026-07-10"
PHASE_ANCHOR_H0 = "2024-01-26"
PHASE_ANCHOR_V1 = "2024-01-26"
COST_ONEWAY = 0.002
SEED = 20260808

def finite(x):
    return None if x is None or not math.isfinite(float(x)) else float(x)

def annualized(values, periods_per_year=13):
    if not values or len(values) == 0:
        return None
    wealth = float(np.prod(1 + np.asarray(values, dtype=float)))
    return -1.0 if wealth <= 0 else wealth ** (13 / len(values)) - 1

def load_data():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    target = json.loads((V2 / "panels/target_table.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    reg = json.loads((V2 / "docs/probes/feature_registry.json").read_text())
    
    core_features = [r["id"] for r in reg["CORE"] if r.get("status") != "UTESLUTEN" and not r.get("ej_feature")]
    
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    # Precompute 13w and 52w forward returns from validated prices for IC evaluation
    series = {
        k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    def fwd_return(k, dt, weeks):
        if k not in series: return None
        ds, values = series[k]
        now = np.datetime64(dt)
        target_dt = now + np.timedelta64(7 * weeks, "D")
        i = np.searchsorted(ds, now, side="right") - 1
        j = np.searchsorted(ds, target_dt, side="right") - 1
        if i < 0 or j < 0 or j >= len(ds) or int((ds[j] - target_dt) / np.timedelta64(1, "D")) > 10:
            return None
        return float(values[j] / values[i] - 1)

    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        y13 = fwd_return(r["kod"], r["panel_date"], 13)
        x = {f: r.get(f) for f in core_features}
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y13": y13, "y52": y52, "has_fundamenta": r.get("has_fundamenta"),
            "mom_12_1": r.get("mom_12_1"), **x
        })
    df_core = pd.DataFrame(df_core)
    
    return df_core, core_features, prices, terminal

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
        by_date[r["panel_date"]].append({"kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18, "y13": r["y13"], "y52": r["y52"]})

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

def train_walkforward_lambdarank(core_df, features):
    dates = sorted(core_df.panel_date.unique())
    eval_dates = [d for d in dates if START_DATE <= d <= END_DATE]
    
    imputer = SimpleImputer(strategy="median")
    df_imp = core_df.copy()
    df_imp[features] = imputer.fit_transform(core_df[features])
    
    predictions = defaultdict(list)
    
    step_size = 13
    eval_indices = [i for i, d in enumerate(dates) if d in eval_dates]
    first_eval_idx = eval_indices[0]
    
    for i in range(first_eval_idx, len(dates), step_size):
        test_dates = dates[i : min(i + step_size, len(dates))]
        test_dates = [d for d in test_dates if d in eval_dates]
        if not test_dates: continue
        
        train_max_date = (date.fromisoformat(test_dates[0]) - timedelta(weeks=13)).isoformat()
        tr = df_imp[df_imp.panel_date <= train_max_date].sort_values("panel_date")
        ev = df_imp[df_imp.panel_date.isin(test_dates)].sort_values("panel_date")
        
        if len(tr) < 500 or len(ev) == 0: continue
        
        tr_y = tr["y52"].fillna(0.0)
        
        y_tr_rel = tr.groupby("panel_date", sort=False)["y52"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x.dropna()) >= 5 else 0
        ).fillna(0).values.astype(int)
        
        train_groups = tr.groupby("panel_date", sort=False).size().values
        
        X_tr = tr[features].values
        X_ev = ev[features].values
        
        ranker = lgb.LGBMRanker(
            n_estimators=150,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=30,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=SEED,
            n_jobs=4,
            verbosity=-1
        )
        ranker.fit(X_tr, y_tr_rel, group=train_groups)
        
        scores = ranker.predict(X_ev)
        
        for (_, r), z in zip(ev.iterrows(), scores):
            predictions[r["panel_date"]].append({
                "kod": r["kod"], "panel_date": r["panel_date"], "score": float(z),
                "y13": r["y13"], "y52": r["y52"], "mom_12_1": r["mom_12_1"]
            })
            
    for dt in predictions:
        predictions[dt].sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        
    return predictions

def execution_engine(core_df, prices, terminal):
    dates = sorted(core_df.panel_date.unique())
    next_date = dict(zip(dates, dates[1:]))
    returns, meta = {}, {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = {r["d"]: r["adj"] for r in rs}

        def first_after(boundary):
            return next((d for d in ds if d > boundary), None)

        for dt in dates:
            nd = next_date.get(dt)
            entry = first_after(dt)
            if not nd: continue
            if not entry or entry > nd:
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
        
        periods.append({"panel_date": dt, "scheduled": scheduled, "net": net, "gross": gross, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r in zip(selected, rets):
            contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

def simulate_v1_engine(rankings, returns_map, all_dates):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_V1) % 3
    previous, periods, contrib = [], [], defaultdict(float)
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 3 == anchor_parity
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
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gross = float(np.mean(rets)) if rets else 0.0
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "scheduled": scheduled, "net": net, "gross": gross, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r in zip(selected, rets):
            contrib[k] += r / len(selected)
        previous = selected
        
    return periods, contrib

def simulate_v1_full(rankings, returns_map, all_dates, prices):
    eval_dates = sorted(rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_V1) % 3
    previous, periods, contrib = [], [], defaultdict(float)
    
    rvol_map = {}
    for kod, rs in prices.items():
        if len(rs) < 26: continue
        adj = pd.Series([r["adj"] for r in rs], index=[r["d"] for r in rs])
        ret = adj.pct_change()
        vol = ret.rolling(26).std() * np.sqrt(52)
        rvol_map[kod] = vol.to_dict()

    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 3 == anchor_parity
        universe = rankings[dt]
        universe_codes = {r["kod"] for r in universe}
        
        if scheduled or not previous:
            gated = [r for r in universe if r.get("mom_12_1") is not None and r["mom_12_1"] > 0.10]
            if len(gated) >= 5:
                candidates = gated[:30]
            else:
                candidates = universe[:30]
            selected = [r["kod"] for r in candidates]
        else:
            selected = [k for k in previous if k in universe_codes]
            if len(selected) < 30:
                fill = [r["kod"] for r in universe if r["kod"] not in selected]
                selected.extend(fill[: 30 - len(selected)])
                
        turnover = 0.0 if not previous else 1.0 - len(set(selected) & set(previous)) / len(selected)
        
        vols = [rvol_map.get(k, {}).get(dt, 0.25) or 0.25 for k in selected]
        inv_vols = [1.0 / max(v, 0.05) for v in vols]
        inv_weights = np.array(inv_vols) / sum(inv_vols)
        eq_weights = np.array([1.0 / len(selected)] * len(selected))
        weights = 0.5 * eq_weights + 0.5 * inv_weights
        
        rets = [returns_map.get((k, dt), 0.0) for k in selected]
        gross = float(np.sum(np.array(rets) * weights))
        net = gross - COST_ONEWAY * turnover
        bench = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe])) if universe else 0.0
        
        periods.append({"panel_date": dt, "scheduled": scheduled, "net": net, "gross": gross, "bench": bench, "excess": net - bench, "turnover": turnover, "selected": selected})
        for k, r, w in zip(selected, rets, weights):
            contrib[k] += r * w
        previous = selected
        
    return periods, contrib

def ic_calc(rankings, target_col):
    ics, top_ics = [], []
    for dt, rs in sorted(rankings.items()):
        if dt < START_DATE or dt > END_DATE: continue
        valid = [r for r in rs if r.get(target_col) is not None]
        if len(valid) > 5:
            sc = np.array([r["score"] for r in valid])
            ys = np.array([r[target_col] for r in valid])
            if len(np.unique(sc)) > 1 and len(np.unique(ys)) > 1:
                ics.append(spearmanr(sc, ys).statistic)
            top = valid[:30]
            top_sc = np.array([r["score"] for r in top])
            top_ys = np.array([r[target_col] for r in top])
            if len(np.unique(top_sc)) > 1 and len(np.unique(top_ys)) > 1:
                top_ics.append(spearmanr(top_sc, top_ys).statistic)
    return {
        "mean_ic": finite(np.mean(ics)) if ics else None,
        "median_ic": finite(np.median(ics)) if ics else None,
        "positive_share": finite(np.mean(np.array(ics) > 0)) if ics else None,
        "mean_top30_ic": finite(np.mean(top_ics)) if top_ics else None,
    }

def evaluate_metrics(periods, rankings):
    nr = [p["net"] for p in periods]
    br = [p["bench"] for p in periods]
    ex = [p["excess"] for p in periods]
    
    cagr_m = annualized(nr, 13)
    bench_m = annualized(br, 13)
    excess_m = cagr_m - bench_m if cagr_m and bench_m else None
    sharpe_m = finite(np.mean(ex) / np.std(ex, ddof=1) * math.sqrt(13)) if len(ex) > 1 and np.std(ex, ddof=1) > 0 else None
    
    wealth = np.cumprod(1 + np.array(nr))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    max_dd = finite(dd.min())
    vol = finite(np.std(nr, ddof=1) * math.sqrt(13))
    turn = finite(np.mean([p["turnover"] for p in periods]))
    
    years = sorted({p["panel_date"][:4] for p in periods})
    yr_stats = {}
    for yr in years:
        sub = [p for p in periods if p["panel_date"].startswith(yr)]
        y_nr = [p["net"] for p in sub]
        y_br = [p["bench"] for p in sub]
        yr_stats[yr] = {
            "cagr": annualized(y_nr, 13),
            "bench_cagr": annualized(y_br, 13),
            "excess": annualized(y_nr, 13) - annualized(y_br, 13) if annualized(y_nr, 13) and annualized(y_br, 13) else None
        }
        
    r12, r24 = [], []
    for i in range(13, len(periods) + 1):
        win = [p["net"] for p in periods[i-13:i]]
        bwin = [p["bench"] for p in periods[i-13:i]]
        c = annualized(win, 13)
        bc = annualized(bwin, 13)
        if c is not None and bc is not None:
            r12.append(c - bc)
    for i in range(26, len(periods) + 1):
        win = [p["net"] for p in periods[i-26:i]]
        bwin = [p["bench"] for p in periods[i-26:i]]
        c = annualized(win, 13)
        bc = annualized(bwin, 13)
        if c is not None and bc is not None:
            r24.append(c - bc)

    r12_stats = {
        "mean_excess": finite(np.mean(r12)) if r12 else None,
        "median_excess": finite(np.median(r12)) if r12 else None,
        "min_excess": finite(np.min(r12)) if r12 else None,
        "max_excess": finite(np.max(r12)) if r12 else None,
        "positive_share": finite(np.mean(np.array(r12) > 0)) if r12 else None
    }
    
    r24_stats = {
        "mean_excess": finite(np.mean(r24)) if r24 else None,
        "median_excess": finite(np.median(r24)) if r24 else None,
        "min_excess": finite(np.min(r24)) if r24 else None,
        "max_excess": finite(np.max(r24)) if r24 else None,
        "positive_share": finite(np.mean(np.array(r24) > 0)) if r24 else None
    }

    return {
        "cagr": cagr_m, "bench_cagr": bench_m, "excess_cagr": excess_m,
        "sharpe": sharpe_m, "volatility": vol, "max_dd": max_dd, "turnover": turn,
        "calendar_years": yr_stats, "rolling_12m": r12_stats, "rolling_24m": r24_stats,
        "ic13": ic_calc(rankings, "y13"),
        "ic52": ic_calc(rankings, "y52")
    }

def concentration_analysis(contrib, returns_map, rankings, periods):
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
        "cagr_leave_top1": leave_out(set(top1)),
        "cagr_leave_top3": leave_out(set(top3)),
        "cagr_leave_top5": leave_out(set(top5)),
        "top1_contrib_share": finite(ranked[0][1] / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
        "top3_contrib_share": finite(sum(v for _, v in ranked[:3]) / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
        "top5_contrib_share": finite(sum(v for _, v in ranked[:5]) / sum(v for _, v in ranked)) if ranked and sum(v for _, v in ranked) > 0 else None,
    }

def main():
    print("=" * 80)
    print("RESEARCH L: LONG-HORIZON HEAD-TO-HEAD AUDIT & SIMULATION")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, core_features, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving H0 scores (50/50 12m+18m momentum)...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Training Walk-Forward V1 LambdaRank on V2 data...")
    v1_rankings = train_walkforward_lambdarank(core_df, core_features)
    
    print("3. Simulating H0/V4 Champion...")
    h0_periods, h0_contrib = simulate_h0(h0_rankings, returns_map, all_dates)
    
    print("4. Simulating V1 LambdaRank Engine (Top 30 Equal Weight, 13w Rebalance)...")
    v1_eng_periods, v1_eng_contrib = simulate_v1_engine(v1_rankings, returns_map, all_dates)
    
    print("5. Simulating V1 Full Architecture (Inverse Vol Sizing, Momentum Gate, Vol Target)...")
    v1_full_periods, v1_full_contrib = simulate_v1_full(v1_rankings, returns_map, all_dates, prices)
    
    # Evaluate
    h0_metrics = evaluate_metrics(h0_periods, h0_rankings)
    v1_eng_metrics = evaluate_metrics(v1_eng_periods, v1_rankings)
    v1_full_metrics = evaluate_metrics(v1_full_periods, v1_rankings)
    
    h0_conc = concentration_analysis(h0_contrib, returns_map, h0_rankings, h0_periods)
    v1_eng_conc = concentration_analysis(v1_eng_contrib, returns_map, v1_rankings, v1_eng_periods)
    v1_full_conc = concentration_analysis(v1_full_contrib, returns_map, v1_rankings, v1_full_periods)
    
    results = {
        "period": {"start": START_DATE, "end": END_DATE, "n_dates": len(h0_periods)},
        "h0_v4_champion": {"metrics": h0_metrics, "concentration": h0_conc},
        "v1_lambdarank_engine": {"metrics": v1_eng_metrics, "concentration": v1_eng_conc},
        "v1_full_architecture": {"metrics": v1_full_metrics, "concentration": v1_full_conc},
    }
    
    out_file = V2 / "research_k/research_l_long_horizon_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY (2021-07-16 to 2026-07-10)")
    print("=" * 80)
    print(f"H0/V4 Champion:       CAGR={h0_metrics['cagr']:.1%}, Bench={h0_metrics['bench_cagr']:.1%}, Excess={h0_metrics['excess_cagr']:.1%}, Sharpe={h0_metrics['sharpe']:.2f}, MaxDD={h0_metrics['max_dd']:.1%}")
    print(f"V1 LambdaRank Engine: CAGR={v1_eng_metrics['cagr']:.1%}, Bench={v1_eng_metrics['bench_cagr']:.1%}, Excess={v1_eng_metrics['excess_cagr']:.1%}, Sharpe={v1_eng_metrics['sharpe']:.2f}, MaxDD={v1_eng_metrics['max_dd']:.1%}")
    print(f"V1 Full Architecture: CAGR={v1_full_metrics['cagr']:.1%}, Bench={v1_full_metrics['bench_cagr']:.1%}, Excess={v1_full_metrics['excess_cagr']:.1%}, Sharpe={v1_full_metrics['sharpe']:.2f}, MaxDD={v1_full_metrics['max_dd']:.1%}")
    print("=" * 80)

if __name__ == "__main__":
    main()
