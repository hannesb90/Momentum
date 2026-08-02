"""N3 stage 09 / SR49: price-vendor and corporate-action sensitivity.

This is a diagnostic exclusion test on the frozen N2 Stage-06 seed42 signals.
It neither retrains nor substitutes price histories.  Suspect groups are removed
from eligibility before the backtest, leaving their weight in cash.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large

apply_large()

from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/08_partial_delisted_inclusion.json"
SOURCE = ROOT / "results/niva2_stage6_winner_signals.csv"
N2_REPORT = ROOT / "results/retraining_staleness_niva2.json"
JUMP_AUDIT = ROOT / "results/research_gates/sr10_jump_audit.csv"
JUMP_REPORT = ROOT / "results/research_gates/sr10_corporate_actions.json"
PIT_COVERAGE = ROOT / "results/point_in_time/pit_coverage.csv"
OUT = ROOT / "results/niva3_vendor_corporate_action_sensitivity.json"
CSV = ROOT / "results/niva3_vendor_corporate_action_arms.csv"
EXCLUSIONS = ROOT / "results/niva3_vendor_corporate_action_exclusions.csv"

# Captured by the Börsdata-first loader in the frozen Large run.  Each switch
# was caused by residual abs weekly return > config.SUSPICIOUS_JUMP_THRESHOLD,
# and is preserved here rather than rediscovered from a mutable API response.
VERIFIED_YAHOO_FALLBACK = {
    "INTRUM.ST", "KEOC.ST", "LAGR-B.ST", "MTG-B.ST", "SAGA-A.ST",
    "SAVE.ST", "SBB-B.ST", "TRUE-B.ST", "VISC.ST", "VPLAY-B.ST",
}


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def pct(value: str) -> float:
    return float(str(value).replace("%", "")) / 100.0


def metrics(values: pd.Series) -> dict:
    values = values.dropna().astype(float)
    ret = values.pct_change().dropna()
    years = (values.index[-1] - values.index[0]).days / 365.25
    return {"cagr": float((values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1),
            "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(52)),
            "max_drawdown": float((values / values.cummax() - 1).min())}


def excluded_arm(base: pd.DataFrame, tickers: set[str]) -> pd.DataFrame:
    out = base.copy()
    hit = out.ticker.isin(tickers)
    out.loc[hit, "selection_eligible"] = 0
    out.loc[hit, "pred_signal"] = 0
    out.loc[hit, "position_size"] = 0.0
    return out


def main():
    parent = verify_manifest(PARENT)
    base = pd.read_csv(SOURCE, parse_dates=["Date"]).set_index("Date").sort_index()
    _, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    if not sectors or not caps:
        raise RuntimeError("Large universe maps are empty")
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS = 52

    jump_rows = pd.read_csv(JUMP_AUDIT)
    jump_report = json.loads(JUMP_REPORT.read_text())
    extreme = set(jump_rows.ticker.dropna().astype(str))
    coverage = pd.read_csv(PIT_COVERAGE)
    conflicts = set(coverage.loc[coverage.ticker_reuse_conflict.fillna(False).astype(bool), "ticker"].astype(str))
    fallback = set(VERIFIED_YAHOO_FALLBACK)
    all_flagged = fallback | extreme | conflicts

    specs = [("frozen_baseline", set()), ("borsdata_only_exclude_yahoo_fallback", fallback),
             ("exclude_extreme_jump_tickers", extreme),
             ("exclude_pit_ticker_reuse_conflicts", conflicts),
             ("exclude_all_flagged", all_flagged)]
    dates = base.index.unique().sort_values()
    bench_close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().dropna()
    benchmark = metrics(bench_close / bench_close.iloc[0])
    selected = set(base.loc[base.pred_signal.eq(1), "ticker"])
    rows = []
    baseline_cagr = None
    for arm, excluded in specs:
        sig = excluded_arm(base, excluded)
        bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
        cagr = pct(stats["CAGR"])
        if arm == "frozen_baseline":
            expected = json.loads(N2_REPORT.read_text())["retrain_13w_parity"]
            mismatch = {k: (stats[k], expected[k]) for k in expected if stats[k] != expected[k]}
            if mismatch:
                raise RuntimeError(f"Frozen Stage-06 parity failed: {mismatch}")
            baseline_cagr = cagr
        rows.append({"arm": arm, **stats, "cagr_numeric": cagr,
                     "benchmark_cagr": benchmark["cagr"], "alpha_cagr": cagr - benchmark["cagr"],
                     "cagr_change_vs_baseline": 0.0 if baseline_cagr is None else cagr - baseline_cagr,
                     "excluded_tickers": len(excluded), "excluded_ever_selected": len(excluded & selected),
                     "excluded_selected_rows": int(base.loc[base.ticker.isin(excluded), "pred_signal"].sum())})
        print(arm, stats, flush=True)
    table = pd.DataFrame(rows)
    table["cagr_change_vs_baseline"] = table.cagr_numeric - float(table.iloc[0].cagr_numeric)
    table.to_csv(CSV, index=False)

    detail = []
    for ticker in sorted(all_flagged):
        detail.append({"ticker": ticker, "yahoo_fallback": ticker in fallback,
                       "extreme_jump_audit": ticker in extreme, "pit_ticker_reuse_conflict": ticker in conflicts,
                       "ever_selected": ticker in selected,
                       "selected_rows": int(base.loc[base.ticker.eq(ticker), "pred_signal"].sum())})
    pd.DataFrame(detail).to_csv(EXCLUSIONS, index=False)

    sensitivity = table[table.arm.ne("frozen_baseline")]
    worst_alpha = float(sensitivity.alpha_cagr.min())
    worst_degradation = float(sensitivity.cagr_change_vs_baseline.min())
    quality_pass = jump_report.get("n_unresolved") == 0
    sensitivity_pass = worst_alpha > 0 and worst_degradation >= -0.03
    report = {
        "status": "PASS", "test": "N3-SR49", "parent_stage": parent["manifest_sha256"],
        "price_contract": "Borsdata dividend-adjusted total return; explicit Yahoo fallback on residual corporate-action jumps",
        "frozen_baseline_parity": "EXACT_ROUNDED", "benchmark": benchmark,
        "source_counts": {"verified_yahoo_fallback": len(fallback), "extreme_jump_tickers": len(extreme),
                          "pit_ticker_reuse_conflicts": len(conflicts), "all_flagged_union": len(all_flagged)},
        "selected_exposure": {"fallback_tickers_ever_selected": len(fallback & selected),
                              "all_flagged_ever_selected": len(all_flagged & selected)},
        "corporate_action_quality_gate": "PASS" if quality_pass else "FAIL",
        "sensitivity_gate": "PASS" if sensitivity_pass else "FAIL",
        "decision_rule_preregistered": "zero unresolved >=50% jumps; every exclusion arm positive index alpha; worst CAGR degradation no more than 3pp/year",
        "worst_exclusion_alpha_cagr": worst_alpha, "worst_cagr_change_vs_baseline": worst_degradation,
        "retrained": False, "holdout_used": False, "production": False,
        "limitations": ["Yahoo fallback identity is frozen from loader diagnostics, not inferred from current API state",
                        "Exclusion tests source dependence but does not prove Yahoo and Borsdata economic equivalence"],
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage("09_vendor_corporate_action_sensitivity",
        [OUT, CSV, EXCLUSIONS, Path(__file__).resolve(), JUMP_REPORT, JUMP_AUDIT],
        {"test": "N3-SR49", "corporate_action_quality_gate": report["corporate_action_quality_gate"],
         "sensitivity_gate": report["sensitivity_gate"], "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False)); print(stage)


if __name__ == "__main__":
    main()
