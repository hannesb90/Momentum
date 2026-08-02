"""N3 stage 10 / SR49 remediation A: instrument-level fallback audit.

Reconstruct Börsdata's dividend-adjusted weekly series from cached raw data and
compare every residual >50% return with the frozen fallback series.  This is a
source audit only: it does not alter prices, signals, models, or production.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

import config
from altdata import borsdata
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/09_vendor_corporate_action_sensitivity.json"
OUT = ROOT / "results/niva3_fallback_instrument_audit.json"
EVENTS = ROOT / "results/niva3_fallback_instrument_events.csv"
TICKERS = ROOT / "results/niva3_fallback_instrument_summary.csv"
PIT_ACTIONS = ROOT / "results/point_in_time/corporate_actions.csv"
IDS = {"INTRUM.ST": 112, "KEOC.ST": 1354, "LAGR-B.ST": 124, "MTG-B.ST": 148,
       "SAGA-A.ST": 194, "SAVE.ST": 161, "SBB-B.ST": 438, "TRUE-B.ST": 2275,
       "VISC.ST": 312, "VPLAY-B.ST": 1794}
JUMP = 0.50
# Frozen before viewing outcomes: corroboration requires same direction and a
# >=35% fallback move within +/- one weekly bar.  Otherwise the vendor paths
# conflict.  Missing fallback history is explicitly unresolved.
CORROBORATION = 0.35


def cached_dividends() -> dict[int, pd.DataFrame]:
    values: dict[int, list] = {}
    for path in glob.glob(str(ROOT / "momentum_ml/cache/borsdata/dividend_calendar_*.json")):
        try:
            payload = json.loads(Path(path).read_text())
        except Exception:
            continue
        for item in payload.get("list", []):
            iid = item.get("insId")
            for row in item.get("values", []):
                date = pd.to_datetime(row.get("excludingDate"), errors="coerce")
                amount = pd.to_numeric(row.get("amountPaid"), errors="coerce")
                if iid and pd.notna(date) and pd.notna(amount) and amount > 0:
                    values.setdefault(int(iid), []).append((date.normalize(), float(amount)))
    out = {}
    for iid, rows in values.items():
        out[iid] = (pd.DataFrame(rows, columns=["ex_date", "amount"])
                    .drop_duplicates().groupby("ex_date", as_index=False).amount.sum())
    return out


def weekly_borsdata(iid: int, divs: dict, splits: dict) -> pd.Series:
    daily = borsdata.stockprices_ohlcv(iid, use_cache=True)
    events = borsdata.normalize_dividends_for_splits(divs.get(iid), splits.get(iid, []))
    daily = borsdata.adjust_ohlc_for_dividends(daily, events)
    weekly = daily.resample("W-FRI").Close.last().dropna()
    weekly.index = weekly.index - pd.Timedelta(days=4)
    return weekly.pct_change()


def main():
    parent = verify_manifest(PARENT)
    _, prices, _, _ = _load_state()
    split_payload = json.loads((ROOT / "momentum_ml/cache/borsdata/stocksplits_from2000.json").read_text())
    splits = borsdata.split_events_map(split_payload)
    divs = cached_dividends()
    actions = pd.read_csv(PIT_ACTIONS, parse_dates=["event_date"])
    rows = []
    for ticker, iid in IDS.items():
        br = weekly_borsdata(iid, divs, splits)
        yr = prices[ticker].Close.pct_change()
        for date, bret in br[br.abs() > JUMP].items():
            near = yr.loc[(yr.index >= date - pd.Timedelta(days=7)) &
                          (yr.index <= date + pd.Timedelta(days=7))].dropna()
            if near.empty:
                cls, ydate, yret = "UNRESOLVED_NO_FALLBACK_HISTORY", pd.NaT, float("nan")
            else:
                # Compare to the largest same-direction fallback move, not the
                # largest absolute move, to avoid pairing a rebound to a crash.
                same = near[near.mul(float(bret)).gt(0)]
                if same.empty:
                    ydate, yret, cls = near.abs().idxmax(), float(near.loc[near.abs().idxmax()]), "VENDOR_CONFLICT"
                else:
                    ydate = same.abs().idxmax(); yret = float(same.loc[ydate])
                    cls = "CORROBORATED_MARKET_MOVE" if abs(yret) >= CORROBORATION else "VENDOR_CONFLICT"
            ev = actions[actions.ticker.eq(ticker) & actions.event_date.notna()]
            nearest = ((ev.event_date - date).abs().dt.days.min() if len(ev) else float("nan"))
            rows.append({"ticker": ticker, "borsdata_id": iid, "borsdata_week": date.date(),
                         "borsdata_return": float(bret), "fallback_week": None if pd.isna(ydate) else ydate.date(),
                         "fallback_return": yret, "classification": cls,
                         "nearest_pit_action_days": nearest, "borsdata_split_events": len(splits.get(iid, [])),
                         "cached_dividend_events": len(divs.get(iid, []))})
    events = pd.DataFrame(rows).sort_values(["ticker", "borsdata_week"])
    events.to_csv(EVENTS, index=False)
    summary = []
    for ticker, group in events.groupby("ticker"):
        classes = set(group.classification)
        if "UNRESOLVED_NO_FALLBACK_HISTORY" in classes:
            decision = "BLOCKED_MISSING_REFERENCE"
        elif "VENDOR_CONFLICT" in classes:
            decision = "REQUIRES_CORPORATE_ACTION_RECONSTRUCTION"
        else:
            decision = "BORSDATA_MOVE_CORROBORATED_FALLBACK_NOT_REQUIRED_FOR_JUMP"
        summary.append({"ticker": ticker, "borsdata_id": IDS[ticker], "residual_jumps": len(group),
                        "corroborated": int(group.classification.eq("CORROBORATED_MARKET_MOVE").sum()),
                        "vendor_conflicts": int(group.classification.eq("VENDOR_CONFLICT").sum()),
                        "unresolved": int(group.classification.str.startswith("UNRESOLVED").sum()),
                        "source_decision": decision})
    table = pd.DataFrame(summary).sort_values("ticker")
    table.to_csv(TICKERS, index=False)
    counts = events.classification.value_counts().to_dict()
    complete = not events.classification.str.startswith("UNRESOLVED").any()
    conflicts = int(events.classification.eq("VENDOR_CONFLICT").sum())
    report = {"status": "PASS", "test": "N3-SR49-remediation-A",
              "parent_stage": parent["manifest_sha256"], "tickers": len(IDS), "events": len(events),
              "classification_counts": counts, "audit_completeness_gate": "PASS" if complete else "FAIL",
              "borsdata_reinstatement_gate": "FAIL" if conflicts or not complete else "PASS",
              "decision_rule": "same-sign fallback move >=35% within +/-1 weekly bar corroborates a >50% Borsdata jump; missing reference is unresolved; all else vendor conflict",
              "vendor_conflicts_requiring_reconstruction": conflicts,
              "retrained": False, "prices_changed": False, "production": False}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    stage = freeze_stage("10_fallback_instrument_audit", [OUT, EVENTS, TICKERS, Path(__file__).resolve(), PIT_ACTIONS],
        {"test": "N3-SR49-remediation-A", "audit_completeness_gate": report["audit_completeness_gate"],
         "borsdata_reinstatement_gate": report["borsdata_reinstatement_gate"], "production": False}, parent=PARENT)
    print(table.to_string(index=False)); print(json.dumps(report, indent=2)); print(stage)


if __name__ == "__main__":
    main()
