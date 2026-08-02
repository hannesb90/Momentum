"""Run all pre-alpha research gates without stopping after the first failure."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess, sys
from research_gates_common import ROOT, OUT

GATES = ["gate_baseline_parity.py", "gate_corporate_actions.py",
         "gate_placebo_leakage.py", "gate_multiple_testing.py"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    status = {}
    for gate in GATES:
        log = OUT / f"{Path(gate).stem}.log"
        with log.open("w", encoding="utf-8") as fh:
            proc = subprocess.run([sys.executable, gate], cwd=ROOT / "momentum_ml",
                                  stdout=fh, stderr=subprocess.STDOUT, check=False)
        status[gate] = {"returncode": proc.returncode, "status": "PASS" if proc.returncode == 0 else "FAIL",
                        "log": str(log.relative_to(ROOT))}
    overall = "PASS" if all(v["returncode"] == 0 for v in status.values()) else "FAIL"
    summary = {"status": overall, "gates": status}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__": raise SystemExit(main())
