"""Pre-registered contrarian exposure overlay on the frozen H1 signal."""
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
import stack_h_repaired_h012 as H

COST, N, PPY = 0.002, 30, 13.0
SIGN_MODE = "--sign" in sys.argv
PRE = V2 / ("research_k/H1_CONTRARIAN_SIGN_EXPOSURE_PREREGISTRATION.json" if SIGN_MODE
            else "research_k/H1_CONTRARIAN_EXPOSURE_PREREGISTRATION.json")
OUT = V2 / ("research_k/h1_contrarian_sign_exposure_results.json" if SIGN_MODE
            else "research_k/h1_contrarian_exposure_results.json")
THRESHOLD = 0.0 if SIGN_MODE else 0.20


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def market_return_26w(series, dt):
    now, then = np.datetime64(dt), np.datetime64(dt) - np.timedelta64(182, "D")
    values = []
    for ds, adj in series.values():
        i = int(np.searchsorted(ds, now, side="right")) - 1
        j = int(np.searchsorted(ds, then, side="right")) - 1
        if i >= 0 and j >= 0 and adj[j] > 0:
            values.append(float(adj[i] / adj[j] - 1))
    return float(np.median(values)) if values else None


def components(rankings, dates, returns, schedule, exposure_fn):
    previous, prev_weights, net, states = [], {}, [], []
    for pi, dt in enumerate(dates):
        raw = rankings[dt]
        eligible = {r["kod"] for r in raw}
        if schedule(pi, dt) or not previous:
            selected = [r["kod"] for r in raw[:N]]
        else:
            selected = [k for k in previous if k in eligible]
            selected += [r["kod"] for r in raw if r["kod"] not in selected][:N-len(selected)]
        market_ret = exposure_fn(dt)
        exposure = 0.0 if market_ret is not None and market_ret >= THRESHOLD else 1.0
        current = {k: exposure / N for k in selected}
        turnover = (float(sum(current.values())) if not prev_weights else
                    sum(abs(current.get(k, 0.0) - prev_weights.get(k, 0.0))
                        for k in set(current) | set(prev_weights)) / 2)
        gross = sum(w * returns.get((k, dt), 0.0) for k, w in current.items())
        net.append(gross - COST * turnover)
        states.append({"date": dt, "market_return_26w": market_ret,
                       "exposure": exposure})
        previous, prev_weights = selected, current
    return np.asarray(net), states


def run_window(label, loader):
    print(f"loading {label}", flush=True)
    H.FEATURE_CACHE.clear()
    base, dates, returns, series, schedule = loader()
    print(f"ranking H1 {label}", flush=True)
    h1 = H.build_rankings(base, series, label)["H1"]
    market = {dt: market_return_26w(series, dt) for dt in dates}
    baseline, _ = components(h1, dates, returns, schedule, lambda dt: None)
    overlay, states = components(h1, dates, returns, schedule, lambda dt: market[dt])
    strong = [s for s in states if s["exposure"] == 0]
    return {"baseline_h1_equal_weight": H.stat(baseline),
            "contrarian_cash_after_strong": H.stat(overlay),
            "delta": H.bootstrap(overlay, baseline),
            "state_counts": {"all_panels": len(states), "cash_strong_panels": len(strong),
                             "h1_exposed_panels": len(states) - len(strong)},
            "states": states}


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RUN":
        raise SystemExit("preregistration not active")
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "preregistration_sha256": sha(PRE), "diagnostic_only": True, "results": {}}
    for label, loader in (("2020_2026", H.load_2020_2026), ("2014_2019", H.load_2014_2019)):
        result["results"][label] = run_window(label, loader)
        print(label, result["results"][label]["delta"], result["results"][label]["state_counts"], flush=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    a, b = result["results"]["2014_2019"], result["results"]["2020_2026"]
    result["decision_screen"] = {
        "positive_both_windows": a["delta"]["delta_cagr"] > 0 and b["delta"]["delta_cagr"] > 0,
        "ci_excludes_zero_both": a["delta"]["ki_lo"] > 0 and b["delta"]["ki_lo"] > 0,
        "minimum_state_count_pass": min(a["state_counts"]["cash_strong_panels"], b["state_counts"]["cash_strong_panels"]) >= 5
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["decision_screen"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
