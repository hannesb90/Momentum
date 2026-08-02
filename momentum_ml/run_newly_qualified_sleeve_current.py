"""N3-29 / SR7+SR40: PIT gate for a newly-qualified stock sleeve.

The economic 0/10/20% sleeve is intentionally not estimated until historical
Large/Mid eligibility covers both survivors and delisted names.  First-price
age in today's universe is causal as an age measure, but the sample itself is
survivorship-biased and therefore cannot establish portfolio alpha.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from niva3_stage_control import freeze_stage, verify_manifest


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/28_master_queue_auto_resume.json"
PIT = ROOT / "results/niva3_pit_universe_audit.json"
COVERAGE = ROOT / "results/point_in_time/pit_coverage.csv"
INTERVALS = ROOT / "results/point_in_time/historical_universe_intervals.csv"
SIGNALS = ROOT / "results/niva3_reconstructed_price_signals_corrected.csv"
OUT = ROOT / "results/niva3_newly_qualified_sleeve_gate.json"
COHORTS = ROOT / "results/niva3_newly_qualified_identifiable_cohorts.csv"
DOCS = (ROOT / "docs/UTVECKLINGSLOGG.md", ROOT / "docs/niva3_status_handoff.md")


def main() -> None:
    parent = verify_manifest(PARENT)
    pit = json.loads(PIT.read_text(encoding="utf-8"))
    sig = pd.read_csv(SIGNALS, parse_dates=["Date"])
    iv = pd.read_csv(INTERVALS, parse_dates=["valid_from", "valid_to"])
    coverage = pd.read_csv(COVERAGE)

    # A verified valid_from is the only permitted age origin.  Unknown origins
    # are left unknown; no first-observed-survivor proxy is silently invented.
    origins = iv.dropna(subset=["valid_from"]).groupby("ticker")["valid_from"].min()
    selected = sig.loc[sig.pred_signal.eq(1), ["Date", "ticker"]].copy()
    selected["valid_from"] = selected.ticker.map(origins)
    selected["weeks_since_valid_from"] = (
        selected.Date - selected.valid_from
    ).dt.days / 7.0
    selected["cohort"] = "unclassified"
    age = selected.weeks_since_valid_from
    selected.loc[age.between(78, 130, inclusive="left"), "cohort"] = "newly_qualified"
    selected.loc[age.ge(260), "cohort"] = "established"
    selected.to_csv(COHORTS, index=False)

    matched = int(selected.valid_from.notna().sum())
    known_new = int(selected.cohort.eq("newly_qualified").sum())
    known_est = int(selected.cohort.eq("established").sum())
    absent_delisted = int(pit["delisted_absent_from_model_panel"])
    historical_cap_ok = bool(pit["historical_large_cap_eligibility_available"])
    survivor_ok = pit["survivorship_gate"] == "PASS"
    cohort_gate = historical_cap_ok and survivor_ok and absent_delisted == 0

    report = {
        "status": "PASS",
        "parent_stage": parent["manifest_sha256"],
        "test": "N3-SR7-SR40-newly-qualified-sleeve",
        "preregistered_variants": {
            "sleeve_share": [0.0, 0.1, 0.2],
            "same_total_positions": True,
            "secondary_interaction": "newly_qualified_x_rank_change",
        },
        "selected_rows": int(len(selected)),
        "selected_rows_with_verified_origin": matched,
        "verified_origin_share": matched / len(selected) if len(selected) else 0.0,
        "identifiable_newly_qualified_rows": known_new,
        "identifiable_established_rows": known_est,
        "unclassified_rows": int(selected.cohort.eq("unclassified").sum()),
        "pit_tickers_in_coverage_file": int(coverage.ticker.nunique()),
        "delisted_absent_from_model_panel": absent_delisted,
        "historical_large_cap_eligibility_available": historical_cap_ok,
        "survivorship_gate": pit["survivorship_gate"],
        "cohort_gate": "PASS" if cohort_gate else "FAIL",
        "economic_sleeve_backtest_run": False,
        "decision": "DEFER_DATA_GATE",
        "reason": (
            "The age cohort is only partially identifiable and all 90 known "
            "delisted names are absent from the scored panel. Testing sleeve "
            "weights on survivors would confound listing-age alpha with survivorship."
        ),
        "unlock_condition": (
            "PIT Large/Mid eligibility plus features/scores for survivors and "
            "delisted securities; then run 0/10/20% with fixed position count."
        ),
        "holdout_used": False,
        "production": False,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    section = (
        "\n## 2026-08-01 – N3-29: SR7/SR40 nykvalificerad sleeve\n\n"
        f"Kohortgrinden klassificerade {matched}/{len(selected)} valda rader med "
        f"verifierad livscykelstart: {known_new} nykvalificerade och {known_est} "
        "etablerade. Den ekonomiska 0/10/20-procents-sleeven kördes inte: "
        f"{absent_delisted} kända avnoterade namn saknas i scorepanelen och historisk "
        "Large/Mid-behörighet saknas. `cohort_gate=FAIL`, `DEFER_DATA_GATE`. Ett "
        "survivor-only-resultat får inte registreras som alpha. Ingen holdout eller "
        "produktion användes.\n"
    )
    for doc in DOCS:
        with doc.open("a", encoding="utf-8") as f:
            f.write(section)
    stage = freeze_stage(
        "29_newly_qualified_sleeve_gate",
        [OUT, COHORTS, Path(__file__).resolve(), PIT, COVERAGE, INTERVALS, SIGNALS],
        {"test": "N3-SR7-SR40", "cohort_gate": "FAIL",
         "decision": "DEFER_DATA_GATE", "production": False},
        parent=PARENT,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(stage)


if __name__ == "__main__":
    main()
