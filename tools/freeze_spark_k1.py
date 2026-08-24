#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,datetime
R=Path(__file__).resolve().parents[1];O=R/'research_k/k1_final_freeze';RES=R/'research_k/results/K1_SECTOR_INFORMATION_DIVERSIFICATION_V2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)}
def main():
 O.mkdir(parents=True,exist_ok=True)
 repro=[]
 for p in sorted(RES.iterdir()):
  if p.is_file():
   q=Path('/tmp/k1_sector_reproduction_20260809')/p.name
   repro.append({'path':p.name,'original_sha256':sha(p),'reproduction_sha256':sha(q),'byte_identical':p.read_bytes()==q.read_bytes()})
 (O/'reproduction_check.json').write_text(json.dumps({'all_byte_identical':all(x['byte_identical'] for x in repro),'files':repro},indent=2)+'\n')
 paths=[R/'research_k/k1_sector_information_diversification_preregistration.json',R/'research_k/k1_future_forward_hypothesis.json',R/'research_k/sector_classification_v1/manifest.json',R/'sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3/rankings.json',R/'docs/K1_SECTOR_INFORMATION_DIVERSIFICATION_RESULT.md',R/'tools/spark_k1_sector_information_diversification.py',R/'tools/verify_spark_k1_results.py',R/'tools/freeze_spark_k1.py',O/'reproduction_check.json']+sorted(p for p in RES.iterdir() if p.is_file())
 m={'version_id':'K1_SECTOR_INFORMATION_DIVERSIFICATION_FINAL_IMMUTABLE_2026-08-09','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'formal_result':{'sector_alpha':'SECTOR TILLFÖR INTE ALPHA','diversification':'INGET STÖD','champion':'H0 OFÖRÄNDRAD'},'historical_tuning_closed':True,'files':[row(p) for p in paths]}
 (O/'FREEZE_MANIFEST.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');h=sha(O/'FREEZE_MANIFEST.json');(O/'FREEZE_MANIFEST.sha256').write_text(h+'  FREEZE_MANIFEST.json\n');print(h)
if __name__=='__main__':main()
