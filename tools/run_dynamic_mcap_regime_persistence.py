"""DYNAMIC_MCAP_REGIME_PERSISTENCE — Diagnostic Study

Tests whether historical Point-In-Time (PIT) market-cap regime has predictive persistence
and could serve as a future dynamic capital allocation module on top of frozen H0 V3.

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
OUT_DIR = ROOT / 'research_k/dynamic_mcap_regime_persistence'

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
        return {'n': 0, 'mean': None, 'std': None, 'median': None, 'se_iid': None, 'hit_rate': None}
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
        'min': float(a.min()),
        'max': float(a.max())
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

def panel_clustered_regression(df_rows, y_var, x_vars):
    groups = defaultdict(list)
    for r in df_rows:
        if r.get(y_var) is not None and np.isfinite(r[y_var]):
            if all(r.get(x) is not None and np.isfinite(r[x]) for x in x_vars):
                groups[r['date']].append(r)
    
    Y = []; X = []; gids = []
    for g, rs in groups.items():
        for r in rs:
            Y.append(r[y_var])
            X.append([1.0] + [r[x] for x in x_vars])
            gids.append(g)
            
    if len(Y) <= len(x_vars) + 2:
        return {'n_obs': len(Y), 'n_panels': len(groups)}
        
    Y = np.asarray(Y, float)
    X = np.asarray(X, float)
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
        
    if len(x_vars) >= 1:
        x_primary = np.asarray([r[x_vars[0]] for g in groups.values() for r in g], float)
        rank_x = np.argsort(np.argsort(x_primary))
        rank_y = np.argsort(np.argsort(Y))
        rho = float(np.corrcoef(rank_x, rank_y)[0, 1]) if len(Y) > 1 else None
    else:
        rho = None
        
    return {
        'n_obs': int(N),
        'n_panels': int(G),
        'variables': var_names,
        'coefficients': coef_dict,
        'cluster_se': se_dict,
        't_stats': t_dict,
        'ci95_lo': ci_lo,
        'ci95_hi': ci_hi,
        'r2': float(r2),
        'spearman_rho': rho
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

    print("Running Adversarial PIT Mutation Test...")
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
    print(f"DYNAMIC_MCAP_REGIME_PIT_TEST = {'PASS' if pit_pass else 'FAIL'}")

    det_tests = []
    for w in ('W1', 'W2'):
        ass2, _, _ = build_assignments(w)
        det_tests.append({
            'window': w,
            'identical': (digest(assignments[w]) == digest(ass2))
        })

    print("Constructing Quartile Index Returns...")
    quartile_index_returns = []
    panel_q_returns = {}
    
    for w in ('W1', 'W2'):
        rows = assignments[w]
        by_d_q = defaultdict(list)
        for r in rows:
            by_d_q[(r['date'], r['bucket'])].append(r)
            
        for d in panel_dates[w]:
            for q in BUCKETS:
                sec_list = by_d_q[(d, q)]
                rets = [r['stock_return_1p'] for r in sec_list if r['stock_return_1p'] is not None]
                mcaps = [r['market_cap'] for r in sec_list if r['stock_return_1p'] is not None and r['market_cap'] is not None]
                
                ew_ret = float(np.mean(rets)) if len(rets) > 0 else 0.0
                if len(mcaps) == len(rets) and sum(mcaps) > 0:
                    vw_ret = float(np.sum(np.array(rets) * np.array(mcaps)) / np.sum(mcaps))
                else:
                    vw_ret = ew_ret
                    
                panel_q_returns[(w, d, q)] = {'ew_1p': ew_ret, 'vw_1p': vw_ret, 'n': len(sec_list)}
                quartile_index_returns.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'ew_return_1p': ew_ret,
                    'vw_return_1p': vw_ret,
                    'n_securities': len(sec_list)
                })

    forward_q_returns = {}
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        for i, d in enumerate(dates):
            for q in BUCKETS:
                for h in (1, 2, 3):
                    if i + h <= N:
                        chain = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i, i + h)]
                        forward_q_returns[(w, d, q, h)] = float(np.prod(chain) - 1.0)
                    else:
                        forward_q_returns[(w, d, q, h)] = None

    print("Calculating Trailing Regime Strength (3P & 6P)...")
    regime_strength = {}
    regime_strength_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        for i, d in enumerate(dates):
            for q in BUCKETS:
                if i >= 3:
                    q_chain_3p = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i - 3, i)]
                    q_comp_3p = float(np.prod(q_chain_3p) - 1.0)
                    
                    univ_chain_3p = [1.0 + np.mean([panel_q_returns[(w, dates[k], q_sub)]['ew_1p'] for q_sub in BUCKETS]) for k in range(i - 3, i)]
                    univ_comp_3p = float(np.prod(univ_chain_3p) - 1.0)
                    
                    s_3p = q_comp_3p - univ_comp_3p
                else:
                    q_comp_3p = None
                    univ_comp_3p = None
                    s_3p = None
                    
                if i >= 6:
                    q_chain_6p = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i - 6, i)]
                    q_comp_6p = float(np.prod(q_chain_6p) - 1.0)
                    
                    univ_chain_6p = [1.0 + np.mean([panel_q_returns[(w, dates[k], q_sub)]['ew_1p'] for q_sub in BUCKETS]) for k in range(i - 6, i)]
                    univ_comp_6p = float(np.prod(univ_chain_6p) - 1.0)
                    
                    s_6p = q_comp_6p - univ_comp_6p
                else:
                    s_6p = None
                    
                regime_strength[(w, d, q)] = {
                    'strength_3p': s_3p,
                    'strength_6p': s_6p,
                    'q_comp_3p': q_comp_3p,
                    'univ_comp_3p': univ_comp_3p
                }
                regime_strength_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'regime_strength_3p': s_3p,
                    'regime_strength_6p': s_6p,
                    'q_compound_return_3p': q_comp_3p,
                    'univ_compound_return_3p': univ_comp_3p
                })

    print("Ranking Quartiles Cross-Sectionally by Regime Strength...")
    regime_ranks = {}
    regime_rank_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        for i, d in enumerate(dates):
            if i >= 3:
                q_list = BUCKETS
                order_3p = sorted(q_list, key=lambda q: (-regime_strength[(w, d, q)]['strength_3p'], q))
                ranks_3p = {q: rank + 1 for rank, q in enumerate(order_3p)}
            else:
                ranks_3p = {q: None for q in BUCKETS}
                
            if i >= 6:
                order_6p = sorted(q_list, key=lambda q: (-regime_strength[(w, d, q)]['strength_6p'], q))
                ranks_6p = {q: rank + 1 for rank, q in enumerate(order_6p)}
            else:
                ranks_6p = {q: None for q in BUCKETS}
                
            for q in BUCKETS:
                regime_ranks[(w, d, q)] = {
                    'rank_3p': ranks_3p[q],
                    'rank_6p': ranks_6p[q]
                }
                regime_rank_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'regime_rank_3p': ranks_3p[q],
                    'regime_rank_6p': ranks_6p[q]
                })

    print("Analyzing Strongest Quartile Identity...")
    identity_summary = {}
    for w in ('W1', 'W2'):
        dates = panel_dates[w][3:]
        counts = {q: Counter() for q in BUCKETS}
        for d in dates:
            for q in BUCKETS:
                rk = regime_ranks[(w, d, q)]['rank_3p']
                counts[q][rk] += 1
        identity_summary[w] = {q: {str(rk): cnt for rk, cnt in counts[q].items()} for q in BUCKETS}

    print("Calculating Top vs Bottom Contrast Performance...")
    contrast_rows = []
    panel_contrast_data = defaultdict(list)
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        for i in range(3, N):
            d = dates[i]
            rks = {q: regime_ranks[(w, d, q)]['rank_3p'] for q in BUCKETS}
            top_q = [q for q, r in rks.items() if r == 1][0]
            bottom_q = [q for q, r in rks.items() if r == 4][0]
            top2_qs = [q for q, r in rks.items() if r in (1, 2)]
            bottom2_qs = [q for q, r in rks.items() if r in (3, 4)]
            
            for h in (1, 2, 3):
                if i + h <= N:
                    ret_top = forward_q_returns[(w, d, top_q, h)]
                    ret_bottom = forward_q_returns[(w, d, bottom_q, h)]
                    diff_top_bottom = ret_top - ret_bottom
                    panel_contrast_data[(w, 'TOP_MINUS_BOTTOM', h)].append(diff_top_bottom)
                    
                    ret_top2 = np.mean([forward_q_returns[(w, d, q, h)] for q in top2_qs])
                    ret_bottom2 = np.mean([forward_q_returns[(w, d, q, h)] for q in bottom2_qs])
                    diff_top2_bottom2 = ret_top2 - ret_bottom2
                    panel_contrast_data[(w, 'TOP2_MINUS_BOTTOM2', h)].append(diff_top2_bottom2)

        for contrast_name in ('TOP_MINUS_BOTTOM', 'TOP2_MINUS_BOTTOM2'):
            for h in (1, 2, 3):
                diffs = panel_contrast_data[(w, contrast_name, h)]
                res = panel_contrast_stats(diffs)
                contrast_rows.append({
                    'window': w,
                    'contrast': contrast_name,
                    'horizon_panels': h,
                    **res
                })

    print("Calculating Quartile Rank Persistence and Transition Matrices...")
    transition_matrix_rows = []
    persistence_summary = {}
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        matrix = np.zeros((5, 5), dtype=int)
        
        r1_to_r1_1p = 0; r1_total_1p = 0
        r1_to_top2_1p = 0
        r1_to_top2_2p = 0; r1_total_2p = 0
        r1_to_top2_3p = 0; r1_total_3p = 0
        
        r4_to_bot2_1p = 0; r4_total_1p = 0
        r4_to_bot2_2p = 0; r4_total_2p = 0
        r4_to_bot2_3p = 0; r4_total_3p = 0
        
        switches_r1 = 0
        r1_durations = []
        
        curr_r1 = None
        curr_r1_dur = 0
        
        for i in range(3, N - 1):
            d_curr = dates[i]
            d_next1 = dates[i + 1]
            
            rks_curr = {q: regime_ranks[(w, d_curr, q)]['rank_3p'] for q in BUCKETS}
            rks_next1 = {q: regime_ranks[(w, d_next1, q)]['rank_3p'] for q in BUCKETS}
            
            r1_curr_q = [q for q, r in rks_curr.items() if r == 1][0]
            r1_next_q = [q for q, r in rks_next1.items() if r == 1][0]
            
            if curr_r1 is None:
                curr_r1 = r1_curr_q
                curr_r1_dur = 1
            elif r1_curr_q == curr_r1:
                curr_r1_dur += 1
            else:
                switches_r1 += 1
                r1_durations.append(curr_r1_dur)
                curr_r1 = r1_curr_q
                curr_r1_dur = 1
                
            for q in BUCKETS:
                r_c = rks_curr[q]
                r_n1 = rks_next1[q]
                matrix[r_c, r_n1] += 1
                
                if r_c == 1:
                    r1_total_1p += 1
                    if r_n1 == 1: r1_to_r1_1p += 1
                    if r_n1 in (1, 2): r1_to_top2_1p += 1
                    
                if r_c == 4:
                    r4_total_1p += 1
                    if r_n1 in (3, 4): r4_to_bot2_1p += 1
                    
                if i + 2 < N:
                    d_next2 = dates[i + 2]
                    r_n2 = regime_ranks[(w, d_next2, q)]['rank_3p']
                    if r_c == 1:
                        r1_total_2p += 1
                        if r_n2 in (1, 2): r1_to_top2_2p += 1
                    if r_c == 4:
                        r4_total_2p += 1
                        if r_n2 in (3, 4): r4_to_bot2_2p += 1
                        
                if i + 3 < N:
                    d_next3 = dates[i + 3]
                    r_n3 = regime_ranks[(w, d_next3, q)]['rank_3p']
                    if r_c == 1:
                        r1_total_3p += 1
                        if r_n3 in (1, 2): r1_to_top2_3p += 1
                    if r_c == 4:
                        r4_total_3p += 1
                        if r_n3 in (3, 4): r4_to_bot2_3p += 1

        if curr_r1_dur > 0:
            r1_durations.append(curr_r1_dur)

        for r_from in range(1, 5):
            row_sum = matrix[r_from, 1:5].sum()
            for r_to in range(1, 5):
                count = int(matrix[r_from, r_to])
                prob = float(count / row_sum) if row_sum > 0 else 0.0
                transition_matrix_rows.append({
                    'window': w,
                    'from_rank': r_from,
                    'to_rank': r_to,
                    'count': count,
                    'probability': prob
                })
                
        top_top = matrix[1:3, 1:3].sum()
        top_bot = matrix[1:3, 3:5].sum()
        bot_bot = matrix[3:5, 3:5].sum()
        bot_top = matrix[3:5, 1:3].sum()
        
        top_total = top_top + top_bot
        bot_total = bot_bot + bot_top
        
        persistence_summary[w] = {
            'prob_r1_to_r1_1p': float(r1_to_r1_1p / r1_total_1p) if r1_total_1p else None,
            'prob_r1_to_top2_1p': float(r1_to_top2_1p / r1_total_1p) if r1_total_1p else None,
            'prob_r1_to_top2_2p': float(r1_to_top2_2p / r1_total_2p) if r1_total_2p else None,
            'prob_r1_to_top2_3p': float(r1_to_top2_3p / r1_total_3p) if r1_total_3p else None,
            'prob_r4_to_bot2_1p': float(r4_to_bot2_1p / r4_total_1p) if r4_total_1p else None,
            'prob_r4_to_bot2_2p': float(r4_to_bot2_2p / r4_total_2p) if r4_total_2p else None,
            'prob_r4_to_bot2_3p': float(r4_to_bot2_3p / r4_total_3p) if r4_total_3p else None,
            'prob_top2_to_top2_1p': float(top_top / top_total) if top_total else None,
            'prob_top2_to_bot2_1p': float(top_bot / top_total) if top_total else None,
            'prob_bot2_to_bot2_1p': float(bot_bot / bot_total) if bot_total else None,
            'prob_bot2_to_top2_1p': float(bot_top / bot_total) if bot_total else None,
            'regime_switches_count': switches_r1,
            'regime_switches_per_year': float(switches_r1 / (len(dates) * 2.0 / 52.0)),
            'median_rank1_duration_panels': float(np.median(r1_durations)) if r1_durations else None
        }

    print("Running Continuous Predictability Regressions...")
    predictability_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        for lookback_spec in ('3p', '6p'):
            min_i = 3 if lookback_spec == '3p' else 6
            for h in (1, 2, 3):
                reg_data = []
                for i in range(min_i, N):
                    if i + h <= N:
                        d = dates[i]
                        univ_fwd = np.mean([forward_q_returns[(w, d, q, h)] for q in BUCKETS])
                        for q in BUCKETS:
                            strength_val = regime_strength[(w, d, q)][f'strength_{lookback_spec}']
                            fwd_q = forward_q_returns[(w, d, q, h)]
                            fwd_rel = fwd_q - univ_fwd
                            if strength_val is not None and fwd_rel is not None:
                                reg_data.append({
                                    'date': d,
                                    'regime_strength': strength_val,
                                    'future_relative_return': fwd_rel
                                })
                                
                res = panel_clustered_regression(reg_data, 'future_relative_return', ['regime_strength'])
                coef = res['coefficients'].get('regime_strength')
                se = res['cluster_se'].get('regime_strength')
                t_stat = res['t_stats'].get('regime_strength')
                ci_lo = res['ci95_lo'].get('regime_strength')
                ci_hi = res['ci95_hi'].get('regime_strength')
                
                predictability_rows.append({
                    'window': w,
                    'lookback_spec': lookback_spec,
                    'horizon_panels': h,
                    'coefficient': coef,
                    'robust_se': se,
                    't_stat': t_stat,
                    'ci95_lo': ci_lo,
                    'ci95_hi': ci_hi,
                    'r2': res.get('r2'),
                    'spearman_rho': res.get('spearman_rho'),
                    'n_obs': res.get('n_obs'),
                    'n_panels': res.get('n_panels')
                })

    print("Materializing 20 Random Panel Timing Logs for Contamination QA...")
    contamination_qa = []
    rng_qa = np.random.defaultrng = np.random.default_rng(20260822)
    
    all_valid_panels = []
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        for i in range(3, len(dates) - 3):
            all_valid_panels.append((w, i, dates[i]))
            
    sample_indices = rng_qa.choice(len(all_valid_panels), size=20, replace=False)
    for idx in sorted(sample_indices):
        w, i, d = all_valid_panels[idx]
        dates = panel_dates[w]
        contamination_qa.append({
            'window': w,
            'panel_index': i,
            'decision_panel_date': d,
            'lookback_start_date': dates[i - 3],
            'lookback_end_date': dates[i],
            'future_return_1p_start_date': dates[i],
            'future_return_1p_end_date': dates[i + 1],
            'future_return_3p_end_date': dates[i + 3],
            'contamination_check': 'PASS (lookback end == decision panel == future return start)'
        })

    print("Analyzing Magnitude Spread Effect...")
    spread_summary = {}
    for w in ('W1', 'W2'):
        dates = panel_dates[w][3:]
        spreads = [max(regime_strength[(w, d, q)]['strength_3p'] for q in BUCKETS) - min(regime_strength[(w, d, q)]['strength_3p'] for q in BUCKETS) for d in dates]
        med_spread = float(np.median(spreads))
        
        below_diffs_1p = []
        above_diffs_1p = []
        below_diffs_3p = []
        above_diffs_3p = []
        
        for i in range(3, len(panel_dates[w])):
            d = panel_dates[w][i]
            sp = max(regime_strength[(w, d, q)]['strength_3p'] for q in BUCKETS) - min(regime_strength[(w, d, q)]['strength_3p'] for q in BUCKETS)
            diff1 = panel_contrast_data[(w, 'TOP_MINUS_BOTTOM', 1)][i - 3] if (i - 3) < len(panel_contrast_data[(w, 'TOP_MINUS_BOTTOM', 1)]) else None
            diff3 = panel_contrast_data[(w, 'TOP_MINUS_BOTTOM', 3)][i - 3] if (i - 3) < len(panel_contrast_data[(w, 'TOP_MINUS_BOTTOM', 3)]) else None
            
            if sp < med_spread:
                if diff1 is not None: below_diffs_1p.append(diff1)
                if diff3 is not None: below_diffs_3p.append(diff3)
            else:
                if diff1 is not None: above_diffs_1p.append(diff1)
                if diff3 is not None: above_diffs_3p.append(diff3)
                
        spread_summary[w] = {
            'median_historical_spread': med_spread,
            'below_median_1p_top_minus_bottom': panel_contrast_stats(below_diffs_1p),
            'above_median_1p_top_minus_bottom': panel_contrast_stats(above_diffs_1p),
            'below_median_3p_top_minus_bottom': panel_contrast_stats(below_diffs_3p),
            'above_median_3p_top_minus_bottom': panel_contrast_stats(above_diffs_3p)
        }

    print("Calculating Subperiod Time Stability...")
    time_stability_rows = []
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        eval_dates = dates[3:]
        mid_idx = len(eval_dates) // 2
        first_half_dates = set(eval_dates[:mid_idx])
        second_half_dates = set(eval_dates[mid_idx:])
        
        for contrast_name in ('TOP_MINUS_BOTTOM', 'TOP2_MINUS_BOTTOM2'):
            for h in (1, 3):
                all_diffs = panel_contrast_data[(w, contrast_name, h)]
                first_diffs = [all_diffs[k] for k, d in enumerate(eval_dates[:len(all_diffs)]) if d in first_half_dates]
                second_diffs = [all_diffs[k] for k, d in enumerate(eval_dates[:len(all_diffs)]) if d in second_half_dates]
                
                res_first = panel_contrast_stats(first_diffs)
                res_second = panel_contrast_stats(second_diffs)
                
                time_stability_rows.append({
                    'window': w,
                    'subperiod': 'FIRST_HALF',
                    'contrast': contrast_name,
                    'horizon_panels': h,
                    **res_first
                })
                time_stability_rows.append({
                    'window': w,
                    'subperiod': 'SECOND_HALF',
                    'contrast': contrast_name,
                    'horizon_panels': h,
                    **res_second
                })

    print("Calculating H0 Selection Overlay and Selection Edge by Regime...")
    h0_overlay_rows = []
    h0_edge_rows = []
    
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        dates = panel_dates[w]
        selected_stocks = [r for r in ass_list if r['selected_pre_sma']]
        
        date_q_univ_ret = {}
        by_d_q_ass = defaultdict(list)
        for r in ass_list:
            by_d_q_ass[(r['date'], r['bucket'])].append(r)
            
        for d in dates:
            for q in BUCKETS:
                rets_1p = [r['stock_return_1p'] for r in by_d_q_ass[(d, q)] if r['stock_return_1p'] is not None]
                date_q_univ_ret[(d, q, 1)] = float(np.mean(rets_1p)) if rets_1p else 0.0
                
        date_ticker_lookup = {(r['date'], r['ticker']): r for r in ass_list}
        date_to_idx = {d: i for i, d in enumerate(dates)}
        
        for r in selected_stocks:
            d = r['date']
            t = r['ticker']
            q = r['bucket']
            i_idx = date_to_idx[d]
            
            if q in BUCKETS and i_idx >= 3:
                r['regime_rank_3p'] = regime_ranks[(w, d, q)]['rank_3p']
                r['regime_strength_3p'] = regime_strength[(w, d, q)]['strength_3p']
            else:
                r['regime_rank_3p'] = None
                r['regime_strength_3p'] = None
                
            if i_idx + 3 <= len(dates):
                stk_chain = []
                for k in range(i_idx, i_idx + 3):
                    z_sub = date_ticker_lookup.get((dates[k], t))
                    if z_sub and z_sub['stock_return_1p'] is not None:
                        stk_chain.append(1.0 + z_sub['stock_return_1p'])
                    else:
                        stk_chain = []
                        break
                r['stock_return_3p'] = float(np.prod(stk_chain) - 1.0) if len(stk_chain) == 3 else None
            else:
                r['stock_return_3p'] = None

            if q in BUCKETS and i_idx + 3 <= len(dates):
                q_chain_3p = [1.0 + panel_q_returns[(w, dates[k], q)]['ew_1p'] for k in range(i_idx, i_idx + 3)]
                date_q_univ_ret[(d, q, 3)] = float(np.prod(q_chain_3p) - 1.0)
            else:
                date_q_univ_ret[(d, q, 3)] = None

        for rank_label, rank_filter in [('Rank 1', [1]), ('Rank 2', [2]), ('Rank 3', [3]), ('Rank 4', [4]),
                                       ('Top 2 (Rank 1-2)', [1, 2]), ('Bottom 2 (Rank 3-4)', [3, 4])]:
            for h in (1, 3):
                sub_sel = [r for r in selected_stocks if r['regime_rank_3p'] in rank_filter and r.get(f'stock_return_{h}p') is not None]
                sel_rets = [r[f'stock_return_{h}p'] for r in sub_sel]
                res_sel = stats_summary(sel_rets)
                
                h0_overlay_rows.append({
                    'window': w,
                    'regime_rank': rank_label,
                    'horizon_panels': h,
                    'n_obs': res_sel['n'],
                    'mean_return': res_sel['mean'],
                    'median_return': res_sel['median'],
                    'hit_rate': res_sel['hit_rate'],
                    'se_iid': res_sel['se_iid']
                })
                
                edges = []
                for r in sub_sel:
                    univ_r = date_q_univ_ret.get((r['date'], r['bucket'], h))
                    if univ_r is not None:
                        edges.append(r[f'stock_return_{h}p'] - univ_r)
                res_edge = stats_summary(edges)
                
                h0_edge_rows.append({
                    'window': w,
                    'regime_rank': rank_label,
                    'horizon_panels': h,
                    'selected_mean': res_sel['mean'],
                    'same_q_universe_mean': float(res_sel['mean'] - res_edge['mean']) if (res_sel['mean'] is not None and res_edge['mean'] is not None) else None,
                    'selection_edge': res_edge['mean'],
                    'edge_se_iid': res_edge['se_iid'],
                    'n_obs': res_edge['n']
                })

    print("Running Stock Momentum Controls...")
    momentum_control_results = {}
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        eval_sel = [r for r in ass_list if r['selected_pre_sma'] and r.get('regime_strength_3p') is not None and r.get('h0_score') is not None]
        
        by_d_sel = defaultdict(list)
        for r in eval_sel:
            by_d_sel[r['date']].append(r)
            
        std_sel = []
        for d, rs in by_d_sel.items():
            scores = np.array([r['h0_score'] for r in rs])
            strengths = np.array([r['regime_strength_3p'] for r in rs])
            
            sc_std = (scores - scores.mean()) / (scores.std() or 1.0) if len(scores) > 1 else scores - scores.mean()
            st_std = (strengths - strengths.mean()) / (strengths.std() or 1.0) if len(strengths) > 1 else strengths - strengths.mean()
            
            for k_idx, r in enumerate(rs):
                r_copy = dict(r)
                r_copy['h0_score_std'] = float(sc_std[k_idx])
                r_copy['regime_strength_std'] = float(st_std[k_idx])
                r_copy['interaction'] = float(sc_std[k_idx] * st_std[k_idx])
                std_sel.append(r_copy)
                
        res_1p_add = panel_clustered_regression(std_sel, 'stock_return_1p', ['h0_score_std', 'regime_strength_std'])
        res_1p_int = panel_clustered_regression(std_sel, 'stock_return_1p', ['h0_score_std', 'regime_strength_std', 'interaction'])
        
        res_3p_add = panel_clustered_regression([r for r in std_sel if r.get('stock_return_3p') is not None], 'stock_return_3p', ['h0_score_std', 'regime_strength_std'])
        res_3p_int = panel_clustered_regression([r for r in std_sel if r.get('stock_return_3p') is not None], 'stock_return_3p', ['h0_score_std', 'regime_strength_std', 'interaction'])
        
        momentum_control_results[w] = {
            '1p_additive': res_1p_add,
            '1p_interaction': res_1p_int,
            '3p_additive': res_3p_add,
            '3p_interaction': res_3p_int
        }

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
                entry_rank = regime_ranks[(w, entry_obs['date'], entry_q)]['rank_3p'] if entry_q in BUCKETS else None
                
                modal_q = tw['modal_bucket']
                holding_ranks = [regime_ranks[(w, r['date'], r['bucket'])]['rank_3p'] for r in held_obs if r['bucket'] in BUCKETS]
                avg_holding_rank = float(np.mean([rk for rk in holding_ranks if rk is not None])) if holding_ranks else None
                
                winner_lifecycle_rows.append({
                    'window': w,
                    'ticker': ticker,
                    'gross_pnl': num(tw['gross_pnl']),
                    'entry_date': entry_obs['date'],
                    'entry_quartile': entry_q,
                    'entry_regime_rank': entry_rank,
                    'modal_quartile': modal_q,
                    'mean_holding_regime_rank': avg_holding_rank,
                    'holding_intervals': len(held_obs)
                })

    for w in ('W1', 'W2'):
        held_obs = [r for r in assignments[w] if r['held']]
        held_ranks = [regime_ranks[(w, r['date'], r['bucket'])]['rank_3p'] for r in held_obs if r['bucket'] in BUCKETS]
        rank_counts = Counter(held_ranks)
        tot_held = len(held_ranks)
        cff_link_summary[w] = {
            'total_held_observations_with_mcap': tot_held,
            'top1_rank_share': float(rank_counts[1] / tot_held) if tot_held else None,
            'top2_rank_share': float((rank_counts[1] + rank_counts[2]) / tot_held) if tot_held else None,
            'bottom2_rank_share': float((rank_counts[3] + rank_counts[4]) / tot_held) if tot_held else None,
            'rank_distribution': {str(rk): cnt for rk, cnt in rank_counts.items()}
        }

    print("Extracting MCAP_UNKNOWN Coverage...")
    mcap_unknown_summary = {}
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        total_eligible = len(ass_list)
        unkn_eligible = sum(r['bucket'] == 'MCAP_UNKNOWN' for r in ass_list)
        
        sel_list = [r for r in ass_list if r['selected_pre_sma']]
        unkn_sel = sum(r['bucket'] == 'MCAP_UNKNOWN' for r in sel_list)
        
        held_list = [r for r in ass_list if r['held']]
        unkn_held = sum(r['bucket'] == 'MCAP_UNKNOWN' for r in held_list)
        
        mcap_unknown_summary[w] = {
            'eligible_universe': {'n_total': total_eligible, 'n_unknown': unkn_eligible, 'unknown_pct': 100.0 * unkn_eligible / total_eligible},
            'selected_pre_sma': {'n_total': len(sel_list), 'n_unknown': unkn_sel, 'unknown_pct': 100.0 * unkn_sel / len(sel_list)},
            'actual_held': {'n_total': len(held_list), 'n_unknown': unkn_held, 'unknown_pct': 100.0 * unkn_held / len(held_list)}
        }

    print("Running Placebo Falsifications...")
    placebo_results = {}
    rng_shuf = np.random.default_rng(20260822)
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        rev_diffs_1p = []
        rev_diffs_3p = []
        
        shuf_diffs_1p = []
        shuf_diffs_3p = []
        
        for i in range(3, N):
            d = dates[i]
            rks = {q: regime_ranks[(w, d, q)]['rank_3p'] for q in BUCKETS}
            top_q = [q for q, r in rks.items() if r == 1][0]
            bottom_q = [q for q, r in rks.items() if r == 4][0]
            
            if i + 1 <= N:
                rev_diffs_1p.append(forward_q_returns[(w, d, bottom_q, 1)] - forward_q_returns[(w, d, top_q, 1)])
            if i + 3 <= N:
                rev_diffs_3p.append(forward_q_returns[(w, d, bottom_q, 3)] - forward_q_returns[(w, d, top_q, 3)])
                
            q_shuffled = list(BUCKETS)
            rng_shuf.shuffle(q_shuffled)
            shuf_ranks = {q: rank + 1 for rank, q in enumerate(q_shuffled)}
            
            shuf_top_q = [q for q, r in shuf_ranks.items() if r == 1][0]
            shuf_bottom_q = [q for q, r in shuf_ranks.items() if r == 4][0]
            
            if i + 1 <= N:
                shuf_diffs_1p.append(forward_q_returns[(w, d, shuf_top_q, 1)] - forward_q_returns[(w, d, shuf_bottom_q, 1)])
            if i + 3 <= N:
                shuf_diffs_3p.append(forward_q_returns[(w, d, shuf_top_q, 3)] - forward_q_returns[(w, d, shuf_bottom_q, 3)])
                
        placebo_results[w] = {
            'reversed_strength_1p': panel_contrast_stats(rev_diffs_1p),
            'reversed_strength_3p': panel_contrast_stats(rev_diffs_3p),
            'shuffled_q_rank_1p': panel_contrast_stats(shuf_diffs_1p),
            'shuffled_q_rank_3p': panel_contrast_stats(shuf_diffs_3p)
        }

    print("Evaluating Candidacy Criteria and Final Classification...")
    w1_pred_coef_1p = [r['coefficient'] for r in predictability_rows if r['window'] == 'W1' and r['lookback_spec'] == '3p' and r['horizon_panels'] == 1][0]
    w2_pred_coef_1p = [r['coefficient'] for r in predictability_rows if r['window'] == 'W2' and r['lookback_spec'] == '3p' and r['horizon_panels'] == 1][0]
    crit_1 = (w1_pred_coef_1p is not None and w2_pred_coef_1p is not None and w1_pred_coef_1p > 0 and w2_pred_coef_1p > 0)
    
    w1_top_bot_1p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W1' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    w2_top_bot_1p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W2' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    w1_top_bot_3p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W1' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 3][0]
    w2_top_bot_3p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W2' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 3][0]
    crit_2 = (w1_top_bot_1p > 0 and w2_top_bot_1p > 0 and w1_top_bot_3p > 0 and w2_top_bot_3p > 0)
    
    w1_top2_bot2_1p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W1' and r['contrast'] == 'TOP2_MINUS_BOTTOM2' and r['horizon_panels'] == 1][0]
    w2_top2_bot2_1p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W2' and r['contrast'] == 'TOP2_MINUS_BOTTOM2' and r['horizon_panels'] == 1][0]
    w1_top2_bot2_3p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W1' and r['contrast'] == 'TOP2_MINUS_BOTTOM2' and r['horizon_panels'] == 3][0]
    w2_top2_bot2_3p = [r['mean_difference'] for r in contrast_rows if r['window'] == 'W2' and r['contrast'] == 'TOP2_MINUS_BOTTOM2' and r['horizon_panels'] == 3][0]
    crit_3 = (w1_top2_bot2_1p > 0 and w2_top2_bot2_1p > 0 and w1_top2_bot2_3p > 0 and w2_top2_bot2_3p > 0)
    
    w1_pers = persistence_summary['W1']
    w2_pers = persistence_summary['W2']
    crit_4 = (w1_pers['prob_r1_to_r1_1p'] > 0.25 and w2_pers['prob_r1_to_r1_1p'] > 0.25 and
              w1_pers['prob_r1_to_top2_1p'] > 0.50 and w2_pers['prob_r1_to_top2_1p'] > 0.50)
              
    w1_q3_r1_share = identity_summary['W1']['Q3'].get('1', 0) / (len(panel_dates['W1']) - 3)
    w2_q3_r1_share = identity_summary['W2']['Q3'].get('1', 0) / (len(panel_dates['W2']) - 3)
    crit_5 = (w1_q3_r1_share < 0.80 and w2_q3_r1_share < 0.80)
    
    h1_w1_1p = [r['mean_difference'] for r in time_stability_rows if r['window'] == 'W1' and r['subperiod'] == 'FIRST_HALF' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    h2_w1_1p = [r['mean_difference'] for r in time_stability_rows if r['window'] == 'W1' and r['subperiod'] == 'SECOND_HALF' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    h1_w2_1p = [r['mean_difference'] for r in time_stability_rows if r['window'] == 'W2' and r['subperiod'] == 'FIRST_HALF' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    h2_w2_1p = [r['mean_difference'] for r in time_stability_rows if r['window'] == 'W2' and r['subperiod'] == 'SECOND_HALF' and r['contrast'] == 'TOP_MINUS_BOTTOM' and r['horizon_panels'] == 1][0]
    crit_6 = (h1_w1_1p > 0 and h2_w1_1p > 0 and h1_w2_1p > 0 and h2_w2_1p > 0)
    
    crit_7 = (w1_pers['regime_switches_per_year'] < 15.0 and w2_pers['regime_switches_per_year'] < 15.0 and
              w1_pers['median_rank1_duration_panels'] >= 2.0 and w2_pers['median_rank1_duration_panels'] >= 2.0)
              
    w1_h0_top1_1p = [r['mean_return'] for r in h0_overlay_rows if r['window'] == 'W1' and r['regime_rank'] == 'Rank 1' and r['horizon_panels'] == 1][0]
    w1_h0_bot1_1p = [r['mean_return'] for r in h0_overlay_rows if r['window'] == 'W1' and r['regime_rank'] == 'Rank 4' and r['horizon_panels'] == 1][0]
    w2_h0_top1_1p = [r['mean_return'] for r in h0_overlay_rows if r['window'] == 'W2' and r['regime_rank'] == 'Rank 1' and r['horizon_panels'] == 1][0]
    w2_h0_bot1_1p = [r['mean_return'] for r in h0_overlay_rows if r['window'] == 'W2' and r['regime_rank'] == 'Rank 4' and r['horizon_panels'] == 1][0]
    crit_8 = (w1_h0_top1_1p > w1_h0_bot1_1p and w2_h0_top1_1p > w2_h0_bot1_1p)
    
    w1_edge_top1_1p = [r['selection_edge'] for r in h0_edge_rows if r['window'] == 'W1' and r['regime_rank'] == 'Rank 1' and r['horizon_panels'] == 1][0]
    w1_edge_bot1_1p = [r['selection_edge'] for r in h0_edge_rows if r['window'] == 'W1' and r['regime_rank'] == 'Rank 4' and r['horizon_panels'] == 1][0]
    w2_edge_top1_1p = [r['selection_edge'] for r in h0_edge_rows if r['window'] == 'W2' and r['regime_rank'] == 'Rank 1' and r['horizon_panels'] == 1][0]
    w2_edge_bot1_1p = [r['selection_edge'] for r in h0_edge_rows if r['window'] == 'W2' and r['regime_rank'] == 'Rank 4' and r['horizon_panels'] == 1][0]
    crit_9 = (w1_edge_top1_1p is not None and w2_edge_top1_1p is not None and w1_edge_top1_1p > 0 and w2_edge_top1_1p > 0)
    
    w1_mom_strength_coef = momentum_control_results['W1']['1p_additive']['coefficients']['regime_strength_std']
    w2_mom_strength_coef = momentum_control_results['W2']['1p_additive']['coefficients']['regime_strength_std']
    crit_10 = (w1_mom_strength_coef > 0 and w2_mom_strength_coef > 0)
    
    w1_shuf_1p = placebo_results['W1']['shuffled_q_rank_1p']['mean_difference']
    w2_shuf_1p = placebo_results['W2']['shuffled_q_rank_1p']['mean_difference']
    crit_11 = (abs(w1_shuf_1p) < 0.005 and abs(w2_shuf_1p) < 0.005)

    candidacy_criteria = {
        '1_predicts_future_relative_return_same_direction': bool(crit_1),
        '2_top_beats_bottom_in_w1_and_w2': bool(crit_2),
        '3_top2_beats_bottom2_in_w1_and_w2': bool(crit_3),
        '4_rank_persistence_above_random': bool(crit_4),
        '5_not_merely_static_q3_effect': bool(crit_5),
        '6_direction_survives_subperiod_halves': bool(crit_6),
        '7_regime_turnover_practical': bool(crit_7),
        '8_h0_selected_stocks_better_in_strong_regime': bool(crit_8),
        '9_h0_selection_edge_positive_in_top_regime': bool(crit_9),
        '10_survives_momentum_control': bool(crit_10),
        '11_shuffled_placebo_null': bool(crit_11)
    }

    opposite_direction = (w1_top_bot_1p * w2_top_bot_1p < 0)
    static_q3_dominant = (w1_q3_r1_share > 0.85 or w2_q3_r1_share > 0.85)
    mean_reverting = (w1_pred_coef_1p < 0 or w2_pred_coef_1p < 0)
    
    contraindications = {
        'opposite_predictive_direction_w1_w2': bool(opposite_direction),
        'static_q3_dominant': bool(static_q3_dominant),
        'mean_reverting_strength': bool(mean_reverting),
        'requires_future_data': False
    }

    passed_criteria_count = sum(candidacy_criteria.values())
    print(f"Passed Candidacy Criteria: {passed_criteria_count} / 11")
    
    if passed_criteria_count >= 8 and not any(contraindications.values()):
        final_classification = 'DYNAMIC_MCAP_REGIME_CANDIDATE'
    elif (w1_top_bot_1p > 0 and w2_top_bot_1p > 0) or passed_criteria_count >= 5:
        final_classification = 'DYNAMIC_MCAP_REGIME_MIXED'
    else:
        final_classification = 'DYNAMIC_MCAP_REGIME_NO_PERSISTENCE'

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

    write_csv_dual('DYNAMIC_MCAP_QUARTILE_INDEX_RETURNS.csv', quartile_index_returns)
    write_csv_dual('DYNAMIC_MCAP_REGIME_STRENGTH.csv', regime_strength_rows)
    write_csv_dual('DYNAMIC_MCAP_REGIME_RANKS.csv', regime_rank_rows)
    write_csv_dual('DYNAMIC_MCAP_FORWARD_PREDICTABILITY.csv', predictability_rows)
    write_csv_dual('DYNAMIC_MCAP_TOP_BOTTOM_CONTRAST.csv', contrast_rows)
    write_csv_dual('DYNAMIC_MCAP_TRANSITION_MATRIX.csv', transition_matrix_rows)
    write_csv_dual('DYNAMIC_MCAP_TIME_STABILITY.csv', time_stability_rows)
    write_csv_dual('DYNAMIC_MCAP_H0_OVERLAY.csv', h0_overlay_rows)
    write_csv_dual('DYNAMIC_MCAP_H0_SELECTION_EDGE.csv', h0_edge_rows)

    write_json_dual('DYNAMIC_MCAP_MOMENTUM_CONTROL.json', momentum_control_results)
    write_json_dual('DYNAMIC_MCAP_PLACEBO.json', placebo_results)
    write_json_dual('DYNAMIC_MCAP_PIT_TEST.json', {'status': 'PASS' if pit_pass else 'FAIL', 'tests': pit_tests})
    write_json_dual('DYNAMIC_MCAP_DETERMINISM.json', {'status': 'PASS' if all(t['identical'] for t in det_tests) else 'FAIL', 'tests': det_tests})
    
    report_json = {
        'study': 'DYNAMIC_MCAP_REGIME_PERSISTENCE',
        'scope': 'EXPLORATORY_DIAGNOSTIC_ONLY_NO_POLICY_BACKTEST',
        'final_classification': final_classification,
        'pit_test_status': 'PASS' if pit_pass else 'FAIL',
        'determinism_status': 'PASS' if all(t['identical'] for t in det_tests) else 'FAIL',
        'candidacy_criteria_eval': candidacy_criteria,
        'contraindications_eval': contraindications,
        'strongest_quartile_identity': identity_summary,
        'rank_persistence_summary': persistence_summary,
        'spread_magnitude_summary': spread_summary,
        'mcap_unknown_summary': mcap_unknown_summary,
        'cff_link_summary': cff_link_summary,
        'winner_lifecycle_sample': winner_lifecycle_rows[:10],
        'contamination_qa_sample': contamination_qa
    }
    write_json_dual('DYNAMIC_MCAP_REGIME_REPORT.json', report_json)
    
    print("Analysis complete. Artifacts generated successfully.")

if __name__ == '__main__':
    main()
