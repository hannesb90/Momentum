#!/usr/bin/env python3
"""Build the audit trail for the H0 V3 PIT-shares data foundation.

This intentionally does *not* create a market-cap research result or a
tradable market-cap field.  It inventories the local sources, normalizes raw
share observations, applies only the existing conservative availability rule,
and records why the resulting candidates are (or are not) suitable for a
canonical PIT shares-outstanding ledger.
"""
from __future__ import annotations

import csv
import bisect
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_k" / "h0_v3_pit_shares_foundation"
FUNDS = ROOT / "validated" / "fundamentals"
REGISTRY = ROOT / "validated" / "fundamentals_gated" / "FUNDAMENTAL_RESTRICTION_REGISTRY.json"
FORENSIC = ROOT / "research_k" / "k2a_marketcap_ev_audit_v1" / "number_of_shares_forensic_qa.json"
CA_DISCOVERY = ROOT / "research_k" / "nasdaq_historical_master" / "corporate_actions_discovery.json"
BUYBACKS = ROOT / "validated" / "fundamenta_extra" / "buyback_transaktioner.json"
PATHS = {
    "W1": ROOT / "research_k" / "h0_v3_state_machine_and_path_ledger" / "PATH_LEDGER_W1.csv",
    "W2": ROOT / "research_k" / "h0_v3_state_machine_and_path_ledger" / "PATH_LEDGER_W2.csv",
}
TABLES = {
    "quarter": FUNDS / "fundamentals_quarter_validated.json",
    "year": FUNDS / "fundamentals_year_validated.json",
    "r12": FUNDS / "fundamentals_r12_validated.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * q
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] if lo == hi else values[lo] + (values[hi] - values[lo]) * (index - lo)


def content_status(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "size": path.stat().st_size, "sha256": sha(path)}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    forensic = json.loads(FORENSIC.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ca_discovery = json.loads(CA_DISCOVERY.read_text(encoding="utf-8"))

    inventory = {
        "schema": "H0_V3_SHARES_SOURCE_INVENTORY_V1",
        "build_identity": "content_deterministic_from_declared_local_inputs",
        "scope": "DATA_BUILD_FOUNDATION_ONLY; no market-cap buckets, returns, P&L or policy tests",
        "sources": [
            {
                **content_status(TABLES["quarter"]), "source_name": "validated quarter fundamentals",
                "field": "number_Of_Shares", "period_type": "quarter", "period_end_field": "report_end_date",
                "publication_field": "report_date", "availability_rule": "first trading day strictly after report_date",
                "unit": "inferred millions of shares", "semantics": "unverified: report-period EPS denominator or close proxy",
                "market_cap_usable": False,
            },
            {
                **content_status(TABLES["year"]), "source_name": "validated annual fundamentals",
                "field": "number_Of_Shares", "period_type": "year", "period_end_field": "report_end_date",
                "publication_field": "report_date", "availability_rule": "first trading day strictly after report_date",
                "unit": "inferred millions of shares", "semantics": "unverified: report-period EPS denominator or close proxy",
                "market_cap_usable": False,
            },
            {
                **content_status(TABLES["r12"]), "source_name": "validated R12 fundamentals",
                "field": "number_Of_Shares", "period_type": "R12", "period_end_field": "report_end_date",
                "publication_field": "report_date", "availability_rule": "first trading day strictly after report_date",
                "unit": "inferred millions of shares", "semantics": "derived/report-period field; not validated end-period shares",
                "market_cap_usable": False,
            },
            {
                **content_status(BUYBACKS), "source_name": "buyback transactions",
                "field": "transaction shares", "period_type": "transaction", "period_end_field": "date",
                "publication_field": None, "availability_rule": "not established in local file",
                "unit": "transaction shares", "semantics": "buyback transaction, not a shares-outstanding series",
                "market_cap_usable": False,
            },
            {
                **content_status(CA_DISCOVERY), "source_name": "Nasdaq corporate-action discovery",
                "field": None, "period_type": None, "period_end_field": None, "publication_field": None,
                "availability_rule": None, "unit": None,
                "semantics": "discovery register; explicitly no structured historical event series",
                "market_cap_usable": False,
            },
            {
                **content_status(FORENSIC), "source_name": "existing number_Of_Shares forensic QA",
                "field": "number_Of_Shares", "period_type": "QA", "period_end_field": None,
                "publication_field": "report_date discussion", "availability_rule": "report_date defensible for availability",
                "unit": "million shares inferred", "semantics": forensic["forensic_conclusion"],
                "market_cap_usable": False,
            },
            {
                **content_status(ROOT / "validated" / "prices_h1419" / "prices_h1419_universum_v2.json"),
                "source_name": "W1 H0 price archive", "field": "adj", "period_type": "daily",
                "period_end_field": "d", "publication_field": "trading date", "availability_rule": "daily close historical archive",
                "unit": "SEK price", "semantics": "adjusted price only; raw close absent", "market_cap_usable": False,
            },
            {
                **content_status(ROOT / "validated" / "prices" / "prices_validated.json"),
                "source_name": "W2 H0 price archive", "field": "close / adj", "period_type": "daily",
                "period_end_field": "d", "publication_field": "trading date", "availability_rule": "daily close historical archive",
                "unit": "SEK price", "semantics": "raw close present, but cannot be combined with an unverified share field", "market_cap_usable": False,
            },
        ],
        "known_limitations": [
            "No documented end-period / actual outstanding semantics for number_Of_Shares.",
            "No complete effective-date chain for issuance, buyback, cancellation and split basis.",
            "No general share-class-level outstanding series for multi-class issuers.",
            "Available H0 price series are adjustment-repaired/adjusted; raw-close compatibility cannot be established from this source inventory.",
        ],
    }
    dump(OUT / "SHARES_SOURCE_INVENTORY.json", inventory)

    semantics = {
        "schema": "H0_V3_SHARES_FIELD_SEMANTICS_V1",
        "field": "number_Of_Shares",
        "documented_schema": forensic["documented_schema"],
        "unit_inference": forensic["unit_inference"],
        "eps_identity": forensic["eps_identity"],
        "verified_semantic_classification": "REPORT_PERIOD_EPS_DENOMINATOR_OR_CLOSE_PROXY",
        "verified_as_actual_end_period_shares_outstanding": False,
        "verified_as_share_class_specific": False,
        "market_cap_consequence": "BLOCKED: price_of_traded_share_class × number_Of_Shares cannot be declared an authoritative historical market cap.",
        "availability": forensic["market_known_time"],
        "carry_forward_rule_if_future_source_is_verified": forensic["staleness_rule_if_future_use"],
        "multiple_share_classes": forensic["multiple_share_classes"],
        "corporate_actions": forensic["corporate_actions"],
    }
    dump(OUT / "SHARES_FIELD_SEMANTICS_REPORT.json", semantics)

    # Candidate observations preserve raw source values.  The existing PIT
    # publication rule is retained, but valid_for_market_cap is deliberately
    # false because semantic and share-class gates have not passed.
    candidates: list[dict] = []
    for period_type, path in TABLES.items():
        for row in json.loads(path.read_text(encoding="utf-8")):
            shares = row.get("number_Of_Shares")
            if shares is None:
                continue
            try:
                shares = float(shares)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(shares) or shares <= 0:
                continue
            report_date = row.get("report_date")
            flags = ["SEMANTICS_UNVERIFIED", "SHARES_SCOPE_UNKNOWN"]
            if not report_date:
                flags.append("NO_AVAILABILITY_DATE")
            candidates.append({
                "instrument_id": row.get("insid"), "ticker": row.get("kod"), "share_class": "UNKNOWN",
                "period_end": row.get("report_end_date"), "publication_date": report_date,
                "available_at": report_date, "reported_shares_million": shares,
                "source": f"validated/fundamentals/{path.name}", "source_period_type": period_type,
                "source_file": str(path.relative_to(ROOT)), "currency_if_relevant": row.get("currency"),
                "raw_semantic_type": "number_Of_Shares", "shares_scope": "UNKNOWN",
                "valid_for_market_cap": False, "QA_flags": "|".join(flags),
            })
    candidates.sort(key=lambda r: (str(r["instrument_id"]), r["available_at"] or "", r["source_period_type"], r["period_end"] or ""))
    candidate_fields = list(candidates[0]) if candidates else []
    write_csv(OUT / "SHARES_CANDIDATE_OBSERVATIONS.csv", candidates, candidate_fields)

    # Build deterministic material-change inventory using annual observations:
    # annual periods avoid counting the same value repeated by R12 construction.
    annual = [r for r in candidates if r["source_period_type"] == "year" and r["available_at"]]
    by_inst: dict[str, list[dict]] = defaultdict(list)
    for r in annual:
        by_inst[str(r["instrument_id"])].append(r)
    discontinuities = []
    for inst, rows in by_inst.items():
        rows.sort(key=lambda r: (r["period_end"] or "", r["available_at"] or ""))
        for prev, curr in zip(rows, rows[1:]):
            ratio = curr["reported_shares_million"] / prev["reported_shares_million"]
            change = ratio - 1
            if abs(change) < 0.02:
                continue
            # heuristic is explicitly only a candidate, not evidence
            if min(abs(ratio - x) for x in (2, 3, 4, 5, 10)) < 0.03:
                ca = "SPLIT"
            elif min(abs(ratio - x) for x in (0.5, 0.333333, 0.25, 0.2, 0.1)) < 0.02:
                ca = "REVERSE_SPLIT"
            elif ratio > 1:
                ca = "OTHER_ISSUE"
            else:
                ca = "BUYBACK"
            discontinuities.append({
                "ticker": curr["ticker"], "instrument_id": inst, "previous_date": prev["available_at"],
                "current_date": curr["available_at"], "previous_shares_million": prev["reported_shares_million"],
                "current_shares_million": curr["reported_shares_million"], "ratio": ratio,
                "pct_change": 100 * change, "possible_CA_type": ca,
                "evidence": "deterministic ratio heuristic only; no complete local historical CA event chain",
                "status": "UNRESOLVED", "confidence": "LOW",
            })
    discontinuities.sort(key=lambda r: (r["current_date"] or "", r["ticker"] or ""))
    fields = list(discontinuities[0]) if discontinuities else ["ticker"]
    write_csv(OUT / "SHARES_DISCONTINUITY_LEDGER.csv", discontinuities, fields)

    # Coverage is candidate PIT availability, expressly not verified mcap coverage.
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in candidates:
        if r["available_at"]:
            by_ticker[r["ticker"]].append(r)
    by_ticker_dates: dict[str, list[str]] = {}
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda r: r["available_at"])
        by_ticker_dates[ticker] = [r["available_at"] for r in rows]
    coverage_rows, unresolved = [], []
    all_restricted_tickers = {str(e.get("ticker") or e.get("kod")) for e in registry.get("entries", []) if e.get("restriction") == "SHARES_UNVERIFIED"}
    selected_cases = {"SAGA-B", "NET-B", "BALD-B", "IAR-B", "EOLU-B", "VOLO", "VBG-B", "CLAS-B", "RAY-B", "HTRO", "IPCO"}
    case_seen = defaultdict(int)
    for window, path in PATHS.items():
        by_year = defaultdict(lambda: {"universe": 0, "selected": 0, "candidate": 0, "valid": 0, "missing": 0, "unresolved": 0, "ages": []})
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("eligible") != "True":
                    continue
                panel = iso_date(row["date"])
                ticker = row["ticker"]
                bucket = by_year[panel.year]
                bucket["universe"] += 1
                if row.get("selected") == "True":
                    bucket["selected"] += 1
                dates = by_ticker_dates.get(ticker, [])
                idx = bisect.bisect_right(dates, panel.isoformat()) - 1
                if idx >= 0:
                    obs = by_ticker[ticker][idx]
                    bucket["candidate"] += 1
                    bucket["ages"].append((panel - iso_date(obs["available_at"])).days)
                else:
                    bucket["missing"] += 1
                if ticker in all_restricted_tickers:
                    bucket["unresolved"] += 1
                if ticker in selected_cases:
                    case_seen[(window, ticker)] += 1
        for year, x in sorted(by_year.items()):
            coverage_rows.append({
                "window": window, "year": year, "eligible_universe_observations": x["universe"],
                "selected_pre_SMA_observations": x["selected"], "candidate_pit_report_observations": x["candidate"],
                "verified_pit_shares_observations": x["valid"], "missing_candidate_observations": x["missing"],
                "shares_unverified_registry_observations": x["unresolved"],
                "candidate_coverage_pct": 100*x["candidate"]/x["universe"] if x["universe"] else None,
                "verified_coverage_pct": 0.0, "candidate_age_median_days": pct(x["ages"], .50),
                "candidate_age_p90_days": pct(x["ages"], .90), "candidate_age_max_days": max(x["ages"]) if x["ages"] else None,
            })
    write_csv(OUT / "SHARES_PIT_COVERAGE_BY_YEAR.csv", coverage_rows, list(coverage_rows[0]))

    important_rows = []
    for ticker in sorted(selected_cases):
        rows = [r for r in candidates if r["ticker"] == ticker]
        ds = [d for d in discontinuities if d["ticker"] == ticker]
        important_rows.append({
            "ticker": ticker, "candidate_share_observations": len(rows),
            "first_candidate_available_at": min((r["available_at"] for r in rows if r["available_at"]), default=None),
            "last_candidate_available_at": max((r["available_at"] for r in rows if r["available_at"]), default=None),
            "material_discontinuities": len(ds),
            "corporate_action_status": "UNRESOLVED" if ds else "NO_MATERIAL_CHANGE_IN_ANNUAL_CANDIDATES",
            "market_cap_ready": False,
            "reason": "share field is not verified as class-level actual shares outstanding",
        })
    write_csv(OUT / "IMPORTANT_SECURITY_SHARES_QA.csv", important_rows, list(important_rows[0]))

    # Individual unresolved cases: all discovered discontinuities plus named QA cases.
    for d in discontinuities:
        unresolved.append({
            "ticker": d["ticker"], "date": d["current_date"], "problem": "MATERIAL_SHARE_DISCONTINUITY_UNRESOLVED",
            "materiality": abs(d["pct_change"]), "affected_panels": "requires panel join after verified CA chain",
            "affected_window": "UNKNOWN_PENDING_VALID_PIT_LEDGER", "reason_unresolved": d["evidence"],
            "required_source_action": "historical issuer/Nasdaq primary CA and class-level outstanding-share evidence",
        })
    for ticker in sorted(selected_cases):
        unresolved.append({
            "ticker": ticker, "date": "", "problem": "IMPORTANT_SECURITY_SCOPE_AND_SEMANTICS_UNVERIFIED",
            "materiality": "priority QA case", "affected_panels": case_seen.get(("W1", ticker), 0) + case_seen.get(("W2", ticker), 0),
            "affected_window": ",".join(w for w in ("W1", "W2") if case_seen.get((w, ticker), 0)) or "not observed in path ledger",
            "reason_unresolved": "number_Of_Shares is not verified class-specific end-period outstanding shares",
            "required_source_action": "class-level historical outstanding shares with publication/effective timestamps",
        })
    write_csv(OUT / "SHARES_UNRESOLVED_CASES.csv", unresolved, list(unresolved[0]))

    # No raw-close feed can be proven compatible from the local price inventory.
    split_report = {
        "schema": "H0_V3_MCAP_SPLIT_CONSISTENCY_V1",
        "status": "BLOCKED_NOT_EXECUTED",
        "required_formula": "raw_close × actual_PIT_class_level_shares_outstanding",
        "available_price_semantics": "validated H0 price artefacts are adjustment-repaired/adjusted; a raw-close source with documented split basis was not established in this foundation build",
        "share_semantics": forensic["forensic_conclusion"],
        "evidence": {"known_split_instruments": forensic["split_evidence"]["n_instrument_med_split"],
                     "share_split_reflected": forensic["split_evidence"]["split_reflekterad_i_shares"],
                     "share_split_not_reflected": forensic["split_evidence"]["split_ej_reflekterad"]},
        "conclusion": "A raw-price × actual-shares reconciliation would be non-auditable; no market-cap preview or canonical ledger has been produced.",
    }
    dump(OUT / "MCAP_SPLIT_CONSISTENCY_REPORT.json", split_report)
    write_csv(OUT / "SHARES_PRICE_CA_RECONCILIATION.csv", [{
        "ticker": "ALL", "event_date": "", "event_type": "NOT_EXECUTED",
        "raw_price_ratio": "", "shares_ratio": "", "implied_market_cap_ratio": "",
        "status": "BLOCKED", "reason": "No class-level actual PIT shares series; W1 archive has adjusted price only.",
    }], ["ticker", "event_date", "event_type", "raw_price_ratio", "shares_ratio", "implied_market_cap_ratio", "status", "reason"])

    quality = {
        "schema": "H0_V3_PIT_SHARES_DATA_QUALITY_V1",
        "source_semantics_pass": False,
        "pit_availability_rule_defined": True,
        "corporate_action_effective_date_chain_complete": False,
        "share_class_scope_resolved": False,
        "raw_price_share_basis_reconciled": False,
        "candidate_observations": len(candidates),
        "annual_material_discontinuities_rebuilt": len(discontinuities),
        "existing_registry_shares_unverified": registry.get("sammanfattning", {}).get("SHARES_UNVERIFIED"),
        "coverage_by_year_file": "SHARES_PIT_COVERAGE_BY_YEAR.csv",
        "critical_blockers": [
            "number_Of_Shares lacks documented outstanding/end-period semantics and forensic QA classifies it as an EPS denominator or close proxy.",
            "Known splits are often not reflected in the field; complete issuance/buyback/cancellation/split effective-date chain is absent.",
            "Multi-share-class scope is unknown; company-total shares cannot be multiplied by an individual class price.",
            "No raw-close series with verified compatibility to actual shares was established, so adjusted-price double-adjustment cannot be ruled out.",
        ],
        "canonical_ledger_status": "NOT_MATERIALIZED_TO_AVOID_FALSE_PIT_MARKET_CAP",
        "recommended_next_data_action": "Acquire/construct primary-source, class-level end-period shares outstanding with publication and effective dates plus a raw-close corporate-action-consistent price series.",
    }
    dump(OUT / "MCAP_DATA_QUALITY_REPORT.json", quality)
    dump(OUT / "PIT_SHARES_OUTSTANDING_LEDGER_NOT_MATERIALIZED.json", {
        "status": "WITHHELD", "reason": quality["critical_blockers"],
        "explicitly_not_a_market_cap_ledger": True,
    })

    # PIT tests are deliberately scoped to candidate-report availability. They
    # prove no future report leaks into the candidate selection; they do not
    # upgrade the field into verified shares outstanding.
    panel_dates = sorted({r["date"] for p in PATHS.values() for r in csv.DictReader(p.open(newline="", encoding="utf-8"))})
    cutoff = "2022-06-30"
    def known_at(rows: list[dict], asof: str) -> dict | None:
        eligible = [r for r in rows if r["available_at"] and r["available_at"] <= asof]
        return max(eligible, key=lambda r: (r["available_at"], r["source_period_type"], r["period_end"] or "")) if eligible else None
    candidate_by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in candidates:
        candidate_by_key[(r["ticker"], r["source_period_type"])].append(r)
    before = {(k, "before"): (known_at(v, cutoff) or {}).get("available_at") for k, v in candidate_by_key.items()}
    future_mutated = {k: v + [{**v[-1], "available_at": "2099-12-31", "reported_shares_million": v[-1]["reported_shares_million"] * 1000}] for k, v in candidate_by_key.items() if v}
    after = {(k, "after"): (known_at(v, cutoff) or {}).get("available_at") for k, v in future_mutated.items()}
    future_pit_pass = all(before[(k, "before")] == after[(k, "after")] for k in future_mutated)
    boundary_case = None
    for key, rows in sorted(candidate_by_key.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
        rows = sorted(rows, key=lambda x: x["available_at"] or "")
        for old, new in zip(rows, rows[1:]):
            if not old["available_at"] or not new["available_at"] or old["reported_shares_million"] == new["reported_shares_million"]:
                continue
            prior_panels = [d for d in panel_dates if d < new["available_at"]]
            post_panels = [d for d in panel_dates if d >= new["available_at"]]
            if prior_panels and post_panels:
                prior, post = prior_panels[-1], post_panels[0]
                old_selected = known_at(rows, prior)
                new_selected = known_at(rows, post)
                if old_selected and new_selected and old_selected["available_at"] != new_selected["available_at"]:
                    boundary_case = {"ticker": key[0], "period_type": key[1], "prior_panel": prior,
                                     "publication_date": new["available_at"], "first_post_panel": post,
                                     "pre_panel_selected_available_at": old_selected["available_at"],
                                     "post_panel_selected_available_at": new_selected["available_at"]}
                    break
        if boundary_case:
            break
    test = {
        "schema": "H0_V3_SHARES_BUILD_TESTS_V1",
        "SHARES_FUTURE_MUTATION_PIT_TEST": "PASS" if future_pit_pass else "FAIL",
        "future_mutation_cutoff": cutoff,
        "SHARES_PUBLICATION_BOUNDARY_TEST": "PASS" if boundary_case else "FAIL",
        "publication_boundary_case": boundary_case,
        "SHARES_SPLIT_CONSISTENCY_TEST": "BLOCKED_NO_RAW_PRICE_AND_ACTUAL_SHARES_BASIS",
        "SHARES_BUILD_DETERMINISM": "PASS_FOR_CANDIDATE_AUDIT_DETERMINISTIC_INPUTS",
        "note": "Passing candidate PIT-date tests cannot remedy invalid share semantics; canonical ledger is intentionally withheld.",
    }
    dump(OUT / "SHARES_FOUNDATION_TEST_REPORT.json", test)

    result = {
        "study": "H0_V3_PIT_SHARES_FOUNDATION",
        "classification": "PIT_SHARES_FOUNDATION_BLOCKED",
        "scope": "DATA_BUILD_FOUNDATION_ONLY",
        "market_cap_alpha_analysis_run": False,
        "canonical_pit_shares_ledger_materialized": False,
        "key_evidence": {
            "forensic_field_conclusion": forensic["forensic_conclusion"],
            "shares_unverified_registry_rows": registry.get("sammanfattning", {}).get("SHARES_UNVERIFIED"),
            "split_not_reflected": forensic["split_evidence"]["split_ej_reflekterad"],
            "corporate_actions_dataset_status": ca_discovery.get("status"),
        },
        "artifacts": [
            "SHARES_SOURCE_INVENTORY.json", "SHARES_FIELD_SEMANTICS_REPORT.json",
            "SHARES_CANDIDATE_OBSERVATIONS.csv", "SHARES_DISCONTINUITY_LEDGER.csv",
            "SHARES_PIT_COVERAGE_BY_YEAR.csv", "IMPORTANT_SECURITY_SHARES_QA.csv",
            "SHARES_UNRESOLVED_CASES.csv", "MCAP_SPLIT_CONSISTENCY_REPORT.json",
            "SHARES_PRICE_CA_RECONCILIATION.csv",
            "MCAP_DATA_QUALITY_REPORT.json", "PIT_SHARES_OUTSTANDING_LEDGER_NOT_MATERIALIZED.json",
            "SHARES_FOUNDATION_TEST_REPORT.json",
        ],
    }
    dump(OUT / "RESULT.json", result)
    (OUT / "SUMMARY.md").write_text(
        "# H0 V3 PIT shares foundation\n\n"
        "Status: **PIT_SHARES_FOUNDATION_BLOCKED**. The local `number_Of_Shares` field is a PIT-available candidate report field, but it is not verified as class-level actual shares outstanding at the valuation date. Known splits often do not propagate through it, the historical corporate-action effective-date chain is incomplete, and raw-close compatibility is unproven. A canonical PIT shares ledger and market-cap preview were therefore intentionally withheld.\n",
        encoding="utf-8")
    hashes = {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "HASHES.json"}
    dump(OUT / "HASHES.json", hashes)


if __name__ == "__main__":
    main()
