"""Quantify what V2 can and cannot prove about historical main-list membership."""
from __future__ import annotations

import glob
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "docs/probes/membership_pit_audit.json"
MAIN_DESTINATION = re.compile(
    r"ny\s+notering(?:\s+av\s+[^.]{0,50})?\s+p[åa]\s+"
    r"(?:nasdaq\s+stockholm|nordiska\s+listan|[oa]-listan)", re.I)


def main() -> None:
    spec = importlib.util.spec_from_file_location("instrument_master_v2",
                                                  V2 / "tools/instrument_master_v2.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text())
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    ledger = json.loads((V2 / "validated/membership_main_list_pit.json").read_text())
    membership = {r["kod"]: r for r in ledger["rows"]}
    entries = defaultdict(list)
    for row in master:
        code = (row.get("eodhd") or {}).get("code")
        files = sorted(glob.glob(str(V2 / "raw/skatteverket/pages" /
                                     f"{row['slug']}__*.html")))
        if not code or not files:
            continue
        parsed = module.tolka_sida(Path(files[-1]).read_text(errors="replace"))
        if not parsed:
            continue
        for event in parsed["handelser"]:
            if event["typ"] == "notering" and MAIN_DESTINATION.search(event["text"]):
                entries[code].append({"date": event["datum"], "year": event["ar"],
                                      "evidence": event["text"], "slug": row["slug"]})

    panel_codes = {r["kod"] for r in core}
    confirmed_pre_entry = []
    for row in core:
        dates = sorted({e["date"] for e in entries.get(row["kod"], []) if e["date"]})
        if dates and row["panel_date"] < dates[0]:
            confirmed_pre_entry.append({"kod": row["kod"], "panel_date": row["panel_date"],
                                        "first_verified_main_list_entry": dates[0]})
    violations = [r for r in core if membership[r["kod"]]["membership_verified"] and
                  r["panel_date"] < membership[r["kod"]]["member_from"]]
    verified_rows = [r for r in core if membership[r["kod"]]["membership_verified"]]
    report = {
        "definition": "Prisexistens är inte membership. Endast explicit destination till Nasdaq "
                      "Stockholm/Nordiska listan/O-/A-listan räknas som verifierad entry.",
        "n_panel_codes": len(panel_codes),
        "n_codes_with_explicit_main_list_entry": len(panel_codes & set(entries)),
        "n_codes_without_explicit_main_list_entry": len(panel_codes - set(entries)),
        "n_ledger_membership_verified": sum(r["membership_verified"] for r in ledger["rows"]),
        "n_ledger_membership_unknown": sum(not r["membership_verified"] for r in ledger["rows"]),
        "n_panel_rows_membership_verified": len(verified_rows),
        "n_panel_rows_membership_unknown": len(core) - len(verified_rows),
        "share_panel_rows_membership_verified": len(verified_rows) / len(core),
        "n_confirmed_pre_entry_rows_lower_bound": len(confirmed_pre_entry),
        "n_confirmed_pre_entry_codes_lower_bound": len({r["kod"] for r in confirmed_pre_entry}),
        "confirmed_pre_entry_rows": confirmed_pre_entry,
        "entry_evidence": {k: v for k, v in sorted(entries.items()) if k in panel_codes},
        "nasdaq_ledger": ledger,
        "n_rows_before_ledger_membership_after_rebuild": len(violations),
        "status": "KÄND DATASETBEGRÄNSNING: daterade admissions filtreras; övrig historisk "
                  "membership är explicit okänd och har ingen påhittad entry_date",
    }
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("confirmed_pre_entry_rows", "entry_evidence")}, indent=2,
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
