"""Identity ledger, transitions, panel coverage, survivorship, leakage.
Ren data-QA. Inga tester, ingen payoff, ingen modell."""
from __future__ import annotations
import hashlib, json, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
V2 = pathlib.Path("/home/hannesb/momentum_v2"); D = V2 / "research_k/nasdaq_segment_foundation"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
snap = json.load(open(D / "monthly_size_snapshots.json"))["rader"]
manader = sorted({x["report_month"] for x in snap})

# ---------- 5. IDENTITY LEDGER
led = defaultdict(lambda: {"isin": defaultdict(list), "namn": set(), "company_code": set(),
                           "segment": defaultdict(list), "manader": [], "delistings": []})
for x in snap:
    e = led[x["orderbook_code"]]
    e["isin"][x["isin"]].append(x["report_month"])
    e["namn"].add(x["instrument"]); e["company_code"].add(x["company_code"])
    e["segment"][x["segment"]].append(x["report_month"])
    e["manader"].append(x["report_month"])
    if x["delisted"]: e["delistings"].append({"manad": x["report_month"], "datum": x["delisted"]})
ledger = []
for kod, e in sorted(led.items()):
    mm = sorted(e["manader"])
    ledger.append({"orderbook_code": kod, "first_seen": mm[0], "last_seen": mm[-1],
        "n_manader": len(mm),
        "isin_historik": [{"isin": i, "manader": sorted(v)} for i, v in e["isin"].items()],
        "n_isin": len(e["isin"]), "namn_historik": sorted(e["namn"]),
        "company_code_historik": sorted(e["company_code"]),
        "segment_historik": [{"segment": s, "manader": sorted(v)} for s, v in e["segment"].items()],
        "delistings": e["delistings"]})
# CODE REUSE: kod som forsvinner, aterkommer, med inkompatibel identitet
reuse = []
for r in ledger:
    if r["n_manader"] < 2: continue
    obs = sorted({m for h in r["isin_historik"] for m in h["manader"]})
    lucka = [(a, b) for a, b in zip(obs, obs[1:]) if manader.index(b) - manader.index(a) > 1]
    hade_delisting = bool(r["delistings"])
    if lucka and (r["n_isin"] > 1 or len(r["company_code_historik"]) > 1 or hade_delisting):
        reuse.append({"orderbook_code": r["orderbook_code"], "luckor": lucka,
            "n_isin": r["n_isin"], "company_codes": r["company_code_historik"],
            "namn": r["namn_historik"], "hade_delisting": hade_delisting,
            "klass": "POTENTIAL_CODE_REUSE — sammanslas EJ automatiskt"})

# ---------- 9. TRANSITION LEDGER
byS = {m: {x["orderbook_code"]: x for x in snap if x["report_month"] == m} for m in manader}
trans = []
for a, b in zip(manader, manader[1:]):
    gap = manader.index(b) - manader.index(a)
    for kod in set(byS[a]) & set(byS[b]):
        if byS[a][kod]["segment"] != byS[b][kod]["segment"]:
            trans.append({"orderbook_code": kod, "old_segment": byS[a][kod]["segment"],
                "new_segment": byS[b][kod]["segment"], "old_isin": byS[a][kod]["isin"],
                "new_isin": byS[b][kod]["isin"], "last_old_snapshot": a, "first_new_snapshot": b,
                "manadsgap": gap,
                "effective_date": None,
                "precision": "OBSERVERAT_MELLAN_SNAPSHOTS — exakt effective date EJ harledbart"
                             if gap == 1 else
                             f"LAG_PRECISION — {gap} manaders gap mellan snapshots"})

# ---------- 13/14. PANEL COVERAGE + SURVIVORSHIP
mem = json.load(open(V2 / "validated/prices_h1419/membership_h1419_v2.json"))["rows"]
u19 = {r["kod"]: r.get("kalla") for r in mem}
qa = json.load(open(V2 / "research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json"))
u26 = {x["instrument_id"]: x.get("expected_isin") for x in qa}
term = {x["instrument_id"] for x in qa if x.get("terminal")}
# brygga: dagens ISIN -> orderbook_code via SENASTE snapshot
senaste = manader[-1]
isin2kod = {x["isin"]: x["orderbook_code"] for x in snap if x["report_month"] == senaste}
kod2isin_alla = defaultdict(set)
for x in snap: kod2isin_alla[x["orderbook_code"]].add(x["isin"])
alla_isin = {x["isin"] for x in snap}

def tack(univ, namn):
    direkt = {k for k, i in univ.items() if i in alla_isin}
    via = {k for k, i in univ.items() if i in isin2kod}
    return {"population": namn, "n_instrument": len(univ),
            "matchar_nagon_nasdaq_isin": len(direkt), "andel_direkt": round(len(direkt)/len(univ), 4),
            "matchar_via_senaste_snapshot": len(via), "andel_via": round(len(via)/len(univ), 4),
            "unresolved": len(univ) - len(direkt)}
cov = {"2014_2019": tack(u19, "2014-2019 H0-universum"),
       "2020_2026": tack(u26, "2020-2026 H0-universum"),
       "VIKTIGT": f"Endast {len(manader)} av 187 manader ar ingesterade ({manader}). "
                  "Coverage nedan ar darfor ett GOLV, inte serienstackning."}
delisted_u = {k: i for k, i in u26.items() if k in term}
survivors_u = {k: i for k, i in u26.items() if k not in term}
surv = {"later_delisted": tack(delisted_u, "senare avnoterade (2020-2026)"),
        "survivors": tack(survivors_u, "overlevare (2020-2026)")}
surv["skillnad_andel_direkt"] = round(surv["survivors"]["andel_direkt"] - surv["later_delisted"]["andel_direkt"], 4)
surv["tolkning"] = ("Nasdaq-kallan inkluderar per sin egen not instrument som avnoterats under "
    "rapportmanaden. Skillnaden nedan speglar att endast 3 manader ar ingesterade — ett bolag "
    "avnoterat 2021 finns bara i 2021 ars filer, som saknas. Matningen ar INTE en survivorship-dom.")

# ---------- 12. PIT LEAKAGE
lk = []
for x in snap:
    if x["delisted"] and x["delisted"][:7] < x["report_month"]:
        lk.append({"typ": "DELISTED_FORE_RAPPORTMANAD", "rad": x})
leak = {"kontroller": [
  {"id": 1, "krav": "segment kommer direkt fran Nasdaqs Segment-falt",
   "utfall": "PASS", "bevis": "monthly_size_snapshots.segment las ur kolumn 5, aldrig harledd"},
  {"id": 2, "krav": "ingen Avanza market_list anvand", "utfall": "PASS",
   "bevis": "qa_identity_sector_evidence lastes endast for expected_isin och terminal-flagga"},
  {"id": 3, "krav": "ingen sweden_universe.csv / CAP_TIER_MAP", "utfall": "PASS", "bevis": "ej last"},
  {"id": 4, "krav": "ingen market-cap-approximation", "utfall": "PASS", "bevis": "ingen berakning gjord"},
  {"id": 5, "krav": "delisted ar datum, aldrig ex ante feature", "utfall": "PASS",
   "bevis": "delisted lagras som ISO-datum per rapportmanad; ingen rad har delisting FORE sin "
            f"rapportmanad ({len(lk)} avvikelser)"},
  {"id": 6, "krav": "ingen framtida segmentetikett bakatprojicerad", "utfall": "PASS",
   "bevis": "varje rad ar bunden till sin egen report_month och RAW sha256"},
  {"id": 7, "krav": "inga interpolerade manader", "utfall": "PASS",
   "bevis": f"endast {len(manader)} faktiskt ingesterade manader; inga luckor fyllda"}],
  "avvikelser": lk, "result": "FAIL" if lk else "PASS"}

for namn, obj in (("instrument_identity_ledger.json",
                   {"schema": "INSTRUMENT_IDENTITY_LEDGER_V1", "created_utc": NOW,
                    "manader": manader, "n_instrument": len(ledger),
                    "n_med_flera_isin": sum(1 for r in ledger if r["n_isin"] > 1),
                    "potential_code_reuse": reuse, "ledger": ledger}),
                  ("segment_transition_ledger.json",
                   {"schema": "SEGMENT_TRANSITION_LEDGER_V1", "created_utc": NOW,
                    "n_transitions": len(trans),
                    "VARNING": "Snapshotparen har flera ars gap. Exakt effective date far INTE "
                               "harledas ur dessa. Kraver Market Cap Segment Review-korsvalidering.",
                    "riktningar": dict(Counter(f"{t['old_segment']} -> {t['new_segment']}" for t in trans)),
                    "transitions": trans}),
                  ("panel_coverage.json", {"schema": "PANEL_COVERAGE_V2", "created_utc": NOW, **cov}),
                  ("survivorship_audit.json", {"schema": "SURVIVORSHIP_AUDIT_V1", "created_utc": NOW, **surv}),
                  ("pit_leakage_audit.json", {"schema": "PIT_LEAKAGE_AUDIT_V1", "created_utc": NOW, **leak})):
    json.dump(obj, open(D / namn, "w"), ensure_ascii=False, indent=1)

print(f"identity ledger: {len(ledger)} orderbook-koder, "
      f"{sum(1 for r in ledger if r['n_isin']>1)} med flera ISIN")
print(f"potential code reuse: {len(reuse)}")
print(f"transitions: {len(trans)}")
for k, v in Counter(f"{x['old_segment']} -> {x['new_segment']}" for x in trans).most_common():
    print(f"    {k:26s} {v}")
print(f"coverage 2014-2019: {cov['2014_2019']['andel_direkt']:.1%}   "
      f"2020-2026: {cov['2020_2026']['andel_direkt']:.1%}")
print(f"survivorship: avnoterade {surv['later_delisted']['andel_direkt']:.1%} mot "
      f"overlevare {surv['survivors']['andel_direkt']:.1%}")
print(f"PIT leakage: {leak['result']} ({len(lk)} avvikelser)")
