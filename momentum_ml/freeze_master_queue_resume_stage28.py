"""Freeze automatic resume semantics for the master queue."""
from __future__ import annotations
import json
from pathlib import Path
from niva3_stage_control import freeze_stage,verify_manifest
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/27_master_night_queue_contract.json';OUT=ROOT/'results/nightly_master_queue_resume_contract.json'
def main():
 p=verify_manifest(PARENT);report={'status':'PASS','test':'N3-28-master-queue-auto-resume','parent_stage':p['manifest_sha256'],
 'runner_convention':'momentum_ml/run_<mechanism_key>_current.py','retry_policy':'BLOCKED_IMPLEMENTATION is reopened automatically when runner exists','schedule':'systemd timer nightly 22:00, Persistent=true','production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');stage=freeze_stage('28_master_queue_auto_resume',[OUT,ROOT/'momentum_ml/nightly_master_queue_resume.py',Path(__file__).resolve()],{'test':'N3-28-master-queue-auto-resume','production':False},parent=PARENT);print(json.dumps(report,indent=2));print(stage)
if __name__=='__main__':main()
