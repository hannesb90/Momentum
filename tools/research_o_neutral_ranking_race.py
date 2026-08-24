"""
RESEARCH O: Neutral Ranking Model Race (2021-07-16 to 2026-07-10)

Preregistered candidates:
A. Frozen H0 (0.5 * rank(12m) + 0.5 * rank(18m))
B. LightGBM LambdaRank (LGBMRanker, qcut(5) labels, panel query groups)
C. XGBoost Ranker (XGBRanker, objective="rank:ndcg", qcut(5) labels, panel query groups)
D. CatBoost Ranker (CatBoostRanker, loss_function="YetiRank", panel query groups)
E. Linear Pairwise Ranker (Pairwise difference Hinge-loss Linear Model)

All models evaluated on identical PIT-safe CORE features, 52-week embargo walk-forward,
V4 post-decision execution, Top 30 equal weight, 8-week rebalance, 20 bp cost.
"""
from __future__ import annotations
import json, math, hashlib, os
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier

import lightgbm as lgb
import xgboost as xgb
import catboost as cb
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

def ndcg_at_k(y_true, y_score, k=30):
    idx = np.argsort(y_score)[::-1][:k]
    y_true_k = np.asarray(y_true)[idx]
    gains = 2**y_true_k - 1
    discounts = np.log2(np.arange(2, len(y_true_k) + 2))
    dcg = np.sum(gains / discounts)
    
    ideal_gains = 2**np.sort(y_true)[::-1][:k] - 1
    idcg = np.sum(ideal_gains / discounts)
    return float(dcg / idcg) if idcg > 0 else 0.0

def load_data():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    target = json.loads((V2 / "panels/target_table.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    reg = json.loads((V2 / "docs/probes/feature_registry.json").read_text())
    
    core_features = [r["id"] for r in reg["CORE"] if r.get("status") != "UTESLUTEN" and not r.get("ej_feature")]
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        x = {f: r.get(f) for f in core_features}
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y52": y52, **x
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
        by_date[r["panel_date"]].append({"kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18, "y52": r["y52"]})

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

def train_walkforward_ranker(core_df, features, model_type="lgb"):
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
        
        train_max_date = (date.fromisoformat(test_dates[0]) - timedelta(weeks=52)).isoformat()
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
        
        if model_type == "lgb":
            ranker = lgb.LGBMRanker(
                n_estimators=100, learning_rate=0.03, num_leaves=31, min_child_samples=30,
                reg_alpha=0.1, reg_lambda=1.0, random_state=SEED, n_jobs=4, verbosity=-1
            )
            ranker.fit(X_tr, y_tr_rel, group=train_groups)
            scores = ranker.predict(X_ev)
            
        elif model_type == "xgb":
            ranker = xgb.XGBRanker(
                n_estimators=100, learning_rate=0.03, max_depth=4, subsample=0.8,
                colsample_bytree=0.8, objective="rank:ndcg", random_state=SEED, n_jobs=4
            )
            ranker.fit(X_tr, y_tr_rel, group=train_groups)
            scores = ranker.predict(X_ev)
            
        elif model_type == "cat":
            group_ids = []
            for gid, sz in enumerate(train_groups): group_ids.extend([gid] * sz)
            train_pool = cb.Pool(data=X_tr, label=y_tr_rel, group_id=group_ids)
            ranker = cb.CatBoostRanker(
                iterations=100, learning_rate=0.03, depth=4, loss_function="YetiRank",
                random_seed=SEED, verbose=False, thread_count=4
            )
            ranker.fit(train_pool)
            scores = ranker.predict(X_ev)
            
        elif model_type == "linear":
            pairs_X, pairs_y = [], []
            for dt_g, group in tr.groupby("panel_date", sort=False):
                g_X = group[features].values
                g_y = group["y52"].values
                if len(g_y) < 10 or np.all(g_y == g_y[0]): continue
                p80 = np.percentile(g_y, 80)
                p20 = np.percentile(g_y, 20)
                top_idx = np.where(g_y >= p80)[0]
                bot_idx = np.where(g_y <= p20)[0]
                for ti in top_idx[:15]:
                    for bi in bot_idx[:15]:
                        pairs_X.append(g_X[ti] - g_X[bi])
                        pairs_y.append(1)
            
            if len(pairs_X) > 0:
                pairs_X = np.array(pairs_X)
                pairs_y = np.array(pairs_y)
                clf = SGDClassifier(loss="hinge", alpha=0.01, random_state=SEED)
                clf.fit(pairs_X, pairs_y)
                scores = clf.decision_function(X_ev)
            else:
                scores = np.zeros(len(X_ev))

        for (_, r), z in zip(ev.iterrows(), scores):
            predictions[r["panel_date"]].append({
                "kod": r["kod"], "panel_date": r["panel_date"], "score": float(z),
                "y52": r["y52"]
            })
            
    for dt in predictions:
        predictions[dt].sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        
    return predictions

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

def simulate_h0_engine(selector_rankings, returns_map, all_dates):
    eval_dates = sorted(selector_rankings.keys())
    anchor_parity = all_dates.index(PHASE_ANCHOR_H0) % 2
    previous, periods, contrib = [], [], defaultdict(float)
    
    for dt in eval_dates:
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = selector_rankings[dt]
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

def ic_and_ndcg_calc(rankings):
    ics, top30_ics, top50_ics = [], [], []
    ndcg30s, ndcg50s = [], []
    prev_ranks = {}
    stabilities = []
    
    for dt, rs in sorted(rankings.items()):
        if dt < START_DATE or dt > END_DATE: continue
        valid = [r for r in rs if r.get("y52") is not None]
        if len(valid) > 5:
            sc = np.array([r["score"] for r in valid])
            ys = np.array([r["y52"] for r in valid])
            if len(np.unique(sc)) > 1 and len(np.unique(ys)) > 1:
                ics.append(spearmanr(sc, ys).statistic)
                
            top30 = valid[:30]
            if len(np.unique([r["score"] for r in top30])) > 1 and len(np.unique([r["y52"] for r in top30])) > 1:
                top30_ics.append(spearmanr([r["score"] for r in top30], [r["y52"] for r in top30]).statistic)
                
            top50 = valid[:50]
            if len(np.unique([r["score"] for r in top50])) > 1 and len(np.unique([r["y52"] for r in top50])) > 1:
                top50_ics.append(spearmanr([r["score"] for r in top50], [r["y52"] for r in top50]).statistic)
                
            y_rel = pd.qcut(ys, 5, labels=False, duplicates='drop') if len(np.unique(ys)) >= 5 else np.zeros(len(ys))
            ndcg30s.append(ndcg_at_k(y_rel, sc, 30))
            ndcg50s.append(ndcg_at_k(y_rel, sc, 50))
            
            curr_ranks = {r["kod"]: idx for idx, r in enumerate(rs)}
            if prev_ranks:
                common = sorted(set(curr_ranks.keys()) & set(prev_ranks.keys()))
                if len(common) > 5:
                    stabilities.append(spearmanr([curr_ranks[k] for k in common], [prev_ranks[k] for k in common]).statistic)
            prev_ranks = curr_ranks

    return {
        "mean_ic52": finite(np.mean(ics)) if ics else None,
        "median_ic52": finite(np.median(ics)) if ics else None,
        "positive_ic_share": finite(np.mean(np.array(ics) > 0)) if ics else None,
        "mean_top30_ic52": finite(np.mean(top30_ics)) if top30_ics else None,
        "mean_top50_ic52": finite(np.mean(top50_ics)) if top50_ics else None,
        "mean_ndcg30": finite(np.mean(ndcg30s)) if ndcg30s else None,
        "mean_ndcg50": finite(np.mean(ndcg50s)) if ndcg50s else None,
        "rank_stability": finite(np.mean(stabilities)) if stabilities else None
    }

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

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "max_dd": max_dd,
        "turnover": turnover, "rolling_24m_win_rate": finite(np.mean(r24_win)) if r24_win else None
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

def audit_overlap(h0_rankings, candidate_rankings):
    dates = sorted(set(h0_rankings.keys()) & set(candidate_rankings.keys()))
    overlaps, jaccards, full_spearman, top30_spearman = [], [], [], []

    for dt in dates:
        h0_set30 = set(r["kod"] for r in h0_rankings[dt][:30])
        cand_set30 = set(r["kod"] for r in candidate_rankings[dt][:30])
        common = h0_set30 & cand_set30
        overlaps.append(len(common))
        jaccards.append(len(common) / len(h0_set30 | cand_set30))
        
        h_dict = {r["kod"]: r["score"] for r in h0_rankings[dt]}
        c_dict = {r["kod"]: r["score"] for r in candidate_rankings[dt]}
        common_all = sorted(set(h_dict.keys()) & set(c_dict.keys()))
        if len(common_all) > 5:
            s_val = spearmanr([h_dict[k] for k in common_all], [c_dict[k] for k in common_all]).statistic
            if math.isfinite(s_val): full_spearman.append(s_val)
        union30 = sorted(h0_set30 | cand_set30)
        if len(union30) > 3:
            s_val30 = spearmanr([h_dict[k] for k in union30], [c_dict[k] for k in union30]).statistic
            if math.isfinite(s_val30): top30_spearman.append(s_val30)

    return {
        "overlap_top30_mean": finite(np.mean(overlaps)),
        "jaccard_mean": finite(np.mean(jaccards)),
        "full_spearman_mean": finite(np.mean(full_spearman)) if full_spearman else None,
        "top30_spearman_mean": finite(np.mean(top30_spearman)) if top30_spearman else None
    }

def main():
    print("=" * 80)
    print("RESEARCH O: NEUTRAL RANKING MODEL RACE")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, core_features, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving Baseline Candidate A: Frozen H0 Selector...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Training Candidate B: LightGBM LambdaRank...")
    lgb_rankings = train_walkforward_ranker(core_df, core_features, "lgb")
    
    print("3. Training Candidate C: XGBoost Ranker (rank:ndcg)...")
    xgb_rankings = train_walkforward_ranker(core_df, core_features, "xgb")
    
    print("4. Training Candidate D: CatBoost Ranker (YetiRank)...")
    cat_rankings = train_walkforward_ranker(core_df, core_features, "cat")
    
    print("5. Training Candidate E: Linear Pairwise Ranker (Hinge Loss)...")
    lin_rankings = train_walkforward_ranker(core_df, core_features, "linear")
    
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

    print("6. Simulating H0 Portfolio Engine for all 5 Candidates...")
    candidates = {
        "A_Frozen_H0": h0_rankings,
        "B_LightGBM_LambdaRank": lgb_rankings,
        "C_XGBoost_Ranker": xgb_rankings,
        "D_CatBoost_YetiRank": cat_rankings,
        "E_Linear_Pairwise": lin_rankings
    }
    
    results = {"period": {"start": START_DATE, "end": END_DATE, "n_dates": len(eval_dates)}}
    
    for name, r_map in candidates.items():
        periods, contrib = simulate_h0_engine(r_map, returns_map, all_dates)
        ranking_stats = ic_and_ndcg_calc(r_map)
        port_stats = evaluate_metrics(periods, b_xact_rets)
        conc_stats = concentration_analysis(contrib, returns_map, r_map, periods)
        overlap_stats = audit_overlap(h0_rankings, r_map) if name != "A_Frozen_H0" else {"overlap_top30_mean": 30.0, "jaccard_mean": 1.0, "full_spearman_mean": 1.0, "top30_spearman_mean": 1.0}
        
        results[name] = {
            "ranking_quality": ranking_stats,
            "portfolio_performance": port_stats,
            "concentration": conc_stats,
            "overlap_vs_h0": overlap_stats
        }

    out_file = V2 / "research_k/research_o_ranking_race_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH O: NEUTRAL RANKING MODEL RACE SUMMARY")
    print("=" * 80)
    for name in sorted(candidates.keys()):
        r_q = results[name]["ranking_quality"]
        p_p = results[name]["portfolio_performance"]
        ic_str = f"{r_q['mean_ic52']:.4f}" if r_q.get('mean_ic52') is not None else "N/A"
        top30_ic_str = f"{r_q['mean_top30_ic52']:.4f}" if r_q.get('mean_top30_ic52') is not None else "N/A"
        cagr_str = f"{p_p['cagr']:.2%}" if p_p.get('cagr') is not None else "N/A"
        exc_str = f"{p_p['excess_cagr_vs_broad_tr']:.2%}" if p_p.get('excess_cagr_vs_broad_tr') is not None else "N/A"
        sh_str = f"{p_p['sharpe_vs_broad_tr']:.2f}" if p_p.get('sharpe_vs_broad_tr') is not None else "N/A"
        print(f"{name:25s} | IC52={ic_str:7s} | Top30_IC={top30_ic_str:7s} | CAGR={cagr_str:7s} | Excess={exc_str:7s} | Sharpe={sh_str:5s}")
    print("=" * 80)

if __name__ == "__main__":
    main()
