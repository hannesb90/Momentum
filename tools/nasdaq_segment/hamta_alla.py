"""Hamtar alla upptackta RAW-filer ur archive_discovery.json. STDLIB ONLY."""
from __future__ import annotations
import hashlib, json, pathlib, time, urllib.request
UA={"User-Agent":"Mozilla/5.0 (compatible; momentum-v2 research data collector)"}
V2=pathlib.Path("/home/hannesb/momentum_v2")
D=V2/"research_k/nasdaq_segment_foundation"
RAW=V2/"raw/nasdaq_segment/monthly"
disc=json.load(open(D/"archive_discovery.json"))
logg=[]
for i,p in enumerate(sorted(disc["poster"],key=lambda x:x["report_month"]),1):
    man,ext=p["report_month"],p["file_type"]
    d=RAW/man[:4]; d.mkdir(parents=True,exist_ok=True)
    f=d/f"{man}.{ext}"
    if f.exists():
        b=f.read_bytes()
        logg.append({**p,"file":str(f.relative_to(V2)),"sha256":hashlib.sha256(b).hexdigest(),
                     "byte_size":len(b),"status":"REDAN_PA_DISK"}); continue
    ok=False
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(p["attachment_url"],headers=UA),
                                        timeout=90) as r:
                b=r.read()
            ok=True; break
        except Exception as e:
            if k==2: logg.append({**p,"status":f"DOWNLOAD_FAILED: {type(e).__name__}"})
            time.sleep(2*(k+1))
    if not ok: continue
    if b[:8]!=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and b[:4]!=b"PK\x03\x04":
        logg.append({**p,"status":"EJ_EXCEL","signatur":b[:8].hex(),"byte_size":len(b)}); continue
    f.write_bytes(b)
    logg.append({**p,"file":str(f.relative_to(V2)),"sha256":hashlib.sha256(b).hexdigest(),
                 "byte_size":len(b),"status":"HAMTAD"})
    if i%20==0: print(f"  {i}/{len(disc['poster'])} ... {man}",flush=True)
from collections import Counter
print("STATUS:",dict(Counter(x["status"].split(':')[0] for x in logg)))
json.dump({"schema":"NASDAQ_RAW_MANIFEST_V2","n":len(logg),
  "status":dict(Counter(x["status"].split(':')[0] for x in logg)),"filer":logg},
  open(D/"raw_manifest.json","w"),ensure_ascii=False,indent=1)
print("skrivet: raw_manifest.json")
