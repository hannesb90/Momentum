"""N3 stage 22: resolve target-horizon versus rotation-cadence semantics."""
from __future__ import annotations
import json
from pathlib import Path
from niva2_stage_control import verify_manifest as verify_n2
from niva3_stage_control import freeze_stage, verify_manifest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/21_semantic_queue_remediation.json'
N2_TARGET=ROOT/'results/niva2_stages/01_target_isolation.json'
N2_ROTATION=ROOT/'results/niva2_stages/02_rotation_isolation.json'
STAGE12=ROOT/'results/niva3_stages/12_reconstructed_price_retrain_corrected.json'
OUT=ROOT/'results/niva3_sr1_anchor_contract.json'

def main():
    parent=verify_manifest(PARENT); target=verify_n2(N2_TARGET); rotation=verify_n2(N2_ROTATION); stage12=verify_manifest(STAGE12)
    target_report=json.loads((ROOT/'results/target_horizon_isolated.json').read_text())
    stage12_report=json.loads((ROOT/'results/niva3_reconstructed_price_retrain_corrected.json').read_text())
    assert target['metadata']['winner']=='binary_13_target'
    assert rotation['metadata']['target']=='binary_13v' and rotation['metadata']['winner']=='calendar_52'
    report={'status':'PASS','test':'N3-SR1-anchor-contract', 'parent_stage':parent['manifest_sha256'],
            'current_anchor_target_weeks':13,'current_execution_rotation_weeks':52,
            'n2_isolated_target_results':{'13v':target_report['binary_13_target'],'52v':target_report['binary_52_target']},
            'stage12_corrected_anchor_cagr':stage12_report['reconstructed_metrics']['CAGR'],
            'invalid_legacy_label':'tune_conditional_13_overlay.py calls selection_rank baseline_52 although it is the 13v-target winner',
            'corrected_test_direction':'13v target anchor plus conditional 52v target-ranker overlay',
            'reason':'52 describes execution cadence, not the frozen model target; adding a 13v target to itself is not an orthogonal overlay',
            'selection_allowed':False,'production':False,'holdout_used':False}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('22_sr1_anchor_contract',[OUT,Path(__file__).resolve()],
                       {'test':'N3-SR1-anchor-contract','anchor_target_weeks':13,
                        'rotation_weeks':52,'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False)); print(stage)

if __name__=='__main__': main()
