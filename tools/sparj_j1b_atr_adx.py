#!/usr/bin/env python3
"""Run preregistered Track J J1B ATR/ADX tests. No tuning and no writes to A-H."""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from decision_portfolio_v2 import V2, annualized, dump, evaluation, ic_metrics, manifest
from decision_portfolio_v3_execution import build_portfolio, execution_returns
from spari_batch1 import alpha_class, champion_scores, extra_metrics, oos, ranked_score, blend

ROOT = V2
J = ROOT / "trackj"
OUT = J / "results/SPARJ_J1B_ATR_ADX_V1"
PREREG = J / "J1B_PREREGISTRATION.json"
COST = 0.002
N = 30
PROTECTED = ("panels", "validated", "spard", "spare", "sparf", "sparg", "trackh", "repair_df", "research_i")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protected_hashes() -> dict[str, str]:
    return {
        p.relative_to(ROOT).as_posix(): sha(p)
        for name in PROTECTED
        for p in sorted((ROOT / name).rglob("*"))
        if p.is_file()
    }


def verify_prereg() -> dict:
    prereg = json.loads(PREREG.read_text())
    assert prereg["status"] == "PREREGISTERED_BEFORE_RESULT_REVIEW"
    assert not OUT.exists(), "J1B output already exists; no overwrite"
    for rel, expected in prereg["locked_inputs"].items():
        assert sha(ROOT / rel) == expected, rel
    return prereg


def wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def weekly_indicators(rows: list[dict]) -> pd.DataFrame:
    daily = pd.DataFrame(rows)
    daily.index = pd.to_datetime(daily.pop("d"))
    weekly = daily.resample("W-FRI").agg({
        "adjusted_open": "first",
        "adjusted_high": "max",
        "adjusted_low": "min",
        "adjusted_close": "last",
    }).dropna()
    high, low, close = weekly.adjusted_high, weekly.adjusted_low, weekly.adjusted_close
    previous = close.shift(1)
    tr = pd.concat((high - low, (high - previous).abs(), (low - previous).abs()), axis=1).max(axis=1)
    atr14 = wilder(tr, 14)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=weekly.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=weekly.index)
    plus_di = 100 * wilder(plus_dm, 14) / atr14
    minus_di = 100 * wilder(minus_dm, 14) / atr14
    denominator = plus_di + minus_di
    dx = (100 * (plus_di - minus_di).abs() / denominator.replace(0, np.nan)).fillna(0)
    weekly["atr_norm_14w"] = atr14 / close
    weekly["adx_14w"] = wilder(dx, 14)
    weekly["atr_stop_10w"] = tr.rolling(10, min_periods=10).mean()
    return weekly


def load() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, list[dict]]]:
    core = json.loads((ROOT / "panels/core_panel.json").read_text())
    d = pd.DataFrame([{
        "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
        "mom_52w": r.get("mom_52w"),
    } for r in core])
    prices = json.loads((ROOT / "validated/prices/prices_validated.json").read_text())
    series = {
        k: (np.array([np.datetime64(r["d"]) for r in rows]), np.array([r["adj"] for r in rows], float))
        for k, rows in prices.items()
    }

    def momentum(k: str, day: str, weeks: int) -> float:
        dates, values = series[k]
        now = np.datetime64(day)
        goal = now - np.timedelta64(7 * weeks, "D")
        i = np.searchsorted(dates, now, "right") - 1
        j = np.searchsorted(dates, goal, "right") - 1
        if i < 0 or j < 0 or int((goal - dates[j]) / np.timedelta64(1, "D")) > 10:
            return np.nan
        return float(values[i] / values[j] - 1)

    d["mom_12m"] = [momentum(k, day, 52) for k, day in zip(d.kod, d.panel_date)]
    d["mom_18m"] = [momentum(k, day, 78) for k, day in zip(d.kod, d.panel_date)]
    assert np.nanmax(np.abs(d.mom_12m - d.mom_52w)) < 1e-12
    with gzip.open(J / "ohlc_v1/validated/ohlc_validated.json.gz", "rt", encoding="utf-8") as handle:
        ohlc = json.load(handle)
    weekly = {k: weekly_indicators(rows) for k, rows in ohlc.items()}
    feature_rows = []
    for row in d.itertuples(index=False):
        frame = weekly[row.kod]
        eligible = frame.loc[frame.index <= pd.Timestamp(row.panel_date)]
        last = eligible.iloc[-1] if len(eligible) else None
        feature_rows.append({
            "atr_norm_14w": None if last is None else float(last.atr_norm_14w),
            "adx_14w": None if last is None else float(last.adx_14w),
        })
    features = pd.DataFrame(feature_rows)
    d = pd.concat((d.reset_index(drop=True), features), axis=1)
    return d, weekly, prices


def assess(scores: pd.DataFrame, name: str, targets: pd.DataFrame, returns_map: dict, execution_meta: dict) -> tuple[dict, dict]:
    sample = oos(scores)
    ic = ic_metrics(sample, targets, n=N)
    portfolio, artifacts = build_portfolio(
        sample, n=N, every=2, cost=COST, model=name,
        returns_map=returns_map, execution_meta=execution_meta,
    )
    portfolio, contribution = extra_metrics(portfolio, artifacts, returns_map)
    return {"ic": ic, "portfolio": portfolio, "ticker_contribution": contribution}, artifacts


def first_after(rows: list[dict], boundary: str) -> dict | None:
    return next((row for row in rows if row["d"] > boundary), None)


def atr_stop_portfolio(
    scores: pd.DataFrame,
    weekly: dict[str, pd.DataFrame],
    daily: dict[str, list[dict]],
    returns_map: dict,
    execution_meta: dict,
) -> tuple[dict, dict]:
    sample = oos(scores)
    baseline_metrics, baseline = build_portfolio(
        sample, n=N, every=2, cost=COST, model="H0_reference_for_ATR_stop",
        returns_map=returns_map, execution_meta=execution_meta,
    )
    baseline_hold = collections.defaultdict(list)
    for row in baseline["holdings"]:
        baseline_hold[row["panel_date"]].append(row["kod"])
    dates = sorted(sample.panel_date.unique())
    active: set[str] = set()
    peak: dict[str, float] = {}
    stopped_until_rebalance: set[str] = set()
    holdings, trades, periods, components = [], [], [], []
    contribution = collections.defaultdict(float)
    previous_baseline: set[str] = set()

    for ix, day in enumerate(dates):
        # Use the frozen global next-panel boundary from execution metadata.
        # The last OOS decision still has an evaluable boundary in 2026.
        boundary = next((execution_meta.get((k, day), {}).get("next_panel_date") for k in baseline_hold[day] if execution_meta.get((k, day), {}).get("next_panel_date")), None)
        baseline_ids = set(baseline_hold[day])
        rebalance = ix % 2 == 0 or not previous_baseline
        if rebalance:
            target = baseline_ids
            stopped_until_rebalance.clear()
        else:
            target = baseline_ids - stopped_until_rebalance
        sells = sorted(active - target)
        buys = sorted(target - active)
        for k in sells:
            trades.append({"model": "atr_stop_2p5_atr10", "panel_date": day, "kod": k, "side": "SELL_SCHEDULED", "decision_date": day, "execution_price_date": execution_meta.get((k, day), {}).get("entry_execution_date")})
            peak.pop(k, None)
        for k in buys:
            meta = execution_meta.get((k, day), {})
            trades.append({"model": "atr_stop_2p5_atr10", "panel_date": day, "kod": k, "side": "BUY", "decision_date": day, "execution_price_date": meta.get("entry_execution_date"), "execution_price_adjusted": meta.get("entry_price_adjusted")})
            if meta.get("entry_price_adjusted") is not None:
                peak[k] = float(meta["entry_price_adjusted"])
        active = set(target)
        for k in sorted(active):
            holdings.append({"model": "atr_stop_2p5_atr10", "panel_date": day, "kod": k, "weight": 1 / N, "rebalance": rebalance})
        if not boundary:
            break

        scheduled_cost = COST * len([k for k in buys if execution_meta.get((k, day), {}).get("entry_strictly_after_decision")]) / N
        period_component: dict[str, float] = {}
        stop_cost = 0.0
        stopped_now: list[str] = []
        for k in sorted(active):
            meta = execution_meta.get((k, day), {})
            entry_date = meta.get("entry_execution_date")
            entry_price = meta.get("entry_price_adjusted")
            stop_row = None
            if entry_date and entry_price:
                frame = weekly[k]
                checks = frame[(frame.index > pd.Timestamp(entry_date)) & (frame.index < pd.Timestamp(boundary))]
                local_peak = peak.get(k, float(entry_price))
                for check_day, row in checks.iterrows():
                    close = float(row.adjusted_close)
                    local_peak = max(local_peak, close)
                    atr = row.atr_stop_10w
                    if pd.notna(atr) and close <= local_peak - 2.5 * float(atr):
                        candidate = first_after(daily[k], check_day.date().isoformat())
                        normal_exit = meta.get("exit_valuation_date")
                        if candidate and (not normal_exit or candidate["d"] < normal_exit):
                            stop_row = candidate
                        break
                peak[k] = local_peak
            if stop_row is not None:
                value = float(stop_row["adj"]) / float(entry_price) - 1
                stopped_now.append(k)
                stopped_until_rebalance.add(k)
                stop_cost += COST / N
                trades.append({
                    "model": "atr_stop_2p5_atr10", "panel_date": day, "kod": k,
                    "side": "ATR_STOP", "trigger_rule": "weekly_close <= peak_close_since_entry - 2.5*ATR10",
                    "execution_price_date": stop_row["d"], "execution_price_adjusted": stop_row["adj"],
                    "execution_strictly_after_trigger": True,
                })
                peak.pop(k, None)
            else:
                value = returns_map.get((k, day), 0.0)
            period_component[k] = value / N
            contribution[k] += value / N
        gross = float(sum(period_component.values()))
        transaction_cost = scheduled_cost + stop_cost
        net = gross - transaction_cost
        benchmark_return = next(row["benchmark_return"] for row in baseline["returns"] if row["panel_date"] == day)
        periods.append({
            "model": "atr_stop_2p5_atr10", "panel_date": day, "gross_return": gross,
            "net_return": net, "benchmark_return": benchmark_return,
            "turnover": scheduled_cost / COST + stop_cost / COST,
            "transaction_cost": transaction_cost, "n_holdings_start": len(active),
            "atr_stops": len(stopped_now), "rebalance": rebalance,
        })
        components.append({"panel_date": day, "returns": period_component})
        active -= set(stopped_now)
        previous_baseline = baseline_ids

    net = np.array([row["net_return"] for row in periods], float)
    gross = np.array([row["gross_return"] for row in periods], float)
    benchmark = np.array([row["benchmark_return"] for row in periods], float)
    excess = net - benchmark
    wealth = np.cumprod(1 + net)
    drawdown = wealth / np.maximum.accumulate(wealth) - 1
    ranked = sorted(contribution.items(), key=lambda item: item[1], reverse=True)

    def leave(count: int) -> float:
        excluded = {k for k, _ in ranked[:count]}
        returns = []
        for period, component in zip(periods, components):
            returns.append(sum(v for k, v in component["returns"].items() if k not in excluded) - period["transaction_cost"])
        return annualized(returns)

    positive_market = benchmark > 0
    negative_market = benchmark < 0
    metrics = {
        "cagr_net": annualized(net.tolist()), "cagr_gross": annualized(gross.tolist()),
        "benchmark_cagr": annualized(benchmark.tolist()),
        "annualized_excess": annualized(net.tolist()) - annualized(benchmark.tolist()),
        "sharpe_excess": float(excess.mean() / excess.std(ddof=1) * math.sqrt(13)),
        "max_drawdown": float(drawdown.min()),
        "mean_turnover": float(np.mean([row["turnover"] for row in periods])),
        "total_transaction_cost": float(sum(row["transaction_cost"] for row in periods)),
        "n_atr_stops": sum(row["atr_stops"] for row in periods),
        "upside_capture": float(net[positive_market].mean() / benchmark[positive_market].mean()) if positive_market.any() else None,
        "downside_capture": float(net[negative_market].mean() / benchmark[negative_market].mean()) if negative_market.any() else None,
        "leave_top3_out_cagr": leave(3), "leave_top5_out_cagr": leave(5),
        "top3_tickers": [k for k, _ in ranked[:3]], "top5_tickers": [k for k, _ in ranked[:5]],
        "scheduled_H0_rankings_unchanged": True,
        "baseline_H0_metrics": baseline_metrics,
    }
    return metrics, {"rankings": baseline["rankings"], "holdings": holdings, "trades": trades, "returns": periods, "period_components": components}


def main() -> None:
    prereg = verify_prereg()
    before = protected_hashes()
    d, weekly, daily = load()
    targets = evaluation(d)
    returns_map, execution_meta = execution_returns()
    champion = champion_scores(d)
    pure_12m = ranked_score(d, "mom_52w")
    references, artifacts = {}, {"rankings": [], "holdings": [], "trades": [], "returns": []}
    for name, scores in (("pure_12m", pure_12m), ("H0_frozen_champion", champion)):
        references[name], built = assess(scores, name, targets, returns_map, execution_meta)
        for key in artifacts:
            artifacts[key].extend(built[key])

    results = {}
    definitions = (("atr_normalized_risk", "atr_norm_14w", -1.0), ("adx_trend_strength", "adx_14w", 1.0))
    for name, column, direction in definitions:
        factor = d[["kod", "panel_date", column]].copy()
        factor[column] *= direction
        factor = ranked_score(factor, column)
        combined = blend(champion, factor)
        solo, solo_art = assess(factor, name + "_solo", targets, returns_map, execution_meta)
        blended, blend_art = assess(combined, name + "_blend", targets, returns_map, execution_meta)
        classification = alpha_class(blended, references["H0_frozen_champion"])
        results[name] = {"classification": classification, "solo": solo, "blend": blended}
        for built in (solo_art, blend_art):
            for key in artifacts:
                artifacts[key].extend(built[key])

    stop_metrics, stop_artifacts = atr_stop_portfolio(champion, weekly, daily, returns_map, execution_meta)
    base = references["H0_frozen_champion"]["portfolio"]
    full_risk = (
        stop_metrics["sharpe_excess"] > base["sharpe_excess"]
        and stop_metrics["max_drawdown"] >= base["max_drawdown"] + 0.01
        and stop_metrics["annualized_excess"] >= base["annualized_excess"] - 0.02
        and (stop_metrics["leave_top3_out_cagr"] - stop_metrics["benchmark_cagr"])
            >= (base["leave_top3_out_cagr"] - base["benchmark_cagr"]) - 0.01
        and (stop_metrics["leave_top5_out_cagr"] - stop_metrics["benchmark_cagr"])
            >= (base["leave_top5_out_cagr"] - base["benchmark_cagr"]) - 0.01
    )
    partial_risk = stop_metrics["sharpe_excess"] > base["sharpe_excess"] or stop_metrics["max_drawdown"] > base["max_drawdown"]
    results["atr_trailing_stop"] = {
        "classification": "STÖD — RISK" if full_risk else ("SVAGT STÖD" if partial_risk else "INGET STÖD"),
        "portfolio": stop_metrics,
    }
    for key in artifacts:
        artifacts[key].extend(stop_artifacts[key])

    results["references"] = references
    results["multiple_testing"] = {
        "families": 3, "alpha_factor_definitions": 2,
        "alpha_score_variants_reviewed": 4, "risk_variants_reviewed": 1,
        "parameter_search": False, "all_results_retained": True,
    }
    OUT.mkdir(parents=True)
    for name, payload in results.items():
        dump(OUT / f"{name}.json", payload)
    for name, payload in artifacts.items():
        dump(OUT / f"{name}.json", payload)
    dump(OUT / "atr_stop_period_components.json", stop_artifacts["period_components"])
    after = protected_hashes()
    scope = {
        "status": "PASS" if before == after else "FAIL",
        "files": len(before),
        "before_aggregate": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "after_aggregate": hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest(),
        "changed": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
    }
    dump(OUT / "protected_scope_audit.json", scope)
    assert before == after
    dump(OUT / "run_provenance.json", {
        "run_id": prereg["run_id"], "preregistration_sha256": sha(PREREG),
        "input_hashes": prereg["locked_inputs"], "code_sha256": sha(Path(__file__)),
        "decision_rows": len(d), "target_evaluation_rows": len(targets),
        "oos_panel_dates": sorted(oos(champion).panel_date.unique()),
        "target_never_used_for_selection": True,
        "H0_H1_H2_modified": False,
    })
    dump(OUT / "manifest.json", manifest(OUT))
    print(json.dumps({"status": "COMPLETE", "out": str(OUT), "classifications": {k: v["classification"] for k, v in results.items() if isinstance(v, dict) and "classification" in v}}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
