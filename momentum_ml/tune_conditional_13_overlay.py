"""SR-1: pre-registered conditional 13-week overlay on frozen 52-week ranks.

DEV/OOF only. No model, config, signals, or production artifact is modified.
"""
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
import config
from backtest.backtester import MomentumBacktester

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/conditional_13_overlay.json"
N = 15


def feature_panel(features: dict) -> pd.DataFrame:
    rows=[]
    for ticker, frame in features.items():
        cols=[c for c in ("roc_13w","roc_accel_4w") if c in frame]
        x=frame[cols].copy(); x.index.name="Date"; x["ticker"]=ticker; rows.append(x)
    return pd.concat(rows).sort_index()


def make_variant(base: pd.DataFrame, variant: str) -> pd.DataFrame:
    rows=[]
    for _, day in base.groupby(level=0, sort=True):
        d=day.copy()
        d["r52"]=d["selection_rank"].rank(pct=True)
        d["r13"]=d["roc_13w"].rank(pct=True)
        d["accel"]=d["roc_accel_4w"].rank(pct=True)
        if variant == "baseline_52": score=d.r52
        elif variant == "agreement":
            agree=((d.r52-.5)*(d.r13-.5)>0)
            score=d.r52.where(~agree, .8*d.r52+.2*d.r13)
        elif variant == "positive_acceleration":
            use=d.accel>.5
            score=d.r52.where(~use, .8*d.r52+.2*d.r13)
        elif variant == "top_quintile_tiebreak":
            pool=d.r52>=d.r52.quantile(.8)
            score=d.r52.copy(); score.loc[pool]=1+d.loc[pool].r13
        else: raise ValueError(variant)
        eligible=d.selection_eligible.astype(bool) & score.notna()
        chosen=d.loc[eligible].assign(_score=score[eligible]).nlargest(N,"_score")
        chosen_tickers=set(chosen["ticker"])
        d["pred_signal"]=d.ticker.isin(chosen_tickers).astype(int)
        count=max(int(d.pred_signal.sum()),1)
        d["position_size"]=d.pred_signal/count
        rows.append(d[["ticker","pred_signal","position_size"]])
    return pd.concat(rows).sort_index()


def main():
    signals=pd.read_csv(ROOT/"results/signals.csv",
        usecols=["Date","ticker","selection_rank","selection_eligible"],
        parse_dates=["Date"]).set_index("Date").sort_index()
    feats=pd.read_pickle(ROOT/"results/abstention_features.pkl")
    panel=feature_panel(feats)
    base=signals.reset_index().merge(panel.reset_index(),on=["Date","ticker"],how="inner").set_index("Date")
    dates=base.index.unique().sort_values()
    holdout_start=dates[-int(config.HOLDOUT_WEEKS)]
    # Keep the already exposed holdout completely closed for variant selection.
    base=base[base.index<holdout_start]
    prices=pd.read_pickle(ROOT/"results/abstention_price_data.pkl")
    seg=config.SEGMENTS["large"]; config.REBALANCE_WEEKS=seg["rebalance_weeks"]
    config.MAX_POSITIONS=seg["max_positions"]
    variants=("baseline_52","agreement","positive_acceleration","top_quintile_tiebreak")
    part_dir=ROOT/"results/conditional_13_parts"
    if os.environ.get("SR1_AGGREGATE") == "1":
        results={"window":{"end_exclusive":str(holdout_start.date()),"weeks":int(base.index.nunique())},
                 "variants":{v:json.loads((part_dir/f"{v}.json").read_text()) for v in variants}}
        OUT.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps(results,indent=2,ensure_ascii=False)); print(OUT); return
    selected=os.environ.get("SR1_VARIANT")
    run_variants=(selected,) if selected else variants
    results={"window":{"end_exclusive":str(holdout_start.date()),"weeks":int(base.index.nunique())},"variants":{}}
    for variant in run_variants:
        if variant not in variants: raise ValueError(variant)
        sig=make_variant(base,variant); bt=MomentumBacktester(sig,prices); bt.run()
        results["variants"][variant]=bt.statistics()
        part_dir.mkdir(parents=True,exist_ok=True)
        (part_dir/f"{variant}.json").write_text(json.dumps(results["variants"][variant],indent=2))
        print(variant,results["variants"][variant],flush=True)
    if selected: return
    OUT.write_text(json.dumps(results,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print(OUT)

if __name__ == "__main__": main()
