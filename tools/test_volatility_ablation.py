#!/usr/bin/env python3
import sys, json, math, pandas as pd, numpy as np
from pathlib import Path

V2 = Path('/home/hannesb/momentum_v2')
sys.path.insert(0, str(V2 / 'tools'))

import stack_h_motor as S

def run_vol_block_sim(F, vol_cutoff=None, g97p_k=None):
    rankings = F['rankings']
    eval_dates = F['eval_dates']
    returns_map = F['returns_map']
    vol_fn = F['vol_fn']
    sma_fn = F['sma_fn']
    conf_fn = F['conf_fn']
    sched_fn = F['sched_fn']
    
    previous, prev_weights, periods = [], {}, []
    for pi, dt in enumerate(eval_dates):
        scheduled = sched_fn(pi, dt)
        raw = rankings[dt]
        elig = {r['kod'] for r in raw}
        rank_map = {r['kod']: i + 1 for i, r in enumerate(raw)}
        
        if vol_cutoff is not None:
            raw = [r for r in raw if vol_fn(r['kod'], dt) <= vol_cutoff]
            elig = {r['kod'] for r in raw}
            rank_map = {r['kod']: i + 1 for i, r in enumerate(raw)}
            
        if g97p_k is not None:
            if scheduled or not previous:
                keep = [k for k in previous if rank_map.get(k, 999) <= 35 and k in elig] if previous else []
                fill = [r['kod'] for r in raw if r['kod'] not in keep]
                cand = (keep + fill)[:30]
                
                cand_vols = [(vol_fn(k, dt), k) for k in cand]
                cand_vols.sort(key=lambda x: x[0], reverse=True)
                bort = {k for _, k in cand_vols[:g97p_k]}
                
                keep_g = [k for k in cand if k not in bort]
                fill_g = [r['kod'] for r in raw if r['kod'] not in keep_g and r['kod'] not in bort]
                sel0 = (keep_g + fill_g)[:30]
            else:
                sel0 = [k for k in previous if k in elig]
                if len(sel0) < 30:
                    sel0 += [r['kod'] for r in raw if r['kod'] not in sel0][: 30 - len(sel0)]
        else:
            if scheduled or not previous:
                keep = [k for k in previous if rank_map.get(k, 999) <= 35 and k in elig] if previous else []
                fill = [r['kod'] for r in raw if r['kod'] not in keep]
                sel0 = (keep + fill)[:30]
            else:
                sel0 = [k for k in previous if k in elig]
                if len(sel0) < 30:
                    sel0 += [r['kod'] for r in raw if r['kod'] not in sel0][: 30 - len(sel0)]
                    
        sel = [k for k in sel0 if sma_fn(k, dt)]
        n = len(sel)
        vols = np.array([vol_fn(k, dt) for k in sel], dtype=float) if n else np.array([])
        
        if n == 0:
            w = np.array([])
        else:
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            w = inv / np.sum(inv) * (n / 30.0)
            w = w * np.array([1.0 if conf_fn(k, dt) else 0.75 for k in sel])
            w = np.clip(w, 0.01, 0.06)
            w = w / np.sum(w) * (n / 30.0)
            if prev_weights:
                w = np.array([prev_weights.get(k, 0.0) if (abs(w[i] - prev_weights.get(k, 0.0)) < 0.005 and prev_weights.get(k, 0.0) > 0) else w[i] for i, k in enumerate(sel)])
                w = w / np.sum(w) * (n / 30.0)
                
        curr = dict(zip(sel, w))
        if not previous:
            turnover = float(np.sum(w)) if n else 0.0
        else:
            alla = set(prev_weights) | set(curr)
            turnover = sum(abs(curr.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in alla) / 2.0
        rets = np.array([returns_map.get((k, dt), 0.0) for k in sel]) if n else np.array([])
        gross = float(np.sum(w * rets)) if n else 0.0
        periods.append({'net': gross - 0.002 * turnover, 'turnover': turnover, 'n': n})
        previous, prev_weights = sel0, curr
        
    net_rets = np.array([p['net'] for p in periods])
    mean_to = float(np.mean([p['turnover'] for p in periods])) * 13.0
    mean_n = float(np.mean([p['n'] for p in periods]))
    st = S.stat(net_rets)
    st['turnover'] = mean_to
    st['mean_n'] = mean_n
    return st

print("=== PORTFOLIO SIMULATION: HIGH VOLATILITY EXCLUSION RULES ===", flush=True)

for win_name, F in [('2014-2019', S.F19), ('2020-2026', S.F26)]:
    print(f"\n--- FÖNSTER {win_name} ---", flush=True)
    
    h0 = run_vol_block_sim(F, vol_cutoff=None, g97p_k=None)
    g97p = run_vol_block_sim(F, vol_cutoff=None, g97p_k=6)
    vol40 = run_vol_block_sim(F, vol_cutoff=0.40, g97p_k=None)
    vol35 = run_vol_block_sim(F, vol_cutoff=0.35, g97p_k=None)
    
    print(f"  1. Locked H0 Baslinje:          CAGR = {h0['cagr']:6.2%}, Vol = {h0['vol']:6.2%}, MaxDD = {h0['maxdd']:6.2%}, Sharpe = {h0['sharpe']:5.3f}", flush=True)
    print(f"  2. G97-P (Exkludera 6 mest vol): CAGR = {g97p['cagr']:6.2%}, Vol = {g97p['vol']:6.2%}, MaxDD = {g97p['maxdd']:6.2%}, Sharpe = {g97p['sharpe']:5.3f} (Δ CAGR: {g97p['cagr']-h0['cagr']:+.2%})", flush=True)
    print(f"  3. Absolut spärr (Vol > 40%):    CAGR = {vol40['cagr']:6.2%}, Vol = {vol40['vol']:6.2%}, MaxDD = {vol40['maxdd']:6.2%}, Sharpe = {vol40['sharpe']:5.3f} (Δ CAGR: {vol40['cagr']-h0['cagr']:+.2%})", flush=True)
    print(f"  4. Absolut spärr (Vol > 35%):    CAGR = {vol35['cagr']:6.2%}, Vol = {vol35['vol']:6.2%}, MaxDD = {vol35['maxdd']:6.2%}, Sharpe = {vol35['sharpe']:5.3f} (Δ CAGR: {vol35['cagr']-h0['cagr']:+.2%})", flush=True)
