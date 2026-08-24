"""Descriptive calendar-year review for the frozen H0 V3 production canonical.

This is a reporting-only replay of the already activated production path.  It
does not offer parameters, variants, or model-selection decisions.  Each
panel return is assigned to the calendar year of its decision date and covers
the canonical [t, t+1] interval.  Alpha is the annualized H0 COST_B net return
less the annualized NASDAQOMXS30GI gross-total-return return over identical
complete cohorts; it is an active-return measure, not a CAPM regression alpha.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import h0_v3_production as PROD

OUT = ROOT / "research_k/h0_v3_canonical_production_implementation"
CHECKPOINT = OUT / "PRODUCTION_CHECKPOINT_FINALIZATION.json"
INDEX = ROOT / "research_k/omxs30gi_cashflow_alpha_audit/NASDAQOMXS30GI_raw.csv"
CSV_OUT = OUT / "PRODUCTION_CALENDAR_YEAR_REVIEW_OMXS30GI.csv"
MD_OUT = OUT / "PRODUCTION_CALENDAR_YEAR_REVIEW_OMXS30GI.md"
JSON_OUT = OUT / "PRODUCTION_CALENDAR_YEAR_REVIEW_OMXS30GI.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index():
    dates, values = [], []
    for row in csv.DictReader(INDEX.open()):
        if row["NASDAQOMXS30GI"]:
            dates.append(np.datetime64(row["observation_date"]))
            values.append(float(row["NASDAQOMXS30GI"]))
    return np.array(dates), np.array(values, dtype=float)


def index_panel_return(dates, values, start: str, end: str) -> float:
    """Same after-start / through-end convention as the canonical return map."""
    i = int(np.searchsorted(dates, np.datetime64(start), side="right"))
    j = int(np.searchsorted(dates, np.datetime64(end), side="right"))
    if i >= len(dates) or j - 1 < i or values[i] <= 0:
        raise RuntimeError(f"OMXS30GI coverage missing for canonical panel {start} -> {end}")
    return float(values[j - 1] / values[i] - 1.0)


def max_drawdown(rets):
    nav = np.cumprod(1.0 + np.asarray(rets, dtype=float))
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0)) if len(nav) else 0.0


def stats(model_rets, index_rets, days, annualize):
    m = np.asarray(model_rets, dtype=float)
    b = np.asarray(index_rets, dtype=float)
    model_return = float(np.prod(1.0 + m) - 1.0)
    index_return = float(np.prod(1.0 + b) - 1.0)
    vol = float(np.std(m, ddof=1) * math.sqrt(13)) if len(m) > 1 else float("nan")
    sharpe = float(np.mean(m) / np.std(m, ddof=1) * math.sqrt(13)) if len(m) > 1 and np.std(m, ddof=1) else float("nan")
    factor = 365.25 / days if annualize else 1.0
    model_cagr = float((1.0 + model_return) ** factor - 1.0)
    index_cagr = float((1.0 + index_return) ** factor - 1.0)
    return {
        "model_cost_b_period_return": model_return,
        "omxs30gi_period_return": index_return,
        "model_cost_b_cagr": model_cagr,
        "omxs30gi_cagr": index_cagr,
        "alpha_active_cagr": model_cagr - index_cagr,
        "model_maxdd": max_drawdown(m),
        "model_vol_annualized": vol,
        "model_sharpe_annualized_rf0": sharpe,
    }


def main():
    checkpoint = json.loads(CHECKPOINT.read_text())
    if not checkpoint.get("all_gates_pass"):
        raise RuntimeError("Production checkpoint is not PASS; refusing report.")
    if checkpoint.get("architecture") != PROD.ARCHITECTURE_ID:
        raise RuntimeError("Production architecture differs from checkpoint.")

    index_dates, index_values = load_index()
    PROD.load_engine()
    rows, reproducibility = [], {}
    for window in ("W1", "W2"):
        result = PROD.replay(window)
        path = PROD.path_hash(window, result)["sha256"]
        expected = checkpoint["evidence"]["path_hashes"][window]["production_sha256"]
        if path != expected:
            raise RuntimeError(f"{window} production path hash drift: {path} != {expected}")
        panels = result["panels"]
        panel_dates = [p["date"] for p in panels]
        returns = result["ret_lists"]["net_b"]
        by_year = defaultdict(list)
        for i, panel in enumerate(panels[:-1]):
            start, end = panel["date"], panels[i + 1]["date"]
            by_year[int(start[:4])].append((start, float(returns[i]), index_panel_return(index_dates, index_values, start, end)))
        for year in sorted(by_year):
            observations = by_year[year]
            m = [x[1] for x in observations]
            b = [x[2] for x in observations]
            end_date = panel_dates[panel_dates.index(observations[-1][0]) + 1]
            days = int((np.datetime64(end_date) - np.datetime64(observations[0][0])).astype(int))
            annualize = len(observations) >= 12 and days >= 330
            coverage = (f"CANONICAL_{len(observations)}_PANEL_COHORT" if annualize
                        else "PARTIAL_COHORT_NOT_ANNUALIZED")
            x = stats(m, b, days, annualize)
            rows.append({
                "window": window, "decision_year": year, "n_scored_panels": len(observations),
                "coverage": coverage, "covered_days": days,
                "first_panel": observations[0][0], "last_panel": observations[-1][0],
                **x,
            })
        reproducibility[window] = {"path_sha256": path, "expected_production_path_sha256": expected, "pass": path == expected}

    fields = list(rows[0])
    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    metadata = {
        "report": "H0_V3_PRODUCTION_CANONICAL_CALENDAR_YEAR_REVIEW_OMXS30GI",
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "architecture": PROD.ARCHITECTURE_ID,
        "scope": "descriptive reporting only; no model or parameter changes",
        "return_timing": "Each row includes canonical [t,t+1] returns labelled by decision-date calendar year; final unscored panel excluded.",
        "cost": "Model uses canonical COST_B = 0.002 * actual executed weight turnover. OMXS30GI is an index gross-total-return series without a trading-cost deduction.",
        "benchmark": "NASDAQOMXS30GI, OMX Stockholm 30 Gross Index (SEK, dividends reinvested).",
        "alpha_definition": "Annualized model COST_B net return minus annualized OMXS30GI return over the same panels when coverage is at least 330 days and 12 panels; otherwise actual-period active return. This is active return, not regression alpha.",
        "sharpe_definition": "mean 4-week COST_B net return / sample std * sqrt(13), risk-free rate 0; short annual samples are descriptive.",
        "checkpoint_sha256": sha256(CHECKPOINT), "index_source_sha256": sha256(INDEX),
        "reproducibility": reproducibility, "rows": rows,
    }
    JSON_OUT.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# H0 V3 production canonical — calendar-year review vs OMXS30GI",
        "", "Reporting-only replay of the activated canonical architecture. Alpha is annualized COST_B-net active return against NASDAQOMXS30GI for complete cohorts, and actual-period active return for the short final cohort; it is not regression alpha.", "",
        "| Window | Year | Panels | Days | Coverage | CAGR / return | MaxDD | Sharpe | OMXS30GI | Alpha |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['window']} | {r['decision_year']} | {r['n_scored_panels']} | {r['covered_days']} | {r['coverage']} | {r['model_cost_b_cagr']:.2%} | {r['model_maxdd']:.2%} | {r['model_sharpe_annualized_rf0']:.2f} | {r['omxs30gi_cagr']:.2%} | {r['alpha_active_cagr']:+.2%} |")
    lines += ["", "Method: row labels use the decision-date year and each return covers canonical [t,t+1]. Cohorts with at least 12 panels and 330 days are annualized by actual covered days; the short 2026 cohort is actual-to-date return, not a CAGR.", "", f"Inputs SHA256: checkpoint `{metadata['checkpoint_sha256']}`; OMXS30GI raw series `{metadata['index_source_sha256']}`."]
    MD_OUT.write_text("\n".join(lines) + "\n")
    print(json.dumps({"csv": str(CSV_OUT), "json": str(JSON_OUT), "rows": len(rows), "path_hashes": reproducibility}, indent=2))


if __name__ == "__main__":
    main()
