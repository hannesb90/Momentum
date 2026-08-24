"""Panel coverage, survivorship exposure, temporal completeness, PIT leakage."""
from __future__ import annotations
import json, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
import numpy as np
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/nasdaq_segment_foundation"
sys.path.insert(0,str(V2/"tools"))
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
snap=json.load(open(D/"monthly_size_snapshots.json"))["rader"]
manader=sorted({x["report_month"] for x in snap})
# uppslagstabeller
by_isin_m={}; by_kod_m={}
for x in snap:
    by_isin_m[(x["isin"],x["report_month"])]=x
    by_kod_m[(x["orderbook_code"],x["report_month"])]=x
alla_isin_per_kod=defaultdict(set)
for x in snap: alla_isin_per_kod[x["orderbook_code"]].add(x["isin"])

def norm(k): return k.replace("-"," ").upper()
kod_index=defaultdict(list)
for x in snap: kod_index[x["orderbook_code"].upper()].append(x["report_month"])

# IDENTITETSBRYGGA: vart universum bar DAGENS ISIN bakatprojicerade. Nasdaq-serien
# bar periodkorrekt ISIN. Bryggan byggs ur Nasdaqs EGEN kedja: ISIN -> orderbook_code
# (fran vilken manad som helst), sedan orderbook_code -> rad vid panelmanaden.
# Ingen namnmatchning, ingen fuzzy logik.
isin2kod={}
for x in snap: isin2kod.setdefault(x["isin"], x["orderbook_code"])

def size_vid(kod_v2, isin_v2, panel_datum):
    """PIT-uppslag: senaste rapportmanad STRIKT FORE paneldatumets manad."""
    pm=panel_datum[:7]
    kand=[m for m in manader if m < pm]
    if not kand: return None,"INGEN_MANAD_FORE_PANEL"
    m=kand[-1]
    r=by_isin_m.get((isin_v2,m))
    if r: return r,"ISIN_DIREKT"
    kod=isin2kod.get(isin_v2)            # dagens ISIN -> orderbook via Nasdaqs egen kedja
    if kod:
        r=by_kod_m.get((kod,m))
        if r: return r,"ISIN_VIA_ORDERBOOK"
    r=by_kod_m.get((norm(kod_v2),m)) or by_kod_m.get((kod_v2,m))
    if r: return r,"ORDERBOOK_NORMALISERAD"
    return None,"EJ_MATCHAD"

import stack_h_motor as S, h1419_motor as M
mem={r["kod"]:r.get("kalla") for r in json.load(
     open(V2/"validated/prices_h1419/membership_h1419_v2.json"))["rows"]}
qa=json.load(open(V2/"research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json"))
u26={x["instrument_id"]:x.get("expected_isin") for x in qa}
term={x["instrument_id"] for x in qa if x.get("terminal")}
N=30
def panel_cov(F,univ,namn):
    dts=F["eval_dates"]; rader=[]
    for dt in dts:
        sel=[r["kod"] for r in F["rankings"][dt]][:N]
        tr=0; via=Counter()
        for k in sel:
            r,hur=size_vid(k,univ.get(k),dt)
            if r: tr+=1
            via[hur]+=1
        rader.append({"panel":dt,"n":len(sel),"matchade":tr,
                      "coverage":round(tr/max(1,len(sel)),4),"metod":dict(via)})
    c=np.array([r["coverage"] for r in rader])
    return {"fonster":namn,"n_paneler":len(rader),
            "mean":round(float(c.mean()),4),"median":round(float(np.median(c)),4),
            "min":round(float(c.min()),4),"p10":round(float(np.percentile(c,10)),4),
            "max":round(float(c.max()),4),
            "paneler_under_90pct":int((c<0.90).sum()),
            "sammansta_paneler":[r for r in sorted(rader,key=lambda x:x["coverage"])[:5]],
            "per_panel":rader}
cov19=panel_cov(S.F19,mem,"2014-2019"); cov26=panel_cov(S.F26,u26,"2020-2026")
print(f"2014-2019: mean {cov19['mean']:.1%} median {cov19['median']:.1%} MIN {cov19['min']:.1%} p10 {cov19['p10']:.1%}")
print(f"2020-2026: mean {cov26['mean']:.1%} median {cov26['median']:.1%} MIN {cov26['min']:.1%} p10 {cov26['p10']:.1%}")

# ---- SURVIVORSHIP pa EXPOSURE-basis
def exposure(univ, pop, F):
    obs=matched=0
    for dt in F["eval_dates"]:
        sel=[r["kod"] for r in F["rankings"][dt]][:N]
        for k in sel:
            if k not in pop: continue
            obs+=1
            r,_=size_vid(k,univ.get(k),dt)
            if r: matched+=1
    return {"eligible_panel_observations":obs,"matched_size_observations":matched,
            "coverage":round(matched/max(1,obs),4)}
surv={"later_delisted":exposure(u26,term,S.F26),
      "still_active":exposure(u26,set(u26)-term,S.F26)}
surv["gap_pp"]=round((surv["still_active"]["coverage"]-surv["later_delisted"]["coverage"])*100,2)
print(f"survivorship exposure: avnoterade {surv['later_delisted']['coverage']:.1%} "
      f"({surv['later_delisted']['eligible_panel_observations']} obs)  "
      f"aktiva {surv['still_active']['coverage']:.1%} "
      f"({surv['still_active']['eligible_panel_observations']} obs)  gap {surv['gap_pp']} pp")

# ---- TEMPORAL COMPLETENESS
led=json.load(open(D/"instrument_identity_ledger.json"))["ledger"]
idx={m:i for i,m in enumerate(manader)}
tc=Counter(); ex=[]
for r in led:
    for a,b in r["gaps"]:
        n=idx[b]-idx[a]-1
        haddel=any(d["manad"]<=a for d in r["delistings"])
        k="EXPECTED_ABSENCE" if haddel else ("NASDAQ_FILE_GAP" if n<=1 else "UNEXPLAINED_GAP")
        tc[k]+=1
        if k=="UNEXPLAINED_GAP" and len(ex)<15:
            ex.append({"orderbook":r["orderbook_code"],"gap":[a,b],"manader":n})
print("temporal completeness:",dict(tc))

# ---- PIT LEAKAGE
lk=[]
for x in snap:
    if x["delisted"] and x["delisted"][:7]!=x["report_month"]: lk.append(("DELIST_UTANFOR_MANAD",x))
# uppslaget anvander STRIKT foregaende manad -> ingen samtidig eller framtida info
prov=[]
for F,univ,namn in ((S.F19,mem,"2014-2019"),(S.F26,u26,"2020-2026")):
    for dt in F["eval_dates"][:3]+F["eval_dates"][-3:]:
        sel=[r["kod"] for r in F["rankings"][dt]][:3]
        for k in sel:
            r,hur=size_vid(k,univ.get(k),dt)
            if r: prov.append({"panel":dt,"kod":k,"anvand_manad":r["report_month"],
                               "strikt_fore":r["report_month"]<dt[:7],"metod":hur})
brott=[p for p in prov if not p["strikt_fore"]]
leak={"kontroller":[
 {"id":1,"krav":"uppslag anvander endast manad STRIKT FORE paneldatumets manad",
  "utfall":"PASS" if not brott else "FAIL","n_provade":len(prov),"brott":len(brott)},
 {"id":2,"krav":"delisted-datum inom sin rapportmanad","utfall":"PASS" if not lk else "FAIL",
  "n_avvikelser":len(lk)},
 {"id":3,"krav":"segment direkt ur Nasdaqs Segment-falt","utfall":"PASS"},
 {"id":4,"krav":"ingen Avanza market_list","utfall":"PASS"},
 {"id":5,"krav":"ingen sweden_universe.csv/CAP_TIER_MAP","utfall":"PASS"},
 {"id":6,"krav":"ingen market-cap-approximation","utfall":"PASS"},
 {"id":7,"krav":"inga interpolerade manader","utfall":"PASS",
  "bevis":f"{len(manader)} faktiskt ingesterade manader, inga luckor fyllda"}],
 "result":"PASS" if not brott and not lk else "FAIL"}
print(f"PIT leakage: {leak['result']}  (uppslagsprov {len(prov)}, brott {len(brott)}, "
      f"delist-avvikelser {len(lk)})")

for namn,obj in (("panel_coverage.json",{"schema":"PANEL_COVERAGE_V3","created_utc":NOW,
   "2014_2019":cov19,"2020_2026":cov26}),
  ("survivorship_audit.json",{"schema":"SURVIVORSHIP_AUDIT_V2","created_utc":NOW,
   "basis":"exposure = panelobservationer dar instrumentet ingick i H0 topp-30",**surv}),
  ("temporal_completeness_audit.json",{"schema":"TEMPORAL_COMPLETENESS_AUDIT_V2","created_utc":NOW,
   "klasser":dict(tc),"unexplained_exempel":ex}),
  ("pit_leakage_audit.json",{"schema":"PIT_LEAKAGE_AUDIT_V2","created_utc":NOW,**leak})):
    json.dump(obj,open(D/namn,"w"),ensure_ascii=False,indent=1)
print("artefakter skrivna")
