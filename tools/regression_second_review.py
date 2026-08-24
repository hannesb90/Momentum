"""Read-only regression gates for the 2026-08-08 independent second review."""
from __future__ import annotations

import json
import hashlib
import copy
from datetime import date, timedelta
from collections import defaultdict
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")


def load(path: str):
    return json.loads((V2 / path).read_text(encoding="utf-8"))


def main() -> None:
    prices = load("validated/prices/prices_validated.json")
    core = load("panels/core_panel.json")
    target = load("panels/target_table.json")
    terminal = load("validated/terminal_events.json")
    master = load("docs/probes/instrument_master.json")
    bextra = load("validated/fundamenta_extra/kpi_ebitda_capex.json")
    aman = load("validated/manifest_sparA.json")
    membership = {r["kod"]: r for r in load("validated/membership_main_list_pit.json")["rows"]}
    fund = load("panels/core_fundamenta_panel.json")
    blueprint = load("docs/probes/feature_blueprint.json")
    external = load("validated/external_dependencies_manifest.json")["active_dependencies"][0]

    assert all(set(r) == {"d", "adj", "close", "v"}
               for rows in prices.values() for r in rows)
    assert all(r["adj"] > 0 and r["close"] > 0 for rows in prices.values() for r in rows)

    # Every separate terminal outcome must have explicit master evidence;
    # no shortened realization may leak into the canonical 52-week target.
    target_rows = [(kod, r) for kod, rows in target.items() for r in rows]
    assert not [r for _, r in target_rows
                if r.get("target_fwd52w") is not None and r.get("target_typ") != "forward_52w"]
    for kod, r in target_rows:
        if r.get("target_typ") == "forward_52w":
            lag = (date.fromisoformat(r["panel_date"]) + timedelta(weeks=52) -
                   date.fromisoformat(next(x["d"] for x in reversed(prices[kod])
                                           if x["d"] <= (date.fromisoformat(r["panel_date"]) +
                                                          timedelta(weeks=52)).isoformat()))).days
            assert 0 <= lag <= 8
        if r.get("terminal_return") is not None:
            assert kod in terminal
            assert r["terminal_event_date"] == terminal[kod]["event_date"]
            assert r["terminal_horisont_dagar"] < 364
    for kod in ("FLERIE", "KDEV", "FPIP", "MAHA-A", "NYF"):
        assert kod not in terminal
        assert not any(r.get("terminal_return") is not None for r in target.get(kod, []))

    # Entity groups are explicit and group attributes were validated by A builder.
    groups = defaultdict(list)
    for r in master:
        kod = (r.get("eodhd") or {}).get("code")
        if kod:
            groups[kod].append(r)
    assert {k for k, v in groups.items() if len(v) > 1 and k in prices} == {
        k for k, v in aman["entity_resolution"].items() if v["n_masterposter"] > 1}

    # Unknown membership has no invented admission date. No observation may
    # precede an admission where membership is actually source-verified.
    by_core = {(r["kod"], r["panel_date"]): r for r in core}
    assert len(by_core) == len(core)
    assert all((m["member_from"] is not None and m["source"] and m["membership_verified"])
               if m["membership_verified"] else
               (m["member_from"] is None and m["source"] is None)
               for m in membership.values())
    assert all(r["panel_date"] >= membership[r["kod"]]["member_from"]
               for r in core if membership[r["kod"]]["membership_verified"])
    assert all(r["membership_verified"] == membership[r["kod"]]["membership_verified"]
               for r in core)

    # Monetary features remain excluded until an actual unadjusted transaction
    # price / PIT market-cap basis has been QA-approved. Null is intentional.
    assert all(r.get("turnover_13w_msek") is None and
               r.get("illiquidity_amihud_13w") is None for r in core)
    assert all(r.get("fcf_yield_ttm") is None and
               r.get("dividend_yield_ttm") is None for r in fund)
    bp = {r["id"]: r for r in blueprint}
    for fid in ("turnover_13w_msek", "illiquidity_amihud_13w",
                "dividend_yield_ttm", "fcf_yield_ttm"):
        assert bp[fid]["status"] == "BLOCKERAD/SAKNAR DATA"
    for kod, rows in prices.items():
        assert len(rows) == len({r["d"] for r in rows})

    # Exact external inventory semantics: change/add/remove all fail.
    from build_external_dependencies_manifest import inventory_matches
    expected, agg = external["files"], external["aggregate_sha256"]
    assert inventory_matches(expected, copy.deepcopy(expected), agg)
    changed = copy.deepcopy(expected)
    changed[0]["sha256"] = "0" * 64
    added = copy.deepcopy(expected) + [{"path": "unexpected", "size": 0, "sha256": "0" * 64}]
    removed = copy.deepcopy(expected[:-1])
    assert not inventory_matches(expected, changed, agg)
    assert not inventory_matches(expected, added, agg)
    assert not inventory_matches(expected, removed, agg)

    # Monetary KPI rows retain local value and exactly one SEK conversion.
    for r in bextra:
        if r["value_local"] is None or r["currency_ratio"] is None:
            assert r["value_sek"] is None
        else:
            assert abs(r["value_sek"] - r["value_local"] * r["currency_ratio"]) < 1e-7

    print(json.dumps({
        "prices": sum(len(v) for v in prices.values()),
        "core_rows": len(core),
        "target_rows": len(target_rows),
        "terminal_events": len(terminal),
        "terminal_outcomes_separate": sum(r.get("terminal_return") is not None
                                           for _, r in target_rows),
        "entity_duplicate_code_groups": sum(len(v) > 1 for v in groups.values()),
        "kpi_extra_rows": len(bextra),
        "status": "PASS",
    }, indent=2))


if __name__ == "__main__":
    main()
