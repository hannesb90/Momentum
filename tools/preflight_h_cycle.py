#!/usr/bin/env python3
"""External, read-only operational preflight for sealed H0/H1/H2 tracks.

It deliberately does not modify any lock, challenger implementation or journal.
Run this before a sealing command.  It supplements (and does not replace) the
immutable forward code, whose H1/H2 inbox checks are intentionally narrower.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import sparh_forward as H0

TRACKS = {
    "H0": ROOT / "trackh",
    "H1": ROOT / "research_i/forward_challengers/H1_DRAW_RESILIENCE",
    "H2": ROOT / "research_i/forward_challengers/H2_TREND_STRENGTH",
}
FORBIDDEN = ("target", "forward_return", "future_return", "terminal_outcome", "delisting_outcome")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_ts(value: str) -> dt.datetime:
    value = value.replace("Z", "+00:00")
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return result


def keys_contain_forbidden(value) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(word in str(key).lower() for word in FORBIDDEN) or keys_contain_forbidden(nested):
                return True
    elif isinstance(value, list):
        return any(keys_contain_forbidden(v) for v in value)
    return False


def verify_locks():
    if not __debug__:
        raise SystemExit("FAIL Python assertions disabled; do not run with -O")
    h0 = H0.lock_verify()
    def challenger_lock(path: Path):
        lock = json.loads(path.read_text())
        if sha(ROOT / "trackh/H0_LOCK.json") != lock["h0_lock_sha256"]:
            raise SystemExit(f"FAIL {path.parent.name} H0 lock reference")
        if sha(ROOT / "research_i/FREEZE_MANIFEST_BATCH1.json") != lock["batch1_freeze_sha256"]:
            raise SystemExit(f"FAIL {path.parent.name} batch manifest reference")
        for item in lock["locked_files"]:
            source = ROOT / item["path"]
            if not source.is_file() or sha(source) != item["sha256"] or source.stat().st_size != item["bytes"]:
                raise SystemExit(f"FAIL {path.parent.name} locked file: {item['path']}")
        return lock
    h1 = challenger_lock(ROOT / "research_i/forward_challengers/H1_DRAW_RESILIENCE/LOCK.json")
    h2 = challenger_lock(ROOT / "research_i/forward_challengers/H2_TREND_STRENGTH/LOCK.json")
    return {"H0_lock": sha(ROOT / "trackh/H0_LOCK.json"),
            "H1_lock": sha(ROOT / "research_i/forward_challengers/H1_DRAW_RESILIENCE/LOCK.json"),
            "H2_lock": sha(ROOT / "research_i/forward_challengers/H2_TREND_STRENGTH/LOCK.json"),
            "h0_verified_v4_files": h0["verified_v4_files"],
            "h0_verified_abc_artifacts": h0["verified_abc_artifacts"],
            "h1_first_eligible": h1["first_forward_eligible_panel"],
            "h2_first_eligible": h2["first_forward_eligible_panel"]}


def validate_inbox(track: str, panel: str):
    folder = TRACKS[track] / "inbox" / panel
    manifest_path = folder / "input_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"FAIL {track} inbox manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    required = {"panel_date", "decision_timestamp", "data_as_of_timestamp", "next_scheduled_trading_date", "files"}
    missing = required - set(manifest)
    if missing or manifest["panel_date"] != panel:
        raise SystemExit(f"FAIL {track} malformed manifest: missing={sorted(missing)}")
    decision, asof = parse_ts(manifest["decision_timestamp"]), parse_ts(manifest["data_as_of_timestamp"])
    if decision.date().isoformat() != panel or asof > decision:
        raise SystemExit(f"FAIL {track} decision/as-of chronology")
    execution_day = dt.date.fromisoformat(manifest["next_scheduled_trading_date"])
    if execution_day <= dt.date.fromisoformat(panel):
        raise SystemExit(f"FAIL {track} execution date is not after decision")
    roles = {}
    duplicates = []
    for entry in manifest["files"]:
        role, path = entry.get("role"), entry.get("path")
        if not role or not path:
            raise SystemExit(f"FAIL {track} file entry lacks role/path")
        if role in roles:
            duplicates.append(role)
        file_path = folder / path
        if not file_path.is_file() or sha(file_path) != entry.get("sha256"):
            raise SystemExit(f"FAIL {track} file hash: {path}")
        roles[role] = file_path
    if duplicates or not {"prices", "universe"} <= set(roles):
        raise SystemExit(f"FAIL {track} required/unique roles: duplicates={duplicates}")
    upstream = manifest.get("upstream_manifests", [])
    for item in upstream:
        source = Path(item["path"])
        source = source if source.is_absolute() else ROOT / source
        if not source.is_file() or sha(source) != item.get("sha256") or parse_ts(item["as_of"]) > decision:
            raise SystemExit(f"FAIL {track} upstream manifest provenance")
    prices, universe = json.loads(roles["prices"].read_text()), json.loads(roles["universe"].read_text())
    if not isinstance(prices, dict) or not isinstance(universe, list) or keys_contain_forbidden(universe):
        raise SystemExit(f"FAIL {track} invalid or target-contaminated inputs")
    codes = [r.get("kod") for r in universe]
    if None in codes or len(codes) != len(set(codes)):
        raise SystemExit(f"FAIL {track} universe codes not unique")
    investable = []
    for row in universe:
        if "known_at" not in row or parse_ts(row["known_at"]) > decision:
            raise SystemExit(f"FAIL {track} universe known_at")
        if not row.get("investable"):
            continue
        kod = row["kod"]
        series = prices.get(kod)
        if not series:
            raise SystemExit(f"FAIL {track} investable security lacks price history: {kod}")
        dates = [x.get("d") for x in series]
        if dates != sorted(dates) or len(dates) != len(set(dates)) or any(d is None or d > panel for d in dates):
            raise SystemExit(f"FAIL {track} invalid price chronology: {kod}")
        if any(not isinstance(x.get("adj"), (int, float)) or x["adj"] <= 0 for x in series):
            raise SystemExit(f"FAIL {track} invalid adjusted price: {kod}")
        investable.append(kod)
    # The locked forward motors retain holdings on their 4-week in-between
    # panel.  Do not let an untradable inherited holding silently pass through
    # that branch: stop before sealing and require an explicit terminal-event
    # decision instead.
    day = dt.date.fromisoformat(panel)
    non_rebalance = ((day - dt.date(2026, 9, 4)).days // 28) % 2 == 1
    journal = TRACKS[track] / "journal/INDEX.jsonl"
    prior = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()] if journal.is_file() else []
    predictions = [entry for entry in prior if entry.get("event") == "PREDICTION"]
    inherited_untradable = []
    if non_rebalance and predictions:
        latest = ROOT / predictions[-1]["path"]
        holdings = json.loads((latest.parent / "planned_holdings.json").read_text())["holdings"]
        universe_state = {row["kod"]: bool(row.get("investable")) for row in universe}
        inherited_untradable = [row["kod"] for row in holdings if not universe_state.get(row["kod"], False)]
        if inherited_untradable:
            raise SystemExit(f"FAIL {track} inherited untradable holdings on non-rebalance: {inherited_untradable}")
    return {"track": track, "panel": panel, "decision_timestamp": manifest["decision_timestamp"],
            "data_as_of_timestamp": manifest["data_as_of_timestamp"], "declared_execution_date": str(execution_day),
            "investable_count": len(investable), "upstream_manifest_count": len(upstream),
            "non_rebalance_panel": non_rebalance, "inherited_untradable_holdings": inherited_untradable,
            "execution_validation": "PENDING: decision snapshot correctly ends at decision; independently timestamped execution evidence is required after trading."}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-locks")
    inbox = sub.add_parser("validate-inbox")
    inbox.add_argument("track", choices=TRACKS)
    inbox.add_argument("panel")
    args = parser.parse_args()
    if args.command == "verify-locks":
        print(json.dumps({"status": "PASS", "checks": verify_locks()}, indent=2))
    else:
        verify_locks()
        print(json.dumps({"status": "PASS", "checks": validate_inbox(args.track, args.panel)}, indent=2))


if __name__ == "__main__":
    main()
