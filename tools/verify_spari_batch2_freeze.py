#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];M=R/'research_i/FREEZE_MANIFEST_BATCH2.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
m=json.loads(M.read_text());bad=[]
for x in m['files']:
 p=R/x['path']
 if not p.is_file() or sha(p)!=x['sha256'] or p.stat().st_size!=x['bytes']:bad.append(x['path'])
agg=hashlib.sha256(json.dumps(m['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert not bad and agg==m['aggregate_sha256'],(bad,agg)
print(json.dumps({'status':'PASS','files':len(m['files']),'manifest_sha256':sha(M),'aggregate_sha256':agg}))
