"""Nivå-2 stage 05: sequential pipeline ablation on the stage-04 winner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large

apply_large()

from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from niva2_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva2_stages/04_score_sizing_isolation.json"
STAGE3 = ROOT / "results/niva2_stage3_winner_signals.csv"
STAGE4 = ROOT / "results/niva2_stage4_winner_signals.csv"
OUT = ROOT / "results/pipeline_ablation_niva2.json"
ARMS_OUT = ROOT / "results/pipeline_ablation_niva2_arms.csv"
WINNER_SIG = ROOT / "results/niva2_stage5_winner_signals.csv"


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


class RecordingCorrelationBacktester(MomentumBacktester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.correlation_membership = []

    def _correlation_filter(self, target_weights, date):
        filtered = super()._correlation_filter(target_weights, date)
        self.correlation_membership.append((pd.Timestamp(date), set(target_weights), set(filtered)))
        return filtered


def _number(stats, key):
    return float(str(stats[key]).replace("%", ""))


def _equal_select(base, score, eligibility=None):
    x = base.copy(); x["position_size"] = 0.0; x["pred_signal"] = 0
    for _, positions in x.groupby(level=0, sort=False).indices.items():
        positions = np.asarray(positions, dtype=int); g = x.iloc[positions]
        valid = pd.Series(True, index=g.index) if eligibility is None else g[eligibility].eq(1)
        candidates = g[valid.to_numpy()].sort_values(score, ascending=False).head(config.MAX_POSITIONS)
        if candidates.empty:
            continue
        # Resolve duplicate Date indices through ticker membership inside this date.
        chosen = set(candidates.ticker)
        local = g.ticker.isin(chosen).to_numpy(); selected_positions = positions[local]
        x.iloc[selected_positions, x.columns.get_loc("position_size")] = 1.0 / len(selected_positions)
        x.iloc[selected_positions, x.columns.get_loc("pred_signal")] = 1
    return x


def _membership(sig):
    return {d: set(g.loc[g.pred_signal.eq(1), "ticker"]) for d, g in sig.groupby(level=0)}


def _jaccard(a, b):
    dates = sorted(set(a) & set(b)); vals = []
    for d in dates:
        union = a[d] | b[d]
        vals.append(len(a[d] & b[d]) / len(union) if union else 1.0)
    return float(np.median(vals)) if vals else np.nan


def _rotation_turnover(sig):
    members = _membership(sig); dates = sorted(members)[::52]; vals = []
    for before, after in zip(dates, dates[1:]):
        denom = max(len(members[before]), 1)
        vals.append(1.0 - len(members[before] & members[after]) / denom)
    return float(np.mean(vals)) if vals else np.nan


def _hash_members(sig):
    data = sig.loc[sig.pred_signal.eq(1), ["ticker"]].reset_index().to_csv(index=False)
    return hashlib.sha256(data.encode()).hexdigest()


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("winner") != "inverse_vol_b075":
        raise RuntimeError("Stage-04 sizing winner mismatch")
    base = pd.read_csv(STAGE3, parse_dates=["Date"]).set_index("Date").sort_index()
    sized = pd.read_csv(STAGE4, parse_dates=["Date"]).set_index("Date").sort_index()
    if not base.index.equals(sized.index) or not base.ticker.equals(sized.ticker):
        raise RuntimeError("Stage-03 and Stage-04 signal panels do not align")
    _, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS = 52

    arms = [
        ("raw_lambdarank_equal", _equal_select(base, "prob_raw"), False),
        ("plus_rank_ema_equal", _equal_select(base, "rank_ema_rank"), False),
        ("plus_eligibility_gate_equal", _equal_select(base, "selection_rank", "selection_eligible"), False),
        ("plus_inverse_vol75", sized.copy(), False),
        ("plus_correlation_filter", sized.copy(), True),
    ]
    rows = []; signals = {}; prior_members = None
    for order, (name, sig, use_corr) in enumerate(arms):
        bt_cls = RecordingCorrelationBacktester if use_corr else NoCorrelationBacktester
        bt = bt_cls(sig, prices); bt.run(); stats = bt.statistics()
        members = _membership(sig)
        corr_pre_post = 1.0
        if use_corr and bt.correlation_membership:
            vals = []
            for _, pre, post in bt.correlation_membership:
                union = pre | post; vals.append(len(pre & post) / len(union) if union else 1.0)
            corr_pre_post = float(np.median(vals))
        rows.append({"order": order, "arm": name, **stats,
                     "median_jaccard_vs_previous": 1.0 if prior_members is None else _jaccard(prior_members, members),
                     "mean_calendar_rotation_turnover": _rotation_turnover(sig),
                     "median_correlation_pre_post_jaccard": corr_pre_post,
                     "signal_membership_hash": _hash_members(sig)})
        prior_members = members; signals[name] = sig
        print(name, stats["CAGR"], stats["Sharpe"], stats["Max Drawdown"], flush=True)
    table = pd.DataFrame(rows)
    # A pipeline component is retained only if the cumulative arm is the best
    # net-CAGR architecture; Sharpe is the declared tie-break.
    winner = max(table.arm, key=lambda n: (
        _number(table.set_index("arm").loc[n], "CAGR"),
        float(table.set_index("arm").loc[n, "Sharpe"])))
    table.to_csv(ARMS_OUT, index=False); signals[winner].to_csv(WINNER_SIG)
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
              "locked_input": "lambdarank_13w_calendar52_inversevol75",
              "holdout_used": False, "retraining": False,
              "arms_tested": len(arms), "winner": winner,
              "winner_metrics": table.set_index("arm").loc[winner].to_dict(),
              "lstm_blend": "not_present_in_locked_stage03_objective_and_therefore_not_silently_added",
              "results_csv": str(ARMS_OUT.relative_to(ROOT))}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("05_pipeline_ablation",
        [OUT, ARMS_OUT, WINNER_SIG, Path(__file__).resolve()],
        {"winner": winner, "objective": "lambdarank", "target_weeks": 13,
         "rotation_weeks": 52, "holdout_used": False, "arms": len(arms)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
