"""Programsemantisk ekvivalens: wrapper mot originalets forskningsblock.

Ingen forskningskod exekveras. Jamforelsen sker pa AST-niva mellan de satser i
originalets main() som bygger ut["detektion"] och ut["rotation"], och wrapperns
motsvarande satser.
"""
from __future__ import annotations
import ast, json, sys
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
ORIG = V2 / "tools/tidig_detektion_och_utdelning.py"
WRAP = V2 / "tools/revalidation_wrapper_tidig_detektion.py"
RESEARCH_KEYS = ("detektion", "rotation")


def main_body(p: Path) -> list:
    t = ast.parse(p.read_text())
    fn = next(n for n in ast.walk(t) if isinstance(n, ast.FunctionDef) and n.name == "main")
    return fn.body


def research_statements(body: list) -> list:
    """Satser som bidrar till forskningsnyttolasten, normaliserade till AST-dump."""
    ut = []
    for n in body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            continue                                   # importer ar inte nyttolast
        s = ast.dump(n)
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and \
           getattr(n.value.func, "id", "") == "print":
            continue                                   # utskrifter ingar inte i nyttolasten
        if "utdelning" in s or "OUT" in s or "version" in s or "run_utc" in s or \
           "wrapper" in s or "original" in s:
            continue
        ut.append(n)
    return ut


def norm(n) -> str:
    """AST-dump utan attribut, med T.-prefix normaliserat bort."""
    d = ast.dump(n, annotate_fields=True, include_attributes=False)
    return d.replace("Attribute(value=Name(id='T', ctx=Load()), attr=", "Name(id=") \
            .replace("del1_detektion', ctx=Load())", "del1_detektion', ctx=Load())") \
            .replace("Load()), attr='", "Load()), attr='")


o = research_statements(main_body(ORIG))
w = research_statements(main_body(WRAP))
R = []


def chk(namn, ok, d=""):
    R.append((namn, "PASS" if ok else "FAIL", d))


# 1. samma antal forskningssatser
chk("samma antal forskningssatser", len(o) == len(w), f"original {len(o)}, wrapper {len(w)}")
# 2. sats-for-sats-ekvivalens efter T.-normalisering
diff = []
for i, (a, b) in enumerate(zip(o, w)):
    na = norm(a).replace("attr='del1_detektion'", "id='del1_detektion'") \
                .replace("attr='del2_rotera'", "id='del2_rotera'")
    nb = norm(b).replace("attr='del1_detektion'", "id='del1_detektion'") \
                .replace("attr='del2_rotera'", "id='del2_rotera'")
    if na != nb:
        diff.append((i, ast.unparse(a)[:70], ast.unparse(b)[:70]))
chk("varje forskningssats identisk (AST)", not diff, f"{len(diff)} avvikande")
for i, a, b in diff:
    R.append((f"  sats {i}", "INFO", f"orig: {a} | wrap: {b}"))
# 3. inga anrop till del3 i wrappern
wrap_calls = [getattr(c.func, "attr", None) or getattr(c.func, "id", None)
              for c in ast.walk(ast.parse(WRAP.read_text())) if isinstance(c, ast.Call)]
chk("wrappern anropar aldrig del3_utdelning", "del3_utdelning" not in wrap_calls,
    f"{len([x for x in wrap_calls if x])} anrop i wrappern, inget till del3")
# 4. originalet oforandrat
import hashlib
ORIG_SHA = "b7d29fb8afbc36ae10d1cfe0f4c1d0a1"
_h = hashlib.sha256(ORIG.read_bytes()).hexdigest()
chk("originalskriptet oforandrat sedan klassificeringen", _h.startswith("b7d29fb8afbc36ae"), _h[:16])
# 5. samma nycklar i nyttolasten
def keys(body):
    k = set()
    for n in body:
        for s in ast.walk(n):
            if isinstance(s, ast.Subscript) and isinstance(s.value, ast.Name) and s.value.id == "ut":
                if isinstance(s.slice, ast.Constant):
                    k.add(s.slice.value)
    return k
ko, kw = keys(o), keys(w)
chk("identiska nyttolastnycklar", ko == kw, f"original {sorted(ko)}, wrapper {sorted(kw)}")
# 6. samma argument till forskningsfunktionerna
def calls(body):
    c = []
    for n in body:
        for s in ast.walk(n):
            if isinstance(s, ast.Call):
                f = getattr(s.func, "attr", None) or getattr(s.func, "id", None)
                if f in ("del1_detektion", "del2_rotera", "kor", "boot", "stat"):
                    c.append((f, [ast.unparse(a) for a in s.args],
                              sorted(k.arg or "**" for k in s.keywords)))
    return c
co, cw = calls(o), calls(w)
chk("samma funktionsanrop med samma argument", co == cw,
    f"{len(co)} anrop original, {len(cw)} wrapper")
if co != cw:
    for a, b in zip(co, cw):
        if a != b: R.append(("  anropsdiff", "INFO", f"{a} != {b}"))
n = sum(1 for x in R if x[1] == "PASS")
tot = sum(1 for x in R if x[1] in ("PASS", "FAIL"))
print(f"{'kontroll':<52}{'utfall':<8}detalj")
for a, b, d in R:
    print(f"{a[:50]:<52}{b:<8}{d[:60]}")
print(f"\n{n}/{tot} PASS")
(V2 / "research_k/p0_closeout/WRAPPER_EQUIVALENCE.json").write_text(json.dumps(
    {"n_checks": tot, "n_pass": n,
     "results": [{"check": a, "outcome": b, "detail": d} for a, b, d in R],
     "metod": "AST-jamforelse. Ingen forskningskod exekverad."}, ensure_ascii=False, indent=1))
sys.exit(0 if n == tot else 1)
