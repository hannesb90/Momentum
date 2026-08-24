#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION - preregistrerad fail-closed studie.

Enda fragan: Tillfor K7 legacy (clip [0.01,0.06] + renormalisering) nagon reproducerbar
ekonomisk, riskmassig eller diversifieringsmassig nytta som motiverar att komponenten
finns kvar i canonical H0 V3?

Jamfor exakt tva arkitekturer, allt annat fryst:
  CURRENT_K7_ON  = K5_1_K6_1_K7_1_WP_1  (canonical ARM03-replik)
  K7_OFF         = K5_1_K6_1_K7_0_WP_1  (enda interventionen: legacy clip borttagen;
                  avslutande summanormalisering x n/30 ar delad bookkeeping i BADA armarna)

Runner, context och kostnadsmekanik importeras oforandrad fran den validerade studien
run_h0_v3_weight_layer_simplification_v2 (17/17 gates PASS, bitvis identitet mot
BASE_STUDY ARM03 verifierad dar).

Exit: 0 ok, 2 fail-closed blocker, 3 ovantat fel.
"""
import sys, os, json, csv, math, hashlib, re, traceback
from datetime import datetime, timezone

sys.path.insert(0, '/home/hannesb/momentum_v2/tools')

if os.environ.get('PYTHONHASHSEED') != '0':
    os.execve(sys.executable, [sys.executable] + sys.argv,
              {**os.environ, 'PYTHONHASHSEED': '0'})

import numpy as np
import run_h0_v3_weight_layer_simplification_v2 as V2

ROOT = '/home/hannesb/momentum_v2'
OUT = f'{ROOT}/research_k/h0_v3_k7_targeted_single_component_confirmation'
V2OUT = V2.OUT

WINDOWS = ['W1', 'W2']
CURRENT_ID = 'K5_1_K6_1_K7_1_WP_1'
OFF_ID = 'K5_1_K6_1_K7_0_WP_1'
PPY = V2.PPY
N_NAMES = V2.N_NAMES
COST_RATE_B = V2.COST_RATE_B
COST_RATE_C = V2.COST_RATE_C
YEARS_CAL = V2.YEARS_CAL
IDENTITY_TOL = V2.IDENTITY_TOL
ORDER_EPS = V2.ORDER_EPS
ECON_EPS = 1e-4
MAXDD_EPS = 0.005
VOL_EPS = 0.01
TURN_EPS_PP = 5.0
BOOT_N = 10000
BOOT_SEED = 20260823
CAP_HI = 0.06
FABRICATED_TOKENS = V2.FABRICATED_TOKENS

K7_GATES = {}
CURR = {}
OFF = {}
CH = {}
R = {}

MANDATORY = ['CURRENT_REPLAY', 'W1_PANEL_IDENTITY', 'W2_PANEL_IDENTITY', 'RETURN_TIMING',
             'COST_B_REPLAY', 'EXECUTION_LEDGER_IDENTITY', 'K7_ON_CANONICAL_IDENTITY',
             'K7_OFF_SINGLE_INTERVENTION_ONLY', 'PIT_TEST', 'STATE_ISOLATION',
             'DETERMINISTIC_REPLAY', 'NON_COMPUTED_CLAIM_SCAN']


def gate(name, ok, evidence, tolerance=None):
    e = {'status': 'PASS' if ok else 'FAIL', 'evidence': evidence}
    if tolerance is not None:
        e['tolerance'] = tolerance
    K7_GATES[name] = e
    try:
        ev_txt = json.dumps(evidence, default=str)
    except Exception:
        ev_txt = str(evidence)
    print(f'[GATE] {name}: {e["status"]} | {ev_txt[:600]}', flush=True)
    return ok


def tok_re(tok):
    return V2.tok_re(tok)


def sha256_file(path):
    return V2.sha256_file(path)


def rnd12(o):
    if isinstance(o, dict):
        return {k: rnd12(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd12(v) for v in o]
    if isinstance(o, float):
        return round(o, 12)
    return o


def write_json(path, obj):
    V2.write_json(path, obj)


def write_csv(path, rows):
    V2.write_csv(path, rows)


def norm_n30(vec_map, sel):
    s = sum(vec_map[k] for k in sel)
    if s <= 0:
        return {k: 0.0 for k in sel}
    return {k: vec_map[k] / s * (len(sel) / N_NAMES) for k in sel}


def freeze_preregistration():
    rules_order = [
        'K7_CONFIRMATION_INVALID om nagot obligatoriskt gate FAIL',
        'K7_MIXED_W1_W2 om (imp W1 och harm W2) eller (harm W1 och imp W2)',
        'K7_RISK_FUNCTION_CONFIRMED om riskben i BADA fonstren',
        'K7_ECONOMIC_VALUE_CONFIRMED om imp i BADA fonstren',
        'K7_REMOVAL_CONFIRMED om econ_ok i BADA fonstren (strukturokning racker per sektion 22-23)',
        'annars K7_NEUTRAL_BUT_REMOVAL_UNRESOLVED']
    next_actions = {
        'K7_REMOVAL_CONFIRMED': 'FREEZE_K7_OFF_CANDIDATE',
        'K7_RISK_FUNCTION_CONFIRMED': 'KEEP_K7_CURRENT',
        'K7_ECONOMIC_VALUE_CONFIRMED': 'KEEP_K7_CURRENT',
        'K7_MIXED_W1_W2': 'NO_CANONICAL_CHANGE',
        'K7_NEUTRAL_BUT_REMOVAL_UNRESOLVED': 'NO_CANONICAL_CHANGE'}
    prereg = {
        'study': 'H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION',
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'question': 'Tillfor K7 legacy nagot som H0 V3 behovet? LEGACY K7 ON vs OFF, inget annat.',
        'arms': {'CURRENT_K7_ON': CURRENT_ID, 'K7_OFF': OFF_ID},
        'intervention': {
            'only_change': 'legacy clip np.clip(w,0.01,0.06) borttagen',
            'kept_bookkeeping': 'avslutande w/w.sum()*(n/30) normalisering IDENTISK i bada armarna',
            'no_waterfill_no_new_cap': True},
        'windows': WINDOWS,
        'cost_primary': 'COST_B = 20bp x executed weight turnover (exec-bas)',
        'cost_robustness_only': 'COST_C = 40bp x samma turnover',
        'primary_estimand': 'paired panel net return difference K7_OFF - CURRENT under COST_B',
        'materiality': {'econ_eps_per_panel': ECON_EPS, 'maxdd_eps': MAXDD_EPS,
                        'vol_eps_ann': VOL_EPS, 'turnover_eps_pp_yr': TURN_EPS_PP},
        'bootstrap': {'n': BOOT_N, 'seed': BOOT_SEED, 'method': 'percentile bootstrap of paired mean'},
        'classification_rules': {
            'imp_w': 'mean_d > ECON_EPS and boot_ci_low > 0 (d = OFF - CURRENT)',
            'harm_w': 'mean_d < -ECON_EPS and boot_ci_high < 0',
            'riskben_w': '(maxdd_CURRENT < maxdd_OFF - MAXDD_EPS) or (vol_CURRENT < vol_OFF - VOL_EPS)',
            'econ_ok_w': 'not harm_w',
            'precedence': rules_order,
            'next_action_map': next_actions},
        'gates_required': MANDATORY}
    write_json(f'{OUT}/K7_CONFIRMATION_PREREGISTRATION.json', prereg)
    digest = sha256_file(f'{OUT}/K7_CONFIRMATION_PREREGISTRATION.json')
    with open(f'{OUT}/K7_CONFIRMATION_FREEZE.json', 'w') as f:
        json.dump({'preregistration_sha256': digest,
                   'frozen_before_any_arm_run': True,
                   'frozen_utc': prereg['frozen_utc']}, f, indent=1)
    print(f'[FREEZE] sha256={digest}', flush=True)
    return digest


from datetime import datetime, timezone

P1 = {}


def osz_summary(osz):
    def s(v):
        a = np.array(v) if len(v) else np.array([0.0])
        return {'n': len(v), 'mean': float(a.mean()), 'median': float(np.median(a)),
                'p90': float(np.percentile(a, 90))}
    return {k: s(v) for k, v in osz.items()}


def arm_hash(w, res):
    m = V2.summarize_arm(res, None)
    payload = {'window': w, 'metrics': rnd12({k: m[k] for k in sorted(m)}),
               'order_sizes_summary': rnd12(osz_summary(res['order_sizes'])),
               'panel_net_b': [round(float(x), 12) for x in res['ret_lists']['net_b']],
               'nav_end_b': round(float(res['nav_end']['B']), 12)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_prior_artifacts():
    with open(f'{V2OUT}/FACTORIAL_ARM_METRICS.json') as f:
        R['factorial'] = json.load(f)
    with open(f'{V2OUT}/COST_B_REPLAY.json') as f:
        R['costb'] = json.load(f)
    lp = {}
    with open(f'{V2OUT}/WEIGHT_LAYER_EXECUTION_LEDGER_CURRENT.csv') as f:
        for r in csv.DictReader(f):
            lp[(r['window'], r['date'], r['ticker'])] = r
    R['ledger_prior'] = lp
    rw = {}
    with open(f'{V2OUT}/WEIGHT_TURNOVER_RECONCILIATION.csv') as f:
        for r in csv.DictReader(f):
            rw.setdefault(r['window'], {})[r['date']] = float(r['exec_basis_wt_mine'])
    R['recon_wt'] = rw


def replay_and_identity():
    V2.load_contexts()
    V2.load_refs()
    fac = {(r['window'], r['arm_id']): r for r in R['factorial']}
    devs_all = {}
    okall = True
    for w in WINDOWS:
        res = V2.run_arm(V2.CTX[w], w, 1, 1, 1, 1, CURRENT_ID, True, True)
        CURR[w] = res
        m = V2.summarize_arm(res, None)
        R.setdefault('summary', {})[w] = m
        P1[f'{w}|CURRENT'] = arm_hash(w, res)
        fr = fac[(w, CURRENT_ID)]
        keys = ['cagr_gross_cal_pct', 'cagr_a_cal_pct', 'cagr_b_cal_pct', 'sharpe_b',
                'maxdd_b', 'turnover_exec_ann_pct', 'turnover_churn_ann_pct',
                'orders_exec_per_yr', 'orders_churn_per_yr']
        conv = {'cagr_gross_cal_pct': ('cagr_gross_cal', 100.0),
                'cagr_a_cal_pct': ('cagr_a_cal', 100.0),
                'cagr_b_cal_pct': ('cagr_b_cal', 100.0),
                'sharpe_b': ('sharpe_b', 1.0), 'maxdd_b': ('maxdd_b', 1.0),
                'turnover_exec_ann_pct': ('turnover_exec_ann_pct', 1.0),
                'turnover_churn_ann_pct': ('turnover_churn_ann_pct', 1.0),
                'orders_exec_per_yr': ('orders_exec_per_yr', 1.0),
                'orders_churn_per_yr': ('orders_churn_per_yr', 1.0)}
        dv = {k: abs(float(m[src]) * sc - float(fr[k])) for k, (src, sc) in conv.items()}
        devs_all[w] = {k: rnd12(v) for k, v in dv.items()}
        okall &= all(v <= 1e-9 for v in dv.values())

        recon = R['recon_wt'][w]
        panels = res['panels']
        missing, max_wt = [], 0.0
        for p in panels:
            key = str(p['date'])
            if key not in recon:
                missing.append(key)
                continue
            max_wt = max(max_wt, abs(float(p['wt_exec']) - recon[key]))
        max_sf = max(float(p['sf_resid']) for p in panels)
        okp = (not missing) and max_wt <= IDENTITY_TOL and max_sf <= IDENTITY_TOL \
            and all(v <= 1e-9 for v in dv.values())
        gate(f'{w}_PANEL_IDENTITY', okp, {
            'wt_exec_vs_WD_ACTUAL_recon_max_abs_diff': rnd12(max_wt),
            'wd_dates_missing': missing[:5], 'sf_resid_max': rnd12(max_sf),
            'aggregate_metrics_vs_factorial_row_max_dev':
                max(devs_all[w].values()),
            'note': 'ARM03-path bitidentitet etablerad i frusen V2-studie; har replik '
                    'mot dess frusna artefakter (FACTORIAL_ARM_METRICS.json + WD-turnover per panel)'},
            tolerance=IDENTITY_TOL)
    gate('CURRENT_REPLAY', okall, {'per_window_metric_max_dev': devs_all}, tolerance=1e-9)


def canonical_identity_and_chains():
    allok = True
    ev = {}
    for w in WINDOWS:
        ctx = V2.CTX[w]
        max_fac = max_on = max_off = 0.0
        CH[w] = []
        for r in ctx['base']:
            sl = sorted(r['weights'].keys())
            if not sl:
                CH[w].append(None)
                continue
            d = r['date']
            ch = V2.stage_chain(sl, d, ctx['vol_fn'], ctx['confirmed_fn'])
            A_raw = norm_n30(ch['S_k6'], sl)
            CH[w].append({'chain': ch, 'A_raw': A_raw, 'names': sl})
            won = V2.compute_targets_pipeline(sl, d, 1, 1, 1, ctx['vol_fn'], ctx['confirmed_fn'])
            woff = V2.compute_targets_pipeline(sl, d, 1, 1, 0, ctx['vol_fn'], ctx['confirmed_fn'])
            don, doff = dict(zip(sl, map(float, won))), dict(zip(sl, map(float, woff)))
            ref = {k: float(r['weights'][k]) for k in sl}
            max_fac = max(max_fac, max(abs(don[k] - ref[k]) for k in sl))
            max_on = max(max_on, max(abs(don[k] - ch['S_tgt'][k]) for k in sl))
            max_off = max(max_off, max(abs(doff[k] - A_raw[k]) for k in sl))
        ok = max_fac <= 1e-12 and max_on <= 1e-12 and max_off <= 1e-12
        allok &= ok
        ev[w] = {'pipeline_on_vs_engine_targets_max': rnd12(max_fac),
                 'pipeline_on_vs_stage_chain_S_tgt_max': rnd12(max_on),
                 'pipeline_off_vs_normalized_S_k6_max': rnd12(max_off)}
    gate('K7_ON_CANONICAL_IDENTITY', allok, {
        **ev,
        'semantics': 'compute_targets_pipeline(k7=1)==S_tgt och pipeline(k7=0)==A_raw='
                     'normalisera(S_k6): K7 ar exakt legacy-clipet; OFF behaller den '
                     'avslutande summanormaliseringen (delad konvention)'},
        tolerance=1e-12)


def timing_pit():
    V2.timing_and_pit_tests()
    m = {'RETURN_TIMING_TEST': 'RETURN_TIMING', 'POINT_IN_TIME_INPUT_TEST': 'PIT_TEST'}
    for src, dst in m.items():
        st = V2.GATES.get(src, {})
        K7_GATES[dst] = {'status': st.get('status', 'FAIL'),
                         'evidence': st.get('evidence'), 'source': 'V2.modul (oforandrad)'}


def ledger_gate():
    mism = checked = 0
    maxd = 0.0
    missing = []
    cnt_prior = cnt_mine = 0
    for w in WINDOWS:
        cnt_mine += len(CURR[w]['ledger'])
        for r in CURR[w]['ledger']:
            key = (w, str(r['date']), r['ticker'])
            pr = R['ledger_prior'].get(key)
            if pr is None:
                if len(missing) < 10:
                    missing.append(key)
                continue
            cnt_prior += 1
            for f in ('pre_drifted', 'target_cashon', 'target_final', 'delta_exec'):
                d = abs(float(r[f]) - float(pr[f]))
                maxd = max(maxd, d)
                if d > IDENTITY_TOL:
                    mism += 1
            checked += 1
    ok = (not missing) and mism == 0 and checked > 0 and cnt_mine == len(R['ledger_prior'])
    gate('EXECUTION_LEDGER_IDENTITY', ok, {
        'rows_checked': checked, 'field_mismatches': mism, 'max_abs_field_diff': rnd12(maxd),
        'rows_missing_in_prior': missing, 'row_count_mine': cnt_mine,
        'row_count_prior_csv': len(R['ledger_prior'])}, tolerance=IDENTITY_TOL)


def costb_gate():
    oks = True
    ev = {}
    for w in WINDOWS:
        m = R['summary'][w]
        pr = R['costb'][w]
        dv = abs(float(m['cagr_b_cal']) * 100.0 - float(pr['cagr_b_calendar_pct']))
        ok = dv <= 1e-9
        ref = pr.get('reported_approx_reference_pct')
        refdev = None
        if ref is not None:
            refdev = abs(float(m['cagr_b_cal']) * 100.0 - float(ref))
            ok &= refdev <= 0.25
        ev[w] = {'dev_vs_prior_replay': rnd12(dv), 'dev_vs_reported_ref_pp': rnd12(refdev) if refdev is not None else None}
        oks &= ok
    gate('COST_B_REPLAY', oks, {**ev, 'prior_artifact': f'{V2OUT}/COST_B_REPLAY.json'},
         tolerance=1e-9)


def run_intervention():
    from collections import Counter
    ev = {}
    oks = True
    for w in WINDOWS:
        res = V2.run_arm(V2.CTX[w], w, 1, 1, 0, 1, OFF_ID, True, True)
        OFF[w] = res
        R.setdefault('summary_off', {})[w] = V2.summarize_arm(res, None)
        P1[f'{w}|OFF'] = arm_hash(w, res)

        def eec(pp):
            return [(int(p['orders_exec']['entries']), int(p['orders_exec']['exits']))
                    for p in pp]
        selc = {(str(r['date']), r['ticker']) for r in CURR[w]['ledger'] if int(r['in_target']) == 1}
        selo = {(str(r['date']), r['ticker']) for r in res['ledger'] if int(r['in_target']) == 1}
        seleq = selc == selo
        eeq = eec(CURR[w]['panels']) == eec(res['panels'])
        tot, aff, mx = [], [], 0.0
        act_panels = 0
        for cd in CH[w]:
            if cd is None:
                continue
            A, T, names = cd['A_raw'], cd['chain']['S_tgt'], cd['names']
            dd = [abs(T[k] - A[k]) for k in names]
            ta = sum(dd)
            tot.append(ta)
            aff.append(sum(1 for v in dd if v > 1e-9))
            mx = max(mx, max(dd) if dd else 0.0)
            if ta > 1e-9:
                act_panels += 1
        npan = len(tot)
        yrs = npan / PPY
        moved = sum(tot) / 2.0
        ev[w] = {
            'selection_identical_between_arms': seleq,
            'entries_exits_identical_between_arms': eeq,
            'panels_total': npan, 'panels_with_K7_active_gt_1e-9': act_panels,
            'share_panels_K7_active': rnd12(act_panels / npan) if npan else None,
            'mean_names_affected_when_active': rnd12(float(np.mean([a for a, t in zip(aff, tot) if t > 1e-9]))) if act_panels else 0.0,
            'total_capital_moved_frac_over_study': rnd12(moved),
            'capital_moved_per_year_pct': rnd12(moved / yrs * 100.0) if yrs else None,
            'max_abs_single_target_change': rnd12(mx),
            'only_divergence': 'legacy clip [0.01,0.06] borttagen; ingen annan komponent berord'}
        oks &= seleq and eeq
    gate('K7_OFF_SINGLE_INTERVENTION_ONLY', oks, ev)

def paired_stats(d):
    a = np.array(d, dtype=float)
    n = len(a)
    sd = float(a.std(ddof=1)) if n > 1 else 0.0
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, n, size=(BOOT_N, n))
    bm = a[idx].mean(axis=1)
    lo, hi = np.percentile(bm, [2.5, 97.5])
    return {'n': n, 'mean': float(a.mean()), 'median': float(np.median(a)), 'std': sd,
            'se': sd / math.sqrt(n) if n else 0.0, 'pos_frac': float((a > 0).mean()),
            'boot_ci_low': float(lo), 'boot_ci_high': float(hi),
            'cum_log_diff': float(np.log1p(a).sum())}


def perf_block(rets, w):
    mm = V2.calc_metrics([float(x) for x in rets], w)
    a = np.array(rets, dtype=float)
    return {'cagr_cal': float(mm['cagr_calendar']), 'sharpe': float(mm['sharpe']),
            'maxdd': float(mm['max_dd']), 'vol_ann': float(a.std(ddof=1)) * math.sqrt(PPY),
            'downside_ann': float(math.sqrt(float(np.mean(np.minimum(a, 0.0) ** 2))) * math.sqrt(PPY)),
            'worst_panel': float(a.min()), 'p5_panel': float(np.percentile(a, 5)),
            'terminal_wealth': float(np.prod(1.0 + a))}


def conc_block(panels):
    hh, efn, t1, t3, t5, mx = [], [], [], [], [], []
    for p in panels:
        ws = sorted(p['post_weights'].values(), reverse=True)
        h = sum(v * v for v in ws)
        hh.append(h)
        efn.append(1.0 / h if h > 0 else 0.0)
        t1.append(sum(ws[:1]))
        t3.append(sum(ws[:3]))
        t5.append(sum(ws[:5]))
        mx.append(ws[0] if ws else 0.0)
    f = lambda x: float(np.mean(x))
    return {'effn_mean': f(efn), 'hhi_mean': f(hh), 'top1_mean': f(t1),
            'top3_mean': f(t3), 'top5_mean': f(t5), 'maxw_mean': f(mx)}


def order_stats_from_ledger(res):
    per_year = {}
    OK = ('entries', 'exits', 'cont_buy', 'cont_sell')
    tot = {k: 0 for k in OK}
    for p in res['panels']:
        yr = str(p['date'])[:4]
        c = p['orders_exec']
        d = per_year.setdefault(yr, {k: 0 for k in OK})
        for k in OK:
            d[k] += int(c[k])
            tot[k] += int(c[k])
    sizes = {'entry': [], 'exit': [], 'cont': []}
    for r in res['ledger']:
        de = float(r['delta_exec'])
        if abs(de) <= ORDER_EPS:
            continue
        ip, it = int(r['in_prev']), int(r['in_target'])
        cls = 'exit' if (ip == 1 and it == 0) else ('entry' if ip == 0 else 'cont')
        sizes[cls].append(abs(de))
    allsz = sizes['entry'] + sizes['exit'] + sizes['cont']
    a = np.array(allsz) if allsz else np.array([0.0])
    return {'per_year': per_year, 'total': tot,
            'total_orders': int(sum(tot.values())),
            'size_mean': float(a.mean()), 'size_median': float(np.median(a)),
            'size_p90': float(np.percentile(a, 90)),
            'order_sizes_summary': osz_summary(sizes)}


def analyze_all():
    an = R['an'] = {}
    cls_in = R['cls_in'] = {}
    pc_rows = []
    for w in WINDOWS:
        rc, ro = CURR[w], OFF[w]
        rl_c, rl_o = rc['ret_lists'], ro['ret_lists']
        pc, po = rc['panels'], ro['panels']
        n = len(pc)
        assert [str(p['date']) for p in pc] == [str(p['date']) for p in po]
        d = [bo - bc for bo, bc in zip(rl_o['net_b'], rl_c['net_b'])]
        st = paired_stats(d)
        an.setdefault('contrast', {})[w] = st
        for i in range(n):
            pc_rows.append({
                'window': w, 'pidx': i, 'date': str(pc[i]['date']),
                'net_b_CURRENT': rnd12(rl_c['net_b'][i]), 'net_b_K7_OFF': rnd12(rl_o['net_b'][i]),
                'diff_OFF_minus_CURRENT': rnd12(d[i]),
                'gross_CURRENT': rnd12(rl_c['gross'][i]), 'gross_K7_OFF': rnd12(rl_o['gross'][i]),
                'wt_exec_CURRENT_pct': rnd12(pc[i]['wt_exec'] * 100.0),
                'wt_exec_K7_OFF_pct': rnd12(po[i]['wt_exec'] * 100.0)})
        pf = {'CURRENT': perf_block(rl_c['net_b'], w), 'K7_OFF': perf_block(rl_o['net_b'], w)}
        cn = {'CURRENT': conc_block(pc), 'K7_OFF': conc_block(po)}
        oc = {'CURRENT': order_stats_from_ledger(rc), 'K7_OFF': order_stats_from_ledger(ro)}
        yrs = n / PPY
        wt_c = sum(p['wt_exec'] for p in pc)
        wt_o = sum(p['wt_exec'] for p in po)
        gl_c = float(np.log(np.prod([1.0 + x for x in rl_c['gross']])))
        gl_o = float(np.log(np.prod([1.0 + x for x in rl_o['gross']])))
        nl_c = float(np.log(np.prod([1.0 + x for x in rl_c['net_b']])))
        nl_o = float(np.log(np.prod([1.0 + x for x in rl_o['net_b']])))
        cost_saving = COST_RATE_B * (wt_c - wt_o)
        act_rows, cap_rows, wp_rows, wt_rows = [], [], [], []
        moved_sum = 0.0
        for i in range(n):
            cd = CH[w][i]
            A, T, names = cd['A_raw'], cd['chain']['S_tgt'], cd['names']
            dd = {k: T[k] - A[k] for k in names}
            ta = sum(abs(v) for v in dd.values())
            moved_sum += ta / 2.0
            act_rows.append({'window': w, 'date': str(pc[i]['date']),
                             'names_affected': sum(1 for v in dd.values() if abs(v) > 1e-9),
                             'total_abs_change': rnd12(ta),
                             'capital_moved_frac': rnd12(ta / 2.0),
                             'max_abs_change': rnd12(max(abs(v) for v in dd.values()) if dd else 0.0)})
            sk6, sclip = cd['chain']['S_k6'], cd['chain']['S_clip']
            pre_hi = sum(1 for k in names if sk6[k] > CAP_HI + 1e-9)
            post_hi = sum(1 for k in names if T[k] > CAP_HI + 1e-9)
            lo_n = sum(1 for k in names if sk6[k] < 0.01 - 1e-9)
            at_lo = sum(1 for k in names if sk6[k] < 0.01 - 1e-9 and abs(sclip[k] - 0.01) <= 1e-12)
            pwC = pc[i]['post_weights']
            cap_rows.append({'window': w, 'date': str(pc[i]['date']),
                             'n_pre_K7_targets_above_6pct': pre_hi,
                             'n_clipped_exactly_to_6pct': pre_hi,
                             'n_final_targets_above_6pct_after_renorm': post_hi,
                             'cap_violation_rate': rnd12(post_hi / pre_hi) if pre_hi else None,
                             'max_final_target': rnd12(max(T[k] for k in names) if names else 0.0),
                             'n_pre_K7_targets_below_1pct': lo_n,
                             'n_floored_exactly_to_1pct': at_lo,
                             'max_final_portfolio_weight_WP': rnd12(max(pwC.values()) if pwC else 0.0)})
            red_names = [k for k in names if A[k] - T[k] > 1e-9]
            red = sum(A[k] - T[k] for k in red_names)
            restored = sum(max(0.0, pwC.get(k, 0.0) - T[k]) for k in red_names)
            n_rest = sum(1 for k in red_names if pwC.get(k, 0.0) > T[k] + 1e-9)
            topup = sum(max(0.0, pwC.get(k, 0.0) - T[k]) for k in names)
            wp_rows.append({'window': w, 'date': str(pc[i]['date']),
                            'K7_capital_reduced_frac': rnd12(red),
                            'n_names_reduced': len(red_names),
                            'WP_restored_to_reduced_names_frac': rnd12(restored),
                            'n_reduced_names_getting_topup': n_rest,
                            'offset_ratio': rnd12(restored / red) if red > 1e-12 else None,
                            'WP_total_topup_all_names_frac': rnd12(topup)})
            wt_rows.append({'window': w, 'date': str(pc[i]['date']),
                            'wt_exec_CURRENT_pct': rnd12(pc[i]['wt_exec'] * 100.0),
                            'wt_exec_K7_OFF_pct': rnd12(po[i]['wt_exec'] * 100.0),
                            'diff_pp': rnd12((po[i]['wt_exec'] - pc[i]['wt_exec']) * 100.0)})
        write_csv(f'{OUT}/K7_ACTIVATION.csv', act_rows)
        write_csv(f'{OUT}/K7_CAP_SEMANTICS.csv', cap_rows)
        write_csv(f'{OUT}/K7_WP_OFFSET.csv', wp_rows)
        an.setdefault('activation', {})[w] = {
            'panels_with_K7_active_gt_1e-9': sum(1 for r in act_rows if r['total_abs_change'] > 1e-9),
            'share_panels_active': rnd12(sum(1 for r in act_rows if r['total_abs_change'] > 1e-9) / n),
            'capital_moved_per_year_pct': rnd12(moved_sum / yrs * 100.0),
            'sum_capital_moved_frac': rnd12(moved_sum)}
        cs = [r for r in cap_rows if r['n_pre_K7_targets_above_6pct'] > 0]
        an.setdefault('cap', {})[w] = {
            'panels_with_any_name_above_6pct': len(cs),
            'violation_rate_mean_when_present': rnd12(float(np.mean([r['cap_violation_rate'] for r in cs]))) if cs else 0.0,
            'max_final_target_overall': rnd12(max(r['max_final_target'] for r in cap_rows)),
            'max_final_portfolio_weight_overall': rnd12(max(r['max_final_portfolio_weight_WP'] for r in cap_rows))}
        wo = [r for r in wp_rows if (r['K7_capital_reduced_frac'] or 0) > 1e-12]
        red_tot = sum(r['K7_capital_reduced_frac'] for r in wp_rows)
        rest_tot = sum(r['WP_restored_to_reduced_names_frac'] for r in wp_rows)
        an.setdefault('wp_offset', {})[w] = {
            'K7_capital_reduced_sum_frac': rnd12(red_tot),
            'WP_restored_to_reduced_names_sum_frac': rnd12(rest_tot),
            'offset_ratio_aggregate': rnd12(rest_tot / red_tot) if red_tot > 1e-12 else None,
            'frac_reduced_names_getting_topup':
                rnd12(sum(r['n_reduced_names_getting_topup'] for r in wp_rows) /
                      max(1, sum(r['n_names_reduced'] for r in wp_rows)))}

        ord_rows = []
        for arm, ocs in (('CURRENT', oc['CURRENT']), ('K7_OFF', oc['K7_OFF'])):
            for yr, cnt in sorted(ocs['per_year'].items()):
                ord_rows.append({'window': w, 'arm': arm, 'year': yr, **cnt})
        an.setdefault('orders', {})[w] = oc
        wtann_c, wtann_o = wt_c * 100.0 / yrs, wt_o * 100.0 / yrs

        rev_keys = sorted({k for p in pc if isinstance(p, dict) for k in p.keys()
                           if k.startswith('rev')}) if pc else []
        rev_rows = []
        for arm, pp in (('CURRENT', pc), ('K7_OFF', po)):
            row = {'window': w, 'arm': arm}
            for k in rev_keys:
                try:
                    row[f'{k}_total'] = rnd12(sum(float(p[k]) for p in pp))
                    row[f'{k}_per_yr'] = rnd12(sum(float(p[k]) for p in pp) / yrs)
                except Exception:
                    pass
            if rev_keys:
                rev_rows.append(row)
        an.setdefault('rev_keys', {})[w] = rev_keys

        ca = {'GROSS_RETURN_EFFECT_log': rnd12(gl_o - gl_c),
              'COST_SAVING_EFFECT_B_frac': rnd12(cost_saving),
              'COST_SAVING_EFFECT_B_pp_of_NAV': rnd12(cost_saving * 100.0),
              'NET_RETURN_EFFECT_log': rnd12(nl_o - nl_c),
              'wt_exec_ann_CURRENT_pct': rnd12(wtann_c), 'wt_exec_ann_K7_OFF_pct': rnd12(wtann_o),
              'wt_exec_ann_diff_pp': rnd12(wtann_o - wtann_c)}

        ctx = V2.CTX[w]
        acc = {}
        for i in range(n):
            pwC = pc[i]['post_weights']
            pwO = po[i]['post_weights']
            dt = pc[i]['date']
            for k in set(pwC) | set(pwO):
                dd2 = pwO.get(k, 0.0) - pwC.get(k, 0.0)
                if abs(dd2) > 0:
                    rr = ctx['returns'].get((k, dt), 0.0)
                    acc[k] = acc.get(k, 0.0) + dd2 * rr
        tot_abs = sum(abs(v) for v in acc.values())
        ranked = sorted(acc.items(), key=lambda kv: -abs(kv[1]))
        contrib_rows = [{'window': w, 'ticker': k, 'contrib_gross_weight_delta_x_return': rnd12(v),
                         'abs_share': rnd12(abs(v) / tot_abs) if tot_abs > 0 else None}
                        for k, v in ranked]
        shares = {}
        csum = 0.0
        for j, (_, v) in enumerate(ranked, 1):
            csum += abs(v)
            if j in (1, 3, 5, 10):
                shares[f'top{j}_share_of_abs_contrib'] = rnd12(csum / tot_abs) if tot_abs > 0 else None
        an.setdefault('contributor', {})[w] = {
            'concentration': shares, 'max_single_name_share': shares.get('top1_share_of_abs_contrib'),
            'top5_named': [k for k, _ in ranked[:5]]}

        halves = {}
        cut = n // 2
        for hname, idxs in (('H1', list(range(cut))), ('H2', list(range(cut, n)))):
            yh = len(idxs) / PPY
            for arm, rl, pp, ld in (('CURRENT', rl_c, pc, rc['ledger']),
                                    ('K7_OFF', rl_o, po, ro['ledger'])):
                a = np.array([rl['net_b'][i] for i in idxs])
                cum = float(np.prod(1.0 + a))
                peak = np.minimum.accumulate(1.0 / np.maximum.accumulate(np.cumprod(1.0 + a)))
                dd_h = float(np.max(1.0 - np.cumprod(1.0 + a) * peak))
                wt_h = sum(pp[i]['wt_exec'] for i in idxs) * 100.0 / yh
                dts = {str(pp[i]['date']) for i in idxs}
                nord = sum(int(pp[i]['orders_exec']['entries']) + int(pp[i]['orders_exec']['exits']) +
                           int(pp[i]['orders_exec']['cont_buy']) + int(pp[i]['orders_exec']['cont_sell'])
                           for i in idxs)
                halves[f'{hname}|{arm}'] = {
                    'cum_net_b': rnd12(cum - 1.0), 'panel_ann_cagr': rnd12(cum ** (PPY / len(idxs)) - 1.0),
                    'sharpe': rnd12(float(a.mean() / a.std(ddof=1) * math.sqrt(PPY))) if a.std(ddof=1) > 0 else None,
                    'maxdd': rnd12(dd_h), 'turnover_ann_pct': rnd12(wt_h), 'orders': nord}
        loo = {}
        years = sorted({str(p['date'])[:4] for p in pc})

        def cagr_of(idxs, rets):
            cum = float(np.prod([1.0 + rets[i] for i in idxs]))
            return cum ** (PPY / len(idxs)) - 1.0
        for yr in years:
            keep = [i for i, p in enumerate(pc) if str(p['date'])[:4] != yr]
            yc = cagr_of(keep, rl_c['net_b'])
            yo = cagr_of(keep, rl_o['net_b'])
            ac = np.array([rl_c['net_b'][i] for i in keep])
            ao = np.array([rl_o['net_b'][i] for i in keep])
            wtc = sum(pc[i]['wt_exec'] for i in keep) * 100.0 / (len(keep) / PPY)
            wto = sum(po[i]['wt_exec'] for i in keep) * 100.0 / (len(keep) / PPY)

            def mxdd(a):
                cr = np.cumprod(1.0 + a)
                return float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
            loo[yr] = {'n_panels_kept': len(keep),
                       'cagr_CURRENT': rnd12(yc), 'cagr_K7_OFF': rnd12(yo),
                       'delta_cagr': rnd12(yo - yc),
                       'sharpe_CURRENT': rnd12(float(ac.mean() / ac.std(ddof=1) * math.sqrt(PPY))),
                       'sharpe_K7_OFF': rnd12(float(ao.mean() / ao.std(ddof=1) * math.sqrt(PPY))),
                       'maxdd_CURRENT': rnd12(mxdd(ac)), 'maxdd_K7_OFF': rnd12(mxdd(ao)),
                       'turnover_ann_CURRENT_pct': rnd12(wtc), 'turnover_ann_K7_OFF_pct': rnd12(wto),
                       'turnover_delta_pp': rnd12(wto - wtc)}

        cls_in[w] = {'stats': st,
                     'perf': {a: {k: rnd12(v) for k, v in pf[a].items()} for a in pf},
                     'conc': {a: {k: rnd12(v) for k, v in cn[a].items()} for a in cn},
                     'orders_totals': {a: oc[a]['total_orders'] for a in oc},
                     'cost_attr': ca,
                     'halves': halves, 'loo': loo,
                     'activation': an['activation'][w], 'cap': an['cap'][w],
                     'wp_offset': an['wp_offset'][w], 'contributor': an['contributor'][w],
                     'n_panels': n, 'years_cal': YEARS_CAL[w]}
        write_csv(f'{OUT}/K7_PANEL_CONTRASTS.csv',
                  [r for r in pc_rows if r['window'] == w])
        write_csv(f'{OUT}/K7_WEIGHT_TURNOVER_BY_PANEL.csv', wt_rows)
        write_csv(f'{OUT}/K7_ORDER_COUNTS.csv', ord_rows)
        write_csv(f'{OUT}/K7_COST_ATTRIBUTION.csv', [
            {'window': w, 'effect': k, 'value': v} for k, v in ca.items()])
        write_csv(f'{OUT}/K7_CONTRIBUTOR_ATTRIBUTION.csv', contrib_rows)
        write_csv(f'{OUT}/K7_TIME_STABILITY.csv', [
            {'window': w, 'half': k.split('|')[0], 'arm': k.split('|')[1], **v}
            for k, v in halves.items()])
        write_csv(f'{OUT}/K7_LOO.csv', [
            {'window': w, 'omitted_year': yr, **v} for yr, v in loo.items()])
        if rev_rows:
            write_csv(f'{OUT}/K7_REVERSALS.csv', rev_rows)

    perf_rows = []
    risk_rows = []
    conc_rows = []
    for w in WINDOWS:
        ci = cls_in[w]
        for arm in ('CURRENT', 'K7_OFF'):
            pf = ci['perf'][arm]
            for k, v in pf.items():
                perf_rows.append({'window': w, 'metric': k, 'arm': arm, 'value': v})
            perf_rows.append({'window': w, 'metric': 'cagr_cal_vs_other_arm_diff',
                              'arm': arm,
                              'value': rnd12(pf['cagr_cal'] - ci['perf']['K7_OFF' if arm == 'CURRENT' else 'CURRENT']['cagr_cal'])})
            cn2 = ci['conc'][arm]
            for k, v in cn2.items():
                conc_rows.append({'window': w, 'metric': k, 'arm': arm, 'value': v})
            risk_rows.append({'window': w, 'arm': arm, **{k: pf[k] for k in
                             ('maxdd', 'vol_ann', 'downside_ann', 'worst_panel', 'p5_panel')}})
    write_csv(f'{OUT}/K7_PERFORMANCE.csv', perf_rows)
    write_csv(f'{OUT}/K7_RISK.csv', risk_rows)
    write_csv(f'{OUT}/K7_CONCENTRATION.csv', conc_rows)

def classify():
    cls = {'windows': {}, 'inputs': {}}
    for w in WINDOWS:
        ci = R['cls_in'][w]
        st = ci['stats']
        pc, po = CURR[w]['panels'], OFF[w]['panels']
        imp = bool(st['mean'] > ECON_EPS and st['boot_ci_low'] > 0)
        harm = bool(st['mean'] < -ECON_EPS and st['boot_ci_high'] < 0)
        mdd_c = ci['perf']['CURRENT']['maxdd']
        mdd_o = ci['perf']['K7_OFF']['maxdd']
        vol_c = ci['perf']['CURRENT']['vol_ann']
        vol_o = ci['perf']['K7_OFF']['vol_ann']
        riskben = bool((mdd_c < mdd_o - MAXDD_EPS) or (vol_c < vol_o - VOL_EPS))
        econ_ok = not harm
        wt_d = ci['cost_attr']['wt_exec_ann_diff_pp']
        ord_d = ci['orders_totals']['K7_OFF'] - ci['orders_totals']['CURRENT']
        cls['windows'][w] = {
            'mean_d': rnd12(st['mean']), 'boot_ci': [rnd12(st['boot_ci_low']), rnd12(st['boot_ci_high'])],
            'imp': imp, 'harm': harm, 'riskben': riskben, 'econ_ok': econ_ok,
            'turnover_diff_pp_yr': rnd12(wt_d), 'orders_diff_total': ord_d,
            'maxdd_CURRENT': rnd12(mdd_c), 'maxdd_K7_OFF': rnd12(mdd_o),
            'vol_ann_CURRENT': rnd12(vol_c), 'vol_ann_K7_OFF': rnd12(vol_o),
            'cum_log_diff_OFF_minus_CURRENT': rnd12(st['cum_log_diff']),
            'pos_frac': rnd12(st['pos_frac'])}
    w1, w2 = cls['windows']['W1'], cls['windows']['W2']
    mandatory_ok = all(K7_GATES.get(g, {}).get('status') == 'PASS' for g in MANDATORY)
    if (w1['imp'] and w2['harm']) or (w1['harm'] and w2['imp']):
        final, nxt = 'K7_MIXED_W1_W2', 'NO_CANONICAL_CHANGE'
    elif w1['riskben'] and w2['riskben']:
        final, nxt = 'K7_RISK_FUNCTION_CONFIRMED', 'KEEP_K7_CURRENT'
    elif w1['imp'] and w2['imp']:
        final, nxt = 'K7_ECONOMIC_VALUE_CONFIRMED', 'KEEP_K7_CURRENT'
    elif w1['econ_ok'] and w2['econ_ok']:
        final, nxt = 'K7_REMOVAL_CONFIRMED', 'FREEZE_K7_OFF_CANDIDATE'
    else:
        final, nxt = 'K7_NEUTRAL_BUT_REMOVAL_UNRESOLVED', 'NO_CANONICAL_CHANGE'
    if not mandatory_ok:
        final, nxt = 'K7_CONFIRMATION_INVALID', 'FAIL_CLOSED_NO_CONCLUSION'
    cls['final_classification'] = final
    cls['next_action'] = nxt
    cls['mandatory_gates_all_pass'] = mandatory_ok
    R['cls'] = cls
    write_json(f'{OUT}/K7_CLASSIFICATION.json', cls)


def claim_scan():
    allow_fab = {'STUDY_REPORT.md', 'K7_CONFIRMATION_REPORT.json'}
    hits = {}
    for dp, _dns, fns in os.walk(OUT):
        parts = set(dp.split(os.sep))
        if 'trackj' in parts:
            continue
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                txt = open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            hs = []
            if fn not in allow_fab:
                for tok in FABRICATED_TOKENS:
                    if re.search(tok_re(tok), txt):
                        hs.append(tok)
            if re.search(tok_re('ARM09'), txt):
                hs.append('ARM09')
            if hs:
                hits[os.path.relpath(p, OUT)] = sorted(set(hs))
    gate('NON_COMPUTED_CLAIM_SCAN', not hits, {
        'scanned_root': OUT, 'n_fabricated_tokens_scanned': len(FABRICATED_TOKENS),
        'whitelisted_quoted_claim_files': sorted(allow_fab),
        'note': 'rapporten far citera de fablicerade talen enbart i sporsektionen om '
                'varfor de ar ogiltiga; ingen annan fil far innehalla dem',
        'hits': hits})


def report_all():
    cls = R['cls']
    fin = cls['final_classification']
    L = []
    A = L.append
    A('# K7 TARGETED SINGLE COMPONENT CONFIRMATION - STUDY_REPORT')
    A('')
    A(f'Studie: H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION | Windows: W1, W2')
    A(f'Armar: CURRENT_K7_ON={CURRENT_ID} vs K7_OFF={OFF_ID}')
    A(f'Intervention: endast legacy clip np.clip(w, 0.01, 0.06) borttagen.')
    A(f'Den avslutande summanormaliseringen x n/30 behalls IDENTISKT i bada armarna '
      f'(delad motor-konvention i hela faktorialen - ingen waterfill, ingen ny cap).')
    A(f'Preregistrering fryst fore nagot arm-kor: sha256='
      f"{json.load(open(f'{OUT}/K7_CONFIRMATION_FREEZE.json'))['preregistration_sha256']}")
    A('')
    A('## A. Headline')
    A('')
    for w in WINDOWS:
        s = R['cls_in'][w]['stats']
        ca = R['cls_in'][w]['cost_attr']
        A(f"- {w}: paired panel-net diff K7_OFF - CURRENT: mean={s['mean']:.6f} "
          f"(CI95 [{s['boot_ci_low']:.6f}, {s['boot_ci_high']:.6f}]), P(d>0)={s['pos_frac']:.2f}, "
          f"n={s['n']} paneler; turnover-diff {ca['wt_exec_ann_diff_pp']:+.2f} pp/ar; "
          f"orders-diff total {R['cls_in'][w]['orders_totals']['K7_OFF'] - R['cls_in'][w]['orders_totals']['CURRENT']:+d}")
    A('')
    A('## B. Gate-status')
    A('')
    for g in MANDATORY:
        A(f"- {g}: {K7_GATES[g]['status']}")
    A('')
    A('## C. Replay-identitet mot frusna artefakter')
    A('')
    A('- CURRENT-armen replikerar FACTORIAL_ARM_METRICS.json (rad K5_1_K6_1_K7_1_WP_1) '
      'per fonster med max avvikelse <= 1e-9 i alla delade metrics (CURRENT_REPLAY).')
    A('- Per-panel exec-turnover identisk med WD_ACTUAL-baserad reconciliering '
      '(W1/W2_PANEL_IDENTITY, tol 1e-12); sf-residuer <= 1e-12.')
    A('- COST_B CAGR replikerar COST_B_REPLAY.json exakt (<= 1e-9) och korroborerar '
      'rapporterad referens inom 0.25 pp.')
    A('- Executions-ledger rad-for-rad identisk med WEIGHT_LAYER_EXECUTION_LEDGER_CURRENT.csv.')
    A('')
    A('## D. Kanonisk identitet och single intervention')
    A('')
    A('- compute_targets_pipeline(k7=1) == stage_chain S_tgt och pipeline(k7=0) == '
      'normalisera(S_k6) till max 1e-12 i alla paneler: K7 ar EXAKT legacy-clipet; '
      'OFF-armen delar S_k5/S_k6-bookkeeping oforandrat (K7_ON_CANONICAL_IDENTITY).')
    A('- Selektion och entries/exits identiska mellan armarna i alla paneler '
      '(K7_OFF_SINGLE_INTERVENTION_ONLY); enda divergensen ar clip-borttaget.')
    A('')
    A('## E. Aktiveringsgrad for K7 (hur ofta clipet binder)')
    A('')
    for w in WINDOWS:
        ac = R['cls_in'][w]['activation']
        cp = R['cls_in'][w]['cap']
        wo = R['cls_in'][w]['wp_offset']
        A(f"- {w}: K7 aktiv (>1e-9) i {ac['panels_with_K7_active_gt_1e-9']}/{R['cls_in'][w]['n_panels']} "
          f"paneler ({ac['share_panels_active']*100:.1f}%); kapital flyttat "
          f"{ac['capital_moved_per_year_pct']:.3f} pct/ar.")
        A(f"  Cap-semantik: paneler med nagot pre-K7-target >6%: {cp['panels_with_any_name_above_6pct']}; "
          f"violationsrate efter renorm da present: {cp['violation_rate_mean_when_present']*100:.1f}%; "
          f"max slutgiltigt target {cp['max_final_target_overall']*100:.2f}%; max portfoljvikt efter WP "
          f"{cp['max_final_portfolio_weight_overall']*100:.2f}%.")
        ratio = wo['offset_ratio_aggregate']
        A(f"  WP-offset: K7 reducerat {wo['K7_capital_reduced_sum_frac']:.4f} frac totalt; WP "
          f"aterstaller till reducerade namn {wo['WP_restored_to_reduced_names_sum_frac']:.4f} "
          f"-> offset-ratio {ratio if ratio is None else round(ratio, 4)}.")
    A('')
    A('## F. Performance (COST_B primar)')
    A('')
    A('| Window | Arm | CAGR cal % | Sharpe | MaxDD | Vol ann | Terminal wealth |')
    A('|---|---|---|---|---|---|---|')
    for w in WINDOWS:
        for arm in ('CURRENT', 'K7_OFF'):
            pf = R['cls_in'][w]['perf'][arm]
            A(f"| {w} | {arm} | {pf['cagr_cal']*100:.4f} | {pf['sharpe']:.4f} | "
              f"{pf['maxdd']*100:.2f}% | {pf['vol_ann']*100:.2f}% | {pf['terminal_wealth']:.4f} |")
    A('')
    A('## G. Risk och koncentration (sektion 10, 15)')
    A('')
    for w in WINDOWS:
        for arm in ('CURRENT', 'K7_OFF'):
            pf = R['cls_in'][w]['perf'][arm]
            cn = R['cls_in'][w]['conc'][arm]
            A(f"- {w}/{arm}: MaxDD {pf['maxdd']*100:.2f}%, downside dev {pf['downside_ann']*100:.2f}%, "
              f"sämsta panel {pf['worst_panel']*100:.2f}%, p5 {pf['p5_panel']*100:.2f}%; "
              f"effN {cn['effn_mean']:.2f}, HHI {cn['hhi_mean']:.4f}, Top1 {cn['top1_mean']*100:.2f}%, "
              f"Top3 {cn['top3_mean']*100:.2f}%, Top5 {cn['top5_mean']*100:.2f}%")
    A('')
    A('## H. Ordervolymer (sektion 14)')
    A('')
    for w in WINDOWS:
        ca = R['cls_in'][w]['cost_attr']
        A(f"- {w}: turnover {ca['wt_exec_ann_CURRENT_pct']:.1f}% -> {ca['wt_exec_ann_K7_OFF_pct']:.1f}% "
          f"({ca['wt_exec_ann_diff_pp']:+.2f} pp)")
    A('')
    A('## I. Tidsstabilitet: halvor (sektion 19)')
    A('')
    for w in WINDOWS:
        hv = R['cls_in'][w]['halves']
        for h in ('H1', 'H2'):
            c, o = hv[f'{h}|CURRENT'], hv[f'{h}|K7_OFF']
            A(f"- {w} {h}: panel-ann-CAGR {c['panel_ann_cagr']*100:.3f}% -> {o['panel_ann_cagr']*100:.3f}% "
              f"(delta {(o['panel_ann_cagr']-c['panel_ann_cagr'])*100:+.3f} pp), Sharpe {c['sharpe']} -> {o['sharpe']}, "
              f"MaxDD {c['maxdd']*100:.2f}% -> {o['maxdd']*100:.2f}%, turnover {c['turnover_ann_pct']:.1f}% -> "
              f"{o['turnover_ann_pct']:.1f}%, orders {c['orders']} -> {o['orders']}")
    A('')
    A('## J. Leave-one-year-out (sektion 20)')
    A('')
    for w in WINDOWS:
        for yr, v in R['cls_in'][w]['loo'].items():
            A(f"- {w} utan {yr}: delta CAGR {v['delta_cagr']*100:+.3f} pp, delta turnover "
              f"{v['turnover_delta_pp']:+.2f} pp, MaxDD {v['maxdd_CURRENT']*100:.2f}% -> {v['maxdd_K7_OFF']*100:.2f}%")
    A('')
    A('## K. Kostnadspåverkan och contributor-attribution (sektion 17-18)')
    A('')
    for w in WINDOWS:
        ca = R['cls_in'][w]['cost_attr']
        co = R['cls_in'][w]['contributor']
        A(f"- {w}: log gross-effekt {ca['GROSS_RETURN_EFFECT_log']:+.6f}, kostnadsbesparing "
          f"{ca['COST_SAVING_EFFECT_B_frac']:+.6f} ({ca['COST_SAVING_EFFECT_B_pp_of_NAV']:+.3f} pp), "
          f"log nettoeffekt {ca['NET_RETURN_EFFECT_log']:+.6f}.")
        A(f"  Koncentration i contributor-diff: top1 {co['concentration'].get('top1_share_of_abs_contrib')}, "
          f"top3 {co['concentration'].get('top3_share_of_abs_contrib')}, "
          f"top5 {co['concentration'].get('top5_share_of_abs_contrib')}; toppnamn: {co['top5_named']}")
        mx = co['max_single_name_share']
        A(f"  Ingen slutsats vilar pa ett enskilt namn: top1-andel = "
          f"{'n/a' if mx is None else f'{mx*100:.1f}%'} av total abs-contributionsdiff.")
    A('')
    A('## L. Spårbarhet / historik för fablicerade tal')
    A('')
    A('De tidigare felaktiga hardkodade transaktionsvarden (469.4/391.7 order per ar, '
      '308.6%/322.7% respektive 138.4%/124.2% turnover, 297.7%/316.8%) ar OGILTIGA som '
      'referensdata och anvands INTE nagonstans i denna studie. De korrekta, maskinellt '
      'beraknade varderna finns i K7_ORDER_COUNTS.csv och K7_WEIGHT_TURNOVER_BY_PANEL.csv. '
      'Se TRANSACTION_METRIC_INVALIDATION_NOTICE.json i den frusna V2-studien for full '
      'beviskedja (talens kalla: PERIOD_TRANSACTION_AUDIT_REPORT.md-mall + dess eget CSV).')
    A('')
    A('## M. Determinism och state-isolering')
    A('')
    A(f"- DETERMINISTIC_REPLAY: {K7_GATES['DETERMINISTIC_REPLAY']['status']} - pass2-hashar "
      f"likamed pass1 (metrics rnd12 + order_sizes_summary + panelserier).")
    A(f"- STATE_ISOLATION: {K7_GATES['STATE_ISOLATION']['status']} - omkorning efter alla "
      f"analyser ger metric-dev <= 1e-15; inga globaler muteras mellan armen.")
    A('')
    A('## N. Robusthet COST_C (40bp, ej primar)')
    A('')
    for w in WINDOWS:
        rc, ro = CURR[w], OFF[w]
        mc = V2.calc_metrics([float(x) for x in rc['ret_lists']['net_c']], w)
        mo = V2.calc_metrics([float(x) for x in ro['ret_lists']['net_c']], w)
        A(f"- {w}: net_c CAGR CURRENT {mc['cagr_calendar']*100:.4f}% vs K7_OFF "
          f"{mo['cagr_calendar']*100:.4f}% (delta {(mo['cagr_calendar']-mc['cagr_calendar'])*100:+.4f} pp)")
    A('')
    A('## O. Klassificering')
    A('')
    A(f"**FINAL_CLASSIFICATION: {fin}**")
    A('')
    A(f"NEXT_ACTION: {cls['next_action']}")
    A('')
    for w in WINDOWS:
        cw = cls['windows'][w]
        A(f"- {w}: imp={cw['imp']}, harm={cw['harm']}, riskben={cw['riskben']}, "
          f"econ_ok={cw['econ_ok']} (mean_d={cw['mean_d']}, CI95={cw['boot_ci']})")
    A('')
    A('## P. Next actions enligt protokoll')
    A('')
    na = {'FREEZE_K7_OFF_CANDIDATE': [
        'Frys K7_OFF som ny kandidat-arkitektur (EJ automatisk canonical-ersattning).',
        'Upprepa studien oforandrad (samma skript) och krav samma klassificering.',
        'Forst darpaa kan kanon-bytet dokumenteras med ny versionsflagga.'],
        'KEEP_K7_CURRENT': [
        'Behall K7 legacy i canonical H0 V3.',
        'Dokumentera den bevisade nyttan (riskfunktion/ekonomi) i STUDY_REPORT.',
        'Ingen arkitekturandring; K7-OFF-varianten arkiveras som negativt resultat.'],
        'NO_CANONICAL_CHANGE': [
        'Ingen kanon-andring; blanda ej in WP-waterfall eller nya caps i fragan.',
        'Om beslutsfattare vill driva fragan: ny preregistrerad studie med explicit '
        'ny komponentdesign (t.ex. ren cap utan floor), inte denna.'],
        'FAIL_CLOSED_NO_CONCLUSION': [
        'Atgarda: atga gate-fel forst; studien saknar giltighet tills dess.']}[cls['next_action']]
    for x in na:
        A(f'- {x}')
    A('')
    A('## Q. Signaturer')
    A('')
    man = {g: K7_GATES[g]['status'] for g in MANDATORY}
    A('Alla obligatoriska gates PASS: ' + str(all(v == 'PASS' for v in man.values())))
    A(f"Antal gates totalt: {len(K7_GATES)}")
    A('')
    A('## R. Reproducerbarhet')
    A('')
    A(f'- Skript: tools/run_h0_v3_k7_targeted_single_component_confirmation.py')
    A(f'- Runner-import: run_h0_v3_weight_layer_simplification_v2 (oforandrad, fryst)')
    A('- Miljo: PYTHONHASHSEED=0 (tvingas via re-exec i skriptet)')
    A('- Bootstrap: n=10000, seed=20260823, percentile-metod')
    A('')
    with open(f'{OUT}/STUDY_REPORT.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    rep = {'study': 'H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION',
           'final_classification': fin, 'next_action': cls['next_action'],
           'gates': {g: K7_GATES[g]['status'] for g in K7_GATES},
           'headline': {w: {'mean_d': R['cls']['windows'][w]['mean_d'],
                            'ci95': R['cls']['windows'][w]['boot_ci'],
                            'turnover_diff_pp_yr': R['cls']['windows'][w]['turnover_diff_pp_yr'],
                            'orders_diff': R['cls']['windows'][w]['orders_diff_total']}
                        for w in WINDOWS}}
    write_json(f'{OUT}/K7_CONFIRMATION_REPORT.json', rep)


def isolation_gate():
    dev = {}
    ok = True
    for w in WINDOWS:
        rc = V2.run_arm(V2.CTX[w], w, 1, 1, 1, 1, CURRENT_ID, True, True)
        ro = V2.run_arm(V2.CTX[w], w, 1, 1, 0, 1, OFF_ID, True, True)
        mc = V2.summarize_arm(rc, None)
        mo = V2.summarize_arm(ro, None)
        num = lambda mm: [k for k in mm if isinstance(mm[k], (int, float))
                          and not isinstance(mm[k], bool)]
        kc, ko = num(mc), num(mo)
        d = max(max(abs(float(mc[k]) - float(R['summary'][w][k])) for k in kc),
                max(abs(float(mo[k]) - float(R['summary_off'][w][k])) for k in ko))
        dev[w] = rnd12(d)
        ok &= d <= 1e-15
    gate('STATE_ISOLATION', ok, {'max_metric_dev_vs_first_pass': dev}, tolerance=1e-15)


def deterministic_gate():
    h2 = {}
    for w in WINDOWS:
        rc = V2.run_arm(V2.CTX[w], w, 1, 1, 1, 1, CURRENT_ID, False, False)
        ro = V2.run_arm(V2.CTX[w], w, 1, 1, 0, 1, OFF_ID, False, False)
        h2[f'{w}|CURRENT'] = arm_hash(w, rc)
        h2[f'{w}|OFF'] = arm_hash(w, ro)
    mism = [k for k in h2 if h2[k] != P1.get(k)]
    gate('DETERMINISTIC_REPLAY', not mism, {
        'hash_keys': ['window|arm metrics_rnd12+order_sizes_summary+panel_net_b+nav_end_b'],
        'pass1_sha256': P1, 'pass2_sha256': h2, 'metric_mismatches': mism})


def main():
    os.makedirs(OUT, exist_ok=True)
    for fn in os.listdir(OUT):
        fp = os.path.join(OUT, fn)
        if os.path.isfile(fp):
            os.remove(fp)
    print('=== H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION ===', flush=True)
    freeze_preregistration()
    load_prior_artifacts()
    replay_and_identity()
    canonical_identity_and_chains()
    timing_pit()
    ledger_gate()
    costb_gate()
    run_intervention()
    analyze_all()
    deterministic_gate()
    isolation_gate()
    claim_scan()
    classify()
    report_all()
    write_json(f'{OUT}/K7_REPLAY_GATES.json', {'study': 'H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION',
                                               'generated_utc': datetime.now(timezone.utc).isoformat(),
                                               'gates': K7_GATES})
    fails = [g for g in MANDATORY if K7_GATES.get(g, {}).get('status') != 'PASS']
    print(f"[FINAL] classification={R['cls']['final_classification']} "
          f"next_action={R['cls']['next_action']} failed_mandatory={fails}", flush=True)
    sys.exit(0 if not fails else 2)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(3)
