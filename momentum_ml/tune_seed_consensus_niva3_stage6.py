"""N3 stage 06: predeclared remediation for failed SR47 seed stability.

Equal-weight cross-sectional rank consensus across seeds 7/42/97.  No seed is
selected or performance-weighted.  Leave-one-seed-out pairs test whether the
consensus itself depends on one member.
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations
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
from tune_seed_fitdate_stability_niva3_stage5 import _jaccard_summary, _members, _pct, _set_seed
from tune_target_horizon_isolated import raw_preds, targets_from_prices


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/05_seed_fitdate_stability.json"
STAGE5_CSV = ROOT / "results/niva3_seed_fitdate_stability_arms.csv"
OUT = ROOT / "results/niva3_seed_consensus.json"
CSV = ROOT / "results/niva3_seed_consensus_arms.csv"
RAW = ROOT / "results/niva3_seed_consensus_raw_scores.csv"
SIGNALS = ROOT / "results/niva3_seed_consensus_signals.csv"
SEEDS = (7, 42, 97)


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _consensus_scores(panel: pd.DataFrame, seeds: tuple[int, ...]) -> pd.Series:
    cols = [f"raw_{seed}" for seed in seeds]
    missing = [c for c in cols if c not in panel]
    if missing:
        raise RuntimeError(f"Missing seed scores: {missing}")
    ranks = panel.groupby("Date", sort=False)[cols].rank(method="average", pct=True)
    return ranks.mean(axis=1)


def _benchmark_cagr(prices: dict, dates: pd.DatetimeIndex) -> float:
    close = prices[config.INDEX_BENCHMARK_TICKER].Close.reindex(dates).ffill().dropna()
    years = (close.index[-1] - close.index[0]).days / 365.25
    return float((close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1)


def _build_panel(features, prices, state):
    cols = list(getattr(state, "feature_cols_", []) or FEATURE_COLS)
    validate_large_contract(cols)
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
    return panel[panel.index < purge], cols


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("stability_gate") != "FAIL":
        raise RuntimeError("Consensus remediation requires failed SR47")
    features, prices, state, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    if not sectors or not caps:
        raise RuntimeError("Large universe maps are empty")
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    dev, cols = _build_panel(features, prices, state)
    expected_hash = json.loads((ROOT / "results/target_horizon_isolated.json").read_text())["same_feature_hash"]
    actual_hash = hashlib.sha256(pd.util.hash_pandas_object(dev[cols], index=True).values.tobytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError("Frozen feature panel hash mismatch")
    splits = walk_forward_splits(dev.index, embargo_weeks=52)
    seed_pieces = {}
    for seed in SEEDS:
        _set_seed(seed); pieces = []
        for split_i, (train_dates, val_dates, test_dates) in enumerate(splits):
            train = dev[dev.index.isin(train_dates)].sort_index()
            val = dev[dev.index.isin(val_dates)].sort_index()
            test = dev[dev.index.isin(test_dates)].sort_index()
            model = _train_lambdarank(train, val, cols)
            piece = test[["ticker"]].copy(); piece[f"raw_{seed}"] = model.predict(test[cols].fillna(0).values)
            pieces.append(piece.reset_index())
            print(f"seed_{seed} split {split_i+1}/{len(splits)}", flush=True)
        seed_pieces[seed] = pd.concat(pieces, ignore_index=True)
    panel = seed_pieces[SEEDS[0]]
    for seed in SEEDS[1:]:
        panel = panel.merge(seed_pieces[seed], on=["Date", "ticker"], how="inner", validate="one_to_one")
    expected_rows = len(seed_pieces[SEEDS[0]])
    if len(panel) != expected_rows or any(len(x) != expected_rows for x in seed_pieces.values()):
        raise RuntimeError("Seed score panels do not align")
    panel.to_csv(RAW, index=False)

    feature_dfs = {ticker: frame.assign(ticker=ticker) for ticker, frame in features.items()}
    config.REBALANCE_WEEKS = 52; config.SIZING_MODE = "inverse_vol"; config.CONVICTION_BLEND = 0.75
    single_members = {}; single_stats = {}
    stage5 = pd.read_csv(STAGE5_CSV).set_index("arm")
    for seed in SEEDS:
        raw = panel[["Date", "ticker", f"raw_{seed}"]].rename(columns={f"raw_{seed}": "raw"}).set_index("Date")
        sig = build_full_output(raw_preds(raw), None, feature_dfs, MomentumEnsemble(), record_diagnostics=False)
        bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
        expected = stage5.loc[f"seed_{seed}_offset_0"]
        for key in ("CAGR", "Sharpe", "Max Drawdown"):
            if str(stats[key]) != str(expected[key]):
                raise RuntimeError(f"Seed {seed} parity failed for {key}: {stats[key]} != {expected[key]}")
        single_members[seed] = _members(sig); single_stats[seed] = stats

    specs = [("consensus_all_3", SEEDS)] + [
        ("consensus_" + "_".join(map(str, pair)), pair) for pair in combinations(SEEDS, 2)
    ]
    rows = []; signals_by_arm = {}; members_by_arm = {}
    for arm, seeds in specs:
        scored = panel[["Date", "ticker"]].copy()
        scored["raw"] = _consensus_scores(panel, tuple(seeds))
        sig = build_full_output(raw_preds(scored.set_index("Date")), None, feature_dfs,
                                MomentumEnsemble(), record_diagnostics=False)
        bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
        signals_by_arm[arm] = sig; members_by_arm[arm] = _members(sig)
        rows.append({"arm": arm, "seeds": "+".join(map(str, seeds)), **stats,
                     "cagr_numeric": _pct(stats["CAGR"])})
        print(arm, stats["CAGR"], stats["Sharpe"], stats["Max Drawdown"], flush=True)
    full_members = members_by_arm["consensus_all_3"]
    table = pd.DataFrame(rows)
    benchmark_cagr = _benchmark_cagr(prices, signals_by_arm["consensus_all_3"].index.unique().sort_values())
    table["alpha_cagr"] = table.cagr_numeric - benchmark_cagr
    table["median_jaccard_vs_full_consensus"] = table.arm.map(
        lambda arm: _jaccard_summary(full_members, members_by_arm[arm])["median"])
    for seed in SEEDS:
        table[f"median_jaccard_vs_seed_{seed}"] = table.arm.map(
            lambda arm, seed=seed: _jaccard_summary(single_members[seed], members_by_arm[arm])["median"])
    table.to_csv(CSV, index=False)
    signals_by_arm["consensus_all_3"].to_csv(SIGNALS)

    full = table.set_index("arm").loc["consensus_all_3"]
    pairs = table[table.arm.ne("consensus_all_3")]
    single_median_cagr = float(np.median([_pct(single_stats[s]["CAGR"]) for s in SEEDS]))
    pair_spread = float(pairs.cagr_numeric.max() - pairs.cagr_numeric.min())
    worst_pair_alpha = float(pairs.alpha_cagr.min())
    full_seed_jaccards = [float(full[f"median_jaccard_vs_seed_{seed}"]) for seed in SEEDS]
    robust = (float(full.cagr_numeric) >= single_median_cagr and pair_spread <= .03
              and worst_pair_alpha > 0 and min(full_seed_jaccards) >= .60)
    report = {
        "status": "PASS", "parent_stage": parent["manifest_sha256"],
        "test": "N3-SR47-seed-consensus-remediation", "seeds": list(SEEDS),
        "method": "equal_weight_mean_cross_sectional_percentile_rank", "performance_weighting": False,
        "full_consensus": full.to_dict(), "single_seed_median_cagr": single_median_cagr,
        "leave_one_out_pair_cagr_spread": pair_spread, "worst_pair_alpha": worst_pair_alpha,
        "full_consensus_min_median_jaccard_vs_single_seed": min(full_seed_jaccards),
        "consensus_gate": "PASS" if robust else "FAIL",
        "decision_rule": "full CAGR >= median single seed; pair spread <=3pp; every pair positive alpha; full median Jaccard >=0.60 vs every seed",
        "selection_allowed": False, "holdout_used": False, "production": False,
        "feature_hash": actual_hash, "splits": len(splits),
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("06_seed_consensus_remediation", [OUT, CSV, RAW, SIGNALS, Path(__file__).resolve()],
        {"test": "N3-SR47-consensus", "consensus_gate": report["consensus_gate"],
         "selection": False, "production": False, "seeds": list(SEEDS)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
