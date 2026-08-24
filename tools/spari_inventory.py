#!/usr/bin/env python3
"""Source-only inventory. Never reads legacy result files or V2 targets."""
from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LEGACY=Path('/home/hannesb/momentum_prod_work/momentum_ml')
OUT=ROOT/'research_i/legacy_hypothesis_registry.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
NOW={
 'attention':('REPLIKERA NU','report/attention/PEAD'),
 'pead':('REPLIKERA NU','report/attention/PEAD'),
 'report_crowding':('REPLIKERA NU','report/attention/PEAD'),
 'report_dip':('REPLIKERA NU','report/attention/PEAD'),
 'dividend_gap':('REPLIKERA SENARE — DATA SAKNAS','dividend-gap'),
 'dispersion':('REPLIKERA NU','dispersion/proxy'),
 'insider_gap':('REPLIKERA SENARE — DATA SAKNAS','insider-gap'),
 'resid':('REPLIKERA NU','residual momentum'),
 'riskadj':('REDAN TESTAD I V2','risk-adjusted momentum'),
 'quality_momentum':('REPLIKERA NU','momentum quality'),
 'trend_consistency':('REPLIKERA NU','momentum quality'),
 'voltarget':('REPLIKERA NU','target-vol overlay'),
 'sizing':('REPLIKERA NU','inverse-vol sizing'),
}
LATER=('exit','drawdown','dd20','streak','milestone','reentry','refill','takeprofit','anchor','hold_forever','correlation_filter')
MISSING=('atr','sentiment','analyst','revision','sue')
ALREADY=('fundamental','macro','regime','horizon','objective','lambdarank','catboost','lightgbm','xgboost','hyperparam','feature_group','ablation','nan_handling')
PRODUCT=('audit','gate_','build_','freeze_','diag_','monitor','start_','update_','fetch_','retrain','remediate','reconcile','dispatcher','stage_control','ticket','commentary','main.py','config.py')
def classify(name):
 low=name.lower()
 if any(x in low for x in PRODUCT):return 'RENT IMPLEMENTATIONS-/PRODUKTTEST','implementation/QA'
 if any(x in low for x in MISSING):return 'REPLIKERA SENARE — DATA SAKNAS','missing verified V2 data'
 if any(x in low for x in LATER):return 'REPLIKERA NU','later preregistered batch; not Batch 1'
 for key,(status,fam) in NOW.items():
  if key in low:return status,fam
 if any(x in low for x in ALREADY):return 'REDAN TESTAD I V2','already tested or architecture family'
 if any(x in low for x in ('etf','theme','large_small','isk','monthly_contribution','leverage','hedge','allocation')):return 'EJ RELEVANT FÖR NY ARKITEKTUR','separate product/allocation mandate'
 if any(x in low for x in ('model','ensemble','ranker','prob_','precision','calibration','training','seed_')):return 'FÖR LIK EN REDAN TESTAD HYPOTES','legacy ML architecture/tuning'
 return 'EJ RELEVANT FÖR NY ARKITEKTUR','no distinct V2 economic hypothesis identified'
def main():
 rows=[]
 for p in sorted(LEGACY.glob('*.py')):
  status,family=classify(p.name)
  rows.append({'legacy_script':p.name,'legacy_path':str(p),'legacy_source_sha256':sha(p),'classification':status,'family':family,'legacy_results_used_as_evidence':False})
 counts={}
 for r in rows:counts[r['classification']]=counts.get(r['classification'],0)+1
 out={'registry_id':'SPARI_LEGACY_HYPOTHESIS_REGISTRY_V1','policy':'Source names/code are hypothesis generators only. No legacy result file was read by this inventory.','legacy_root':str(LEGACY),'scripts_inventory_count':len(rows),'classification_counts':counts,'rows':rows}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':'COMPLETE','scripts':len(rows),'counts':counts},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
