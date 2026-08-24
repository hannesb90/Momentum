"""Time-split, causal exit-model diagnostic on frozen H0 rankings."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as BASE
import stack_h_repaired_h012 as STATS

PRE = V2 / "research_k/H0_EXIT_MODEL_TIME_SPLIT_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_exit_model_time_split_results.json"
N, MAX_KEEP, COST, RIDGE = 30, 5, 0.002, 1.0
FEATURES = ["score", "rank", "score_change", "sma120_gap", "relative_since_entry", "vol60", "dd52", "trend_t52"]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def price_at(series, kod, day):
    ds, values = series.get(kod, (np.array([]), np.array([])))
    idx = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    return float(values[idx]) if idx >= 0 else None


def raw_features(series, rankings, entry_prices, entry_day, entry_score, kod, day, rank, score):
    ds, values = series.get(kod, (np.array([]), np.array([])))
    idx = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    if idx < 200 or kod not in entry_day or kod not in entry_score:
        return None
    sma = float(np.mean(values[idx - 120:idx]))
    pnow, pentry = float(values[idx]), entry_prices.get((kod, entry_day[kod]))
    if not pentry or pentry <= 0:
        return None
    peer = []
    for row in rankings[entry_day[kod]]:
        a, b = entry_prices.get((row["kod"], entry_day[kod])), price_at(series, row["kod"], day)
        if a and b:
            peer.append(b / a - 1)
    if not peer:
        return None
    p60 = values[max(0, idx - 60):idx + 1]
    vol = float(np.std(np.diff(p60) / p60[:-1]) * math.sqrt(252)) if len(p60) >= 61 else None
    lo = int(np.searchsorted(ds, np.datetime64(day) - np.timedelta64(364, "D"), side="left"))
    win = values[lo:idx + 1]
    if len(win) < 200 or vol is None:
        return None
    peak = np.maximum.accumulate(win)
    dd = float(np.min(win / peak - 1))
    x, y = np.arange(len(win), dtype=float), np.log(win)
    xc, yc = x - x.mean(), y - y.mean()
    sxx = float(xc @ xc); slope = float(xc @ yc) / sxx
    resid = yc - slope * xc; se = math.sqrt(float(resid @ resid) / max(1, len(x) - 2) / sxx)
    trend = slope / se if se > 0 else 0.0
    return np.array([score, rank, score - entry_score[kod], pnow / sma - 1,
                     pnow / pentry - 1 - float(np.median(peer)), vol, dd, trend], dtype=float)


def eight_week(returns, dates, i, kod):
    if i + 1 >= len(dates): return None
    return float((1 + returns.get((kod, dates[i]), 0.0)) * (1 + returns.get((kod, dates[i + 1]), 0.0)) - 1)


def exit_rows(rankings, dates, returns, entry_prices, series, schedule):
    prior, entry_day, entry_score, rows = [], {}, {}, []
    for i, day in enumerate(dates):
        ranked = rankings[day]; rank = {r["kod"]: j + 1 for j, r in enumerate(ranked)}; score = {r["kod"]: float(r["score"]) for r in ranked}
        if not prior or schedule(i, day):
            current = [r["kod"] for r in ranked[:N]]
            bought, sold = set(current) - set(prior), set(prior) - set(current)
            basket = [eight_week(returns, dates, i, k) for k in bought]
            basket = [x for x in basket if x is not None]
            for kod in sold:
                features = raw_features(series, rankings, entry_prices, entry_day, entry_score, kod, day, rank.get(kod, 999), score.get(kod, 0.0))
                future = eight_week(returns, dates, i, kod)
                if features is not None and future is not None and basket:
                    rows.append({"date": day, "kod": kod, "features": features.tolist(), "target": future - float(np.mean(basket))})
                entry_day.pop(kod, None); entry_score.pop(kod, None)
            for kod in bought:
                entry_day[kod], entry_score[kod] = day, score[kod]
            prior = current
    return rows


def fit(rows):
    x = np.asarray([r["features"] for r in rows], float); y = np.asarray([r["target"] for r in rows], float)
    mean, scale = x.mean(axis=0), x.std(axis=0); scale[scale < 1e-12] = 1.0
    z = (x - mean) / scale
    coef = np.linalg.solve(z.T @ z + RIDGE * np.eye(z.shape[1]), z.T @ (y - y.mean()))
    return {"mean": mean, "scale": scale, "coef": coef, "intercept": float(y.mean()), "n_train": len(rows)}


def predict(model, features): return float(model["intercept"] + ((features - model["mean"]) / model["scale"]) @ model["coef"])


def simulate(rankings, dates, returns, entry_prices, series, schedule, model, start, end):
    prior, entry_day, entry_score, values, turnover, kept, preds = [], {}, {}, [], [], 0, []
    for i, day in enumerate(dates):
        ranked = rankings[day]; rank = {r["kod"]: j + 1 for j, r in enumerate(ranked)}; score = {r["kod"]: float(r["score"]) for r in ranked}
        active = start <= day <= end
        if not prior or schedule(i, day):
            baseline = [r["kod"] for r in ranked[:N]]; guard = []
            if active and model and prior:
                for kod in prior:
                    if kod in baseline: continue
                    f = raw_features(series, rankings, entry_prices, entry_day, entry_score, kod, day, rank.get(kod, 999), score.get(kod, 0.0))
                    if f is not None:
                        p = predict(model, f); preds.append((p, day, kod))
                        if p > 0: guard.append((p, kod))
                guard = [k for _, k in sorted(guard, reverse=True)[:MAX_KEEP]]
            current = baseline[:N-len(guard)] + guard
            bought, sold = set(current) - set(prior), set(prior) - set(current)
            for kod in sold: entry_day.pop(kod, None); entry_score.pop(kod, None)
            for kod in bought: entry_day[kod], entry_score[kod] = day, score[kod]
            kept += len(guard); turn = len(bought) / N; prior = current
        else: turn = 0.0
        if active:
            values.append(sum(returns.get((k, day), 0.0) for k in prior) / N - COST * turn)
            turnover.append(turn)
    return np.asarray(values), {"mean_one_way_turnover": round(float(np.mean(turnover)), 4), "total_one_way_turnover": round(float(np.sum(turnover)), 4), "guarded_holding_events": kept, "prediction_count": len(preds)}


def data_sets():
    rankings, dates, returns, entry, schedule = BASE.late_loader()
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    series = {k: (np.array([np.datetime64(x["d"]) for x in rs]), np.array([x["adj"] for x in rs], float)) for k, rs in prices.items()}
    yield "2021_2026", rankings, dates, returns, entry, series, schedule
    import h1419_motor as M
    rankings, dates, returns, entry, schedule = BASE.early_loader()
    yield "2014_2019", rankings, dates, returns, entry, M.SERIE, schedule


def eval_fold(name, train_rows, test_data, start, end):
    model = fit(train_rows); rankings, dates, returns, entry, series, schedule = test_data
    base, base_diag = simulate(rankings, dates, returns, entry, series, schedule, None, start, end)
    variant, variant_diag = simulate(rankings, dates, returns, entry, series, schedule, model, start, end)
    test_rows = [r for r in exit_rows(rankings, dates, returns, entry, series, schedule) if start <= r["date"] <= end]
    actual = np.asarray([r["target"] for r in test_rows]); forecast = np.asarray([predict(model, np.asarray(r["features"])) for r in test_rows])
    corr = float(np.corrcoef(actual, forecast)[0, 1]) if len(actual) > 2 and actual.std() and forecast.std() else None
    return {"name": name, "train_n": model["n_train"], "test_n": len(test_rows), "prediction_correlation": None if corr is None else round(corr, 4),
            "baseline_h0": {**STATS.stat(base), **base_diag}, "exit_model_guard": {**STATS.stat(variant), **variant_diag},
            "delta": STATS.bootstrap(variant, base), "coefficients_standardized": dict(zip(FEATURES, [round(float(x), 6) for x in model["coef"]]))}


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RUN": raise SystemExit("preregistration inactive")
    datasets = {label: data for label, *data in data_sets()}
    early = datasets["2014_2019"]; late = datasets["2021_2026"]
    early_rows = exit_rows(*early)
    train_internal = [r for r in early_rows if r["date"] < "2017-01-01"]
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "preregistration_sha256": sha(PRE), "diagnostic_only": True, "folds": {}}
    result["folds"]["older_internal"] = eval_fold("older_internal", train_internal, early, "2017-01-01", "2019-12-31")
    result["folds"]["later_independent"] = eval_fold("later_independent", early_rows, late, "2021-07-16", "2026-07-10")
    later = result["folds"]["later_independent"]; older = result["folds"]["older_internal"]
    result["decision_screen"] = {"later_positive": later["delta"]["delta_cagr"] > 0, "later_ci_excludes_zero": later["delta"]["ki_lo"] > 0,
                                 "later_prediction_correlation_positive": (later["prediction_correlation"] or 0) > 0,
                                 "later_turnover_lower": later["exit_model_guard"]["total_one_way_turnover"] < later["baseline_h0"]["total_one_way_turnover"],
                                 "older_not_negative": older["delta"]["delta_cagr"] >= 0}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["decision_screen"], ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
