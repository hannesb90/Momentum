from __future__ import annotations
import json,sys
from pathlib import Path
import pandas as pd
from decision_portfolio_v2 import V2,sha,dump,manifest,load_decision,evaluation,splits,ic_metrics
from decision_portfolio_v3_execution import build_portfolio
from spard_neutral_race import models

OUT=V2/'repair_df/results/SPARD_CORE_NEUTRAL_RACE_V3_EXECUTION_PIT'; OLD=V2/'spard/results/SPARD_CORE_NEUTRAL_RACE_V1'; NAMES=['ridge','elasticnet','lightgbm','xgboost','catboost']
LOCK={'core_panel.json':'220e258669b1eed774e533065dec5ed8e5780edc0e31ec4eb3e841c128a1c974','target_table.json':'6c2b87aad0e1853837b8d60a3b11e100bca781486b7c12966a27b9a8bd671d21','feature_registry.json':'391a365fd73f981d682ed756deacb94d921f14d61a47628eb16ac1de9eb65f05'}
def main():
 assert sha(V2/'panels/core_panel.json')==LOCK['core_panel.json'];assert sha(V2/'panels/target_table.json')==LOCK['target_table.json'];assert sha(V2/'docs/probes/feature_registry.json')==LOCK['feature_registry.json']
 reg=json.loads((V2/'docs/probes/feature_registry.json').read_text());features=[r['id'] for r in reg['CORE'] if r.get('status')!='UTESLUTEN' and not r.get('ej_feature')];assert len(features)==29
 dec=load_decision('core_panel.json',features);tar=evaluation(dec);sp=splits(dec);dump(OUT/'split_manifest.json',{'decision_universe_rows':len(dec),'evaluation_rows':len(tar),'splits':sp,'features':features,'original_preregistration_sha256':sha(V2/'spard/core_race_preregistration.json')})
 predictions=[];all_art={'rankings':[],'holdings':[],'trades':[],'returns':[]};metrics={}
 for name in NAMES:
  score_parts=[]
  for s in sp:
   train=dec[dec.panel_date<=s['train_to']].merge(tar,on=['kod','panel_date'],how='inner');ev=dec[(dec.panel_date>=s['eval_from'])&(dec.panel_date<=s['eval_to'])].copy();m=models(name);m.fit(train[features],train.y);ev['score']=m.predict(ev[features]);ev['model']=name;ev['split']=s['name'];ev['role']=s['role'];score_parts.append(ev[['kod','panel_date','score','model','split','role']])
  scores=pd.concat(score_parts,ignore_index=True);predictions.extend(scores.to_dict('records'));test=scores[scores.role=='test'][['kod','panel_date','score']];ic=ic_metrics(test,tar,n=30);pm,art=build_portfolio(test,n=30,every=1,cost=.002,model=name);metrics[name]={'test':{'ic':ic,'portfolio':pm}}
  for k in all_art:all_art[k].extend(art[k])
 # Exact original baseline formula, now ranked on the full decision universe.
 parts=[]
 for s in sp:
  ev=dec[(dec.panel_date>=s['eval_from'])&(dec.panel_date<=s['eval_to'])].copy();med=ev.groupby('panel_date').mom_52w.transform('median');ev['score']=ev.mom_52w.fillna(med);ev['model']='momentum_52w';ev['split']=s['name'];ev['role']=s['role'];parts.append(ev[['kod','panel_date','score','model','split','role']])
 scores=pd.concat(parts,ignore_index=True);predictions.extend(scores.to_dict('records'));test=scores[scores.role=='test'][['kod','panel_date','score']];ic=ic_metrics(test,tar,n=30);pm,art=build_portfolio(test,n=30,every=1,cost=.002,model='momentum_52w');metrics['momentum_52w']={'test':{'ic':ic,'portfolio':pm}}
 for k in all_art:all_art[k].extend(art[k])
 dump(OUT/'predictions.json',predictions);dump(OUT/'metrics.json',metrics)
 for k,v in all_art.items():dump(OUT/(k+'.json'),v)
 dump(OUT/'manifest.json',manifest(OUT));print(json.dumps({'status':'COMPLETE','decision_rows':len(dec),'evaluation_rows':len(tar),'output':str(OUT)},indent=2))
if __name__=='__main__':main()
