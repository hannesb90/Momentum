#!/usr/bin/env python3
"""Cross-source event QA for immutable MFN events and Börsdata probes."""

from __future__ import annotations

import glob
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trackj/validated_mfn_events_v1/mfn_borsdata_event_qa.json"


def main() -> None:
    if OUT.exists(): raise RuntimeError("QA output exists; refuse overwrite")
    matching = json.loads((ROOT / "raw/borsdata/_matchning.json").read_text())
    ins_to_code = {int(r["insid"]): r["kod"] for g in ("matchade", "ej_matchade")
                   for r in matching[g] if r.get("insid") is not None}
    bd_report = set(); bd_buyback = []
    for path in glob.glob(str(ROOT / "trackj/j2a_borsdata_api_probe/raw/*/report_calendar/*.json")):
        for block in json.loads(Path(path).read_text()).get("list", []):
            code = ins_to_code.get(int(block["insId"]));
            if not code: continue
            for row in block.get("values", []):
                day = (row.get("releaseDate") or "")[:10]
                if "2020-01-01" <= day <= "2026-08-09": bd_report.add((code, day))
    for path in glob.glob(str(ROOT / "trackj/j2a_borsdata_api_probe/raw/*/buyback/*.json")):
        for block in json.loads(Path(path).read_text()).get("list", []):
            code = ins_to_code.get(int(block["insId"]));
            if not code: continue
            for row in block.get("values", []): bd_buyback.append((code, row))
    mfn_all = set(); mfn_provider = set(); subtype = Counter()
    for line in (ROOT / "trackj/validated_mfn_events_v1/validated_mfn_events.jsonl").open():
        row = json.loads(line)
        families = row["derived_event_families"]
        if "REPORT" in families:
            key = (row["instrument_id"], row["published_at"][:10]); mfn_all.add(key)
            if row["report_classification_basis"] == "MFN_PROVIDER_TAG": mfn_provider.add(key)
        if "BUYBACK_ANNOUNCEMENT" in families: subtype[row["buyback_subtype"]] += 1
    neg = sum((r.get("change") or 0) < 0 for _, r in bd_buyback)
    zero = sum((r.get("price") or 0) == 0 for _, r in bd_buyback)
    result = {
        "version": "MFN_BORSDATA_EVENT_QA_V1",
        "report_calendar": {
            "borsdata_code_dates_through_retrieval_date": len(bd_report),
            "mfn_all_candidate_code_dates": len(mfn_all),
            "mfn_provider_tag_code_dates": len(mfn_provider),
            "exact_borsdata_mfn_all": len(bd_report & mfn_all),
            "borsdata_only_vs_all": len(bd_report - mfn_all),
            "mfn_all_only": len(mfn_all - bd_report),
            "exact_borsdata_mfn_provider": len(bd_report & mfn_provider),
            "borsdata_only_vs_provider": len(bd_report - mfn_provider),
            "mfn_provider_only": len(mfn_provider - bd_report),
            "interpretation": "Börsdata calendar is date-only and mixes unknown actual/estimated status; MFN is publication-time evidence.",
        },
        "buyback": {
            "borsdata_rows": len(bd_buyback), "negative_change_rows": neg, "zero_price_rows": zero,
            "mfn_announcement_subtypes": dict(subtype),
            "semantic_conclusion": "Börsdata change is not safely interpretable as cash repurchase: negative changes and zero prices demonstrate a broader treasury-share ledger. MFN announcements are not transaction-ledger substitutes.",
        },
        "target_feature_model_data_read": False,
    }
    data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(); OUT.write_bytes(data)
    print(json.dumps({**result, "sha256": hashlib.sha256(data).hexdigest()}, indent=2, sort_keys=True))


if __name__ == "__main__": main()
