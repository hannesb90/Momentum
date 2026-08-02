"""Stateful, time-safe expected-return anchored early-exit experiment.

Anchors are expanding medians of realised 52-week returns whose outcomes were
already fully observable at entry, grouped by sector and entry score bucket.
They are frozen in position state and never recomputed after purchase.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json, math
import numpy as np
import pandas as pd

import config
from data.data_loader import (fetch_weekly_data, filter_active_universe,
                              filter_liquid_universe, load_sweden_universe)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "anchor_exit_results.json"
WEEKS = 52


@dataclass
class Position:
    shares: float
    entry_price: float
    entry_date: pd.Timestamp
    anchor: float


def _panel(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({t: d["Close"] for t, d in data.items()}).sort_index().ffill(limit=2)


def add_oof_anchors(signals: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    s = signals.reset_index().copy()
    s["Date"] = pd.to_datetime(s["Date"])
    s["score_bucket"] = np.minimum((s["prob_rank"].fillna(.5) * 5).astype(int), 4)
    long_px = close.stack().rename("px").reset_index()
    long_px.columns = ["Date", "ticker", "px"]
    future = long_px.copy(); future["Date"] -= pd.Timedelta(weeks=WEEKS)
    future = future.rename(columns={"px": "future_px"})
    s = s.merge(long_px, on=["Date", "ticker"], how="left").merge(
        future, on=["Date", "ticker"], how="left")
    s["realized_52"] = s.future_px / s.px - 1
    s["outcome_known"] = s.Date + pd.Timedelta(weeks=WEEKS)
    s["anchor_return"] = np.nan

    # Explicit expanding loop: slower than a vectorised leaky groupby, but makes
    # the information cutoff auditable and deterministic.
    known: dict[tuple[str, int], list[float]] = {}
    global_known: list[float] = []
    by_known = s.dropna(subset=["realized_52"]).sort_values("outcome_known")
    events = list(by_known[["outcome_known", "sector", "score_bucket", "realized_52"]]
                  .itertuples(index=False, name=None))
    event_i = 0
    for date, idxs in s.sort_values("Date").groupby("Date").groups.items():
        while event_i < len(events) and events[event_i][0] <= date:
            _, sector, bucket, value = events[event_i]
            if np.isfinite(value):
                known.setdefault((str(sector), int(bucket)), []).append(float(value))
                global_known.append(float(value))
            event_i += 1
        for idx in idxs:
            key = (str(s.at[idx, "sector"]), int(s.at[idx, "score_bucket"]))
            values = known.get(key, [])
            base = np.median(values) if len(values) >= 20 else (
                np.median(global_known) if len(global_known) >= 100 else np.nan)
            pred = s.at[idx, "pred_return"] if "pred_return" in s else np.nan
            # Shrink the noisy ranker regression toward the PIT historical base.
            if np.isfinite(base) and np.isfinite(pred):
                anchor = .75 * float(base) + .25 * float(pred)
            else:
                anchor = base
            s.at[idx, "anchor_return"] = np.clip(anchor, .05, 1.50) if np.isfinite(anchor) else .25
    return s.set_index("Date").sort_index()


def _metrics(nav: pd.Series) -> dict:
    r = nav.pct_change().dropna(); years = len(r) / 52
    return {"cagr": float((nav.iloc[-1]/nav.iloc[0])**(1/years)-1),
            "sharpe": float(r.mean()/r.std(ddof=0)*math.sqrt(52)) if r.std(ddof=0) else None,
            "max_drawdown": float((nav/nav.cummax()-1).min()), "weeks": len(nav)}


def simulate(signals: pd.DataFrame, close: pd.DataFrame, mode: str,
             threshold: float | None = None, k: float | None = None,
             opportunity_gap: float = .10) -> tuple[pd.Series, dict]:
    cash = float(config.INITIAL_CAPITAL); positions: dict[str, Position] = {}
    nav_rows, exits = [], 0
    dates = signals.index.unique().sort_values()
    n_pos = int(config.SEGMENTS["large"].get("max_positions", 10))
    cost = float(config.COMMISSION + config.SLIPPAGE)

    def price(t, d):
        try:
            x = close.at[d, t]
            return float(x) if np.isfinite(x) and x > 0 else None
        except KeyError: return None

    for i, date in enumerate(dates):
        day = signals.loc[[date]].sort_values("selection_rank", ascending=False)
        equity = cash + sum(p.shares*(price(t,date) or 0) for t,p in positions.items())
        rebalance = i % WEEKS == 0
        if rebalance:
            for t, p in list(positions.items()):
                px = price(t,date)
                if px: cash += p.shares*px*(1-cost)
            positions.clear()
            candidates = day[day.get("selection_eligible", 1).astype(bool)].head(n_pos)
            target = cash/(max(len(candidates), 1)*(1+cost))
            for row in candidates.itertuples():
                px = price(row.ticker,date)
                if px and cash >= target*(1+cost):
                    positions[row.ticker] = Position(target/px, px, date, float(row.anchor_return))
                    cash -= target*(1+cost)
        elif mode != "baseline":
            ranked = day[day.get("selection_eligible", 1).astype(bool)]
            held = set(positions)
            replacements = ranked[~ranked.ticker.isin(held)]
            for t, p in list(positions.items()):
                px = price(t,date)
                if not px or replacements.empty: continue
                realised = px/p.entry_price-1
                trigger = realised >= threshold if mode == "fixed" else realised >= float(k)*p.anchor
                current_row = day[day.ticker.eq(t)]
                held_score = float(current_row.pred_return.iloc[0]) if len(current_row) else -np.inf
                repl = replacements.iloc[0]
                repl_score = float(repl.pred_return) if np.isfinite(repl.pred_return) else -np.inf
                if trigger and repl_score >= held_score + opportunity_gap:
                    proceeds = p.shares*px*(1-cost); del positions[t]
                    rpx = price(repl.ticker,date)
                    if rpx:
                        invest = proceeds/(1+cost)
                        positions[repl.ticker] = Position(invest/rpx, rpx, date, float(repl.anchor_return))
                        cash += proceeds-invest*(1+cost); exits += 1
                        replacements = replacements[~replacements.ticker.eq(repl.ticker)]
                    else: cash += proceeds
        equity = cash + sum(p.shares*(price(t,date) or 0) for t,p in positions.items())
        nav_rows.append((date,equity))
    nav = pd.Series(dict(nav_rows)).sort_index()
    return nav, {"early_exits": exits}


def main() -> None:
    seg = config.SEGMENTS["large"]
    signals = pd.read_csv(ROOT/"results"/"signals.csv", parse_dates=["Date"]).set_index("Date")
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_liquid_universe(filter_active_universe(data), config.UNIVERSE_MIN_AVG_TURNOVER)
    close = _panel(data).reindex(signals.index.unique().sort_values()).ffill(limit=2)
    anchored = add_oof_anchors(signals, close)
    specs = [("baseline", "baseline", None, None)]
    specs += [(f"fixed_{x:.0%}", "fixed", x, None) for x in (.15,.25,.35,.50)]
    specs += [(f"anchor_{x}", "anchor", None, x) for x in (.75,1.,1.25,1.5)]
    output = {}
    for name, mode, threshold, k in specs:
        nav, diag = simulate(anchored, close, mode, threshold, k)
        output[name] = {**_metrics(nav), **diag}
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2)); print(f"Sparat: {OUT}")


if __name__ == "__main__":
    main()
