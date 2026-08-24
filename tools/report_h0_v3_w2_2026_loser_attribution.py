"""Read-only W2 2026 constituent-return attribution for the frozen canonical."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import h0_v3_production as PROD

OUT = ROOT / "research_k/h0_v3_canonical_production_implementation"
CHECKPOINT = OUT / "PRODUCTION_CHECKPOINT_FINALIZATION.json"
CSV_OUT = OUT / "PRODUCTION_W2_2026_CONSTITUENT_ATTRIBUTION.csv"
JSON_OUT = OUT / "PRODUCTION_W2_2026_CONSTITUENT_ATTRIBUTION.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cp = json.loads(CHECKPOINT.read_text())
    if not cp.get("all_gates_pass"):
        raise RuntimeError("Refusing attribution: production checkpoint not PASS")
    PROD.load_engine()
    res = PROD.replay("W2")
    got = PROD.path_hash("W2", res)["sha256"]
    want = cp["evidence"]["path_hashes"]["W2"]["production_sha256"]
    if got != want:
        raise RuntimeError("Refusing attribution: frozen W2 path hash mismatch")
    returns = PROD.V2.CTX["W2"]["returns"]
    totals = defaultdict(lambda: {"n_panels": 0, "weight_sum": 0.0, "contribution": 0.0, "weighted_return_sum": 0.0})
    panel_rows = []
    for panel in res["panels"][:-1]:
        d = panel["date"]
        if not d.startswith("2026-"):
            continue
        for ticker, weight in panel["post_weights"].items():
            ret = float(returns.get((ticker, d), 0.0))
            contrib = weight * ret
            x = totals[ticker]
            x["n_panels"] += 1; x["weight_sum"] += weight
            x["contribution"] += contrib; x["weighted_return_sum"] += weight * ret
            panel_rows.append({"panel_date": d, "ticker": ticker, "post_execution_weight": weight,
                               "subsequent_panel_return": ret, "contribution": contrib})
    rows = []
    for ticker, x in totals.items():
        rows.append({"ticker": ticker, "n_panels_held": x["n_panels"],
                     "mean_post_execution_weight": x["weight_sum"] / x["n_panels"],
                     "aggregate_contribution": x["contribution"],
                     "weighted_average_return": x["weighted_return_sum"] / x["weight_sum"] if x["weight_sum"] else 0.0})
    rows.sort(key=lambda x: x["aggregate_contribution"])
    with CSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    payload = {"scope": "W2 canonical production, scored 2026 decision panels only", "method": "sum of actual post-execution weight times subsequent canonical [t,t+1] security return; security attribution is gross of common portfolio COST_B.", "path_hash": got, "checkpoint_sha256": sha(CHECKPOINT), "panel_rows": panel_rows, "aggregate": rows}
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path_hash_pass": got == want, "worst_10": rows[:10]}, indent=2))


if __name__ == "__main__":
    main()
