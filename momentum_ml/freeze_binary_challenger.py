"""Freeze raw-score binary shadow model and diagnose the latest five years.

Never overwrites production artifacts. Historical comparison uses the same
25 DEV/OOF splits as the locked tournament and extrapolates each model class's
last split model only after its test window. The latest five years are already
research-exposed and are diagnostic, not a selection holdout.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large, validate_large_contract
apply_large()
from features.feature_engineering import FEATURE_COLS, to_model_df
from models.lgbm_model import walk_forward_splits
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_pointwise

ROOT=Path(__file__).resolve().parents[1]
MODEL_OUT=ROOT/"results/challengers/binary_raw_v1.joblib"
SIGNAL_OUT=ROOT/"results/challengers/binary_raw_v1_shadow_signals.csv"
REPORT_OUT=ROOT/"results/binary_vs_lambdarank_latest_5y.json"

def prediction_panel(features, model_df, cols):
    dates=model_df.index.unique().sort_values(); purge=dates[-(config.HOLDOUT_WEEKS+config.FORWARD_WEEKS)]
    dev=model_df[model_df.index<purge]; splits=walk_forward_splits(dev.index); rows=[]; last=None
    for i,(tr,va,te) in enumerate(splits):
        train=dev[dev.index.isin(tr)].sort_index();val=dev[dev.index.isin(va)].sort_index();test=dev[dev.index.isin(te)].sort_index()
        last=_train_pointwise(train,val,cols,"binary")
        x=test[["ticker"]].copy();x["raw"]=last.predict(test[cols].fillna(0).values);rows.append(x)
        print(f"historical split {i+1}/{len(splits)}",flush=True)
    last_test=max(splits[-1][2]); future=[]
    for ticker,frame in features.items():
        x=frame[frame.index>last_test].dropna(subset=cols[:5]).copy()
        if len(x):
            y=pd.DataFrame({"ticker":ticker,"raw":last.predict(x[cols].fillna(0).values)},index=x.index);future.append(y)
    return pd.concat(rows+future).sort_index(),last_test

def raw_to_preds(panel):
    p=panel.copy();p["prob_up"]=p.groupby(level=0).raw.transform(lambda s:(s-s.min())/(s.max()-s.min()+1e-12) if s.max()>s.min() else .5)
    p["prob_raw"]=p.raw;p["prob_up_calibrated"]=p.raw.clip(.01,.99)
    p["pred_return"]=p.raw-p.groupby(level=0).raw.transform("median");p["pred_signal"]=(p.prob_up>.5).astype(int)
    return {t:g.drop(columns=["ticker","raw"]).sort_index() for t,g in p.groupby("ticker")}

def stats(sig,prices,start):
    x=sig[sig.index>=start];bt=MomentumBacktester(x,prices);bt.run();return bt.statistics()

def passive(frame,dates,start):
    px=frame.Close.reindex(dates).ffill();px=px[px.index>=start].dropna();nav=(1-config.COMMISSION-config.SLIPPAGE)*px/px.iloc[0]
    r=nav.pct_change().dropna();years=(nav.index[-1]-nav.index[0]).days/365.25;dd=nav/nav.cummax()-1
    return {"total_return":float(nav.iloc[-1]-1),"CAGR":float(nav.iloc[-1]**(1/years)-1),
            "Sharpe":float(r.mean()/r.std()*np.sqrt(52)),"Max Drawdown":float(dd.min()),"Weeks":len(nav)}

def main():
    features,prices,lambdarank,_=_load_state();cols=list(getattr(lambdarank,"feature_cols_",[]) or FEATURE_COLS)
    contract=validate_large_contract(cols);_,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    mdf=to_model_df(features);panel,last_test=prediction_panel(features,mdf,cols)
    fd={t:f.assign(ticker=t) for t,f in features.items()};ens=MomentumEnsemble()
    binary=build_full_output(raw_to_preds(panel),None,fd,ens,record_diagnostics=False)
    all_dates=binary.index.unique().sort_values();lp={}
    for t,f in features.items():
        x=f[f.index.isin(all_dates)].dropna(subset=cols[:5])
        if len(x):lp[t]=lambdarank.predict(x)
    lamb=build_full_output(lp,None,fd,ens,record_diagnostics=False)
    production=pd.read_csv(ROOT/"results/signals.csv",parse_dates=["Date"]).set_index("Date")
    common=all_dates.intersection(lamb.index.unique()).intersection(production.index.unique())
    end=common.max();start=end-pd.DateOffset(years=5)
    bench=config.INDEX_BENCHMARK_TICKER

    # Freeze a separate serving challenger on all currently label-complete data.
    label_dates=mdf.index.unique().sort_values();val_dates=label_dates[-26:];train_dates=label_dates[:-26]
    serving=_train_pointwise(mdf[mdf.index.isin(train_dates)],mdf[mdf.index.isin(val_dates)],cols,"binary")
    MODEL_OUT.parent.mkdir(parents=True,exist_ok=True)
    frozen={"model":serving,"feature_cols":cols,"contract":contract,"version":"binary_raw_v1",
            "frozen_at":datetime.now(timezone.utc).isoformat(),"tuning_locked":True,
            "production":False,"selection_holdout":"future observations only"}
    joblib.dump(frozen,MODEL_OUT)
    # Save serving shadow signals; retain full history for rank EMA, publish recent two years only.
    serv=[]
    for t,f in features.items():
        x=f.dropna(subset=cols[:5]);
        if len(x):serv.append(pd.DataFrame({"ticker":t,"raw":serving.predict(x[cols].fillna(0).values)},index=x.index))
    serv_sig=build_full_output(raw_to_preds(pd.concat(serv).sort_index()),None,fd,ens,record_diagnostics=False)
    serv_sig[serv_sig.index>=end-pd.DateOffset(years=2)].to_csv(SIGNAL_OUT)
    report={"status":"PASS","diagnostic_research_exposed":True,"contract":contract,
            "window":{"start":str(start.date()),"end":str(end.date()),"last_oof_test":str(pd.Timestamp(last_test).date())},
            "binary":stats(binary,prices,start),"lambdarank":stats(lamb,prices,start),
            "saved_production":stats(production,prices,start),"xact_sverige":passive(prices[bench],common,start),
            "frozen_model":str(MODEL_OUT),"shadow_signals":str(SIGNAL_OUT)}
    REPORT_OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(REPORT_OUT)

if __name__=="__main__":main()
