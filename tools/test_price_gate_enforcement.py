"""ENFORCEMENT-TESTER for REVALIDATION_PRICE_GATE.

Negativa test forsoker komma at blockerad data och MASTE ge hart fel.
Positiva test verifierar att giltig data inte sparras av misstag.

Kor: /opt/momentum/venv/bin/python tools/test_price_gate_enforcement.py
"""
from __future__ import annotations
import hashlib, json, shutil, sys, tempfile
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
from revalidation_price_gate import (PriceGate, PriceRestrictionError,
                                     PriceGateIntegrityError, BASE)

R = []


def neg(namn, fn, vantat=PriceRestrictionError):
    try:
        fn()
    except vantat as e:
        R.append((namn, "PASS", str(e).splitlines()[0][:78])); return
    except Exception as e:
        R.append((namn, "FAIL", f"fel undantagstyp: {type(e).__name__}")); return
    R.append((namn, "FAIL", "inget fel kastades — data lamnades ut"))


def pos(namn, fn):
    try:
        v = fn()
        R.append((namn, "PASS", f"utlamnat: {len(v) if hasattr(v,'__len__') else v}"))
    except Exception as e:
        R.append((namn, "FAIL", f"{type(e).__name__}: {str(e).splitlines()[0][:60]}"))


g = PriceGate()

# ---------- NEGATIVA ----------
neg("las blockerat adjusted segment (NEWA-B over 2020-05-14)",
    lambda: g.window("NEWA-B", "2020-01-02", "2020-12-30", "adj"))
neg("las FLERIE raw close",
    lambda: g.series("FLERIE", "close"))
neg("las IMMNOV raw close",
    lambda: g.series("IMMNOV", "close"))
neg("las SAS raw close",
    lambda: g.series("SAS", "close"))
neg("korsa SERIES_SPLIT (ATORX over 2025-01-24)",
    lambda: g.window("ATORX", "2024-06-01", "2025-06-01", "adj"))
neg("korsa SERIES_SPLIT (BETS-B over 2022-05-13)",
    lambda: g.window("BETS-B", "2022-01-01", "2022-12-31", "adj"))
neg("rullande momentum over blockerad boundary (SWED-A)",
    lambda: g.window("SWED-A", "2020-01-02", "2020-12-30", "adj"))
neg("hela serien for instrument med boundary (NEWA-B)",
    lambda: g.series("NEWA-B", "adj"))


def fel_sha():
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(BASE / "REVALIDATION_PRICE_GATE_MANIFEST.json", tmp / "m.json")
    m = json.loads((tmp / "m.json").read_text()); m["price_sha256"] = "0" * 64
    (tmp / "m.json").write_text(json.dumps(m))
    PriceGate(manifest=tmp / "m.json")


def gammalt_register():
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(BASE / "PRICE_RESTRICTION_REGISTRY.json", tmp / "r.json")
    r = json.loads((tmp / "r.json").read_text()); r["registry_version"] = "V0"
    (tmp / "r.json").write_text(json.dumps(r, ensure_ascii=False))
    shutil.copy(BASE / "REVALIDATION_PRICE_GATE_MANIFEST.json", tmp / "m.json")
    m = json.loads((tmp / "m.json").read_text())
    m["registry_sha256"] = hashlib.sha256((tmp / "r.json").read_bytes()).hexdigest()
    (tmp / "m.json").write_text(json.dumps(m))
    PriceGate(registry=tmp / "r.json", manifest=tmp / "m.json")


neg("fel price SHA i manifestet", fel_sha, PriceGateIntegrityError)
neg("gammalt restriktionsregister (version V0)", gammalt_register, PriceGateIntegrityError)
neg("kor utan register", lambda: PriceGate(registry=Path("/nonexistent.json")),
    PriceGateIntegrityError)
neg("kor utan manifest", lambda: PriceGate(manifest=Path("/nonexistent.json")),
    PriceGateIntegrityError)
neg("okant instrument", lambda: g.series("INTE-ETT-INSTRUMENT", "adj"))

# ---------- POSITIVA ----------
pos("SAS giltiga corporate action 2020-09-29 far anvandas (adj)",
    lambda: g.window("SAS", "2020-06-01", "2020-12-31", "adj"))
pos("BEIJ-B efter reparerad period",
    lambda: g.window("BEIJ-B", "2021-01-04", "2022-12-30", "adj"))
pos("instrument utan restriktion (VOLV-B) — hela serien",
    lambda: g.series("VOLV-B", "adj"))
pos("NEWA-B segment HELT efter boundary",
    lambda: g.window("NEWA-B", "2021-01-04", "2021-12-30", "adj"))
pos("NEWA-B segment HELT fore boundary",
    lambda: g.window("NEWA-B", "2020-01-02", "2020-04-30", "adj"))
pos("SSAB-A ar REPARERAD — hela serien far lasas",
    lambda: g.series("SSAB-A", "adj"))
pos("FLERIE adjusted close ar tillaten",
    lambda: g.window("FLERIE", "2021-01-04", "2021-12-30", "adj"))
pos("ATORX behallet segment (fore boundary) far anvandas",
    lambda: g.window("ATORX", "2023-01-02", "2024-12-30", "adj"))

# eligibility-logiken
def elig(kod, asof, lb, vantat):
    got = g.eligible(kod, asof, lb)
    R.append((f"eligible({kod}, {asof}, {lb}d) == {vantat}",
              "PASS" if got == vantat else "FAIL", f"fick {got}"))


elig("NEWA-B", "2020-09-01", 365, False)   # lookback korsar 2020-05-14
elig("NEWA-B", "2021-09-01", 365, True)    # helt efter
elig("ATORX", "2025-06-01", 365, False)    # korsar 2025-01-24
elig("ATORX", "2026-06-01", 365, False)    # inget data efter boundary (segmentet borttaget)
elig("ATORX", "2024-06-01", 365, True)     # helt inom behallet segment
elig("SSAB-A", "2020-06-01", 365, True)    # REPARERAD, ingen boundary
elig("VOLV-B", "2023-06-01", 365, True)    # orestricerat
elig("FLERIE", "2023-06-01", 365, True)    # adj ar tillaten

n_pass = sum(1 for x in R if x[1] == "PASS")
print(f"{'test':<62}{'utfall':<8}detalj")
for namn, ut, d in R:
    print(f"{namn[:60]:<62}{ut:<8}{d}")
print(f"\n{n_pass}/{len(R)} PASS   avvisningar loggade: {len(g.log)}")
out = V2 / "validated/prices_adjustment_repair_v4/enforcement_test_results.json"
out.write_text(json.dumps({"n_tests": len(R), "n_pass": n_pass,
                           "results": [{"test": a, "outcome": b, "detail": c} for a, b, c in R],
                           "denial_log": g.log}, ensure_ascii=False, indent=1))
sys.exit(0 if n_pass == len(R) else 1)
