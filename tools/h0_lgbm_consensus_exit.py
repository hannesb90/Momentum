"""Pre-registered LightGBM consensus validator above frozen H0 exits."""
from __future__ import annotations

import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
from scipy.stats import spearmanr

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as BASE
import stack_h_repaired_h012 as STATS
from h0_core_meta_exit import CORE, EXTRA, FEATURES, eight_week

PRE = V2 / "research_k/H0_LGBM_CONSENSUS_EXIT_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_lgbm_consensus_exit_results.json"
N, COST = 30, .002


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def load():
    rankings, dates, returns, entry, schedule = BASE.late_loader()
    panel = json.loads((V2 / "panels/core_panel.json").read_text())
    return rankings, dates, returns, schedule, {(r["kod"], r["panel_date"]): r for r in panel}


def vector(core, day, row, rank):
    c = core.get((row["kod"], day), {})
    vals = [c.get(k) for k in CORE] + [row["score"], rank, row.get("m12_rank"), row.get("m18_rank")]
    return [np.nan if x is None else float(x) for x in vals]


def observations(data):
    rankings, dates, returns, schedule, core = data; out = []
    for i, day in enumerate(dates):
        for rank, row in enumerate(rankings[day], 1):
            y = eight_week(returns, dates, i, row["kod"])
            if y is not None: out.append({"date": day, "kod": row["kod"], "y": y, "x": vector(core, day, row, rank)})
    return out


def fit(rows):
    x = np.asarray([r["x"] for r in rows], float); y = np.asarray([r["y"] for r in rows], float)
    return lgb.LGBMRegressor(objective="regression", n_estimators=80, learning_rate=.03, num_leaves=7,
        max_depth=3, min_child_samples=40, reg_lambda=10., reg_alpha=1., colsample_bytree=.7,
        subsample=.8, random_state=20260816, n_jobs=1, verbosity=-1).fit(x, y)


def predictions(model, data, day):
    rankings, dates, returns, schedule, core = data
    rows = rankings[day]; x = np.asarray([vector(core, day, r, j + 1) for j, r in enumerate(rows)], float)
    return {r["kod"]: float(p) for r, p in zip(rows, model.predict(x))}


def panel_ic(model, obs, start, end):
    vals = []
    for day in sorted({r["date"] for r in obs if start <= r["date"] <= end}):
        rows = [r for r in obs if r["date"] == day]
        y = np.asarray([r["y"] for r in rows]); p = model.predict(np.asarray([r["x"] for r in rows], float))
        if len(rows) > 3 and y.std() and p.std(): vals.append(float(spearmanr(y, p).statistic))
    return {"panel_dates": len(vals), "mean_spearman_ic": None if not vals else round(float(np.mean(vals)), 4), "positive_share": None if not vals else round(float(np.mean(np.asarray(vals) > 0)), 4)}


def simulate(data, model, start, end):
    rankings, dates, returns, schedule, core = data; prior, vals, turns, kept = [], [], [], 0
    for i, day in enumerate(dates):
        ranked = rankings[day]; active = start <= day <= end
        if not prior or schedule(i, day):
            base = [r["kod"] for r in ranked[:N]]; current = base
            if active and model is not None and prior:
                p = predictions(model, data, day)
                ordered = sorted(p, key=lambda k: (-p[k], k)); ml_rank = {k: j + 1 for j, k in enumerate(ordered)}
                guard = [k for k in prior if k not in base and ml_rank.get(k, 10**9) <= N]
                new = [k for k in base if k not in prior]
                remove = set(sorted(new, key=lambda k: (p.get(k, -np.inf), k))[:len(guard)])
                current = [k for k in base if k not in remove] + guard
                kept += len(guard)
            turn = len(set(current) - set(prior)) / N if prior else 0.0; prior = current
        else: turn = 0.0
        if active:
            vals.append(sum(returns.get((k, day), 0.) for k in prior) / N - COST * turn); turns.append(turn)
    return np.asarray(vals), {"total_one_way_turnover": round(float(sum(turns)), 4), "mean_one_way_turnover": round(float(np.mean(turns)), 4), "consensus_retained_events": kept}


def evaluate(name, train, obs, data, start, end):
    model = fit(train); base, db = simulate(data, None, start, end); variant, dv = simulate(data, model, start, end)
    return {"name": name, "train_n": len(train), "features": len(FEATURES), "validator_ic": panel_ic(model, obs, start, end), "baseline_h0": {**STATS.stat(base), **db}, "consensus_h0_lgbm": {**STATS.stat(variant), **dv}, "delta": STATS.bootstrap(variant, base)}


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RESULTS": raise SystemExit("inactive preregistration")
    data = load(); obs = observations(data)
    dev_train = [r for r in obs if r["date"] <= "2022-12-30"]
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "preregistration_sha256": sha(PRE), "diagnostic_only": True, "development": evaluate("development_2023", dev_train, obs, data, "2023-01-27", "2023-12-29")}
    d = result["development"]
    gate = d["delta"]["delta_cagr"] > 0 and d["consensus_h0_lgbm"]["total_one_way_turnover"] < d["baseline_h0"]["total_one_way_turnover"] and (d["validator_ic"]["mean_spearman_ic"] or 0) > 0
    result["development_gate_pass"] = gate
    if gate:
        tr = [r for r in obs if r["date"] <= "2023-12-29"]
        result["independent"] = evaluate("independent_2024_2026", tr, obs, data, "2024-01-26", "2026-07-10")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"development_gate_pass": gate, "development": {"ic": d["validator_ic"], "delta": d["delta"]}}, ensure_ascii=False))


if __name__ == "__main__": main()
