#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[1];O=R/'research_k/results/K1_SECTOR_INFORMATION_DIVERSIFICATION_V2';M=O/'manifest.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.load(open(M));bad=[]
 for x in m['files']:
  p=O/x['path']
  if not p.exists() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:bad.append(x['path'])
 prov=json.load(open(O/'run_provenance.json'))
 checks={R/'research_k/k1_sector_information_diversification_preregistration.json':prov['preregistration_sha256'],R/'research_k/sector_classification_v1/manifest.json':prov['sector_manifest_sha256'],R/'sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3/rankings.json':prov['h0_rankings_sha256']}
 for p,h in checks.items():
  if not p.exists() or sha(p)!=h:bad.append(str(p.relative_to(R)))
 fm=R/'research_k/k1_final_freeze/FREEZE_MANIFEST.json'
 if fm.exists():
  freeze=json.load(open(fm))
  for x in freeze['files']:
   p=R/x['path']
   if not p.exists() or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:bad.append('FREEZE:'+x['path'])
 print(json.dumps({'checked_outputs':len(m['files']),'checked_locked_inputs':len(checks),'checked_final_freeze_files':len(freeze['files']) if fm.exists() else 0,'manifest_aggregate_sha256':m['aggregate_sha256'],'failures':bad},indent=2));return bool(bad)
if __name__=='__main__':sys.exit(main())
