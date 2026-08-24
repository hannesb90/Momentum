"""
Test True V1 LambdaRank Model on Corrected V2 Data.
Compares exact V1 LambdaRank (objective=lambdarank, qcut(5), query groups, date weighting)
against H0 momentum baseline on V2 panels.
"""
from __future__ import annotations
import json, math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import lightgbm as lgb
from sklearn.impute import SimpleImputer

V2 = Path("/home/hannesb/momentum_v2")
SEED = 20260808

def finite(x):
    return None if x is None or not math.isfinite(float(x)) else float(x)

def load_data(panel_name, feature_ids):
    panel = json.loads((V2 / f"panels/{panel_name}").read_text())
    target = json.loads((V2 / "panels/target_table.json").read_text())
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    rows = []
    for r in panel:
        t = tm.get((r["kod"], r["panel_date"]))
        if not t or t["target_fwd52w"] is None: continue
        x = {f: r.get(f) for f in feature_ids}
        rows.append({"kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"], "y": t["target_fwd52w"], "has_fundamenta": r.get("has_fundamenta"), **x})
    return pd.DataFrame(rows)

def split_defs(df):
    specs = [
        ("validation_2023", "validation", "2023-01-01", "2023-12-31"),
        ("oos_2024", "test", "2024-01-01", "2024-12-31"),
        ("oos_2025", "test", "2025-01-01", "2025-12-31")
    ]
    out = []
    for name, role, lo, hi in specs:
        cutoff = (date.fromisoformat(lo) - timedelta(weeks=52)).isoformat()
        tr = df[df.panel_date <= cutoff]
        ev = df[(df.panel_date >= lo) & (df.panel_date <= hi)]
        out.append(dict(
            name=name, role=role, eval_from=lo, eval_to=hi, train_to=cutoff,
            n_train=len(tr), n_eval=len(ev),
            train_dates=tr.panel_date.nunique(), eval_dates=ev.panel_date.nunique()
        ))
    return out

def fit_predict_lambdarank(df, features):
    splits = split_defs(df)
    preds = []
    
    imputer = SimpleImputer(strategy="median")
    df_imputed = df.copy()
    df_imputed[features] = imputer.fit_transform(df[features])

    for s in splits:
        tr = df_imputed[df_imputed.panel_date <= s["train_to"]].sort_values("panel_date")
        ev = df_imputed[(df_imputed.panel_date >= s["eval_from"]) & (df_imputed.panel_date <= s["eval_to"])].sort_values("panel_date")

        y_tr_rel = tr.groupby("panel_date", sort=False)["y"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        ).values.astype(int)

        y_va_rel = ev.groupby("panel_date", sort=False)["y"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        ).values.astype(int)

        train_groups = tr.groupby("panel_date", sort=False).size().values
        val_groups = ev.groupby("panel_date", sort=False).size().values

        w_tr = (1.0 / tr.groupby("panel_date", sort=False)["y"].transform("size")).values.astype(np.float32)

        X_tr = tr[features].values
        X_va = ev[features].values

        ranker = lgb.LGBMRanker(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=30,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=SEED,
            n_jobs=4,
            verbosity=-1
        )

        ranker.fit(
            X_tr, y_tr_rel, group=train_groups, sample_weight=w_tr,
            eval_set=[(X_va, y_va_rel)], eval_group=[val_groups],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )

        score = ranker.predict(X_va)

        for (_, r), z in zip(ev.iterrows(), score):
            preds.append({
                "dataset": "CORE", "model": "v1_lambdarank", "split": s["name"],
                "role": s["role"], "kod": r.kod, "panel_date": r.panel_date,
                "score": float(z), "target_fwd52w": float(r.y),
                "has_fundamenta": None if pd.isna(r.has_fundamenta) else bool(r.has_fundamenta)
            })

    return preds

def ic_metrics(rows):
    by = defaultdict(list)
    for r in rows: by[r["panel_date"]].append(r)
    per = []
    for dt, rs in sorted(by.items()):
        scores = np.array([r["score"] for r in rs])
        ys = np.array([r["target_fwd52w"] for r in rs])
        mask = np.isfinite(scores) & np.isfinite(ys)
        if mask.sum() > 2 and len(np.unique(scores[mask])) > 1 and len(np.unique(ys[mask])) > 1:
            res = spearmanr(scores[mask], ys[mask])
            ic = finite(getattr(res, 'statistic', res[0]))
        else:
            ic = None
        
        top = sorted(rs, key=lambda z: (z["score"], z["kod"]), reverse=True)[:30]
        top_scores = np.array([r["score"] for r in top])
        top_ys = np.array([r["target_fwd52w"] for r in top])
        top_mask = np.isfinite(top_scores) & np.isfinite(top_ys)
        if top_mask.sum() > 2 and len(np.unique(top_scores[top_mask])) > 1 and len(np.unique(top_ys[top_mask])) > 1:
            res_top = spearmanr(top_scores[top_mask], top_ys[top_mask])
            tic = finite(getattr(res_top, 'statistic', res_top[0]))
        else:
            tic = None

        per.append({
            "panel_date": dt, "n": len(rs), "ic52": ic, "top30_ic52": tic,
            "distinct_scores": len(set(scores)), "tie_share": 1 - len(set(scores)) / len(scores),
            "score_std": float(scores.std())
        })
    vals = [r["ic52"] for r in per if r["ic52"] is not None]
    top = [r["top30_ic52"] for r in per if r["top30_ic52"] is not None]
    return {
        "n_obs": len(rows), "n_dates": len(per),
        "mean_ic52": finite(np.mean(vals)) if vals else None,
        "median_ic52": finite(np.median(vals)) if vals else None,
        "positive_ic_share": finite(np.mean(np.array(vals) > 0)) if vals else None,
        "mean_top30_ic52": finite(np.mean(top)) if top else None,
        "median_top30_ic52": finite(np.median(top)) if top else None
    }

def price_returns():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    by = defaultdict(dict)
    for r in core: by[r["kod"]][r["panel_date"]] = r["price_date"]
    dates = sorted({r["panel_date"] for r in core})
    nxt = dict(zip(dates, dates[1:]))
    adj = {k: {r["d"]: r["adj"] for r in rs} for k, rs in prices.items()}
    last = {k: rs[-1]["d"] for k, rs in prices.items()}
    ret = {}
    for k, ds in by.items():
        for dt, p0d in ds.items():
            nd = nxt.get(dt)
            if not nd: continue
            p1d = ds.get(nd)
            if p1d: ret[(k, dt)] = adj[k][p1d] / adj[k][p0d] - 1
            elif k in terminal and dt < terminal[k]["event_date"] <= nd: ret[(k, dt)] = adj[k][last[k]] / adj[k][p0d] - 1
            else: ret[(k, dt)] = 0.0
    return ret

def annualized(rs):
    if not rs: return None
    wealth = np.cumprod(1 + np.array(rs))
    years = len(rs) / 13
    return finite(wealth[-1] ** (1 / years) - 1) if wealth[-1] > 0 else -1.0

def portfolio(rows):
    by = defaultdict(list)
    for r in rows: by[r["panel_date"]].append(r)
    pret = price_returns()
    prev = set()
    periods = []
    contrib = defaultdict(float)
    for dt, rs in sorted(by.items()):
        chosen = sorted(rs, key=lambda z: (z["score"], z["kod"]), reverse=True)[:30]
        ids = {r["kod"] for r in chosen}
        turn = 1 - len(ids & prev) / 30 if prev else 1.0
        cr = {r["kod"]: pret.get((r["kod"], dt), 0.0) / len(chosen) for r in chosen}
        gross = sum(cr.values())
        net = gross - .002 * turn
        bench = np.mean([pret.get((r["kod"], dt), 0.0) for r in rs]) if rs else 0
        periods.append({"panel_date": dt, "gross_return_4w": gross, "net_return_4w": net, "benchmark_return_4w": float(bench), "excess_return_4w": net - bench, "turnover": turn})
        for k, v in cr.items(): contrib[k] += v
        prev = ids
    nr = [r["net_return_4w"] for r in periods]
    br = [r["benchmark_return_4w"] for r in periods]
    ex = [a - b for a, b in zip(nr, br)]
    wealth = np.cumprod(1 + np.array(nr))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    base = annualized(nr)
    be = annualized(br)
    ann_ex = None if base is None or be is None else base - be
    ranked = sorted(contrib.items(), key=lambda z: z[1], reverse=True)
    top3 = [k for k, _ in ranked[:3]]
    def leave(excluded):
        rr = []
        for dt, rs in sorted(by.items()):
            ch = [r for r in sorted(rs, key=lambda z: (z["score"], z["kod"]), reverse=True)[:30] if r["kod"] not in excluded]
            rr.append(float(np.mean([pret.get((r["kod"], dt), 0.0) for r in ch])) if ch else 0)
        return annualized(rr)

    return {
        "cagr": base, "benchmark_cagr": be, "annualized_excess": ann_ex,
        "sharpe": finite(np.mean(ex) / np.std(ex, ddof=1) * math.sqrt(13)) if len(ex) > 1 and np.std(ex, ddof=1) > 0 else None,
        "max_drawdown": finite(dd.min()), "mean_turnover": finite(np.mean([r["turnover"] for r in periods])),
        "top3_tickers": top3, "leave_top3_out_cagr": leave(set(top3))
    }

def main():
    reg = json.loads((V2 / "docs/probes/feature_registry.json").read_text())
    coref = [r["id"] for r in reg["CORE"] if r.get("status") != "UTESLUTEN" and not r.get("ej_feature")]
    core = load_data("core_panel.json", coref)
    
    print("Fitting True V1 LambdaRank model on V2 data...")
    preds = fit_predict_lambdarank(core, coref)
    
    test_preds = [r for r in preds if r["role"] == "test"]
    ic = ic_metrics(test_preds)
    p = portfolio(test_preds)
    
    def fmt_pct(val): return f"{val:.1%}" if val is not None else "N/A"
    def fmt_flt(val, d=4): return f"{val:.{d}f}" if val is not None else "N/A"

    print("--- TRUE V1 LAMBDARANK ON V2 DATA (2024-2025 OOS) ---")
    print(f"Mean IC52:         {fmt_flt(ic['mean_ic52'])}")
    print(f"Median IC52:       {fmt_flt(ic['median_ic52'])}")
    print(f"Positive IC share: {fmt_pct(ic['positive_ic_share'])}")
    print(f"Top-30 IC52:       {fmt_flt(ic['mean_top30_ic52'])}")
    print(f"CAGR:              {fmt_pct(p['cagr'])}")
    print(f"Benchmark CAGR:    {fmt_pct(p['benchmark_cagr'])}")
    print(f"Excess CAGR:       {fmt_pct(p['annualized_excess'])}")
    print(f"Sharpe:            {fmt_flt(p['sharpe'], 2)}")
    print(f"Max Drawdown:      {fmt_pct(p['max_drawdown'])}")
    print(f"Mean Turnover:     {fmt_pct(p['mean_turnover'])}")
    print(f"Top 3 Tickers:     {p['top3_tickers']}")
    print(f"Leave Top 3 CAGR:  {fmt_pct(p['leave_top3_out_cagr'])}")

if __name__ == "__main__":
    main()
