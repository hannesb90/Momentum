"""Fail-closed end-to-end shadow validation of raw-score binary vs LambdaRank.

Research artifacts only. Trains OOF binary models, then sends both model classes
through the same current ensemble/output/sizing/backtest path without LSTM.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large, validate_large_contract
apply_large()
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_pointwise

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/binary_shadow_validation.json"


def resolution(frame:pd.DataFrame,col:str)->dict:
    g=frame.groupby(level=0)[col]
    unique=g.nunique(); plateau=g.apply(lambda s:s.value_counts(dropna=False).max()/len(s))
    return {"median_unique":float(unique.median()),"min_unique":int(unique.min()),
            "median_largest_plateau":float(plateau.median()),"max_largest_plateau":float(plateau.max())}


def preds_from_panel(panel:pd.DataFrame)->dict:
    panel=panel.copy()
    panel["prob_up"]=panel.groupby(level=0).raw.transform(
        lambda s:(s-s.min())/(s.max()-s.min()+1e-12) if s.max()>s.min() else .5)
    panel["prob_raw"]=panel.raw
    panel["prob_up_calibrated"]=panel.raw.clip(.01,.99)
    panel["pred_return"]=panel.raw-panel.groupby(level=0).raw.transform("median")
    panel["pred_signal"]=(panel.prob_up>.5).astype(int)
    return {t:g.drop(columns=["ticker","raw"]).sort_index() for t,g in panel.groupby("ticker")}


def turnover(signals:pd.DataFrame)->float:
    dates=signals.index.unique().sort_values()[::int(config.REBALANCE_WEEKS)]
    sets=[]
    for d in dates:
        x=signals.loc[[d]]; sets.append(set(x.loc[x.position_size>0,"ticker"]))
    changes=[len(b-a)/max(len(a),1) for a,b in zip(sets,sets[1:])]
    return float(np.mean(changes)) if changes else float("nan")


def stats(signals,prices,cutoff):
    bt=MomentumBacktester(signals,prices); bt.run()
    return {"dev":bt.statistics_for_period(end=cutoff),
            "turnover_per_rebalance":turnover(signals)}


def main():
    features,prices,lambdarank,holdout_start=_load_state()
    cols=list(getattr(lambdarank,"feature_cols_",[]) or FEATURE_COLS)
    contract=validate_large_contract(cols)
    tickers,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)
    model_df=to_model_df(features); dates=model_df.index.unique().sort_values()
    purge=dates[-(int(config.HOLDOUT_WEEKS)+int(config.FORWARD_WEEKS))]
    dev=model_df[model_df.index<purge]; splits=walk_forward_splits(dev.index)
    rows=[]
    for i,(tr,va,te) in enumerate(splits):
        train=dev[dev.index.isin(tr)].sort_index(); val=dev[dev.index.isin(va)].sort_index()
        test=dev[dev.index.isin(te)].sort_index()
        model=_train_pointwise(train,val,cols,"binary")
        raw=model.predict(test[cols].fillna(0).values)
        x=test[["ticker"]].copy(); x["raw"]=raw; rows.append(x)
        print(f"split {i+1}/{len(splits)}",flush=True)
    binary_panel=pd.concat(rows).sort_index()
    binary_preds=preds_from_panel(binary_panel)
    common_dates=binary_panel.index.unique().sort_values()
    lambda_preds={}
    for ticker,feat in features.items():
        clean=feat[feat.index.isin(common_dates)].dropna(subset=cols[:5])
        if len(clean): lambda_preds[ticker]=lambdarank.predict(clean)
    feature_dfs={t:f.assign(ticker=t) for t,f in features.items()}
    ensemble=MomentumEnsemble()
    binary_signals=build_full_output(binary_preds,None,feature_dfs,ensemble,record_diagnostics=False)
    lambda_signals=build_full_output(lambda_preds,None,feature_dfs,ensemble,record_diagnostics=False)
    common=binary_signals.index.unique().intersection(lambda_signals.index.unique())
    binary_signals=binary_signals[binary_signals.index.isin(common)]
    lambda_signals=lambda_signals[lambda_signals.index.isin(common)]
    overlap=[]
    for d in common[::int(config.REBALANCE_WEEKS)]:
        b=set(binary_signals.loc[[d]].query("position_size>0").ticker)
        l=set(lambda_signals.loc[[d]].query("position_size>0").ticker)
        overlap.append(len(b&l)/max(len(b|l),1))
    report={"status":"PASS","contract":contract,"split_count":len(splits),
            "holdout_used_for_training_or_selection":False,
            "raw_resolution":resolution(binary_panel,"raw"),
            "normalized_resolution":resolution(pd.concat(binary_preds.values()),"prob_up"),
            "binary":stats(binary_signals,prices,holdout_start),
            "lambdarank":stats(lambda_signals,prices,holdout_start),
            "mean_top15_jaccard":float(np.mean(overlap)),"rebalance_observations":len(overlap)}
    # Hard gates: no score collapse and exactly N holdings on scheduled dates when eligible.
    if report["raw_resolution"]["median_unique"]<20 or report["raw_resolution"]["median_largest_plateau"]>.10:
        report["status"]="FAIL_SCORE_COLLAPSE"
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    binary_signals.to_csv(ROOT/"results/binary_shadow_signals.csv")
    print(json.dumps(report,indent=2,ensure_ascii=False,default=str)); print(OUT)
    if report["status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
