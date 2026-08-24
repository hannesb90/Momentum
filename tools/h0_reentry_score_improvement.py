"""Pre-registered score-improvement re-entry diagnostic for H0."""
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
import stack_h_repaired_h012 as STATS

PRE = V2 / "research_k/H0_REENTRY_SCORE_IMPROVEMENT_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_reentry_score_improvement_results.json"
N, COST, THRESHOLD = 30, 0.002, 0.10


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def simulate(rankings, dates, returns, entry_prices, scheduled, require_improvement):
    previous, exit_score, last_sell_price = [], {}, {}
    values, turnovers, reentries, higher_reentries, blocked = [], [], 0, 0, 0
    for i, day in enumerate(dates):
        ranked = rankings[day]
        score = {r["kod"]: float(r["score"]) for r in ranked}
        if not previous or scheduled(i, day):
            old = set(previous)
            chosen = []
            for row in ranked:
                kod = row["kod"]
                if kod in old or kod not in exit_score or not require_improvement or score[kod] >= exit_score[kod] + THRESHOLD:
                    chosen.append(kod)
                else:
                    blocked += 1
                if len(chosen) == N:
                    break
            if len(chosen) < N:
                raise RuntimeError(f"not enough eligible names on {day}")
            removed = old - set(chosen)
            for kod in removed:
                exit_score[kod] = score.get(kod, exit_score.get(kod, float("inf")))
                last_sell_price[kod] = entry_prices.get((kod, day))
            bought = set(chosen) - old
            for kod in bought:
                if kod in exit_score:
                    reentries += 1
                    prior_price, buy_price = last_sell_price.get(kod), entry_prices.get((kod, day))
                    higher_reentries += int(prior_price is not None and buy_price is not None and buy_price > prior_price)
            turnover = len(bought) / N
            previous = chosen
        else:
            turnover = 0.0
        gross = sum(returns.get((kod, day), 0.0) for kod in previous) / N
        values.append(gross - COST * turnover)
        turnovers.append(turnover)
    return np.asarray(values), {"mean_one_way_turnover": round(float(np.mean(turnovers)), 4),
                                "total_one_way_turnover": round(float(np.sum(turnovers)), 4),
                                "reentry_count": reentries, "blocked_candidate_count": blocked,
                                "higher_price_reentry_count": higher_reentries}


def late_loader():
    import spark_h0_historical_time_stability as H
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    rankings, _ = H.derive_scores(core, prices)
    returns, meta, all_dates = H.execution_maps(core, prices, terminal)
    dates = sorted(rankings)
    entry = {(kod, day): next((x["adj"] for x in rs if x["d"] == info.get("entry_date")), None)
             for kod, rs in prices.items() for day in dates if (info := meta.get((kod, day)))}
    anchor = all_dates.index(H.PHASE_ANCHOR) % 2
    phase = {day: all_dates.index(day) % 2 == anchor for day in dates}
    return rankings, dates, returns, entry, lambda i, day: phase[day]


def early_loader():
    import h1419_motor as H
    entry = {}
    for kod, (days, values) in H.SERIE.items():
        for day in H.PANELER:
            idx = int(np.searchsorted(days, np.datetime64(day), side="right"))
            entry[(kod, day)] = float(values[idx]) if idx < len(values) else None
    return H.RANKNINGAR, H.PANELER, H.RET, entry, lambda i, day: i % 2 == 0


def run_window(label, loader):
    print(f"loading {label}", flush=True)
    rankings, dates, returns, entry, schedule = loader()
    base, base_diag = simulate(rankings, dates, returns, entry, schedule, False)
    gated, gated_diag = simulate(rankings, dates, returns, entry, schedule, True)
    return {"baseline_h0": {**STATS.stat(base), **base_diag},
            "score_improvement_reentry": {**STATS.stat(gated), **gated_diag},
            "delta": STATS.bootstrap(gated, base)}


def main():
    pre = json.loads(PRE.read_text())
    if pre["status"] != "PREREGISTERED_BEFORE_RUN":
        raise SystemExit("preregistration inactive")
    result = {"version": pre["version"], "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "preregistration_sha256": sha(PRE), "diagnostic_only": True, "results": {}}
    for label, loader in (("2021_2026", late_loader), ("2014_2019", early_loader)):
        result["results"][label] = run_window(label, loader)
        print(label, result["results"][label]["delta"], flush=True)
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    early, late = result["results"]["2014_2019"], result["results"]["2021_2026"]
    result["decision_screen"] = {
        "positive_both_windows": all(x["delta"]["delta_cagr"] > 0 for x in (early, late)),
        "ci_excludes_zero_both": all(x["delta"]["ki_lo"] > 0 for x in (early, late)),
        "turnover_lower_both": all(x["score_improvement_reentry"]["total_one_way_turnover"] < x["baseline_h0"]["total_one_way_turnover"] for x in (early, late))
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["decision_screen"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
