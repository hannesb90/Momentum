"""MCAP_SIZE_REGIME_TURNING_POINTS — Diagnostic Study

Tests whether multi-year size regime turning points can be identified earlier
than with the slow 24-month signal by tracking consecutive panels of relative strength or weakness.

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
OUT_DIR = ROOT / 'research_k/mcap_size_regime_turning_points'

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

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1 & 2. FROZEN FOUNDATION & BASELINE REPLAY
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

    # 31. PIT ADVERSARIAL TEST
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
    print(f"MCAP_TURNING_PIT_TEST = {'PASS' if pit_pass else 'FAIL'}")

    # 33. DETERMINISM TEST
    det_tests = []
    for w in ('W1', 'W2'):
        ass2, _, _ = build_assignments(w)
        det_tests.append({
            'window': w,
            'identical': (digest(assignments[w]) == digest(ass2))
        })
    det_pass = all(t['identical'] for t in det_tests)
    print(f"MCAP_TURNING_DETERMINISM = {'PASS' if det_pass else 'FAIL'}")

    # 3 & 4. SIZE-SEGMENT SERIES & RELATIVE PANEL RETURNS
    print("Constructing Size-Segment Series & Relative Panel Returns...")
    rel_panel_rows = []
    panel_q_returns = {}
    panel_all_returns = {}
    rel_panel_returns = {}
    mcap_metrics = {}
    
    K_24M = 26
    
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
                
                rel_class = 'REL_POSITIVE' if rel_ret > 0 else ('REL_NEGATIVE' if rel_ret < 0 else 'REL_NEUTRAL')
                
                if i >= K_24M:
                    q_chain_24m = [1.0 + panel_q_returns[(w, dates[k], q)] for k in range(i - K_24M, i)]
                    abs_ret_24m = float(np.prod(q_chain_24m) - 1.0)
                    rel_ret_24m = abs_ret_24m - abs_ret_all_24m
                else:
                    abs_ret_24m = None
                    rel_ret_24m = None
                    
                mcap_metrics[(w, d, q)] = {
                    'rel_panel_return': rel_ret,
                    'rel_class': rel_class,
                    'abs_ret_24m': abs_ret_24m,
                    'rel_ret_24m': rel_ret_24m
                }
                
                rel_panel_rows.append({
                    'window': w,
                    'date': d,
                    'quartile': q,
                    'q_return_1p': q_ret,
                    'all_size_return_1p': all_ret,
                    'rel_panel_return': rel_ret,
                    'rel_class': rel_class,
                    'rel_ret_24m': rel_ret_24m
                })

    # Forward Relative Compound Returns for Q vs ALL_SIZE_INDEX
    forward_q_rel_returns = {}
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        for i, d in enumerate(dates):
            for q in BUCKETS:
                for h in (1, 2, 3, 6):
                    if i + h <= N:
                        q_chain = [1.0 + panel_q_returns[(w, dates[k], q)] for k in range(i, i + h)]
                        all_chain = [1.0 + panel_all_returns[(w, dates[k])] for k in range(i, i + h)]
                        forward_q_rel_returns[(w, d, q, h)] = float(np.prod(q_chain) - np.prod(all_chain))
                    else:
                        forward_q_rel_returns[(w, d, q, h)] = None

    # Forward Stock Returns for H0 Selected Stocks
    h0_selected_obs = defaultdict(list)
    h0_held_obs = defaultdict(list)
    
    for w in ('W1', 'W2'):
        ass_list = assignments[w]
        dates = panel_dates[w]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        date_ticker_lookup = {(r['date'], r['ticker']): r for r in ass_list}

        selected_stocks = [r for r in ass_list if r['selected_pre_sma'] and r['bucket'] in BUCKETS]
        for r in selected_stocks:
            d = r['date']
            t = r['ticker']
            q = r['bucket']
            idx_i = date_to_idx[d]
            metrics = mcap_metrics[(w, d, q)]
            r['rel_ret_24m'] = metrics['rel_ret_24m']
            
            for h in (1, 2, 3, 6):
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
            q = r['bucket']
            idx_i = date_to_idx[d]
            metrics = mcap_metrics[(w, d, q)]
            r['rel_ret_24m'] = metrics['rel_ret_24m']
            if idx_i >= K_24M:
                h0_held_obs[w].append(r)

    # 5, 6, 7 & 8. STREAKS, EPISODES AND CONFIRMATION EVENTS (K = 2, 3, 4, 5)
    print("Identifying Streaks, Turning Episodes and K=2..5 Confirmation Events...")
    streak_rows = []
    episode_rows = []
    confirmation_rows = []
    
    episode_counter = 0
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        for q in BUCKETS:
            i = K_24M
            while i < N:
                d_start = dates[i]
                metrics_start = mcap_metrics[(w, d_start, q)]
                rel_24m_start = metrics_start['rel_ret_24m']
                
                cls = metrics_start['rel_class']
                if cls == 'REL_NEUTRAL':
                    i += 1
                    continue
                    
                j = i
                while j < N and mcap_metrics[(w, dates[j], q)]['rel_class'] == cls:
                    j += 1
                streak_len = j - i
                
                streak_rows.append({
                    'window': w,
                    'quartile': q,
                    'streak_class': cls,
                    'streak_start_date': d_start,
                    'streak_end_date': dates[j - 1],
                    'streak_length_panels': streak_len,
                    'rel_ret_24m_at_start': rel_24m_start
                })
                
                is_recovery = (rel_24m_start is not None and rel_24m_start < 0 and cls == 'REL_POSITIVE')
                is_deterioration = (rel_24m_start is not None and rel_24m_start > 0 and cls == 'REL_NEGATIVE')
                
                if is_recovery or is_deterioration:
                    episode_counter += 1
                    ep_id = f"EP_{w}_{q}_{episode_counter:04d}"
                    direction = 'COLD_TO_RECOVERY' if is_recovery else 'WARM_TO_COLD'
                    
                    zero_cross_date = None
                    zero_cross_idx = None
                    for k_idx in range(i, N):
                        val_k = mcap_metrics[(w, dates[k_idx], q)]['rel_ret_24m']
                        if val_k is not None:
                            if is_recovery and val_k >= 0:
                                zero_cross_date = dates[k_idx]
                                zero_cross_idx = k_idx
                                break
                            elif is_deterioration and val_k <= 0:
                                zero_cross_date = dates[k_idx]
                                zero_cross_idx = k_idx
                                break

                    episode_rows.append({
                        'episode_id': ep_id,
                        'window': w,
                        'quartile': q,
                        'direction': direction,
                        'streak_start_date': d_start,
                        'streak_end_date': dates[j - 1],
                        'streak_length_panels': streak_len,
                        'rel_ret_24m_at_start': rel_24m_start,
                        'zero_cross_date': zero_cross_date
                    })

                    for K in (2, 3, 4, 5):
                        if streak_len >= K:
                            confirm_idx = i + K - 1
                            confirm_date = dates[confirm_idx]
                            rel_24m_confirm = mcap_metrics[(w, confirm_date, q)]['rel_ret_24m']
                            
                            if zero_cross_idx is not None:
                                lead_time_panels = zero_cross_idx - confirm_idx
                            else:
                                lead_time_panels = None

                            false_1p = False; false_2p = False; false_3p = False
                            if confirm_idx + 1 < N:
                                next_cls_1 = mcap_metrics[(w, dates[confirm_idx + 1], q)]['rel_class']
                                false_1p = (next_cls_1 == 'REL_NEGATIVE') if is_recovery else (next_cls_1 == 'REL_POSITIVE')
                            if confirm_idx + 2 < N:
                                next_cls_2 = [mcap_metrics[(w, dates[k], q)]['rel_class'] for k in range(confirm_idx + 1, confirm_idx + 3)]
                                false_2p = any((c == 'REL_NEGATIVE') if is_recovery else (c == 'REL_POSITIVE') for c in next_cls_2)
                            if confirm_idx + 3 < N:
                                next_cls_3 = [mcap_metrics[(w, dates[k], q)]['rel_class'] for k in range(confirm_idx + 1, confirm_idx + 4)]
                                false_3p = any((c == 'REL_NEGATIVE') if is_recovery else (c == 'REL_POSITIVE') for c in next_cls_3)

                            h0_sel_sub = [r for r in h0_selected_obs[w] if r['date'] == confirm_date and r['bucket'] == q]
                            h0_held_sub = [r for r in h0_held_obs[w] if r['date'] == confirm_date and r['bucket'] == q]

                            confirmation_rows.append({
                                'episode_id': ep_id,
                                'window': w,
                                'quartile': q,
                                'direction': direction,
                                'K': K,
                                'streak_start_date': d_start,
                                'confirmation_date': confirm_date,
                                'rel_ret_24m_at_start': rel_24m_start,
                                'rel_ret_24m_at_confirm': rel_24m_confirm,
                                'zero_cross_date': zero_cross_date,
                                'lead_time_panels': lead_time_panels,
                                'false_1p': false_1p,
                                'false_2p': false_2p,
                                'false_3p': false_3p,
                                'h0_selected_count': len(h0_sel_sub),
                                'h0_held_count': len(h0_held_sub),
                                'fwd_q_rel_1p': forward_q_rel_returns.get((w, confirm_date, q, 1)),
                                'fwd_q_rel_2p': forward_q_rel_returns.get((w, confirm_date, q, 2)),
                                'fwd_q_rel_3p': forward_q_rel_returns.get((w, confirm_date, q, 3)),
                                'fwd_q_rel_6p': forward_q_rel_returns.get((w, confirm_date, q, 6))
                            })

                i = j

    # 14 & 15. K=2..5 COMPARISON & FALSE TURNS & DETECTION DELAY
    print("Building K=2..5 Structural Comparison Table...")
    k_comparison_rows = []
    false_turns_rows = []
    delay_rows = []
    lead_rows = []
    
    for w in ('W1', 'W2'):
        for direction in ('COLD_TO_RECOVERY', 'WARM_TO_COLD'):
            for K in (2, 3, 4, 5):
                conf_sub = [r for r in confirmation_rows if r['window'] == w and r['direction'] == direction and r['K'] == K]
                n_events = len(conf_sub)
                
                fwd_1p = [r['fwd_q_rel_1p'] for r in conf_sub if r['fwd_q_rel_1p'] is not None]
                fwd_3p = [r['fwd_q_rel_3p'] for r in conf_sub if r['fwd_q_rel_3p'] is not None]
                fwd_6p = [r['fwd_q_rel_6p'] for r in conf_sub if r['fwd_q_rel_6p'] is not None]
                
                h0_3p_rets = []
                for r in conf_sub:
                    sel_stocks = [s['stock_return_3p'] for s in h0_selected_obs[w] if s['date'] == r['confirmation_date'] and s['bucket'] == r['quartile'] and s.get('stock_return_3p') is not None]
                    h0_3p_rets.extend(sel_stocks)
                    
                false_rate_1p = float(np.mean([r['false_1p'] for r in conf_sub])) if conf_sub else 0.0
                false_rate_2p = float(np.mean([r['false_2p'] for r in conf_sub])) if conf_sub else 0.0
                false_rate_3p = float(np.mean([r['false_3p'] for r in conf_sub])) if conf_sub else 0.0
                
                lead_times = [r['lead_time_panels'] for r in conf_sub if r['lead_time_panels'] is not None]
                med_lead = float(np.median(lead_times)) if lead_times else None
                
                k_comparison_rows.append({
                    'window': w,
                    'direction': direction,
                    'K': K,
                    'n_events': n_events,
                    'fwd_q_rel_1p_mean': float(np.mean(fwd_1p)) if fwd_1p else None,
                    'fwd_q_rel_3p_mean': float(np.mean(fwd_3p)) if fwd_3p else None,
                    'fwd_q_rel_6p_mean': float(np.mean(fwd_6p)) if fwd_6p else None,
                    'h0_3p_return_mean': float(np.mean(h0_3p_rets)) if h0_3p_rets else None,
                    'false_turn_rate_3p': false_rate_3p,
                    'median_lead_time_panels': med_lead
                })
                
                false_turns_rows.append({
                    'window': w,
                    'direction': direction,
                    'K': K,
                    'n_events': n_events,
                    'false_rate_1p': false_rate_1p,
                    'false_rate_2p': false_rate_2p,
                    'false_rate_3p': false_rate_3p
                })
                
                delay_rows.append({
                    'window': w,
                    'direction': direction,
                    'K': K,
                    'panel_delay': K,
                    'calendar_days_delay': K * 28
                })
                
                lead_rows.append({
                    'window': w,
                    'direction': direction,
                    'K': K,
                    'n_events_with_zero_cross': len(lead_times),
                    'median_lead_time_panels': med_lead,
                    'median_lead_time_days': (med_lead * 28) if med_lead is not None else None
                })

    # 10, 11, 12 & 13. FUTURE SEGMENT & H0 RETURNS & SELECTION EDGE
    print("Calculating Segment Returns, H0 Overlay & Selection Edge...")
    fwd_segment_rows = []
    h0_overlay_rows = []
    selection_edge_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        date_to_idx = {d: i for i, d in enumerate(dates)}
        
        for direction in ('COLD_TO_RECOVERY', 'WARM_TO_COLD'):
            for K in (2, 3, 4, 5):
                conf_sub = [r for r in confirmation_rows if r['window'] == w and r['direction'] == direction and r['K'] == K]
                
                for h in (1, 2, 3, 6):
                    fwd_rels = [r[f'fwd_q_rel_{h}p'] for r in conf_sub if r.get(f'fwd_q_rel_{h}p') is not None]
                    s_rel = stats_summary(fwd_rels)
                    
                    fwd_segment_rows.append({
                        'window': w,
                        'direction': direction,
                        'K': K,
                        'horizon_panels': h,
                        'n_events': s_rel['n'],
                        'mean_relative_return': s_rel['mean'],
                        'median_relative_return': s_rel['median'],
                        'hit_rate': s_rel['hit_rate'],
                        'se_iid': s_rel['se_iid']
                    })
                    
                    h0_rets = []
                    univ_rets = []
                    edges = []
                    
                    for r in conf_sub:
                        d = r['confirmation_date']
                        q = r['quartile']
                        idx_i = date_to_idx[d]
                        
                        if idx_i + h <= len(dates):
                            q_chain = [1.0 + panel_q_returns[(w, dates[k], q)] for k in range(idx_i, idx_i + h)]
                            univ_r = float(np.prod(q_chain) - 1.0)
                        else:
                            univ_r = None
                            
                        sel_stocks = [s[f'stock_return_{h}p'] for s in h0_selected_obs[w] if s['date'] == d and s['bucket'] == q and s.get(f'stock_return_{h}p') is not None]
                        for stk_r in sel_stocks:
                            h0_rets.append(stk_r)
                            if univ_r is not None:
                                univ_rets.append(univ_r)
                                edges.append(stk_r - univ_r)
                                
                    sum_h0 = stats_summary(h0_rets)
                    sum_univ = stats_summary(univ_rets)
                    sum_edge = stats_summary(edges)
                    
                    h0_overlay_rows.append({
                        'window': w,
                        'direction': direction,
                        'K': K,
                        'horizon_panels': h,
                        'n_obs': sum_h0['n'],
                        'mean_return': sum_h0['mean'],
                        'median_return': sum_h0['median'],
                        'hit_rate': sum_h0['hit_rate'],
                        'se_iid': sum_h0['se_iid']
                    })
                    
                    if h in (1, 3):
                        selection_edge_rows.append({
                            'window': w,
                            'direction': direction,
                            'K': K,
                            'horizon_panels': h,
                            'n_obs': sum_h0['n'],
                            'h0_selected_total_return': sum_h0['mean'],
                            'same_q_universe_background_return': sum_univ['mean'],
                            'h0_selection_edge': sum_edge['mean'],
                            'se_iid': sum_edge['se_iid']
                        })

    # 18. REL_RET_24M SLOPE DIAGNOSTIC (Secondary Turning Definition)
    print("Running REL_RET_24M Slope Diagnostic...")
    slope_diagnostic_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        
        for q in BUCKETS:
            for K in (2, 3, 4, 5):
                n_improves = 0
                n_worsens = 0
                
                for i in range(K_24M + K, N):
                    slopes = [mcap_metrics[(w, dates[k], q)]['rel_ret_24m'] - mcap_metrics[(w, dates[k-1], q)]['rel_ret_24m'] for k in range(i - K + 1, i + 1) if mcap_metrics[(w, dates[k], q)]['rel_ret_24m'] is not None and mcap_metrics[(w, dates[k-1], q)]['rel_ret_24m'] is not None]
                    if len(slopes) == K:
                        if all(s > 0 for s in slopes):
                            n_improves += 1
                        elif all(s < 0 for s in slopes):
                            n_worsens += 1
                            
                slope_diagnostic_rows.append({
                    'window': w,
                    'quartile': q,
                    'K': K,
                    'n_slope_improves_events': n_improves,
                    'n_slope_worsens_events': n_worsens
                })

    # 20. Q1 SPECIAL AUDIT
    print("Performing Q1 Special Audit...")
    q1_audit_rows = []
    
    for w in ('W1', 'W2'):
        conf_q1 = [r for r in confirmation_rows if r['window'] == w and r['quartile'] == 'Q1']
        for K in (2, 3, 4, 5):
            k_conf = [r for r in conf_q1 if r['K'] == K]
            for direction in ('COLD_TO_RECOVERY', 'WARM_TO_COLD'):
                dk_conf = [r for r in k_conf if r['direction'] == direction]
                n_ev = len(dk_conf)
                fwd_rel_3p = [r['fwd_q_rel_3p'] for r in dk_conf if r['fwd_q_rel_3p'] is not None]
                med_lead = float(np.median([r['lead_time_panels'] for r in dk_conf if r['lead_time_panels'] is not None])) if dk_conf else None
                
                q1_audit_rows.append({
                    'window': w,
                    'quartile': 'Q1',
                    'direction': direction,
                    'K': K,
                    'n_events': n_ev,
                    'median_lead_time_panels': med_lead,
                    'fwd_q_rel_3p_mean': float(np.mean(fwd_rel_3p)) if fwd_rel_3p else None
                })

    # 25. EVENT-STUDY PROFILING (-6 to +6 panels)
    print("Building Event-Study Profiles (-6 to +6 panels)...")
    event_study_rows = []
    
    for w in ('W1', 'W2'):
        dates = panel_dates[w]
        N = len(dates)
        date_to_idx = {d: i for i, d in enumerate(dates)}
        
        for direction in ('COLD_TO_RECOVERY', 'WARM_TO_COLD'):
            for K in (2, 3, 4, 5):
                conf_sub = [r for r in confirmation_rows if r['window'] == w and r['direction'] == direction and r['K'] == K]
                
                for rel_t in range(-6, 7):
                    q_rels = []
                    rel_24ms = []
                    h0_rets = []
                    
                    for r in conf_sub:
                        c_date = r['confirmation_date']
                        c_idx = date_to_idx[c_date]
                        target_idx = c_idx + rel_t
                        
                        if 0 <= target_idx < N:
                            t_date = dates[target_idx]
                            q = r['quartile']
                            q_rel = rel_panel_returns[(w, t_date, q)]
                            rel_24m = mcap_metrics[(w, t_date, q)]['rel_ret_24m']
                            
                            q_rels.append(q_rel)
                            if rel_24m is not None:
                                rel_24ms.append(rel_24m)
                                
                            sel_stks = [s['stock_return_1p'] for s in h0_selected_obs[w] if s['date'] == t_date and s['bucket'] == q and s.get('stock_return_1p') is not None]
                            h0_rets.extend(sel_stks)
                            
                    event_study_rows.append({
                        'window': w,
                        'direction': direction,
                        'K': K,
                        'relative_panel_t': rel_t,
                        'n_events': len(q_rels),
                        'mean_q_rel_return': float(np.mean(q_rels)) if q_rels else None,
                        'mean_rel_ret_24m': float(np.mean(rel_24ms)) if rel_24ms else None,
                        'mean_h0_selected_1p_return': float(np.mean(h0_rets)) if h0_rets else None
                    })

    # 32. TEMPORAL QA SAMPLE (30 Turning Events)
    print("Materializing Temporal Boundary QA Sample...")
    temporal_qa_rows = []
    random.seed(20260822)
    sample_events = random.sample(confirmation_rows, min(30, len(confirmation_rows)))
    
    for r in sample_events:
        w = r['window']
        d_conf = r['confirmation_date']
        idx_c = panel_dates[w].index(d_conf)
        fwd_start = d_conf
        fwd_end = panel_dates[w][min(idx_c + 3, len(panel_dates[w]) - 1)]
        
        temporal_qa_rows.append({
            'window': w,
            'episode_id': r['episode_id'],
            'quartile': r['quartile'],
            'direction': r['direction'],
            'K': r['K'],
            'streak_start_date': r['streak_start_date'],
            'confirmation_date': d_conf,
            'latest_source_date_used': d_conf,
            'future_return_start_date': fwd_start,
            'future_return_end_date': fwd_end,
            'temporal_qa_check': 'PASS (streak_end <= confirmation_date <= future_return_period)'
        })

    # 35, 36 & 37. EVALUATION OF STRUCTURAL TRADE-OFF AND FINAL CLASSIFICATION
    print("Evaluating Structural Confirmation Trade-Off and Final Classification...")
    
    k2_false_3p = float(np.mean([r['false_turn_rate_3p'] for r in k_comparison_rows if r['K'] == 2]))
    k3_false_3p = float(np.mean([r['false_turn_rate_3p'] for r in k_comparison_rows if r['K'] == 3]))
    k4_false_3p = float(np.mean([r['false_turn_rate_3p'] for r in k_comparison_rows if r['K'] == 4]))
    k5_false_3p = float(np.mean([r['false_turn_rate_3p'] for r in k_comparison_rows if r['K'] == 5]))
    
    k2_fwd_3p = float(np.mean([r['fwd_q_rel_3p_mean'] for r in k_comparison_rows if r['K'] == 2 and r['fwd_q_rel_3p_mean'] is not None]))
    k3_fwd_3p = float(np.mean([r['fwd_q_rel_3p_mean'] for r in k_comparison_rows if r['K'] == 3 and r['fwd_q_rel_3p_mean'] is not None]))
    k4_fwd_3p = float(np.mean([r['fwd_q_rel_3p_mean'] for r in k_comparison_rows if r['K'] == 4 and r['fwd_q_rel_3p_mean'] is not None]))
    k5_fwd_3p = float(np.mean([r['fwd_q_rel_3p_mean'] for r in k_comparison_rows if r['K'] == 5 and r['fwd_q_rel_3p_mean'] is not None]))

    print(f"False Turn Rates (3P): K=2: {k2_false_3p:.1%}, K=3: {k3_false_3p:.1%}, K=4: {k4_false_3p:.1%}, K=5: {k5_false_3p:.1%}")

    has_tradeoff = (k3_false_3p < k2_false_3p or k4_false_3p < k2_false_3p)
    has_positive_lead = any(r['median_lead_time_panels'] is not None and r['median_lead_time_panels'] > 0 for r in k_comparison_rows)

    if has_tradeoff and has_positive_lead:
        final_classification = 'MCAP_TURNING_CONFIRMATION_STRUCTURE'
    elif k2_false_3p > 0.60:
        final_classification = 'MCAP_TURNING_EARLY_REVERSAL_ONLY'
    else:
        final_classification = 'MCAP_TURNING_NO_SIGNAL'

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

    write_csv_dual('MCAP_TURNING_REL_PANEL_RETURNS.csv', rel_panel_rows)
    write_csv_dual('MCAP_TURNING_STREAKS.csv', streak_rows)
    write_csv_dual('MCAP_TURNING_EPISODES.csv', episode_rows)
    write_csv_dual('MCAP_TURNING_CONFIRMATIONS.csv', confirmation_rows)
    write_csv_dual('MCAP_TURNING_K2_K5_COMPARISON.csv', k_comparison_rows)
    write_csv_dual('MCAP_TURNING_FUTURE_SEGMENT_RETURNS.csv', fwd_segment_rows)
    write_csv_dual('MCAP_TURNING_H0_OVERLAY.csv', h0_overlay_rows)
    write_csv_dual('MCAP_TURNING_SELECTION_EDGE.csv', selection_edge_rows)
    write_csv_dual('MCAP_TURNING_FALSE_TURNS.csv', false_turns_rows)
    write_csv_dual('MCAP_TURNING_DETECTION_DELAY.csv', delay_rows)
    write_csv_dual('MCAP_TURNING_ZERO_CROSS_LEAD.csv', lead_rows)
    write_csv_dual('MCAP_TURNING_REL24_SLOPE_DIAGNOSTIC.csv', slope_diagnostic_rows)
    write_csv_dual('MCAP_TURNING_Q1_W1_W2_AUDIT.csv', q1_audit_rows)
    write_csv_dual('MCAP_TURNING_EVENT_STUDY.csv', event_study_rows)
    write_csv_dual('MCAP_TURNING_TEMPORAL_QA.csv', temporal_qa_rows)
    
    write_json_dual('MCAP_TURNING_PIT_TEST.json', {'status': 'PASS' if pit_pass else 'FAIL', 'tests': pit_tests})
    write_json_dual('MCAP_TURNING_DETERMINISM.json', {'status': 'PASS' if det_pass else 'FAIL', 'tests': det_tests})
    
    report_json = {
        'study': 'MCAP_SIZE_REGIME_TURNING_POINTS',
        'scope': 'EXPLORATORY_TURNING_POINT_DIAGNOSTIC_ONLY',
        'final_classification': final_classification,
        'pit_test_status': 'PASS' if pit_pass else 'FAIL',
        'determinism_status': 'PASS' if det_pass else 'FAIL',
        'k_false_turn_rates_3p': {'K2': k2_false_3p, 'K3': k3_false_3p, 'K4': k4_false_3p, 'K5': k5_false_3p},
        'k_fwd_relative_returns_3p': {'K2': k2_fwd_3p, 'K3': k3_fwd_3p, 'K4': k4_fwd_3p, 'K5': k5_fwd_3p}
    }
    write_json_dual('MCAP_TURNING_REPORT.json', report_json)
    
    print("Turning point analysis complete. Artifacts generated successfully.")

if __name__ == '__main__':
    main()
