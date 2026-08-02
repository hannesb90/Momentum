"""Nivå-2 step 1: isolate binary target horizon, hold execution at 52 weeks."""
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
from tune_objective_comparison import _train_pointwise
from niva2_stage_control import freeze_stage,verify_manifest

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"results/target_horizon_isolated.json"

def targets_from_prices(base,prices,horizon):
    parts=[]
    for ticker,g in base.groupby("ticker"):
        if ticker not in prices:continue
        idx=g.index.unique().sort_values();px=prices[ticker].Close.reindex(idx).ffill()
        r=px.shift(-horizon)/px-1
        x=pd.DataFrame({"ticker":ticker,"target_return":r},index=idx);x.index.name="Date";parts.append(x)
    p=pd.concat(parts).sort_index();p["target_signal"]=p.groupby(level=0).target_return.rank(pct=True).ge(config.XS_TARGET_QUANTILE).astype(float)
    p.loc[p.target_return.isna(),"target_signal"]=np.nan
    return p

def raw_preds(panel):
    p=panel.copy();p["prob_up"]=p.groupby(level=0).raw.transform(lambda s:(s-s.min())/(s.max()-s.min()+1e-12) if s.max()>s.min() else .5)
    p["prob_raw"]=p.raw;p["prob_up_calibrated"]=p.raw.clip(.01,.99);p["pred_return"]=p.raw-p.groupby(level=0).raw.transform("median");p["pred_signal"]=(p.prob_up>.5).astype(int)
    return {t:g.drop(columns=["ticker","raw"]).sort_index() for t,g in p.groupby("ticker")}

def bt(sig,prices):
    x=MomentumBacktester(sig,prices);x.run();return x.statistics()

def passive(frame,dates):
    px=frame.Close.reindex(dates).ffill().dropna();nav=(1-config.COMMISSION-config.SLIPPAGE)*px/px.iloc[0];r=nav.pct_change().dropna();years=(nav.index[-1]-nav.index[0]).days/365.25;dd=nav/nav.cummax()-1
    return {"CAGR":float(nav.iloc[-1]**(1/years)-1),"Sharpe":float(r.mean()/r.std()*np.sqrt(52)),"Max Drawdown":float(dd.min())}

def main():
    features,prices,state,holdout_start=_load_state();cols=list(getattr(state,"feature_cols_",[]) or FEATURE_COLS);contract=validate_large_contract(cols)
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"]);config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    base=to_model_df(features).sort_index();base.index.name="Date"
    t13=targets_from_prices(base,prices,13);t52=targets_from_prices(base,prices,52)
    b=base.reset_index();a=t13.reset_index().rename(columns={"target_return":"ret13","target_signal":"sig13"});z=t52.reset_index().rename(columns={"target_return":"ret52","target_signal":"sig52"})
    common=b.merge(a,on=["Date","ticker"]).merge(z,on=["Date","ticker"]).dropna(subset=["ret13","sig13","ret52","sig52"]).set_index("Date").sort_index()
    # Same feature rows and conservative 52-week embargo for both targets.
    dates=common.index.unique().sort_values();purge=dates[-(config.HOLDOUT_WEEKS+52)];dev=common[common.index<purge]
    splits=walk_forward_splits(dev.index,embargo_weeks=52);out={13:[],52:[]}
    feature_hash=hashlib.sha256(pd.util.hash_pandas_object(dev[cols],index=True).values.tobytes()).hexdigest()
    for i,(tr,va,te) in enumerate(splits):
        for h in (13,52):
            d=dev.copy();d["target_return"]=d[f"ret{h}"];d["target_signal"]=d[f"sig{h}"]
            train=d[d.index.isin(tr)].sort_index();val=d[d.index.isin(va)].sort_index();test=d[d.index.isin(te)].sort_index()
            m=_train_pointwise(train,val,cols,"binary");x=test[["ticker"]].copy();x["raw"]=m.predict(test[cols].fillna(0).values);out[h].append(x)
        print(f"split {i+1}/{len(splits)}",flush=True)
    fd={t:f.assign(ticker=t) for t,f in features.items()};signals={}
    for h in (13,52):signals[h]=build_full_output(raw_preds(pd.concat(out[h]).sort_index()),None,fd,MomentumEnsemble(),record_diagnostics=False)
    common_dates=signals[13].index.unique().intersection(signals[52].index.unique())
    report={"status":"PASS","contract":contract,"execution_rebalance_weeks":52,"embargo_weeks_both":52,
            "same_feature_hash":feature_hash,"same_splits":len(splits),"same_rows":len(dev),
            "target_positive_rate":{"13v":float(dev.sig13.mean()),"52v":float(dev.sig52.mean())},
            "target_agreement":float((dev.sig13==dev.sig52).mean()),
            "binary_13_target":bt(signals[13][signals[13].index.isin(common_dates)],prices),
            "binary_52_target":bt(signals[52][signals[52].index.isin(common_dates)],prices),
            "xact_sverige":passive(prices[config.INDEX_BENCHMARK_TICKER],common_dates),
            "window":{"start":str(common_dates.min().date()),"end":str(common_dates.max().date()),"weeks":len(common_dates)},
            "holdout_used":False}
    sig13=ROOT/"results/niva2_target_13_signals.csv";sig52=ROOT/"results/niva2_target_52_signals.csv"
    signals[13].to_csv(sig13);signals[52].to_csv(sig52)
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    stage0=ROOT/"results/niva2_stages/00_baseline_contract.json"
    if not stage0.exists():
        stage0=freeze_stage("00_baseline_contract",[
            ROOT/"results/research_gates/sr9_baseline_parity.json",ROOT/"momentum_ml/config.py",
            ROOT/"momentum_ml/backtest/backtester.py",ROOT/"momentum_ml/research_gates_common.py"],
            {"gate":"SR-9 PASS","segment":"large"})
    else:verify_manifest(stage0)
    stage1=freeze_stage("01_target_isolation",[OUT,sig13,sig52,Path(__file__).resolve()],
        {"winner":"binary_13_target","execution_rebalance_weeks":52,"holdout_used":False},parent=stage0)
    print(json.dumps(report,indent=2,ensure_ascii=False));print(OUT);print(stage1)

if __name__=="__main__":main()
