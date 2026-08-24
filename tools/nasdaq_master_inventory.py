"""STEG 1-2: fullstandig schema- och faltinventering over ALLA 201 filer och ALLA blad."""
from __future__ import annotations
import json, pathlib, re, sys, zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/nasdaq_historical_master"
sys.path.insert(0,str(V2/"tools/nasdaq_segment"))
from ole2 import OLE2
import biff8
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def las_xlsx(p):
    z=zipfile.ZipFile(p); ss=[]
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{NS}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rels={r.get("Id"):r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    ark={}
    for s in wb.iter(f"{NS}sheet"):
        tgt=rels.get(s.get(RNS+"id"))
        if not tgt: continue
        path=tgt if tgt.startswith("xl/") else "xl/"+tgt.lstrip("/")
        if path not in z.namelist(): continue
        rader=[]
        for row in ET.fromstring(z.read(path)).iter(f"{NS}row"):
            c=[]
            for cell in row.iter(f"{NS}c"):
                v=cell.find(f"{NS}v"); t=cell.get("t")
                c.append(ss[int(v.text)] if (t=="s" and v is not None) else (v.text if v is not None else ""))
            rader.append(c)
            if len(rader)>25: break
        ark[s.get("name")]=rader
    return ark

def las_xls(p):
    ark={}
    for b in biff8.parse(OLE2(p.read_bytes()).read("Workbook")):
        c=b["cells"]
        if not c: ark[b["name"]]=[]; continue
        maxr=min(25,max(r for r,_ in c)); maxc=max(x for _,x in c)
        ark[b["name"]]=[[c.get((r,k),"") for k in range(maxc+1)] for r in range(maxr+1)]
    return ark

def norm(s): return re.sub(r'\s+',' ',str(s or '')).strip()

filer=sorted(V2.glob("raw/nasdaq_segment/monthly/*/[0-9]*.xls*"))
blad=Counter(); falt=defaultdict(lambda:{"sheets":Counter(),"manader":[],"raw_names":Counter()})
schema_sig=defaultdict(list); per_fil={}
for i,f in enumerate(filer,1):
    man=f.stem
    try:
        ark=las_xlsx(f) if f.suffix==".xlsx" else las_xls(f)
    except Exception as e:
        per_fil[man]={"fel":f"{type(e).__name__}: {e}"}; continue
    info={}
    for namn,rader in ark.items():
        blad[namn]+=1
        # hitta headerrad = raden med flest icke-tomma unika textceller
        best,bi=0,None
        for ri,r in enumerate(rader[:20]):
            txt=[norm(x) for x in r if norm(x) and not norm(x).replace('.','').replace('-','').isdigit()]
            if len(set(txt))>best: best,bi=len(set(txt)),ri
        hdr=[norm(x) for x in (rader[bi] if bi is not None else []) if norm(x)]
        info[namn]={"header_row":bi,"n_headers":len(hdr),"headers":hdr}
        for h in hdr:
            k=h.lower().replace('\n',' ')
            falt[k]["sheets"][namn]+=1; falt[k]["manader"].append(man); falt[k]["raw_names"][h]+=1
        schema_sig[(namn,tuple(sorted(set(h.lower() for h in hdr))))].append(man)
    per_fil[man]=info
    if i%40==0: print(f"  {i}/{len(filer)} ... {man}",flush=True)

manader=sorted(per_fil)
inv=[]
for k,v in sorted(falt.items()):
    mm=sorted(set(v["manader"]))
    inv.append({"canonical_name":k,"raw_names":sorted(v["raw_names"]),
      "sheets":dict(v["sheets"]),"first_month":mm[0],"last_month":mm[-1],
      "months_present":len(mm),"coverage_fraction":round(len(mm)/len(manader),4)})
print(f"\nblad: {dict(blad)}")
print(f"unika faltnamn (normaliserade): {len(inv)}")
print(f"schemavarianter (blad x headerset): {len(schema_sig)}")
json.dump({"schema":"NASDAQ_MAIN_MARKET_SCHEMA_INVENTORY_V1",
  "created_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
  "n_filer":len(filer),"manader":[manader[0],manader[-1]],
  "blad":dict(blad),"n_unika_falt":len(inv),"n_schemavarianter":len(schema_sig),
  "falt":inv},open(D/"field_inventory.json","w"),ensure_ascii=False,indent=1)
json.dump({"schema":"NASDAQ_SCHEMA_HISTORY_V1",
  "varianter":[{"sheet":k[0],"n_headers":len(k[1]),"manader":sorted(v),
                "first":min(v),"last":max(v),"n_manader":len(v),"headers":sorted(k[1])}
               for k,v in sorted(schema_sig.items(),key=lambda x:-len(x[1]))],
  "per_fil":per_fil},open(D/"schema_history.json","w"),ensure_ascii=False,indent=1)
print("skrivet: field_inventory.json, schema_history.json")
