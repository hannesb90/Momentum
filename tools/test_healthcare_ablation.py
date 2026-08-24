#!/usr/bin/env python3
import sys, json, math, pandas as pd, numpy as np
from pathlib import Path

V2 = Path('/home/hannesb/momentum_v2')
sys.path.insert(0, str(V2 / 'tools'))

import stack_h_motor as S

sec_data = json.loads((V2 / 'research_k/sector_classification_v1/validated/sector_classification_intervals.json').read_text(encoding='utf-8'))
sec_map = {x['instrument_id']: x['canonical_sector'] for x in sec_data}

def run_sim(F, blocked_sector=None):
    rankings = F['rankings']
    eval_dates = F['eval_dates']
    returns_map = F['returns_map']
    vol_fn = F['vol_fn']
    sma_fn = F['sma_fn']
    conf_fn = F['conf_fn']
    sched_fn = F['sched_fn']
    
    if blocked_sector:
        filtered_rankings = {}
        for dt, raw in rankings.items():
            filtered_rankings[dt] = [r for r in raw if sec_map.get(r['kod']) != blocked_sector]
    else:
        filtered_rankings = rankings
        
    net_rets, mean_to, mean_n = S.kor(filtered_rankings, eval_dates, returns_map, vol_fn, sma_fn, conf_fn, sched_fn)
    st = S.stat(net_rets)
    st['turnover'] = mean_to
    st['mean_n'] = mean_n
    return st

print("=== HEALTHCARE ABLATION TEST (LOCKED H0 PORTFOLIO) ===", flush=True)

# 2014-2019
h0_1419_base = run_sim(S.F19, None)
h0_1419_no_health = run_sim(S.F19, 'Hälsovård')

print("\n--- Fönster 2014-2019 ---", flush=True)
print(f"Baslinje (Alla sektorer): CAGR = {h0_1419_base['cagr']:6.2%}, Vol = {h0_1419_base['vol']:6.2%}, MaxDD = {h0_1419_base['maxdd']:6.2%}, Sharpe = {h0_1419_base['sharpe']:5.3f}", flush=True)
print(f"Blockerad Hälsovård:      CAGR = {h0_1419_no_health['cagr']:6.2%}, Vol = {h0_1419_no_health['vol']:6.2%}, MaxDD = {h0_1419_no_health['maxdd']:6.2%}, Sharpe = {h0_1419_no_health['sharpe']:5.3f}", flush=True)
print(f"Effekt på CAGR:           {h0_1419_no_health['cagr'] - h0_1419_base['cagr']:+.2%}", flush=True)

# 2020-2026
h0_2026_base = run_sim(S.F26, None)
h0_2026_no_health = run_sim(S.F26, 'Hälsovård')

print("\n--- Fönster 2020-2026 ---", flush=True)
print(f"Baslinje (Alla sektorer): CAGR = {h0_2026_base['cagr']:6.2%}, Vol = {h0_2026_base['vol']:6.2%}, MaxDD = {h0_2026_base['maxdd']:6.2%}, Sharpe = {h0_2026_base['sharpe']:5.3f}", flush=True)
print(f"Blockerad Hälsovård:      CAGR = {h0_2026_no_health['cagr']:6.2%}, Vol = {h0_2026_no_health['vol']:6.2%}, MaxDD = {h0_2026_no_health['maxdd']:6.2%}, Sharpe = {h0_2026_no_health['sharpe']:5.3f}", flush=True)
print(f"Effekt på CAGR:           {h0_2026_no_health['cagr'] - h0_2026_base['cagr']:+.2%}", flush=True)
