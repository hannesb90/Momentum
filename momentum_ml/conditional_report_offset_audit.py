"""Rapportavstånd endast inom modellens topp-20-kandidatpool."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import config
from data.data_loader import fetch_weekly_data, load_sweden_universe

BINS = [-1, 7, 14, 28, 56, 91, 10_000]
LABELS = ["0-7d", "8-14d", "15-28d", "29-56d", "57-91d", ">91d"]


def main():
    rd = Path(config.anchor(config.SEGMENTS["large"]["results_dir"]))
    sig = pd.read_csv(rd / "signals.csv", parse_dates=["Date"])
    reports = []
    for name in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = rd / name
        if p.exists():
            x = pd.read_csv(p, usecols=["ticker", "published"])
            x["published"] = pd.to_datetime(
                x["published"], utc=True, errors="coerce").dt.tz_localize(None)
            reports.append(x.dropna())
    reports = pd.concat(reports).drop_duplicates().sort_values("published")
    report_dates = {
        t: pd.DatetimeIndex(g["published"]).sort_values()
        for t, g in reports.groupby("ticker")
    }
    tickers, _, _, _ = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    px_data = fetch_weekly_data(
        tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in px_data.items() if "Close" in d}).sort_index()

    rows = []
    rank_col = "prob_rank" if "prob_rank" in sig else "prob_up"
    for date, g in sig.groupby("Date"):
        candidates = g.sort_values(rank_col, ascending=False).head(20)
        pos = px.index.searchsorted(date)
        if pos >= len(px) or pos + 13 >= len(px):
            continue
        for r in candidates.itertuples(index=False):
            if r.ticker not in px:
                continue
            dates = report_dates.get(r.ticker)
            if dates is None:
                continue
            report_pos = dates.searchsorted(date, side="right") - 1
            if report_pos < 0:
                continue
            days = (date - dates[report_pos]).days
            p0, p1 = px[r.ticker].iloc[pos], px[r.ticker].iloc[pos + 13]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            rows.append({
                "Date": date, "ticker": r.ticker, "days": days,
                "rank": getattr(r, rank_col), "ret13": p1 / p0 - 1,
            })
    out = pd.DataFrame(rows)
    out["offset"] = pd.cut(out["days"], BINS, labels=LABELS)
    # Excess mot samma dags topp-20-medel isolerar rapporttimingen från marknaden.
    out["excess"] = out["ret13"] - out.groupby("Date")["ret13"].transform("mean")
    print("period       rapportoffset      n  medel-excess median-excess positiv")
    for period, mask in (
        ("DEV <2024", out["Date"] < "2024-01-01"),
        ("TEST 2024+", out["Date"] >= "2024-01-01"),
    ):
        for label in LABELS:
            x = out.loc[mask & (out["offset"] == label), "excess"].dropna()
            if len(x):
                print(f"{period:<13}{label:<16}{len(x):>5}{x.mean():>14.2%}"
                      f"{x.median():>14.2%}{(x > 0).mean():>9.1%}")
    print("\nNegativa offsets kräver historiska kalender-snapshots och testas inte "
          "med framtida faktiskt rapportdatum (det vore lookahead).")


if __name__ == "__main__":
    main()
