"""H0 V2 HISTORICAL MEMBERSHIP INTEGRITY AUDIT.
Ren audit. Andrar inget. Size/Segment anvands INTE."""
from __future__ import annotations
import hashlib, json, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
import numpy as np
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/h0_membership_audit"
sys.path.insert(0,str(V2/"tools"))
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
sha=lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

# ---- 3. NASDAQ PIT MEMBERSHIP LEDGER (endast STO + Stock; INGEN segmentanvandning)
snap=json.load(open(V2/"research_k/nasdaq_segment_foundation/monthly_size_snapshots.json"))["rader"]
manader=sorted({x["report_month"] for x in snap})
pres=defaultdict(set); isin_hist=defaultdict(set); delist={}; namn=defaultdict(set)
for x in snap:
    k=x["orderbook_code"].upper()
    pres[k].add(x["report_month"]); isin_hist[k].add(x["isin"]); namn[k].add(x["instrument"])
    if x["delisted"]: delist[k]=min(delist.get(k,"9999"),x["delisted"])
reuse={r["orderbook_code"].upper():r["klass"] for r in
       json.load(open(V2/"research_k/nasdaq_segment_foundation/code_reuse_audit.json"))["flaggade"]}
ledger=[]
for k in sorted(pres):
    mm=sorted(pres[k])
    ledger.append({"orderbook_code":k,"first_seen":mm[0],"last_seen":mm[-1],
      "n_months":len(mm),"isin_interval":sorted(isin_hist[k]),"names":sorted(namn[k]),
      "delisted_date":delist.get(k),"code_reuse_status":reuse.get(k,"CONTINUOUS_INSTRUMENT"),
      "source":"nasdaq monthly Equity Trading by Company and Instrument, Location=STO, Type=Stock"})
json.dump({"schema":"NASDAQ_PIT_MEMBERSHIP_LEDGER_V1","created_utc":NOW,
  "manader":[manader[0],manader[-1]],"n_instrument":len(ledger),
  "notering":"Byggd UTAN segmentinformation. Endast presence/listing/delisting/identitet.",
  "ledger":ledger},open(D/"nasdaq_pit_membership_ledger.json","w"),ensure_ascii=False,indent=1)
print(f"membership-ledger: {len(ledger)} instrument, {manader[0]}..{manader[-1]}")

by_kod_m={(x["orderbook_code"].upper(),x["report_month"]) for x in snap}
by_isin_m={(x["isin"],x["report_month"]) for x in snap}
isin2kod={}
for x in snap: isin2kod.setdefault(x["isin"],x["orderbook_code"].upper())
def norm(k): return k.replace("-"," ").upper()

def klassa(kod, isin, panel):
    pm=panel[:7]; kand=[m for m in manader if m<pm]
    if not kand: return "NASDAQ_DATA_GAP"
    m=kand[-1]; nk=norm(kod)
    k2=isin2kod.get(isin) if isin else None
    for kk in (nk,k2):
        if kk and (kk,m) in by_kod_m: 
            return "CODE_REUSE_AMBIGUITY" if reuse.get(kk,"").startswith("CONFIRMED") else "VALID_MEMBER"
    if isin and (isin,m) in by_isin_m: return "VALID_MEMBER"
    kk = nk if nk in pres else (k2 if k2 in pres else None)
    if kk is None: return "NOT_STO_MAIN_MARKET"
    if m < min(pres[kk]): return "PRE_LISTING"
    if m > max(pres[kk]): return "POST_DELISTING"
    return "OTHER_UNRESOLVED"

# ---- 5+6+9. KLASSIFICERA VARJE PANELOBSERVATION
import stack_h_motor as S
mem={r["kod"]:r.get("kalla") for r in json.load(
     open(V2/"validated/prices_h1419/membership_h1419_v2.json"))["rows"]}
qa=json.load(open(V2/"research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json"))
u26={x["instrument_id"]:x.get("expected_isin") for x in qa}
term={x["instrument_id"] for x in qa if x.get("terminal")}
N=30
def audit(F,univ,namn_f,term_set=None):
    rows=[]; per_panel=[]
    for dt in F["eval_dates"]:
        raw=F["rankings"][dt]
        top=set(r["kod"] for r in raw[:N])
        pv=Counter()
        for i,r in enumerate(raw,1):
            k=r["kod"]; kl=klassa(k,univ.get(k),dt)
            rows.append({"panel":dt,"rank":i,"ticker":k,"isin":univ.get(k),
                "klass":kl,"i_top30":i<=N,
                "bucket":"1-10" if i<=10 else ("11-20" if i<=20 else ("21-30" if i<=30 else "31+")),
                "later_delisted":bool(term_set and k in term_set)})
            if i<=N: pv[kl]+=1
        per_panel.append({"panel":dt,"n_top30":min(N,len(raw)),
            "valid":pv["VALID_MEMBER"],"andel_valid":round(pv["VALID_MEMBER"]/max(1,min(N,len(raw))),4),
            "klasser":dict(pv)})
    return rows,per_panel
r19,p19=audit(S.F19,mem,"2014-2019")
r26,p26=audit(S.F26,u26,"2020-2026",term)
print(f"panelobservationer: 2014-2019 {len(r19)}  2020-2026 {len(r26)}")

def sam(rows,per_panel,namn):
    tot=Counter(x["klass"] for x in rows)
    top=Counter(x["klass"] for x in rows if x["i_top30"])
    c=np.array([p["andel_valid"] for p in per_panel])
    return {"fonster":namn,"N_total":len(rows),"klasser_alla_rankade":dict(tot),
      "klasser_top30":dict(top),"N_top30":sum(top.values()),
      "per_bucket":{b:dict(Counter(x["klass"] for x in rows if x["bucket"]==b))
                    for b in ("1-10","11-20","21-30","31+")},
      "per_ar":{a:dict(Counter(x["klass"] for x in rows if x["panel"][:4]==a))
                for a in sorted({x["panel"][:4] for x in rows})},
      "panel_valid_membership":{"mean":round(float(c.mean()),4),
        "median":round(float(np.median(c)),4),"min":round(float(c.min()),4),
        "p10":round(float(np.percentile(c,10)),4),"p25":round(float(np.percentile(c,25)),4)},
      "per_panel":per_panel}
s19=sam(r19,p19,"2014-2019"); s26=sam(r26,p26,"2020-2026")
for s in (s19,s26):
    pv=s["panel_valid_membership"]
    print(f"  {s['fonster']}: top30-klasser {s['klasser_top30']}")
    print(f"     panel valid membership mean {pv['mean']:.1%} median {pv['median']:.1%} "
          f"MIN {pv['min']:.1%} p10 {pv['p10']:.1%} p25 {pv['p25']:.1%}")
json.dump({"schema":"H0_PANEL_MEMBERSHIP_CLASSIFICATION_V1","created_utc":NOW,
  "2014_2019":s19,"2020_2026":s26},
  open(D/"h0_panel_membership_classification.json","w"),ensure_ascii=False,indent=1)
json.dump({"schema":"H0_PANEL_ROWS_V1","rows":r19+r26},
  open(D/"h0_panel_rows.json","w"),ensure_ascii=False,indent=1)
print("klassificering skriven")
