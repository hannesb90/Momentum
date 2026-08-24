#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,datetime
R=Path(__file__).resolve().parents[1];O=R/'research_k/k2a_marketcap_ev_audit_v1';F=O/'FINAL_FREEZE_MANIFEST.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)}
def main():
 base=json.load(open(O/'manifest.json'));paths=[R/x['path'] for x in base['inputs']+base['outputs']]+[R/'docs/K2A_PIT_MARKET_CAP_EV_DATA_FOUNDATION.md',R/'tools/spark_k2a_marketcap_ev_audit.py',R/'tools/verify_spark_k2a_audit.py',R/'tools/freeze_spark_k2a_audit.py']
 m={'version_id':'K2A_PIT_MARKET_CAP_EV_DATA_AUDIT_BLOCKED_V1_FINAL_IMMUTABLE_2026-08-09','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'decisions':{'pit_market_cap':'BLOCKERAD','pit_ev':'BLOCKERAD','value_within_momentum':'FORTSATT BLOCKERAD'},'files':[row(p) for p in paths]};F.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(O/'FINAL_FREEZE_MANIFEST.sha256').write_text(sha(F)+'  FINAL_FREEZE_MANIFEST.json\n');print(sha(F))
if __name__=='__main__':main()
