#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[1]; O=R/'research_k/sector_classification_v1'; M=O/'manifest.json'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.load(open(M)); failures=[]
 for x in m['inputs']+m['artifacts']:
  p=R/x['path']
  if not p.exists(): failures.append(f"MISSING {x['path']}")
  elif p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']: failures.append(f"MISMATCH {x['path']}")
 side=(O/'manifest.sha256').read_text().split()[0]
 if sha(M)!=side: failures.append('MANIFEST_HASH_MISMATCH')
 print(json.dumps({'version_id':m['version_id'],'checked':len(m['inputs'])+len(m['artifacts']),'failures':failures},indent=2)); return 1 if failures else 0
if __name__=='__main__': sys.exit(main())
