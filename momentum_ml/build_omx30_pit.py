"""Build weekly PIT OMXS30 membership from Nasdaq's public weighting endpoint."""
from __future__ import annotations

from pathlib import Path
import time
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "omx30_membership_pit.csv"
RAW = ROOT / "cache" / "omx30_pit_weekly.csv"
PAGE = "https://indexes.nasdaqomx.com/index/Weighting/OMXS30"
API = "https://indexes.nasdaqomx.com/Index/WeightingData"

SPECIAL = {
    "NDA SEK": "NDA-SE.ST", "NOKI SEK": "NOKIA-SEK.ST", "TLSN": "TELIA.ST",
    "LUPE": "LUNE.ST", "HM B": "HM-B.ST", "SECU B": "SECU-B.ST",
}


def yahoo_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    return SPECIAL.get(symbol, symbol.replace(" ", "-") + ".ST")


def fetch_date(session: requests.Session, date: pd.Timestamp) -> list[dict]:
    # Signaletiketten är måndag men kan vara svensk/amerikansk helgdag. Nasdaq
    # returnerar då en tom lista. Använd senaste FÖREGÅENDE indexdag (aldrig en
    # framtida dag), vilket också är rätt information cutoff för signalen.
    observed = []
    for lag in range(0, 8):
        query_date = date - pd.Timedelta(days=lag)
        payload = {"id": "OMXS30",
                   "tradeDate": query_date.strftime("%Y-%m-%dT00:00:00.000"),
                   "timeOfDay": "SOD"}
        for attempt in range(3):
            response = session.post(API, data=payload, timeout=45)
            response.raise_for_status()
            rows = response.json().get("aaData", [])
            observed.append((str(query_date.date()), len(rows)))
            # OMXS30 can temporarily contain 29 names after an extraordinary
            # deletion and before the replacement becomes effective.  This is
            # visible in Nasdaq's own historical weighting data (for example
            # around 2014-05-26) and must not be "repaired" with future data.
            # Temporary vacancies *and* transition overlaps occur in the
            # official series (29–31 names). Preserve Nasdaq's as-of state.
            if len(rows) in (29, 30, 31):
                return rows
            if len(rows) not in (0, 29, 30, 31):
                time.sleep(2 ** attempt)
            else:
                break
    raise RuntimeError(
        f"Nasdaq gav aldrig 29–31 komponenter för/asof {date.date()}; "
        f"försök={observed}"
    )


def compress(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.sort_values(["nasdaq_symbol", "date"])
    intervals = []
    one_week = pd.Timedelta(weeks=1)
    for symbol, group in raw.groupby("nasdaq_symbol"):
        dates = list(group.date.sort_values())
        start = prev = dates[0]
        for date in dates[1:]:
            if date - prev > one_week:
                intervals.append((symbol, start, prev))
                start = date
            prev = date
        intervals.append((symbol, start, prev))
    out = pd.DataFrame(intervals, columns=["nasdaq_symbol", "member_from", "member_to"])
    out["ticker"] = out.nasdaq_symbol.map(yahoo_ticker)
    out["source_url"] = PAGE
    return out[["ticker", "nasdaq_symbol", "member_from", "member_to", "source_url"]]


def main() -> None:
    signals = pd.read_csv(ROOT / "results" / "signals.csv", usecols=["Date"], parse_dates=["Date"])
    dates = pd.DatetimeIndex(signals.Date.unique()).sort_values()
    existing = pd.read_csv(RAW, parse_dates=["date"]) if RAW.exists() else pd.DataFrame()
    done = set(existing.date) if len(existing) else set()
    session = requests.Session(); session.headers["User-Agent"] = "Momentum PIT audit/1.0"
    session.get(PAGE, timeout=45).raise_for_status()
    frames = [existing] if len(existing) else []
    for i, date in enumerate(dates, 1):
        if date in done: continue
        rows = fetch_date(session, date)
        frame = pd.DataFrame({"date": date, "nasdaq_symbol": [r["Symbol"] for r in rows],
                              "name": [r["Name"] for r in rows]})
        frames.append(frame)
        if i % 25 == 0:
            pd.concat(frames, ignore_index=True).drop_duplicates(["date", "nasdaq_symbol"]).to_csv(RAW,index=False)
        time.sleep(.05)
    raw = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "nasdaq_symbol"])
    raw.to_csv(RAW, index=False)
    out = compress(raw); out.to_csv(OUT, index=False)
    print(f"OMXS30 PIT: {len(dates)} signalveckor, {raw.nasdaq_symbol.nunique()} symboler, "
          f"{len(out)} intervall -> {OUT}")


if __name__ == "__main__":
    main()
