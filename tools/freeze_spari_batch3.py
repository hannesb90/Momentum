#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'research_i/results/SPARI_BATCH3_FINAL_LEGACY_V1';M=R/'research_i/FREEZE_MANIFEST_BATCH3.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):return {'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size}
fixed=['research_i/I3_PREREG_FREEZE.json','research_i/batch3_preregistration.json','research_i/LEGACY_V2_COVERAGE_MATRIX_PRE_BATCH3.json','research_i/LEGACY_V2_COVERAGE_MATRIX.json','research_i/BATCH3_REPRODUCTION_PROOF.json','tools/spari_final_inventory.py','tools/spari_batch3.py','tools/test_spari_batch3.py','tools/spari_finalize_coverage.py','docs/LEGACY_V2_COVERAGE_MATRIX.md']
files=[item(R/x) for x in fixed]+[item(p) for p in sorted(O.iterdir()) if p.is_file()];agg=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest();m={'freeze_id':'SPARI_BATCH3_FINAL_LEGACY_V1_IMMUTABLE_2026-08-09','status':'LEGACY_REPLICATION_COMPLETE_STOPPED','files':files,'aggregate_sha256':agg,'new_forward_challengers':[],'H0_H1_H2_modified':False};M.write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2)+'\n');M.with_suffix('.sha256').write_text(sha(M)+'  '+M.name+'\n');print(json.dumps({'files':len(files),'manifest_sha256':sha(M),'aggregate_sha256':agg},indent=2))
