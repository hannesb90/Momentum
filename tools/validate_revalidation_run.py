"""ACCEPTANSGRIND for revalidation-resultat.

Ett resultat far inte foras in i ledger, champion eller preregistrerade resultat
utan att denna grind sager VALID. Allt annat ar REVALIDATION_RESULT_INVALID.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
BASE = V2 / "validated/prices_adjustment_repair_v4"
FORBIDDEN_MARKERS = ("validated/prices/prices_validated.json.bak", "prices_validated_v1_1",
                     "prices_v2_0", "prices_adjustment_repair_v2", "prices_adjustment_repair_v3",
                     "_SUPERSEDED_", "eodhd_archive", "prod_work/cache")


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def validate_revalidation_run(run_dir: Path, expected_script_sha: str | None = None) -> dict:
    fel: list[str] = []
    mp = Path(run_dir) / "EXECUTION_MANIFEST.json"
    if not mp.exists():
        return {"status": "REVALIDATION_RESULT_INVALID", "fel": ["exekveringsmanifest saknas"]}
    m = json.loads(mp.read_text())

    if m.get("execution_mode") != "REVALIDATION":
        fel.append(f"mode ar {m.get('execution_mode')}, inte REVALIDATION — "
                   f"far aldrig raknas som ny revalidation")
    krav = ["run_id", "test_id", "script_path", "script_sha256", "timestamp_utc", "execution_mode",
            "price_file", "price_sha256", "restriction_registry", "restriction_registry_sha256",
            "restriction_registry_version", "price_gate_sha256", "sandbox_sha256",
            "universe_manifest", "universe_sha256", "identity_mapping_hash",
            "h1419_gated_sha256", "h1419_registry_sha256", "fundamental_registry_sha256",
            "fundamental_pit_gate_sha256", "identity_map_sha256",
            "effective_sample_dates", "excluded_observations", "gate_status", "exit_status"]
    saknade = [k for k in krav if k not in m or m[k] is None]
    if saknade:
        fel.append(f"ofullstandigt manifest, saknar: {saknade}")

    live = {"price_sha256": BASE / "prices_validated_adjustment_repair_v4.json",
            "restriction_registry_sha256": BASE / "PRICE_RESTRICTION_REGISTRY.json",
            "price_gate_sha256": V2 / "tools/revalidation_price_gate.py",
            "sandbox_sha256": V2 / "tools/revalidation_sandbox.py",
            "h1419_gated_sha256": V2 / "validated/prices_h1419_gated/prices_h1419_gated.json",
            "h1419_registry_sha256": V2 / "validated/prices_h1419_gated/PRICE_H1419_RESTRICTION_REGISTRY.json",
            "fundamental_registry_sha256": V2 / "validated/fundamentals_gated/FUNDAMENTAL_RESTRICTION_REGISTRY.json",
            "fundamental_pit_gate_sha256": V2 / "tools/fundamental_pit_gate.py",
            "identity_map_sha256": V2 / "research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json"}
    for key, p in live.items():
        if key in m and p.exists() and m[key] != sha(p):
            fel.append(f"hash-avvikelse pa {key}: manifest {str(m[key])[:16]}… mot faktisk {sha(p)[:16]}…")

    if m.get("gate_status") != "PASS":
        fel.append(f"PriceGate status {m.get('gate_status')}, inte PASS")
    if m.get("exit_status") not in (0, "DRY_RUN"):
        fel.append(f"exit_status {m.get('exit_status')}")
    if expected_script_sha and m.get("script_sha256") != expected_script_sha:
        fel.append("script-SHA matchar inte den preregistrerade versionen")

    al = Path(run_dir) / "access_log.json"
    if al.exists():
        log = json.loads(al.read_text())
        for e in log:
            if e["kind"] == "DENY":
                fel.append(f"forbjuden sokvag oppnades: {e['path']}")
            if e["kind"] == "REDIRECT" and any(x in e["path"] for x in FORBIDDEN_MARKERS):
                fel.append(f"gammalt prisdataset i loggen: {e['path']}")
    elif m.get("exit_status") != "DRY_RUN":
        fel.append("access_log saknas — kan inte visa att inga forbjudna vagar oppnades")

    gv = m.get("gated_view") or {}
    if m.get("exit_status") != "DRY_RUN" or True:
        if not gv.get("gated_view_sha256"):
            fel.append("restriktionsregistret applicerades inte — ingen gatad vy")
        elif gv.get("exkluderade_observationer") is None:
            fel.append("gatad vy saknar redovisning av uteslutna observationer")

    ung = m.get("ungated_inputs_allowed") or []
    status = ("REVALIDATION_RESULT_INVALID" if fel else
              ("VALID_WITH_UNGATED_INPUT" if ung else "VALID"))
    return {"status": status, "ungated_inputs": ung,
            "run_id": m.get("run_id"), "test_id": m.get("test_id"),
            "execution_mode": m.get("execution_mode"), "fel": fel}


if __name__ == "__main__":
    r = validate_revalidation_run(Path(sys.argv[1]))
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r["status"] == "VALID" else 1)
