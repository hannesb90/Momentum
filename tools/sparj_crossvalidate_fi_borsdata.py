#!/usr/bin/env python3
"""Conservative FI versus Börsdata insider-data QA; no features or targets."""

from __future__ import annotations

import glob
import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
def norm(value, places: str) -> str | None:
    if value in (None, ""): return None
    return str(Decimal(str(value)).quantize(Decimal(places)))


def fi_signed_quantity(row: dict) -> str | None:
    value = row.get("quantity")
    if value in (None, ""): return None
    amount = Decimal(str(value))
    kind = (row.get("transaction_character") or "").lower()
    negative = any(token in kind for token in ("avyttring", "gåva lämnad", "utdelning lämnad", "försälj"))
    return norm(-abs(amount) if negative else abs(amount), "0.0001")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validated-dir", default="trackj/validated_fi_insider_v2")
    args = ap.parse_args()
    validated_dir = ROOT / args.validated_dir
    fi_path = validated_dir / "validated_fi_insider.jsonl"
    out = validated_dir / "fi_borsdata_crossvalidation.json"
    if out.exists(): raise RuntimeError("cross-validation output exists; refuse overwrite")
    match = json.loads((ROOT / "raw/borsdata/_matchning.json").read_text())
    ins_to_identity = {int(r["insid"]): (r["kod"], r["isin"]) for group in ("matchade", "ej_matchade")
                       for r in match[group] if r.get("insid") is not None and r.get("isin")}
    fi_rows = [json.loads(x) for x in fi_path.read_text().splitlines()]
    fi_index = defaultdict(list)
    for row in fi_rows:
        key = (row["instrument_id"], row["transaction_date"], fi_signed_quantity(row),
               norm(row["price"], "0.0001"), row["currency"])
        fi_index[key].append(row)
    bd_rows = []
    for path in sorted(glob.glob(str(ROOT / "trackj/j2a_borsdata_api_probe/raw/*/insider/*.json"))):
        for block in json.loads(Path(path).read_text()).get("list", []):
            identity = ins_to_identity.get(int(block["insId"]))
            if not identity: continue
            code, isin = identity
            for value in block.get("values", []):
                tx = (value.get("transactionDate") or "")[:10]
                if not tx or tx < "2020-01-01" or tx > "2026-08-09": continue
                bd_rows.append({**value, "instrument_id": code, "isin": isin})
    matched_bd = 0; matched_fi = set(); lags = []; ambiguous = 0
    for row in bd_rows:
        key = (row["instrument_id"], (row.get("transactionDate") or "")[:10],
               norm(row.get("shares"), "0.0001"), norm(row.get("price"), "0.0001"), row.get("currency"))
        candidates = fi_index.get(key, [])
        if not candidates: continue
        matched_bd += 1
        if len(candidates) > 1: ambiguous += 1
        # This is QA matching only. Never merge the sources automatically.
        # Börsdata verificationDate is an ISO timestamp without offset and is
        # documented/empirically aligned as UTC; make that assumption explicit.
        bd_time = datetime.fromisoformat(row["verificationDate"])
        if bd_time.tzinfo is None:
            bd_time = bd_time.replace(tzinfo=timezone.utc)
        closest = min(candidates, key=lambda x: abs((datetime.fromisoformat(x["market_known_time"]) - bd_time).total_seconds()))
        matched_fi.add(closest["source_record_fingerprint_sha256"])
        lags.append((bd_time - datetime.fromisoformat(closest["market_known_time"])).total_seconds() / 3600)
    current_codes = {v[0] for v in ins_to_identity.values()}
    fi_current = [r for r in fi_rows if r["instrument_id"] in current_codes]
    result = {
        "version": "FI_BORSDATA_CROSSVALIDATION_V1",
        "matching_rule": "exact instrument bridge + transaction date + exact signed quantity(4dp) + price(4dp) + currency",
        "automatic_source_merge": False,
        "borsdata_rows_2020_2026_current_instruments": len(bd_rows),
        "fi_rows_2020_2026_current_instruments": len(fi_current),
        "borsdata_rows_with_conservative_fi_match": matched_bd,
        "fi_rows_used_by_conservative_match": len(matched_fi),
        "ambiguous_borsdata_matches": ambiguous,
        "unmatched_borsdata_rows": len(bd_rows) - matched_bd,
        "unmatched_fi_rows": len(fi_current) - len(matched_fi),
        "verification_minus_fi_publication_hours": {
            "count": len(lags), "median": statistics.median(lags) if lags else None,
            "min": min(lags) if lags else None, "max": max(lags) if lags else None,
            "nonzero": sum(abs(x) > 1 / 3600 for x in lags),
        },
        "interpretation": "FI is primary evidence; Börsdata is QA only because its verificationDate and coded transaction semantics are secondary.",
        "target_feature_model_data_read": False,
    }
    data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    out.write_bytes(data)
    print(json.dumps({**result, "sha256": hashlib.sha256(data).hexdigest()}, indent=2, sort_keys=True))


if __name__ == "__main__": main()
