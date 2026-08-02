"""Append one independent weekly mark-to-market observation for Stage 07."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config
from research_gates_common import apply_large

apply_large()

from data.data_loader import fetch_weekly_data
from niva2_stage_control import verify_manifest


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "results/niva2_stages/07_forward_preregistration.json"
DIR = ROOT / "results/niva2_forward"
PROTOCOL = DIR / "protocol.json"
INITIAL = DIR / "initial_candidate_signal.csv"
PRODUCTION = DIR / "initial_production_signal.csv"
LEDGER = DIR / "weekly_ledger.jsonl"
STATUS = DIR / "status.json"


def _positions(path, date_column=True):
    frame = pd.read_csv(path, parse_dates=["Date"] if date_column else None)
    frame = frame[frame.pred_signal.eq(1)][["ticker", "position_size"]].copy()
    if frame.empty or abs(float(frame.position_size.sum()) - 1.0) > 1e-6:
        raise RuntimeError(f"Invalid frozen weights: {path}")
    return dict(zip(frame.ticker, frame.position_size.astype(float)))


def _nav(weights, prices, start, current, capital, entry_cost):
    gross = 0.0
    missing = []
    for ticker, weight in weights.items():
        frame = prices.get(ticker)
        if frame is None or "Close" not in frame:
            missing.append(ticker); continue
        p0 = frame.Close.asof(start); p1 = frame.Close.asof(current)
        if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
            missing.append(ticker); continue
        gross += weight * float(p1 / p0)
    if missing:
        raise RuntimeError(f"Missing frozen holding prices; no partial NAV allowed: {missing}")
    return capital * (1.0 - entry_cost) * gross


def main():
    verify_manifest(STAGE)
    protocol = json.loads(PROTOCOL.read_text())
    start = pd.Timestamp(protocol["start_date"])
    minimum_end = pd.Timestamp(protocol["minimum_end_date"])
    candidate = _positions(INITIAL); production = _positions(PRODUCTION)
    benchmark = config.INDEX_BENCHMARK_TICKER
    tickers = sorted(set(candidate) | set(production) | {benchmark})
    prices = fetch_weekly_data(tickers, start=str((start - pd.Timedelta(weeks=104)).date()),
                               end=None, use_cache=True)
    if benchmark not in prices or prices[benchmark].empty:
        raise RuntimeError("Benchmark price missing; fail closed")
    current = pd.Timestamp(prices[benchmark].index.max())
    records = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    if any(pd.Timestamp(row["date"]) == current for row in records):
        result = {"status": "NO_NEW_WEEK", "latest_date": str(current.date()),
                  "observations": len(records), "production_changed": False}
        STATUS.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2)); return
    if current < start:
        raise RuntimeError("Latest market date precedes forward start")
    entry_cost = float(config.COMMISSION + config.SLIPPAGE)
    capital = float(protocol["initial_capital_sek"])
    candidate_nav = _nav(candidate, prices, start, current, capital, entry_cost)
    production_nav = _nav(production, prices, start, current, capital, entry_cost)
    b0 = float(prices[benchmark].Close.asof(start)); b1 = float(prices[benchmark].Close.asof(current))
    benchmark_nav = capital * (1.0 - entry_cost) * b1 / b0
    weeks = int(round((current - start).days / 7))
    status = "ROTATION_DUE" if current >= minimum_end else "ACTIVE_INSUFFICIENT_FORWARD"
    row = {"date": str(current.date()), "observation": len(records) + 1,
           "observed_calendar_weeks": weeks, "status": status,
           "candidate_nav": candidate_nav, "production_nav": production_nav,
           "benchmark_nav": benchmark_nav, "entry_cost_each_arm": entry_cost,
           "candidate_alpha_nav": candidate_nav - benchmark_nav,
           "candidate_vs_production_nav": candidate_nav - production_nav,
           "production_changed": False}
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {**row, "observations": len(records) + 1,
               "note": "ROTATION_DUE is not PASS; explicit frozen-model refit/rotation required"}
    STATUS.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
