"""Nivå-2 stage 04: score/sizing only on frozen stage-03 selections.

The selected names, dates, target, objective and 52-week calendar rotation are
fixed.  Only the cross-sectional weight allocation among the same selected
names changes.  The correlation filter is disabled because it otherwise uses
weight size to remove names, which would confound sizing with selection.
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
from niva2_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva2_stages/03_objective_tournament.json"
SOURCE = ROOT / "results/niva2_stage3_winner_signals.csv"
OUT = ROOT / "results/sizing_isolated_niva2.json"
ARMS_OUT = ROOT / "results/sizing_isolated_niva2_arms.csv"
WINNER_SIG = ROOT / "results/niva2_stage4_winner_signals.csv"
BLENDS = (0.25, 0.50, 0.75, 1.00)


class SizingOnlyBacktester(MomentumBacktester):
    """Keep membership fixed; correlation selection belongs to stage 05."""

    def _correlation_filter(self, target_weights, date):
        return target_weights


def _number(stats, key):
    return float(str(stats[key]).replace("%", ""))


def _capped_weights(raw: pd.Series, cap: float) -> pd.Series:
    """Normalize non-negative weights and redistribute above-cap excess."""
    w = raw.clip(lower=0.0).astype(float)
    if not np.isfinite(w).all() or float(w.sum()) <= 0:
        w = pd.Series(1.0, index=raw.index)
    w /= float(w.sum())
    for _ in range(len(w) + 1):
        high = w > cap + 1e-12
        if not high.any():
            break
        excess = float((w[high] - cap).sum())
        w.loc[high] = cap
        low = ~high
        room = (cap - w[low]).clip(lower=0.0)
        if not low.any() or float(room.sum()) <= 0:
            break
        base = w[low]
        alloc = base / float(base.sum()) if float(base.sum()) > 0 else room / float(room.sum())
        w.loc[low] += excess * alloc
    return w / float(w.sum())


def _vol_map(features, dates):
    rows = []
    for ticker, frame in features.items():
        if "rvol_13w" not in frame:
            continue
        x = frame[["rvol_13w"]].copy()
        x["ticker"] = ticker
        x.index = pd.to_datetime(x.index)
        rows.append(x[x.index.isin(dates)].reset_index().rename(columns={x.index.name or "index": "Date"}))
    out = pd.concat(rows, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"])
    return out.set_index(["Date", "ticker"])["rvol_13w"]


def _realized_13w(signals, prices):
    """Forward return labels used only after their 13-week maturity date."""
    dates = signals.index.unique().sort_values()
    pieces = []
    for ticker, group in signals.groupby("ticker"):
        frame = prices.get(ticker)
        if frame is None or "Close" not in frame:
            continue
        close = frame["Close"].reindex(dates).ffill()
        ret = close.shift(-13) / close - 1.0
        pieces.append(pd.DataFrame({"Date": dates, "ticker": ticker, "ret13": ret.values}))
    return pd.concat(pieces, ignore_index=True).set_index(["Date", "ticker"])["ret13"]


def _empirical_scores(signals, prices):
    """Expanding rank-decile edge, using only outcomes known at each date."""
    realized = _realized_13w(signals, prices)
    panel = signals.reset_index().copy()
    panel["decile"] = np.minimum((panel["prob_rank"].clip(0, 1) * 10).astype(int), 9)
    panel["ret13"] = pd.MultiIndex.from_frame(panel[["Date", "ticker"]]).map(realized)
    panel["edge"] = panel["ret13"] - panel.groupby("Date")["ret13"].transform("median")
    dated = panel.dropna(subset=["edge"]).groupby(["Date", "decile"])["edge"].agg(["sum", "count"]).reset_index()
    dates = signals.index.unique().sort_values()
    running_sum = np.zeros(10); running_n = np.zeros(10); cursor = 0
    dated = dated.sort_values("Date").reset_index(drop=True)
    maps = []
    for date in dates:
        cutoff = date - pd.Timedelta(weeks=13)
        while cursor < len(dated) and dated.loc[cursor, "Date"] <= cutoff:
            dec = int(dated.loc[cursor, "decile"])
            running_sum[dec] += float(dated.loc[cursor, "sum"])
            running_n[dec] += float(dated.loc[cursor, "count"])
            cursor += 1
        means = np.divide(running_sum, running_n, out=np.zeros(10), where=running_n > 0)
        # Fixed 10%-return temperature; zero-history dates reduce to equal weight.
        score = np.exp(np.clip(means / 0.10, -4.0, 4.0))
        maps.extend((date, dec, score[dec], int(running_n[dec])) for dec in range(10))
    return pd.DataFrame(maps, columns=["Date", "decile", "emp_score", "history_n"])


def _variant(base, rule, blend, vol, empirical):
    x = base.reset_index().copy()
    x["decile"] = np.minimum((x["prob_rank"].clip(0, 1) * 10).astype(int), 9)
    x = x.merge(empirical, on=["Date", "decile"], how="left", validate="many_to_one").set_index("Date")
    key = pd.MultiIndex.from_arrays([x.index, x["ticker"]])
    x["vol13"] = vol.reindex(key).to_numpy()
    weights = np.zeros(len(x), dtype=float)
    for _, positions in x.groupby(level=0, sort=False).indices.items():
        positions = np.asarray(positions, dtype=int)
        g = x.iloc[positions]
        selected = g["pred_signal"].eq(1)
        chosen = g[selected]
        if chosen.empty:
            continue
        eq = pd.Series(1.0 / len(chosen), index=chosen.index)
        if rule == "equal_weight":
            tilt = eq
        elif rule == "raw_rank":
            tilt = _capped_weights(chosen["selection_rank"].clip(lower=1e-6), config.MAX_POSITION)
        elif rule == "inverse_vol":
            tilt = _capped_weights(1.0 / chosen["vol13"].fillna(0.20).clip(lower=0.05), config.MAX_POSITION)
        elif rule == "empirical_rank":
            tilt = _capped_weights(chosen["emp_score"].fillna(1.0), config.MAX_POSITION)
        else:
            raise ValueError(rule)
        mixed = _capped_weights((1.0 - blend) * eq + blend * tilt, config.MAX_POSITION)
        chosen_positions = positions[selected.to_numpy()]
        weights[chosen_positions] = mixed.to_numpy()
    x["position_size"] = weights
    x["pred_signal"] = (x["position_size"] > 0).astype(int)
    return x.drop(columns=["decile", "emp_score", "history_n", "vol13"])


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("winner") != "lambdarank":
        raise RuntimeError("Stage-03 winner is not LambdaRank")
    base = pd.read_csv(SOURCE, parse_dates=["Date"]).set_index("Date").sort_index()
    features, prices, _, _ = _load_state()
    _, sectors, caps, names = load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    config.REBALANCE_WEEKS = 52
    selected_fingerprint = base.loc[base.pred_signal.eq(1), ["ticker"]].reset_index().to_csv(index=False)
    selected_hash = __import__("hashlib").sha256(selected_fingerprint.encode()).hexdigest()
    vol = _vol_map(features, base.index.unique())
    empirical = _empirical_scores(base, prices)
    arms = [("equal_weight", "equal_weight", 0.0)]
    for rule in ("raw_rank", "inverse_vol", "empirical_rank"):
        arms.extend((f"{rule}_b{int(b*100):03d}", rule, b) for b in BLENDS)
    rows = []; signals = {}
    for name, rule, blend in arms:
        sig = _variant(base, rule, blend, vol, empirical)
        member_hash = __import__("hashlib").sha256(
            sig.loc[sig.pred_signal.eq(1), ["ticker"]].reset_index().to_csv(index=False).encode()).hexdigest()
        if member_hash != selected_hash:
            raise RuntimeError(f"Selection changed in sizing arm {name}")
        bt = SizingOnlyBacktester(sig, prices); bt.run(); stats = bt.statistics()
        rows.append({"arm": name, "rule": rule, "blend": blend, **stats,
                     "selection_hash": member_hash,
                     "median_effective_n": float(sig.groupby(level=0).position_size.apply(
                         lambda w: 1.0 / float((w[w > 0] ** 2).sum())).median())})
        signals[name] = sig
        print(name, stats["CAGR"], stats["Sharpe"], stats["Max Drawdown"], flush=True)
    table = pd.DataFrame(rows)
    winner = max(table.arm, key=lambda n: (
        _number(table.set_index("arm").loc[n], "CAGR"),
        float(table.set_index("arm").loc[n, "Sharpe"])))
    table.to_csv(ARMS_OUT, index=False); signals[winner].to_csv(WINNER_SIG)
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
              "locked_architecture": "lambdarank_13w_target_calendar52",
              "same_selection_hash_all_arms": selected_hash, "holdout_used": False,
              "correlation_filter": "disabled_to_prevent_selection_confound",
              "arms_tested": len(arms), "winner": winner,
              "winner_metrics": table.set_index("arm").loc[winner].to_dict(),
              "results_csv": str(ARMS_OUT.relative_to(ROOT))}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    stage = freeze_stage("04_score_sizing_isolation",
        [OUT, ARMS_OUT, WINNER_SIG, Path(__file__).resolve()],
        {"winner": winner, "objective": "lambdarank", "target_weeks": 13,
         "rotation_weeks": 52, "holdout_used": False, "arms": len(arms)}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
