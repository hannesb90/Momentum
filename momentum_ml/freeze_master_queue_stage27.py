"""Freeze the unattended master queue contract before service start."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from niva3_stage_control import freeze_stage,verify_manifest
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/26_sr3_regime_rvol_fullmodel.json'
QUEUE=ROOT/'results/research_master_queue_2026_08_01_v2.csv';OUT=ROOT/'results/nightly_master_queue_contract_2026_08_01.json'
RUNNER=ROOT/'momentum_ml/nightly_master_queue_2026_08_01.py'
def main():
 p=verify_manifest(PARENT);q=pd.read_csv(QUEUE)
 report={'status':'PASS','test':'N3-27-master-night-queue-contract','parent_stage':p['manifest_sha256'],'queue_items':len(q),
         'controls':['recursive N2/N3 verification before and after each item','production artifact hash lock','per-item log and atomic state','continue after FAIL/BLOCKED/TIMEOUT','successful economic runner must advance frozen N3 chain','no stale-script execution'],
         'completed_before_queue':['baseline_pipeline_parity','conditional_52_13','regime_cross_section_interaction','generic_model_gate','statistical_reality_check'],
         'runner_policy':'current-contract runners only; missing implementations are explicit blockers, not results','production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 stage=freeze_stage('27_master_night_queue_contract',[OUT,QUEUE,RUNNER,Path(__file__).resolve()],{'test':'N3-27-master-night-queue-contract','queue_items':len(q),'production':False},parent=PARENT)
 print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
