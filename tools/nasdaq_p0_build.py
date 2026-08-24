"""P0 Main Market monthly master + P1 historical ICB. Ren datauppbyggnad."""
from __future__ import annotations
import hashlib, json, pathlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
V2=pathlib.Path("/home/hannesb/momentum_v2")
D=V2/"research_k/nasdaq_historical_master"; N=D/"normalized"
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
sha=lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

ext=json.load(open(D/"instrument_monthly_extract.json"))["rader"]
disc=json.load(open(V2/"research_k/nasdaq_segment_foundation/archive_discovery.json"))
raw=json.load(open(V2/"research_k/nasdaq_segment_foundation/raw_manifest.json"))["filer"]
pub={p["report_month"]:p["release_time"] for p in disc["poster"]}
rawh={r["report_month"]:{"file":r.get("file"),"sha256":r.get("sha256")} for r in raw}
manader=sorted({x["report_month"] for x in ext}); idx={m:i for i,m in enumerate(manader)}

# ---------- DEL A+B: PIT monthly master
master=[]
for x in ext:
    m=x["report_month"]; rt=pub.get(m)
    kf=rt[:10] if rt else None
    master.append({**x,
      "observation_month":m,
      "period_end":"sista handelsdagen i "+m,
      "source_publication_date":rt,
      "known_from":kf,
      "known_from_rule":"faktiskt release_time fran Nasdaqs nyhets-API" if rt else "SAKNAS",
      "valid_from":kf,
      "valid_to":pub.get(manader[idx[m]+1],"")[:10] if idx[m]+1<len(manader) else None,
      "source_file":rawh.get(m,{}).get("file"),
      "raw_sha256":rawh.get(m,{}).get("sha256")})
utan_pub=sum(1 for x in master if not x["known_from"])
print(f"monthly master: {len(master)} rader, {len(manader)} manader, utan publiceringsdatum: {utan_pub}")

# ---------- DEL B: leakage-test
lk=[]
for x in master:
    if x["known_from"] and x["known_from"][:7] <= x["observation_month"]:
        lk.append({"kod":x["orderbook_code"],"obs":x["observation_month"],"known":x["known_from"]})
print(f"leakage: observationer dar known_from <= observationsmanaden: {len(lk)}")

# ---------- DEL C: identity history
reuse={r["orderbook_code"].upper() for r in json.load(
       open(V2/"research_k/nasdaq_segment_foundation/code_reuse_audit.json"))["flaggade"]}
conf={r["orderbook_code"].upper() for r in json.load(
      open(V2/"research_k/nasdaq_segment_foundation/code_reuse_audit.json"))["flaggade"]
      if r["klass"]=="CONFIRMED_CODE_REUSE"}
ident=defaultdict(lambda:{"isin":defaultdict(list),"namn":set(),"cc":set(),"man":[],"del":[]})
for x in master:
    e=ident[x["orderbook_code"]]
    if x["isin"]: e["isin"][x["isin"]].append(x["observation_month"])
    if x["instrument"]: e["namn"].add(x["instrument"])
    if x["company_code"]: e["cc"].add(x["company_code"])
    e["man"].append(x["observation_month"])
    if x["delisted"]: e["del"].append({"manad":x["observation_month"],"datum":x["delisted"]})
ih=[]
for kod,e in sorted(ident.items()):
    mm=sorted(set(e["man"]))
    iv=[]
    for i,ms in e["isin"].items():
        s=sorted(set(ms)); iv.append({"isin":i,"valid_from":s[0],"valid_to":s[-1],"n_manader":len(s)})
    iv.sort(key=lambda z:z["valid_from"])
    ih.append({"orderbook_code":kod,"first_seen":mm[0],"last_seen":mm[-1],"months_present":len(mm),
      "isin_intervals":iv,"n_isin":len(iv),"names":sorted(e["namn"]),
      "company_codes":sorted(e["cc"]),"delistings":e["del"],
      "code_reuse_flag":("CONFIRMED_CODE_REUSE" if kod.upper() in conf else
                         ("FLAGGED" if kod.upper() in reuse else "NONE")),
      "canonical_instrument_id":f"{kod}#REUSE" if kod.upper() in conf else kod,
      "far_sammanfogas":kod.upper() not in conf})
print(f"identity history: {len(ih)} orderbook-koder, {sum(1 for r in ih if r['n_isin']>1)} med ISIN-byte, "
      f"{sum(1 for r in ih if r['code_reuse_flag']=='CONFIRMED_CODE_REUSE')} confirmed reuse")
issuer=defaultdict(set)
for x in master:
    if x["company_code"]: issuer[x["company_code"]].add(x["orderbook_code"])

# ---------- intervallbyggare
def intervall(nyckel_falt):
    ut=[]
    per=defaultdict(list)
    for x in master:
        v=x.get(nyckel_falt)
        if v: per[x["orderbook_code"]].append((x["observation_month"],v,x.get("known_from")))
    for kod,obs in per.items():
        obs.sort(); cur=None
        for m,v,kf in obs:
            if cur and cur["value"]==v and idx[m]-idx[cur["_last"]]==1:
                cur["_last"]=m
            else:
                if cur: ut.append(cur)
                cur={"orderbook_code":kod,"level":nyckel_falt,"value":v,"valid_from":m,
                     "known_from":kf,"_last":m}
        if cur: ut.append(cur)
    for r in ut:
        j=idx[r["_last"]]
        r["valid_to"]=manader[j+1] if j+1<len(manader) else None
        r["n_manader"]=idx[r["_last"]]-idx[r["valid_from"]]+1
        r["provenance"]="nasdaq monthly Instrument Trading Details"
        del r["_last"]
    return ut

seg_iv=intervall("segment")
tax={f:intervall(f) for f in ("industry","supersector","sector","sub_industry")}
print(f"segment intervals: {len(seg_iv)}")
for f,v in tax.items(): print(f"  {f} intervals: {len(v)}")

for namn,obj in (
 ("instrument_monthly_master.json",{"schema":"NASDAQ_MM_INSTRUMENT_MONTHLY_MASTER_V1",
   "created_utc":NOW,"n_rader":len(master),"manader":[manader[0],manader[-1]],
   "population":"Location=STO, Instrument Type=Stock","rader":master}),
 ("instrument_identity_history.json",{"schema":"NASDAQ_MM_IDENTITY_HISTORY_V1","created_utc":NOW,
   "n":len(ih),"regel":"CONFIRMED_CODE_REUSE far ALDRIG sammanfogas","identity":ih}),
 ("issuer_mapping.json",{"schema":"NASDAQ_MM_ISSUER_MAPPING_V1","created_utc":NOW,
   "n_issuers":len(issuer),"princip":"separat lager; instrumenthistorik kastas aldrig",
   "fordelning":dict(Counter(len(v) for v in issuer.values())),
   "mapping":[{"company_code":k,"orderbooks":sorted(v)} for k,v in sorted(issuer.items())]}),
 ("segment_intervals.json",{"schema":"NASDAQ_MM_SEGMENT_INTERVALS_V1","created_utc":NOW,
   "n":len(seg_iv),"precision":"MONTH","intervals":seg_iv}),
 ("taxonomy_intervals.json",{"schema":"NASDAQ_MM_TAXONOMY_INTERVALS_V1","created_utc":NOW,
   "niva_antal":{f:len(v) for f,v in tax.items()},"precision":"MONTH",
   "ingen_bakatprojektion":True,"intervals":{f:v for f,v in tax.items()}})):
    json.dump(obj,open(N/namn,"w"),ensure_ascii=False)
json.dump({"schema":"PIT_LEAKAGE_QA_V1","created_utc":NOW,
  "regel":"known_from ar faktiskt release_time; observationsmanaden M far aldrig vara >= known_from",
  "n_observationer":len(master),"utan_publiceringsdatum":utan_pub,
  "violations":len(lk),"exempel":lk[:10]},open(D/"pit_publication_qa.json","w"),ensure_ascii=False,indent=1)
print("normalized-lager skrivet")
