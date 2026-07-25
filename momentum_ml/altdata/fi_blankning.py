"""Point-in-time-signaler från Finansinspektionens blankningsregister.

Historiska publika positioner rekonstrueras per rapportör och emittent. En
kalenderdags publiceringsfördröjning används för att undvika look-ahead.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import requests

import config

HISTORY_URL = "https://www.fi.se/BlankningsRegister/GetHistFile"
CACHE_FILE = "fi_blankning_historik.ods"
_NS = {"t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0"}


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(ab|publ|aktiebolaget|group|holding|plc|oyj|class|series)\b", " ", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _cache_path() -> Path:
    return Path(config.anchor("cache/fi_blankning")) / CACHE_FILE


def refresh_history(force: bool = False) -> Path:
    """Hämta FI-filen högst en gång per dygn; gammal cache behålls vid fel."""
    path = _cache_path()
    fresh = path.exists() and (
        pd.Timestamp.now().timestamp() - path.stat().st_mtime < 20 * 3600
    )
    if fresh and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(HISTORY_URL, timeout=45)
        response.raise_for_status()
        if not response.content.startswith(b"PK"):
            raise ValueError("FI returnerade inte en giltig ODS-fil")
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(path)
    except Exception:
        if not path.exists():
            raise
    return path


def _ods_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    rows: list[list[str]] = []
    for row in root.findall(".//t:table-row", _NS):
        cells = ["".join(cell.itertext()).strip()
                 for cell in row.findall("t:table-cell", _NS)]
        if cells:
            rows.append(cells)
    return rows


@lru_cache(maxsize=3)
def load_events(path: Path | None = None) -> pd.DataFrame:
    """Returnera aggregerad blankning efter varje historisk positionsändring."""
    path = path or refresh_history()
    parsed = path.with_suffix(".events.pkl")
    if parsed.exists() and parsed.stat().st_mtime >= path.stat().st_mtime:
        try:
            return pd.read_pickle(parsed)
        except Exception:
            pass
    raw = []
    for row in _ods_rows(path):
        if len(row) < 5:
            continue
        holder, issuer, isin, value, reported = row[:5]
        date = pd.to_datetime(reported, errors="coerce")
        if pd.isna(date):
            continue
        pct = 0.0 if "<" in value else pd.to_numeric(value.replace(",", "."), errors="coerce")
        if pd.isna(pct):
            continue
        raw.append((date, issuer, holder, float(pct), isin))
    raw.sort()
    positions: dict[str, dict[str, float]] = defaultdict(dict)
    events = []
    for reported, issuer, holder, pct, isin in raw:
        positions[issuer][holder] = pct
        # Signalen får användas först följande kalenderdag.
        events.append((reported + pd.Timedelta(days=1), issuer,
                       sum(positions[issuer].values()), isin))
    result = pd.DataFrame(events, columns=["date", "issuer", "short_pct", "isin"])
    try:
        result.to_pickle(parsed)
    except OSError:
        pass
    return result


def _issuer_map(events: pd.DataFrame, ticker_names: dict[str, str]) -> dict[str, str]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for ticker, name in ticker_names.items():
        by_name[_normalise(name or ticker)].append(ticker)
    result = {}
    for issuer in events["issuer"].dropna().unique():
        key = _normalise(issuer)
        exact = by_name.get(key, [])
        if len(exact) == 1:
            result[issuer] = exact[0]
            continue
        candidates = [tickers[0] for name, tickers in by_name.items()
                      if len(tickers) == 1 and len(key) >= 6
                      and (key in name or name in key)]
        if len(candidates) == 1:
            result[issuer] = candidates[0]
    return result


def attach_features(frame: pd.DataFrame, path: Path | None = None) -> pd.DataFrame:
    """Lägg FI-nivå och 4/8/13-veckors förändring på en Date/ticker-panel."""
    out = frame.copy()
    for col in ("short_pct", "short_delta_4w", "short_delta_8w", "short_delta_13w"):
        out[col] = float("nan")
    if out.empty:
        return out
    events = load_events(path)
    names = {str(t): config.NAME_MAP.get(str(t), str(t))
             for t in out["ticker"].dropna().unique()}
    events["ticker"] = events["issuer"].map(_issuer_map(events, names))
    events = events.dropna(subset=["ticker"]).sort_values(["ticker", "date"])
    if events.empty:
        return out

    original_index = out.index
    feature_cols = ("short_pct", "short_delta_4w", "short_delta_8w", "short_delta_13w")
    work = out.drop(columns=list(feature_cols)).reset_index().rename(
        columns={out.index.name or "index": "Date"}
    )
    work["_order"] = range(len(work))
    parts = []
    # Ett enda vektoriserat asof-join. Den tidigare tickerslingan gjorde ~200
    # separata merge_asof och lade flera minuter på varje nattkörning.
    work["Date"] = pd.to_datetime(work["Date"]).astype("datetime64[ns]")
    history = events[["ticker", "date", "short_pct"]].copy()
    history["date"] = pd.to_datetime(history["date"]).astype("datetime64[ns]")
    # merge_asof kräver global sortering på själva tidsnyckeln även med by=.
    joined = pd.merge_asof(
        work.sort_values(["Date", "ticker"]),
        history.sort_values(["date", "ticker"]),
        left_on="Date", right_on="date", by="ticker", direction="backward",
    ).drop(columns=["date"])
    joined = joined.sort_values(["ticker", "Date"])
    for weeks in (4, 8, 13):
        joined[f"short_delta_{weeks}w"] = (
            joined["short_pct"] - joined.groupby("ticker")["short_pct"].shift(weeks)
        )
    joined = joined.sort_values("_order").drop(columns=["_order", "Date"])
    joined.index = original_index
    return joined


def latest_features(tickers: list[str], path: Path | None = None) -> dict[str, dict]:
    """Senaste veckovisa signalvärde för exitskanningen."""
    if not tickers:
        return {}
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=14, freq="W-MON")
    panel = pd.DataFrame([(date, ticker) for ticker in tickers for date in dates],
                         columns=["Date", "ticker"]).set_index("Date")
    enriched = attach_features(panel, path=path)
    return {ticker: group.iloc[-1].to_dict()
            for ticker, group in enriched.groupby("ticker")}
