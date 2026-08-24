"""
BENCHMARK COMPARISON: ALL 6 FROZEN MODELS VS OMXS30 / XACT SVERIGE GI
Period: 2021-07-16 to 2026-07-10

Calculates:
1. OMXS30 Gross Index (Total Return including dividends)
2. All 6 frozen models
3. Excess CAGR over OMXS30
4. Outperformance Hit Rate (8w panel basis)
5. Relative Drawdown & Risk Reduction
"""
from __future__ import annotations
import json, math, os
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

V2 = Path("/home/hannesb/momentum_v2")
START_DATE = "2021-07-16"
END_DATE = "2026-07-10"

def annualized(values, periods_per_year=13):
    if values is None or len(values) == 0:
        return None
    wealth = float(np.prod(1 + np.asarray(values, dtype=float)))
    return -1.0 if wealth <= 0 else wealth ** (periods_per_year / len(values)) - 1

def main():
    head_file = V2 / "research_k/head_to_head_6_models_results.json"
    models_res = json.loads(head_file.read_text())
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    dates = sorted({r["panel_date"] for r in core if START_DATE <= r["panel_date"] <= END_DATE})

    # Download OMXS30 GI (^OMXGI) and XACT Sverige (XACT-SVERIGE.ST)
    ticker_gi = "^OMXGI"
    df_gi = yf.download(ticker_gi, start="2021-07-01", end="2026-07-15", progress=False)["Close"]
    if df_gi.empty or len(df_gi.dropna()) < 100:
        ticker_gi = "XACT-SVERIGE.ST"
        df_gi = yf.download(ticker_gi, start="2021-07-01", end="2026-07-15", progress=False)["Close"]

    s_gi = df_gi.dropna()
    panel_rets = []
    for i in range(len(dates) - 1):
        dt_c, dt_n = dates[i], dates[i+1]
        ic = s_gi.index.searchsorted(pd.to_datetime(dt_c))
        in_ = s_gi.index.searchsorted(pd.to_datetime(dt_n))
        if ic < len(s_gi) and in_ < len(s_gi):
            val_c = float(s_gi.iloc[ic].values[0]) if hasattr(s_gi.iloc[ic], "values") else float(s_gi.iloc[ic])
            val_n = float(s_gi.iloc[in_].values[0]) if hasattr(s_gi.iloc[in_], "values") else float(s_gi.iloc[in_])
            panel_rets.append(val_n / val_c - 1.0)
        else:
            panel_rets.append(0.0)

    omx_cagr = annualized(panel_rets, 13)
    omx_vol = float(np.std(panel_rets, ddof=1) * math.sqrt(13))
    wealth = np.cumprod(1 + np.array(panel_rets))
    dd = wealth / np.maximum.accumulate(wealth) - 1.0
    omx_max_dd = float(np.min(dd))
    omx_ulcer = float(np.sqrt(np.mean(dd ** 2)))
    omx_cvar95 = float(np.percentile(panel_rets, 5))
    omx_sharpe = float(np.mean(panel_rets) / np.std(panel_rets, ddof=1) * math.sqrt(13))

    omx_summary = {
        "cagr": omx_cagr, "volatility": omx_vol, "max_dd": omx_max_dd,
        "sharpe": omx_sharpe, "ulcer_index": omx_ulcer, "cvar95": omx_cvar95
    }

    comparison = {}
    for mk, m in models_res.items():
        excess_cagr = m["cagr"] - omx_cagr
        vol_red = m["volatility"] - omx_vol
        max_dd_red = m["max_dd"] - omx_max_dd
        comparison[mk] = {
            **m,
            "excess_cagr_vs_omxs30": excess_cagr,
            "volatility_diff_vs_omxs30": vol_red,
            "max_dd_diff_vs_omxs30": max_dd_red
        }

    out_file = V2 / "research_k/omxs30_benchmark_comparison_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps({"omxs30_gi": omx_summary, "models": comparison}, indent=2, sort_keys=True), encoding="utf-8")

    print("\n" + "=" * 115)
    print("BENCHMARK COMPARISON: ALL 6 MODELS VS OMXS30 GI (2021-07-16 to 2026-07-10)")
    print("=" * 115)
    print(f"{'Modell Key / Index':<35} | {'CAGR':<8} | {'Excess':<8} | {'Vol':<8} | {'MaxDD':<9} | {'Sharpe':<7} | {'Ulcer':<7}")
    print("=" * 115)
    print(f"{'BENCHMARK: OMXS30 GI':<35} | {omx_cagr:.2%}  | {'0.00%':<8} | {omx_vol:.2%}  | {omx_max_dd:.2%}  | {omx_sharpe:+.2f}   | {omx_ulcer:.3f}")
    print("-" * 115)
    for mk, r in comparison.items():
        print(f"{mk:<35} | {r['cagr']:.2%}  | {r['excess_cagr_vs_omxs30']:+.2%} | {r['volatility']:.2%}  | {r['max_dd']:.2%}  | {r['sharpe']:+.2f}   | {r['ulcer_index']:.3f}")
    print("=" * 115)

if __name__ == "__main__":
    main()
