"""Import every EODHD delisted Stockholm series available to this account.

Raw responses and normalized OHLCV are cached permanently.  Subscription
warnings are recorded as coverage gaps; they are never treated as price data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


HOME = Path("/opt/momentum/momentum_ml")
FACTS = HOME / "cache/aktiehistorik/survival_facts.json"
CACHE = HOME / "cache/eodhd_delisted"
OUT = HOME / "results/point_in_time/eodhd_delisted_coverage.json"


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9åäö]", "", str(value).lower())


def api_get(path: str, token: str, params: dict) -> requests.Response:
    return requests.get(
        f"https://eodhd.com/api/{path}",
        params={**params, "api_token": token, "fmt": "json"}, timeout=45)


def warning(payload) -> str:
    if isinstance(payload, dict):
        return str(payload.get("warning") or payload.get("message") or "")
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return str(payload[0].get("warning") or payload[0].get("message") or "")
    return ""


def normalize_prices(payload: list) -> pd.DataFrame:
    frame = pd.DataFrame(payload)
    required = {"date", "open", "high", "low", "close", "volume"}
    if frame.empty or not required.issubset(frame):
        return pd.DataFrame()
    frame = frame.rename(columns={
        "date": "Date", "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
        "adjusted_close": "AdjustedClose",
    })
    frame["Date"] = pd.to_datetime(frame.Date, errors="coerce")
    frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date")
    return frame


def run(start: str, pause: float = .25) -> dict:
    token = os.environ.get("EODHD_API_TOKEN")
    if not token:
        raise RuntimeError("EODHD_API_TOKEN saknas")
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    facts = json.loads(FACTS.read_text())
    known = {
        ticker: value for ticker, value in facts.items()
        if value.get("status") == "avnoterad"
    }
    response = api_get(
        "exchange-symbol-list/ST", token, {"delisted": 1})
    response.raise_for_status()
    catalogue = response.json()
    by_code = {norm(row.get("Code")): row for row in catalogue}
    by_name = {norm(row.get("Name")): row for row in catalogue}

    rows = []
    # Most recent delistings first: these can still fit a one-year free window.
    ordered = sorted(
        known.items(), key=lambda item: item[1].get("delisted_date") or "",
        reverse=True)
    for ticker, fact in ordered:
        hit = (
            by_code.get(norm(ticker.removesuffix(".ST")))
            or by_name.get(norm(fact.get("name"))))
        if not hit:
            rows.append({"ticker": ticker, "status": "catalogue_missing"})
            continue
        eod_code = f"{hit['Code']}.ST"
        if (fact.get("delisted_date")
                and pd.Timestamp(fact["delisted_date"]) < pd.Timestamp(start)):
            rows.append({
                "ticker": ticker, "eodhd_code": eod_code,
                "status": "outside_subscription_window"})
            continue
        raw_path = CACHE / f"{ticker.replace('.', '_')}.json"
        csv_path = CACHE / f"{ticker.replace('.', '_')}.csv"
        if raw_path.exists():
            payload = json.loads(raw_path.read_text())
        else:
            r = api_get(
                f"eod/{eod_code}", token,
                {"from": start, "to": date.today().isoformat(), "period": "d"})
            if not r.ok:
                rows.append({
                    "ticker": ticker, "eodhd_code": eod_code,
                    "status": f"http_{r.status_code}", "detail": r.text[:160]})
                if r.status_code == 429:
                    break
                continue
            payload = r.json()
            raw_path.write_text(json.dumps(payload, ensure_ascii=False))
            time.sleep(pause)
        warn = warning(payload)
        frame = normalize_prices(payload if isinstance(payload, list) else [])
        if not frame.empty:
            frame.to_csv(csv_path, index=False)
            rows.append({
                "ticker": ticker, "eodhd_code": eod_code, "status": "ok",
                "rows": len(frame), "start": str(frame.Date.min().date()),
                "end": str(frame.Date.max().date()),
                "complete_from_listing": bool(
                    fact.get("first_listed_date")
                    and frame.Date.min() <= pd.Timestamp(fact["first_listed_date"])
                    + pd.Timedelta(days=14)),
            })
        else:
            rows.append({
                "ticker": ticker, "eodhd_code": eod_code,
                "status": "subscription_limited" if warn else "empty",
                "detail": warn[:200],
            })
    result = pd.DataFrame(rows)
    result.to_csv(OUT.with_suffix(".csv"), index=False)
    report = {
        "requested_from": start, "catalogue_rows": len(catalogue),
        "known_delisted": len(known), "matched_catalogue": int(
            result.eodhd_code.notna().sum()) if "eodhd_code" in result else 0,
        "downloaded_series": int(result.status.eq("ok").sum()),
        "complete_series": int(
            result.get("complete_from_listing", pd.Series(dtype=bool))
            .fillna(False).sum()),
        "status_counts": result.status.value_counts().to_dict(),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start", default=(date.today() - timedelta(days=365)).isoformat())
    args = parser.parse_args()
    print(json.dumps(run(args.start), ensure_ascii=False, indent=2))
