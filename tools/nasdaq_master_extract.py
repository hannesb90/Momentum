"""Valideringsextraktion av nyckelfalt ur Instrument Trading Details, alla 201 manader.
Endast for datavalidering (Steg 3-8). Ingen forskning, ingen avkastningsanalys."""
from __future__ import annotations
import json, pathlib, re, sys, zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/nasdaq_historical_master"
sys.path.insert(0,str(V2/"tools/nasdaq_segment"))
from ole2 import OLE2
import biff8
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
ARK="Instrument Trading Details"
VILL={"instrument":"instrument","company code":"company_code","orderbook code":"orderbook_code",
 "isin":"isin","instrument type":"instrument_type","segment":"segment","industry":"industry",
 "indsutry":"industry","sector":"sector","sub- industry":"sub_industry","super sector":"supersector",
 "curr- ency":"currency","loca- tion":"location","delisted":"delisted","issuer country":"issuer_country",
 "no of shares listed":"no_of_shares_listed","market cap":"market_cap","latest paid":"latest_paid",
 "listed days":"listed_days","total turnover":"total_turnover",
 "total no of traded shares":"total_traded_shares","total no of trades":"total_trades",
 "average turnover":"avg_turnover","average trade size":"avg_trade_size","traded days":"traded_days",
 "turnover velocity":"turnover_velocity","average closing spread":"avg_closing_spread",
 "vwap":"vwap","high paid":"high_paid","low paid":"low_paid",
 "otc turnover":"otc_turnover","otc no of trades":"otc_trades","round lot":"round_lot"}
def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def rader_xlsx(p):
    z=zipfile.ZipFile(p); ss=[]
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{NS}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rels={r.get("Id"):r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for s in wb.iter(f"{NS}sheet"):
        if s.get("name")!=ARK: continue
        tgt=rels[s.get(RNS+"id")]; path=tgt if tgt.startswith("xl/") else "xl/"+tgt.lstrip("/")
        out=[]
        for row in ET.fromstring(z.read(path)).iter(f"{NS}row"):
            c=[]
            for cell in row.iter(f"{NS}c"):
                v=cell.find(f"{NS}v"); t=cell.get("t")
                c.append(ss[int(v.text)] if (t=="s" and v is not None) else (v.text if v is not None else ""))
            out.append(c)
        return out
    return []
def rader_xls(p):
    for b in biff8.parse(OLE2(p.read_bytes()).read("Workbook")):
        if b["name"]!=ARK: continue
        c=b["cells"]
        if not c: return []
        maxr=max(r for r,_ in c); maxc=max(x for _,x in c)
        return [[c.get((r,k),"") for k in range(maxc+1)] for r in range(maxr+1)]
    return []
def num(v):
    try: return float(v)
    except (TypeError,ValueError): return None
def xdatum(v):
    n=num(v)
    if n is None or n<=0: return None
    return (date(1899,12,30)+timedelta(days=int(n))).isoformat()
filer=sorted(V2.glob("raw/nasdaq_segment/monthly/*/[0-9]*.xls*"))
ut=[]; fel=[]
for i,f in enumerate(filer,1):
    man=f.stem
    rader=rader_xlsx(f) if f.suffix==".xlsx" else rader_xls(f)
    hi=None
    for ri,r in enumerate(rader[:20]):
        n=[norm(x).lower() for x in r]
        if "isin" in n and "segment" in n: hi=ri; break
    if hi is None: fel.append({"manad":man,"fel":"header ej hittad"}); continue
    kol={}
    for ci,h in enumerate(rader[hi]):
        k=norm(h).lower()
        if k in VILL: kol.setdefault(VILL[k],ci)
    for r in rader[hi+1:]:
        g=lambda n: (r[kol[n]] if n in kol and kol[n]<len(r) else "")
        namn=norm(g("instrument"))
        if not namn: continue
        rad={"report_month":man,"instrument":namn}
        for fk in ("company_code","orderbook_code","isin","instrument_type","segment","industry",
                   "sector","sub_industry","supersector","currency","location","issuer_country"):
            rad[fk]=norm(g(fk)) or None
        rad["delisted"]=xdatum(g("delisted"))
        for fk in ("no_of_shares_listed","market_cap","latest_paid","listed_days","total_turnover",
                   "total_traded_shares","total_trades","avg_turnover","avg_trade_size","traded_days",
                   "turnover_velocity","avg_closing_spread","vwap","high_paid","low_paid",
                   "otc_turnover","otc_trades","round_lot"):
            rad[fk]=num(g(fk))
        ut.append(rad)
    if i%40==0: print(f"  {i}/{len(filer)} ... {man}  rader {len(ut)}",flush=True)
sto=[x for x in ut if x["location"]=="STO" and x["instrument_type"]=="Stock"]
print(f"\ntotalt {len(ut)} rader, STO+Stock {len(sto)}")
json.dump({"schema":"NASDAQ_INSTRUMENT_MONTHLY_VALIDATION_EXTRACT_V1",
 "created_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
 "syfte":"VALIDERINGSEXTRAKTION for faltinventering. Inte ett canonical dataset.",
 "n_rader_totalt":len(ut),"n_sto_stock":len(sto),"fel":fel,
 "rader":sto},open(D/"instrument_monthly_extract.json","w"),ensure_ascii=False)
print("skrivet: instrument_monthly_extract.json")
