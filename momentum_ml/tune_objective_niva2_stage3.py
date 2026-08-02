"""Nivå-2 stage 03: objective-only tournament on frozen 13v target/52v rotation."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large,validate_large_contract
apply_large()
from features.feature_engineering import FEATURE_COLS,to_model_df
from models.lgbm_model import walk_forward_splits
from models.ensemble import MomentumEnsemble,build_full_output
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from tune_abstention_gate import _load_state
from tune_target_horizon_isolated import targets_from_prices,raw_preds
from tune_objective_comparison import (_train_pointwise,_train_lambdarank,
    _train_upper_tail,_two_stage_score,_eval_on_test)
from niva2_stage_control import verify_manifest,freeze_stage

ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/"results/niva2_stages/02_rotation_isolation.json"
OUT=ROOT/"results/objective_niva2_stage3.json";SPLIT_OUT=ROOT/"results/objective_niva2_stage3_splits.csv"
WINNER_SIG=ROOT/"results/niva2_stage3_winner_signals.csv"
NAMES=("binary","regression","lambdarank","upper_tail","two_stage")

def number(s,key):return float(str(s[key]).replace("%",""))
def main():
    parent=verify_manifest(PARENT);features,prices,state,_=_load_state();cols=list(getattr(state,"feature_cols_",[]) or FEATURE_COLS);contract=validate_large_contract(cols)
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"]);config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    base=to_model_df(features).sort_index();base.index.name="Date";t13=targets_from_prices(base,prices,13);t52=targets_from_prices(base,prices,52)
    b=base.reset_index();a=t13.reset_index().rename(columns={"target_return":"ret13","target_signal":"sig13"});z=t52.reset_index().rename(columns={"target_return":"ret52","target_signal":"sig52"})
    common=b.merge(a,on=["Date","ticker"]).merge(z,on=["Date","ticker"]).dropna(subset=["ret13","sig13","ret52","sig52"]).set_index("Date").sort_index()
    common["target_return"]=common.ret13;common["target_signal"]=common.sig13
    dates=common.index.unique().sort_values();purge=dates[-(config.HOLDOUT_WEEKS+52)];dev=common[common.index<purge]
    expected=json.loads((ROOT/"results/target_horizon_isolated.json").read_text())["same_feature_hash"]
    actual=hashlib.sha256(pd.util.hash_pandas_object(dev[cols],index=True).values.tobytes()).hexdigest()
    if actual!=expected:raise RuntimeError("Stage-01 feature panel hash mismatch")
    splits=walk_forward_splits(dev.index,embargo_weeks=52);raw={n:[] for n in NAMES};metrics=[]
    for i,(tr,va,te) in enumerate(splits):
        train=dev[dev.index.isin(tr)].sort_index();val=dev[dev.index.isin(va)].sort_index();test=dev[dev.index.isin(te)].sort_index();X=test[cols].fillna(0).values
        cls=_train_pointwise(train,val,cols,"binary");reg=_train_pointwise(train,val,cols,"regression")
        rank=_train_lambdarank(train,val,cols);upper=_train_upper_tail(train,val,cols)
        scores={"binary":cls.predict(X),"regression":reg.predict(X),"lambdarank":rank.predict(X),"upper_tail":upper.predict(X)}
        scores["two_stage"]=_two_stage_score(test,scores["binary"],scores["regression"])
        for name,score in scores.items():
            x=test[["ticker"]].copy();x["raw"]=score;raw[name].append(x)
            metrics.append({"split":i+1,"objective":name,**_eval_on_test(test,score)})
        print(f"split {i+1}/{len(splits)}",flush=True)
    pd.DataFrame(metrics).to_csv(SPLIT_OUT,index=False)
    fd={t:f.assign(ticker=t) for t,f in features.items()};signals={};stats={};config.REBALANCE_WEEKS=52
    for name in NAMES:
        signals[name]=build_full_output(raw_preds(pd.concat(raw[name]).sort_index()),None,fd,MomentumEnsemble(),record_diagnostics=False)
        bt=MomentumBacktester(signals[name],prices);bt.run();stats[name]=bt.statistics()
    winner=max(NAMES,key=lambda n:(number(stats[n],"CAGR"),float(stats[n]["Sharpe"])))
    signals[winner].to_csv(WINNER_SIG)
    med=pd.DataFrame(metrics).groupby("objective")[["test_ic","test_top_decile_edge","ndcg_at_10"]].median().to_dict("index")
    report={"status":"PASS","parent_stage":parent["manifest_sha256"],"target_weeks":13,"rotation_weeks":52,
            "feature_hash":actual,"same_rows":len(dev),"same_splits":len(splits),"objectives":stats,
            "median_model_metrics":med,"winner":winner,"holdout_used":False,"multiple_arms":len(NAMES)}
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    stage=freeze_stage("03_objective_tournament",[OUT,SPLIT_OUT,WINNER_SIG,Path(__file__).resolve()],
        {"winner":winner,"target_weeks":13,"rotation_weeks":52,"holdout_used":False,"arms":len(NAMES)},parent=PARENT)
    print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(OUT);print(stage)

if __name__=="__main__":main()
