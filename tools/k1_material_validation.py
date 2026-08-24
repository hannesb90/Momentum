"""K1 MATERIAL VALIDATION + PIT-SIZE LOOK-AHEAD QUANTIFIERING

Deskriptiv datavalidering. Ingen payoff-analys, ingen avkastning berak nas,
ingen taxonomi andras. K1:s frysta filer lases read-only.

Kor: /opt/momentum/venv/bin/python tools/k1_material_validation.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/k1_material_validation_results.json"
IV = json.loads((V2 / "research_k/sector_classification_v1/validated/"
                 "sector_classification_intervals.json").read_text(encoding="utf-8"))
TERM = json.loads((V2 / "validated/terminal_events.json").read_text(encoding="utf-8"))
MEM = json.loads((V2 / "validated/prices_h1419/membership_h1419_v2.json")
                 .read_text(encoding="utf-8"))["rows"]
BY = {x["instrument_id"]: x for x in IV}
res = {"version": "K1_MATERIAL_VALIDATION_V1",
       "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
       "notering": "Deskriptiv validering. Ingen avkastning berak nad, ingen taxonomi andrad."}


def sektor(kod, dt):
    """Strikt dokumenterad semantik: valid_from <= panel_date < valid_to."""
    r = BY.get(kod)
    if not r:
        return None, "SAKNAS_HELT"
    vf, vt = r.get("valid_from"), r.get("valid_to")
    if vf and dt < vf:
        return None, "PANEL_FORE_VALID_FROM"
    if vt and dt >= vt:
        return None, "PANEL_EFTER_VALID_TO"
    return r.get("canonical_sector"), "OK"


# ---- 1. intervallstruktur
c = Counter(x["instrument_id"] for x in IV)
res["intervallstruktur"] = {
    "poster": len(IV), "unika_instrument": len(c),
    "instrument_med_fler_an_ett_intervall": sum(1 for v in c.values() if v > 1),
    "valid_from_topp": Counter(x.get("valid_from") for x in IV).most_common(4),
    "andel_valid_from_2020_01_02": round(
        sum(1 for x in IV if x.get("valid_from") == "2020-01-02") / len(IV), 4),
    "min_valid_from": min(x["valid_from"] for x in IV if x.get("valid_from")),
    "identity_status": dict(Counter(x.get("identity_status") for x in IV)),
    "qa_status": dict(Counter(x.get("qa_status") for x in IV))}

# ---- 2. coverage per fonster under STRIKT semantik
paneler = {"2014_2019": ["2014-01-01", "2015-06-01", "2016-01-01", "2017-06-01",
                         "2018-01-01", "2019-12-25"],
           "2020_2026": ["2021-07-16", "2022-09-09", "2023-12-01", "2025-02-21", "2026-07-10"]}
univ = {"2014_2019": sorted({r["kod"] for r in MEM}),
        "2020_2026": sorted(BY)}
res["coverage_strikt"] = {}
for f, dts in paneler.items():
    u = univ[f]; rader = []
    for dt in dts:
        st = Counter(sektor(k, dt)[1] for k in u)
        rader.append({"panel": dt, "n_universum": len(u),
                      "med_sektor": st["OK"],
                      "andel": round(st["OK"] / max(1, len(u)), 4),
                      "orsaker": dict(st)})
    res["coverage_strikt"][f] = rader

# ---- 3. terminalhantering: lacker framtida terminalstatus bakat?
tset = set(TERM) if isinstance(TERM, list) else set(TERM.keys())
tposter = [x for x in IV if x.get("terminal")]
har_vt = sum(1 for x in tposter if x.get("valid_to"))
res["terminalhantering"] = {
    "terminala_poster": len(tposter),
    "med_valid_to_satt": har_vt,
    "andel_med_valid_to": round(har_vt / max(1, len(tposter)), 4),
    "semantik": "valid_to = avnoteringsdatum; strikt uppslag ger dt >= valid_to -> ingen sektor. "
                "Terminalstatus lacker darfor INTE bakat via sektoruppslaget.",
    "MEN": "faltet 'terminal' i intervallfilen ar en EX POST-flagga utan datum och far inte "
           "lasas som feature vid beslutstidpunkt."}

# ---- 4. stratifierat stickprov
def prov(namn, koder, dt):
    ut = []
    for k in koder[:6]:
        r = BY.get(k, {})
        s, orsak = sektor(k, dt)
        ut.append({"kod": k, "panel": dt, "sektor": s, "orsak": orsak,
                   "valid_from": r.get("valid_from"), "valid_to": r.get("valid_to"),
                   "identity_status": r.get("identity_status"),
                   "qa_status": r.get("qa_status"), "terminal": r.get("terminal")})
    return {namn: ut}


sektorer = defaultdict(list)
for x in IV:
    sektorer[x.get("canonical_sector")].append(x["instrument_id"])
res["stickprov"] = {}
res["stickprov"].update(prov("terminala_i_sen_panel",
                             [x["instrument_id"] for x in tposter], "2023-12-01"))
res["stickprov"].update(prov("olost_identitet",
                             [x["instrument_id"] for x in IV
                              if x.get("identity_status") == "UNRESOLVED"], "2023-12-01"))
res["stickprov"].update(prov("manuell_klassificering",
                             [x["instrument_id"] for x in IV
                              if x.get("qa_status") == "MANUAL_EXPERT_CLASSIFICATION"], "2023-12-01"))
res["stickprov"].update(prov("tidig_panel_2016",
                             sorted({r["kod"] for r in MEM})[:6], "2016-01-01"))
for s in list(sektorer)[:3]:
    res["stickprov"].update(prov(f"sektor_{s}", sorted(sektorer[s]), "2023-12-01"))

# ---- 5. LOOK-AHEAD fran den gamla 2026-metoden: terminaletiketten
#      Gamla metoden satte Terminal/Avnoterad i SAMTLIGA paneler. Har raknas
#      exakt hur manga panelrader som darmed etiketterades fore handelsen.
tev = TERM if isinstance(TERM, dict) else {}
pan = [f"20{y:02d}-{m:02d}-01" for y in range(21, 27) for m in (1, 3, 5, 7, 9, 11)]
fore = efter = utan_datum = 0
for x in tposter:
    k = x["instrument_id"]
    ev = (tev.get(k) or {}).get("event_date") if isinstance(tev.get(k), dict) else None
    if not ev:
        utan_datum += 1; continue
    for dt in pan:
        if dt < ev:
            fore += 1
        else:
            efter += 1
res["lookahead_terminaletikett"] = {
    "terminala_instrument": len(tposter),
    "utan_kant_eventdatum": utan_datum,
    "panelrader_etiketterade_FORE_handelsen": fore,
    "panelrader_etiketterade_efter_handelsen": efter,
    "andel_felaktiga": round(fore / max(1, fore + efter), 4),
    "tolkning": "Varje rad i 'FORE' ar en panel dar den gamla metoden visste att bolaget skulle "
                "avnoteras. Detta ar en EXAKT matning av EN komponent av look-aheaden. "
                "Segmentkomponenten (Large/Mid/Small bakatprojicerad) kan INTE kvantifieras "
                "eftersom ingen PIT-segmenthistorik existerar att jamfora mot."}

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
i = res["intervallstruktur"]
print("=== 1. INTERVALLSTRUKTUR ===")
print(f"  {i['poster']} poster / {i['unika_instrument']} unika instrument")
print(f"  instrument med FLER AN ETT intervall: {i['instrument_med_fler_an_ett_intervall']}")
print(f"  andel valid_from = 2020-01-02: {i['andel_valid_from_2020_01_02']:.1%}   "
      f"min valid_from: {i['min_valid_from']}")
print(f"  identity_status: {i['identity_status']}")
print("\n=== 2. COVERAGE UNDER STRIKT SEMANTIK ===")
for f, rader in res["coverage_strikt"].items():
    print(f"  {f}:")
    for r in rader:
        print(f"    {r['panel']}  {r['med_sektor']:>3}/{r['n_universum']:<3} = {r['andel']:6.1%}  {r['orsaker']}")
t = res["terminalhantering"]
print(f"\n=== 3. TERMINALHANTERING ===\n  {t['terminala_poster']} terminala, "
      f"{t['med_valid_to_satt']} med valid_to ({t['andel_med_valid_to']:.1%})")
l = res["lookahead_terminaletikett"]
print(f"\n=== 5. LOOK-AHEAD, TERMINALETIKETT ===")
print(f"  panelrader etiketterade FORE handelsen: {l['panelrader_etiketterade_FORE_handelsen']}")
print(f"  efter handelsen: {l['panelrader_etiketterade_efter_handelsen']}  "
      f"andel felaktiga: {l['andel_felaktiga']:.1%}")
print(f"  utan kant eventdatum: {l['utan_kant_eventdatum']}")
print(f"\nskrivet: {OUT}")
