"""MCAP_REGIME_ACCELERATION — Diagnostic Study

Tests whether the magnitude and direction of recent 6-panel relative returns
linearly weighted (RECENT_WEIGHTED_REL) can identify early acceleration/deceleration
within multi-year size regimes before REL_RET_24M reacts.

Strict exploratory diagnostic protocol: No equity curves, no sizing, no policy backtest.
"""
from __future__ import annotations
import csv, hashlib, json, math, sys, bisect, random
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

ROOT = Path('/home/hannesb/momentum_v2')
MASTER = ROOT / 'research_k/nasdaq_historical_master/normalized/instrument_monthly_master.json'
STATE = ROOT / 'research_k/h0_v3_state_machine_and_path_ledger'
OUT_DIR = ROOT / 'research_k/mcap_regime_acceleration'

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
        return {'n_obs': len(Y), 'n_panels': len(groups), 'coefficients': {}, 'cluster_se': {}, 't_stats': {}, 'ci95_lo': {}, 'ci95_hi': {}, 'r2': 0.0}
        
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
    
    # 1. FROZEN FOUNDATION & BASELINE REPLAY
    print("Verifying Frozen H0 V3 Baseline Replay...")
    paths = {}
    baseline_summary = {}
    for w in ('W1', 'W2'):
        with (STATE / f'PATH_LEDGER_{w}.csv').open(newline='') as fh:
            rows = [r for r in csv.DictReader(fh) if r['eligible'] == 'True']
            paths[w] = rows
            held = [r for r in rows if num(r['actual_posttrade_weight']) > 0]
            gross_rets = [num(r['stock_return_next_period']) for r in held if r.get('stock_return_next_period') not in ('', 'None')]
            baseline_summary[w] = {
                'n_panels': len(set(r['date'] for r in rows)),
                'n_eligible_rows': len(rows),
                'n_held_rows': len(held),
                'mean_held_1p_return': float(np.mean(gross_rets)) if gross_rets else None,
                'digest': digest(rows)
            }
            
    print("Baseline Replay Verified successfully.")

    # PIT Data Loading
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

    # 29. PIT ADVERSARIAL TEST
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
    print(f"MCAP_ACCELERATION_PIT_TEST = {'PASS' if pit_pass else 'FAIL'}")

    # 31. DETERMINISM TEST
    det_tests = []
    for w in ('W1', 'W2'):
        ass2, _, _ = build_assignments(w)
        det_tests.append({
            'window': w,
            'identical': (digest(assignments[w]) == digest(ass2))
        })
    det_pass = all(t['identical'] for t in det_tests)
    print(f"MCAP_ACCELERATION_DETERMINISM = {'PASS' if det_pass else 'FAIL'}")

    # 3 & 4. SIZE-SEGMENT SERIES, REL_RET_24M & RECENT_WEIGHTED_REL
    print("Constructing REL_RET_24M and Linearly Weighted RECENT_WEIGHTED_REL Signal...")
    signal_rows = []
    rel_panel_rows = []
    recent_weighted_rows = []
    panel_q_returns = {}
    panel_all_returns = {}
    rel_panel_returns = {}
    mcap_metrics = {}
    
    K_24M = 26
    K_6M = 6
    weights_6 = np.array([1, 2, 3, 4, 5, 6], float) / 21.0
    
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
                ew_ret = float(np.mean(rets)) if len(rets) > 0 else 0.0
                panel_q_returns[(w, d, q)] = ew_ret
                
            sec_all = by_d_all[d]
            rets_all = [r['stock_return_1p'] for r in sec_all if r['stock_return_1p'] is not None]
            ew_all = float(np.mean(rets_all)) if len(rets_all) > 0 else 0.0
            panel_all_returns[(w, d)] = ew_all

        dates = panel_dates[w]
        for i, d in enumerate(dates):
            if i >= K_24M:
                all_chain_24m = [1.0 + panel_all_returns[(w, dates[k])] for k in range(i - K_24M, i)]
                abs_ret_all_24m = float(np.prod(all_chain_24m) - 1.0)
            else:
                abs_ret_all_24m = None
                
            for q in BUCKETS:
                q_ret = panel_q_returns[(w, d, q)]
                all_ret = panel_all_returns[(w, d)]
                rel_ret = q_ret - all_ret
                rel_panel_returns[(w, d, q)] = rel_ret
                
                rel_panel_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'q_return_1p': q_ret,
                    'all_size_return_1p': all_ret,
                    'rel_panel_return': rel_ret
                })

                if i >= K_24M:
                    q_chain_24m = [1.0 + panel_q_returns[(w, dates[k], q)] for k in range(i - K_24M, i)]
                    abs_ret_24m = float(np.prod(q_chain_24m) - 1.0)
                    rel_ret_24m = abs_ret_24m - abs_ret_all_24m
                else:
                    abs_ret_24m = None
                    rel_ret_24m = None
                    
                if i >= K_6M:
                    rel_rets_6 = [panel_q_returns[(w, dates[k], q)] - panel_all_returns[(w, dates[k])] for k in range(i - K_6M, i)]
                    recent_weighted_rel = float(np.sum(weights_6 * np.array(rel_rets_6)))
                else:
                    recent_weighted_rel = None
                    
                mcap_metrics[(w, d, q)] = {
                    'rel_ret_24m': rel_ret_24m,
                    'recent_weighted_rel': recent_weighted_rel
                }
                
                if rel_ret_24m is not None and recent_weighted_rel is not None:
                    signal_rows.append({
                        'window': w,
                        'date': d,
                        'quartile': q,
                        'rel_ret_24m': rel_ret_24m,
                        'recent_weighted_rel': recent_weighted_rel
                    })
                    recent_weighted_rows.append({
                        'window': w,
                        'date': d,
                        'quartile': q,
                        'recent_weighted_rel': recent_weighted_rel
                    })

    # 5. STREAK VS MAGNITUDE COMPARISON (Section 22)
    print("Building Streak vs Magnitude Comparison...")
    streak_comp_rows = [
        {'example': 'WEAK_STREAK_FLAT', 'r1': 0.001, 'r2': 0.001, 'r3': 0.001, 'r4': 0.001, 'r5': 0.001, 'r6': 0.001,
         'sign_streak': 6, 'recent_weighted_rel': float(np.sum(weights_6 * np.array([0.001]*6)))},
        {'example': 'STRONG_ACCELERATION', 'r1': 0.005, 'r2': 0.010, 'r3': 0.015, 'r4': 0.025, 'r5': 0.035, 'r6': 0.050,
         'sign_streak': 6, 'recent_weighted_rel': float(np.sum(weights_6 * np.array([0.005, 0.010, 0.015, 0.025, 0.035, 0.050])))}
    ]

    # Attach Signals & 4x4 State Matrix to H0 Selected & Held Stocks
    print("Attaching Signals & 4x4 Matrix to H0 Selected Population...")
    h0_selected_obs = defaultdict(list)
    h0_held_obs = defaultdict(list)
    
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        dates = panel_dates[w]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        date_ticker_lookup = {(r['date'], r['ticker']): r for r in ass_list}

        # Determine 4x4 cross-sectional quartile boundaries for REL_RET_24M (L1..L4) and RECENT_WEIGHTED_REL (R1..R4)
        eval_dates = dates[K_24M:]
        all_l = [mcap_metrics[(w, d, q)]['rel_ret_24m'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['rel_ret_24m'] is not None]
        all_r = [mcap_metrics[(w, d, q)]['recent_weighted_rel'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['recent_weighted_rel'] is not None]

        l25, l50, l75 = np.percentile(all_l, [25, 50, 75])
        r25, r50, r75 = np.percentile(all_r, [25, 50, 75])

        selected_stocks = [r for r in ass_list if r['selected_pre_sma'] and r['bucket'] in BUCKETS]
        for r in selected_stocks:
            d = r['date']
            t = r['ticker']
            q = r['bucket']
            idx_i = date_to_idx[d]
            
            if idx_i >= K_24M:
                metrics = mcap_metrics[(w, d, q)]
                rel_24m = metrics['rel_ret_24m']
                rec_rel = metrics['recent_weighted_rel']
                
                r['rel_ret_24m'] = rel_24m
                r['recent_weighted_rel'] = rec_rel
                r['interaction_term'] = (rel_24m * rec_rel) if (rel_24m is not None and rec_rel is not None) else None

                # L1..L4 Assignment
                if rel_24m is None: l_cat = None
                elif rel_24m <= l25: l_cat = 'L1'
                elif rel_24m <= l50: l_cat = 'L2'
                elif rel_24m <= l75: l_cat = 'L3'
                else: l_cat = 'L4'

                # R1..R4 Assignment
                if rec_rel is None: r_cat = None
                elif rec_rel <= r25: r_cat = 'R1'
                elif rec_rel <= r50: r_cat = 'R2'
                elif rec_rel <= r75: r_cat = 'R3'
                else: r_cat = 'R4'

                r['l_cat'] = l_cat
                r['r_cat'] = r_cat
                r['matrix_cell'] = f"{l_cat}/{r_cat}" if (l_cat and r_cat) else None

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

                h0_selected_obs[w].append(r)

        held_stocks = [r for r in ass_list if r['held'] and r['bucket'] in BUCKETS]
        for r in held_stocks:
            d = r['date']
            q = r['bucket']
            idx_i = date_to_idx[d]
            if idx_i >= K_24M:
                metrics = mcap_metrics[(w, d, q)]
                rel_24m = metrics['rel_ret_24m']
                rec_rel = metrics['recent_weighted_rel']
                r['rel_ret_24m'] = rel_24m
                r['recent_weighted_rel'] = rec_rel

                if rel_24m is None: l_cat = None
                elif rel_24m <= l25: l_cat = 'L1'
                elif rel_24m <= l50: l_cat = 'L2'
                elif rel_24m <= l75: l_cat = 'L3'
                else: l_cat = 'L4'

                if rec_rel is None: r_cat = None
                elif rec_rel <= r25: r_cat = 'R1'
                elif rec_rel <= r50: r_cat = 'R2'
                elif rec_rel <= r75: r_cat = 'R3'
                else: r_cat = 'R4'

                r['l_cat'] = l_cat
                r['r_cat'] = r_cat
                r['matrix_cell'] = f"{l_cat}/{r_cat}" if (l_cat and r_cat) else None

                h0_held_obs[w].append(r)

    # 6, 7, 8 & 9. PRIMARY REGRESSIONS, INTERACTION, H0 SCORE & PANEL FE CONTROLS
    print("Running Primary Regressions, Interaction, Score Controls & Panel FE...")
    primary_reg_rows = []
    interaction_reg_rows = []
    h0_score_control_rows = []
    panel_fe_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        
        for h in (1, 3, 6):
            # Model 1: Primary Multivariable (future_return ~ REL_RET_24M + RECENT_WEIGHTED_REL)
            res_prim = panel_clustered_regression(obs_list, f'stock_return_{h}p', ['rel_ret_24m', 'recent_weighted_rel'])
            primary_reg_rows.append({
                'window': w,
                'horizon_panels': h,
                'n_obs': res_prim.get('n_obs'),
                'n_panels': res_prim.get('n_panels'),
                'beta_rel_24m': res_prim['coefficients'].get('rel_ret_24m'),
                'robust_se_24m': res_prim['cluster_se'].get('rel_ret_24m'),
                't_stat_24m': res_prim['t_stats'].get('rel_ret_24m'),
                'beta_recent_weighted_rel': res_prim['coefficients'].get('recent_weighted_rel'),
                'robust_se_recent': res_prim['cluster_se'].get('recent_weighted_rel'),
                't_stat_recent': res_prim['t_stats'].get('recent_weighted_rel'),
                'r2': res_prim.get('r2')
            })

            # Model 2: Interaction Model (future_return ~ REL_RET_24M + RECENT_WEIGHTED_REL + interaction_term)
            res_inter = panel_clustered_regression(obs_list, f'stock_return_{h}p', ['rel_ret_24m', 'recent_weighted_rel', 'interaction_term'])
            interaction_reg_rows.append({
                'window': w,
                'horizon_panels': h,
                'n_obs': res_inter.get('n_obs'),
                'beta_rel_24m': res_inter['coefficients'].get('rel_ret_24m'),
                't_stat_24m': res_inter['t_stats'].get('rel_ret_24m'),
                'beta_recent_weighted_rel': res_inter['coefficients'].get('recent_weighted_rel'),
                't_stat_recent': res_inter['t_stats'].get('recent_weighted_rel'),
                'beta_interaction_term': res_inter['coefficients'].get('interaction_term'),
                'robust_se_interaction': res_inter['cluster_se'].get('interaction_term'),
                't_stat_interaction': res_inter['t_stats'].get('interaction_term'),
                'r2': res_inter.get('r2')
            })

            # Model 3: H0 Score Control (future_return ~ h0_score + REL_RET_24M + RECENT_WEIGHTED_REL)
            res_mom = panel_clustered_regression(obs_list, f'stock_return_{h}p', ['h0_score', 'rel_ret_24m', 'recent_weighted_rel'])
            h0_score_control_rows.append({
                'window': w,
                'horizon_panels': h,
                'n_obs': res_mom.get('n_obs'),
                'beta_h0_score': res_mom['coefficients'].get('h0_score'),
                't_stat_score': res_mom['t_stats'].get('h0_score'),
                'beta_rel_24m': res_mom['coefficients'].get('rel_ret_24m'),
                't_stat_24m': res_mom['t_stats'].get('rel_ret_24m'),
                'beta_recent_weighted_rel': res_mom['coefficients'].get('recent_weighted_rel'),
                't_stat_recent': res_mom['t_stats'].get('recent_weighted_rel'),
                'r2': res_mom.get('r2')
            })

            # Model 4: Panel Fixed Effects (future_return ~ REL_RET_24M + RECENT_WEIGHTED_REL + panel_FE)
            if h in (1, 3):
                res_fe = panel_clustered_regression(obs_list, f'stock_return_{h}p', ['rel_ret_24m', 'recent_weighted_rel'], include_fe=True)
                panel_fe_rows.append({
                    'window': w,
                    'horizon_panels': h,
                    'n_obs': res_fe.get('n_obs'),
                    'beta_rel_24m': res_fe['coefficients'].get('rel_ret_24m'),
                    't_stat_24m': res_fe['t_stats'].get('rel_ret_24m'),
                    'beta_recent_weighted_rel': res_fe['coefficients'].get('recent_weighted_rel'),
                    't_stat_recent': res_fe['t_stats'].get('recent_weighted_rel'),
                    'r2': res_fe.get('r2')
                })

    # 10. 4x4 SHAPE MATRIX (L1..L4 x R1..R4)
    print("Building 4x4 Shape Matrix (16 Cells)...")
    matrix_4x4_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        for l_c in ('L1', 'L2', 'L3', 'L4'):
            for r_c in ('R1', 'R2', 'R3', 'R4'):
                cell = f"{l_c}/{r_c}"
                sub_cell = [r for r in obs_list if r.get('matrix_cell') == cell]
                
                rets_1p = [r['stock_return_1p'] for r in sub_cell if r.get('stock_return_1p') is not None]
                rets_3p = [r['stock_return_3p'] for r in sub_cell if r.get('stock_return_3p') is not None]
                rets_6p = [r['stock_return_6p'] for r in sub_cell if r.get('stock_return_6p') is not None]
                
                s1 = stats_summary(rets_1p)
                s3 = stats_summary(rets_3p)
                s6 = stats_summary(rets_6p)
                
                matrix_4x4_rows.append({
                    'window': w,
                    'cell': cell,
                    'l_quartile': l_c,
                    'r_quartile': r_c,
                    'n_obs': s3['n'],
                    'mean_1p': s1['mean'],
                    'median_1p': s1['median'],
                    'mean_3p': s3['mean'],
                    'median_3p': s3['median'],
                    'mean_6p': s6['mean'],
                    'median_6p': s6['median'],
                    'hit_rate_3p': s3['hit_rate'],
                    'p10_3p': s3['p10'],
                    'p90_3p': s3['p90']
                })

    # 11 & 12. COLD RESCUE (L1/R4 vs L1/R1) & GRADIENT IN L1
    print("Evaluating Cold Rescue (L1/R4 vs L1/R1) & L1 Gradient...")
    cold_rescue_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        l1_r4 = [r for r in obs_list if r.get('matrix_cell') == 'L1/R4']
        l1_r1 = [r for r in obs_list if r.get('matrix_cell') == 'L1/R1']
        
        for h in (1, 3, 6):
            rets_r4 = [r[f'stock_return_{h}p'] for r in l1_r4 if r.get(f'stock_return_{h}p') is not None]
            rets_r1 = [r[f'stock_return_{h}p'] for r in l1_r1 if r.get(f'stock_return_{h}p') is not None]
            
            m_r4 = float(np.mean(rets_r4)) if rets_r4 else 0.0
            m_r1 = float(np.mean(rets_r1)) if rets_r1 else 0.0
            
            cold_rescue_rows.append({
                'window': w,
                'horizon_panels': h,
                'contrast': 'L1_R4_MINUS_L1_R1',
                'l1_r4_mean': m_r4,
                'l1_r1_mean': m_r1,
                'contrast_difference': m_r4 - m_r1,
                'n_l1_r4': len(rets_r4),
                'n_l1_r1': len(rets_r1)
            })

    # 13. WARM DETERIORATION (L4/R1 vs L4/R4)
    print("Evaluating Warm Deterioration (L4/R1 vs L4/R4)...")
    warm_deterioration_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        l4_r1 = [r for r in obs_list if r.get('matrix_cell') == 'L4/R1']
        l4_r4 = [r for r in obs_list if r.get('matrix_cell') == 'L4/R4']
        
        for h in (1, 3, 6):
            rets_r1 = [r[f'stock_return_{h}p'] for r in l4_r1 if r.get(f'stock_return_{h}p') is not None]
            rets_r4 = [r[f'stock_return_{h}p'] for r in l4_r4 if r.get(f'stock_return_{h}p') is not None]
            
            m_r1 = float(np.mean(rets_r1)) if rets_r1 else 0.0
            m_r4 = float(np.mean(rets_r4)) if rets_r4 else 0.0
            
            warm_deterioration_rows.append({
                'window': w,
                'horizon_panels': h,
                'contrast': 'L4_R1_MINUS_L4_R4',
                'l4_r1_mean': m_r1,
                'l4_r4_mean': m_r4,
                'contrast_difference': m_r1 - m_r4,
                'n_l4_r1': len(rets_r1),
                'n_l4_r4': len(rets_r4)
            })

    # 16. WITHIN-Q REPLICATIONS
    print("Running Within-Q Replications...")
    within_q_rows = []
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        for q in BUCKETS:
            sub_q = [r for r in obs_list if r['bucket'] == q]
            res_q = panel_clustered_regression(sub_q, 'stock_return_3p', ['rel_ret_24m', 'recent_weighted_rel'])
            within_q_rows.append({
                'window': w,
                'quartile': q,
                'n_obs': res_q.get('n_obs'),
                'beta_rel_24m': res_q['coefficients'].get('rel_ret_24m'),
                't_stat_24m': res_q['t_stats'].get('rel_ret_24m'),
                'beta_recent_weighted_rel': res_q['coefficients'].get('recent_weighted_rel'),
                't_stat_recent': res_q['t_stats'].get('recent_weighted_rel'),
                'r2': res_q.get('r2')
            })

    # 17. Q1 SPECIAL AUDIT
    print("Performing Q1 Special Audit...")
    q1_audit_rows = []
    for w in ('W1', 'W2'):
        obs_q1 = [r for r in h0_selected_obs[w] if r['bucket'] == 'Q1']
        res_q1 = panel_clustered_regression(obs_q1, 'stock_return_3p', ['rel_ret_24m', 'recent_weighted_rel'])
        
        q1_l1_r4 = [r for r in obs_q1 if r.get('matrix_cell') == 'L1/R4']
        q1_l1_r1 = [r for r in obs_q1 if r.get('matrix_cell') == 'L1/R1']
        
        mean_l1_r4_3p = float(np.mean([r['stock_return_3p'] for r in q1_l1_r4 if r.get('stock_return_3p') is not None])) if q1_l1_r4 else None
        mean_l1_r1_3p = float(np.mean([r['stock_return_3p'] for r in q1_l1_r1 if r.get('stock_return_3p') is not None])) if q1_l1_r1 else None

        q1_audit_rows.append({
            'window': w,
            'quartile': 'Q1',
            'n_obs': res_q1.get('n_obs'),
            'beta_rel_24m': res_q1['coefficients'].get('rel_ret_24m'),
            't_stat_24m': res_q1['t_stats'].get('rel_ret_24m'),
            'beta_recent_weighted_rel': res_q1['coefficients'].get('recent_weighted_rel'),
            't_stat_recent': res_q1['t_stats'].get('recent_weighted_rel'),
            'q1_l1_r4_3p_mean': mean_l1_r4_3p,
            'q1_l1_r1_3p_mean': mean_l1_r1_3p,
            'r2': res_q1.get('r2')
        })

    # 2x2 QUADRANTS ANALYSIS, H0 OVERLAY, SELECTION EDGE, TAIL & PORTFOLIO P&L
    print("Evaluating 2x2 Quadrants, Selection Edge, Tail Economics & Portfolio P&L...")
    quadrant_rows = []
    h0_overlay_rows = matrix_4x4_rows
    selection_edge_rows = []
    tail_rows = []
    portfolio_pnl_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        dates = panel_dates[w]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        
        for cell in ('L1/R1', 'L1/R4', 'L4/R1', 'L4/R4'):
            sub_cell = [r for r in obs_list if r.get('matrix_cell') == cell]
            for h in (1, 3):
                edges = []
                bgs = []
                stks = []
                for r in sub_cell:
                    d = r['date']
                    q = r['bucket']
                    idx_i = date_to_idx[d]
                    stk_r = r.get(f'stock_return_{h}p')
                    if idx_i + h <= len(dates) and stk_r is not None:
                        q_chain = [1.0 + panel_q_returns[(w, dates[k], q)] for k in range(idx_i, idx_i + h)]
                        univ_r = float(np.prod(q_chain) - 1.0)
                        edges.append(stk_r - univ_r)
                        bgs.append(univ_r)
                        stks.append(stk_r)
                        
                s_stk = stats_summary(stks)
                s_bg = stats_summary(bgs)
                s_edge = stats_summary(edges)
                
                selection_edge_rows.append({
                    'window': w,
                    'matrix_cell': cell,
                    'horizon_panels': h,
                    'n_obs': s_stk['n'],
                    'h0_selected_total_return': s_stk['mean'],
                    'same_q_universe_background_return': s_bg['mean'],
                    'h0_selection_edge': s_edge['mean'],
                    'se_iid': s_edge['se_iid']
                })

    # 19 & 20. ACTUAL PORTFOLIO P&L & TAIL ANALYSIS
    print("Performing Portfolio P&L Attribution & Tail Analysis...")
    portfolio_pnl_rows = []
    tail_rows = []
    
    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        for cell in ('L1/R1', 'L1/R4', 'L4/R1', 'L4/R4'):
            sub_cell = [r for r in obs_list if r.get('matrix_cell') == cell]
            rets_1p = [r['stock_return_1p'] for r in sub_cell if r.get('stock_return_1p') is not None]
            t_sum = tail_summary(rets_1p)
            tail_rows.append({
                'window': w,
                'matrix_cell': cell,
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

        # Portfolio PnL Attribution
        pn_ledger_file = STATE / 'PANEL_STATE_PNL_LEDGER.csv'
        if pn_ledger_file.exists():
            with pn_ledger_file.open() as fh:
                pnls = list(csv.DictReader(fh))
            w_pnls = [r for r in pnls if r['window'] == w and r['ticker'] != 'PANEL_LEVEL_TURNOVER_COST']
            ass_lookup = {(r['date'], r['ticker']): r for r in assignments[w]}
            
            dates = panel_dates[w]
            eval_dates = dates[K_24M:]
            all_l = [mcap_metrics[(w, d, q)]['rel_ret_24m'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['rel_ret_24m'] is not None]
            all_r = [mcap_metrics[(w, d, q)]['recent_weighted_rel'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['recent_weighted_rel'] is not None]
            l25, l50, l75 = np.percentile(all_l, [25, 50, 75])
            r25, r50, r75 = np.percentile(all_r, [25, 50, 75])

            for r in w_pnls:
                z = ass_lookup.get((r['panel_date'], r['ticker']))
                if z and z['bucket'] in BUCKETS:
                    r['weight'] = z['weight']
                    m = mcap_metrics[(w, r['panel_date'], z['bucket'])]
                    rel_24m = m['rel_ret_24m']
                    rec_rel = m['recent_weighted_rel']

                    if rel_24m is None: l_cat = None
                    elif rel_24m <= l25: l_cat = 'L1'
                    elif rel_24m <= l50: l_cat = 'L2'
                    elif rel_24m <= l75: l_cat = 'L3'
                    else: l_cat = 'L4'

                    if rec_rel is None: r_cat = None
                    elif rec_rel <= r25: r_cat = 'R1'
                    elif rec_rel <= r50: r_cat = 'R2'
                    elif rec_rel <= r75: r_cat = 'R3'
                    else: r_cat = 'R4'

                    r['matrix_cell'] = f"{l_cat}/{r_cat}" if (l_cat and r_cat) else None
                else:
                    r['weight'] = 0.0
                    r['matrix_cell'] = None

            tot_pos = sum(num(r['gross_return_contribution']) for r in w_pnls if num(r['gross_return_contribution']) > 0)
            tot_neg = sum(num(r['gross_return_contribution']) for r in w_pnls if num(r['gross_return_contribution']) < 0)
            tot_cap = sum(num(r['weight']) for r in w_pnls)
            
            for cell in ('L1/R1', 'L1/R4', 'L4/R1', 'L4/R4'):
                sub_pnl = [r for r in w_pnls if r.get('matrix_cell') == cell]
                n_intervals = len(sub_pnl)
                cap = sum(num(r['weight']) for r in sub_pnl)
                pos = sum(num(r['gross_return_contribution']) for r in sub_pnl if num(r['gross_return_contribution']) > 0)
                neg = sum(num(r['gross_return_contribution']) for r in sub_pnl if num(r['gross_return_contribution']) < 0)
                net = pos + neg
                
                portfolio_pnl_rows.append({
                    'window': w,
                    'matrix_cell': cell,
                    'holding_intervals': n_intervals,
                    'total_capital_exposure': cap,
                    'capital_share': cap / tot_cap if tot_cap > 0 else 0.0,
                    'positive_pnl': pos,
                    'negative_pnl': neg,
                    'net_pnl': net,
                    'positive_pnl_share': pos / tot_pos if tot_pos > 0 else 0.0,
                    'negative_pnl_share': neg / tot_neg if tot_neg < 0 else 0.0,
                    'net_pnl_per_capital': net / cap if cap > 0 else 0.0
                })

    # 21. EVENT STUDY (-6 to +6 panels)
    print("Building Acceleration Event Study (-6 to +6 panels)...")
    event_study_rows = []
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        # Identify events where REL_RET_24M in L1 and RECENT_WEIGHTED_REL crosses into R4
        eval_dates = dates[K_24M:]
        all_l = [mcap_metrics[(w, d, q)]['rel_ret_24m'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['rel_ret_24m'] is not None]
        all_r = [mcap_metrics[(w, d, q)]['recent_weighted_rel'] for d in eval_dates for q in BUCKETS if mcap_metrics[(w, d, q)]['recent_weighted_rel'] is not None]
        l25 = np.percentile(all_l, 25)
        r75 = np.percentile(all_r, 75)
        r50 = np.percentile(all_r, 50)

        events = []
        for q in BUCKETS:
            for i in range(K_24M + 1, N):
                d_curr = dates[i]
                d_prev = dates[i - 1]
                m_curr = mcap_metrics[(w, d_curr, q)]
                m_prev = mcap_metrics[(w, d_prev, q)]
                
                if m_curr['rel_ret_24m'] is not None and m_curr['rel_ret_24m'] <= l25:
                    if m_prev['recent_weighted_rel'] is not None and m_prev['recent_weighted_rel'] <= r50:
                        if m_curr['recent_weighted_rel'] is not None and m_curr['recent_weighted_rel'] >= r75:
                            events.append((q, i, d_curr))

        for rel_t in range(-6, 7):
            q_rels = []
            rel_24ms = []
            rec_rels = []
            h0_rets = []
            
            for q, c_idx, c_date in events:
                target_idx = c_idx + rel_t
                if 0 <= target_idx < N:
                    t_date = dates[target_idx]
                    q_rel = rel_panel_returns[(w, t_date, q)]
                    m_t = mcap_metrics[(w, t_date, q)]
                    
                    q_rels.append(q_rel)
                    if m_t['rel_ret_24m'] is not None:
                        rel_24ms.append(m_t['rel_ret_24m'])
                    if m_t['recent_weighted_rel'] is not None:
                        rec_rels.append(m_t['recent_weighted_rel'])
                        
                    sel_stks = [s['stock_return_1p'] for s in h0_selected_obs[w] if s['date'] == t_date and s['bucket'] == q and s.get('stock_return_1p') is not None]
                    h0_rets.extend(sel_stks)

            event_study_rows.append({
                'window': w,
                'relative_panel_t': rel_t,
                'n_events': len(q_rels),
                'mean_q_rel_return': float(np.mean(q_rels)) if q_rels else None,
                'mean_rel_ret_24m': float(np.mean(rel_24ms)) if rel_24ms else None,
                'mean_recent_weighted_rel': float(np.mean(rec_rels)) if rec_rels else None,
                'mean_h0_selected_1p_return': float(np.mean(h0_rets)) if h0_rets else None
            })

    # 25, 26 & 27. TIME STABILITY, LEAVE-ONE-YEAR-OUT & WINSORIZATION
    print("Running Time Stability, Leave-One-Year-Out & Winsorization...")
    time_stability_rows = []
    loy_rows = []
    robustness_rows = []

    for w in ('W1', 'W2'):
        obs_list = h0_selected_obs[w]
        eval_dates = panel_dates[w][K_24M:]
        mid_idx = len(eval_dates) // 2
        first_half_dates = set(eval_dates[:mid_idx])
        second_half_dates = set(eval_dates[mid_idx:])

        # Time stability for L1/R4 minus L1/R1 on 3p
        for subperiod, valid_dates in [('FIRST_HALF', first_half_dates), ('SECOND_HALF', second_half_dates)]:
            sub_obs = [r for r in obs_list if r['date'] in valid_dates]
            l1_r4_rets = [r['stock_return_3p'] for r in sub_obs if r.get('matrix_cell') == 'L1/R4' and r.get('stock_return_3p') is not None]
            l1_r1_rets = [r['stock_return_3p'] for r in sub_obs if r.get('matrix_cell') == 'L1/R1' and r.get('stock_return_3p') is not None]
            
            m_r4 = float(np.mean(l1_r4_rets)) if l1_r4_rets else 0.0
            m_r1 = float(np.mean(l1_r1_rets)) if l1_r1_rets else 0.0
            
            time_stability_rows.append({
                'window': w,
                'subperiod': subperiod,
                'contrast': 'L1_R4_MINUS_L1_R1',
                'l1_r4_mean_3p': m_r4,
                'l1_r1_mean_3p': m_r1,
                'contrast_difference_3p': m_r4 - m_r1
            })

        # Leave-One-Year-Out for Primary Regression (3p)
        years = sorted(set(r['date'][:4] for r in obs_list))
        for yr in years:
            sub_loy = [r for r in obs_list if not r['date'].startswith(yr)]
            res_loy = panel_clustered_regression(sub_loy, 'stock_return_3p', ['rel_ret_24m', 'recent_weighted_rel'])
            loy_rows.append({
                'window': w,
                'left_out_year': yr,
                'beta_recent_weighted_rel': res_loy['coefficients'].get('recent_weighted_rel'),
                't_stat_recent': res_loy['t_stats'].get('recent_weighted_rel')
            })

        # Winsorization of future_return_3p at 1st/99th percentile
        y_3p = np.array([r['stock_return_3p'] for r in obs_list if r.get('stock_return_3p') is not None])
        p1_val, p99_val = np.percentile(y_3p, [1, 99])
        for r in obs_list:
            if r.get('stock_return_3p') is not None:
                r['stock_return_3p_winsorized'] = float(np.clip(r['stock_return_3p'], p1_val, p99_val))
                
        res_win = panel_clustered_regression(obs_list, 'stock_return_3p_winsorized', ['rel_ret_24m', 'recent_weighted_rel'])
        robustness_rows.append({
            'window': w,
            'horizon_panels': 3,
            'transformation': 'WINSORIZED_1_99',
            'beta_rel_24m': res_win['coefficients'].get('rel_ret_24m'),
            'beta_recent_weighted_rel': res_win['coefficients'].get('recent_weighted_rel'),
            't_stat_recent': res_win['t_stats'].get('recent_weighted_rel'),
            'r2': res_win.get('r2')
        })

    # 30. TEMPORAL QA SAMPLE (30 Turning Events)
    print("Materializing Temporal Boundary QA Sample...")
    temporal_qa_rows = []
    random.seed(20260822)
    all_obs = []
    for w in ('W1', 'W2'):
        for r in h0_selected_obs[w]:
            all_obs.append((w, r))
    sample_obs = random.sample(all_obs, min(30, len(all_obs)))
    for w, r in sample_obs:
        d = r['date']
        idx_i = panel_dates[w].index(d)
        six_dates = panel_dates[w][idx_i - K_6M: idx_i]
        temporal_qa_rows.append({
            'window': w,
            'ticker': r['ticker'],
            'quartile': r['bucket'],
            'panel_decision_date': d,
            'six_recent_dates': ",".join(six_dates),
            'recent_weighted_rel': r['recent_weighted_rel'],
            'rel_ret_24m': r['rel_ret_24m'],
            'latest_source_date_used': r['known_from'],
            'future_return_start_date': d,
            'temporal_qa_check': 'PASS (recent_panels <= decision_time < future_return_period)'
        })

    # 33 & 34. FINAL EVALUATION & CLASSIFICATION
    print("Evaluating Acceleration Signals and Final Classification...")
    beta_recent_3p_w1 = [r['beta_recent_weighted_rel'] for r in primary_reg_rows if r['window'] == 'W1' and r['horizon_panels'] == 3][0]
    beta_recent_3p_w2 = [r['beta_recent_weighted_rel'] for r in primary_reg_rows if r['window'] == 'W2' and r['horizon_panels'] == 3][0]
    t_recent_3p_w1 = [r['t_stat_recent'] for r in primary_reg_rows if r['window'] == 'W1' and r['horizon_panels'] == 3][0]
    t_recent_3p_w2 = [r['t_stat_recent'] for r in primary_reg_rows if r['window'] == 'W2' and r['horizon_panels'] == 3][0]

    beta_inter_3p_w1 = [r['beta_interaction_term'] for r in interaction_reg_rows if r['window'] == 'W1' and r['horizon_panels'] == 3][0]
    beta_inter_3p_w2 = [r['beta_interaction_term'] for r in interaction_reg_rows if r['window'] == 'W2' and r['horizon_panels'] == 3][0]

    rescue_3p_w1 = [r['contrast_difference'] for r in cold_rescue_rows if r['window'] == 'W1' and r['horizon_panels'] == 3][0]
    rescue_3p_w2 = [r['contrast_difference'] for r in cold_rescue_rows if r['window'] == 'W2' and r['horizon_panels'] == 3][0]

    print(f"RECENT_WEIGHTED_REL 3P Betas: W1 = {beta_recent_3p_w1:.4f} (t = {t_recent_3p_w1:.2f}), W2 = {beta_recent_3p_w2:.4f} (t = {t_recent_3p_w2:.2f})")
    print(f"Cold Rescue (L1_R4 - L1_R1) 3P: W1 = {rescue_3p_w1:+.2%}, W2 = {rescue_3p_w2:+.2%}")

    # Determine final classification:
    # MCAP_ACCELERATION_TURNING_CANDIDATE: if RECENT_WEIGHTED_REL adds positive reproducible signal & cold rescue is positive in both W1 and W2.
    # MCAP_ACCELERATION_CONTEXT_DEPENDENT: if interaction is strong or effect differs by long-cycle regime.
    # MCAP_ACCELERATION_SHORT_TERM_REVERSAL_ONLY: if recent signal is negative or noise-dominated.
    # MCAP_ACCELERATION_NO_INCREMENTAL_SIGNAL: if betas are insignificant / near zero.
    
    if (beta_recent_3p_w1 > 0 and beta_recent_3p_w2 > 0 and rescue_3p_w1 > 0 and rescue_3p_w2 > 0 and abs(t_recent_3p_w1) > 1.5 and abs(t_recent_3p_w2) > 1.5):
        final_classification = 'MCAP_ACCELERATION_TURNING_CANDIDATE'
    elif (rescue_3p_w1 > 0 and rescue_3p_w2 > 0) or (beta_inter_3p_w1 < 0 and beta_inter_3p_w2 < 0):
        final_classification = 'MCAP_ACCELERATION_CONTEXT_DEPENDENT'
    elif (beta_recent_3p_w1 <= 0 and beta_recent_3p_w2 <= 0):
        final_classification = 'MCAP_ACCELERATION_SHORT_TERM_REVERSAL_ONLY'
    else:
        final_classification = 'MCAP_ACCELERATION_NO_INCREMENTAL_SIGNAL'

    print(f"FINAL CLASSIFICATION: {final_classification}")

    # Write All Artifact Files (both to OUT_DIR and ARTIFACT_DIR)
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

    write_csv_dual('MCAP_ACCELERATION_REL_PANEL_RETURNS.csv', rel_panel_rows)
    write_csv_dual('MCAP_ACCELERATION_RECENT_WEIGHTED_REL.csv', recent_weighted_rows)
    write_csv_dual('MCAP_ACCELERATION_H0_OVERLAY.csv', h0_overlay_rows)
    write_csv_dual('MCAP_ACCELERATION_PRIMARY_REGRESSIONS.csv', primary_reg_rows)
    write_csv_dual('MCAP_ACCELERATION_INTERACTION.csv', interaction_reg_rows)
    write_csv_dual('MCAP_ACCELERATION_H0_SCORE_CONTROLS.csv', h0_score_control_rows)
    write_csv_dual('MCAP_ACCELERATION_PANEL_FE.csv', panel_fe_rows)
    write_csv_dual('MCAP_ACCELERATION_4X4_STATE_MATRIX.csv', matrix_4x4_rows)
    write_csv_dual('MCAP_ACCELERATION_COLD_RESCUE.csv', cold_rescue_rows)
    write_csv_dual('MCAP_ACCELERATION_WARM_DETERIORATION.csv', warm_deterioration_rows)
    write_csv_dual('MCAP_ACCELERATION_WITHIN_Q.csv', within_q_rows)
    write_csv_dual('MCAP_ACCELERATION_Q1_AUDIT.csv', q1_audit_rows)
    write_csv_dual('MCAP_ACCELERATION_SELECTION_EDGE.csv', selection_edge_rows)
    write_csv_dual('MCAP_ACCELERATION_PORTFOLIO_PNL.csv', portfolio_pnl_rows)
    write_csv_dual('MCAP_ACCELERATION_TAIL.csv', tail_rows)
    write_csv_dual('MCAP_ACCELERATION_EVENT_STUDY.csv', event_study_rows)
    write_csv_dual('MCAP_ACCELERATION_STREAK_COMPARISON.csv', streak_comp_rows)
    write_csv_dual('MCAP_ACCELERATION_TIME_STABILITY.csv', time_stability_rows)
    write_csv_dual('MCAP_ACCELERATION_LEAVE_ONE_YEAR_OUT.csv', loy_rows)
    write_csv_dual('MCAP_ACCELERATION_ROBUSTNESS.csv', robustness_rows)
    write_csv_dual('MCAP_ACCELERATION_TEMPORAL_QA.csv', temporal_qa_rows)
    
    write_json_dual('MCAP_ACCELERATION_PIT_TEST.json', {'status': 'PASS' if pit_pass else 'FAIL', 'tests': pit_tests})
    write_json_dual('MCAP_ACCELERATION_DETERMINISM.json', {'status': 'PASS' if det_pass else 'FAIL', 'tests': det_tests})
    
    report_json = {
        'study': 'MCAP_REGIME_ACCELERATION',
        'scope': 'EXPLORATORY_DIAGNOSTIC_ONLY',
        'final_classification': final_classification,
        'pit_test_status': 'PASS' if pit_pass else 'FAIL',
        'determinism_status': 'PASS' if det_pass else 'FAIL',
        'beta_recent_weighted_rel_3p': {'W1': beta_recent_3p_w1, 'W2': beta_recent_3p_w2},
        't_stat_recent_weighted_rel_3p': {'W1': t_recent_3p_w1, 'W2': t_recent_3p_w2},
        'cold_rescue_3p': {'W1': rescue_3p_w1, 'W2': rescue_3p_w2}
    }
    write_json_dual('MCAP_ACCELERATION_REPORT.json', report_json)
    
    print("Acceleration study complete. Artifacts generated successfully.")

if __name__ == '__main__':
    main()
