#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];M=R/'research_i/FREEZE_MANIFEST_BATCH3.json';m=json.loads(M.read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();bad=[x['path'] for x in m['files'] if not (R/x['path']).is_file() or sha(R/x['path'])!=x['sha256'] or (R/x['path']).stat().st_size!=x['bytes']];agg=hashlib.sha256(json.dumps(m['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest();assert not bad and agg==m['aggregate_sha256'],(bad,agg);print(json.dumps({'status':'PASS','files':len(m['files']),'manifest_sha256':sha(M),'aggregate_sha256':agg}))
