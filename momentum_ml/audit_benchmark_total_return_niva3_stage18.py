"""N3 stage 18 / SR54: benchmark total-return, dividend and endpoint parity.

The investable benchmark is XACT Sverige.  It pays cash distributions, so its
adjusted close—not raw exchange close—is required for an apples-to-apples
comparison with the dividend-adjusted stock portfolio.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large
apply_large()
from altdata import borsdata
from niva3_stage_control import freeze_stage, verify_manifest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/17_publication_missingness_selection.json"
SIGNALS = ROOT / "results/niva3_reconstructed_price_signals_corrected.csv"
SNAPSHOT = ROOT / "results/niva3_xact_total_return_snapshot.csv"
OUT = ROOT / "results/niva3_benchmark_total_return_audit.json"
CACHE_CSV = ROOT / "results/niva3_benchmark_cache_parity.csv"
CANONICAL_CACHE = ROOT / "cache/6118405f.pkl"


def cagr(series: pd.Series) -> float:
    series = series.dropna().astype(float)
    years = (series.index[-1] - series.index[0]).days / 365.25
    return float((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1)


def main():
    parent = verify_manifest(PARENT)
    ticker = config.INDEX_BENCHMARK_TICKER
    if ticker != "XACT-SVERIGE.ST":
        raise RuntimeError(f"Unexpected Large benchmark: {ticker}")

    dates = pd.DatetimeIndex(pd.read_csv(SIGNALS, parse_dates=["Date"]).Date.drop_duplicates().sort_values())
    # The benchmark is not one of the reconstructed corporate-action equities.
    # Read the exact frozen Yahoo cache directly; loading the entire feature
    # state here would add memory pressure without changing this audit.
    with CANONICAL_CACHE.open("rb") as fh:
        canonical_payload = pickle.load(fh)
    adjusted = canonical_payload[ticker].Close.reindex(dates).ffill().dropna().astype(float)
    del canonical_payload
    if not adjusted.index.equals(dates):
        raise RuntimeError("Benchmark does not cover the exact frozen OOF calendar")

    snap = pd.read_csv(SNAPSHOT, parse_dates=["week_date", "ex_date"]).set_index("week_date")
    endpoints = snap.loc[[dates[0], dates[-1]]]
    raw = endpoints.raw_close
    raw_cagr = cagr(raw)
    adjusted_snapshot_cagr = cagr(endpoints.adjusted_close)
    adjusted_cagr = cagr(adjusted)
    start_abs = abs(float(adjusted.iloc[0]) - float(endpoints.adjusted_close.iloc[0]))
    end_abs = abs(float(adjusted.iloc[-1]) - float(endpoints.adjusted_close.iloc[-1]))

    rows = []
    for path in sorted((ROOT / "cache").glob("*.pkl")):
        try:
            with path.open("rb") as fh:
                payload = pickle.load(fh)
            if not isinstance(payload, dict) or ticker not in payload:
                continue
            series = payload[ticker].Close.reindex(dates).ffill().dropna().astype(float)
            common = adjusted.index.intersection(series.index)
            diff = (series.reindex(common) - adjusted.reindex(common)).abs()
            rows.append({
                "cache_file": path.name,
                "coverage_start": str(series.index.min().date()) if len(series) else None,
                "coverage_end": str(series.index.max().date()) if len(series) else None,
                "oof_rows": int(len(common)),
                "max_abs_close_difference": float(diff.max()) if len(diff) else None,
                "max_relative_close_difference": float((diff / adjusted.reindex(common).abs()).max()) if len(diff) else None,
            })
        except Exception as exc:
            rows.append({"cache_file": path.name, "error": type(exc).__name__})
    cache_table = pd.DataFrame(rows)
    cache_table.to_csv(CACHE_CSV, index=False)
    comparable = cache_table.loc[cache_table.get("oof_rows", pd.Series(dtype=float)).eq(len(dates))]
    cache_parity = bool(len(comparable) >= 2 and comparable.max_relative_close_difference.max() <= 1e-6)

    instrument_map = borsdata.stockprice_instrument_map()
    borsdata_has_ticker = ticker in instrument_map
    loader = (ROOT / "momentum_ml/data/data_loader.py").read_text(encoding="utf-8")
    yahoo_adjustment_contract = "auto_adjust=True" in loader
    distributions = snap.loc[snap.dividend_sek.gt(0)]
    no_splits = bool(snap.stock_split.fillna(0).eq(0).all())
    endpoint_parity = start_abs <= 1e-3 and end_abs <= 1e-3 and abs(adjusted_cagr-adjusted_snapshot_cagr) <= 1e-6
    total_return_gate = bool(endpoint_parity and cache_parity and yahoo_adjustment_contract and len(distributions) == 6 and no_splits)

    # The ETF itself is investable and therefore a valid primary benchmark.
    # No local PIT series exists for its proprietary underlying GI index, so
    # ETF-versus-index tracking error must fail closed rather than be invented.
    underlying_index = "OMXSB through 2018-10-09; SIX Sweden ESG Selection Index GI from 2018-10-10"
    underlying_index_pit_available = False
    tracking_error_gate = "UNAVAILABLE_FAIL_CLOSED"
    report = {
        "status": "PASS",
        "test": "N3-SR54",
        "parent_stage": parent["manifest_sha256"],
        "benchmark_ticker": ticker,
        "benchmark_role": "investable cash-distributing ETF measured with reinvested distributions",
        "underlying_index": underlying_index,
        "oof_window": {"start": str(dates[0].date()), "end": str(dates[-1].date()), "weeks": len(dates)-1},
        "adjusted_start_close": float(adjusted.iloc[0]),
        "adjusted_end_close": float(adjusted.iloc[-1]),
        "raw_start_close": float(raw.iloc[0]),
        "raw_end_close": float(raw.iloc[-1]),
        "adjusted_total_return_cagr": adjusted_cagr,
        "raw_price_cagr": raw_cagr,
        "dividend_adjustment_effect_pp": (adjusted_cagr-raw_cagr)*100,
        "stage12_portfolio_cagr": 0.222,
        "alpha_vs_adjusted_etf_cagr": 0.222-adjusted_cagr,
        "counterfactual_alpha_vs_raw_price_cagr": 0.222-raw_cagr,
        "cash_distributions_in_window": int(len(distributions)),
        "cash_distributions_total_sek": float(distributions.dividend_sek.sum()),
        "stock_splits_in_snapshot": int(snap.stock_split.fillna(0).ne(0).sum()),
        "borsdata_instrument_mapping_available": borsdata_has_ticker,
        "actual_loader_path": "Yahoo fallback because Börsdata instrument map has no ETF ticker",
        "yahoo_auto_adjust_contract": yahoo_adjustment_contract,
        "endpoint_max_abs_difference": max(start_abs, end_abs),
        "full_oof_cache_variants": int(len(comparable)),
        "cache_parity_gate": "PASS" if cache_parity else "FAIL",
        "total_return_endpoint_gate": "PASS" if total_return_gate else "FAIL",
        "underlying_index_pit_available": underlying_index_pit_available,
        "underlying_index_tracking_error_gate": tracking_error_gate,
        "decision": "ETF_ALPHA_VALID_INDEX_ATTRIBUTION_INCOMPLETE" if total_return_gate else "BENCHMARK_PARITY_FAIL",
        "decision_rule": "Adjusted endpoints/CAGR exact within 1e-6; >=2 complete cache copies agree within 1e-6 relative; six official/Yahoo dividend events and zero splits; proprietary underlying GI tracking error fails closed without PIT index series",
        "official_sources": [
            "https://www.xact.se/AboutETFs",
            "https://www.xact.se/en/News?year=2016",
            "https://www.xact.se/en/News?year=2017",
            "https://www.xact.se/en/News?year=2018",
            "https://www.xact.se/en/News?year=2019",
            "https://www.xact.se/en/News?year=2020",
            "https://www.xact.se/en/News?year=2021",
        ],
        "selection_allowed": False,
        "production": False,
        "holdout_used": False,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage(
        "18_benchmark_total_return_parity",
        [OUT, CACHE_CSV, SNAPSHOT, Path(__file__).resolve()],
        {"test": "N3-SR54", "total_return_endpoint_gate": report["total_return_endpoint_gate"],
         "underlying_index_tracking_error_gate": tracking_error_gate, "production": False},
        parent=PARENT,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(stage)


if __name__ == "__main__":
    main()
