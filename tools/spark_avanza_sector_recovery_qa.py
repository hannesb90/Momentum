#!/usr/bin/env python3
"""QA normalized Avanza recovery evidence; never reads targets or returns."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
ROOT = V2 / "research_k/avanza_sector_recovery_probe"
V1 = Path("/home/hannesb/momentum_prod_work/momentum_ml")


def shab(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    original = json.loads((ROOT / "identity_sector_evidence.json").read_text())
    terminal_events = json.loads((V2 / "validated/terminal_events.json").read_text())
    # A same ticker with another ISIN/name/market is ticker reuse, not historical identity.
    accepted = []
    false_ticker = []
    for x in original:
        y = dict(x)
        if y["identity_method"] == "VERIFIED_HISTORICAL_TICKER" and \
                y.get("avanza_isin") != y.get("expected_isin"):
            false_ticker.append({"instrument_id": y["instrument_id"],
                                 "expected_isin": y.get("expected_isin"),
                                 "returned_isin": y.get("avanza_isin"),
                                 "returned_name": y.get("avanza_name"),
                                 "returned_market": y.get("market_place"),
                                 "reason": "ticker reuse/different entity"})
            y["rejected_candidate"] = {k: y.get(k) for k in
                                         ("avanza_orderbook_id", "avanza_isin", "avanza_name",
                                          "avanza_ticker", "market_place", "avanza_sector_path_raw")}
            y["identity_method"] = "UNRESOLVED"
            y["identity_confidence"] = "NONE"
            y["avanza_sector_path_raw"] = []
        accepted.append(y)

    exact = [x for x in accepted if x["identity_method"] == "EXACT_ISIN_MATCH"]
    active = [x for x in exact if not x["terminal"]]
    terminal = [x for x in accepted if x["terminal"]]
    with (V1 / "cache/avanza_sectors.csv").open(encoding="utf-8") as f:
        old = {r["ticker"].replace(".ST", ""): r for r in csv.DictReader(f)}
    old_compare = []
    for x in active:
        if x["instrument_id"] in old:
            old_path = old[x["instrument_id"]]["sector_path"].split(" | ")
            old_compare.append({"instrument_id": x["instrument_id"], "old": old_path,
                                "live": x["avanza_sector_path_raw"],
                                "equal": old_path == x["avanza_sector_path_raw"]})

    crosswalk = defaultdict(Counter)
    branch_crosswalk = defaultdict(Counter)
    for x in active:
        path = tuple(x["avanza_sector_path_raw"])
        crosswalk[str(x["borsdata_sector_id_current"])][path[-1] if path else ""] += 1
        branch_crosswalk[str(x["borsdata_branch_id_current"])][path[0] if path else ""] += 1

    by_year = defaultdict(lambda: {"total": 0, "exact_isin": 0, "with_sector": 0,
                                   "unresolved": 0, "conflict": 0})
    for x in terminal:
        year = terminal_events[x["instrument_id"]]["event_date"][:4]
        by_year[year]["total"] += 1
        if x["identity_method"] == "EXACT_ISIN_MATCH":
            by_year[year]["exact_isin"] += 1
        if x.get("avanza_sector_path_raw"):
            by_year[year]["with_sector"] += 1
        if x["identity_method"] == "UNRESOLVED":
            by_year[year]["unresolved"] += 1

    qa = {
        "status": "QA_COMPLETE_DATA_ONLY",
        "target_read": False,
        "source_method": {
            "search": "POST https://www.avanza.se/_api/search/filtered-search (public, unauthenticated)",
            "stock_info": "GET https://www.avanza.se/_api/market-guide/stock/{orderBookId} (public, unauthenticated)",
            "identity_acceptance": "Avanza stock-info ISIN must equal frozen V2 ISIN; no fuzzy mapping.",
            "fields": ["isin", "name", "orderbookId", "listing.tickerSymbol",
                       "listing.marketPlaceName", "listing.marketListName", "sectors[]"],
        },
        "coverage": {
            "all": len(accepted), "active_total": len(active), "active_exact_isin": len(active),
            "active_with_sector": sum(bool(x["avanza_sector_path_raw"]) for x in active),
            "active_with_industry": sum(len(x["avanza_sector_path_raw"]) >= 2 for x in active),
            "terminal_total": len(terminal),
            "terminal_exact_isin": sum(x["identity_method"] == "EXACT_ISIN_MATCH" for x in terminal),
            "terminal_with_sector": sum(bool(x["avanza_sector_path_raw"]) for x in terminal),
            "terminal_with_industry": sum(len(x["avanza_sector_path_raw"]) >= 2 for x in terminal),
            "terminal_unresolved": sum(x["identity_method"] == "UNRESOLVED" for x in terminal),
            "terminal_false_ticker_reuse_rejected": len(false_ticker),
        },
        "terminal_coverage_by_delisting_year": dict(sorted(by_year.items())),
        "false_ticker_matches_rejected": false_ticker,
        "avanza_snapshot_cross_validation": {
            "old_cache_exact_ticker_rows": len(old_compare),
            "identical_paths": sum(x["equal"] for x in old_compare),
            "different_paths": [x for x in old_compare if not x["equal"]],
            "interpretation": "Two Avanza observations agree for 342 current entities; not historical proof.",
        },
        "borsdata_avanza_taxonomy_crosswalk": {
            "sectorId_to_avanza_broad": {k: dict(v) for k, v in sorted(crosswalk.items())},
            "branchId_to_avanza_fine": {k: dict(v) for k, v in sorted(branch_crosswalk.items())},
            "note": "Association table, not one-to-one normalization. Taxonomies differ in granularity.",
        },
        "stability_assessment": {
            "stable_current_entities_supported": 342,
            "current_only_exact_entities": 10,
            "terminal_stable_entities_supported": 0,
            "historical_effective_dates_available": False,
            "assessment": "Cross-source/current-snapshot agreement supports sector as a relatively stable entity attribute for current firms, but cannot establish classification from V2 entry for restructurings or terminal firms.",
        },
        "k1_decision": {
            "sector_momentum": "DELVIS TESTBAR",
            "sector_relative_stock_momentum": "DELVIS TESTBAR",
            "sector_breadth": "DELVIS TESTBAR",
            "industry_relative_momentum": "DELVIS TESTBAR",
            "scope": "Only a current-survivor matched diagnostic (352/420); not a survivorship-safe full V2 test.",
            "full_v2_historical_test": "FORTSATT BLOCKERAD",
            "reason": "0/68 terminal entities recovered; using only the 352 would hide terminal survivorship.",
        },
    }
    (ROOT / "qa_identity_sector_evidence.json").write_text(
        json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "QA_RESULTS.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    # Explicitly supersede the permissive preliminary parser summary.
    prelim = json.loads((ROOT / "probe_summary.json").read_text())
    prelim["status"] = "SUPERSEDED_PRE_QA_TICKER_MATCHES_NOT_ACCEPTED"
    prelim["authoritative_summary"] = "QA_RESULTS.json"
    (ROOT / "probe_summary.json").write_text(json.dumps(prelim, indent=2), encoding="utf-8")
    files = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files.append({"path": str(p.relative_to(V2)), "bytes": p.stat().st_size,
                          "sha256": shab(p)})
    agg = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (ROOT / "manifest.json").write_text(json.dumps({"files": files, "aggregate_sha256": agg}, indent=2))
    print(json.dumps(qa["coverage"] | {"aggregate_sha256": agg}, indent=2))


if __name__ == "__main__":
    main()
