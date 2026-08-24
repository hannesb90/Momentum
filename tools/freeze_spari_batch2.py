#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research_i/results/SPARI_BATCH2_EXIT_HOLDING_V2';FREEZE=ROOT/'research_i/FREEZE_MANIFEST_BATCH2.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size}
def main():
 assert not FREEZE.exists(),'no overwrite'
 fixed=[ROOT/x for x in ['research_i/batch2_preregistration.json','research_i/FREEZE_MANIFEST_BATCH1.json','research_i/BATCH2_REPRODUCTION_PROOF.json','trackh/H0_LOCK.json','research_i/docs/TREND_CONSISTENCY_DEFINITION_MISMATCH.md','research_i/docs/UNTESTED_DATA_BACKLOG.md','tools/spari_batch2.py','tools/test_spari_batch2.py','docs/SPARI_BATCH2_EXIT_HOLDING_RESULT.md']]
 files=[item(p) for p in fixed]+[item(p) for p in sorted(OUT.iterdir()) if p.is_file()]
 agg=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest();m={'freeze_id':'SPARI_BATCH2_EXIT_HOLDING_V2_IMMUTABLE_2026-08-09','status':'COMPLETE_STOP_AFTER_BATCH2','result':'NO_FORWARD_CHALLENGER_RECOMMENDED','files':files,'aggregate_sha256':agg,'protected_tracks_modified':False,'invalid_diagnostic_runs_retained':['research_i/results/SPARI_BATCH2_EXIT_HOLDING_V2_INVALID_H0_RECONCILIATION','research_i/results/SPARI_BATCH2_EXIT_HOLDING_V2_INVALID_MISSING_LAST_PERIOD','research_i/results/SPARI_BATCH2_EXIT_HOLDING_V2_INVALID_ENTRY_STATE_RESET']}
 FREEZE.write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2)+'\n');(FREEZE.with_suffix('.sha256')).write_text(sha(FREEZE)+'  '+FREEZE.name+'\n');print(json.dumps({'freeze':m['freeze_id'],'files':len(files),'manifest_sha256':sha(FREEZE),'aggregate':agg},indent=2))
if __name__=='__main__':main()
