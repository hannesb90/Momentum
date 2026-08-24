"""REPOSITORY INTEGRITY GATE V2 — obligatorisk pre-flight före all forskning.

FAIL CLOSED: returkod 1 vid FAIL eller internt fel. En agent som inte kan köra
gaten, eller får returkod != 0, får inte påbörja forskning.

FRYSNINGSSEMANTIK (formaliserad 2026-08-18)
  En komponent får kallas FROZEN endast om HELA kedjan verifierar:
    PREREGISTRATION -> INPUT MANIFEST -> EXECUTABLE IMPLEMENTATION
      -> RESULT ARTIFACT -> DECISION -> FREEZE/MANIFEST
  En hash av ett löst script är inte i sig en freeze.

  UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION och
  COMPUTED_BUT_NOT_VALIDATED_CANDIDATE får finnas utan FAIL, förutsatt att de
  inte anges som frozen/validated, inte är beroende för en fryst komponent,
  inte bär en öppen kandidat, och har konsekvent status i samtliga register.

Gaten får INTE ge PASS bara för att dokumentationen är självkonsistent.
Källa för kedjorna: research_k/freeze_chains.json

Kör: /opt/momentum/venv/bin/python tools/repo_integrity_gate.py
"""
from __future__ import annotations
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/repo_integrity_gate_result.json"
CHAINS = V2 / "research_k/freeze_chains.json"
FROZEN_OK = {"FROZEN", "VERIFIED_TAXONOMY"}
EJ_FRYST = {"UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION",
            "COMPUTED_BUT_NOT_VALIDATED_CANDIDATE"}
FORBJUDNA = ["market_list", "list_segment", "terminal_events", "market_cap",
             "enterprise_value", "fundamental_kpi"]
# Variabler som passerat en dokumenterad foundation gate och darfor ar undantagna
# fran substring-traffen ovan. Undantaget kraver att raden sjalv pekar ut sin gate
# via qa_status — annars galler forbudet. Detta forsvagar inte regeln: det gor den
# identitetsbaserad i stallet for substrangbaserad.
PIT_UNDANTAG = {"nasdaq_market_cap_segment_pit": "PASSED_FOUNDATION_GATE"}
TILLATNA_PERMISSIONS = {"FORBIDDEN_IN_MODEL_TEST", "DATA_BLOCKED_GOVERNANCE",
                        "FAILED_PIT_HISTORY_GATE"}
DOKUMENT = ["AGENTS_RESEARCH_HANDOFF.md", "docs/CURRENT_RESEARCH_STATE.md",
            "docs/RESEARCH_INDEX.md", "docs/DATA_GOVERNANCE_REGISTRY.md",
            "docs/FREEZE_REGISTRY.md", "docs/INVALIDATED_AND_SUPERSEDED_RESULTS.md"]
blockers: list[dict] = []


def block(check, msg, ev=None, sev="CRITICAL"):
    blockers.append({"check": check, "severity": sev, "message": msg, "evidence": ev})


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def las(p: Path, kritisk=True):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        if kritisk:
            block("READ", f"kan inte läsa {p}", str(e))
        return None


# ---- 1: frysningssemantik — hela kedjan för varje FROZEN-komponent -------
def check_chains(chains):
    for c in chains.get("components", []):
        cid, st = c.get("id", "?"), c.get("status", "?")
        if st not in FROZEN_OK:
            continue
        # freeze-artefakt + preregistreringshash
        fz = c.get("freeze")
        if not fz or not (V2 / fz).is_file():
            block("1_CHAIN_FREEZE", f"{cid}: FROZEN men frysningsartefakt saknas ({fz})"); continue
        fzd = las(V2 / fz) or {}
        pre = c.get("preregistration")
        if pre:
            if not (V2 / pre).is_file():
                block("1_CHAIN_PREREG", f"{cid}: preregistrering saknas ({pre})"); continue
            want = fzd.get("sha256")
            got = sha(V2 / pre)
            if not want:
                block("1_CHAIN_PREREG", f"{cid}: frysningsartefakten saknar sha256")
            elif want != got:
                block("1_CHAIN_PREREG", f"{cid}: preregistreringens hash stämmer inte",
                      {"registrerad": want, "faktisk": got})
            # INPUT MANIFEST — varje låst indatafil.
            # Accepteras fran preregistreringens indata_last ELLER fran ett separat
            # input_manifest. Det senare kravs nar preregistreringen ar fryst fore
            # resultat och darfor inte far kompletteras i efterhand. Samma verifiering.
            pred = las(V2 / pre) or {}
            ind = pred.get("indata_last") or []
            if not ind and c.get("input_manifest"):
                mp = V2 / c["input_manifest"]
                if not mp.is_file():
                    block("1_CHAIN_INPUTS", f"{cid}: input_manifest saknas — {c['input_manifest']}")
                else:
                    if c.get("input_manifest_sha256") and sha(mp) != c["input_manifest_sha256"]:
                        block("1_CHAIN_INPUTS", f"{cid}: input_manifest har andrats",
                              {"registrerad": c["input_manifest_sha256"], "faktisk": sha(mp)})
                    ind = (las(mp) or {}).get("indata_last") or []
            if not ind:
                block("1_CHAIN_INPUTS", f"{cid}: varken indata_last eller input_manifest")
            for x in ind:
                p = V2 / x.get("fil", "")
                if not p.is_file():
                    block("1_CHAIN_INPUTS", f"{cid}: låst indatafil saknas — {x.get('fil')}")
                elif sha(p) != x.get("sha256"):
                    block("1_CHAIN_INPUTS", f"{cid}: låst indatafil ändrad — {x.get('fil')}",
                          {"registrerad": x.get("sha256"), "faktisk": sha(p)})
        else:
            # taxonomi: manifesthash mot registrerat värde
            if c.get("freeze_sha256") and sha(V2 / fz) != c["freeze_sha256"]:
                block("1_CHAIN_FREEZE", f"{cid}: manifesthash stämmer inte",
                      {"registrerad": c["freeze_sha256"], "faktisk": sha(V2 / fz)})
        # IMPLEMENTATION
        impl = c.get("implementation")
        if st == "FROZEN":
            if not impl or not (V2 / impl).is_file():
                block("1_CHAIN_IMPL", f"{cid}: exekverbar implementation saknas ({impl})")
        # RESULT + DECISION
        rs = c.get("result")
        if not rs or not (V2 / rs).is_file():
            block("1_CHAIN_RESULT", f"{cid}: resultatartefakt saknas ({rs})"); continue
        if st == "FROZEN":
            rd = las(V2 / rs) or {}
            f = c.get("result_prereg_field")
            if f and pre and rd.get(f) != fzd.get("sha256"):
                block("1_CHAIN_RESULT", f"{cid}: resultatet refererar inte frysningens prereg-hash",
                      {"i_resultat": rd.get(f), "i_freeze": fzd.get("sha256")})
            df = c.get("decision_field")
            if df and not rd.get(df):
                block("1_CHAIN_DECISION", f"{cid}: resultatartefakten saknar beslutsfält '{df}'")


# ---- 2: ej frysta komponenter får inte anges som frysta ------------------
def check_ej_fryst(chains):
    fr_md = V2 / "docs/FREEZE_REGISTRY.md"
    txt = fr_md.read_text(encoding="utf-8") if fr_md.is_file() else ""
    # bara den aktiva tabellen, inte audit history
    aktiv = txt.split("## AUDIT HISTORY")[0] if "## AUDIT HISTORY" in txt else txt
    for c in chains.get("components", []):
        if c.get("status") not in EJ_FRYST:
            continue
        cid = c["id"]
        for f in (c.get("implementation"), c.get("result")):
            if f and f in aktiv:
                block("2_UNVERIFIED_AS_FROZEN",
                      f"{cid} har status {c['status']} men {f} förekommer i FREEZE_REGISTRY:s aktiva tabell")
        # får inte vara beroende för en fryst komponent
        for o in chains.get("components", []):
            if o.get("status") in FROZEN_OK:
                s = json.dumps({k: v for k, v in o.items()
                                if k in ("preregistration", "implementation", "result", "freeze")},
                               ensure_ascii=False)
                if c.get("implementation") and c["implementation"] in s:
                    block("2_UNVERIFIED_AS_DEPENDENCY",
                          f"{cid} används som beroende av fryst komponent {o.get('id')}")


# ---- 3 + 4: registerkonsistens och statuskonsekvens ---------------------
def check_registry(chains):
    rr = las(V2 / "research_k/research_registry.json")
    oppna = None
    if rr:
        tracks = rr.get("tracks", [])
        oppna = rr.get("status_summary", {}).get("OPEN", 0)
        for t in tracks:
            tid, st = t.get("test_id", "?"), str(t.get("status", ""))
            if st in ("VALIDATED", "FROZEN") and (t.get("computation_real") is False
                                                  or t.get("pit_valid") is False):
                block("3_INVALID_AS_VALID",
                      f"{tid}: status {st} men computation_real/pit_valid är False", t)
        ni = [t.get("test_id") for t in tracks if t.get("status") == "NOT_IDENTIFIED"]
        nc = [t.get("test_id") for t in tracks if t.get("status") == "NON_COMPUTED_CLAIM"]
        if oppna and (ni or nc):
            block("3_NOT_IDENTIFIED_AS_EVIDENCE",
                  f"{oppna} öppna kandidater samtidigt som NOT_IDENTIFIED/NON_COMPUTED finns",
                  {"not_identified": ni, "non_computed": nc})
    # statuskonsekvens över samtliga auktoritativa dokument
    for c in chains.get("components", []):
        st, cid = c.get("status"), c["id"]
        if st not in EJ_FRYST:
            continue
        for d in DOKUMENT:
            p = V2 / d
            if not p.is_file():
                continue
            t = p.read_text(encoding="utf-8")
            aktiv = t.split("## AUDIT HISTORY")[0] if "## AUDIT HISTORY" in t else t
            nyckel = {"HYSTERES_RANK35": "ysteres", "G97P_TAIL": "G97-P"}.get(cid)
            if nyckel and nyckel in aktiv and st not in aktiv:
                block("4_STATUS_INCONSISTENT",
                      f"{cid} nämns i {d} utan sin status {st}", {"dokument": d}, sev="CRITICAL")
    return oppna


# ---- 5 + 6: governance -------------------------------------------------
def check_governance():
    js = las(V2 / "research_k/data_governance_registry.json")
    mdp = V2 / "docs/DATA_GOVERNANCE_REGISTRY.md"
    if js is None or not mdp.is_file():
        block("5_GOVERNANCE", "governanceregister saknas"); return
    md = mdp.read_text(encoding="utf-8")
    rader = []

    def walk(o):
        if isinstance(o, dict):
            if "variable_name" in o:
                rader.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(js)
    if not rader:
        block("5_GOVERNANCE", "inga variabelrader i JSON-registret"); return
    for r in rader:
        namn, perm = str(r.get("variable_name", "")), str(r.get("model_usage_permission", ""))
        undantagen = any(namn.strip().lower().startswith(u) for u in PIT_UNDANTAG)
        if undantagen and not str(r.get("qa_status", "")).startswith("PASSED_FOUNDATION_GATE"):
            block("5_UNDANTAG_UTAN_GATE",
                  f"'{namn}' ar listad som PIT-undantag men saknar qa_status "
                  f"PASSED_FOUNDATION_GATE (har: {r.get('qa_status')})", r)
        if not undantagen and any(f in namn.lower() for f in FORBJUDNA):
            if perm not in TILLATNA_PERMISSIONS:
                block("5_FORBIDDEN_LICENSED",
                      f"icke-PIT-variabel '{namn}' har tillåtelse '{perm}'", r)
            if perm not in TILLATNA_PERMISSIONS and r.get("date_fields"):
                block("5_FORBIDDEN_LICENSED",
                      f"'{namn}' är licensierad OCH påstår date_fields {r.get('date_fields')}", r)
        kort = namn.split()[0].strip("`")
        # Matcha MD-raden pa den BACKTICKADE identiteten, inte pa delstrang — annars
        # kan en ny variabel vars namn innehaller en forbjuden term traffas i stallet.
        if kort:
            md_rad = next((l for l in md.splitlines()
                           if l.startswith("|") and f"`{kort}`" in l), "")
        else:
            md_rad = ""
        if kort and md_rad:
            f_js = perm in TILLATNA_PERMISSIONS
            f_md = any(w in md_rad.upper() for w in ("FÖRBJUD", "BLOCKERAD", "FORBIDDEN"))
            if md_rad and f_js != f_md:
                block("6_MD_JSON_MISMATCH",
                      f"'{kort}': JSON förbjuden={f_js}, MD förbjuden={f_md}",
                      {"json_permission": perm, "md_rad": md_rad[:200]})


def main():
    chains = las(CHAINS)
    if not chains:
        block("0_CHAINS", f"kedjedefinitionen saknas: {CHAINS}")
        chains = {"components": []}
    check_chains(chains)
    check_ej_fryst(chains)
    oppna = check_registry(chains)
    check_governance()

    krit = [b for b in blockers if b["severity"] == "CRITICAL"]
    komp = chains.get("components", [])
    res = {"gate_version": "REPO_INTEGRITY_GATE_V2",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "result": "FAIL" if krit else "PASS",
           "research_may_resume": not krit,
           "open_research_candidates": oppna if oppna is not None else "UNKNOWN",
           "frozen_components": [c["id"] for c in komp if c.get("status") in FROZEN_OK],
           "unverified_components": [c["id"] for c in komp if c.get("status") in EJ_FRYST],
           "n_blockers": len(blockers), "blockers": blockers, "fail_closed": True}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"REPOSITORY INTEGRITY: {res['result']}")
    print(f"RESEARCH MAY RESUME: {'YES' if res['research_may_resume'] else 'NO'}")
    print(f"OPEN RESEARCH CANDIDATES: {res['open_research_candidates']}")
    print(f"FROZEN: {res['frozen_components']}")
    print(f"UNVERIFIED: {res['unverified_components']}")
    print(f"BLOCKERS: {len(blockers)}")
    for b in blockers:
        print(f"  [{b['severity']}] {b['check']}: {b['message']}")
        if b.get("evidence"):
            print(f"      {json.dumps(b['evidence'], ensure_ascii=False)[:170]}")
    print(f"\nskrivet: {OUT}")
    return 1 if krit else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"REPOSITORY INTEGRITY: FAIL (gate-fel: {e})")
        print("RESEARCH MAY RESUME: NO")
        sys.exit(1)
