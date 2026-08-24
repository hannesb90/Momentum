#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[1];O=R/'research_k/k2a_marketcap_ev_audit_v1';M=O/'manifest.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.load(open(M));bad=[]
 for x in m['inputs']+m['outputs']:
  p=R/x['path']
  if not p.exists() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:bad.append(x['path'])
 if sha(M)!=(O/'manifest.sha256').read_text().split()[0]:bad.append('manifest.json')
 f=O/'FINAL_FREEZE_MANIFEST.json';n=0
 if f.exists():
  fm=json.load(open(f));n=len(fm['files'])
  for x in fm['files']:
   p=R/x['path']
   if not p.exists() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:bad.append('FREEZE:'+x['path'])
  if sha(f)!=(O/'FINAL_FREEZE_MANIFEST.sha256').read_text().split()[0]:bad.append('FINAL_FREEZE_MANIFEST.json')
 print(json.dumps({'checked_base':len(m['inputs'])+len(m['outputs'])+1,'checked_final_freeze':n+1,'failures':bad},indent=2));return bool(bad)
if __name__=='__main__':sys.exit(main())
