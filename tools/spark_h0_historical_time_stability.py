"""Locked historical robustness analysis of immutable H0. No model development."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

V2 = Path("/home/hannesb/momentum_v2")
PREREG = V2 / "research_k/H0_HISTORICAL_TIME_STABILITY_PREREGISTRATION.json"
OUT = V2 / "research_k/h0_historical_time_stability_v1"
START = "2021-07-16"
PHASE_ANCHOR = "2024-01-26"
COST = 0.002
N = 30


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def finite(x):
    return None if x is None or not math.isfinite(float(x)) else float(x)


def annualized(values):
    if not values:
        return None
    wealth = float(np.prod(1 + np.asarray(values, dtype=float)))
    return -1.0 if wealth <= 0 else wealth ** (13 / len(values)) - 1


def derive_scores(core, prices):
    series = {
        k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    def momentum(k, dt, weeks):
        ds, values = series[k]
        now = np.datetime64(dt)
        target = now - np.timedelta64(7 * weeks, "D")
        i = np.searchsorted(ds, now, side="right") - 1
        j = np.searchsorted(ds, target, side="right") - 1
        if i < 0 or j < 0 or int((target - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(values[i] / values[j] - 1)

    by_date = defaultdict(list)
    for r in core:
        if r["panel_date"] < START:
            continue
        m12 = momentum(r["kod"], r["panel_date"], 52)
        m18 = momentum(r["kod"], r["panel_date"], 78)
        by_date[r["panel_date"]].append({"kod": r["kod"], "panel_date": r["panel_date"], "mom_12m": m12, "mom_18m": m18})

    rankings, coverage = {}, []
    for dt, rows in sorted(by_date.items()):
        for col in ("mom_12m", "mom_18m"):
            valid = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            ranks = {}
            # Average percentile rank, matching pandas rank(pct=True), ascending.
            grouped = defaultdict(list)
            for value, kod in valid:
                grouped[value].append(kod)
            pos = 1
            for value in sorted(grouped):
                ks = grouped[value]
                avg = (pos + pos + len(ks) - 1) / 2 / len(valid)
                for kod in ks:
                    ranks[kod] = avg
                pos += len(ks)
            for r in rows:
                r[col + "_rank"] = ranks.get(r["kod"])
        raw = [0.5 * (r["mom_12m_rank"] + r["mom_18m_rank"]) if r["mom_12m_rank"] is not None and r["mom_18m_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raw if x is not None]))
        scored = []
        for r, value in zip(rows, raw):
            scored.append({**r, "score": med if value is None else value, "score_imputed": value is None})
        scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        for i, r in enumerate(scored, 1):
            r["rank"] = i
        rankings[dt] = scored
        coverage.append({
            "panel_date": dt,
            "n": len(rows),
            "mom12_available": sum(r["mom_12m"] is not None for r in rows),
            "mom18_available": sum(r["mom_18m"] is not None for r in rows),
            "combined_imputed": sum(r["score_imputed"] for r in scored),
        })
    return rankings, coverage


def execution_maps(core, prices, terminal):
    dates = sorted({r["panel_date"] for r in core})
    next_date = dict(zip(dates, dates[1:]))
    returns, meta = {}, {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        adj = {r["d"]: r["adj"] for r in rs}

        def first_after(boundary):
            return next((d for d in ds if d > boundary), None)

        for dt in dates:
            nd = next_date.get(dt)
            entry = first_after(dt)
            if not nd:
                meta[(kod, dt)] = {"next_panel_date": None, "entry_date": entry, "status": "NO_NEXT_PANEL"}
                continue
            if not entry or entry > nd:
                returns[(kod, dt)] = 0.0
                meta[(kod, dt)] = {"next_panel_date": nd, "entry_date": entry, "status": "UNFILLED"}
                continue
            exit_date = first_after(nd)
            event = terminal.get(kod)
            if exit_date:
                returns[(kod, dt)] = adj[exit_date] / adj[entry] - 1
                status = "POST_DECISION_CLOSE_TO_NEXT_POST_DECISION_CLOSE"
            elif event and entry <= event["event_date"] <= nd:
                exit_date = ds[-1]
                returns[(kod, dt)] = adj[exit_date] / adj[entry] - 1
                status = "VERIFIED_TERMINAL_EXIT"
            else:
                returns[(kod, dt)] = 0.0
                status = "NO_VERIFIABLE_EXIT_CASH_ZERO"
            meta[(kod, dt)] = {"next_panel_date": nd, "entry_date": entry, "exit_date": exit_date, "status": status}
    return returns, meta, dates


def build_portfolio(rankings, returns_map, meta, all_dates):
    anchor_parity = all_dates.index(PHASE_ANCHOR) % 2
    previous, holdings, periods, trades = [], {}, [], []
    for dt in sorted(rankings):
        scheduled = all_dates.index(dt) % 2 == anchor_parity
        universe = rankings[dt]
        universe_codes = {r["kod"] for r in universe}
        if scheduled:
            selected = [r["kod"] for r in universe[:N]]
        elif previous:
            selected = [k for k in previous if k in universe_codes]
            selected += [r["kod"] for r in universe if r["kod"] not in selected][: N - len(selected)]
        else:
            # Preserve frozen phase: do not invent an initial off-phase rebalance.
            continue
        buys = sorted(set(selected) - set(previous))
        sells = sorted(set(previous) - set(selected))
        executed_buys = [k for k in buys if meta.get((k, dt), {}).get("entry_date", "") > dt]
        for k in buys:
            trades.append({"panel_date": dt, "kod": k, "side": "BUY", "execution_date": meta.get((k, dt), {}).get("entry_date")})
        for k in sells:
            trades.append({"panel_date": dt, "kod": k, "side": "SELL"})
        holdings[dt] = selected
        evaluable = any(meta.get((r["kod"], dt), {}).get("next_panel_date") for r in universe)
        if evaluable:
            gross = sum(returns_map.get((k, dt), 0.0) for k in selected) / N
            turnover = len(executed_buys) / N
            benchmark = float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in universe]))
            periods.append({
                "panel_date": dt,
                "gross_return": gross,
                "net_return": gross - COST * turnover,
                "benchmark_return": benchmark,
                "turnover": turnover,
                "scheduled_8w_rebalance": scheduled,
                "n_holdings": len(selected),
            })
        previous = selected
    return holdings, periods, trades


def ic_rows(rankings, target):
    target_map = {(k, r["panel_date"]): r.get("target_fwd52w") for k, rs in target.items() for r in rs}
    out = []
    for dt, ranked in sorted(rankings.items()):
        available = [(r, target_map.get((r["kod"], dt))) for r in ranked]
        available = [(r, y) for r, y in available if y is not None]
        all_ic = finite(spearmanr([r["score"] for r, _ in available], [y for _, y in available]).statistic) if len(available) > 2 else None
        # Evaluation-only Top-30 definition used by frozen D/F/G: first remove
        # observations without observable target, then take the score Top-30.
        # This never feeds back into decision rankings or holdings.
        selected = available[:N]
        top_ic = finite(spearmanr([r["score"] for r, _ in selected], [y for _, y in selected]).statistic) if len(selected) > 2 and len({r["score"] for r, _ in selected}) > 1 else None
        if available:
            out.append({"panel_date": dt, "n": len(available), "n_top30": len(selected), "ic52": all_ic, "top30_ic52": top_ic})
    return out


def summarize(name, start, end, periods, ic, holdings, returns_map):
    ps = [p for p in periods if start <= p["panel_date"] <= end]
    ii = [r for r in ic if start <= r["panel_date"] <= end]
    nr = [p["net_return"] for p in ps]
    br = [p["benchmark_return"] for p in ps]
    excess = np.asarray(nr) - np.asarray(br)
    wealth = np.cumprod(1 + np.asarray(nr)) if nr else np.array([])
    dd = wealth / np.maximum.accumulate(wealth) - 1 if len(wealth) else np.array([])
    contribution = defaultdict(float)
    for p in ps:
        for k in holdings[p["panel_date"]]:
            contribution[k] += returns_map.get((k, p["panel_date"]), 0.0) / N
    ranked = sorted(contribution.items(), key=lambda x: x[1], reverse=True)

    def leave(count):
        excluded = {k for k, _ in ranked[:count]}
        vals = []
        previous = []
        for p in ps:
            ids = [k for k in holdings[p["panel_date"]] if k not in excluded]
            buys = [k for k in ids if k not in previous]
            vals.append(sum(returns_map.get((k, p["panel_date"]), 0.0) for k in ids) / N - COST * len(buys) / N)
            previous = ids
        return annualized(vals)

    arithmetic_excess = float(np.sum(excess)) if len(excess) else 0.0
    def share(k):
        numerator = sum(v for _, v in ranked[:k])
        return None if abs(arithmetic_excess) < 1e-12 else numerator / arithmetic_excess

    iv = [r["ic52"] for r in ii if r["ic52"] is not None]
    tv = [r["top30_ic52"] for r in ii if r["top30_ic52"] is not None]
    return {
        "name": name,
        "start": start,
        "end": end,
        "ranking": {
            "n_ic_panels": len(iv), "mean_ic52": finite(np.mean(iv)) if iv else None,
            "median_ic52": finite(np.median(iv)) if iv else None,
            "mean_top30_ic52": finite(np.mean(tv)) if tv else None,
            "positive_ic_share": finite(np.mean(np.asarray(iv) > 0)) if iv else None,
        },
        "portfolio": {
            "n_return_panels": len(ps),
            "n_actual_8w_rebalances": sum(p.get("scheduled_8w_rebalance", p.get("rebalance", False)) for p in ps),
            "cagr": annualized(nr), "benchmark_cagr": annualized(br),
            "excess_cagr": None if not nr else annualized(nr) - annualized(br),
            "sharpe_excess": finite(excess.mean() / excess.std(ddof=1) * math.sqrt(13)) if len(excess) > 1 and excess.std(ddof=1) > 0 else None,
            "max_drawdown": finite(dd.min()) if len(dd) else None,
            "mean_turnover": finite(np.mean([p["turnover"] for p in ps])) if ps else None,
            "low_statistical_power": sum(p.get("scheduled_8w_rebalance", p.get("rebalance", False)) for p in ps) < 5,
        },
        "robustness": {
            "leave_top1_cagr": leave(1), "leave_top3_cagr": leave(3), "leave_top5_cagr": leave(5),
            "top1_tickers": [k for k, _ in ranked[:1]], "top3_tickers": [k for k, _ in ranked[:3]], "top5_tickers": [k for k, _ in ranked[:5]],
            "top1_arithmetic_excess_share": finite(share(1)), "top3_arithmetic_excess_share": finite(share(3)), "top5_arithmetic_excess_share": finite(share(5)),
        },
    }


def main():
    prereg_hash = sha(PREREG)
    core_path = V2 / "panels/core_panel.json"
    target_path = V2 / "panels/target_table.json"
    prices_path = V2 / "validated/prices/prices_validated.json"
    terminal_path = V2 / "validated/terminal_events.json"
    core = json.loads(core_path.read_text())
    prices = json.loads(prices_path.read_text())
    terminal = json.loads(terminal_path.read_text())
    target = json.loads(target_path.read_text())
    rankings, coverage = derive_scores(core, prices)
    ret, execution_meta, all_dates = execution_maps(core, prices, terminal)
    holdings, periods, trades = build_portfolio(rankings, ret, execution_meta, all_dates)
    ic = ic_rows(rankings, target)

    first_return, last_return = periods[0]["panel_date"], periods[-1]["panel_date"]
    specs = [("pre_2024", START, "2023-12-29"), ("full_history", START, "2026-07-10"), ("champion_2024_2025_continuous_slice", "2024-01-26", "2025-12-26")]
    for year in range(2021, 2027):
        specs.append((f"calendar_{year}", f"{year}-01-01", f"{year}-12-31"))
    summaries = [summarize(*s, periods, ic, holdings, ret) for s in specs]
    frozen_g_returns_path = V2 / "sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3/returns.json"
    frozen_g_periods = json.loads(frozen_g_returns_path.read_text())
    summaries.append(summarize("champion_2024_2025_frozen_standalone", "2024-01-26", "2025-12-26", frozen_g_periods, ic, holdings, ret))

    pdates = [p["panel_date"] for p in periods]
    rolling12 = [summarize(f"rolling12_{pdates[i]}_{pdates[i+12]}", pdates[i], pdates[i+12], periods, ic, holdings, ret) for i in range(len(pdates) - 12)]
    rolling24 = [summarize(f"rolling24_{pdates[i]}_{pdates[i+25]}", pdates[i], pdates[i+25], periods, ic, holdings, ret) for i in range(len(pdates) - 25)]

    macro = json.loads((V2 / "spare/macro_v1/macro_panel.json").read_text())
    regimes = []
    for year in range(2021, 2027):
        rows = [r for r in macro if str(year) == r["panel_date"][:4] and START <= r["panel_date"] <= "2026-07-10"]
        if not rows:
            continue
        def avg(key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return finite(np.mean(vals)) if vals else None
        regimes.append({"year": year, "n_panels": len(rows), "mean_se_market_ret12m": avg("se_market_ret12m"), "mean_se_market_vol3m": avg("se_market_vol3m"), "mean_policy_rate": avg("policy_rate_level"), "mean_policy_rate_d12m": avg("policy_rate_d12m"), "mean_vix": avg("vix_level")})

    pre = next(x for x in summaries if x["name"] == "pre_2024")
    champ = next(x for x in summaries if x["name"] == "champion_2024_2025_frozen_standalone")
    independent_24m = len(periods) // 26
    full = next(x for x in summaries if x["name"] == "full_history")
    # D/G already treated >50% dependence on a few tickers as fragility. This
    # operationalizes the preregistered phrase "without one ticker set
    # dominating"; it is not a new H0 acceptance rule or parameter search.
    top5_dominates = abs(full["robustness"]["top5_arithmetic_excess_share"] or 0) > 0.50
    if independent_24m < 2:
        classification = "OTILLRÄCKLIG HISTORIK"
    elif (pre["portfolio"]["excess_cagr"] or 0) <= 0 and (pre["ranking"]["mean_ic52"] or 0) <= 0 and (champ["portfolio"]["excess_cagr"] or 0) > 0:
        classification = "2024–2025-DOMINERAD"
    else:
        annual = [x for x in summaries if x["name"].startswith("calendar_") and not x["portfolio"]["low_statistical_power"]]
        pos_excess = sum((x["portfolio"]["excess_cagr"] or 0) > 0 for x in annual)
        pos_ic = sum((x["ranking"]["mean_ic52"] or 0) > 0 for x in annual if x["ranking"]["n_ic_panels"])
        classification = "BRED HISTORISK TIDSSTABILITET" if pos_excess >= max(3, len(annual)-1) and pos_ic >= max(3, len(annual)-1) and not top5_dominates else "BLANDAD TIDSSTABILITET"

    inventory = {
        "methodological_status": "HISTORICAL ROBUSTNESS — NOT UNTOUCHED FORWARD",
        "data_and_feature_development": "2020-01-03 through 2026-07-10 panels were available to V2 audits/builds; none are untouched after research completion.",
        "model_training": "2020-2022/2023 observations used in D walk-forward training according to split-specific 52w embargo.",
        "validation": "calendar 2023 was explicit validation and influenced research decisions.",
        "champion_selection": "2024-01-26 through 2025-07-11 target-observable OOS panels and portfolio returns through 2025-12-26 influenced F/G/K decisions.",
        "later_research_exposure": "Research E-K and data/implementation audits examined outcomes and artifacts through the pre-freeze history; historical extension is not untouched validation.",
        "untouched_forward": "separate protocol; first eligible panel remains 2026-09-04 and is not read or modified here."
    }

    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "data_history_and_research_exposure.json", inventory)
    dump(OUT / "score_coverage.json", coverage)
    dump(OUT / "ic_per_date.json", ic)
    dump(OUT / "portfolio_periods.json", periods)
    dump(OUT / "historical_rankings.json", [r for dt in sorted(rankings) for r in rankings[dt]])
    dump(OUT / "historical_holdings.json", [{"panel_date": dt, "kod": k, "weight": 1/N} for dt in sorted(holdings) for k in holdings[dt]])
    dump(OUT / "historical_trades.json", trades)
    dump(OUT / "fixed_windows.json", summaries)
    dump(OUT / "rolling_12m.json", rolling12)
    dump(OUT / "rolling_24m.json", rolling24)
    dump(OUT / "regime_diagnostic.json", regimes)
    result = {
        "classification": classification,
        "methodological_status": "HISTORICAL ROBUSTNESS — NOT UNTOUCHED FORWARD",
        "first_possible_h0_decision": START,
        "first_phase_compatible_rebalance": first_return,
        "last_historical_decision": max(rankings),
        "last_evaluable_return_panel": last_return,
        "last_observable_ic_panel": max(r["panel_date"] for r in ic),
        "total_actual_8w_rebalances": sum(p["scheduled_8w_rebalance"] for p in periods),
        "independent_24m_equivalents": independent_24m,
        "classification_diagnostics": {
            "full_history_top5_arithmetic_excess_share": full["robustness"]["top5_arithmetic_excess_share"],
            "top5_concentration_dominates_under_inherited_D_G_50pct_rule": top5_dominates
        },
        "fixed_windows": summaries,
        "rolling_12m_count": len(rolling12),
        "rolling_24m_count": len(rolling24),
        "preregistration_sha256": prereg_hash,
    }
    dump(OUT / "result.json", result)
    files = []
    for path in sorted(OUT.glob("*.json")):
        if path.name != "manifest.json":
            files.append({"path": path.relative_to(V2).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
    manifest = {
        "analysis_id": "H0_HISTORICAL_TIME_STABILITY_V1",
        "immutable_h0_changed": False,
        "forward_journal_changed": False,
        "preregistration": {"path": PREREG.relative_to(V2).as_posix(), "sha256": prereg_hash},
        "inputs": {p.relative_to(V2).as_posix(): sha(p) for p in (core_path, target_path, prices_path, terminal_path, V2 / "repair_df/FREEZE_MANIFEST.json", V2 / "spare/macro_v1/macro_panel.json", frozen_g_returns_path, Path(__file__))},
        "outputs": files,
    }
    manifest["aggregate_sha256"] = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    dump(OUT / "manifest.json", manifest)
    print(json.dumps({"classification": classification, "first": first_return, "last": last_return, "rebalances": result["total_actual_8w_rebalances"], "manifest": sha(OUT / "manifest.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
