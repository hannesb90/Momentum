"""Final downstream/index gates using saved binary shadow signals."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import config
from research_gates_common import apply_large, validate_large_contract
apply_large()
from features.feature_engineering import FEATURE_COLS
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from tune_abstention_gate import _load_state
from data.data_loader import load_sweden_universe

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"results/binary_shadow_replay.json"

def bt_stats(sig,prices):
    bt=MomentumBacktester(sig,prices); bt.run(); return bt.statistics()

def selected_stats(sig):
    x=sig.groupby(level=0).agg(n=("position_size",lambda s:int((s>0).sum())),
        weight_sum=("position_size","sum"),max_weight=("position_size","max"))
    return {"dates":len(x),"n_median":float(x.n.median()),"n_min":int(x.n.min()),
            "n_max":int(x.n.max()),"weight_sum_median":float(x.weight_sum.median()),
            "max_weight_observed":float(x.max_weight.max())}

def passive_stats(price_frame,dates):
    px=price_frame["Close"].reindex(dates).ffill().dropna()
    cost=float(config.COMMISSION+config.SLIPPAGE)
    nav=(1-cost)*px/px.iloc[0]
    ret=nav.pct_change().dropna(); years=(nav.index[-1]-nav.index[0]).days/365.25
    dd=nav/nav.cummax()-1
    return {"total_return":float(nav.iloc[-1]-1),"CAGR":float(nav.iloc[-1]**(1/years)-1),
            "Sharpe":float(ret.mean()/ret.std()*np.sqrt(52)),"Max Drawdown":float(dd.min()),
            "Weeks":len(nav),"note":"passive buy-and-hold; no stock sector/correlation filters"}

def main():
    features,prices,lgbm,_=_load_state(); cols=list(getattr(lgbm,"feature_cols_",[]) or FEATURE_COLS)
    contract=validate_large_contract(cols)
    _,sectors,caps,names=load_sweden_universe(min_market_cap=config.SEGMENTS["large"]["market_cap"])
    config.SECTOR_MAP.update(sectors);config.CAP_TIER_MAP.update(caps);config.NAME_MAP.update(names)
    binary=pd.read_csv(ROOT/"results/binary_shadow_signals.csv",parse_dates=["Date"]).set_index("Date")
    dates=binary.index.unique().sort_values()
    lp={}
    for t,f in features.items():
        clean=f[f.index.isin(dates)].dropna(subset=cols[:5])
        if len(clean):lp[t]=lgbm.predict(clean)
    fd={t:f.assign(ticker=t) for t,f in features.items()}
    lamb=build_full_output(lp,None,fd,MomentumEnsemble(),record_diagnostics=False)
    production=pd.read_csv(ROOT/"results/signals.csv",parse_dates=["Date"]).set_index("Date")
    common=dates.intersection(lamb.index.unique()).intersection(production.index.unique())
    binary=binary[binary.index.isin(common)];lamb=lamb[lamb.index.isin(common)]
    production=production[production.index.isin(common)]
    bench_ticker=config.INDEX_BENCHMARK_TICKER
    if bench_ticker not in prices: raise RuntimeError(f"Benchmark {bench_ticker} absent from PIT price cache")
    overlap=[]
    for d in common[::int(config.REBALANCE_WEEKS)]:
        b=set(binary.loc[[d]].query("position_size>0").ticker)
        p=set(production.loc[[d]].query("position_size>0").ticker)
        overlap.append(len(b&p)/max(len(b|p),1))
    one_way=float(json.loads((ROOT/"results/binary_shadow_validation.json").read_text())["binary"]["turnover_per_rebalance"])
    report={"status":"PASS","contract":contract,"window":{"start":str(common.min().date()),
        "end":str(common.max().date()),"weeks":len(common)},
        "binary":{"statistics":bt_stats(binary,prices),"selection":selected_stats(binary)},
        "lambdarank_same_path":{"statistics":bt_stats(lamb,prices),"selection":selected_stats(lamb)},
        "saved_production":{"statistics":bt_stats(production,prices),"selection":selected_stats(production)},
        "xact_sverige":{"statistics":passive_stats(prices[bench_ticker],common)},
        "binary_vs_saved_production_top15_jaccard":float(np.mean(overlap)),
        "costs":{"commission":float(config.COMMISSION),"slippage":float(config.SLIPPAGE),
                 "already_applied_in_backtests":True,
                 "binary_estimated_two_way_cost_drag_per_annual_rebalance":one_way*2*(config.COMMISSION+config.SLIPPAGE)}}
    for key in ("binary","lambdarank_same_path","saved_production"):
        s=report[key]["selection"]
        if s["n_max"]>int(config.MAX_POSITIONS) or s["weight_sum_median"]>1.000001: report["status"]="FAIL_PORTFOLIO_CONSTRAINT"
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False,default=str));print(OUT)
    if report["status"]!="PASS":raise SystemExit(1)

if __name__=="__main__":main()
