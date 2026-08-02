"""N3 stage 21: correct SR8 separation in the frozen semantic queue."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from niva3_stage_control import freeze_stage, verify_manifest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/niva3_stages/20_semantic_research_queue.json'
SOURCE=ROOT/'results/research_semantic_mapping_2026_08_01.csv'
MAP_OUT=ROOT/'results/research_semantic_mapping_2026_08_01_v2.csv'
QUEUE_OUT=ROOT/'results/research_master_queue_2026_08_01_v2.csv'
SUMMARY=ROOT/'results/research_master_queue_summary_2026_08_01_v2.json'

def main():
    parent=verify_manifest(PARENT); x=pd.read_csv(SOURCE).fillna('')
    mask=x.script.isin(['tune_riskadj_momentum_ablation.py','tune_riskadj_momentum_ic.py'])
    if int(mask.sum())!=2: raise RuntimeError('Expected exactly two risk-adjusted momentum scripts')
    x.loc[mask,'mechanism_key']='conditional_risk_adjusted_momentum'; x.loc[mask,'sr_links']='SR8'
    x.to_csv(MAP_OUT,index=False)
    actionable=x[x.disposition.isin(['STALE_REVALIDATE_OR_REWRITE','BLOCKED_DATA_GATE'])]
    priority={'baseline_pipeline_parity':0,'conditional_52_13':1,'regime_cross_section_interaction':2,
              'newly_qualified_sleeve':3,'conditional_risk_adjusted_momentum':4,
              'ranker_uncertainty_switch':5,'cause_specific_reentry':6,
              'drawdown_rank_confirmed_exit':7,'armed_takeprofit_state_machine':8,
              'rank_calibration':9,'capacity_execution_cost':10,'statistical_reality_check':99}
    rows=[]
    for key,g in actionable.groupby('mechanism_key',sort=False):
        blocked=bool((g.disposition=='BLOCKED_DATA_GATE').any())
        rows.append({'mechanism_key':key,'sr_links':','.join(sorted({v for c in g.sr_links for v in str(c).split(',')})),
                     'priority':priority.get(key,80 if blocked else 50),
                     'status':'BLOCKED_DATA_GATE' if blocked else 'READY_FOR_METHOD_REWRITE',
                     'historical_scripts':';'.join(sorted(g.script)),'script_count':len(g),
                     'has_any_old_result':bool(g.has_saved_result.astype(bool).any()),
                     'old_result_locators':';'.join(sorted(set(v for v in g.latest_saved_result if v))),
                     'adoption_allowed_from_old_result':False,
                     'next_action':'satisfy PIT/event data gate' if blocked else 'preregister current-baseline implementation'})
    q=pd.DataFrame(rows).sort_values(['priority','mechanism_key']).reset_index(drop=True)
    q.insert(0,'queue_order',range(1,len(q)+1)); q.to_csv(QUEUE_OUT,index=False)
    report={'status':'PASS','test':'N3-21-semantic-queue-remediation','parent_stage':parent['manifest_sha256'],
            'correction':'SR8 separated from SR3 regime-interaction family','source_scripts':len(x),
            'unique_actionable_mechanisms':len(q),'ready_for_method_rewrite':int((q.status=='READY_FOR_METHOD_REWRITE').sum()),
            'blocked_data_gate':int((q.status=='BLOCKED_DATA_GATE').sum()),
            'historical_result_locators_preserved':int(q.old_result_locators.ne('').sum()),
            'first_economic_test':'conditional_52_13 / SR1','production':False}
    SUMMARY.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    stage=freeze_stage('21_semantic_queue_remediation',[MAP_OUT,QUEUE_OUT,SUMMARY,Path(__file__).resolve()],
                       {'test':'N3-21-semantic-queue-remediation','unique_actionable_mechanisms':len(q),'production':False},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False)); print(stage)

if __name__=='__main__': main()
