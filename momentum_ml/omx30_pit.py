"""PIT OMX30 membership loader and strict validator.

The canonical input is a reviewed CSV, never today's constituent list projected
backwards. Rows describe inclusive membership intervals.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "omx30_membership_pit.csv"
REQUIRED = {"ticker", "member_from", "member_to", "source_url"}


def load_membership(path: Path = DEFAULT_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"PIT OMX30 saknas: {path}. Bygg den från Nasdaqs officiella "
            "halvårs-/extraändringsmeddelanden; dagens lista får inte användas."
        )
    df = pd.read_csv(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"OMX30 PIT saknar kolumner: {sorted(missing)}")
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["member_from"] = pd.to_datetime(df["member_from"], errors="raise")
    df["member_to"] = pd.to_datetime(df["member_to"], errors="coerce")
    if (df["member_to"].notna() & (df["member_to"] < df["member_from"])).any():
        raise ValueError("OMX30 PIT har member_to före member_from")
    if df["source_url"].fillna("").str.strip().eq("").any():
        raise ValueError("Varje OMX30-intervall måste ha officiell source_url")
    return df.sort_values(["member_from", "ticker"]).reset_index(drop=True)


def members_on(df: pd.DataFrame, date: pd.Timestamp) -> set[str]:
    date = pd.Timestamp(date).normalize()
    mask = (df.member_from <= date) & (df.member_to.isna() | (df.member_to >= date))
    return set(df.loc[mask, "ticker"])


def validate_membership(df: pd.DataFrame, start="2010-01-01", end=None,
                        dates=None) -> dict:
    if dates is None:
        end = pd.Timestamp.today().normalize() if end is None else pd.Timestamp(end)
        dates = pd.date_range(pd.Timestamp(start), end, freq="W-MON")
    else:
        dates = pd.DatetimeIndex(pd.to_datetime(dates)).sort_values().unique()
    counts = pd.Series({d: len(members_on(df, d)) for d in dates}, name="n_members")
    # Extraordinary deletions can leave the official index at 29 components
    # until a replacement is effective. Requiring exactly 30 would either
    # reject valid Nasdaq history or tempt a future-membership backfill.
    bad = counts[~counts.isin([29, 30, 31])]
    if len(bad):
        sample = ", ".join(f"{d.date()}={n}" for d, n in bad.iloc[:10].items())
        raise ValueError(
            f"OMX30 PIT är ofullständig/överlappande: {len(bad)} veckor har "
            f"inte 29–31 medlemmar ({sample})"
        )
    return {"start": str(dates.min().date()), "end": str(dates.max().date()),
            "weeks": len(dates), "intervals": len(df),
            "unique_tickers": int(df.ticker.nunique())}


if __name__ == "__main__":
    frame = load_membership()
    signal_path = ROOT / "results" / "signals.csv"
    signal_dates = pd.read_csv(signal_path, usecols=["Date"], parse_dates=["Date"])["Date"].unique()
    print(validate_membership(frame, dates=signal_dates))
