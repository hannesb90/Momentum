from __future__ import annotations
import json
import pandas as pd
from xgboost import XGBRegressor
from catboost import CatBoostRegressor
from decision_portfolio_v2 import V2,sha,dump,manifest,load_decision,evaluation,splits,ic_metrics,build_portfolio
SEED=20260808;OUT=V2/'repair_df/results/SPARE_CHALLENGERS_V2_PIT'
def model(n):
 if n=='xgboost':return XGBRegressor(n_estimators=300,learning_rate=.03,max_depth=3,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=1,objective='reg:squarederror',random_state=SEED,n_jobs=4)
 return CatBoostRegressor(iterations=300,learning_rate=.03,depth=4,l2_leaf_reg=3,loss_function='RMSE',verbose=False,random_seed=SEED,thread_count=4,allow_writing_files=False)
def predict(dec,features,tag):
 tar=evaluation(dec);out=[]
 for s in splits(dec):
  tr=dec[dec.panel_date<=s['train_to']].merge(tar,on=['kod','panel_date'],how='inner');ev=dec[(dec.panel_date>=s['eval_from'])&(dec.panel_date<=s['eval_to'])]
  for n in ['catboost','xgboost']:
   m=model(n);m.fit(tr[features],tr.y);z=m.predict(ev[features]);out.extend({'dataset':tag,'model':n,'split':s['name'],'role':s['role'],'kod':r.kod,'panel_date':r.panel_date,'score':float(v),'has_fundamenta':None if pd.isna(r.has_fundamenta) else bool(r.has_fundamenta)} for (_,r),v in zip(ev.iterrows(),z))
 return pd.DataFrame(out),tar
def evaluate(pred,tar,tag,arts):
 out={}
 for n in ['catboost','xgboost']:
  t=pred[(pred.model==n)&(pred.role=='test')][['kod','panel_date','score']];ic=ic_metrics(t,tar);pm,a=build_portfolio(t,model=tag+'_'+n)
  for k in arts:arts[k].extend(a[k])
  out[n]={'ic':ic,'portfolio':pm}
 return out
def compact(m):
 i=m['ic'];p=m['portfolio'];return {'mean_ic52':i['mean_ic52'],'median_ic52':i['median_ic52'],'positive_ic_share':i['positive_ic_share'],'mean_top30_ic52':i['mean_topN_ic52'],'cagr':p['cagr_net'],'sharpe':p['sharpe_excess'],'max_drawdown':p['max_drawdown'],'mean_turnover':p['mean_turnover'],'leave_top3_out_excess':p['leave_top3_out_cagr']-p['benchmark_cagr']}
def main():
 reg=json.loads((V2/'docs/probes/feature_registry.json').read_text());cf=[x['id'] for x in reg['CORE'] if x.get('status')!='UTESLUTEN' and not x.get('ej_feature')];ff=[x['id'] for x in reg['FUNDAMENTA'] if x.get('status')!='UTESLUTEN' and not x.get('ej_feature')];arts={'rankings':[],'holdings':[],'trades':[],'returns':[]}
 core=load_decision('core_panel.json',cf);fund=load_decision('core_fundamenta_panel.json',cf+ff);a,tar=predict(core,cf,'E1_CORE');b,_=predict(fund,cf+ff,'E1_CORE_FUND');am=evaluate(a,tar,'E1_CORE',arts);bm=evaluate(b,tar,'E1_CORE_FUND',arts);delta={n:{'A':compact(am[n]),'B':compact(bm[n]),'B_minus_A':{k:compact(bm[n])[k]-compact(am[n])[k] for k in compact(am[n])}} for n in ['catboost','xgboost']};dump(OUT/'E1_metrics_core.json',am);dump(OUT/'E1_metrics_fund.json',bm);dump(OUT/'E1_delta.json',delta);dump(OUT/'E1_predictions_core.json',a.to_dict('records'));dump(OUT/'E1_predictions_fund.json',b.to_dict('records'))
 macro=pd.DataFrame(json.loads((V2/'spare/macro_v1/macro_panel.json').read_text()));mf=[x for x in macro if x!='panel_date'];cm=core.merge(macro,on='panel_date',how='left',validate='many_to_one');ma,tar=predict(core,cf,'E4_CORE');mb,_=predict(cm,cf+mf,'E4_CORE_MACRO');mam=evaluate(ma,tar,'E4_CORE',arts);mbm=evaluate(mb,tar,'E4_CORE_MACRO',arts);mdelta={n:{'A':compact(mam[n]),'B':compact(mbm[n]),'B_minus_A':{k:compact(mbm[n])[k]-compact(mam[n])[k] for k in compact(mam[n])}} for n in ['catboost','xgboost']};dump(OUT/'E4_metrics_core.json',mam);dump(OUT/'E4_metrics_macro.json',mbm);dump(OUT/'E4_delta.json',mdelta);dump(OUT/'E4_predictions_core.json',ma.to_dict('records'));dump(OUT/'E4_predictions_macro.json',mb.to_dict('records'))
 for k,v in arts.items():dump(OUT/(k+'.json'),v)
 dump(OUT/'manifest.json',manifest(OUT));print(json.dumps({'status':'COMPLETE','E1':delta,'E4':mdelta},indent=2))
if __name__=='__main__':main()
