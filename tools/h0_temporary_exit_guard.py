"""Pre-registered temporary-exit guard diagnostic on frozen H0 rankings."""
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

PRE = V2 / "research_k/H0_TEMPORARY_EXIT_GUARD_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_temporary_exit_guard_results.json"
N, MAX_GUARDS, COST = 30, 5, 0.002


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def price_at(series, kod, day):
    ds, values = series.get(kod, (np.array([]), np.array([])))
    index = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    return float(values[index]) if index >= 0 else None


def sma_ok(series, kod, day):
    ds, values = series.get(kod, (np.array([]), np.array([])))
    index = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    return bool(index < 120 or values[index] >= float(np.mean(values[index - 120:index]))) if index >= 0 else False


def simulate(rankings, dates, returns, entry, series, schedule, guard):
    prior, entry_day, exit_price = [], {}, {}
    values, turns, guard_events, reentries, higher_reentries = [], [], 0, 0, 0
    for i, day in enumerate(dates):
        ranked = rankings[day]
        rank = {row["kod"]: j + 1 for j, row in enumerate(ranked)}
        if not prior or schedule(i, day):
            baseline = [row["kod"] for row in ranked[:N]]
            guarded = []
            if guard and prior:
                # Market return since a holding's true entry is measured from
                # the entry-date universe and prices known at this decision.
                for kod in prior:
                    r = rank.get(kod, 10**9)
                    start = entry_day.get(kod)
                    if not (31 <= r <= 45 and start is not None and sma_ok(series, kod, day)):
                        continue
                    stock_start, stock_now = entry.get((kod, start)), price_at(series, kod, day)
                    if not stock_start or not stock_now:
                        continue
                    universe_returns = []
                    for row in rankings[start]:
                        other_start, other_now = entry.get((row["kod"], start)), price_at(series, row["kod"], day)
                        if other_start and other_now:
                            universe_returns.append(other_now / other_start - 1)
                    if universe_returns and stock_now / stock_start - 1 > float(np.median(universe_returns)):
                        guarded.append(kod)
                guarded = sorted(set(guarded), key=lambda k: rank[k])[:MAX_GUARDS]
            current = baseline[:N - len(guarded)] + guarded
            removed, bought = set(prior) - set(current), set(current) - set(prior)
            for kod in removed:
                exit_price[kod] = entry.get((kod, day))
                entry_day.pop(kod, None)
            for kod in bought:
                if kod in exit_price:
                    reentries += 1
                    before, now = exit_price[kod], entry.get((kod, day))
                    higher_reentries += int(before is not None and now is not None and now > before)
                entry_day[kod] = day
            guard_events += len(guarded)
            turnover = len(bought) / N
            prior = current
        else:
            turnover = 0.0
        values.append(sum(returns.get((kod, day), 0.0) for kod in prior) / N - COST * turnover)
        turns.append(turnover)
    return np.asarray(values), {"mean_one_way_turnover": round(float(np.mean(turns)), 4),
                                "total_one_way_turnover": round(float(np.sum(turns)), 4),
                                "guarded_holding_events": guard_events, "reentry_count": reentries,
                                "higher_price_reentry_count": higher_reentries}


def loaders():
    rankings, dates, returns, entry, schedule = BASE.late_loader()
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    late_series = {k: (np.array([np.datetime64(x["d"]) for x in rs]), np.array([x["adj"] for x in rs], float)) for k, rs in prices.items()}
    yield "2021_2026", rankings, dates, returns, entry, late_series, schedule
    import h1419_motor as M
    rankings, dates, returns, entry, schedule = BASE.early_loader()
    yield "2014_2019", rankings, dates, returns, entry, M.SERIE, schedule


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RUN":
        raise SystemExit("preregistration inactive")
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "preregistration_sha256": sha(PRE), "diagnostic_only": True, "results": {}}
    for label, rankings, dates, returns, entry, series, schedule in loaders():
        print(f"running {label}", flush=True)
        base, base_diag = simulate(rankings, dates, returns, entry, series, schedule, False)
        variant, variant_diag = simulate(rankings, dates, returns, entry, series, schedule, True)
        result["results"][label] = {"baseline_h0": {**STATS.stat(base), **base_diag},
                                     "temporary_exit_guard": {**STATS.stat(variant), **variant_diag},
                                     "delta": STATS.bootstrap(variant, base)}
        print(label, result["results"][label]["delta"], flush=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    early, late = result["results"]["2014_2019"], result["results"]["2021_2026"]
    result["decision_screen"] = {
        "positive_both_windows": all(x["delta"]["delta_cagr"] > 0 for x in (early, late)),
        "ci_excludes_zero_both": all(x["delta"]["ki_lo"] > 0 for x in (early, late)),
        "turnover_lower_both": all(x["temporary_exit_guard"]["total_one_way_turnover"] < x["baseline_h0"]["total_one_way_turnover"] for x in (early, late)),
        "higher_price_reentry_lower_both": all(x["temporary_exit_guard"]["higher_price_reentry_count"] < x["baseline_h0"]["higher_price_reentry_count"] for x in (early, late))}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["decision_screen"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
