"""N3 stage 03 / SR46: decompose the frozen Large eligibility gate.

This is diagnostic after the N3-02 architecture failure.  It does not revive
or tune a calendar phase.  All arms use the same frozen scores, inverse-vol75
sizing and calendar52 execution.  The historical holdout has no vote.
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
from tune_sizing_niva2_stage4 import _vol_map


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/03_calendar52_phase_corrected.json"
SOURCE = ROOT / "results/niva2_stage6_winner_signals.csv"
OUT = ROOT / "results/niva3_eligibility_decomposition.json"
CSV = ROOT / "results/niva3_eligibility_decomposition_arms.csv"
THRESHOLDS = (0.00, 0.05, 0.10, 0.15, 0.20)
RANDOM_SEEDS = (11, 29, 47)


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _feature_map(features: dict, column: str, dates: pd.DatetimeIndex) -> pd.Series:
    rows = []
    for ticker, frame in features.items():
        if column not in frame:
            continue
        x = frame[[column]].copy()
        x.index = pd.to_datetime(x.index)
        x = x[x.index.isin(dates)]
        x["ticker"] = ticker
        x.index.name = "Date"
        rows.append(x.reset_index())
    if not rows:
        raise RuntimeError(f"No feature values found for {column}")
    out = pd.concat(rows, ignore_index=True)
    return out.set_index(["Date", "ticker"])[column]


def _attach_components(signals: pd.DataFrame, features: dict, fund_tickers: set[str]) -> pd.DataFrame:
    x = signals.copy()
    key = pd.MultiIndex.from_arrays([x.index, x.ticker])
    mom = _feature_map(features, "mom_12_1", x.index.unique())
    x["mom_12_1"] = mom.reindex(key).to_numpy()
    x["gate_expected"] = x.pred_return.gt(float(config.MIN_EXPECTED_RETURN))
    x["gate_fund"] = ~x.ticker.isin(fund_tickers)
    x["gate_momentum"] = x.mom_12_1.gt(0.10)
    reconstructed = x.gate_expected & x.gate_fund & x.gate_momentum
    observed = x.selection_eligible.astype(bool)
    mismatch = int((reconstructed != observed).sum())
    if mismatch:
        examples = x.loc[reconstructed != observed,
                         ["ticker", "pred_return", "mom_12_1", "selection_eligible"]].head().to_dict("records")
        raise RuntimeError(f"Frozen eligibility cannot be reproduced: {mismatch} mismatches; {examples}")
    return x


def _random_matched_mask(base: pd.DataFrame, seed: int) -> pd.Series:
    """Random eligibility with exactly the frozen eligible count per date."""
    out = pd.Series(False, index=np.arange(len(base)))
    rng = np.random.default_rng(seed)
    for _, pos in base.groupby(level=0, sort=False).indices.items():
        pos = np.asarray(pos, dtype=int)
        n = int(base.iloc[pos].selection_eligible.sum())
        if n:
            out.iloc[rng.choice(pos, size=min(n, len(pos)), replace=False)] = True
    return out


def _build_arm(base: pd.DataFrame, eligible: np.ndarray, vol: pd.Series) -> pd.DataFrame:
    x = base.copy()
    x["position_size"] = 0.0
    x["pred_signal"] = 0
    x["_arm_eligible"] = np.asarray(eligible, dtype=bool)
    key = pd.MultiIndex.from_arrays([x.index, x.ticker])
    x["_vol13"] = vol.reindex(key).to_numpy()
    for _, pos in x.groupby(level=0, sort=False).indices.items():
        pos = np.asarray(pos, dtype=int)
        g = x.iloc[pos]
        chosen = (g[g._arm_eligible]
                  .sort_values(["selection_rank", "prob_up", "prob_raw"], ascending=False)
                  .head(config.MAX_POSITIONS))
        if chosen.empty:
            continue
        inv = 1.0 / chosen._vol13.fillna(0.20).clip(lower=0.05).to_numpy()
        inv = inv / float(inv.sum())
        mixed = 0.25 * (1.0 / len(chosen)) + 0.75 * inv
        # Frozen Large uses MOMENTUM_GATE_MODE="cash": if fewer than MAX_POSITIONS
        # qualify, invested exposure is n/MAX_POSITIONS rather than renormalized
        # to 100%.  Omitting this scale silently creates a different portfolio.
        mixed = np.minimum(
            mixed * min(len(chosen) / float(config.MAX_POSITIONS), 1.0),
            float(config.MAX_POSITION),
        )
        selected_pos = pos[g.ticker.isin(set(chosen.ticker)).to_numpy()]
        # Tickers are unique within a date; preserve the chosen sort order via a map.
        weight_map = dict(zip(chosen.ticker, mixed))
        weights = np.array([weight_map[t] for t in x.iloc[selected_pos].ticker])
        x.iloc[selected_pos, x.columns.get_loc("position_size")] = weights
        x.iloc[selected_pos, x.columns.get_loc("pred_signal")] = 1
    return x.drop(columns=["_arm_eligible", "_vol13"])


def _metrics(values: pd.Series) -> dict:
    values = values.dropna().astype(float)
    ret = values.pct_change().dropna()
    years = (values.index[-1] - values.index[0]).days / 365.25
    return {
        "cagr": float((values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1),
        "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(52)),
        "max_drawdown": float((values / values.cummax() - 1).min()),
    }


def _annual_alpha(values: pd.Series, benchmark: pd.Series) -> list[float]:
    joined = pd.concat([values.rename("model"), benchmark.rename("bench")], axis=1).dropna()
    out = []
    for _, g in joined.groupby(joined.index.year):
        if len(g) < 13:
            continue
        out.append(float(g.model.iloc[-1] / g.model.iloc[0] - g.bench.iloc[-1] / g.bench.iloc[0]))
    return out


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("robustness_gate") != "PASS":
        raise RuntimeError("SR46 requires the corrected phase robustness PASS")
    base = pd.read_csv(SOURCE, parse_dates=["Date"]).set_index("Date").sort_index()
    features, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    fund_tickers = {ticker for ticker, tier in caps.items() if tier == "Fond"}
    base = _attach_components(base, features, fund_tickers)
    dates = base.index.unique().sort_values()
    common_start = dates[51]
    common_dates = dates[51:]
    benchmark = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(common_dates).ffill().dropna()
    bench_metrics = _metrics(benchmark / benchmark.iloc[0])
    vol = _vol_map(features, dates)
    config.REBALANCE_WEEKS = 52

    e, f, m = base.gate_expected, base.gate_fund, base.gate_momentum
    specs = [
        ("no_gate", pd.Series(True, index=base.index)),
        ("expected_only", e), ("fund_only", f), ("momentum_only", m),
        ("expected_fund", e & f), ("expected_momentum", e & m),
        ("fund_momentum", f & m), ("all_frozen_gates", e & f & m),
    ]
    specs.extend((f"momentum_threshold_{int(t*100):02d}", e & f & base.mom_12_1.gt(t))
                 for t in THRESHOLDS)
    specs.extend((f"random_matched_seed_{seed}", _random_matched_mask(base, seed))
                 for seed in RANDOM_SEEDS)

    rows = []
    baseline_membership = None
    for name, mask in specs:
        sig = _build_arm(base, np.asarray(mask, dtype=bool), vol)
        if name == "all_frozen_gates":
            observed = base.loc[base.pred_signal.eq(1), ["ticker"]].reset_index().to_csv(index=False)
            rebuilt = sig.loc[sig.pred_signal.eq(1), ["ticker"]].reset_index().to_csv(index=False)
            if observed != rebuilt:
                raise RuntimeError("All-gates arm does not reproduce frozen Stage-06 membership")
            weight_diff = float(np.max(np.abs(base.position_size.to_numpy() - sig.position_size.to_numpy())))
            if weight_diff > 1e-7:
                raise RuntimeError(f"All-gates arm does not reproduce frozen Stage-06 weights: {weight_diff}")
            baseline_membership = True
        bt = NoCorrelationBacktester(sig, prices)
        result = bt.run()
        values = result.loc[result.index >= common_start, "portfolio_value"]
        met = _metrics(values)
        yearly = _annual_alpha(values, benchmark)
        rows.append({
            "arm": name, **met, "benchmark_cagr": bench_metrics["cagr"],
            "alpha_cagr": met["cagr"] - bench_metrics["cagr"],
            "eligible_share": float(np.asarray(mask, dtype=bool).mean()),
            "positive_alpha_year_share": float(np.mean(np.asarray(yearly) > 0)) if yearly else np.nan,
            "worst_calendar_year_alpha": float(min(yearly)) if yearly else np.nan,
            "calendar_years": len(yearly),
        })
        print(f"{name}: CAGR={met['cagr']:.2%} alpha={met['cagr']-bench_metrics['cagr']:+.2%}", flush=True)

    table = pd.DataFrame(rows)
    table.to_csv(CSV, index=False)
    by = table.set_index("arm")
    frozen = by.loc["all_frozen_gates"]
    no_gate = by.loc["no_gate"]
    random_median = float(by.loc[[f"random_matched_seed_{s}" for s in RANDOM_SEEDS], "alpha_cagr"].median())
    plateau = by.loc[[f"momentum_threshold_{int(t*100):02d}" for t in THRESHOLDS]]
    plateau_winner = str(plateau.alpha_cagr.idxmax())
    gate = bool(frozen.alpha_cagr > 0 and frozen.positive_alpha_year_share > 0.5)
    report = {
        "status": "PASS", "parent_stage": parent["manifest_sha256"], "test": "N3-SR46",
        "common_window": {"start": str(common_start.date()), "end": str(common_dates[-1].date()),
                          "weeks": len(common_dates)},
        "eligibility_reproduction": "EXACT", "frozen_membership_reproduction": bool(baseline_membership),
        "frozen_weight_max_abs_diff": weight_diff,
        "benchmark_metrics": bench_metrics, "frozen_all_gates": frozen.to_dict(),
        "no_gate": no_gate.to_dict(), "incremental_alpha_vs_no_gate": float(frozen.alpha_cagr - no_gate.alpha_cagr),
        "random_matched_median_alpha": random_median, "plateau_best_arm": plateau_winner,
        "eligibility_gate": "PASS" if gate else "FAIL",
        "decision_rule": "positive full-window alpha and positive alpha in a majority of calendar years",
        "holdout_used": False, "production": False, "arms": len(table),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("04_eligibility_decomposition", [OUT, CSV, Path(__file__).resolve()],
        {"test": "N3-SR46", "eligibility_gate": report["eligibility_gate"],
         "architecture_gate": "PASS", "production": False, "arms": len(table)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
