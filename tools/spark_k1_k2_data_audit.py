#!/usr/bin/env python3
"""Read-only K1/K2 data/provenance audit. Never reads targets or results."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import subprocess
from bisect import bisect_right
from collections import Counter
from datetime import date
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
V1 = Path("/home/hannesb/momentum_prod_work")
OUT = V2 / "research_k/data_audit_k1_k2"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def source(p: Path, retrieved: str | None, identity: str, granularity: str, note: str):
    st = p.stat()
    return {"path": str(p), "sha256": sha(p), "bytes": st.st_size,
            "mtime": st.st_mtime, "retrieved_at_evidence": retrieved,
            "identity": identity, "granularity": granularity, "note": note}


def main() -> None:  # noqa: C901
    OUT.mkdir(parents=True, exist_ok=True)
    prices = load(V2 / "validated/prices/prices_validated.json")
    panel = load(V2 / "panels/core_panel.json")
    terminal = set(load(V2 / "validated/terminal_events.json"))
    codes = set(prices)
    active = codes - terminal
    match_doc = load(V2 / "raw/borsdata/_matchning.json")
    match = {x["kod"]: x for x in match_doc["matchade"]}

    bd_paths = [
        V1 / "momentum_ml/cache/borsdata/instruments_all.json",
        V1 / "momentum_ml/cache/borsdata/instruments_all_refresh.json",
        V2 / "docs/probes/instruments_live.json",
    ]
    retrieval = ["2026-07-27 (filesystem evidence only)",
                 "2026-08-02 (filesystem evidence only)",
                 "2026-08-09 (J2A probe snapshot)"]
    bd_maps, sources = [], []
    for p, rt in zip(bd_paths, retrieval):
        d = load(p)
        rows = d.get("instruments", d) if isinstance(d, dict) else d
        by_isin = {x.get("isin"): x for x in rows if x.get("isin")}
        by_ins = {x.get("insId"): x for x in rows if x.get("insId") is not None}
        mapped = {}
        for code in codes:
            m = match.get(code)
            if m:
                hit = by_isin.get(m.get("isin")) or by_ins.get(m.get("insid"))
                if hit:
                    mapped[code] = hit
        bd_maps.append(mapped)
        sources.append(source(p, rt, "ISIN or verified V2 insId bridge",
                              "sectorId + branchId snapshot",
                              "Current instrument-register snapshot; no effective-from/to fields."))

    avanza = V1 / "momentum_ml/cache/avanza_sectors.csv"
    with avanza.open(encoding="utf-8") as f:
        av_rows = list(csv.DictReader(f))
    av_by_ticker = {r["ticker"].replace(".ST", ""): r for r in av_rows}
    sweden = V1 / "momentum_ml/data/sweden_universe.csv"
    with sweden.open(encoding="utf-8") as f:
        sw_rows = list(csv.DictReader(f))
    sw_by_ticker = {r["ticker"].replace(".ST", ""): r for r in sw_rows}
    sources.extend([
        source(avanza, "2026-07-27 (filesystem; extractor verified 2026-07-18)",
               "ticker only", "Avanza fine/mid/broad sector snapshot",
               "Extractor overwrites by ticker; not accepted as historical identity."),
        source(sweden, "git history first commit 2026-06-26; last substantive 2026-07-15",
               "ticker only", "FinanceDatabase broad sector snapshot",
               "Filtered current/non-delisted universe; no ISIN or effective dates."),
    ])

    # Same-taxonomy changes across the three Börsdata snapshots.
    conflicts = []
    classifications = []
    for code in sorted(codes):
        vals = [(m[code].get("sectorId"), m[code].get("branchId"))
                for m in bd_maps if code in m]
        if len(set(vals)) > 1:
            cls = "CONFLICT"
            conflicts.append({"kod": code, "values": vals})
        elif len(vals) >= 2:
            cls = "STABLE CLASSIFICATION SUPPORTED"
        elif len(vals) == 1:
            cls = "CURRENT ONLY"
        else:
            cls = "UNKNOWN"
        classifications.append({"kod": code, "terminal": code in terminal,
                                "classification": cls,
                                "borsdata_values": vals,
                                "avanza_ticker_only_hit": code in av_by_ticker,
                                "finance_database_ticker_only_hit": code in sw_by_ticker})

    cls_counts = Counter(x["classification"] for x in classifications)
    # All panel dates end before the earliest defensible snapshot date.
    earliest_snapshot = date(2026, 7, 27)
    pit_rows = sum(date.fromisoformat(r["panel_date"]) >= earliest_snapshot and
                   any(r["kod"] in m for m in bd_maps) for r in panel)
    k1 = {
        "scope": {"v2_instruments": len(codes), "active": len(active),
                  "terminal": len(terminal), "panel_rows": len(panel),
                  "last_panel_date": max(r["panel_date"] for r in panel)},
        "sources": sources,
        "borsdata_exact_coverage": [{"snapshot": str(p), "all": len(m),
                                      "active": len(set(m) & active),
                                      "terminal": len(set(m) & terminal)}
                                     for p, m in zip(bd_paths, bd_maps)],
        "ticker_only_diagnostic_coverage": {
            "avanza_all": len(codes & set(av_by_ticker)),
            "avanza_terminal": len(terminal & set(av_by_ticker)),
            "finance_database_all": len(codes & set(sw_by_ticker)),
            "finance_database_terminal": len(terminal & set(sw_by_ticker)),
            "accepted_as_verified_mapping": 0,
        },
        "instrument_classification_counts": dict(cls_counts),
        "same_taxonomy_conflicts": conflicts,
        "pit_verified_historical_panel_rows_without_backfill_assumption": pit_rows,
        "decisions": {
            "sector_momentum": "FORTSATT BLOCKERAD",
            "sector_relative_momentum": "FORTSATT BLOCKERAD",
            "sector_breadth": "FORTSATT BLOCKERAD",
            "industry_relative_momentum": "FORTSATT BLOCKERAD",
            "reason": "All identified issuer classifications are 2026 snapshots; the frozen panel ends before the earliest snapshot. No historical effective dates exist.",
            "future_from_snapshot_date": "DELVIS TESTBAR after an immutable snapshot exists at or before each decision date; never backfilled.",
        },
        "instrument_periods_usable_without_assumption": 0,
        "panel_rows_usable_without_assumption": pit_rows,
    }

    # K2: validated R12 and point-in-time panel matching; no target is read.
    r12_path = V2 / "validated/fundamentals/fundamentals_r12_validated.json"
    r12 = load(r12_path)
    by_code = {}
    for r in r12:
        by_code.setdefault(r["kod"], []).append(r)
    for rows in by_code.values():
        rows.sort(key=lambda x: x["report_date"])
    dates = {k: [x["report_date"] for x in v] for k, v in by_code.items()}
    matched = []
    for p in panel:
        rs = by_code.get(p["kod"], [])
        i = bisect_right(dates.get(p["kod"], []), p["panel_date"]) - 1
        if i >= 0:
            matched.append((p, rs[i]))

    def present(field):
        rows = [(p, r) for p, r in matched if r.get(field) is not None]
        return {"panel_rows": len(rows), "instruments": len({p["kod"] for p, _ in rows}),
                "terminal_instruments": len({p["kod"] for p, _ in rows} & terminal)}

    sh_rows = [r for r in r12 if r.get("number_Of_Shares") is not None]
    eps_identity = []
    for r in r12:
        a, b, c = r.get("profit_To_Equity_Holders"), r.get("number_Of_Shares"), r.get("earnings_Per_Share")
        if a is not None and b not in (None, 0) and c not in (None, 0):
            eps_identity.append(abs(a / b - c) / abs(c))
    lag = [(date.fromisoformat(p["panel_date"]) - date.fromisoformat(r["report_date"])).days
           for p, r in matched]
    currencies = Counter(x.get("stockPriceCurrency") for x in bd_maps[-1].values())
    split_probe = load(V2 / "docs/probes/fund_split_verify.json")

    k2 = {
        "sources": [
            source(r12_path, "frozen Spår B 2026-08-08", "verified insId→code bridge",
                   "R12 report rows", "report_date is market-known boundary used by V2"),
            source(V2 / "trackj/ohlc_v1/manifest.json", "immutable Track J freeze",
                   "V2 code", "raw and adjusted OHLC extension", "No feature engineering"),
            source(V2 / "docs/probes/fund_split_verify.json", "Spår B QA",
                   "verified code/insId", "split/share diagnostics", "Existing QA evidence"),
        ],
        "r12": {"rows": len(r12), "instruments": len(by_code),
                "number_of_shares_rows": len(sh_rows),
                "number_of_shares_positive_rows": sum((r.get("number_Of_Shares") or 0) > 0 for r in sh_rows),
                "number_of_shares_instruments": len({r["kod"] for r in sh_rows}),
                "eps_identity_n": len(eps_identity),
                "eps_identity_within_1pct": sum(x <= .01 for x in eps_identity) / len(eps_identity),
                "eps_identity_within_10pct": sum(x <= .10 for x in eps_identity) / len(eps_identity)},
        "asof_panel_coverage": {
            "any_fundamentals": {"panel_rows": len(matched), "instruments": len({p['kod'] for p, _ in matched}),
                                 "terminal_instruments": len({p['kod'] for p, _ in matched} & terminal)},
            "number_of_shares": present("number_Of_Shares"),
            "profit": present("profit_To_Equity_Holders"),
            "free_cash_flow": present("free_Cash_Flow"),
            "revenues": present("revenues"),
            "book_equity": present("total_Equity"),
            "net_debt": present("net_Debt"),
        },
        "report_staleness_days": {"min": min(lag), "median": sorted(lag)[len(lag)//2], "max": max(lag)},
        "current_stock_price_currency_for_exactly_mapped_instruments": dict(currencies),
        "split_alignment_evidence": {
            "instrument_with_split": split_probe["n_instrument_med_split"],
            "instrument_years_share_change_matches_vendor_factor": split_probe["split_reflekterad_i_shares"],
            "instrument_years_not_matching_vendor_factor": split_probe["split_ej_reflekterad"],
            "interpretation": "Existing QA cannot establish a split-only price/share basis. EODHD adjustment_factor also reflects cash distributions; adjusted_close is total-return adjusted, while raw close conflicts with retrospectively restated/per-report share bases around some actions.",
        },
        "semantic_findings": {
            "number_of_shares": "API schema supplies no outstanding-vs-weighted-average definition. Strong profit/number_Of_Shares≈EPS identity shows it is at least an EPS/report-period denominator, not verified shares outstanding at panel date.",
            "unit": "Empirical identity supports million shares: report monetary values are SEK million and quotient is SEK/share.",
            "pit": "Latest report_date is PIT-known, but its share count is stale between reports and does not encode exact effective dates for issuance, buybacks or splits.",
            "price_basis": "Unadjusted close is executable price but cannot be paired safely with an unverified/restated share basis. adjusted_close includes distributions and therefore is not a market-cap price.",
            "currency": "Most/current exact mappings quote SEK; non-SEK listings require explicit price conversion aligned to report SEK totals.",
        },
        "market_cap_decision": "FORTSATT BLOCKERAD AS EXACT PIT MARKET CAP",
        "market_cap_proxy": "DELVIS BYGGBAR only as explicitly named latest-reported-share market-cap proxy after a separate split/action basis QA; not approved as market cap here.",
        "value_metrics": {
            "earnings_yield": "BLOCKERAD (market-cap denominator or split-aligned EPS/price basis not verified)",
            "fcf_yield": "BLOCKERAD (market cap)",
            "sales_yield": "BLOCKERAD (market cap)",
            "book_to_market": "BLOCKERAD (market cap)",
            "dividend_yield": "BLOCKERAD (per-share/price split basis not verified)",
            "ebitda_to_ev": "BLOCKERAD (market cap; EBITDA itself approved)",
            "ev_to_ebitda": "BLOCKERAD (market cap)",
            "ev_note": "net_Debt is PIT-available on the matched population, but EV cannot be approved until market cap is approved; no need to infer debt-cash separately where approved net_Debt exists.",
        },
        "survivorship": {"status": "NOT SURVIVORSHIP SAFE", "terminal_total": len(terminal),
                         "terminal_with_any_r12_asof_panel": len({p['kod'] for p, _ in matched} & terminal),
                         "known_limitation": "67/68 terminal instruments lack fundamentals."},
        "preregisterable_path_without_testing": [
            "Obtain or validate historical shares outstanding with effective dates (not weighted-average/report-period shares).",
            "Build a split-only price basis or prove exact alignment between historical share basis and price basis; do not use total-return adjusted_close for market cap.",
            "Account for issuance/buyback effective dates and non-SEK price conversion.",
            "Then freeze a separate market-cap/EV data extension and use matched-population diagnostics marked NOT SURVIVORSHIP SAFE.",
        ],
    }

    audit = {"audit": "K1/K2 DATA AND PROVENANCE ONLY", "target_read": False,
             "alpha_or_backtest_run": False, "k1": k1, "k2": k2}
    (OUT / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "k1_instrument_classification.json").write_text(
        json.dumps(classifications, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"files": []}
    for p in sorted(OUT.glob("*.json")):
        if p.name == "manifest.json":
            continue
        manifest["files"].append({"path": str(p.relative_to(V2)), "bytes": p.stat().st_size,
                                  "sha256": sha(p)})
    payload = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
    manifest["aggregate_sha256"] = hashlib.sha256(payload).hexdigest()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"k1": k1["scope"] | {"classes": dict(cls_counts), "pit_rows": pit_rows},
                      "k2": k2["r12"] | {"asof_shares": present("number_Of_Shares")},
                      "manifest": manifest["aggregate_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
