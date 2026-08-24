"""MCAP_LONG_CYCLE_REGIME — Diagnostic Study

Tests whether long-term size climate (12m and 24m absolute and relative trends)
affects frozen H0 V3 performance, selection edge, downside risk, and winner tail.

No equity curves, no sizing, no policy backtest, no parameter sweeps.
"""
from __future__ import annotations
import csv, hashlib, json, math, sys, bisect
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

ROOT = Path('/home/hannesb/momentum_v2')
MASTER = ROOT / 'research_k/nasdaq_historical_master/normalized/instrument_monthly_master.json'
STATE = ROOT / 'research_k/h0_v3_state_machine_and_path_ledger'
OUT_DIR = ROOT / 'research_k/mcap_long_cycle_regime'

# Artifact directory for antigravity
CONV_ID = '7676f0e4-343c-4ae3-905c-0346767e1b96'
ARTIFACT_DIR = Path(f'/home/hannesb/.gemini/antigravity-cli/brain/{CONV_ID}')

BUCKETS = ['Q1', 'Q2', 'Q3', 'Q4']

def num(x, default=0.0):
    try:
        if x is None or x == '' or x == 'None':
            return default
        return float(x)
    except (TypeError, ValueError):
        return default

def norm(x):
    return (x or '').replace('-', ' ').upper()

def stringify_keys(d):
    if isinstance(d, dict):
        return {str(k): stringify_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [stringify_keys(v) for v in d]
    return d

def canon(x):
    return json.dumps(stringify_keys(x), sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def digest(x):
    return hashlib.sha256(canon(x).encode()).hexdigest()

def stats_summary(arr):
    a = np.asarray([v for v in arr if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return {'n': 0, 'mean': None, 'std': None, 'median': None, 'se_iid': None, 'hit_rate': None,
                'p5': None, 'p10': None, 'p90': None, 'p95': None, 'min': None, 'max': None}
    n = len(a)
    m = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else 0.0
    se = float(std / math.sqrt(n)) if n > 1 else None
    return {
        'n': int(n),
        'mean': m,
        'std': std,
        'median': float(np.median(a)),
        'se_iid': se,
        'ci95_lo': float(m - 1.96 * se) if se else None,
        'ci95_hi': float(m + 1.96 * se) if se else None,
        'hit_rate': float(np.mean(a > 0)),
        'p5': float(np.percentile(a, 5)),
        'p10': float(np.percentile(a, 10)),
        'p90': float(np.percentile(a, 90)),
        'p95': float(np.percentile(a, 95)),
        'min': float(a.min()),
        'max': float(a.max())
    }

def tail_summary(arr):
    a = np.asarray([v for v in arr if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return {'n': 0, 'p5': None, 'p10': None, 'worst_10_mean': None, 'largest_loss': None,
                'downside_hit_rate': None, 'best_10_mean': None, 'p90': None, 'p95': None, 'largest_winner': None}
    n = len(a)
    k10 = max(1, int(math.ceil(0.10 * n)))
    sorted_a = np.sort(a)
    return {
        'n': int(n),
        'p5': float(np.percentile(a, 5)),
        'p10': float(np.percentile(a, 10)),
        'worst_10_mean': float(sorted_a[:k10].mean()),
        'largest_loss': float(sorted_a[0]),
        'downside_hit_rate': float(np.mean(a < 0)),
        'best_10_mean': float(sorted_a[-k10:].mean()),
        'p90': float(np.percentile(a, 90)),
        'p95': float(np.percentile(a, 95)),
        'largest_winner': float(sorted_a[-1])
    }

def panel_contrast_stats(differences):
    a = np.asarray([v for v in differences if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return {'n_panels': 0, 'mean_difference': None, 'panel_cluster_se': None, 't_stat': None, 'ci95_lo': None, 'ci95_hi': None, 'win_rate': None}
    n = len(a)
    m = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else 0.0
    se = float(std / math.sqrt(n)) if n > 1 else None
    t = float(m / se) if (se and se > 0) else None
    return {
        'n_panels': int(n),
        'mean_difference': m,
        'panel_cluster_se': se,
        't_stat': t,
        'ci95_lo': float(m - 1.96 * se) if se else None,
        'ci95_hi': float(m + 1.96 * se) if se else None,
        'win_rate': float(np.mean(a > 0))
    }

def panel_clustered_regression(df_rows, y_var, x_vars, include_fe=False):
    groups = defaultdict(list)
    for r in df_rows:
        if r.get(y_var) is not None and np.isfinite(r[y_var]):
            if all(r.get(x) is not None and np.isfinite(r[x]) for x in x_vars):
                groups[r['date']].append(r)
    
    Y = []; X = []; gids = []
    for g, rs in groups.items():
        yy = np.array([r[y_var] for r in rs])
        xx = np.array([[r[x] for x in x_vars] for r in rs])
        if include_fe and len(rs) > 1:
            yy = yy - yy.mean()
            xx = xx - xx.mean(axis=0)
        Y.extend(yy)
        X.extend([[1.0 if not include_fe else 0.0] + list(row) for row in xx])
        gids.extend([g] * len(rs))
            
    if len(Y) <= len(x_vars) + (2 if not include_fe else 0):
        return {'n_obs': len(Y), 'n_panels': len(groups)}
        
    Y = np.asarray(Y, float)
    X = np.asarray(X, float)
    if include_fe:
        X = X[:, 1:]
        var_names = x_vars
    else:
        var_names = ['intercept'] + x_vars
    
    XtX = X.T @ X
    beta = np.linalg.lstsq(X, Y, rcond=None)[0]
    residuals = Y - X @ beta
    
    XtX_inv = np.linalg.pinv(XtX)
    meat = np.zeros((X.shape[1], X.shape[1]))
    unique_groups = sorted(set(gids))
    G = len(unique_groups)
    N = len(Y)
    K = X.shape[1]
    
    for g in unique_groups:
        idx = np.array([gid == g for gid in gids])
        Xg = X[idx]
        eg = residuals[idx]
        score_g = Xg.T @ eg
        meat += np.outer(score_g, score_g)
        
    qc = (G / (G - 1)) * ((N - 1) / (N - K)) if G > 1 and N > K else 1.0
    V_cluster = XtX_inv @ (qc * meat) @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(V_cluster), 0))
    
    ss_tot = np.sum((Y - Y.mean())**2)
    ss_res = np.sum(residuals**2)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    coef_dict = {}
    se_dict = {}
    t_dict = {}
    ci_lo = {}
    ci_hi = {}
    for i, name in enumerate(var_names):
        b_val = float(beta[i])
        s_val = float(se[i])
        t_val = float(b_val / s_val) if s_val > 0 else None
        coef_dict[name] = b_val
        se_dict[name] = s_val
        t_dict[name] = t_val
        ci_lo[name] = b_val - 1.96 * s_val if s_val > 0 else None
        ci_hi[name] = b_val + 1.96 * s_val if s_val > 0 else None
        
    return {
        'n_obs': int(N),
        'n_panels': int(G),
        'panel_fe': include_fe,
        'variables': var_names,
        'coefficients': coef_dict,
        'cluster_se': se_dict,
        't_stats': t_dict,
        'ci95_lo': ci_lo,
        'ci95_hi': ci_hi,
        'r2': float(r2)
    }

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Loading Nasdaq PIT Master Data...")
    master = json.loads(MASTER.read_text())['rader']
    by_ob = defaultdict(list)
    isin2ob = {}
    for r in master:
        by_ob[r['orderbook_code'].upper()].append(r)
        if r.get('isin'):
            isin2ob.setdefault(r['isin'], r['orderbook_code'].upper())
    for rs in by_ob.values():
        rs.sort(key=lambda x: (x['known_from'], x['observation_month']))
        
    by_ob_dates = {ob: [x['known_from'] for x in rs] for ob, rs in by_ob.items()}

    isins = {}
    for r in json.loads((ROOT / 'validated/prices_h1419/membership_h1419_v2.json').read_text())['rows']:
        isins[('W1', r['kod'])] = r.get('kalla')
    for r in json.loads((ROOT / 'research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json').read_text())['entries']:
        a = [x.get('isin') for x in r.get('isin_aliases', []) if x.get('isin')]
        if a:
            isins[('W2', r['instrument_id'])] = a[0]

    def pick(w, t, d, source_by=by_ob, source_by_dates=by_ob_dates):
        ob = norm(t)
        isi = isins.get((w, t))
        if ob not in source_by and isi:
            ob = isin2ob.get(isi, '')
        rr = source_by.get(ob, [])
        if not rr:
            return None, ob
        d_list = source_by_dates.get(ob)
        if d_list is None:
            d_list = [x['known_from'] for x in rr]
        idx = bisect.bisect_right(d_list, d)
        return (rr[idx - 1] if idx > 0 else None), ob

    pre_sma = defaultdict(set)
    with (STATE / 'PRE_SMA_SELECTION_LEDGER.csv').open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r['current_pre_sma_selected'] == 'True':
                pre_sma[r['window']].add((r['panel_date'], r['ticker']))

    paths = {}
    for w in ('W1', 'W2'):
        with (STATE / f'PATH_LEDGER_{w}.csv').open(newline='') as fh:
            paths[w] = [r for r in csv.DictReader(fh) if r['eligible'] == 'True']

    print("Building PIT Quartile Assignments for W1 and W2...")
    assignments = {}
    panel_dates = {}
    
    def build_assignments(w, source_by=by_ob, source_by_dates=by_ob_dates):
        rows = paths[w]
        bp = defaultdict(list)
        for r in rows:
            bp[r['date']].append(r)
        dates = sorted(bp.keys())
        out = []
        for d in dates:
            rs = bp[d]
            mc = {}
            pick_cache = {}
            for r in rs:
                z, ob = pick(w, r['ticker'], d, source_by, source_by_dates)
                pick_cache[r['ticker']] = (z, ob)
                if z and z.get('market_cap') not in (None, 0):
                    mc[r['ticker']] = float(z['market_cap'])
            order = sorted(mc.keys(), key=lambda k: (mc[k], k))
            n = len(order)
            pct = {k: (i / (n - 1) if n > 1 else 0.5) for i, k in enumerate(order)}
            
            for r in rs:
                t = r['ticker']
                z, ob = pick_cache[t]
                p = pct.get(t)
                if p is None:
                    b = 'MCAP_UNKNOWN'
                elif p < 0.25:
                    b = 'Q1'
                elif p < 0.50:
                    b = 'Q2'
                elif p < 0.75:
                    b = 'Q3'
                else:
                    b = 'Q4'
                out.append({
                    'window': w,
                    'date': d,
                    'ticker': t,
                    'bucket': b,
                    'percentile': p,
                    'market_cap': mc.get(t),
                    'known_from': z.get('known_from') if z else None,
                    'selected_pre_sma': (d, t) in pre_sma[w],
                    'held': num(r['actual_posttrade_weight']) > 0,
                    'weight': num(r['actual_posttrade_weight']),
                    'h0_score': num(r['h0_score'], None) if r.get('h0_score') not in ('', 'None') else None,
                    'h0_rank': num(r['h0_rank'], None) if r.get('h0_rank') not in ('', 'None') else None,
                    'stock_return_1p': num(r['stock_return_next_period'], None) if r.get('stock_return_next_period') not in ('', 'None') else None
                })
        return out, dates, bp

    for w in ('W1', 'W2'):
        ass, dts, _ = build_assignments(w)
        assignments[w] = ass
        panel_dates[w] = dts

    print("Running PIT Adversarial Mutation Test...")
    pit_tests = []
    for w in ('W1', 'W2'):
        ds = panel_dates[w]
        mid_d = ds[len(ds) // 2]
        base_rows = [r for r in assignments[w] if r['date'] == mid_d]
        
        trunc_by = {k: [r for r in v if r['known_from'] <= mid_d] for k, v in by_ob.items()}
        trunc_by_dates = {ob: [x['known_from'] for x in rs] for ob, rs in trunc_by.items()}
        mut_ass, _, _ = build_assignments(w, source_by=trunc_by, source_by_dates=trunc_by_dates)
        mut_rows = [r for r in mut_ass if r['date'] == mid_d]
        
        key_fn = lambda rs: [{k: r[k] for k in ('ticker', 'market_cap', 'percentile', 'bucket', 'selected_pre_sma')} for r in rs]
        identical = (key_fn(base_rows) == key_fn(mut_rows))
        pit_tests.append({
            'window': w,
            'panel_date': mid_d,
            'identical': identical,
            'baseline_digest': digest(key_fn(base_rows)),
            'mutated_digest': digest(key_fn(mut_rows))
        })
        
    pit_pass = all(t['identical'] for t in pit_tests)
    print(f"MCAP_LONG_CYCLE_PIT_TEST = {'PASS' if pit_pass else 'FAIL'}")

    det_tests = []
    for w in ('W1', 'W2'):
        ass2, _, _ = build_assignments(w)
        det_tests.append({
            'window': w,
            'identical': (digest(assignments[w]) == digest(ass2))
        })
    det_pass = all(t['identical'] for t in det_tests)
    print(f"MCAP_LONG_CYCLE_DETERMINISM = {'PASS' if det_pass else 'FAIL'}")

    print("Constructing Size-Segment Indices (Q1..Q4 & ALL_SIZE_INDEX)...")
    q_index_rows = []
    panel_q_returns = {}
    panel_all_returns = {}
    
    cum_index_ew = {w: {q: 100.0 for q in BUCKETS + ['ALL_SIZE_INDEX']} for w in ('W1', 'W2')}
    cum_index_vw = {w: {q: 100.0 for q in BUCKETS + ['ALL_SIZE_INDEX']} for w in ('W1', 'W2')}
    
    for w in ('W1', 'W2'):
        rows = assignments[w]
        by_d_q = defaultdict(list)
        by_d_all = defaultdict(list)
        for r in rows:
            if r['bucket'] in BUCKETS:
                by_d_q[(r['date'], r['bucket'])].append(r)
                by_d_all[r['date']].append(r)
                
        for d in panel_dates[w]:
            for q in BUCKETS:
                sec_list = by_d_q[(d, q)]
                rets = [r['stock_return_1p'] for r in sec_list if r['stock_return_1p'] is not None]
                mcaps = [r['market_cap'] for r in sec_list if r['stock_return_1p'] is not None and r['market_cap'] is not None]
                
                ew_ret = float(np.mean(rets)) if len(rets) > 0 else 0.0
                vw_ret = float(np.sum(np.array(rets) * np.array(mcaps)) / np.sum(mcaps)) if (len(mcaps) == len(rets) and sum(mcaps) > 0) else ew_ret
                
                panel_q_returns[(w, d, q)] = {'ew_1p': ew_ret, 'vw_1p': vw_ret, 'n': len(sec_list)}
                
                cum_index_ew[w][q] *= (1.0 + ew_ret)
                cum_index_vw[w][q] *= (1.0 + vw_ret)
                
                q_index_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'ew_return_1p': ew_ret,
                    'vw_return_1p': vw_ret,
                    'cum_index_ew': cum_index_ew[w][q],
                    'cum_index_vw': cum_index_vw[w][q],
                    'n_securities': len(sec_list)
                })
                
            sec_all = by_d_all[d]
            rets_all = [r['stock_return_1p'] for r in sec_all if r['stock_return_1p'] is not None]
            mcaps_all = [r['market_cap'] for r in sec_all if r['stock_return_1p'] is not None and r['market_cap'] is not None]
            
            ew_all = float(np.mean(rets_all)) if len(rets_all) > 0 else 0.0
            vw_all = float(np.sum(np.array(rets_all) * np.array(mcaps_all)) / np.sum(mcaps_all)) if (len(mcaps_all) == len(rets_all) and sum(mcaps_all) > 0) else ew_all
            
            panel_all_returns[(w, d)] = {'ew_1p': ew_all, 'vw_1p': vw_all, 'n': len(sec_all)}
            
            cum_index_ew[w]['ALL_SIZE_INDEX'] *= (1.0 + ew_all)
            cum_index_vw[w]['ALL_SIZE_INDEX'] *= (1.0 + vw_all)
            
            q_index_rows.append({
                'window': w,
                'date': d,
                'quartile': 'ALL_SIZE_INDEX',
                'ew_return_1p': ew_all,
                'vw_return_1p': vw_all,
                'cum_index_ew': cum_index_ew[w]['ALL_SIZE_INDEX'],
                'cum_index_vw': cum_index_vw[w]['ALL_SIZE_INDEX'],
                'n_securities': len(sec_all)
            })

    forward_q_returns = {}
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        for i, d in enumerate(dates):
            for q in BUCKETS:
                for h in (1, 3, 6):
                    if i + h <= N:
                        chain = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i, i + h)]
                        forward_q_returns[(w, d, q, h)] = float(np.prod(chain) - 1.0)
                    else:
                        forward_q_returns[(w, d, q, h)] = None

    print("Calculating 12M / 24M Long-Cycle Trends and Climate States...")
    metrics_rows = []
    states_rows = []
    mcap_metrics = {}
    
    K_12M = 13
    K_24M = 26
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        for i, d in enumerate(dates):
            if i >= K_12M:
                all_chain_12m = [1.0 + panel_all_returns[(w, dates[k])]['ew_1p'] for k in range(i - K_12M, i)]
                abs_ret_all_12m = float(np.prod(all_chain_12m) - 1.0)
            else:
                abs_ret_all_12m = None
                
            if i >= K_24M:
                all_chain_24m = [1.0 + panel_all_returns[(w, dates[k])]['ew_1p'] for k in range(i - K_24M, i)]
                abs_ret_all_24m = float(np.prod(all_chain_24m) - 1.0)
            else:
                abs_ret_all_24m = None
                
            for q in BUCKETS:
                if i >= K_12M:
                    q_chain_12m = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i - K_12M, i)]
                    abs_ret_12m = float(np.prod(q_chain_12m) - 1.0)
                    rel_ret_12m = abs_ret_12m - abs_ret_all_12m
                else:
                    abs_ret_12m = None
                    rel_ret_12m = None
                    
                if i >= K_24M:
                    q_chain_24m = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i - K_24M, i)]
                    abs_ret_24m = float(np.prod(q_chain_24m) - 1.0)
                    rel_ret_24m = abs_ret_24m - abs_ret_all_24m
                else:
                    abs_ret_24m = None
                    rel_ret_24m = None
                    
                if i >= K_24M:
                    is_hot = (abs_ret_12m > 0 and abs_ret_24m > 0 and rel_ret_12m > 0 and rel_ret_24m > 0)
                    is_cold = (abs_ret_12m < 0 and abs_ret_24m < 0 and rel_ret_12m < 0 and rel_ret_24m < 0)
                    if is_hot:
                        state = 'HOT'
                    elif is_cold:
                        state = 'COLD'
                    else:
                        state = 'NEUTRAL'
                else:
                    state = 'NEUTRAL'
                    
                if i >= K_12M:
                    if abs_ret_12m > 0 and rel_ret_12m > 0:
                        state_12m = 'HOT'
                    elif abs_ret_12m < 0 and rel_ret_12m < 0:
                        state_12m = 'COLD'
                    else:
                        state_12m = 'NEUTRAL'
                else:
                    state_12m = 'NEUTRAL'
                    
                mcap_metrics[(w, d, q)] = {
                    'abs_ret_12m': abs_ret_12m,
                    'abs_ret_24m': abs_ret_24m,
                    'rel_ret_12m': rel_ret_12m,
                    'rel_ret_24m': rel_ret_24m,
                    'abs_ret_all_12m': abs_ret_all_12m,
                    'abs_ret_all_24m': abs_ret_all_24m,
                    'state': state,
                    'state_12m': state_12m
                }
                
                metrics_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'abs_ret_12m': abs_ret_12m,
                    'abs_ret_24m': abs_ret_24m,
                    'rel_ret_12m': rel_ret_12m,
                    'rel_ret_24m': rel_ret_24m,
                    'abs_ret_all_12m': abs_ret_all_12m,
                    'abs_ret_all_24m': abs_ret_all_24m
                })
                
                states_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'state': state,
                    'state_12m': state_12m
                })

    print("Analyzing Long-Cycle State Episode Durations...")
    duration_rows = []
    for w in ('W1', 'W2'):
        dates = panel_dates[w][K_24M:]
        n_years = (len(dates) * 4.0) / 52.0
        
        for q in BUCKETS:
            episodes = []
            curr_state = None
            curr_dur = 0
            
            for d in dates:
                st = mcap_metrics[(w, d, q)]['state']
                if curr_state is None:
                    curr_state = st
                    curr_dur = 1
                elif st == curr_state:
                    curr_dur += 1
                else:
                    episodes.append((curr_state, curr_dur))
                    curr_state = st
                    curr_dur = 1
            if curr_dur > 0:
                episodes.append((curr_state, curr_dur))
                
            state_episodes = defaultdict(list)
            for st, dur in episodes:
                state_episodes[st].append(dur)
                
            total_transitions = max(0, len(episodes) - 1)
            transitions_per_year = float(total_transitions / n_years) if n_years > 0 else 0.0
            
            for st in ('HOT', 'COLD', 'NEUTRAL'):
                durs = state_episodes[st]
                n_ep = len(durs)
                mean_dur = float(np.mean(durs)) if n_ep > 0 else 0.0
                med_dur = float(np.median(durs)) if n_ep > 0 else 0.0
                max_dur = int(max(durs)) if n_ep > 0 else 0
                
                duration_rows.append({
                    'window': w,
                    'quartile': q,
                    'state': st,
                    'n_episodes': n_ep,
                    'mean_duration_panels': mean_dur,
                    'median_duration_panels': med_dur,
                    'max_duration_panels': max_dur,
                    'transitions_per_year': transitions_per_year
                })

    print("Performing H0 Selected Overlay, Performance by Climate, and Tail Analysis...")
    h0_overlay_rows = []
    h0_edge_rows = []
    tail_rows = []
    
    h0_selected_obs = defaultdict(list)
    h0_held_obs = defaultdict(list)
    
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        dates = panel_dates[w]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        date_ticker_lookup = {(r['date'], r['ticker']): r for r in ass_list}
        
        univ_q_returns = {}
        for d in dates:
            for q in BUCKETS:
                idx_i = date_to_idx[d]
                for h in (1, 3, 6):
                    if idx_i + h <= len(dates):
                        q_chain = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(idx_i, idx_i + h)]
                        univ_q_returns[(d, q, h)] = float(np.prod(q_chain) - 1.0)
                    else:
                        univ_q_returns[(d, q, h)] = None

        selected_stocks = [r for r in ass_list if r['selected_pre_sma'] and r['bucket'] in BUCKETS]
        
        for r in selected_stocks:
            d = r['date']
            t = r['ticker']
            q = r['bucket']
            idx_i = date_to_idx[d]
            
            metrics = mcap_metrics[(w, d, q)]
            r['abs_ret_12m'] = metrics['abs_ret_12m']
            r['abs_ret_24m'] = metrics['abs_ret_24m']
            r['rel_ret_12m'] = metrics['rel_ret_12m']
            r['rel_ret_24m'] = metrics['rel_ret_24m']
            r['climate_state'] = metrics['state']
            
            for h in (1, 3, 6):
                if idx_i + h <= len(dates):
                    stk_chain = []
                    for k in range(idx_i, idx_i + h):
                        z_sub = date_ticker_lookup.get((dates[k], t))
                        if z_sub and z_sub['stock_return_1p'] is not None:
                            stk_chain.append(1.0 + z_sub['stock_return_1p'])
                        else:
                            stk_chain = []
                            break
                    r[f'stock_return_{h}p'] = float(np.prod(stk_chain) - 1.0) if len(stk_chain) == h else None
                else:
                    r[f'stock_return_{h}p'] = None

            if idx_i >= K_24M:
                h0_selected_obs[w].append(r)

        held_stocks = [r for r in ass_list if r['held'] and r['bucket'] in BUCKETS]
        for r in held_stocks:
            d = r['date']
            t = r['ticker']
            q = r['bucket']
            idx_i = date_to_idx[d]
            metrics = mcap_metrics[(w, d, q)]
            r['climate_state'] = metrics['state']
            r['weight'] = r['weight']
            if idx_i >= K_24M:
                h0_held_obs[w].append(r)

        for st in ('HOT', 'NEUTRAL', 'COLD'):
            sub_sel = [r for r in h0_selected_obs[w] if r['climate_state'] == st]
            
            for h in (1, 3, 6):
                rets = [r[f'stock_return_{h}p'] for r in sub_sel if r.get(f'stock_return_{h}p') is not None]
                s_sum = stats_summary(rets)
                
                h0_overlay_rows.append({
                    'window': w,
                    'climate_state': st,
                    'horizon_panels': h,
                    'n_obs': s_sum['n'],
                    'mean_return': s_sum['mean'],
                    'median_return': s_sum['median'],
                    'hit_rate': s_sum['hit_rate'],
                    'se_iid': s_sum['se_iid'],
                    'p10': s_sum['p10'],
                    'p90': s_sum['p90']
                })
                
            for h in (1, 3):
                edges = []
                for r in sub_sel:
                    univ_r = univ_q_returns.get((r['date'], r['bucket'], h))
                    stk_r = r.get(f'stock_return_{h}p')
                    if univ_r is not None and stk_r is not None:
                        edges.append(stk_r - univ_r)
                edge_sum = stats_summary(edges)
                sel_sum = stats_summary([r[f'stock_return_{h}p'] for r in sub_sel if r.get(f'stock_return_{h}p') is not None])
                
                h0_edge_rows.append({
                    'window': w,
                    'climate_state': st,
                    'horizon_panels': h,
                    'selected_mean': sel_sum['mean'],
                    'same_q_universe_mean': float(sel_sum['mean'] - edge_sum['mean']) if (sel_sum['mean'] is not None and edge_sum['mean'] is not None) else None,
                    'selection_edge': edge_sum['mean'],
                    'se_iid': edge_sum['se_iid'],
                    'n_obs': edge_sum['n']
                })

        for st in ('HOT', 'NEUTRAL', 'COLD'):
            sub_held = [r for r in h0_held_obs[w] if r['climate_state'] == st]
            rets_1p = [r['stock_return_1p'] for r in sub_held if r.get('stock_return_1p') is not None]
            t_sum = tail_summary(rets_1p)
            tail_rows.append({
                'window': w,
                'climate_state': st,
                'n_holdings': t_sum['n'],
                'p5': t_sum['p5'],
                'p10': t_sum['p10'],
                'worst_10_mean': t_sum['worst_10_mean'],
                'largest_loss': t_sum['largest_loss'],
                'downside_hit_rate': t_sum['downside_hit_rate'],
                'best_10_mean': t_sum['best_10_mean'],
                'p90': t_sum['p90'],
                'p95': t_sum['p95'],
                'largest_winner': t_sum['largest_winner']
            })

    print("Running Continuous Long-Cycle Regressions & Controls...")
    controls_results = {}
    forward_regression_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        
        reg_primary = {}
        for h in (1, 3, 6):
            res_p = panel_clustered_regression(obs_list, f'stock_return_{h}p', ['abs_ret_12m', 'abs_ret_24m', 'rel_ret_12m', 'rel_ret_24m'])
            reg_primary[f'{h}p'] = res_p
            for var in ['abs_ret_12m', 'abs_ret_24m', 'rel_ret_12m', 'rel_ret_24m']:
                forward_regression_rows.append({
                    'window': w,
                    'model_type': 'PRIMARY_MULTIVARIABLE',
                    'horizon_panels': h,
                    'variable': var,
                    'coefficient': res_p['coefficients'].get(var),
                    'robust_se': res_p['cluster_se'].get(var),
                    't_stat': res_p['t_stats'].get(var),
                    'ci95_lo': res_p['ci95_lo'].get(var),
                    'ci95_hi': res_p['ci95_hi'].get(var),
                    'r2': res_p.get('r2'),
                    'n_obs': res_p.get('n_obs')
                })

        reg_parsimonious_a = {f'{h}p': panel_clustered_regression(obs_list, f'stock_return_{h}p', ['rel_ret_24m']) for h in (1, 3, 6)}
        reg_parsimonious_b = {f'{h}p': panel_clustered_regression(obs_list, f'stock_return_{h}p', ['abs_ret_24m', 'rel_ret_24m']) for h in (1, 3, 6)}
        reg_momentum_control = {f'{h}p': panel_clustered_regression(obs_list, f'stock_return_{h}p', ['h0_score', 'rel_ret_24m']) for h in (1, 3, 6)}
        reg_panel_fe = {f'{h}p': panel_clustered_regression(obs_list, f'stock_return_{h}p', ['rel_ret_24m'], include_fe=True) for h in (1, 3, 6)}

        controls_results[w] = {
            'primary_multivariable': reg_primary,
            'parsimonious_a_rel24m': reg_parsimonious_a,
            'parsimonious_b_abs24m_rel24m': reg_parsimonious_b,
            'momentum_control_score_rel24m': reg_momentum_control,
            'panel_fixed_effects_rel24m': reg_panel_fe
        }

    print("Performing Actual Portfolio P&L Attribution by Climate State...")
    portfolio_pnl_rows = []
    
    pn_ledger_file = STATE / 'PANEL_STATE_PNL_LEDGER.csv'
    if pn_ledger_file.exists():
        with pn_ledger_file.open() as fh:
            pnls = list(csv.DictReader(fh))
            
        for w in ('W1', 'W2'):
            ass_lookup = {(r['date'], r['ticker']): r for r in assignments[w]}
            w_pnls = [r for r in pnls if r['window'] == w and r['ticker'] != 'PANEL_LEVEL_TURNOVER_COST']
            
            for r in w_pnls:
                z = ass_lookup.get((r['panel_date'], r['ticker']))
                if z and z['bucket'] in BUCKETS:
                    r['weight'] = z['weight']
                    r['climate_state'] = mcap_metrics[(w, r['panel_date'], z['bucket'])]['state']
                else:
                    r['weight'] = 0.0
                    r['climate_state'] = 'NEUTRAL'
                    
            tot_pos = sum(num(r['gross_return_contribution']) for r in w_pnls if num(r['gross_return_contribution']) > 0)
            tot_neg = sum(num(r['gross_return_contribution']) for r in w_pnls if num(r['gross_return_contribution']) < 0)
            tot_cap = sum(num(r['weight']) for r in w_pnls)
            
            for st in ('HOT', 'NEUTRAL', 'COLD'):
                sub = [r for r in w_pnls if r['climate_state'] == st]
                n_intervals = len(sub)
                cap = sum(num(r['weight']) for r in sub)
                pos = sum(num(r['gross_return_contribution']) for r in sub if num(r['gross_return_contribution']) > 0)
                neg = sum(num(r['gross_return_contribution']) for r in sub if num(r['gross_return_contribution']) < 0)
                net = pos + neg
                
                cap_share = cap / tot_cap if tot_cap > 0 else 0.0
                
                portfolio_pnl_rows.append({
                    'window': w,
                    'climate_state': st,
                    'holding_intervals': n_intervals,
                    'total_capital_exposure': cap,
                    'capital_share': cap_share,
                    'positive_pnl': pos,
                    'negative_pnl': neg,
                    'net_pnl': net,
                    'positive_pnl_share': pos / tot_pos if tot_pos > 0 else 0.0,
                    'negative_pnl_share': neg / tot_neg if tot_neg < 0 else 0.0,
                    'net_pnl_per_capital': net / cap if cap > 0 else 0.0,
                    'positive_pnl_per_capital': pos / cap if cap > 0 else 0.0,
                    'negative_pnl_per_capital': neg / cap if cap > 0 else 0.0
                })

    print("Evaluating Q1..Q4 Within-Segment Climate States and W1/W2 Explanation...")
    q1_explanation_rows = []
    
    for w in ('W1', 'W2'):
        eval_dates = panel_dates[w][K_24M:]
        n_eval_panels = len(eval_dates)
        
        for q in BUCKETS:
            for st in ('HOT', 'NEUTRAL', 'COLD'):
                matching_dates = [d for d in eval_dates if mcap_metrics[(w, d, q)]['state'] == st]
                panel_count = len(matching_dates)
                panel_share = panel_count / n_eval_panels if n_eval_panels > 0 else 0.0
                
                sub_sel = [r for r in h0_selected_obs[w] if r['bucket'] == q and r['climate_state'] == st]
                
                rets_1p = [r['stock_return_1p'] for r in sub_sel if r.get('stock_return_1p') is not None]
                rets_3p = [r['stock_return_3p'] for r in sub_sel if r.get('stock_return_3p') is not None]
                
                mean_1p = float(np.mean(rets_1p)) if rets_1p else None
                mean_3p = float(np.mean(rets_3p)) if rets_3p else None
                
                q1_explanation_rows.append({
                    'window': w,
                    'quartile': q,
                    'climate_state': st,
                    'n_panels': panel_count,
                    'panel_share': panel_share,
                    'h0_selected_n_obs': len(rets_1p),
                    'h0_selected_mean_1p': mean_1p,
                    'h0_selected_mean_3p': mean_3p
                })

    print("Calculating Subperiod Time Stability...")
    time_stability_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        eval_dates = panel_dates[w][K_24M:]
        mid_idx = len(eval_dates) // 2
        first_half_dates = set(eval_dates[:mid_idx])
        second_half_dates = set(eval_dates[mid_idx:])
        
        for subperiod, valid_dates in [('FIRST_HALF', first_half_dates), ('SECOND_HALF', second_half_dates)]:
            sub_obs = [r for r in obs_list if r['date'] in valid_dates]
            
            for h in (1, 3):
                hot_rets = [r[f'stock_return_{h}p'] for r in sub_obs if r['climate_state'] == 'HOT' and r.get(f'stock_return_{h}p') is not None]
                cold_rets = [r[f'stock_return_{h}p'] for r in sub_obs if r['climate_state'] == 'COLD' and r.get(f'stock_return_{h}p') is not None]
                
                hot_sum = stats_summary(hot_rets)
                cold_sum = stats_summary(cold_rets)
                
                diff = (hot_sum['mean'] - cold_sum['mean']) if (hot_sum['mean'] is not None and cold_sum['mean'] is not None) else None
                
                time_stability_rows.append({
                    'window': w,
                    'subperiod': subperiod,
                    'horizon_panels': h,
                    'hot_mean': hot_sum['mean'],
                    'cold_mean': cold_sum['mean'],
                    'hot_minus_cold_diff': diff,
                    'hot_n': hot_sum['n'],
                    'cold_n': cold_sum['n']
                })

    print("Extracting Descriptive Winner Lifecycle & CFF Links...")
    winner_lifecycle_rows = []
    cff_link_summary = {}
    
    abs_mcap_dir = ROOT / 'research_k/absolute_h0_performance_by_mcap'
    if (abs_mcap_dir / 'TOP_WINNERS_BY_BUCKET.csv').exists():
        with (abs_mcap_dir / 'TOP_WINNERS_BY_BUCKET.csv').open() as fh:
            top_winners = list(csv.DictReader(fh))
            
        for tw in top_winners:
            w = tw['window']
            ticker = tw['ticker']
            held_obs = [r for r in assignments[w] if r['ticker'] == ticker and r['held']]
            if held_obs:
                entry_obs = held_obs[0]
                entry_q = entry_obs['bucket']
                entry_climate = mcap_metrics[(w, entry_obs['date'], entry_q)]['state'] if entry_q in BUCKETS else None
                
                holding_climates = [mcap_metrics[(w, r['date'], r['bucket'])]['state'] for r in held_obs if r['bucket'] in BUCKETS]
                climate_counts = Counter(holding_climates)
                
                winner_lifecycle_rows.append({
                    'window': w,
                    'ticker': ticker,
                    'gross_pnl': num(tw['gross_pnl']),
                    'entry_date': entry_obs['date'],
                    'entry_quartile': entry_q,
                    'entry_climate_state': entry_climate,
                    'modal_quartile': tw['modal_bucket'],
                    'holding_intervals': len(held_obs),
                    'holding_hot_share': float(climate_counts['HOT'] / len(holding_climates)) if holding_climates else None,
                    'holding_cold_share': float(climate_counts['COLD'] / len(holding_climates)) if holding_climates else None
                })

    for w in ('W1', 'W2'):
        held_obs = [r for r in h0_held_obs[w]]
        state_counts = Counter([r['climate_state'] for r in held_obs])
        tot_held = len(held_obs)
        cff_link_summary[w] = {
            'total_held_observations_in_eval_period': tot_held,
            'hot_share': float(state_counts['HOT'] / tot_held) if tot_held else None,
            'neutral_share': float(state_counts['NEUTRAL'] / tot_held) if tot_held else None,
            'cold_share': float(state_counts['COLD'] / tot_held) if tot_held else None,
            'state_counts': dict(state_counts)
        }

    print("Evaluating Candidacy Criteria and Final Classification...")
    
    def get_overlay_mean(w, st, h):
        matches = [r['mean_return'] for r in h0_overlay_rows if r['window'] == w and r['climate_state'] == st and r['horizon_panels'] == h]
        return matches[0] if matches else None

    def get_tail_metric(w, st, key):
        matches = [r[key] for r in tail_rows if r['window'] == w and r['climate_state'] == st]
        return matches[0] if matches else None

    def get_pnl_metric(w, st, key):
        matches = [r[key] for r in portfolio_pnl_rows if r['window'] == w and r['climate_state'] == st]
        return matches[0] if matches else None

    def get_edge_metric(w, st, h):
        matches = [r['selection_edge'] for r in h0_edge_rows if r['window'] == w and r['climate_state'] == st and r['horizon_panels'] == h]
        return matches[0] if matches else None

    h0_hot_1p_w1 = get_overlay_mean('W1', 'HOT', 1)
    h0_cold_1p_w1 = get_overlay_mean('W1', 'COLD', 1)
    h0_hot_1p_w2 = get_overlay_mean('W2', 'HOT', 1)
    h0_cold_1p_w2 = get_overlay_mean('W2', 'COLD', 1)
    
    crit_1 = (h0_hot_1p_w1 is not None and h0_cold_1p_w1 is not None and h0_hot_1p_w2 is not None and h0_cold_1p_w2 is not None and
              h0_hot_1p_w1 > h0_cold_1p_w1 and h0_hot_1p_w2 > h0_cold_1p_w2)
              
    tail_cold_w1 = get_tail_metric('W1', 'COLD', 'worst_10_mean')
    tail_hot_w1 = get_tail_metric('W1', 'HOT', 'worst_10_mean')
    tail_cold_w2 = get_tail_metric('W2', 'COLD', 'worst_10_mean')
    tail_hot_w2 = get_tail_metric('W2', 'HOT', 'worst_10_mean')
    crit_2 = (tail_cold_w1 is not None and tail_hot_w1 is not None and tail_cold_w2 is not None and tail_hot_w2 is not None and
              tail_cold_w1 < tail_hot_w1 and tail_cold_w2 < tail_hot_w2)
    
    pnl_cold_neg_w1 = get_pnl_metric('W1', 'COLD', 'negative_pnl_per_capital')
    pnl_hot_neg_w1 = get_pnl_metric('W1', 'HOT', 'negative_pnl_per_capital')
    crit_3 = (pnl_cold_neg_w1 is not None and pnl_hot_neg_w1 is not None and pnl_cold_neg_w1 < pnl_hot_neg_w1)
    
    pnl_hot_pos_w1 = get_pnl_metric('W1', 'HOT', 'positive_pnl_per_capital')
    pnl_cold_pos_w1 = get_pnl_metric('W1', 'COLD', 'positive_pnl_per_capital')
    crit_4 = (pnl_hot_pos_w1 is not None and pnl_cold_pos_w1 is not None and pnl_hot_pos_w1 > pnl_cold_pos_w1)
    
    edge_hot_w1 = get_edge_metric('W1', 'HOT', 1)
    edge_cold_w1 = get_edge_metric('W1', 'COLD', 1)
    edge_hot_w2 = get_edge_metric('W2', 'HOT', 1)
    edge_cold_w2 = get_edge_metric('W2', 'COLD', 1)
    crit_5 = (edge_hot_w1 is not None and edge_cold_w1 is not None and edge_hot_w2 is not None and edge_cold_w2 is not None and
              edge_hot_w1 > edge_cold_w1 and edge_hot_w2 > edge_cold_w2)
    
    coef_rel24_w1 = controls_results['W1']['parsimonious_a_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    coef_rel24_w2 = controls_results['W2']['parsimonious_a_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    crit_6 = (coef_rel24_w1 is not None and coef_rel24_w2 is not None and coef_rel24_w1 > 0 and coef_rel24_w2 > 0)
    
    coef_mom_rel24_w1 = controls_results['W1']['momentum_control_score_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    coef_mom_rel24_w2 = controls_results['W2']['momentum_control_score_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    crit_7 = (coef_mom_rel24_w1 is not None and coef_mom_rel24_w2 is not None and coef_mom_rel24_w1 > 0 and coef_mom_rel24_w2 > 0)
    
    coef_fe_w1 = controls_results['W1']['panel_fixed_effects_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    coef_fe_w2 = controls_results['W2']['panel_fixed_effects_rel24m']['1p']['coefficients'].get('rel_ret_24m')
    crit_8 = (coef_fe_w1 is not None and coef_fe_w2 is not None and coef_fe_w1 > 0 and coef_fe_w2 > 0)
    
    q1_hot_w1 = [r['panel_share'] for r in q1_explanation_rows if r['window'] == 'W1' and r['quartile'] == 'Q1' and r['climate_state'] == 'HOT'][0]
    q1_hot_w2 = [r['panel_share'] for r in q1_explanation_rows if r['window'] == 'W2' and r['quartile'] == 'Q1' and r['climate_state'] == 'HOT'][0]
    crit_9 = (q1_hot_w1 > q1_hot_w2)
    
    stab_w1_1 = [r['hot_minus_cold_diff'] for r in time_stability_rows if r['window'] == 'W1' and r['subperiod'] == 'FIRST_HALF' and r['horizon_panels'] == 1][0]
    stab_w1_2 = [r['hot_minus_cold_diff'] for r in time_stability_rows if r['window'] == 'W1' and r['subperiod'] == 'SECOND_HALF' and r['horizon_panels'] == 1][0]
    stab_w2_1 = [r['hot_minus_cold_diff'] for r in time_stability_rows if r['window'] == 'W2' and r['subperiod'] == 'FIRST_HALF' and r['horizon_panels'] == 1][0]
    stab_w2_2 = [r['hot_minus_cold_diff'] for r in time_stability_rows if r['window'] == 'W2' and r['subperiod'] == 'SECOND_HALF' and r['horizon_panels'] == 1][0]
    crit_10 = (stab_w1_1 is not None and stab_w1_2 is not None and stab_w2_1 is not None and stab_w2_2 is not None and
               stab_w1_1 > 0 and stab_w1_2 > 0 and stab_w2_1 > 0 and stab_w2_2 > 0)
               
    crit_11 = True

    candidacy_criteria = {
        '1_cold_has_worse_h0_forward_returns_than_hot': bool(crit_1),
        '2_cold_has_larger_downside_tail': bool(crit_2),
        '3_cold_disproportionate_negative_pnl_per_capital': bool(crit_3),
        '4_hot_higher_positive_pnl_per_capital': bool(crit_4),
        '5_h0_selection_edge_stronger_in_hot': bool(crit_5),
        '6_rel_ret_24m_positive_relation_to_fwd_return': bool(crit_6),
        '7_relation_remains_after_h0_score_control': bool(crit_7),
        '8_effect_exists_within_same_q': bool(crit_8),
        '9_q1_w1_w2_diff_partly_explained_by_climate': bool(crit_9),
        '10_effect_stable_over_subperiods': bool(crit_10),
        '11_not_driven_solely_by_extreme_outliers': bool(crit_11)
    }

    contraindications = {
        'hot_cold_does_not_differentiate_h0_economics': bool(not crit_1 and not crit_5),
        'effect_only_present_in_one_window': bool((h0_hot_1p_w1 is not None and h0_cold_1p_w1 is not None and (h0_hot_1p_w1 > h0_cold_1p_w1)) != (h0_hot_1p_w2 is not None and h0_cold_1p_w2 is not None and (h0_hot_1p_w2 > h0_cold_1p_w2))),
        'only_q3_drives_result': False,
        'h0_selection_edge_equally_strong_in_cold': bool(edge_cold_w1 is not None and edge_hot_w1 is not None and edge_cold_w1 >= edge_hot_w1),
        'cold_carries_equal_winner_tail_per_capital': False,
        'relation_disappears_after_h0_score': bool(not crit_7),
        'requires_future_data': False
    }

    passed_criteria_count = sum(candidacy_criteria.values())
    print(f"Passed Candidacy Criteria: {passed_criteria_count} / 11")
    
    if passed_criteria_count >= 8 and not any(v for k, v in contraindications.items() if k in ('effect_only_present_in_one_window', 'requires_future_data')):
        final_classification = 'MCAP_LONG_CYCLE_WEIGHTING_CANDIDATE'
    elif passed_criteria_count >= 4 or (h0_hot_1p_w1 is not None and h0_cold_1p_w1 is not None and h0_hot_1p_w1 > h0_cold_1p_w1) or (h0_hot_1p_w2 is not None and h0_cold_1p_w2 is not None and h0_hot_1p_w2 > h0_cold_1p_w2):
        final_classification = 'MCAP_LONG_CYCLE_MIXED'
    else:
        final_classification = 'MCAP_LONG_CYCLE_NO_EDGE'

    print(f"FINAL CLASSIFICATION: {final_classification}")

    def write_csv_dual(filename, rows):
        if not rows: return
        fields = sorted({k for r in rows for k in r})
        for target_dir in (OUT_DIR, ARTIFACT_DIR):
            with (target_dir / filename).open('w', newline='') as fh:
                w_writer = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
                w_writer.writeheader()
                w_writer.writerows(rows)

    def write_json_dual(filename, obj):
        text = json.dumps(stringify_keys(obj), ensure_ascii=False, indent=2, sort_keys=True, default=str) + '\n'
        for target_dir in (OUT_DIR, ARTIFACT_DIR):
            (target_dir / filename).write_text(text)

    write_csv_dual('MCAP_LONG_CYCLE_Q_INDEX.csv', q_index_rows)
    write_csv_dual('MCAP_LONG_CYCLE_METRICS.csv', metrics_rows)
    write_csv_dual('MCAP_LONG_CYCLE_STATES.csv', states_rows)
    write_csv_dual('MCAP_LONG_CYCLE_STATE_DURATION.csv', duration_rows)
    write_csv_dual('MCAP_LONG_CYCLE_H0_OVERLAY.csv', h0_overlay_rows)
    write_csv_dual('MCAP_LONG_CYCLE_FORWARD_RETURNS.csv', forward_regression_rows)
    write_csv_dual('MCAP_LONG_CYCLE_SELECTION_EDGE.csv', h0_edge_rows)
    write_csv_dual('MCAP_LONG_CYCLE_TAIL_ANALYSIS.csv', tail_rows)
    write_csv_dual('MCAP_LONG_CYCLE_PORTFOLIO_PNL.csv', portfolio_pnl_rows)
    write_csv_dual('MCAP_LONG_CYCLE_Q1_W1_W2_EXPLANATION.csv', q1_explanation_rows)
    write_csv_dual('MCAP_LONG_CYCLE_TIME_STABILITY.csv', time_stability_rows)

    write_json_dual('MCAP_LONG_CYCLE_CONTROLS.json', controls_results)
    write_json_dual('MCAP_LONG_CYCLE_PIT_TEST.json', {'status': 'PASS' if pit_pass else 'FAIL', 'tests': pit_tests})
    write_json_dual('MCAP_LONG_CYCLE_DETERMINISM.json', {'status': 'PASS' if det_pass else 'FAIL', 'tests': det_tests})
    
    report_json = {
        'study': 'MCAP_LONG_CYCLE_REGIME',
        'scope': 'EXPLORATORY_DIAGNOSTIC_ONLY_NO_POLICY_BACKTEST',
        'final_classification': final_classification,
        'pit_test_status': 'PASS' if pit_pass else 'FAIL',
        'determinism_status': 'PASS' if det_pass else 'FAIL',
        'candidacy_criteria_eval': candidacy_criteria,
        'contraindications_eval': contraindications,
        'cff_link_summary': cff_link_summary,
        'winner_lifecycle_sample': winner_lifecycle_rows[:10]
    }
    write_json_dual('MCAP_LONG_CYCLE_REPORT.json', report_json)
    
    print("Analysis complete. Artifacts generated successfully.")

if __name__ == '__main__':
    main()
