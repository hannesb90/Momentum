"""Testa Otto-högvärdering endast inom qualified-holder-kandidater."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd

import config
from backtest.integrated_backtest import IntegratedBacktester
from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe,
    load_sweden_universe,
)

HORIZONS = (13, 26, 52)


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(
        Path(config.anchor(seg["results_dir"])) / "signals.csv",
        parse_dates=["Date"]).sort_values(["ticker", "Date"])
    sig["prev"] = sig.groupby("ticker")["pred_signal"].shift()
    exits = sig[(sig["prev"] == 1) & (sig["pred_signal"] == 0)]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = filter_liquid_universe(
        filter_active_universe(fetch_weekly_data(
            tickers, start="2010-01-01", end=None, use_cache=True)),
        min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()

    bt = IntegratedBacktester(
        sig.set_index("Date"), data, hold_fund_enabled=False,
        insider_enabled=False, sellwatch_enabled=False)
    bt._build_close_panel(px.index)
    otto = bt._build_otto_panel(px.index, list(px.columns))

    rows = []
    for r in exits.itertuples(index=False):
        pos = px.index.searchsorted(r.Date)
        if pos < 26 or pos >= len(px) or r.ticker not in px:
            continue
        p = px[r.ticker].iloc[pos]
        trend = (
            p > px[r.ticker].iloc[pos - 19:pos + 1].mean()
            and p / px[r.ticker].iloc[pos - 26]
            > idx.iloc[pos] / idx.iloc[pos - 26])
        if not trend:
            continue
        high = bool(
            r.ticker in otto.columns and pd.notna(otto.at[px.index[pos], r.ticker])
            and otto.at[px.index[pos], r.ticker])
        row = {"Date": r.Date, "otto_high": high}
        for h in HORIZONS:
            row[f"ret_{h}"] = (
                px[r.ticker].iloc[pos + h] / p - 1
                if pos + h < len(px) and pd.notna(px[r.ticker].iloc[pos + h])
                else np.nan)
        rows.append(row)
    out = pd.DataFrame(rows)
    print("period       grupp          h      n    medel   median   positiv")
    for label, mask in (
        ("DEV <2024", out["Date"] < "2024-01-01"),
        ("TEST 2024+", out["Date"] >= "2024-01-01"),
    ):
        for group, gm in (
            ("otto hög", out["otto_high"]),
            ("ej hög", ~out["otto_high"]),
        ):
            for h in HORIZONS:
                x = out.loc[mask & gm, f"ret_{h}"].dropna()
                if len(x):
                    print(f"{label:<13}{group:<14}{h:>3}{len(x):>7}"
                          f"{x.mean():>9.2%}{x.median():>9.2%}"
                          f"{(x > 0).mean():>9.1%}")
    modern_high = out[(out["Date"] >= "2024-01-01") & out["otto_high"]]
    print(f"\nModerna Otto-high qualified holders: {len(modern_high)}")


if __name__ == "__main__":
    main()
