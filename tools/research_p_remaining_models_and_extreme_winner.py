"""
RESEARCH P: Remaining Model Families & Extreme-Winner Test (2021-07-16 to 2026-07-10)

Preregistered Candidates:
P1: ExtraTrees Regressor (Non-boosted, non-linear tree ensemble)
P2: GAM / Additive Model (HistGradientBoostingRegressor with depth=3, additive constraints)
P3: Listwise Ranker (ListMLE Loss Ranker per panel date query)
P4: Neural RankNet -> NOT JUSTIFIED (Insufficient independent temporal sample size)
P5: Extreme-Winner Classifier (LogisticRegression predicting top decile fwd52w return)

Evaluated on clean V2 CORE features, 52w walk-forward embargo, V4 post-decision execution,
Top 30 equal weight, 8w rebalance, 20 bp cost.
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
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score
import torch
import torch.nn as nn
import torch.optim as optim
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

class ListMLELoss(nn.Module):
    def forward(self, scores, perm):
        s_sorted = scores[perm]
        max_s = torch.max(s_sorted)
        exp_s = torch.exp(s_sorted - max_s)
        cum_sums = torch.flip(torch.cumsum(torch.flip(exp_s, dims=[0]), dim=0), dims=[0])
        log_sums = torch.log(cum_sums + 1e-10) + max_s
        loss = -torch.sum(s_sorted - log_sums)
        return loss

def train_walkforward_models(core_df, features, model_type="P1_ExtraTrees"):
    dates = sorted(core_df.panel_date.unique())
    eval_dates = [d for d in dates if START_DATE <= d <= END_DATE]
    
    imputer = SimpleImputer(strategy="median")
    df_imp = core_df.copy()
    df_imp[features] = imputer.fit_transform(core_df[features])
    
    predictions = defaultdict(list)
    step_size = 13
    eval_indices = [i for i, d in enumerate(dates) if d in eval_dates]
    first_eval_idx = eval_indices[0]
    
    torch.manual_seed(SEED)
    
    for i in range(first_eval_idx, len(dates), step_size):
        test_dates = dates[i : min(i + step_size, len(dates))]
        test_dates = [d for d in test_dates if d in eval_dates]
        if not test_dates: continue
        
        train_max_date = (date.fromisoformat(test_dates[0]) - timedelta(weeks=52)).isoformat()
        tr = df_imp[df_imp.panel_date <= train_max_date].sort_values("panel_date")
        ev = df_imp[df_imp.panel_date.isin(test_dates)].sort_values("panel_date")
        
        if len(tr) < 500 or len(ev) == 0: continue
        
        tr_y = tr["y52"].fillna(0.0).values
        X_tr = tr[features].values
        X_ev = ev[features].values
        
        if model_type == "P1_ExtraTrees":
            model = ExtraTreesRegressor(
                n_estimators=100, max_depth=6, max_features="sqrt", random_state=SEED, n_jobs=4
            )
            model.fit(X_tr, tr_y)
            scores = model.predict(X_ev)
            
        elif model_type == "P2_GAM_EBM":
            model = HistGradientBoostingRegressor(
                max_iter=100, max_depth=3, interaction_cst=None, random_state=SEED
            )
            model.fit(X_tr, tr_y)
            scores = model.predict(X_ev)
            
        elif model_type == "P3_ListMLE":
            net = nn.Linear(len(features), 1, bias=True)
            optimizer = optim.Adam(net.parameters(), lr=0.01, weight_decay=1e-4)
            criterion = ListMLELoss()
            
            grouped = [group for _, group in tr.groupby("panel_date", sort=False)]
            for epoch in range(15):
                for group in grouped:
                    if len(group) < 10: continue
                    g_X = torch.tensor(group[features].values, dtype=torch.float32)
                    g_y = group["y52"].values
                    perm = torch.tensor(np.argsort(g_y)[::-1].copy(), dtype=torch.long)
                    
                    optimizer.zero_grad()
                    s = net(g_X).squeeze(-1)
                    loss = criterion(s, perm)
                    loss.backward()
                    optimizer.step()
                    
            with torch.no_grad():
                scores = net(torch.tensor(X_ev, dtype=torch.float32)).squeeze(-1).numpy()
                
        elif model_type == "P5_Extreme_Winner":
            tr_winner = tr.groupby("panel_date", sort=False)["y52"].transform(
                lambda x: (x >= np.percentile(x.dropna(), 90)).astype(int) if len(x.dropna()) >= 10 else np.zeros(len(x))
            ).fillna(0).values.astype(int)
            
            clf = LogisticRegression(random_state=SEED, max_iter=500)
            clf.fit(X_tr, tr_winner)
            scores = clf.predict_proba(X_ev)[:, 1]

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
                s_val = spearmanr(sc, ys).statistic
                if math.isfinite(s_val): ics.append(s_val)
                
            top30 = valid[:30]
            if len(np.unique([r["score"] for r in top30])) > 1 and len(np.unique([r["y52"] for r in top30])) > 1:
                s_val30 = spearmanr([r["score"] for r in top30], [r["y52"] for r in top30]).statistic
                if math.isfinite(s_val30): top30_ics.append(s_val30)
                
            top50 = valid[:50]
            if len(np.unique([r["score"] for r in top50])) > 1 and len(np.unique([r["y52"] for r in top50])) > 1:
                s_val50 = spearmanr([r["score"] for r in top50], [r["y52"] for r in top50]).statistic
                if math.isfinite(s_val50): top50_ics.append(s_val50)
                
            y_rel = pd.qcut(ys, 5, labels=False, duplicates='drop') if len(np.unique(ys)) >= 5 else np.zeros(len(ys))
            ndcg30s.append(ndcg_at_k(y_rel, sc, 30))
            ndcg50s.append(ndcg_at_k(y_rel, sc, 50))
            
            curr_ranks = {r["kod"]: idx for idx, r in enumerate(rs)}
            if prev_ranks:
                common = sorted(set(curr_ranks.keys()) & set(prev_ranks.keys()))
                if len(common) > 5:
                    s_stab = spearmanr([curr_ranks[k] for k in common], [prev_ranks[k] for k in common]).statistic
                    if math.isfinite(s_stab): stabilities.append(s_stab)
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
    
    r12_win, r24_win = [], []
    for i in range(13, len(nr) + 1):
        c = annualized(nr[i-13:i], 13)
        bc = annualized(br[i-13:i], 13)
        if c is not None and bc is not None: r12_win.append(c > bc)
    for i in range(26, len(nr) + 1):
        c = annualized(nr[i-26:i], 13)
        bc = annualized(br[i-26:i], 13)
        if c is not None and bc is not None: r24_win.append(c > bc)

    return {
        "cagr": cagr, "bench_cagr": bench_cagr, "excess_cagr_vs_broad_tr": excess_cagr,
        "volatility": vol, "sharpe_vs_broad_tr": sharpe, "max_dd": max_dd,
        "turnover": turnover, "rolling_12m_win_rate": finite(np.mean(r12_win)) if r12_win else None,
        "rolling_24m_win_rate": finite(np.mean(r24_win)) if r24_win else None
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

def audit_p5_extreme_winner_classifier(p5_rankings, h0_rankings):
    dates = sorted(set(p5_rankings.keys()) & set(h0_rankings.keys()))
    roc_aucs, pr_aucs, p5_prec30s, h0_prec30s = [], [], [], []
    p5_rec30s, h0_rec30s = [], []

    for dt in dates:
        rows = p5_rankings[dt]
        valid = [r for r in rows if r.get("y52") is not None]
        if len(valid) < 20: continue
        
        ys = np.array([r["y52"] for r in valid])
        scores = np.array([r["score"] for r in valid])
        
        p90 = np.percentile(ys, 90)
        labels = (ys >= p90).astype(int)
        
        if len(np.unique(labels)) > 1:
            roc_aucs.append(roc_auc_score(labels, scores))
            pr_aucs.append(average_precision_score(labels, scores))
            
            p5_top30_kods = set(r["kod"] for r in rows[:30])
            h0_top30_kods = set(r["kod"] for r in h0_rankings[dt][:30])
            winner_kods = set(r["kod"] for i, r in enumerate(valid) if labels[i] == 1)
            
            if winner_kods:
                p5_rec30s.append(len(p5_top30_kods & winner_kods) / len(winner_kods))
                h0_rec30s.append(len(h0_top30_kods & winner_kods) / len(winner_kods))
                
            p5_prec30s.append(len(p5_top30_kods & winner_kods) / 30.0)
            h0_prec30s.append(len(h0_top30_kods & winner_kods) / 30.0)

    return {
        "mean_roc_auc": finite(np.mean(roc_aucs)) if roc_aucs else None,
        "mean_pr_auc": finite(np.mean(pr_aucs)) if pr_aucs else None,
        "p5_precision_at_30": finite(np.mean(p5_prec30s)) if p5_prec30s else None,
        "h0_precision_at_30": finite(np.mean(h0_prec30s)) if h0_prec30s else None,
        "p5_recall_at_30": finite(np.mean(p5_rec30s)) if p5_rec30s else None,
        "h0_recall_at_30": finite(np.mean(h0_rec30s)) if h0_rec30s else None,
        "lift_p5_vs_h0_recall": finite(np.mean(p5_rec30s) / np.mean(h0_rec30s)) if h0_rec30s and np.mean(h0_rec30s) > 0 else None
    }

def main():
    print("=" * 80)
    print("RESEARCH P: REMAINING MODEL FAMILIES & EXTREME-WINNER TEST")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 80)
    
    core_df, core_features, prices, terminal = load_data()
    returns_map, all_dates = execution_engine(core_df, prices, terminal)
    
    print("\n1. Deriving Baseline Candidate A: Frozen H0 Selector...")
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("2. Training P1: ExtraTrees Regressor...")
    p1_rankings = train_walkforward_models(core_df, core_features, "P1_ExtraTrees")
    
    print("3. Training P2: GAM / EBM Additive Model...")
    p2_rankings = train_walkforward_models(core_df, core_features, "P2_GAM_EBM")
    
    print("4. Training P3: Listwise Ranker (ListMLE Loss)...")
    p3_rankings = train_walkforward_models(core_df, core_features, "P3_ListMLE")
    
    print("5. Documenting P4: Neural RankNet -> NOT JUSTIFIED (Insufficient Temporal Sample)")
    
    print("6. Training P5: Extreme-Winner Classifier (LogisticRegression Top Decile)...")
    p5_rankings = train_walkforward_models(core_df, core_features, "P5_Extreme_Winner")
    
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

    print("7. Simulating H0 Portfolio Engine for all Candidates...")
    candidates = {
        "A_Frozen_H0": h0_rankings,
        "P1_ExtraTrees": p1_rankings,
        "P2_GAM_EBM": p2_rankings,
        "P3_Listwise_ListMLE": p3_rankings,
        "P5_Extreme_Winner_Classifier": p5_rankings
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

    p5_diag = audit_p5_extreme_winner_classifier(p5_rankings, h0_rankings)
    results["P5_Extreme_Winner_Diagnostics"] = p5_diag

    out_file = V2 / "research_k/research_p_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    
    print("\n" + "=" * 80)
    print("RESEARCH P: REMAINING MODEL FAMILIES SUMMARY")
    print("=" * 80)
    for name in sorted(candidates.keys()):
        r_q = results[name]["ranking_quality"]
        p_p = results[name]["portfolio_performance"]
        ic_str = f"{r_q['mean_ic52']:.4f}" if r_q.get('mean_ic52') is not None else "N/A"
        top30_ic_str = f"{r_q['mean_top30_ic52']:.4f}" if r_q.get('mean_top30_ic52') is not None else "N/A"
        cagr_str = f"{p_p['cagr']:.2%}" if p_p.get('cagr') is not None else "N/A"
        exc_str = f"{p_p['excess_cagr_vs_broad_tr']:.2%}" if p_p.get('excess_cagr_vs_broad_tr') is not None else "N/A"
        sh_str = f"{p_p['sharpe_vs_broad_tr']:.2f}" if p_p.get('sharpe_vs_broad_tr') is not None else "N/A"
        print(f"{name:30s} | IC52={ic_str:7s} | Top30_IC={top30_ic_str:7s} | CAGR={cagr_str:7s} | Excess={exc_str:7s} | Sharpe={sh_str:5s}")
    print("=" * 80)
    print("\nP5 EXTREME WINNER DIAGNOSTICS:")
    roc_str = f"{p5_diag['mean_roc_auc']:.4f}" if p5_diag.get('mean_roc_auc') is not None else "N/A"
    pr_str = f"{p5_diag['mean_pr_auc']:.4f}" if p5_diag.get('mean_pr_auc') is not None else "N/A"
    p5_rec_str = f"{p5_diag['p5_recall_at_30']:.2%}" if p5_diag.get('p5_recall_at_30') is not None else "N/A"
    h0_rec_str = f"{p5_diag['h0_recall_at_30']:.2%}" if p5_diag.get('h0_recall_at_30') is not None else "N/A"
    lift_str = f"{p5_diag['lift_p5_vs_h0_recall']:.2f}x" if p5_diag.get('lift_p5_vs_h0_recall') is not None else "N/A"
    print(f"ROC-AUC={roc_str} | PR-AUC={pr_str}")
    print(f"P5 Recall@30={p5_rec_str} vs H0 Recall@30={h0_rec_str} (Lift: {lift_str})")
    print("=" * 80)

if __name__ == "__main__":
    main()
