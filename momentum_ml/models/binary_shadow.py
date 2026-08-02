"""Frozen binary challenger inference and append-only paper journal."""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import config
from models.ensemble import MomentumEnsemble, build_full_output

def run_binary_shadow(model_features:dict, results_dir:str, start_date=None)->pd.DataFrame|None:
    model_path=Path(results_dir)/"challengers/binary_raw_v1.joblib"
    # Large research workspace stores challenger under root results.
    if not model_path.exists(): model_path=Path("results/challengers/binary_raw_v1.joblib")
    if not model_path.exists(): return None
    frozen=joblib.load(model_path)
    if frozen.get("production") is not False or frozen.get("tuning_locked") is not True:
        raise RuntimeError("Binary shadow artifact lacks frozen non-production contract")
    model=frozen["model"];cols=frozen["feature_cols"];rows=[]
    for ticker,frame in model_features.items():
        x=frame.dropna(subset=cols[:5])
        if start_date is not None: x=x[x.index>=start_date]
        if len(x): rows.append(pd.DataFrame({"ticker":ticker,"raw":model.predict(x[cols].fillna(0).values)},index=x.index))
    if not rows:return None
    p=pd.concat(rows).sort_index();p["prob_up"]=p.groupby(level=0).raw.transform(
        lambda s:(s-s.min())/(s.max()-s.min()+1e-12) if s.max()>s.min() else .5)
    p["prob_raw"]=p.raw;p["prob_up_calibrated"]=p.raw.clip(.01,.99)
    p["pred_return"]=p.raw-p.groupby(level=0).raw.transform("median");p["pred_signal"]=(p.prob_up>.5).astype(int)
    preds={t:g.drop(columns=["ticker","raw"]).sort_index() for t,g in p.groupby("ticker")}
    fd={t:f.assign(ticker=t) for t,f in model_features.items()}
    sig=build_full_output(preds,None,fd,MomentumEnsemble(),record_diagnostics=False)
    out_dir=Path(results_dir)/"challengers";out_dir.mkdir(parents=True,exist_ok=True)
    sig.to_csv(out_dir/"binary_raw_v1_shadow_signals.csv")
    latest=sig.index.max();top=sig.loc[[latest]].query("position_size>0").sort_values("position_size",ascending=False)
    record={"date":str(latest.date()),"model":"binary_raw_v1","production":False,
            "tickers":top.ticker.tolist(),"weights":[float(x) for x in top.position_size],
            "score_unique":int(sig.loc[[latest],"prob_raw"].nunique())}
    ledger=out_dir/"binary_raw_v1_paper_ledger.jsonl"
    existing_dates=set()
    if ledger.exists():
        existing_dates={json.loads(line)["date"] for line in ledger.read_text().splitlines() if line.strip()}
    if record["date"] not in existing_dates:
        with ledger.open("a",encoding="utf-8") as f:f.write(json.dumps(record,ensure_ascii=False)+"\n")
    return sig
