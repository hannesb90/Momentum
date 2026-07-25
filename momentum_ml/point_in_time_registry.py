"""Build a free, diagnostic Swedish point-in-time security registry.

Sources are already-cached Skatteverket Aktiehistorik pages plus Momentum's
price caches.  Outputs are research inputs only and never alter live signals.
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config
from altdata import aktiehistorik as ah


HOME = Path("/opt/momentum/momentum_ml")
CACHE = HOME / "cache/aktiehistorik"
UNIVERSE = HOME / "data/sweden_universe.csv"
VERSION = "skv_pit_registry_v1"

_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:[-/](\d{2,4}))?\b")
_TYPE_RULES = (
    ("split", re.compile(r"(?:^|\s)S\s+\d+\s*:\s*\d+|split", re.I)),
    ("new_issue", re.compile(r"(?:^|\s)N\s+\d|nyemission|emission", re.I)),
    ("redemption", re.compile(r"inlösen|tvångsinlösen", re.I)),
    ("rights_issue", re.compile(r"uniträtt|teckningsrätt", re.I)),
    ("offer", re.compile(r"uppköp|budgiv|offentligt erbjudande", re.I)),
    ("bankruptcy", re.compile(r"konkurs", re.I)),
    ("liquidation", re.compile(r"likvidation|upplös", re.I)),
)


def classify_event(text: str) -> str:
    for kind, pattern in _TYPE_RULES:
        if pattern.search(text or ""):
            return kind
    return "other"


def event_date(cells: list[str], year: int) -> str | None:
    text = " ".join(cells)
    date = ah._parse_sv_date(text, year)
    if date:
        return date
    match = _SLASH_DATE.search(text)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    parsed_year = int(match.group(3)) if match.group(3) else year
    parsed_year += 2000 if parsed_year < 100 else 0
    try:
        return pd.Timestamp(parsed_year, month, day).date().isoformat()
    except ValueError:
        return None


def corporate_actions(html: str, ticker: str, source_url: str) -> list[dict]:
    """Extract dated actions from every table, preserving raw source text."""
    rows = []
    for table_no, table in enumerate(ah._extract_tables(html)):
        if not table:
            continue
        header = " | ".join(table[0]).lower()
        for cells in table[1:]:
            if not cells or not str(cells[0]).strip().isdigit():
                continue
            year = int(str(cells[0]).strip())
            text = " | ".join(str(x).strip() for x in cells[1:] if str(x).strip())
            kind = classify_event(text)
            # Table zero already feeds the universe interval register.  Keep
            # only materially useful lifecycle events from it here.
            if table_no == 0:
                if re.search(r"namnändring", text, re.I):
                    kind = "name_change"
                elif re.search(r"avnoter", text, re.I):
                    kind = "delisting"
                elif re.search(r"(?:ny\s+)?notering|överförd", text, re.I):
                    kind = "listing"
                else:
                    continue
            elif kind == "other" and not any(
                    word in header for word in ("villkor", "kommentar")):
                continue
            rows.append({
                "ticker": ticker, "event_date": event_date(cells[1:], year),
                "event_year": year, "event_type": kind, "raw_text": text,
                "table_no": table_no, "source": "Skatteverket Aktiehistorik",
                "source_url": source_url, "registry_version": VERSION,
            })
    return rows


def listing_intervals(fact: dict) -> list[dict]:
    """Convert ordered listing/delisting facts to tradability intervals."""
    dated = [
        e for e in fact.get("events", [])
        if e.get("date") and e.get("type") in {"notering", "avnotering"}
    ]
    dated.sort(key=lambda e: e["date"])
    intervals, opened = [], None
    for event in dated:
        if event["type"] == "notering":
            if opened is None:
                opened = event["date"]
        elif opened is not None:
            intervals.append((opened, event["date"]))
            opened = None
    if opened is not None:
        intervals.append((opened, None))
    if not intervals:
        intervals = [(fact.get("first_listed_date"), fact.get("delisted_date"))]
    return [
        {
            "ticker": fact["ticker"], "name": fact.get("name"),
            "valid_from": start, "valid_to": end,
            "status_at_extract": fact.get("status"),
            "source": "Skatteverket Aktiehistorik",
            "source_url": fact.get("url"), "registry_version": VERSION,
        }
        for start, end in intervals if start or end
    ]


def cached_html_for(url: str) -> Path:
    return CACHE / f"_probe_{ah._slug(url)}.html"


def price_coverage(max_cache_files: int = 24) -> dict[str, dict]:
    """Union recent immutable price caches; newest observation wins."""
    found: dict[str, dict] = {}
    paths = sorted(
        (HOME / "cache").glob("*.pkl"),
        key=lambda p: p.stat().st_mtime, reverse=True)[:max_cache_files]
    for path in paths:
        try:
            payload = pickle.loads(path.read_bytes())
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for ticker, frame in payload.items():
            if ticker in found or not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            if "Close" not in frame:
                continue
            close = frame.Close.dropna()
            if close.empty:
                continue
            found[ticker] = {
                "price_start": str(pd.Timestamp(close.index.min()).date()),
                "price_end": str(pd.Timestamp(close.index.max()).date()),
                "price_observations": int(len(close)),
            }
    return found


def build(out_dir: Path) -> dict:
    facts = json.loads((CACHE / "survival_facts.json").read_text())
    matches = json.loads((CACHE / "ticker_match.json").read_text())
    current = pd.read_csv(UNIVERSE)
    current_tickers = set(current.ticker)
    prices = price_coverage()

    intervals, actions, coverage = [], [], []
    for ticker, fact in sorted(facts.items()):
        intervals.extend(listing_intervals(fact))
        page = cached_html_for(fact["url"])
        if page.exists():
            actions.extend(corporate_actions(
                page.read_text(encoding="utf-8"), ticker, fact["url"]))
        p = prices.get(ticker, {})
        is_dead = fact.get("status") == "avnoterad"
        price_start = pd.to_datetime(p.get("price_start"), errors="coerce")
        delisted = pd.to_datetime(fact.get("delisted_date"), errors="coerce")
        price_overlaps_lifecycle = bool(
            p and (
                pd.isna(delisted) or pd.isna(price_start)
                or price_start <= delisted))
        ticker_reuse_conflict = bool(
            is_dead and p and pd.notna(price_start) and pd.notna(delisted)
            and price_start > delisted + pd.Timedelta(days=90))
        coverage.append({
            "ticker": ticker, "name": fact.get("name"),
            "in_current_universe": ticker in current_tickers,
            "status": fact.get("status"),
            "first_listed_date": fact.get("first_listed_date"),
            "delisted_date": fact.get("delisted_date"),
            "has_cached_price": bool(p),
            **p,
            "price_overlaps_lifecycle": price_overlaps_lifecycle,
            "ticker_reuse_conflict": ticker_reuse_conflict,
            "delisted_price_gap": bool(
                is_dead and (not p or not price_overlaps_lifecycle)),
            "source_url": fact.get("url"),
        })

    interval_df = pd.DataFrame(intervals).sort_values(
        ["ticker", "valid_from"], na_position="first")
    action_df = pd.DataFrame(actions).drop_duplicates(
        ["ticker", "event_date", "event_type", "raw_text"]).sort_values(
            ["ticker", "event_year", "event_date"], na_position="first")
    coverage_df = pd.DataFrame(coverage).sort_values("ticker")
    out_dir.mkdir(parents=True, exist_ok=True)
    interval_df.to_csv(out_dir / "historical_universe_intervals.csv", index=False)
    action_df.to_csv(out_dir / "corporate_actions.csv", index=False)
    coverage_df.to_csv(out_dir / "pit_coverage.csv", index=False)

    confirmed = sum(bool(v.get("confirmed")) for v in matches.values())
    dead = coverage_df.status.eq("avnoterad")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": VERSION,
        "skatteverket_index_companies": len(json.loads(
            (CACHE / "_company_index.json").read_text())),
        "ticker_matches": len(matches), "confirmed_ticker_matches": confirmed,
        "facts_extracted": len(facts), "intervals": len(interval_df),
        "corporate_actions": len(action_df),
        "delisted_facts": int(dead.sum()),
        "delisted_with_cached_price": int((
            dead & coverage_df.has_cached_price
            & coverage_df.price_overlaps_lifecycle).sum()),
        "delisted_missing_price": int(
            (dead & (
                ~coverage_df.has_cached_price
                | ~coverage_df.price_overlaps_lifecycle)).sum()),
        "ticker_reuse_conflicts": int(coverage_df.ticker_reuse_conflict.sum()),
        "historical_backtest_ready": False,
        "blocking_reason": (
            "delisted_price_history_missing"
            if (dead & (
                ~coverage_df.has_cached_price
                | ~coverage_df.price_overlaps_lifecycle)).any()
            else "manual_point_in_time_review_required"),
        "production_change_authorized": False,
    }
    (out_dir / "pit_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir", type=Path, default=HOME / "results/point_in_time")
    args = parser.parse_args()
    print(json.dumps(build(args.out_dir), ensure_ascii=False, indent=2))
