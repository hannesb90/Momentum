"""PIT OMX30 portfolio-construction test on frozen Large signals."""
from __future__ import annotations

from pathlib import Path
import json
import gc
import os
import subprocess
import sys
import pandas as pd

import config
from backtest.backtester import MomentumBacktester
from data.data_loader import (fetch_weekly_data, filter_active_universe,
                              filter_liquid_universe, load_sweden_universe)
from omx30_pit import load_membership, members_on, validate_membership

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "idx_mix_pit_results.json"


def constrained_signals(signals: pd.DataFrame, membership: pd.DataFrame,
                        n_omx: int | None, exclude: bool = False) -> pd.DataFrame:
    rows = []
    n_total = int(config.SEGMENTS["large"].get("max_positions", 10))
    for i, (date, day) in enumerate(signals.groupby(level=0, sort=True)):
        day = day.copy()
        eligible = day[day.get("selection_eligible", 1).astype(bool)].copy()
        order = "selection_rank" if "selection_rank" in eligible else "prob_raw"
        eligible = eligible.sort_values(order, ascending=False)
        omx = members_on(membership, date)
        inside = eligible[eligible.ticker.isin(omx)]
        outside = eligible[~eligible.ticker.isin(omx)]
        if exclude:
            chosen = outside.head(n_total)
        elif n_omx is None:
            chosen = eligible.head(n_total)
        else:
            chosen = pd.concat([inside.head(n_omx), outside.head(n_total-n_omx)])
            if i % int(config.REBALANCE_WEEKS) == 0 and len(chosen) != n_total:
                raise RuntimeError(f"{date}: kan inte fylla {n_omx}/{n_total} PIT OMX30-mix")
        day["pred_signal"] = 0
        day["position_size"] = 0.0
        if len(chosen):
            chosen_tickers = set(chosen.ticker)
            mask = day.ticker.isin(chosen_tickers)
            day.loc[mask, "pred_signal"] = 1
            day.loc[mask, "position_size"] = 1.0 / len(chosen_tickers)
        rows.append(day)
    return pd.concat(rows)[["ticker", "pred_signal", "position_size"]].sort_index()


def metrics(bt: MomentumBacktester) -> dict:
    bt.run()
    return bt.statistics()


def main() -> None:
    arm = os.environ.get("IDX_MIX_ARM")
    arm_names = ["baseline"] + [f"exact_{x}_omx30" for x in (0, 2, 4, 6, 8)] + ["exclude_omx30"]
    parts_dir = ROOT / "results" / "idx_mix_parts"
    if os.environ.get("IDX_MIX_AGGREGATE") == "1":
        combined = {name: json.loads((parts_dir / f"{name}.json").read_text())
                    for name in arm_names}
        membership = load_membership()
        signal_dates = pd.read_csv(ROOT / "results/signals.csv", usecols=["Date"],
                                   parse_dates=["Date"])["Date"].unique()
        coverage = validate_membership(membership, dates=signal_dates)
        OUT.write_text(json.dumps({"coverage": coverage, "variants": combined}, indent=2,
                                  ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(combined, indent=2, ensure_ascii=False)); print(f"Sparat: {OUT}")
        return
    if arm is None:
        combined = {}
        for name in arm_names:
            print(f"[idx_mix] Separat process: {name}", flush=True)
            env = os.environ.copy(); env["IDX_MIX_ARM"] = name
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve())], cwd=Path(__file__).parent,
                                  env=env, text=True, capture_output=True, check=False)
            print(proc.stdout, end="")
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                raise RuntimeError(f"IDX-MIX-arm {name} föll med exit={proc.returncode}")
            line = next(x for x in proc.stdout.splitlines() if x.startswith("IDX_RESULT "))
            combined[name] = json.loads(line[len("IDX_RESULT "):])
        membership = load_membership()
        signals_dates = pd.read_csv(ROOT / "results/signals.csv", usecols=["Date"], parse_dates=["Date"])["Date"].unique()
        coverage = validate_membership(membership, dates=signals_dates)
        OUT.write_text(json.dumps({"coverage": coverage, "variants": combined}, indent=2,
                                  ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps(combined, indent=2, ensure_ascii=False)); print(f"Sparat: {OUT}")
        return

    membership = load_membership()
    signals = pd.read_csv(ROOT / "results" / "signals.csv",
                          usecols=["Date", "ticker", "selection_rank", "selection_eligible"],
                          parse_dates=["Date"]).set_index("Date")
    coverage = validate_membership(membership, dates=signals.index.unique())
    seg = config.SEGMENTS["large"]
    config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    config.MAX_POSITIONS = seg["max_positions"]
    # Exact 0..8 OMX30 of 15 is only a defined experiment when all arms can
    # actually fill at every scheduled rebalance. Find the earliest common
    # start rather than treating sparse warm-up weeks as a strategy failure.
    dates = signals.index.unique().sort_values()
    start = None
    for offset, candidate in enumerate(dates):
        scheduled = dates[offset::config.REBALANCE_WEEKS]
        if len(scheduled) < 3:
            continue
        feasible = True
        for date in scheduled:
            day = signals.loc[[date]]
            eligible = day[day.get("selection_eligible", 1).astype(bool)]
            omx = members_on(membership, date)
            n_in = int(eligible.ticker.isin(omx).sum())
            n_out = len(eligible) - n_in
            if len(eligible) < config.MAX_POSITIONS or n_in < 8 or n_out < config.MAX_POSITIONS:
                feasible = False; break
        if feasible:
            start = candidate; break
    if start is None:
        raise RuntimeError("Ingen gemensam PIT-period kan fylla samtliga IDX-MIX-armar")
    signals = signals[signals.index >= start]
    print(f"[idx_mix] Gemensamt genomförbart fönster från {pd.Timestamp(start).date()}")
    tickers, sectors, caps, names = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    cached = ROOT / "results" / "abstention_price_data.pkl"
    if cached.exists():
        data = pd.read_pickle(cached)
    else:
        data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
        data = filter_liquid_universe(filter_active_universe(data), config.UNIVERSE_MIN_AVG_TURNOVER)
    # Build/run one arm at a time; retaining seven 100k-row signal copies caused
    # avoidable peak memory and could kill an otherwise valid overnight test.
    specs = [("baseline", None, False)]
    specs += [(f"exact_{x}_omx30", x, False) for x in (0, 2, 4, 6, 8)]
    specs += [("exclude_omx30", None, True)]
    specs = [spec for spec in specs if spec[0] == arm]
    result = {}
    for name, n_omx, exclude in specs:
        print(f"[idx_mix] Kör {name}...")
        sig = constrained_signals(signals, membership, n_omx, exclude=exclude)
        result[name] = metrics(MomentumBacktester(sig, data))
        parts_dir.mkdir(parents=True, exist_ok=True)
        (parts_dir / f"{name}.json").write_text(
            json.dumps(result[name], indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
        del sig
        gc.collect()
    print("IDX_RESULT " + json.dumps(result[arm], ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
