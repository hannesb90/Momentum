"""N3 stage 05 / SR47: LambdaRank seed and fit-cutoff stability.

No winning seed or cutoff is selected.  Three seeds are compared at the frozen
cutoff and the frozen seed is compared with 1/2/4-week older fit information.
Every arm keeps identical OOF test dates and portfolio architecture.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large, validate_large_contract

apply_large()

from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from features.feature_engineering import FEATURE_COLS, to_model_df
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_lambdarank
from tune_target_horizon_isolated import raw_preds, targets_from_prices


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/04_eligibility_decomposition.json"
N2_REPORT = ROOT / "results/retraining_staleness_niva2.json"
OUT = ROOT / "results/niva3_seed_fitdate_stability.json"
CSV = ROOT / "results/niva3_seed_fitdate_stability_arms.csv"
SEEDS = (7, 42, 97)
OFFSETS = (0, 1, 2, 4)


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _members(signals: pd.DataFrame) -> dict[pd.Timestamp, set[str]]:
    return {pd.Timestamp(d): set(g.loc[g.pred_signal.eq(1), "ticker"])
            for d, g in signals.groupby(level=0)}


def _jaccard_summary(reference: dict, challenger: dict) -> dict:
    vals = []
    for date in sorted(set(reference) & set(challenger)):
        a, b = reference[date], challenger[date]
        union = a | b
        vals.append(len(a & b) / len(union) if union else 1.0)
    return {"median": float(np.median(vals)), "p10": float(np.quantile(vals, .10)),
            "worst": float(np.min(vals)), "dates": len(vals)}


def _set_seed(seed: int) -> None:
    for key in ("seed", "bagging_seed", "feature_fraction_seed", "data_random_seed"):
        config.LGBM_PARAMS[key] = int(seed)


def _trim_cutoff(dates: pd.DatetimeIndex, weeks: int) -> pd.DatetimeIndex:
    if weeks == 0:
        return dates
    if len(dates) <= weeks:
        raise RuntimeError("Fit cutoff removes the whole window")
    return dates[:-weeks]


def _benchmark_cagr(prices: dict, dates: pd.DatetimeIndex) -> float:
    close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().dropna()
    years = (close.index[-1] - close.index[0]).days / 365.25
    return float((close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1)


def _pct(value: str) -> float:
    return float(str(value).replace("%", "")) / 100.0


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("eligibility_gate") != "PASS":
        raise RuntimeError("SR47 requires SR46 PASS")
    features, prices, state, _ = _load_state()
    cols = list(getattr(state, "feature_cols_", []) or FEATURE_COLS)
    validate_large_contract(cols)
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    if not sectors or not caps:
        raise RuntimeError("Large universe maps are empty")
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)

    base = to_model_df(features).sort_index(); base.index.name = "Date"
    target13 = targets_from_prices(base, prices, 13)
    target52 = targets_from_prices(base, prices, 52)
    feature_base = base.drop(columns=[c for c in base.columns if c.startswith("target_")], errors="ignore")
    t13 = target13.reset_index().rename(columns={"target_return": "ret13", "target_signal": "sig13"})
    t52 = target52.reset_index().rename(columns={"target_return": "ret52", "target_signal": "sig52"})
    panel = (feature_base.reset_index().merge(t13, on=["Date", "ticker"])
             .merge(t52, on=["Date", "ticker"]).dropna(subset=["ret13", "sig13", "ret52", "sig52"])
             .set_index("Date").sort_index())
    panel["target_return"] = panel.ret13; panel["target_signal"] = panel.sig13
    dates = panel.index.unique().sort_values(); purge = dates[-(config.HOLDOUT_WEEKS + 52)]
    dev = panel[panel.index < purge]
    expected_hash = json.loads((ROOT / "results/target_horizon_isolated.json").read_text())["same_feature_hash"]
    actual_hash = hashlib.sha256(pd.util.hash_pandas_object(dev[cols], index=True).values.tobytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError("Frozen feature panel hash mismatch")
    splits = walk_forward_splits(dev.index, embargo_weeks=52)
    feature_dfs = {ticker: frame.assign(ticker=ticker) for ticker, frame in features.items()}
    config.REBALANCE_WEEKS = 52; config.SIZING_MODE = "inverse_vol"; config.CONVICTION_BLEND = 0.75

    specs = [(f"seed_{seed}_offset_0", seed, 0) for seed in SEEDS]
    specs += [(f"seed_42_offset_{offset}", 42, offset) for offset in OFFSETS if offset]
    rows = []; arm_signals = {}; baseline_members = None
    for arm, seed, offset in specs:
        _set_seed(seed)
        raw = []
        for split_i, (train_dates, val_dates, test_dates) in enumerate(splits):
            train = dev[dev.index.isin(_trim_cutoff(train_dates, offset))].sort_index()
            # With the frozen 52-week embargo the admissible validation slice is
            # only one week.  Keep that causal early-stopping observation fixed;
            # the cutoff perturbation makes training information older while OOF
            # test and validation dates remain identical across arms.
            val = dev[dev.index.isin(val_dates)].sort_index()
            test = dev[dev.index.isin(test_dates)].sort_index()
            model = _train_lambdarank(train, val, cols)
            piece = test[["ticker"]].copy(); piece["raw"] = model.predict(test[cols].fillna(0).values)
            raw.append(piece)
            print(f"{arm} split {split_i+1}/{len(splits)}", flush=True)
        sig = build_full_output(raw_preds(pd.concat(raw).sort_index()), None, feature_dfs,
                                MomentumEnsemble(), record_diagnostics=False)
        bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
        members = _members(sig)
        if arm == "seed_42_offset_0":
            frozen = json.loads(N2_REPORT.read_text())["retrain_13w_parity"]
            mismatch = {k: (stats[k], frozen[k]) for k in frozen if stats[k] != frozen[k]}
            if mismatch:
                raise RuntimeError(f"Frozen seed/cutoff baseline parity failed: {mismatch}")
            baseline_members = members
        arm_signals[arm] = (sig, members, stats, seed, offset)
        print(arm, stats["CAGR"], stats["Sharpe"], stats["Max Drawdown"], flush=True)

    if baseline_members is None:
        raise RuntimeError("Baseline arm missing")
    benchmark_cagr = _benchmark_cagr(prices, next(iter(arm_signals.values()))[0].index.unique().sort_values())
    for arm, (_, members, stats, seed, offset) in arm_signals.items():
        jac = _jaccard_summary(baseline_members, members)
        rows.append({"arm": arm, "seed": seed, "fit_cutoff_offset_weeks": offset,
                     **stats, "cagr_numeric": _pct(stats["CAGR"]),
                     "alpha_cagr": _pct(stats["CAGR"]) - benchmark_cagr,
                     "median_top15_jaccard_vs_baseline": jac["median"],
                     "p10_top15_jaccard_vs_baseline": jac["p10"],
                     "worst_top15_jaccard_vs_baseline": jac["worst"]})
    table = pd.DataFrame(rows); table.to_csv(CSV, index=False)
    seed_rows = table[table.fit_cutoff_offset_weeks.eq(0)]
    offset_rows = table[table.seed.eq(42)]
    seed_spread = float(seed_rows.cagr_numeric.max() - seed_rows.cagr_numeric.min())
    worst_alpha = float(table.alpha_cagr.min())
    worst_median_jaccard = float(table.median_top15_jaccard_vs_baseline.min())
    robust = seed_spread <= .03 and worst_alpha > 0 and worst_median_jaccard >= .60
    report = {
        "status": "PASS", "parent_stage": parent["manifest_sha256"], "test": "N3-SR47",
        "seeds": list(SEEDS), "fit_cutoff_offsets_weeks": list(OFFSETS), "arms": len(table),
        "same_oof_test_dates": True, "feature_hash": actual_hash, "splits": len(splits),
        "baseline_parity": "EXACT_ROUNDED", "benchmark_cagr": benchmark_cagr,
        "seed_cagr_range": {"min": float(seed_rows.cagr_numeric.min()),
                            "max": float(seed_rows.cagr_numeric.max()), "spread": seed_spread},
        "offset_worst_cagr": float(offset_rows.cagr_numeric.min()),
        "worst_alpha_all_arms": worst_alpha, "worst_median_top15_jaccard": worst_median_jaccard,
        "stability_gate": "PASS" if robust else "FAIL",
        "decision_rule": "seed CAGR spread <=3pp; every arm positive alpha; every arm median top15 Jaccard >=0.60",
        "selection_allowed": False, "holdout_used": False, "production": False,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage("05_seed_fitdate_stability", [OUT, CSV, Path(__file__).resolve()],
        {"test": "N3-SR47", "stability_gate": report["stability_gate"],
         "selection": False, "production": False, "arms": len(table)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False)); print(stage)


if __name__ == "__main__":
    main()
