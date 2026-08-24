"""BYPASS-TESTER: kan en framtida revalidation kringga PriceGate?

Varje negativt test skriver ett litet syntetiskt skript som forsoker na forbjuden
data, kor det genom runnern i REVALIDATION-mode och kraver HARD FAIL.
Legacy-skript ror vi aldrig.
"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
import revalidation_runner as RR
from validate_revalidation_run import validate_revalidation_run

def _fail(fn):
    try:
        fn()
    except Exception:
        return True
    return False


R = []
TMP = Path(tempfile.mkdtemp(prefix="bypass_"))


def mk(namn, kod):
    p = TMP / f"{namn}.py"; p.write_text(kod); return p


def neg(namn, kod, fields="adj"):
    m = RR.run(f"BYPASS-{namn}", str(mk(namn, kod)), "REVALIDATION", fields.split(","))
    ok = m["exit_status"] != 0
    R.append((namn, "PASS" if ok else "FAIL",
              f"exit={m['exit_status']} gate={m['gate_status']} denials={m.get('denials',0)}"))


def pos(namn, kod, fields="adj"):
    m = RR.run(f"OK-{namn}", str(mk(namn, kod)), "REVALIDATION", fields.split(","))
    ok = m["exit_status"] == 0
    R.append((namn, "PASS" if ok else "FAIL",
              f"exit={m['exit_status']} redirects={m.get('redirects',0)}"))


V = '/home/hannesb/momentum_v2'
neg("absolut_legacy_path", f"import json;json.loads(open('{V}/validated/prices/prices_validated_v1_1.json').read())")
neg("relativ_path", "import json,os;os.chdir('/home/hannesb/momentum_v2');json.loads(open('validated/prices_v2_0/prices_validated.json').read())")
neg("pathlib_read_text", f"import pathlib;pathlib.Path('{V}/validated/prices_adjustment_repair_v2/prices_validated_adjustment_repair_v2.json').read_text()")
neg("pathlib_read_bytes", f"import pathlib;pathlib.Path('{V}/validated/prices_adjustment_repair_v3/prices_validated_adjustment_repair_v3.json').read_bytes()")
neg("gzip_ra_arkiv", "import gzip;gzip.open('/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST/active/eod/AAK.json.gz','rt').read()")
neg("legacy_cache", "import json;json.loads(open('/home/hannesb/momentum_prod_work/cache/borsdata/instruments_all.json').read())")
neg("os_open", f"import os;os.open('{V}/validated/prices/prices_validated_v1_1.json', os.O_RDONLY)")
neg("pandas_read_json", f"import pandas as pd;pd.read_json('{V}/validated/prices_v2_0/prices_validated.json')")
neg("glob_sedan_open", f"import glob,json;p=glob.glob('{V}/validated/prices_v2_0/*.json')[0];json.loads(open(p).read())")
neg("superseded_fundamenta", f"import json;json.loads(open('{V}/validated/_SUPERSEDED_2026-08-08_valutabugg/fundamentals_year_validated.json').read())")
neg("skript_som_kraschar", "raise RuntimeError('test')")
neg("h1419 mellansteg preliminar", f"import json;json.loads(open('{V}/validated/prices_h1419/prices_h1419_preliminar.json').read())")
neg("h1419 mellansteg klassificerad", f"import json;json.loads(open('{V}/validated/prices_h1419/prices_h1419_klassificerad.json').read())")
neg("h1419 via pathlib", f"import pathlib;pathlib.Path('{V}/validated/prices_h1419/prices_h1419_klassificerad.json').read_text()")
neg("h1419 via pandas", f"import pandas as pd;pd.read_json('{V}/validated/prices_h1419/prices_h1419_preliminar.json')")

# gatad vy: legacy-vagen ska ge MASKAD data, inte originalet
pos("legacy_path_omdirigeras",
    f"""import json
d=json.loads(open('{V}/validated/prices/prices_validated.json').read())
n=sum(len(v) for v in d.values())
assert n < 579458, f'fick omaskad data: {{n}}'
assert 'FLERIE' in d, 'adj-only-test ska behalla FLERIE'
print('gatad vy:', len(d), 'instrument', n, 'rader')""")
pos("raw_close_test_utesluter_FLERIE",
    f"""import json
d=json.loads(open('{V}/validated/prices/prices_validated.json').read())
assert 'FLERIE' not in d, 'FLERIE skulle ha uteslutits'
assert 'IMMNOV' not in d and 'SAS' not in d
print('raw-close-vy:', len(d), 'instrument')""", fields="adj,close")
pos("boundary_kan_inte_korsas",
    f"""import json
d=json.loads(open('{V}/validated/prices/prices_validated.json').read())
r=d.get('NEWA-B',[])
assert r, 'NEWA-B saknas'
ds=[x['d'] for x in r]
assert not (min(ds) < '2020-05-14' <= max(ds)), f'boundary korsades: {{min(ds)}}..{{max(ds)}}'
print('NEWA-B segment:', min(ds), max(ds))""")

pos("h1419 universum_v2 omdirigeras till gatad vy",
    f"""import json
d=json.loads(open('{V}/validated/prices_h1419/prices_h1419_universum_v2.json').read())
n=sum(len(v) for v in d.values())
assert n==501502, f'fick {{n}}, forvantade 501502'
print('h1419 gatad:', len(d), 'instrument', n, 'rader')""")
pos("h1419 boundary kan inte korsas (NET-B 2016-05-04)",
    f"""import json
d=json.loads(open('{V}/validated/prices_h1419/prices_h1419_universum.json').read())
r=d.get('NET-B',[])
ds=[x['d'] for x in r]
assert r and not (min(ds) < '2016-05-04' <= max(ds)), f'boundary korsades: {{min(ds)}}..{{max(ds)}}'
print('NET-B segment:', min(ds), max(ds))""")
pos("h1419 relativ path omdirigeras ocksa",
    """import json,os
os.chdir('/home/hannesb/momentum_v2')
d=json.loads(open('validated/prices_h1419/prices_h1419_universum_v2.json').read())
assert sum(len(v) for v in d.values())==501502
print('relativ path gatad ok')""")
R.append(("inga ogatade lager kvar (UNGATED tomt)",
          "PASS" if not RR.UNGATED else "FAIL", str(list(RR.UNGATED))))
R.append(("okant ogatat lager avvisas",
          "PASS" if _fail(lambda: RR.run("U2", str(mk("u2", "pass")), "REVALIDATION", ["adj"],
                                         allow_ungated=["hittepa"])) else "FAIL", ""))

# --- historisk reproduktion med OFORANDRAT legacy-skript
m_hr = RR.run("HIST-LEGACY", "tools/h0_v3_eligibility.py", "HISTORICAL_REPRODUCTION", ["adj"])
R.append(("HISTORICAL_REPRODUCTION accepterar legacy-skript oforandrat",
          "PASS" if m_hr["execution_mode"] == "HISTORICAL_REPRODUCTION"
          and m_hr["result_class"] == "HISTORICAL_REPRODUCTION_ONLY" else "FAIL",
          m_hr.get("result_class", "")))

# --- manifest/acceptans
m_ok = RR.run("ACCEPT-OK", str(mk("accept_ok", "print('ok')")), "REVALIDATION", ["adj"])
v = validate_revalidation_run(RR.RUNS / m_ok["run_id"])
R.append(("acceptansgrind pa giltig korning", "PASS" if v["status"] == "VALID" else "FAIL", str(v["fel"])[:60]))
m_h = RR.run("HIST", str(mk("hist", "print('legacy')")), "HISTORICAL_REPRODUCTION", ["adj"])
v2_ = validate_revalidation_run(RR.RUNS / m_h["run_id"])
R.append(("HISTORICAL_REPRODUCTION avvisas som revalidation",
          "PASS" if v2_["status"] == "REVALIDATION_RESULT_INVALID" else "FAIL", str(v2_["fel"])[:60]))
rd = RR.RUNS / m_ok["run_id"]
mm = json.loads((rd / "EXECUTION_MANIFEST.json").read_text()); mm["price_sha256"] = "0" * 64
(rd / "EXECUTION_MANIFEST.json").write_text(json.dumps(mm))
v3 = validate_revalidation_run(rd)
R.append(("manipulerad price-SHA i manifestet avvisas",
          "PASS" if v3["status"] == "REVALIDATION_RESULT_INVALID" else "FAIL", str(v3["fel"])[:60]))
d2 = RR.RUNS / (m_ok["run_id"] + "-nomanifest"); d2.mkdir(exist_ok=True)
v4 = validate_revalidation_run(d2)
R.append(("korning utan exekveringsmanifest avvisas",
          "PASS" if v4["status"] == "REVALIDATION_RESULT_INVALID" else "FAIL", str(v4["fel"])[:60]))
R.append(("okant exekveringslage avvisas",
          "PASS" if _fail(lambda: RR.run("X", str(mk("x", "pass")), "FUSK", ["adj"])) else "FAIL", ""))

n = sum(1 for x in R if x[1] == "PASS")
print(f"{'test':<48}{'utfall':<8}detalj")
for a, b, c in R: print(f"{a[:46]:<48}{b:<8}{c}")
print(f"\n{n}/{len(R)} PASS")
(V2 / "research_k/revalidation_runs/BYPASS_TEST_RESULTS.json").write_text(
    json.dumps({"n": len(R), "pass": n,
                "results": [{"test": a, "outcome": b, "detail": c} for a, b, c in R]},
               ensure_ascii=False, indent=1))
sys.exit(0 if n == len(R) else 1)
