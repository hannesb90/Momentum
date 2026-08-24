#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_i/FREEZE_MANIFEST_BATCH1.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files():
 paths=[ROOT/'tools/spari_inventory.py',ROOT/'tools/spari_batch1.py',ROOT/'tools/test_spari_batch1.py',ROOT/'tools/freeze_spari_batch1.py',ROOT/'docs/SPARI_BATCH1_RESULT.md']
 paths += [p for p in sorted((ROOT/'research_i').rglob('*')) if p.is_file() and p!=OUT]
 return paths
def build():
 fs=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files()]
 return {'freeze_id':'SPARI_BATCH1_V1_IMMUTABLE_2026-08-09','track_h_effect':'NONE','result_status':'BATCH1_COMPLETE_STOPPED_BEFORE_EXITS','files':fs,'aggregate_sha256':hashlib.sha256(json.dumps(fs,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
def main():
 if OUT.exists():
  m=json.loads(OUT.read_text());actual=build();assert m==actual,'freeze mismatch';print(json.dumps({'status':'PASS','files':len(m['files']),'aggregate_sha256':m['aggregate_sha256'],'manifest_sha256':sha(OUT)},indent=2));return
 OUT.write_text(json.dumps(build(),ensure_ascii=False,sort_keys=True,indent=2)+'\n');main()
if __name__=='__main__':main()
