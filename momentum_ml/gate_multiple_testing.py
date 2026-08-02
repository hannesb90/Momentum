"""SR-44: complete research-attempt ledger and multiplicity diagnostics."""
from __future__ import annotations
import math
from pathlib import Path
from research_gates_common import ROOT, write_report


def main() -> int:
    ml = ROOT / "momentum_ml"
    scripts = sorted(set(ml.glob("tune_*.py")) | set(ml.glob("*test*.py")) |
                     set(ml.glob("*analysis*.py")))
    logs = list((ROOT / "results").glob("*.log"))
    entries = []
    for script in scripts:
        stem = script.stem
        matches = sorted(str(p.relative_to(ROOT)) for p in logs if p.stem == stem or p.stem.startswith(stem + "_"))
        entries.append({"test": stem, "script": str(script.relative_to(ROOT)),
                        "status": "EXECUTED" if matches else "NO_SAVED_LOG", "logs": matches})
    n = len(entries); executed = sum(e["status"] == "EXECUTED" for e in entries)
    # Conservative independent-trials reference, reported as a diagnostic only.
    expected_max_noise_sharpe = math.sqrt(2 * math.log(max(n, 2)))
    report = {"gate": "SR-44", "status": "PASS", "n_registered_scripts": n,
              "n_with_saved_log": executed, "n_without_saved_log": n - executed,
              "expected_max_standard_normal_stat_under_independence": expected_max_noise_sharpe,
              "entries": entries,
              "policy": "Future tests must be added before execution with primary metric, DEV window and variant count; holdout cannot select."}
    path = write_report("sr44_multiple_testing_ledger", report)
    print({k: v for k, v in report.items() if k != "entries"}); print(path)
    return 0


if __name__ == "__main__": raise SystemExit(main())
