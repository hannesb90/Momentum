"""Forward-only Avanza ETF retail-flow snapshot collector.

Reads delayed public market data and writes only its own append-only ledger.
It never imports portfolio or order code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from altdata import avanza


HOME = Path(os.environ.get("MOMENTUM_HOME", "/opt/momentum/momentum_ml"))
UNIVERSE = HOME / "data/rotation_universe.csv"
DEFAULT_OUT = HOME / "results/etf_flow"
PAUSE_SECONDS = 0.15


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    os.replace(tmp, path)


def title_has_ticker(title: str, ticker: str) -> bool:
    bare = ticker.split(".")[0].upper()
    return bool(re.search(rf"\({re.escape(bare)}\)\s*$", title.upper()))


def fund_name_tokens(name: str) -> set[str]:
    stop = {
        "ucits", "etf", "acc", "dist", "usd", "eur", "gbp", "de",
        "the", "and",
    }
    return {
        token for token in re.findall(r"[a-z0-9]+", name.lower())
        if len(token) > 2 and token not in stop
    }


def resolve_etf(ticker: str, name: str) -> dict | None:
    """Prefer exact ticker, then a uniquely identifiable Avanza share class."""
    queries = [ticker.split(".")[0], name]
    name_candidates = []
    for query in queries:
        response = avanza.search(query)
        hits = response.get("hits") or []
        exact = next((
            hit for hit in hits
            if hit.get("type") == "EXCHANGE_TRADED_FUND"
            and title_has_ticker(str(hit.get("title") or ""), ticker)
            and hit.get("orderBookId")
        ), None)
        if exact:
            exact["match_method"] = "exact_ticker"
            return exact
        if query == name:
            wanted = fund_name_tokens(name)
            name_candidates = [
                hit for hit in hits
                if hit.get("type") == "EXCHANGE_TRADED_FUND"
                and hit.get("orderBookId")
                and wanted.issubset(fund_name_tokens(str(hit.get("title") or "")))
            ]
        time.sleep(PAUSE_SECONDS)
    if name_candidates:
        # The Avanza-traded accumulating share class is the best proxy for
        # an accumulating London/Xetra listing when that exact ticker is absent.
        name_candidates.sort(
            key=lambda hit: ("(ACC)" not in str(hit.get("title") or "").upper(),
                             str(hit.get("title") or "")))
        chosen = dict(name_candidates[0])
        chosen["match_method"] = "same_fund_avanza_share_class"
        return chosen
    return None


def load_mapping(path: Path, universe: pd.DataFrame) -> dict:
    existing = json.loads(path.read_text()) if path.exists() else {}
    changed = False
    for row in universe.itertuples(index=False):
        current = existing.get(row.ticker)
        if current and current.get("orderBookId"):
            continue
        hit = resolve_etf(row.ticker, row.name)
        if not hit:
            existing[row.ticker] = {"status": "unmatched"}
        else:
            existing[row.ticker] = {
                "status": "confirmed",
                "orderBookId": str(hit["orderBookId"]),
                "title": hit.get("title"),
                "match_method": hit.get("match_method"),
            }
        changed = True
        time.sleep(PAUSE_SECONDS)
    if changed:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        os.replace(tmp, path)
    return existing


def numeric(value):
    try:
        return float(value) if value is not None else np.nan
    except (TypeError, ValueError):
        return np.nan


def snapshot_row(meta, mapping, info, collected_at):
    quote = info.get("quote") or {}
    indicators = info.get("keyIndicators") or {}
    listing = info.get("listing") or {}
    quote_ms = quote.get("timeOfLast")
    quote_time = (
        datetime.fromtimestamp(float(quote_ms) / 1000, timezone.utc).isoformat()
        if quote_ms else ""
    )
    return {
        "snapshot_date": collected_at.date().isoformat(),
        "collected_at": collected_at.isoformat(),
        "ticker": meta.ticker,
        "name": meta.name,
        "group": meta.group,
        "kind": meta.kind,
        "orderbook_id": mapping["orderBookId"],
        "match_method": mapping.get("match_method") or "",
        "currency": listing.get("currency") or "",
        "quote_time": quote_time,
        "is_real_time": bool(quote.get("isRealTime", False)),
        "last": numeric(quote.get("last")),
        "vwap": numeric(quote.get("volumeWeightedAveragePrice")),
        "total_volume": numeric(quote.get("totalVolumeTraded")),
        "total_value": numeric(quote.get("totalValueTraded")),
        "number_of_owners": numeric(indicators.get("numberOfOwners")),
    }


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values(["ticker", "snapshot_date", "collected_at"]).copy()
    frame["owner_change_1d"] = frame.groupby("ticker").number_of_owners.diff()
    frame["owner_change_pct_1d"] = (
        frame.owner_change_1d
        / frame.groupby("ticker").number_of_owners.shift(1).replace(0, np.nan)
    )
    frame["owner_change_5obs"] = (
        frame.number_of_owners
        - frame.groupby("ticker").number_of_owners.shift(5)
    )
    frame["owner_change_pct_5obs"] = (
        frame.owner_change_5obs
        / frame.groupby("ticker").number_of_owners.shift(5).replace(0, np.nan)
    )
    positive = frame.owner_change_1d.gt(0).where(frame.owner_change_1d.notna())
    frame["owner_flow_persistence_5obs"] = (
        positive.groupby(frame.ticker)
        .rolling(5, min_periods=3).mean().reset_index(level=0, drop=True)
    )
    frame["price_vs_vwap"] = frame["last"] / frame["vwap"] - 1
    frame["owner_rank"] = frame.groupby("snapshot_date").number_of_owners.rank(
        pct=True, method="average")
    frame["owner_change_rank"] = frame.groupby(
        "snapshot_date").owner_change_pct_1d.rank(pct=True, method="average")
    frame["owner_change_5obs_rank"] = frame.groupby(
        "snapshot_date").owner_change_pct_5obs.rank(
            pct=True, method="average")
    frame["flow_score"] = pd.concat([
        frame.owner_change_rank,
        frame.owner_change_5obs_rank,
        frame.owner_flow_persistence_5obs,
    ], axis=1).mean(axis=1, skipna=True)
    # Within-kind rank prevents the larger theme set from drowning the smaller
    # sector and region sleeves when the flow overlay is eventually evaluated.
    if "kind" in frame:
        frame["flow_rank_within_kind"] = frame.groupby(
            ["snapshot_date", "kind"]).flow_score.rank(
                pct=True, method="average")
    return frame


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE)
    mapping = load_mapping(out_dir / "avanza_etf_map.json", universe)
    now = datetime.now(timezone.utc)
    rows, errors = [], []
    for meta in universe.itertuples(index=False):
        match = mapping.get(meta.ticker) or {}
        if match.get("status") != "confirmed":
            errors.append({"ticker": meta.ticker, "error": "unmatched"})
            continue
        try:
            info = avanza._get(
                f"/_api/market-guide/stock/{match['orderBookId']}")
            rows.append(snapshot_row(meta, match, info, now))
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticker": meta.ticker, "error": str(exc)[:200]})
        time.sleep(PAUSE_SECONDS)
    if not rows:
        raise RuntimeError("Inga ETF-snapshots kunde hämtas.")

    ledger_path = out_dir / "etf_flow_snapshots.csv"
    new = pd.DataFrame(rows)
    old = pd.read_csv(ledger_path) if ledger_path.exists() else pd.DataFrame()
    ledger = pd.concat([old, new], ignore_index=True)
    ledger = ledger.drop_duplicates(
        ["snapshot_date", "ticker"], keep="last")
    ledger = enrich(ledger)
    atomic_csv(ledger, ledger_path)
    latest = ledger[ledger.snapshot_date == ledger.snapshot_date.max()].copy()
    atomic_csv(latest.sort_values("owner_rank", ascending=False),
               out_dir / "etf_flow_latest.csv")
    atomic_csv(pd.DataFrame(errors, columns=["ticker", "error"]),
               out_dir / "etf_flow_errors.csv")
    print(json.dumps({
        "snapshot_date": latest.snapshot_date.max(),
        "captured": len(latest),
        "unmatched_or_failed": len(errors),
        "historical_dates": int(ledger.snapshot_date.nunique()),
        "out_dir": str(out_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    run(parser.parse_args().out_dir)
