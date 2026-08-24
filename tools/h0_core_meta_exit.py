"""Pre-registered CORE-feature meta exit layer above frozen H0."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as BASE
import stack_h_repaired_h012 as STATS

PRE = V2 / "research_k/H0_CORE_META_EXIT_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_core_meta_exit_results.json"
N, MAX_KEEP, COST = 30, 5, 0.002
CORE = ["mom_4w", "mom_13w", "mom_26w", "mom_52w", "mom_12_1", "mom_relative_index_52w", "residual_momentum_52w", "trend_strength_52w", "trend_consistency_52w", "momentum_acceleration_13w", "reversal_1w", "vol_13w", "vol_52w", "downside_vol_52w", "beta_52w", "idio_vol_52w", "skew_52w", "kurtosis_52w", "price_vs_sma26w", "price_vs_sma52w", "high52w_ratio", "low52w_ratio", "drawdown_current_104w", "max_drawdown_52w", "risk_adj_momentum_52w", "volume_trend_13w", "rank_mom_52w_pct", "market_regime_trend", "market_regime_vol"]
EXTRA = ["h0_score", "h0_rank", "h0_m12_rank", "h0_m18_rank"]
FEATURES = CORE + EXTRA


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def eight_week(returns, dates, i, kod):
    if i + 1 >= len(dates): return None
    return float((1 + returns.get((kod, dates[i]), 0.0)) * (1 + returns.get((kod, dates[i + 1]), 0.0)) - 1)


def load():
    rankings, dates, returns, entry, schedule = BASE.late_loader()
    panel = json.loads((V2 / "panels/core_panel.json").read_text())
    core = {(r["kod"], r["panel_date"]): r for r in panel}
    return rankings, dates, returns, entry, schedule, core


def vector(core, row, rank):
    p = core.get((row["kod"], row["date"]), {})
    vals = [p.get(k) for k in CORE] + [row["score"], rank, row["m12_rank"], row["m18_rank"]]
    return np.asarray([np.nan if v is None else float(v) for v in vals], float)


def events(rankings, dates, returns, schedule, core):
    prior, out = [], []
    for i, day in enumerate(dates):
        ranked = rankings[day]
        rank = {r["kod"]: j + 1 for j, r in enumerate(ranked)}
        if not prior or schedule(i, day):
            current = [r["kod"] for r in ranked[:N]]
            bought, sold = set(current) - set(prior), set(prior) - set(current)
            replacement = [eight_week(returns, dates, i, k) for k in bought]
            replacement = [x for x in replacement if x is not None]
            for old in prior:
                if old not in sold: continue
                r = next((z for z in ranked if z["kod"] == old), None)
                own = eight_week(returns, dates, i, old)
                if r and own is not None and replacement:
                    meta = {"kod": old, "date": day, "score": r["score"], "m12_rank": r.get("m12_rank"), "m18_rank": r.get("m18_rank")}
                    out.append({"date": day, "kod": old, "target": own - float(np.mean(replacement)), "x": vector(core, meta, rank[old]).tolist()})
            prior = current
    return out


def fit(rows):
    x = np.asarray([r["x"] for r in rows], float)
    med = np.asarray([np.nanmedian(x[:, j]) if np.isfinite(x[:, j]).any() else 0.0 for j in range(x.shape[1])])
    x = np.where(np.isnan(x), med, x)
    model = HistGradientBoostingRegressor(max_iter=100, learning_rate=.05, max_leaf_nodes=5,
        min_samples_leaf=20, l2_regularization=10., random_state=20260816).fit(x, np.asarray([r["target"] for r in rows]))
    return model, med


def forecast(model, med, x): return float(model.predict(np.where(np.isnan(np.asarray(x, float)), med, x).reshape(1, -1))[0])


def simulate(rankings, dates, returns, schedule, core, model, med, start, end):
    prior, values, turns, kept = [], [], [], 0
    for i, day in enumerate(dates):
        ranked = rankings[day]; rank = {r["kod"]: j + 1 for j, r in enumerate(ranked)}
        active = start <= day <= end
        if not prior or schedule(i, day):
            baseline = [r["kod"] for r in ranked[:N]]; guard = []
            if active and model is not None:
                for kod in prior:
                    if kod in baseline: continue
                    r = next((z for z in ranked if z["kod"] == kod), None)
                    if r:
                        meta = {"kod": kod, "date": day, "score": r["score"], "m12_rank": r.get("m12_rank"), "m18_rank": r.get("m18_rank")}
                        p = forecast(model, med, vector(core, meta, rank[kod]))
                        if p > 0: guard.append((p, kod))
                guard = [k for _, k in sorted(guard, reverse=True)[:MAX_KEEP]]
            current = baseline[:N-len(guard)] + guard
            turn = len(set(current) - set(prior)) / N if prior else 0.0
            kept += len(guard); prior = current
        else: turn = 0.0
        if active:
            values.append(sum(returns.get((k, day), 0.0) for k in prior) / N - COST * turn); turns.append(turn)
    return np.asarray(values), {"total_one_way_turnover": round(float(sum(turns)), 4), "mean_one_way_turnover": round(float(np.mean(turns)), 4), "guarded_holding_events": kept}


def evaluate(name, train, all_events, data, start, end):
    model, med = fit(train); rankings, dates, returns, _, schedule, core = data
    base, db = simulate(rankings, dates, returns, schedule, core, None, None, start, end)
    meta, dm = simulate(rankings, dates, returns, schedule, core, model, med, start, end)
    test = [r for r in all_events if start <= r["date"] <= end]
    actual = np.asarray([r["target"] for r in test]); pred = np.asarray([forecast(model, med, r["x"]) for r in test])
    corr = float(np.corrcoef(actual, pred)[0, 1]) if actual.std() and pred.std() else None
    return {"name": name, "train_n": len(train), "test_n": len(test), "prediction_correlation": None if corr is None else round(corr, 4), "baseline_h0": {**STATS.stat(base), **db}, "core_meta_guard": {**STATS.stat(meta), **dm}, "delta": STATS.bootstrap(meta, base)}


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RESULTS": raise SystemExit("inactive preregistration")
    data = load(); rankings, dates, returns, entry, schedule, core = data
    all_events = events(rankings, dates, returns, schedule, core)
    train = [r for r in all_events if r["date"] <= "2022-12-30"]
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "preregistration_sha256": sha(PRE), "diagnostic_only": True, "features": FEATURES, "development": evaluate("development_2023", train, all_events, data, "2023-01-27", "2023-12-29")}
    d = result["development"]
    passed = (d["prediction_correlation"] or 0) > 0 and d["delta"]["delta_cagr"] > 0 and d["core_meta_guard"]["total_one_way_turnover"] < d["baseline_h0"]["total_one_way_turnover"]
    result["development_gate_pass"] = passed
    if passed:
        train2 = [r for r in all_events if r["date"] <= "2023-12-29"]
        result["independent"] = evaluate("independent_2024_2026", train2, all_events, data, "2024-01-26", "2026-07-10")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"development_gate_pass": passed, "development": {"corr": d["prediction_correlation"], "delta": d["delta"]}}, ensure_ascii=False))


if __name__ == "__main__": main()
