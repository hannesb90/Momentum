"""REVALIDATION_RUNNER — enda sanktionerade korvagen for framtida revalidation.

Tva strikt atskilda lagen:

  HISTORICAL_REPRODUCTION   legacy-skript mot legacy-data, gamla sokvagar tillatna.
                            Anvands ENBART for att aterskapa en tidigare korning.
                            Resultatet far ALDRIG raknas som ny revalidation.

  REVALIDATION              obligatorisk central runner, kanonisk datafrysning,
                            PriceGate, restriktionsregister och exekveringsmanifest.
                            Gamla prisvagar ar oatkomliga.

Legacy-skripten ror vi inte. Enforcement sker i miljon runt dem: en gatad prisvy
materialiseras ur den kanoniska filen enligt restriktionsregistret, den gamla
sokvagen pekas om dit, och alla ovriga prisvagar ar forbjudna.

Den gatade vyn byggs deterministiskt:
  * instrument med boundary  -> endast langsta giltiga segment exponeras, sa att
                                ingen rullande berakning KAN korsa en sparr
  * RAW_CLOSE_INVALID        -> instrumentet utesluts helt om testet deklarerat
                                att det laser 'close'; annars behalls det
Varje utesluten observation rakans och skrivs i manifestet. Ingen tyst filtrering.

Kor:
  python tools/revalidation_runner.py --test-id T0123 --script tools/x.py \
         --mode REVALIDATION --price-fields adj
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
BASE = V2 / "validated/prices_adjustment_repair_v4"
GATE_MANIFEST = BASE / "REVALIDATION_PRICE_GATE_MANIFEST.json"
REGISTRY = BASE / "PRICE_RESTRICTION_REGISTRY.json"
PRICES = BASE / "prices_validated_adjustment_repair_v4.json"
RUNS = V2 / "research_k/revalidation_runs"

LEGACY_PRICE = V2 / "validated/prices/prices_validated.json"
FORBIDDEN = [
    V2 / "validated/prices/prices_validated.json.bak_2026-08-15",
    V2 / "validated/prices/prices_validated_v1_1.json",
    V2 / "validated/prices_v2_0",
    V2 / "validated/prices_adjustment_repair_v2",
    V2 / "validated/prices_adjustment_repair_v3",
    V2 / "validated/_SUPERSEDED_2026-08-08_valutabugg",
    Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive"),
    Path("/home/hannesb/momentum_prod_work/cache"),
]

# H1419 (2014-2019-fonstret) har nu ett eget restriktionsregister och en gatad vy.
# De tva universumfilerna pekas om dit; mellanstegen i bygget ar forbjudna.
H1419_GATED = V2 / "validated/prices_h1419_gated/prices_h1419_gated.json"
H1419_REGISTRY = V2 / "validated/prices_h1419_gated/PRICE_H1419_RESTRICTION_REGISTRY.json"
H1419_REDIRECT = {
    V2 / "validated/prices_h1419/prices_h1419_universum_v2.json": H1419_GATED,
    V2 / "validated/prices_h1419/prices_h1419_universum.json": H1419_GATED,
}
H1419_FORBIDDEN = [V2 / "validated/prices_h1419/prices_h1419_preliminar.json",
                   V2 / "validated/prices_h1419/prices_h1419_klassificerad.json"]

H1419_WITH_VOLUME = V2 / "validated/prices_h1419_gated/prices_h1419_gated_with_volume.json"
BENCHMARK_GATED = V2 / "validated/benchmark_gated/benchmark_xact_sverige_gated.json"
ADAPTERS = V2 / "tools/revalidation_adapters.py"
# Registrerade adaptrar: modul som patchas -> patchfunktion i revalidation_adapters
ADAPTER_REGISTRY = {"prima_storbolag": "patch_prima_storbolag"}

FUND_REGISTRY = V2 / "validated/fundamentals_gated/FUNDAMENTAL_RESTRICTION_REGISTRY.json"
IDENTITY_MAP = V2 / "research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json"
FUND_GATE = V2 / "tools/fundamental_pit_gate.py"
# Superseded fundamenta ar redan i FORBIDDEN via _SUPERSEDED_-katalogen.

# Ogatade lager: tomt sedan H1419 gatades. Mekanismen behalls for framtida fall.
UNGATED: dict = {}

MODES = ("REVALIDATION", "HISTORICAL_REPRODUCTION")


class RunnerError(RuntimeError):
    pass


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _preflight() -> dict:
    """Obligatoriska komponenter. Saknas nagon far ingen revalidation koras."""
    krav = {"gate_manifest": GATE_MANIFEST, "restriction_registry": REGISTRY,
            "canonical_prices": PRICES, "price_gate_impl": V2 / "tools/revalidation_price_gate.py",
            "sandbox_impl": V2 / "tools/revalidation_sandbox.py"}
    saknas = [k for k, p in krav.items() if not p.exists()]
    if saknas:
        raise RunnerError(f"HARD FAIL — obligatoriska komponenter saknas: {saknas}")
    man = json.loads(GATE_MANIFEST.read_text())
    for namn, p, key in (("prisfil", PRICES, "price_sha256"),
                         ("register", REGISTRY, "registry_sha256")):
        if sha(p) != man[key]:
            raise RunnerError(f"HARD FAIL — {namn} matchar inte gate-manifestet")
    reg = json.loads(REGISTRY.read_text())
    if reg["registry_version"] != man["registry_version"]:
        raise RunnerError("HARD FAIL — registerversion matchar inte manifestet")
    # datafrysning: universum + identitet (fundamenta/PIT laggs till nar de ar klara)
    univ = V2 / "research_k/nasdaq_historical_master/canonical_universe/canonical_pit_universe.json"
    if not univ.exists():
        raise RunnerError("HARD FAIL — universum-/datafrysningsmanifest saknas")
    for namn, p_ in (("H1419 gatad vy", H1419_GATED), ("H1419-register", H1419_REGISTRY)):
        if not p_.exists():
            raise RunnerError(f"HARD FAIL — {namn} saknas: {p_}")
    h1man = json.loads((V2 / "validated/prices_h1419_gated/H1419_GATED_MANIFEST.json").read_text())
    if sha(H1419_GATED) != h1man["gated_sha256"] or sha(H1419_REGISTRY) != h1man["registry_sha256"]:
        raise RunnerError("HARD FAIL — H1419 gatad vy eller register matchar inte sitt manifest")
    for namn, p_ in (("H1419 med volym", H1419_WITH_VOLUME), ("gatad benchmark", BENCHMARK_GATED),
                     ("adaptermodul", ADAPTERS)):
        if not p_.exists():
            raise RunnerError(f"HARD FAIL — {namn} saknas: {p_}")
    vman = json.loads((V2 / "validated/h1419_volume_v1/H1419_VOLUME_MANIFEST.json").read_text())
    if sha(V2 / "validated/h1419_volume_v1/h1419_volume.json") != vman["output_sha256"]:
        raise RunnerError("HARD FAIL — H1419-volymlagret matchar inte sitt manifest")
    if not FUND_REGISTRY.exists():
        raise RunnerError("HARD FAIL — fundamentalt restriktionsregister saknas")
    if not IDENTITY_MAP.exists():
        raise RunnerError("HARD FAIL — kanonisk identitetskarta saknas")
    freg = json.loads(FUND_REGISTRY.read_text())
    for k, v in freg["kallor"].items():
        if sha(V2 / v["path"]) != v["sha256"]:
            raise RunnerError(f"HARD FAIL — fundamentaltabell {k} matchar inte registret")
    return {"gate_manifest": man, "registry": reg,
            "universe_manifest": str(univ.relative_to(V2)), "universe_sha256": sha(univ),
            "identity_mapping_version": man["identity_mapping_version"],
            "price_gate_sha256": sha(V2 / "tools/revalidation_price_gate.py"),
            "sandbox_sha256": sha(V2 / "tools/revalidation_sandbox.py"),
            "h1419_gated_sha256": sha(H1419_GATED),
            "h1419_registry_sha256": sha(H1419_REGISTRY),
            "h1419_registry_version": json.loads(H1419_REGISTRY.read_text())["registry_version"],
            "fundamental_registry_sha256": sha(FUND_REGISTRY),
            "fundamental_registry_version": freg["version"],
            "fundamental_table_sha256": {k: v["sha256"] for k, v in freg["kallor"].items()},
            "fundamental_pit_gate_sha256": sha(FUND_GATE),
            "identity_map_sha256": sha(IDENTITY_MAP),
            "identity_map_version": json.loads(IDENTITY_MAP.read_text())["version"],
            "h1419_with_volume_sha256": sha(H1419_WITH_VOLUME),
            "benchmark_gated_sha256": sha(BENCHMARK_GATED),
            "adapters_sha256": sha(ADAPTERS),
            "fundamentals_pit_manifest": str(FUND_REGISTRY.relative_to(V2))}


VIEW_CACHE = V2 / "research_k/revalidation_runs/_gated_view_cache"


def build_gated_view(price_fields: list[str], out: Path) -> dict:
    """Materialisera den restriktionsmaskade prisvyn. Deterministisk och cachad
    pa (prisfil-SHA, register-SHA, deklarerade falt) — samma indata ger samma vy."""
    key = hashlib.sha256(
        (sha(PRICES) + sha(REGISTRY) + ",".join(sorted(price_fields))).encode()).hexdigest()[:16]
    VIEW_CACHE.mkdir(parents=True, exist_ok=True)
    cv, cm = VIEW_CACHE / f"{key}.json", VIEW_CACHE / f"{key}.meta.json"
    if cv.exists() and cm.exists():
        out.write_bytes(cv.read_bytes())
        meta = json.loads(cm.read_text())
        meta["gated_view_path"] = str(out)
        meta["cache_key"] = key
        return meta
    P = json.loads(PRICES.read_text())
    reg = json.loads(REGISTRY.read_text())
    bounds: dict[str, list[dict]] = {}
    fieldblk: dict[str, list[str]] = {}
    for e in reg["entries"]:
        if e["blocked_operation"] == "BOUNDARY_CROSSING" and e.get("boundary_date"):
            bounds.setdefault(e["ticker"], []).append(e)
        for f in e["blocked_fields"]:
            fieldblk.setdefault(e["ticker"], []).append(f)
    uses_close = "close" in price_fields
    excl_rows = 0
    excl_inst: list[dict] = []
    view = {}
    for kod, rows in P.items():
        blocked = set(fieldblk.get(kod, []))
        if blocked & set(price_fields):
            excl_inst.append({"kod": kod, "skal": "RAW_CLOSE_INVALID och testet deklarerar "
                              f"{sorted(blocked & set(price_fields))}",
                              "rader": len(rows)})
            excl_rows += len(rows)
            continue
        b = sorted({e["boundary_date"] for e in bounds.get(kod, [])})
        if not b:
            view[kod] = rows
            continue
        segs, prev = [], None
        for cut in b + [None]:
            seg = [r for r in rows if (prev is None or r["d"] >= prev) and (cut is None or r["d"] < cut)]
            if seg:
                segs.append(seg)
            prev = cut
        best = max(segs, key=len) if segs else []
        excl_rows += len(rows) - len(best)
        excl_inst.append({"kod": kod, "skal": f"boundary crossing sparrad vid {b}; "
                          f"endast langsta segment exponeras",
                          "rader_fore": len(rows), "rader_efter": len(best),
                          "behallet_intervall": [best[0]["d"], best[-1]["d"]] if best else None})
        if best:
            view[kod] = best
    out.write_text(json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    cv.write_bytes(out.read_bytes())
    meta = {"gated_view_path": str(out), "gated_view_sha256": sha(out), "cache_key": key,
            "instrument_fore": len(P), "instrument_efter": len(view),
            "rader_fore": sum(len(v) for v in P.values()),
            "rader_efter": sum(len(v) for v in view.values()),
            "exkluderade_observationer": excl_rows,
            "restricted_instruments": excl_inst,
            "price_fields_declared": price_fields}
    cm.write_text(json.dumps(meta, ensure_ascii=False))
    return meta


BOOTSTRAP = r'''
import json, sys, runpy, pathlib
sys.path.insert(0, "/home/hannesb/momentum_v2/tools")
import revalidation_sandbox as S
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
S.install(cfg["redirect"], cfg["forbidden"], cfg["run_id"], cfg["test_id"])
try:
    if cfg.get("adapter"):
        import importlib, revalidation_adapters as A
        mod = importlib.import_module(cfg["adapter"])
        info = getattr(A, cfg["adapter_fn"])(mod)
        pathlib.Path(cfg["log"]).with_name("adapter_info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=1))
        mod.main()
    else:
        runpy.run_path(cfg["script"], run_name="__main__")
    rc = 0
except S.RevalidationAccessError as e:
    print(str(e), file=sys.stderr); rc = 42
except SystemExit as e:
    rc = int(e.code or 0)
except Exception as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr); rc = 1
S.dump_log(pathlib.Path(cfg["log"]))
sys.exit(rc)
'''


def run(test_id: str, script: str, mode: str, price_fields: list[str],
        test_family: str = "UNKNOWN", dry_run: bool = False,
        allow_ungated: list[str] | None = None, adapter: str | None = None) -> dict:
    if mode not in MODES:
        raise RunnerError(f"HARD FAIL — okant exekveringslage: {mode}")
    sp = Path(script) if Path(script).is_absolute() else V2 / script
    if not sp.exists():
        raise RunnerError(f"HARD FAIL — skript saknas: {sp}")
    run_id = f"RV-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    RUNS.mkdir(parents=True, exist_ok=True)
    rd = RUNS / run_id
    rd.mkdir()
    man = {"run_id": run_id, "test_id": test_id, "test_family": test_family,
           "script_path": str(sp.relative_to(V2)) if str(sp).startswith(str(V2)) else str(sp),
           "script_sha256": sha(sp),
           "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "execution_mode": mode,
           "code_provenance": "momentum_v2 saknar versionshantering — skript-SHA ar enda provenance",
           "runner_sha256": sha(V2 / "tools/revalidation_runner.py")}

    if mode == "HISTORICAL_REPRODUCTION":
        man.update({"gate_status": "EJ TILLAMPLIG",
                    "note": "Legacy-data och gamla sokvagar tillatna. Resultatet far ALDRIG "
                            "klassas som ny revalidation eller foras in i ledger/champion.",
                    "result_class": "HISTORICAL_REPRODUCTION_ONLY",
                    "exit_status": "DRY_RUN" if dry_run else None})
        (rd / "EXECUTION_MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
        return man

    pf = _preflight()
    man.update({"price_file": str(PRICES.relative_to(V2)), "price_sha256": sha(PRICES),
                "restriction_registry": str(REGISTRY.relative_to(V2)),
                "restriction_registry_sha256": sha(REGISTRY),
                "restriction_registry_version": pf["registry"]["registry_version"],
                "price_gate_version": "revalidation_price_gate.py",
                "price_gate_sha256": pf["price_gate_sha256"],
                "sandbox_sha256": pf["sandbox_sha256"],
                "universe_manifest": pf["universe_manifest"],
                "universe_sha256": pf["universe_sha256"],
                "identity_mapping_hash": pf["identity_mapping_version"],
                "h1419_gated_sha256": pf["h1419_gated_sha256"],
                "h1419_registry_sha256": pf["h1419_registry_sha256"],
                "h1419_registry_version": pf["h1419_registry_version"],
                "fundamental_registry_sha256": pf["fundamental_registry_sha256"],
                "fundamental_registry_version": pf["fundamental_registry_version"],
                "fundamental_table_sha256": pf["fundamental_table_sha256"],
                "fundamental_pit_gate_sha256": pf["fundamental_pit_gate_sha256"],
                "identity_map_sha256": pf["identity_map_sha256"],
                "identity_map_version": pf["identity_map_version"],
                "h1419_with_volume_sha256": pf["h1419_with_volume_sha256"],
                "benchmark_gated_sha256": pf["benchmark_gated_sha256"],
                "adapters_sha256": pf["adapters_sha256"],
                "adapter": adapter,
                "fundamentals_pit_manifest": pf["fundamentals_pit_manifest"]})
    view = build_gated_view(price_fields, rd / "gated_price_view.json")
    man["gated_view"] = view
    rows = json.loads((rd / "gated_price_view.json").read_text())
    dts = sorted({r["d"] for v in rows.values() for r in v})
    man["effective_sample_dates"] = [dts[0], dts[-1]] if dts else None
    man["excluded_observations"] = view["exkluderade_observationer"]
    man["restricted_instruments"] = [x["kod"] for x in view["restricted_instruments"]]

    allow_ungated = allow_ungated or []
    okand = [x for x in allow_ungated if x not in UNGATED]
    if okand:
        raise RunnerError(f"HARD FAIL — okant ogatat lager: {okand}")
    forbidden = [str(f) for f in FORBIDDEN] + [str(f) for f in H1419_FORBIDDEN]
    for namn, path in UNGATED.items():
        if namn not in allow_ungated:
            forbidden.append(str(path))
    man["ungated_inputs_allowed"] = allow_ungated
    man["ungated_input_note"] = (
        "prices_h1419 saknar restriktionsregister och kan inte gatas. Anvands det maste "
        "det deklareras explicit; resultatet far da status VALID_WITH_UNGATED_INPUT."
        if allow_ungated else "inga ogatade lager tillatna i denna korning")
    if adapter and adapter not in ADAPTER_REGISTRY:
        raise RunnerError(f"HARD FAIL — okand adapter: {adapter}")
    cfg = {"adapter": adapter, "adapter_fn": ADAPTER_REGISTRY.get(adapter),
           "script": str(sp), "run_id": run_id, "test_id": test_id,
           "redirect": {str(LEGACY_PRICE): str(rd / "gated_price_view.json"),
                        **{str(k): str(v) for k, v in H1419_REDIRECT.items()}},
           "forbidden": forbidden,
           "log": str(rd / "access_log.json")}
    (rd / "sandbox_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    if dry_run:
        man.update({"gate_status": "PASS", "exit_status": "DRY_RUN",
                    "note": "Alla obligatoriska komponenter verifierade och gatad vy byggd. "
                            "Skriptet exekverades INTE."})
        (rd / "EXECUTION_MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
        return man
    bs = rd / "bootstrap.py"
    bs.write_text(BOOTSTRAP)
    r = subprocess.run([sys.executable, str(bs), str(rd / "sandbox_config.json")],
                       cwd=str(V2), capture_output=True, text=True, timeout=7200)
    (rd / "stdout.txt").write_text(r.stdout or "")
    (rd / "stderr.txt").write_text(r.stderr or "")
    log = json.loads((rd / "access_log.json").read_text()) if (rd / "access_log.json").exists() else []
    man.update({"exit_status": r.returncode,
                "gate_status": "PASS" if r.returncode == 0 else
                               ("BLOCKED_ACCESS" if r.returncode == 42 else "SCRIPT_ERROR"),
                "access_log_entries": len(log),
                "redirects": sum(1 for x in log if x["kind"] == "REDIRECT"),
                "denials": sum(1 for x in log if x["kind"] == "DENY")})
    (rd / "EXECUTION_MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    return man


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-id", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--price-fields", default="adj")
    ap.add_argument("--test-family", default="UNKNOWN")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-ungated", default="", help="komma-separerad lista")
    ap.add_argument("--adapter", default=None, help="registrerad adapter, t.ex. prima_storbolag")
    a = ap.parse_args()
    m = run(a.test_id, a.script, a.mode, a.price_fields.split(","), a.test_family, a.dry_run,
            [x for x in a.allow_ungated.split(",") if x], a.adapter)
    print(json.dumps({k: v for k, v in m.items() if k != "gated_view"}, ensure_ascii=False, indent=1))
