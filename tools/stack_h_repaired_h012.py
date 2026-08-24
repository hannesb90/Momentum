"""Repaired Stack H on the frozen H0/H1/H2 signal definitions.

Diagnostic only.  This script never writes into Track H or the H1/H2 locks.
The specification is fixed in research_k/STACK_H_REPAIRED_H012_PREREGISTRATION.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import gc
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))

OUT = V2 / "research_k/stack_h_repaired_h012_results.json"
PRE = V2 / "research_k/STACK_H_REPAIRED_H012_PREREGISTRATION.json"
PPY, RF, COST, N, CAP, FLOOR = 13.0, 0.0224, 0.002, 30, 0.06, 0.01
FEATURE_CACHE = {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct_rank(values):
    ok = sorted((float(x), i) for i, x in enumerate(values) if x is not None and math.isfinite(float(x)))
    out, j, n = [None] * len(values), 0, len(ok)
    while j < n:
        k = j + 1
        while k < n and ok[k][0] == ok[j][0]:
            k += 1
        value = ((j + 1) + k) / 2 / n
        for _, i in ok[j:k]:
            out[i] = value
        j = k
    return out


def median_fill(values):
    good = sorted(x for x in values if x is not None and math.isfinite(float(x)))
    fill = float(np.median(good)) if good else 0.5
    return [fill if x is None else float(x) for x in values]


def hard_cap(weights, target):
    """Waterfill with both floor and cap; validates the result rather than renormalising past the cap."""
    w = np.asarray(weights, dtype=float).copy()
    if not len(w):
        return w
    if len(w) * FLOOR - target > 1e-12 or target - len(w) * CAP > 1e-12:
        raise ValueError("infeasible floor/cap target")
    total = float(w.sum())
    base = np.full(len(w), target / len(w)) if total <= 0 else w / total * target
    # Project onto the bounded simplex.  A shared offset has a unique solution
    # for every feasible target and, unlike clip-then-renormalise, cannot push
    # a capped holding above CAP on the final normalisation.
    lo, hi = FLOOR - float(base.max()), CAP - float(base.min())
    for _ in range(100):
        offset = (lo + hi) / 2
        candidate = np.clip(base + offset, FLOOR, CAP)
        if float(candidate.sum()) < target:
            lo = offset
        else:
            hi = offset
    w = np.clip(base + (lo + hi) / 2, FLOOR, CAP)
    if abs(float(w.sum()) - target) > 1e-10 or float(w.max()) > CAP + 1e-12:
        raise AssertionError("hard-cap invariant failed")
    return w


def trailing_features(series, kod, dt):
    # Rankings reuse these features during portfolio construction.  The cache
    # is intentionally process-local: it changes runtime only, never inputs.
    key = (id(series), kod, dt)
    cached = FEATURE_CACHE.get(key)
    if cached is not None:
        return cached
    ds, adj = series.get(kod, (np.array([]), np.array([])))
    if not len(ds):
        result = (None, None, False, 0.25)
        FEATURE_CACHE[key] = result
        return result
    now = np.datetime64(dt)
    i = int(np.searchsorted(ds, now, side="right")) - 1
    if i < 0:
        result = (None, None, False, 0.25)
        FEATURE_CACHE[key] = result
        return result
    lo = int(np.searchsorted(ds, now - np.timedelta64(364, "D"), side="left"))
    win = adj[lo:i + 1]
    if len(win) < 200:
        result = (None, None, False, 0.25)
        FEATURE_CACHE[key] = result
        return result
    peak = np.maximum.accumulate(win)
    dd_res = -abs(float(np.min(win / peak - 1.0)))
    # Closed-form OLS trend t-stat.  This is algebraically equivalent to the
    # former least-squares matrix solve, but avoids thousands of tiny LAPACK
    # calls when ranking every candidate on every panel.
    y, x = np.log(win), np.arange(len(win), dtype=float)
    xc, yc = x - x.mean(), y - y.mean()
    sxx = float(xc @ xc)
    slope = float(xc @ yc) / sxx
    resid = yc - slope * xc
    s2 = float(resid @ resid) / max(1, len(x) - 2)
    se = math.sqrt(s2 / sxx)
    trend = float(slope / se) if se > 0 else None
    p60 = adj[max(0, i - 60):i + 1]
    rets = np.diff(p60) / p60[:-1] if len(p60) >= 61 else np.array([])
    vol = float(np.std(rets) * math.sqrt(252)) if len(rets) else 0.25
    ma120 = float(np.mean(adj[i - 120:i])) if i >= 120 else None
    confirmed = bool(ma120 is not None and adj[i] >= ma120 and vol < 0.35)
    result = (dd_res, trend, confirmed, vol if vol > 1e-4 else 0.25)
    FEATURE_CACHE[key] = result
    return result


def build_rankings(base_rankings, series, label):
    out = {"H0": {}, "H1": {}, "H2": {}}
    for panel_no, (dt, rows) in enumerate(base_rankings.items(), start=1):
        if panel_no == 1 or panel_no % 10 == 0:
            print(f"{label}: ranking panel {panel_no}/{len(base_rankings)}", flush=True)
        rows = [dict(r) for r in rows]
        h0 = [r["score"] for r in rows]
        dd, trend = [], []
        for r in rows:
            a, b, _, _ = trailing_features(series, r["kod"], dt)
            dd.append(a); trend.append(b)
        h0r = median_fill(pct_rank(h0))
        for name, factor in (("H0", None), ("H1", dd), ("H2", trend)):
            if factor is None:
                score = h0r
            else:
                fr = median_fill(pct_rank(factor))
                score = [(a + b) / 2 for a, b in zip(h0r, fr)]
            ranked = [dict(r, score=float(s)) for r, s in zip(rows, score)]
            ranked.sort(key=lambda r: (r["score"], r["kod"]), reverse=True)
            out[name][dt] = ranked
    return out


def stat(x):
    wealth = np.cumprod(1 + x)
    dd = wealth / np.maximum.accumulate(wealth) - 1
    cagr = float(wealth[-1] ** (PPY / len(x)) - 1)
    vol = float(np.std(x, ddof=1) * math.sqrt(PPY))
    return {"cagr": round(cagr, 4), "vol": round(vol, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((cagr - RF) / vol, 3) if vol else None}


def bootstrap(a, b, seed=20260816, block=13, draws=2000):
    rng, n = np.random.default_rng(seed), len(a)
    outcomes = []
    for _ in range(draws):
        idx = []
        while len(idx) < n:
            start = rng.integers(0, n - block + 1)
            idx.extend(range(start, start + block))
        idx = np.asarray(idx[:n])
        outcomes.append(np.cumprod(1 + a[idx])[-1] ** (PPY / n) - np.cumprod(1 + b[idx])[-1] ** (PPY / n))
    d = a - b
    return {"delta_cagr": round(stat(a)["cagr"] - stat(b)["cagr"], 4),
            "ki_lo": round(float(np.percentile(outcomes, 2.5)), 4),
            "ki_hi": round(float(np.percentile(outcomes, 97.5)), 4),
            "t": round(float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))), 3) if d.std(ddof=1) else None}


def run(rankings, dates, returns, series, schedule, stack):
    previous, prev_weights, nets, caps, cash = [], {}, [], [], []
    for pi, dt in enumerate(dates):
        raw = rankings[dt]
        eligible = {r["kod"] for r in raw}
        rank = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedule(pi, dt) or not previous:
            if stack and previous:
                sel0 = [k for k in previous if k in eligible and rank.get(k, 999) <= 35]
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:N - len(sel0)]
            else:
                sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in previous if k in eligible]
            sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:N - len(sel0)]
        # The comparator is exactly the same signal's equal-weight Top-30.
        # Only Stack H applies its post-selection SMA cash sleeve.
        selected = [] if stack else list(sel0)
        features = {}
        for k in sel0:
            _, _, confirmed, vol = trailing_features(series, k, dt)
            features[k] = (confirmed, vol)
            if not stack:
                continue
            ds, adj = series.get(k, (np.array([]), np.array([])))
            i = int(np.searchsorted(ds, np.datetime64(dt), side="right")) - 1 if len(ds) else -1
            sma_ok = i < 200 or adj[i] >= float(np.mean(adj[i - 200:i]))
            if sma_ok:
                selected.append(k)
        target = len(selected) / N
        if stack and selected:
            raw_w = np.array([1 / max(features[k][1], 0.05) ** 1.5 for k in selected], dtype=float)
            raw_w *= np.array([1.0 if features[k][0] else 0.75 for k in selected])
            weights = hard_cap(raw_w, target)
            if prev_weights:
                weights = np.array([prev_weights.get(k, 0.0) if abs(weights[i] - prev_weights.get(k, 0.0)) < 0.005 and prev_weights.get(k, 0.0) > 0 else weights[i] for i, k in enumerate(selected)])
                weights = hard_cap(weights, target)
        elif selected:
            weights = np.full(len(selected), 1.0 / N)
        else:
            weights = np.array([])
        current = dict(zip(selected, weights))
        turnover = float(weights.sum()) if not previous else sum(abs(current.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in set(current) | set(prev_weights)) / 2
        gross = sum(current[k] * returns.get((k, dt), 0.0) for k in current)
        nets.append(gross - COST * turnover)
        caps.append(max(current.values()) if current else 0.0)
        cash.append(1.0 - sum(current.values()))
        previous, prev_weights = sel0, current
    return np.asarray(nets), {"max_weight": round(max(caps), 6), "cap_pass": bool(max(caps) <= CAP + 1e-12),
                              "mean_cash": round(float(np.mean(cash)), 4)}


def load_2020_2026():
    # Deliberately avoids importing the old head-to-head module: it imports
    # optional network packages and materialises a pandas target frame although
    # Stack H only needs the target-free panel calendar and adjusted prices.
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    start, end = "2021-07-16", "2026-07-10"
    dates = sorted({r["panel_date"] for r in core})
    next_date = dict(zip(dates, dates[1:]))
    by_date = defaultdict(list)
    for r in core:
        if start <= r["panel_date"] <= end:
            by_date[r["panel_date"]].append({"kod": r["kod"], "score": None})
    series26 = {k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float)) for k, rs in prices.items()}
    base26 = {}
    for dt, rows in by_date.items():
        vals = []
        for r in rows:
            ds, adj = series26.get(r["kod"], (np.array([]), np.array([])))
            now = np.datetime64(dt)
            pair = []
            for weeks in (52, 78):
                i = int(np.searchsorted(ds, now, side="right")) - 1
                j = int(np.searchsorted(ds, now - np.timedelta64(7 * weeks, "D"), side="right")) - 1
                pair.append(None if i < 0 or j < 0 or int(((now - np.timedelta64(7 * weeks, "D")) - ds[j]) / np.timedelta64(1, "D")) > 10 else float(adj[i] / adj[j] - 1))
            vals.append(pair)
        r12, r18 = pct_rank([x[0] for x in vals]), pct_rank([x[1] for x in vals])
        score = median_fill([(a + b) / 2 if a is not None and b is not None else None for a, b in zip(r12, r18)])
        ranked = [dict(r, score=float(s)) for r, s in zip(rows, score)]
        ranked.sort(key=lambda r: (r["score"], r["kod"]), reverse=True)
        base26[dt] = ranked
    ret26 = {}
    for kod, (ds, adj) in series26.items():
        for dt in sorted(base26):
            nd = next_date.get(dt)
            if not nd:
                ret26[(kod, dt)] = 0.0
                continue
            i = int(np.searchsorted(ds, np.datetime64(dt), side="right"))
            j = int(np.searchsorted(ds, np.datetime64(nd), side="right"))
            ret26[(kod, dt)] = float(adj[j] / adj[i] - 1) if i < len(adj) and j < len(adj) else 0.0
    anchor = dates.index("2024-01-26") % 2
    panel_phase = {dt: i % 2 for i, dt in enumerate(dates)}
    return base26, sorted(base26), ret26, series26, lambda pi, dt: panel_phase[dt] == anchor


def load_2014_2019():
    # Kept local: the historical price backbone is large and must not coexist
    # in memory with the 2020-2026 pandas-backed source layer.
    import h1419_motor as M
    return M.RANKNINGAR, M.PANELER, M.RET, M.SERIE, lambda pi, dt: pi % 2 == 0


def main():
    print("starting repaired Stack-H H0/H1/H2 diagnostic", flush=True)
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RUN":
        raise SystemExit("preregistration not active")
    result = {"version": "STACK_H_REPAIRED_H012_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "preregistration_sha256": sha(PRE), "diagnostic_only": True, "results": {}}
    for label, loader in (("2020_2026", load_2020_2026), ("2014_2019", load_2014_2019)):
        print(f"loading {label}", flush=True)
        base, dates, returns, series, schedule = loader()
        print(f"running {label}", flush=True)
        signals = build_rankings(base, series, label)
        result["results"][label] = {}
        for model, ranking in signals.items():
            baseline, diag_base = run(ranking, dates, returns, series, schedule, stack=False)
            repaired, diag_stack = run(ranking, dates, returns, series, schedule, stack=True)
            result["results"][label][model] = {"baseline_equal_weight": {**stat(baseline), **diag_base},
                                                 "stack_h_repaired": {**stat(repaired), **diag_stack},
                                                 "delta": bootstrap(repaired, baseline)}
            print(label, model, result["results"][label][model])
        # A checkpoint permits a bounded execution environment to resume
        # reporting without changing the preregistered calculation.
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        del base, dates, returns, series, signals
        gc.collect()
    for model in ("H0", "H1", "H2"):
        late = result["results"]["2020_2026"][model]["delta"]
        early = result["results"]["2014_2019"][model]["delta"]
        result.setdefault("decision_screen", {})[model] = {"positive_both_windows": late["delta_cagr"] > 0 and early["delta_cagr"] > 0,
                                                             "late_ci_excludes_zero": late["ki_lo"] > 0,
                                                             "cap_pass_all": all(result["results"][w][model]["stack_h_repaired"]["cap_pass"] for w in result["results"])}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["decision_screen"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
