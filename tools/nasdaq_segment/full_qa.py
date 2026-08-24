"""Full foundation-QA pa hela manadsserien. Ren data-QA, inga tester."""
from __future__ import annotations
import hashlib, json, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, date
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/nasdaq_segment_foundation"
sys.path.insert(0,str(V2/"tools")); sys.path.insert(0,str(V2/"tools/nasdaq_segment"))
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
sha=lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
snap=json.load(open(D/"monthly_size_snapshots.json"))["rader"]
manader=sorted({x["report_month"] for x in snap})
idx={m:i for i,m in enumerate(manader)}
print(f"manader: {len(manader)}  {manader[0]}..{manader[-1]}  rader: {len(snap)}")

# ---------------- 8. IDENTITY LEDGER
led=defaultdict(lambda:{"isin":defaultdict(list),"namn":set(),"cc":set(),
                        "seg":defaultdict(list),"man":[],"del":[]})
for x in snap:
    e=led[x["orderbook_code"]]
    e["isin"][x["isin"]].append(x["report_month"]); e["namn"].add(x["instrument"])
    e["cc"].add(x["company_code"]); e["seg"][x["segment"]].append(x["report_month"])
    e["man"].append(x["report_month"])
    if x["delisted"]: e["del"].append({"manad":x["report_month"],"datum":x["delisted"]})
ledger=[]
for kod,e in sorted(led.items()):
    mm=sorted(set(e["man"]))
    luckor=[(a,b) for a,b in zip(mm,mm[1:]) if idx[b]-idx[a]>1]
    ledger.append({"orderbook_code":kod,"first_seen":mm[0],"last_seen":mm[-1],
      "months_present":len(mm),
      "all_isin":[{"isin":i,"manader":sorted(set(v)),"first":min(v),"last":max(v)}
                  for i,v in e["isin"].items()],
      "n_isin":len(e["isin"]),"names":sorted(e["namn"]),"company_codes":sorted(e["cc"]),
      "segments":[{"segment":s,"manader":sorted(set(v))} for s,v in e["seg"].items()],
      "delistings":e["del"],"gaps":luckor})

# ---------------- 9. CODE REUSE (nu pa riktigt)
reuse=[]
for r in ledger:
    if not r["gaps"]: 
        klass="CONTINUOUS_INSTRUMENT" if r["n_isin"]==1 else "IDENTITY_CHANGE_SAME_INSTRUMENT"
    else:
        stor=[g for g in r["gaps"] if idx[g[1]]-idx[g[0]]>=3]
        namnbyte=len(r["names"])>1; ccbyte=len(r["company_codes"])>1
        haddel=bool(r["delistings"])
        if stor and haddel and (namnbyte or ccbyte or r["n_isin"]>1):
            klass="CONFIRMED_CODE_REUSE"
        elif stor and (namnbyte or ccbyte or r["n_isin"]>1):
            klass="POSSIBLE_CODE_REUSE"
        elif stor:
            klass="UNRESOLVED"
        else:
            klass="CONTINUOUS_INSTRUMENT" if r["n_isin"]==1 else "IDENTITY_CHANGE_SAME_INSTRUMENT"
    r["reuse_class"]=klass
    if klass in ("CONFIRMED_CODE_REUSE","POSSIBLE_CODE_REUSE","UNRESOLVED"):
        reuse.append({"orderbook_code":r["orderbook_code"],"klass":klass,"gaps":r["gaps"],
          "n_isin":r["n_isin"],"names":r["names"],"company_codes":r["company_codes"],
          "delistings":r["delistings"],"first_seen":r["first_seen"],"last_seen":r["last_seen"]})
kl=Counter(r["reuse_class"] for r in ledger)
print("code reuse:",dict(kl))

# ---------------- 10. SHARE CLASSES / ISSUER
per_cc=defaultdict(set)
for x in snap: per_cc[x["company_code"]].add(x["orderbook_code"])
fordel=Counter(len(v) for v in per_cc.values())
segdiff=0
for cc,koder in per_cc.items():
    if len(koder)<2: continue
    per_man=defaultdict(set)
    for x in snap:
        if x["company_code"]==cc: per_man[x["report_month"]].add(x["segment"])
    if any(len(v)>1 for v in per_man.values()): segdiff+=1
print(f"issuers: {len(per_cc)}  1 instr {fordel.get(1,0)}  2 {fordel.get(2,0)}  "
      f"3+ {sum(v for k,v in fordel.items() if k>=3)}  segment skiljer inom issuer: {segdiff}")

# ---------------- 11. DELISTING QA
dl=[x for x in snap if x["delisted"]]
dq={"n_delistings":len(dl),"inom_rapportmanad":sum(1 for x in dl if x["delisted"][:7]==x["report_month"]),
    "utanfor":[{"orderbook":x["orderbook_code"],"datum":x["delisted"],"manad":x["report_month"]}
               for x in dl if x["delisted"][:7]!=x["report_month"]][:20]}
sista={r["orderbook_code"]:r["last_seen"] for r in ledger}
eftr=[]
for x in dl:
    if sista[x["orderbook_code"]]>x["report_month"]:
        eftr.append({"orderbook":x["orderbook_code"],"delisted_manad":x["report_month"],
                     "last_seen":sista[x["orderbook_code"]]})
dq["forekommer_efter_delisting"]=len(eftr); dq["exempel"]=eftr[:10]
print(f"delistings: {dq['n_delistings']}  inom rapportmanad {dq['inom_rapportmanad']}  "
      f"forekommer efter {dq['forekommer_efter_delisting']}")

# ---------------- 12. TRANSITIONS
byM={m:{x["orderbook_code"]:x for x in snap if x["report_month"]==m} for m in manader}
trans=[]
for a,b in zip(manader,manader[1:]):
    for kod in set(byM[a])&set(byM[b]):
        if byM[a][kod]["segment"]!=byM[b][kod]["segment"]:
            trans.append({"orderbook_code":kod,"old_segment":byM[a][kod]["segment"],
              "new_segment":byM[b][kod]["segment"],"last_old_month":a,"first_new_month":b,
              "old_isin":byM[a][kod]["isin"],"new_isin":byM[b][kod]["isin"],
              "identity_status":"SAME_ISIN" if byM[a][kod]["isin"]==byM[b][kod]["isin"] else "ISIN_CHANGED"})
print(f"transitions: {len(trans)}  {dict(Counter(f'{t[chr(111)+chr(108)+chr(100)+chr(95)+chr(115)+chr(101)+chr(103)+chr(109)+chr(101)+chr(110)+chr(116)]}->{t[chr(110)+chr(101)+chr(119)+chr(95)+chr(115)+chr(101)+chr(103)+chr(109)+chr(101)+chr(110)+chr(116)]}' for t in trans))}")

# ---------------- 14. PIT INTERVALS
intervals=[]
for r in ledger:
    kod=r["orderbook_code"]
    obs=sorted([(x["report_month"],x["segment"],x["isin"]) for x in snap
                if x["orderbook_code"]==kod])
    cur=None
    for man,seg,isin in obs:
        if cur and cur["segment"]==seg and idx[man]-idx[cur["_last"]]==1:
            cur["_last"]=man; cur["valid_to"]=None
        else:
            if cur: intervals.append(cur)
            cur={"orderbook_code":kod,"isin_at_interval":isin,"segment":seg,
                 "valid_from":man,"valid_to":None,"_last":man,
                 "precision":"MONTH","source_basis":"NASDAQ_MONTHLY_SNAPSHOT",
                 "provenance_status":"VERIFIED"}
    if cur: intervals.append(cur)
for iv in intervals:
    j=idx[iv["_last"]]
    iv["valid_to"]=manader[j+1] if j+1<len(manader) else None
    iv["n_manader"]=idx[iv["_last"]]-idx[iv["valid_from"]]+1
    del iv["_last"]
print(f"pit intervals: {len(intervals)}")

for namn,obj in (("instrument_identity_ledger.json",{"schema":"INSTRUMENT_IDENTITY_LEDGER_V2",
   "created_utc":NOW,"manader":[manader[0],manader[-1]],"n_instrument":len(ledger),
   "n_med_flera_isin":sum(1 for r in ledger if r["n_isin"]>1),"ledger":ledger}),
  ("code_reuse_audit.json",{"schema":"CODE_REUSE_AUDIT_V2","created_utc":NOW,
   "klasser":dict(kl),"n_flaggade":len(reuse),"flaggade":reuse,
   "regel":"CONFIRMED_CODE_REUSE slas ALDRIG ihop till samma canonical instrument_id"}),
  ("issuer_mapping.json",{"schema":"ISSUER_MAPPING_V2","created_utc":NOW,
   "n_issuers":len(per_cc),"fordelning_instrument_per_issuer":dict(sorted(fordel.items())),
   "issuers_dar_segment_skiljer_mellan_aktieslag":segdiff,
   "princip":"instrumentniva canonical; A/B/C/SDB aldrig hopslagna",
   "mapping":[{"company_code":cc,"orderbooks":sorted(v)} for cc,v in sorted(per_cc.items())]}),
  ("delisting_audit.json",{"schema":"DELISTING_AUDIT_V2","created_utc":NOW,**dq}),
  ("segment_transition_ledger.json",{"schema":"SEGMENT_TRANSITION_LEDGER_V2","created_utc":NOW,
   "n":len(trans),"riktningar":dict(Counter(f"{t['old_segment']} -> {t['new_segment']}" for t in trans)),
   "transitions":trans}),
  ("pit_segment_intervals.json",{"schema":"PIT_SEGMENT_INTERVALS_V1","created_utc":NOW,
   "n":len(intervals),"precision":"MONTH — manadsupplosning; dagprecision kraver review effective_date",
   "intervals":intervals})):
    json.dump(obj,open(D/namn,"w"),ensure_ascii=False,indent=1)
print("QA-artefakter skrivna")
