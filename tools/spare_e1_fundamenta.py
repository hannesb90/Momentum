from __future__ import annotations
import hashlib,json
from pathlib import Path
import pandas as pd
from xgboost import XGBRegressor
from catboost import CatBoostRegressor
from spard_neutral_race import V2,load_data,split_defs,evaluate,dump,sha,manifest_tree,SEED,ic_metrics,portfolio

OUT=V2/"spare/results/SPARE_E1_FUNDAMENTA_DIAGNOSTIC_V1"
LOCK={"core_panel.json":"220e258669b1eed774e533065dec5ed8e5780edc0e31ec4eb3e841c128a1c974","core_fundamenta_panel.json":"117ac6e811ff62ea62168fea2f55a6da430c43774794bed8733573dc4dd1eaaa","target_table.json":"6c2b87aad0e1853837b8d60a3b11e100bca781486b7c12966a27b9a8bd671d21","feature_registry.json":"391a365fd73f981d682ed756deacb94d921f14d61a47628eb16ac1de9eb65f05"}
def model(n):
 if n=="xgboost": return XGBRegressor(n_estimators=300,learning_rate=.03,max_depth=3,min_child_weight=20,subsample=.8,colsample_bytree=.8,reg_lambda=1,objective="reg:squarederror",random_state=SEED,n_jobs=4)
 return CatBoostRegressor(iterations=300,learning_rate=.03,depth=4,l2_leaf_reg=3,loss_function="RMSE",verbose=False,random_seed=SEED,thread_count=4,allow_writing_files=False)
def predict(df,features,tag,flags):
 out=[]
 for s in split_defs(df):
  tr=df[df.panel_date<=s["train_to"]]; ev=df[(df.panel_date>=s["eval_from"])&(df.panel_date<=s["eval_to"])]
  for n in ("catboost","xgboost"):
   m=model(n);m.fit(tr[features],tr.y);z=m.predict(ev[features])
   for (_,r),v in zip(ev.iterrows(),z): out.append({"dataset":tag,"model":n,"split":s["name"],"role":s["role"],"kod":r.kod,"panel_date":r.panel_date,"score":float(v),"target_fwd52w":float(r.y),"has_fundamenta":bool(flags[(r.kod,r.panel_date)])})
 return out
def compact(m):
 i=m["ic"];p=m["portfolio"];return {"mean_ic52":i["mean_ic52"],"median_ic52":i["median_ic52"],"positive_ic_share":i["positive_ic_share"],"mean_top30_ic52":i["mean_top30_ic52"],"cagr":p["cagr"],"sharpe":p["sharpe"],"max_drawdown":p["max_drawdown"],"mean_turnover":p["mean_turnover"],"annualized_excess":p["annualized_excess"],"leave_top3_out_excess":p["leave_top3_out_cagr"]-p["benchmark_cagr"]}
def main():
 paths={"core_panel.json":V2/"panels/core_panel.json","core_fundamenta_panel.json":V2/"panels/core_fundamenta_panel.json","target_table.json":V2/"panels/target_table.json","feature_registry.json":V2/"docs/probes/feature_registry.json"}
 assert {k:sha(v) for k,v in paths.items()}==LOCK
 reg=json.loads(paths["feature_registry.json"].read_text());cf=[x["id"] for x in reg["CORE"] if x.get("status")!="UTESLUTEN" and not x.get("ej_feature")];ff=[x["id"] for x in reg["FUNDAMENTA"] if x.get("status")!="UTESLUTEN" and not x.get("ej_feature")]
 core=load_data("core_panel.json",cf);fund=load_data("core_fundamenta_panel.json",cf+ff);flags={(r.kod,r.panel_date):r.has_fundamenta for _,r in fund.iterrows()};assert set(zip(core.kod,core.panel_date))==set(flags)
 dump(OUT/"split_manifest.json",{"before_fit":True,"splits":split_defs(core),"core_features":cf,"fundamenta_features":ff,"native_missing":True})
 a=predict(core,cf,"CORE",flags);b=predict(fund,cf+ff,"CORE_FUNDAMENTA",flags);dump(OUT/"predictions_core.json",a);dump(OUT/"predictions_core_fundamenta.json",b)
 am=evaluate(a,"CORE");bm=evaluate(b,"CORE_FUNDAMENTA");dump(OUT/"metrics_core.json",am);dump(OUT/"metrics_core_fundamenta.json",bm)
 delta={}
 for n in ("catboost","xgboost"):
  delta[n]={}
  for subset,flt in (("full",lambda r:True),("comparable_has_fundamenta",lambda r:r["has_fundamenta"])):
   ar=[r for r in a if r["model"]==n and r["role"]=="test" and flt(r)];br=[r for r in b if r["model"]==n and r["role"]=="test" and flt(r)]
   aa={"ic":ic_metrics(ar),"portfolio":portfolio(ar)};bb={"ic":ic_metrics(br),"portfolio":portfolio(br)};ca,cb=compact(aa),compact(bb)
   delta[n][subset]={"A":ca,"B":cb,"B_minus_A":{k:cb[k]-ca[k] for k in ca}}
 dump(OUT/"incremental_delta.json",delta);dump(OUT/"manifest.json",manifest_tree(OUT));print(json.dumps({"status":"COMPLETE","output":str(OUT)},indent=2))
if __name__=="__main__":main()
