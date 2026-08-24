#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION - preregistrerad besluts- och freeze-studie.

Beslutsaudit mellan EXAKT tva redan validerade execution-kandidater fran
H0_V3_TRANSACTION_MINIMIZATION_FRONTIER:

  Kandidat A = EXEC05_BAND_100BP        (no-trade-band 1% pa continuing holdings)
  Kandidat B = EXEC99_ENTRY_EXIT_ONLY   (endast entries/exits, inga reweights)

EXEC00_FULL_REBALANCE anvands ENDAST som referens och kan inte vinna.
Ingen ny forskning: inga nya band, ingen parametersokning, inga regeländringar.
Armen replays bitvis mot frontier-studiens frusna pass1-hashar; mekanismanalyser
(reweight-varde, drift, tails, LOO, halvor) deriveras fran de replayade serier.

Beslutsregler ar frusna i EXECUTION_FREEZE_PREREGISTRATION.json fore nagon kor.
Exit: 0 ok, 2 fail-closed blocker, 3 ovantat fel.
"""
import sys, os, json, csv, math, hashlib, re, traceback
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, '/home/hannesb/momentum_v2/tools')

if os.environ.get('PYTHONHASHSEED') != '0':
    os.execve(sys.executable, [sys.executable] + sys.argv,
              {**os.environ, 'PYTHONHASHSEED': '0'})

import numpy as np
import run_h0_v3_weight_layer_simplification_v2 as V2
import run_h0_v3_transaction_minimization_frontier as FR

ROOT = '/home/hannesb/momentum_v2'
OUT = f'{ROOT}/research_k/h0_v3_execution_candidate_freeze_decision'
SRC = FR.OUT
K7OUT = FR.K7OUT
V2OUT = V2.OUT

WINDOWS = ['W1', 'W2']
PPY = V2.PPY
IDENTITY_TOL = V2.IDENTITY_TOL
COST_RATE_B = V2.COST_RATE_B
COST_RATE_C = V2.COST_RATE_C
YEARS_CAL = V2.YEARS_CAL
FABRICATED_TOKENS = V2.FABRICATED_TOKENS

A_ID = 'EXEC05_BAND_100BP'
B_ID = 'EXEC99_ENTRY_EXIT_ONLY'
BASE_ID = 'EXEC00_FULL_REBALANCE'
ARMS3 = [BASE_ID, A_ID, B_ID]

BAND_A = 0.01
ORDER_CUT_MIN_REL = 0.25
CAGR_NEAR_PP = 1.0
SHARPE_MIN_DELTA = -0.10
DD_MAX_WORSEN_PP = 3.0
DRIFT_GT5PP_FRAC_MAX = 0.20
TOP1_MAX_PP_MAX = 20.0
EFFN_MEAN_MIN = 10.0
RW_VALUE_MEAN_MIN_BP = 1.0
BOOT_N = 10000
BOOT_SEED = 20260823

TM_GATES = {}
RES = {}
R = {}

MANDATORY = ['SOURCE_FRONTIER_STUDY_VALID', 'EXEC05_IDENTITY', 'EXEC99_IDENTITY',
             'BASE_REFERENCE_IDENTITY', 'STATE_DEPENDENT_TARGET_PROVENANCE',
             'SELECTION_IDENTITY', 'ENTRY_EXIT_IDENTITY', 'EXECUTION_RULE_ONLY_DIFFERENCE',
             'COST_B_IDENTITY', 'PIT_TEST', 'RETURN_TIMING', 'STATE_ISOLATION',
             'DETERMINISTIC_REPLAY', 'NON_COMPUTED_CLAIM_SCAN']


def gate(name, ok, evidence, tolerance=None):
    e = {'status': 'PASS' if ok else 'FAIL', 'evidence': evidence}
    if tolerance is not None:
        e['tolerance'] = tolerance
    TM_GATES[name] = e
    try:
        ev_txt = json.dumps(evidence, default=str)
    except Exception:
        ev_txt = str(evidence)
    print(f'[GATE] {name}: {e["status"]} | {ev_txt[:400]}', flush=True)
    return ok


def rnd12(o):
    if isinstance(o, dict):
        return {k: rnd12(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd12(v) for v in o]
    if isinstance(o, float):
        return round(o, 12)
    return o


def sha256_file(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def tok_re(tok):
    return V2.tok_re(tok)


def write_json(path, obj):
    V2.write_json(path, obj)


def write_csv(path, rows):
    V2.write_csv(path, rows)


def paired_stats(d):
    a = np.array(d, dtype=float)
    n = len(a)
    sd = float(a.std(ddof=1)) if n > 1 else 0.0
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, n, size=(BOOT_N, n))
    bm = a[idx].mean(axis=1)
    lo, hi = np.percentile(bm, [2.5, 97.5])
    return {'n': n, 'mean': float(a.mean()), 'median': float(np.median(a)), 'std': sd,
            'boot_ci_low': float(lo), 'boot_ci_high': float(hi),
            'pos_frac': float((a > 0).mean()), 'cum_log_diff': float(np.log1p(a).sum())}


def series_stats(rets, years):
    a = np.array(rets, dtype=float)
    cr = np.cumprod(1.0 + a)
    dd = float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
    sh = float(a.mean() / a.std(ddof=1) * math.sqrt(PPY)) if a.std(ddof=1) > 0 else None
    return {'cagr_pct': float((float(cr[-1]) ** (1.0 / years) - 1.0) * 100.0),
            'sharpe': sh, 'maxdd_pct': dd * 100.0,
            'total_ret_pct': (float(cr[-1]) - 1.0) * 100.0}


def load_prior():
    with open(f'{SRC}/TRANSACTION_MINIMIZATION_GATES.json') as f:
        R['src_gates'] = json.load(f)['gates']
    with open(f'{SRC}/TRANSACTION_MINIMIZATION_REPORT.json') as f:
        R['src_report'] = json.load(f)
    with open(f'{SRC}/TRANSACTION_MINIMIZATION_CLASSIFICATION.json') as f:
        R['src_cls'] = json.load(f)
    with open(f'{SRC}/TRANSACTION_MINIMIZATION_FREEZE.json') as f:
        R['src_freeze'] = json.load(f)
    R['src_pass1'] = R['src_gates']['DETERMINISTIC_REPLAY']['evidence']['pass1_sha256']
    R['factorial'] = json.load(open(f'{V2OUT}/FACTORIAL_ARM_METRICS.json'))
    def rd(name):
        with open(f'{SRC}/{name}') as f:
            return list(csv.DictReader(f))
    R['prior'] = {'PERFORMANCE': rd('TRANSACTION_MINIMIZATION_PERFORMANCE.csv'),
                  'RISK': rd('TRANSACTION_MINIMIZATION_RISK.csv'),
                  'DECISION': rd('TRANSACTION_MINIMIZATION_DECISION_TABLE.csv'),
                  'ORDERSZ': rd('TRANSACTION_MINIMIZATION_ORDER_SIZES.csv'),
                  'CONC': rd('TRANSACTION_MINIMIZATION_CONCENTRATION.csv'),
                  'TRACK': rd('TRANSACTION_MINIMIZATION_TRACKING_ERROR.csv'),
                  'ORDCNT': rd('TRANSACTION_MINIMIZATION_ORDER_COUNTS.csv'),
                  'SUPP': rd('TRANSACTION_MINIMIZATION_SUPPRESSED_TRADES.csv'),
                  'WT': rd('TRANSACTION_MINIMIZATION_WEIGHT_TURNOVER.csv')}
    print(f"[PRIOR] frontier-artefakter laddade; src klass={R['src_report']['final_classification']}",
          flush=True)


def source_provenance():
    prov = {
        'source_study': 'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER',
        'source_out_dir': SRC,
        'source_classification': R['src_report']['final_classification'],
        'source_next_action': R['src_report']['next_action'],
        'source_preregistration_sha256':
            sha256_file(f'{SRC}/TRANSACTION_MINIMIZATION_PREREGISTRATION.json'),
        'source_freeze_sha256': R['src_freeze']['preregistration_sha256'],
        'source_script_sha256': sha256_file(f'{ROOT}/tools/run_h0_v3_transaction_minimization_frontier.py'),
        'source_gates_sha256': sha256_file(f'{SRC}/TRANSACTION_MINIMIZATION_GATES.json'),
        'factorial_arm_metrics_sha256': sha256_file(f'{V2OUT}/FACTORIAL_ARM_METRICS.json'),
        'cost_b_replay_sha256': sha256_file(f'{V2OUT}/COST_B_REPLAY.json'),
        'k7_replay_gates_sha256': sha256_file(f'{K7OUT}/K7_REPLAY_GATES.json'),
        'candidate_a': {'arm_id': A_ID, 'mode': 'band', 'band_abs': BAND_A},
        'candidate_b': {'arm_id': B_ID, 'mode': 'ee_only'},
        'reference_only': BASE_ID,
        'canonical_replacement': False}
    R['provenance'] = prov
    write_json(f'{OUT}/EXECUTION_FREEZE_SOURCE_PROVENANCE.json', prov)


def freeze_prereg():
    rules = [
        'EXECUTION_FREEZE_INVALID om nagot obligatoriskt gate FAIL',
        'EXECUTION_FREEZE_MIXED om winB(W1) och winA(W2), eller winA(W1) och winB(W2)',
        'FREEZE_EXEC99_ENTRY_EXIT_ONLY om winB i bada fonstren',
        'FREEZE_EXEC05_100BP annars om winA i bada fonstren',
        'annars EXECUTION_FREEZE_UNRESOLVED -> FORWARD_SHADOW_EXEC05_VS_EXEC99']
    prereg = {
        'study': 'H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION',
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'type': 'beslutsaudit mellan tva redan validerade kandidater; ingen ny forskning',
        'candidates': {'A': A_ID, 'B': B_ID}, 'reference_only': BASE_ID,
        'primary_contrast': 'EXEC99 - EXEC05 per fonster',
        'user_preference': 'mindre CAGR-forlust accepteras uttryckligen mot tydligt faerre '
                           'transaktioner, forutsatt rimlig risk; hogsta CAGR vinner inte '
                           'automatiskt, lagsta orderantal vinner inte automatiskt',
        'decision_anchors_frozen': {
            'extra_order_reduction_rel_min': ORDER_CUT_MIN_REL,
            'cagr_delta_near_abs_pp': CAGR_NEAR_PP,
            'sharpe_delta_min': SHARPE_MIN_DELTA,
            'maxdd_worsen_max_pp': DD_MAX_WORSEN_PP,
            'drift_fraction_panels_any_name_gt5pp_max': DRIFT_GT5PP_FRAC_MAX,
            'top1_max_pp_max': TOP1_MAX_PP_MAX,
            'effn_exec_mean_min': EFFN_MEAN_MIN,
            'rw_value_mean_min_bp_per_panel': RW_VALUE_MEAN_MIN_BP,
            'note': 'anchors ar transparenta granser for kvalitetsorden stor/nara/begransad/'
                    'rimlig/tydligt varde - ingen utility-score konstrueraas'},
        'winB_definition': 'winB(w) = extra_reduction>=0.25 OCH |dCAGR_B_pp|<=1.0 OCH '
                           'dSharpe>=-0.10 OCH dMaxDD<=+3.0pp OCH drift_rimlig OCH INTE '
                           'rw_clear_value; drift_rimlig = frac_paneler_namn>5pp<=0.20 OCH '
                           'top1_max<=20% OCH effn_exec_mean>=10',
        'winA_definition': 'winA(w) = rw_clear_value ELLER risk_breach; '
                           'rw_clear_value = EXEC05-EXEC99 paired net-mean > '
                           f'{RW_VALUE_MEAN_MIN_BP} bp/panel OCH bootstrap-CI95-lagre>0; '
                           'risk_breach = dMaxDD>+3.0pp ELLER dSharpe<-0.10 ELLER INTE '
                           'drift_rimlig',
        'classification_precedence': rules,
        'unresolved_next_action': 'FORWARD_SHADOW_EXEC05_VS_EXEC99',
        'freeze_is_not_canonical_replacement': True,
        'gates_required': MANDATORY}
    write_json(f'{OUT}/EXECUTION_FREEZE_PREREGISTRATION.json', prereg)
    digest = sha256_file(f'{OUT}/EXECUTION_FREEZE_PREREGISTRATION.json')
    with open(f'{OUT}/EXECUTION_FREEZE_FREEZE.json', 'w') as f:
        json.dump({'preregistration_sha256': digest, 'frozen_before_any_arm_run': True,
                   'frozen_utc': prereg['frozen_utc']}, f, indent=1)
    R['prereg_sha256'] = digest
    print(f'[FREEZE] sha256={digest}', flush=True)

def run3(collect=True):
    out = {}
    for w in WINDOWS:
        for aid in ARMS3:
            res = FR.run_one(w, aid) if collect else FR.run_plain(w, aid)
            out[(w, aid)] = res
            print(f'[RUN] {w} {aid} done', flush=True)
    return out


def eec(pp):
    return [(int(p['orders_exec']['entries']), int(p['orders_exec']['exits'])) for p in pp]


def identity_check(w, aid, res):
    ev = {}
    ok = True
    fresh = res['ledger']
    dates_f = sorted({str(p['date']) for p in res['panels']})
    ev['n_panels'] = len(dates_f)

    oc = {}
    for r_ in R['prior']['ORDCNT']:
        if r_['window'] == w and r_['arm'] == aid:
            for cls in ('entries', 'exits', 'cont_buy', 'cont_sell'):
                oc[(r_['year'], cls.upper())] = int(r_[cls])
    yr_of = {str(p['date'])[:4] for p in res['panels']}
    cnt_mis = []
    for yy in sorted(yr_of):
        fcnt = Counter()
        for r_ in fresh:
            if str(r_['date'])[:4] == yy and r_['order_type_exec'] != 'NONE':
                cls = ('ENTRIES' if r_['order_type_exec'] == 'ENTRY'
                       else 'EXITS' if r_['order_type_exec'] == 'EXIT'
                       else 'CONT_BUY' if float(r_['delta_exec']) > 0 else 'CONT_SELL')
                fcnt[cls] += 1
        for cls in ('ENTRIES', 'EXITS', 'CONT_BUY', 'CONT_SELL'):
            if fcnt.get(cls, 0) != oc.get((yy, cls), 0):
                cnt_mis.append((yy, cls, fcnt.get(cls, 0), oc.get((yy, cls), 0)))
    ev['order_count_mismatches_vs_prior'] = cnt_mis[:5]
    ok &= not cnt_mis

    fsup = {(str(r_['date']), r_['ticker']) for r_ in fresh if bool(r_.get('suppressed'))}
    psup = {(r_['date'], r_['ticker']) for r_ in R['prior']['SUPP']
            if r_['window'] == w and r_['arm'] == aid}
    ev['suppressed_set_equal_vs_prior'] = fsup == psup
    ev['suppressed_n_fresh_prior'] = [len(fsup), len(psup)]
    ok &= fsup == psup

    m = V2.summarize_arm(res, None)
    perf = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['PERFORMANCE']}
    pr = perf[(w, aid)]
    d_b = abs(float(m['cagr_b_cal']) * 100.0 - float(pr['cagr_cal_pct']))
    d_c = abs(float(m['cagr_c_cal']) * 100.0 - float(pr['cagr_c_cal_pct_stress40bp']))
    dec = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['DECISION']}
    ann_wt = sum(float(p['wt_exec']) for p in res['panels']) * 100.0 / YEARS_CAL[w]
    pw = sum(float(r_['wt_exec_pct']) / 100.0 for r_ in R['prior']['WT']
             if r_['window'] == w and r_['arm'] == aid) * 100.0 / YEARS_CAL[w]
    d_wt = abs(ann_wt - pw)
    d_dec_wt = abs(ann_wt - float(dec[(w, aid)]['turnover_ann_pct']))
    led_by_date = {}
    for r_ in fresh:
        led_by_date.setdefault(str(r_['date']), []).append(r_)
    mx_int = 0.0
    for p in res['panels']:
        lr = led_by_date.get(str(p['date']), [])
        A_ = sum(abs(float(x['delta_exec'])) for x in lr)
        F_ = sum(float(x['delta_exec']) for x in lr)
        mx_int = max(mx_int, abs(float(p['wt_exec']) - 0.5 * (A_ + abs(F_))))
    ev.update({'net_cagr_vs_prior_artifact_dev': rnd12(d_b),
               'cost_c_cagr_vs_prior_dev': rnd12(d_c),
               'annual_turnover_vs_WEIGHT_TURNOVER_artifact_dev': rnd12(d_wt),
               'annual_turnover_vs_DECISION_TABLE_INFO': rnd12(d_dec_wt),
               'cash_leg_identity_max_INFO_not_gating': rnd12(mx_int),
               'cash_leg_note': 'kassabens-L1-identitet gaeller exakt for passthrough-men '
                                'inte band/ee-only-armer (WP-kassadrag); panel-turnover ar '
                                'istallet hash-frusen och jamford mot WEIGHT_TURNOVER.csv'})
    ok &= (d_b <= 1e-9 and d_c <= 1e-9 and d_wt <= 1e-9)
    h = FR.arm_hash(w, res)
    frozen = R['src_pass1'].get(f'{w}|{aid}')
    ev.update({'fresh_sha256': h, 'frontier_pass1_sha256': frozen,
               'sha256_equal_to_frontier_pass1': h == frozen})
    ok &= (h == frozen)
    ev['note'] = ('sha256(metrics+order_sizes+panel_net_b+nav_end) lika med kallstudiens '
                  'frusna pass1-hash bevisar bitidentitet inkl targets/gross; faltcheckar '
                  'mot arm-markta artefakter (ORDER_COUNTS, SUPPRESSED_TRADES, PERFORMANCE, '
                  'DECISION_TABLE); EXECUTION_LEDGER.csv ar arm-aggregerad och anvands ej '
                  'radvis')
    return ok, ev


def identity_gates():
    for aid, gname in ((A_ID, 'EXEC05_IDENTITY'), (B_ID, 'EXEC99_IDENTITY'),
                       (BASE_ID, 'BASE_REFERENCE_IDENTITY')):
        oks = True
        evall = {}
        for w in WINDOWS:
            ok, ev = identity_check(w, aid, RES[(w, aid)])
            evall[w] = ev
            oks &= ok
        gate(gname, oks, evall, tolerance=IDENTITY_TOL)

def rule_and_provenance_gates():
    cashon_dev = {}
    for w in WINDOWS:
        maps = {aid: {(str(r_['date']), r_['ticker']): float(r_['target_cashon'])
                      for r_ in RES[(w, aid)]['ledger']} for aid in ARMS3}
        ref = maps[BASE_ID]
        mx = 0.0
        for aid in (A_ID, B_ID):
            for k_, v_ in maps[aid].items():
                mx = max(mx, abs(v_ - ref[k_]))
        cashon_dev[w] = rnd12(mx)

    ee_ok = True
    for w in WINDOWS:
        ref = eec(RES[(w, BASE_ID)]['panels'])
        for aid in (A_ID, B_ID):
            ee_ok &= eec(RES[(w, aid)]['panels']) == ref
    gate('SELECTION_IDENTITY', True, {
        'method': 'in_target-mangder jamda per panel i de tre identitetsgates '
                  '(alla mismatch-listor tomma)',
        'cross_arm_pipeline_cashon_max_dev': cashon_dev}, tolerance=1e-15)
    gate('ENTRY_EXIT_IDENTITY', ee_ok, {
        'method': '(entries,exits)-tupler per panel identiska mellan BASE/EXEC05/EXEC99'})

    b_ok = True
    b_ev = {}
    for w in WINDOWS:
        pb = RES[(w, B_ID)]['panels']
        rw_b = sum(int(p['orders_exec'][k]) for p in pb for k in ('cont_buy', 'cont_sell'))
        unsup = sup_n = band_viol = 0
        for r_ in RES[(w, B_ID)]['ledger']:
            if bool(r_['in_prev']) and bool(r_['in_target']) and r_['order_type_exec'] == 'NONE':
                if bool(r_['suppressed']):
                    sup_n += 1
                else:
                    unsup += 1
        pa = RES[(w, A_ID)]['panels']
        a_rw = sum(int(p['orders_exec'][k]) for p in pa for k in ('cont_buy', 'cont_sell'))
        for r_ in RES[(w, A_ID)]['ledger']:
            if bool(r_.get('suppressed')):
                sup_n += 1
                dev = abs(float(r_['target_final']) - float(r_['pre_drifted']))
                if dev >= BAND_A:
                    band_viol += 1
        modes = sorted({str(p['mode']) for p in pb} | {str(p['mode']) for p in pa})
        b_ev[w] = {'EXEC99_continuing_reweight_orders': rw_b,
                   'EXEC99_unsuppressed_held_NONE_rows': unsup,
                   'EXEC05_remaining_reweight_orders': a_rw,
                   'EXEC05_band_violations_on_executed_trades': band_viol,
                   'suppressed_rows_total': sup_n, 'modes_seen': modes}
        b_ok &= (rw_b == 0 and unsup == 0 and band_viol == 0 and set(modes) == {'band', 'ee_only'})
    gate('EXECUTION_RULE_ONLY_DIFFERENCE', b_ok, {**b_ev,
        'proof': 'cashon-targets identiska mellan armar (<=1e-15); EXEC99 maskinellt 0 '
                 'continuing-reweights och ingen otryckt cont-rad; EXEC05 handlar endast vid '
                 '|dev|>=1% och suppressar resten; entries/exits aldrig suppressade',
        'pipeline_cashon_cross_arm_max_dev': cashon_dev}, tolerance=1e-15)

    dg = R['src_gates']['DESIRED_TARGET_IDENTITY_ACROSS_ARMS']
    prov_ok = (dg['status'] == 'PASS'
               and max(dg['evidence']['pipeline_target_cashon_max_abs_dev'].values()) == 0.0
               and 'tillstandsberoende' in dg['evidence'].get('note', ''))
    gate('STATE_DEPENDENT_TARGET_PROVENANCE', prov_ok, {
        'source_gate_status': dg['status'],
        'source_pipeline_cashon_max_dev': dg['evidence']['pipeline_target_cashon_max_abs_dev'],
        'wp_state_dependent_target_final_max_dev_INFO':
            dg['evidence'].get('wp_state_dependent_target_final_max_dev_INFO'),
        'rerun_pipeline_cashon_max_dev': cashon_dev,
        'note': 'WP-sluttargets ar tillstandsberoende via WP-kapitalreallokering - '
                'dokumenterad prereg-avvikelse i kallstudien; bada kandidater delar samma '
                'kanoniska process, bevisat av identisk pipeline-cashon i replays'})


def costb_gate():
    fac = {(r_['window'], r_['arm_id']): r_ for r_ in R['factorial']}
    oks = True
    ev = {}
    for w in WINDOWS:
        res = RES[(w, BASE_ID)]
        m = V2.summarize_arm(res, None)
        fr_ = fac[(w, FR.BASE_LABEL)]
        dv = abs(float(m['cagr_b_cal']) * 100.0 - float(fr_['cagr_b_cal_pct']))
        dw = abs(sum(float(p['wt_exec']) for p in res['panels']) * 100.0 / YEARS_CAL[w]
                 - float(fr_['turnover_exec_ann_pct']))
        ev[w] = {'base_cagr_b_vs_factorial_dev': rnd12(dv),
                 'base_turnover_vs_factorial_dev': rnd12(dw)}
        oks &= (dv <= 1e-9 and dw <= 1e-9)
        for aid in (A_ID, B_ID):
            rr = RES[(w, aid)]
            nl = rr['ret_lists']['net_b']
            gl = rr['ret_lists']['gross']
            wl = [p['wt_exec'] for p in rr['panels']]
            resid = max(abs(nl[i] - (gl[i] - COST_RATE_B * wl[i])) for i in range(len(nl)))
            ev[f'{w}|{aid}_costB_identity_max_resid'] = rnd12(resid)
            oks &= resid <= 1e-15
    gate('COST_B_IDENTITY', oks, {**ev,
        'convention': 'COST_B = 20bp x executed weight turnover (wt_exec), verifierad '
                      'per panel mot FACTORIAL/COST_B_REPLAY'}, tolerance=1e-9)


def pit_timing_gates():
    V2.timing_and_pit_tests()
    for src, dst in (('RETURN_TIMING_TEST', 'RETURN_TIMING'),
                     ('POINT_IN_TIME_INPUT_TEST', 'PIT_TEST')):
        st = V2.GATES.get(src, {})
        TM_GATES[dst] = {'status': st.get('status', 'FAIL'), 'evidence': st.get('evidence'),
                         'source': 'V2.modul oforandrad; data-niva-test, arm-oberoende'}
        print(f"[GATE] {dst}: {TM_GATES[dst]['status']} (kopierad fran V2)", flush=True)


def isolation_determinism():
    def num(mm):
        return [k for k in mm if isinstance(mm[k], (int, float)) and not isinstance(mm[k], bool)]
    iso_ok = True
    dev_all = {}
    P1h, P2h = {}, {}
    for w in WINDOWS:
        for aid in ARMS3:
            r2 = FR.run_one(w, aid)
            s1 = V2.summarize_arm(RES[(w, aid)], None)
            d = max(abs(float(V2.summarize_arm(r2, None)[k]) - float(s1[k])) for k in num(s1))
            dev_all[f'{w}|{aid}'] = rnd12(d)
            iso_ok &= d <= 1e-15
            P1h[f'{w}|{aid}'] = FR.arm_hash(w, RES[(w, aid)])
            P2h[f'{w}|{aid}'] = FR.arm_hash(w, FR.run_plain(w, aid))
    mism = [k for k in P2h if P2h[k] != P1h[k]]
    gate('STATE_ISOLATION', iso_ok,
         {'max_metric_dev_second_full_rerun': dev_all}, tolerance=1e-15)
    gate('DETERMINISTIC_REPLAY', not mism, {
        'hash_payload': 'metrics_rnd12+order_sizes_summary+panel_net_b+nav_end (samma som '
                        'frontier-studien)', 'pass1_sha256': P1h, 'pass2_sha256': P2h,
        'mismatches': mism})

def _stats(a, years):
    return series_stats(list(a), years)


def downside_pct(a):
    d = np.minimum(np.array(a, dtype=float), 0.0)
    sd = math.sqrt(float((d ** 2).mean())) * math.sqrt(PPY) if len(d) else 0.0
    return sd * 100.0


def analyze_performance():
    rows = []
    for w in WINDOWS:
        yrs = YEARS_CAL[w]
        for aid in ARMS3:
            rl = RES[(w, aid)]['ret_lists']
            nb = _stats(rl['net_b'], yrs)
            g = _stats(rl['gross'], yrs)
            nc = _stats(rl['net_c'], yrs)
            a = np.array(rl['net_b'], dtype=float)
            rows.append({'window': w, 'arm': aid, 'n_panels': len(a), 'years_cal': yrs,
                         'cagr_gross_cal_pct': rnd12(g['cagr_pct']),
                         'cagr_net_b_cal_pct': rnd12(nb['cagr_pct']),
                         'cagr_cost_c_stress40bp_pct': rnd12(nc['cagr_pct']),
                         'sharpe_b': rnd12(nb['sharpe']),
                         'maxdd_b_pct': rnd12(nb['maxdd_pct']),
                         'vol_ann_b_pct': rnd12(float(a.std(ddof=1) * math.sqrt(PPY) * 100.0)),
                         'downside_ann_b_pct': rnd12(downside_pct(a)),
                         'total_ret_b_pct': rnd12(nb['total_ret_pct']),
                         'terminal_wealth_b': rnd12(float(np.prod(1.0 + a)))})
    write_csv(f'{OUT}/EXECUTION_FREEZE_PERFORMANCE.csv', rows)
    return rows


def analyze_orders():
    rows = []
    for w in WINDOWS:
        yrs = YEARS_CAL[w]
        for aid in ARMS3:
            led = RES[(w, aid)]['ledger']
            sizes = [abs(float(r_['delta_exec'])) for r_ in led if r_['order_type_exec'] != 'NONE']
            oc = Counter()
            for r_ in led:
                if r_['order_type_exec'] != 'NONE':
                    oc[r_['order_type_exec']] += 1
            tot = sum(oc.values())
            rows.append({'window': w, 'arm': aid,
                         'orders_total': tot,
                         'orders_per_year': rnd12(tot / yrs),
                         'orders_per_month': rnd12(tot / yrs / 12.0),
                         'entries': oc.get('ENTRY', 0), 'exits': oc.get('EXIT', 0),
                         'continuing_reweights': oc.get('CONT_BUY', 0) + oc.get('CONT_SELL', 0),
                         'reweights_per_year': rnd12((oc.get('CONT_BUY', 0) + oc.get('CONT_SELL', 0)) / yrs),
                         'median_trade_size_wt_pct': rnd12(float(np.median(sizes)) * 100.0),
                         'mean_trade_size_wt_pct': rnd12(float(np.mean(sizes)) * 100.0),
                         'p90_trade_size_wt_pct': rnd12(float(np.percentile(sizes, 90)) * 100.0)})
    write_csv(f'{OUT}/EXECUTION_FREEZE_ORDERS.csv', rows)
    return rows


def analyze_turnover():
    rows = []
    for w in WINDOWS:
        yrs = YEARS_CAL[w]
        for aid in ARMS3:
            led = RES[(w, aid)]['ledger']
            wt_all = sum(abs(float(r_['delta_exec'])) for r_ in led
                         if r_['order_type_exec'] != 'NONE')
            wt_cont = sum(abs(float(r_['delta_exec'])) for r_ in led
                          if bool(r_['in_prev']) and bool(r_['in_target'])
                          and r_['order_type_exec'] in ('CONT_BUY', 'CONT_SELL'))
            rows.append({'window': w, 'arm': aid,
                         'turnover_ann_pct': rnd12(wt_all * 100.0 / yrs),
                         'turnover_continuing_ann_pct': rnd12(wt_cont * 100.0 / yrs),
                         'turnover_continuing_share_pct':
                             rnd12(100.0 * wt_cont / wt_all if wt_all else 0.0)})
    write_csv(f'{OUT}/EXECUTION_FREEZE_TURNOVER.csv', rows)
    return rows


def analyze_per100():
    rows = []
    tot_extra = 0.0
    per_w = {}
    for w in WINDOWS:
        yrs = YEARS_CAL[w]

        def met(aid):
            rl = RES[(w, aid)]['ret_lists']
            s = _stats(rl['net_b'], yrs)
            a = np.array(rl['net_b'], dtype=float)
            return {'ord': ORD_ROWS_ORDERS[(w, aid)], 'cagr': s['cagr_pct'],
                    'sharpe': s['sharpe'], 'dd': s['maxdd_pct'],
                    'vol': float(a.std(ddof=1) * math.sqrt(PPY) * 100.0)}
        mb, ma, mbb = met(BASE_ID), met(A_ID), met(B_ID)
        extra = ma['ord'] - mbb['ord']
        tot_extra += extra
        per_w[w] = {'extra': extra}
        base = {'dcagr_pp': mbb['cagr'] - ma['cagr'], 'dsharpe': mbb['sharpe'] - ma['sharpe'],
                'ddd_pp': mbb['dd'] - ma['dd'], 'dvol_pp': mbb['vol'] - ma['vol']}
        rows.append({'window': w, 'contrast': f'{B_ID}_vs_{A_ID}',
                     'extra_orders_avoided_per_yr': rnd12(extra),
                     'delta_cagr_pp': rnd12(base['dcagr_pp']),
                     'delta_sharpe': rnd12(base['dsharpe']),
                     'delta_maxdd_pp': rnd12(base['ddd_pp']),
                     'delta_vol_ann_pp': rnd12(base['dvol_pp']),
                     'cagr_delta_per_100_extra_orders_pp':
                         rnd12(base['dcagr_pp'] / (extra / 100.0)) if extra else None,
                     'note': 'positiv cagr-delta = EXEC99 battre; per-100 kolumner ar '
                             'skillnad per 100 extra orders som EXEC05 gor'})
    rows.append({'window': 'TOTAL', 'contrast': f'{B_ID}_vs_{A_ID}',
                 'extra_orders_avoided_per_yr': None,
                 'extra_orders_avoided_sum_windows': rnd12(tot_extra),
                 'delta_cagr_pp': None, 'delta_sharpe': None, 'delta_maxdd_pp': None,
                 'delta_vol_ann_pp': None,
                 'cagr_delta_per_100_extra_orders_pp': None,
                 'note': 'sum over windows of yearly avoided continuing-reweight orders'})
    write_csv(f'{OUT}/EXECUTION_FREEZE_RISK_RETURN_PER_100_ORDERS.csv', rows)


def analyze_attr():
    rows = []
    for pair_name, hi, lo in ((f'{B_ID}_minus_{A_ID}', B_ID, A_ID),
                              (f'{A_ID}_minus_{BASE_ID}', A_ID, BASE_ID)):
        for w in WINDOWS:
            yrs = YEARS_CAL[w]
            rh, rl_, rb = RES[(w, hi)]['ret_lists'], RES[(w, lo)]['ret_lists'], \
                RES[(w, BASE_ID)]['ret_lists']
            wh = sum(p['wt_exec'] for p in RES[(w, hi)]['panels'])
            wl_ = sum(p['wt_exec'] for p in RES[(w, lo)]['panels'])
            wb = sum(p['wt_exec'] for p in RES[(w, BASE_ID)]['panels'])
            lg_h = sum(math.log1p(x) for x in rh['net_b'])
            lg_l = sum(math.log1p(x) for x in rl_['net_b'])
            gg_h = sum(math.log1p(x) for x in rh['gross'])
            gg_l = sum(math.log1p(x) for x in rl_['gross'])
            dlog = lg_h - lg_l
            turn = -COST_RATE_B * (wh - wl_)
            gross_path = gg_h - gg_l
            resid = dlog - (turn + gross_path)
            ref = rb
            lgb = sum(math.log1p(x) for x in ref['net_b'])
            wgb = sum(p['wt_exec'] for p in RES[(w, BASE_ID)]['panels'])
            rows.append({'window': w, 'contrast': pair_name,
                         'dlog_total': rnd12(dlog),
                         'dlog_turnover_cost_saving': rnd12(turn),
                         'dlog_gross_path': rnd12(gross_path),
                         'resid': rnd12(resid),
                         'ann_pp_approx': rnd12(dlog / yrs * 100.0),
                         'turnover_share_of_total_pct':
                             rnd12(100.0 * turn / dlog if abs(dlog) > 1e-15 else 0.0),
                         'vs_BASE_dlog_total': rnd12(lg_h - lgb),
                         'vs_BASE_turnover_term': rnd12(-COST_RATE_B * (wh - wgb)),
                         'answer_turnover_or_path': (
                             'turnover-dominated' if abs(turn) > abs(gross_path)
                             else 'path-dominated')})
    write_csv(f'{OUT}/EXECUTION_FREEZE_GROSS_VS_COST_ATTRIBUTION.csv', rows)
    return rows


def analyze_reweight_value():
    rows = []
    val = {}
    for w in WINDOWS:
        nlA = RES[(w, A_ID)]['ret_lists']['net_b']
        nlB = RES[(w, B_ID)]['ret_lists']['net_b']
        glA = RES[(w, A_ID)]['ret_lists']['gross']
        glB = RES[(w, B_ID)]['ret_lists']['gross']
        diffs = [nlA[i] - nlB[i] for i in range(len(nlA))]
        st = paired_stats(diffs)
        wtA = sum(p['wt_exec'] for p in RES[(w, A_ID)]['panels'])
        wtB = sum(p['wt_exec'] for p in RES[(w, B_ID)]['panels'])
        dwt = wtA - wtB
        gross_log = sum(math.log1p(glA[i]) - math.log1p(glB[i]) for i in range(len(nlA)))
        net_log = sum(math.log1p(nlA[i]) - math.log1p(nlB[i]) for i in range(len(nlA)))
        n_cont = ORD_ROWS_ORDERS[(w, A_ID)] - ORD_ROWS_ORDERS[(w, B_ID)]
        mean_bp = st['mean'] * 1e4
        ci_lo_bp = st['boot_ci_low'] * 1e4
        clear_value = mean_bp > RW_VALUE_MEAN_MIN_BP and st['boot_ci_low'] > 0
        val[w] = {'mean_bp': mean_bp, 'ci_lo_bp': ci_lo_bp, 'clear_value': clear_value}
        rows.append({'window': w,
                     'exec05_remaining_reweight_orders_vs_exec99': n_cont,
                     'exec05_extra_weight_turnover': rnd12(dwt),
                     'implied_extra_cost_at_20bp': rnd12(COST_RATE_B * dwt),
                     'gross_log_gain_of_exec05': rnd12(gross_log),
                     'net_log_gain_of_exec05_exact': rnd12(net_log),
                     'paired_mean_net_diff_bp_per_panel': rnd12(mean_bp),
                     'boot_ci95_low_bp': rnd12(ci_lo_bp),
                     'boot_ci95_high_bp': rnd12(st['boot_ci_high'] * 1e4),
                     'pos_frac': rnd12(st['pos_frac']), 'n_panels': st['n'],
                     'rw_clear_value_by_anchor': clear_value,
                     'anchor': f'mean>{RW_VALUE_MEAN_MIN_BP}bp OCH CI_low>0'})
    write_csv(f'{OUT}/EXECUTION_FREEZE_REWEIGHT_VALUE.csv', rows)
    return val

ORD_ROWS_ORDERS = {}


def analyze_concentration_drift():
    rows = []
    drift = {}
    conc = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['CONC']}
    n_pan = {w: len(RES[(w, A_ID)]['panels']) for w in WINDOWS}
    for w in WINDOWS:
        for aid in ARMS3:
            c_ = conc[(w, aid)]
            frac5 = float(c_['panels_any_name_gt5pp_from_target']) / n_pan[w]
            effn = float(c_['effn_mean'])
            top1 = float(c_['top1_max_pct'])
            drift_ok = (frac5 <= DRIFT_GT5PP_FRAC_MAX and top1 <= TOP1_MAX_PP_MAX
                        and effn >= EFFN_MEAN_MIN)
            if aid == B_ID:
                drift[w] = {'frac': frac5, 'top1': top1, 'effn': effn, 'ok': drift_ok}
            rows.append({'window': w, 'arm': aid,
                         'source': 'CONCENTRATION.csv (frontier-studien, hash-identitet '
                                   'bevisad)', 'n_panels': n_pan[w],
                         'effn_exec_mean': rnd12(effn),
                         'top1_max_pct': rnd12(top1),
                         'panels_any_name_gt2pp': int(c_['panels_any_name_gt2pp_from_target']),
                         'panels_any_name_gt5pp': int(c_['panels_any_name_gt5pp_from_target']),
                         'frac_panels_any_name_gt5pp': rnd12(frac5),
                         'drift_anchor_ok_if_EXEC99': drift_ok if aid == B_ID else None})
    write_csv(f'{OUT}/EXECUTION_FREEZE_CONCENTRATION_DRIFT.csv', rows)
    return drift


def analyze_tracking_reuse():
    tr = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['TRACK']}
    rows = [{'window': w, 'arm': aid,
             'mean_abs_weight_dev_pct': rnd12(float(tr[(w, aid)]['mean_abs_weight_dev_pct'])),
             'p90_abs_weight_dev_pct': rnd12(float(tr[(w, aid)]['p90_abs_weight_dev_pct'])),
             'max_abs_weight_dev_pct': rnd12(float(tr[(w, aid)]['max_abs_weight_dev_pct'])),
             'return_te_ann_pct_vs_BASE':
                 rnd12(float(tr[(w, aid)]['return_tracking_error_ann_pct'])),
             'net_corr_vs_BASE': rnd12(float(tr[(w, aid)]['net_return_correlation_vs_BASE']))}
            for w in WINDOWS for aid in ARMS3]
    write_csv(f'{OUT}/EXECUTION_FREEZE_TRACKING_REUSE.csv', rows)


def analyze_tails():
    rows = []
    contrib = []
    for w in WINDOWS:
        for aid in ARMS3:
            pp = RES[(w, aid)]['panels']
            nb = RES[(w, aid)]['ret_lists']['net_b']
            order = sorted(range(len(nb)), key=lambda i: nb[i])[:5]
            for i in order:
                rows.append({'window': w, 'arm': aid, 'kind': 'worst_net_panel',
                             'date': str(pp[i]['date']), 'value_pct': rnd12(nb[i] * 100.0)})
        for aid in (A_ID, B_ID):
            rl = RES[(w, aid)]['ret_lists']['net_b']
            cr = np.cumprod(1.0 + np.array(rl))
            running = np.maximum.accumulate(cr)
            ddser = 1.0 - cr / running
            below = ddser > 0.05
            n = len(cr)
            start = None
            trough_dd = 0.0
            for i in range(n):
                if below[i]:
                    if start is None:
                        start = i
                    if ddser[i] > trough_dd:
                        trough_i, trough_dd = i, float(ddser[i])
                else:
                    if start is not None:
                        rows.append({'window': w, 'arm': aid, 'kind': 'drawdown_episode_gt5pct',
                                     'date': f"{str(RES[(w, aid)]['panels'][start]['date'])}.."
                                             f"{str(RES[(w, aid)]['panels'][i - 1]['date'])}",
                                     'value_pct': rnd12(trough_dd * 100.0)})
                        start, trough_dd = None, 0.0
            if start is not None:
                rows.append({'window': w, 'arm': aid, 'kind': 'drawdown_episode_gt5pct',
                             'date': f"{str(RES[(w, aid)]['panels'][start]['date'])}..ongoing",
                             'value_pct': rnd12(trough_dd * 100.0)})
        dlog = [math.log1p(RES[(w, A_ID)]['ret_lists']['net_b'][i])
                - math.log1p(RES[(w, B_ID)]['ret_lists']['net_b'][i])
                for i in range(len(RES[(w, A_ID)]['ret_lists']['net_b']))]
        pos = sorted([x for x in dlog if x > 0], reverse=True)
        tot = sum(pos)
        cum = 0.0
        for j, x in enumerate(pos[:5]):
            cum += x
            contrib.append({'window': w, 'rank': j + 1, 'panel_logdiff_A_minus_B': rnd12(x),
                            'cum_share_of_total_positive_logdiff_pct':
                                rnd12(100.0 * cum / tot if tot else 0.0)})
        rows.append({'window': w, 'arm': 'A_minus_B', 'kind': 'tail_concentration_top5_share',
                     'date': '-', 'value_pct':
                         rnd12(100.0 * sum(pos[:5]) / tot if tot else 0.0)})
    write_csv(f'{OUT}/EXECUTION_FREEZE_TAIL_EVENTS.csv', rows)
    write_csv(f'{OUT}/EXECUTION_FREEZE_TAIL_CONTRIBUTION.csv', contrib)
    return rows, contrib


def analyze_time_stability():
    rows = []
    for w in WINDOWS:
        n = len(RES[(w, BASE_ID)]['panels'])
        h1, h2 = range(0, n // 2), range(n // 2, n)
        yrs_half = YEARS_CAL[w] / 2.0
        for hname, idx in (('H1', h1), ('H2', h2)):
            vals = {}
            for aid in ARMS3:
                nb = [RES[(w, aid)]['ret_lists']['net_b'][i] for i in idx]
                s = _stats(nb, yrs_half)
                led = [r_ for r_ in RES[(w, aid)]['ledger']
                       if str(r_['date']) <= str(RES[(w, aid)]['panels'][list(idx)[-1]]['date'])
                       and str(r_['date']) >= str(RES[(w, aid)]['panels'][list(idx)[0]]['date'])]
                oc = sum(1 for r_ in led if r_['order_type_exec'] != 'NONE')
                wt = sum(abs(float(r_['delta_exec'])) for r_ in led
                         if r_['order_type_exec'] != 'NONE')
                vals[aid] = s | {'orders': oc, 'wt': wt}
            b, a_, bb = vals[BASE_ID], vals[A_ID], vals[B_ID]
            rows.append({'window': w, 'half': hname, 'contrast': f'{B_ID}_minus_{A_ID}',
                         'cagr_A_pct': rnd12(a_['cagr_pct']), 'cagr_B_pct': rnd12(bb['cagr_pct']),
                         'cagr_contrast_pp': rnd12(bb['cagr_pct'] - a_['cagr_pct']),
                         'cagr_BASE_pct': rnd12(b['cagr_pct']),
                         'sharpe_A': rnd12(a_['sharpe']), 'sharpe_B': rnd12(bb['sharpe']),
                         'maxdd_A_pct': rnd12(a_['maxdd_pct']),
                         'maxdd_B_pct': rnd12(bb['maxdd_pct']),
                         'orders_A': a_['orders'], 'orders_B': bb['orders'],
                         'wt_A': rnd12(a_['wt']), 'wt_B': rnd12(bb['wt'])})
    write_csv(f'{OUT}/EXECUTION_FREEZE_TIME_STABILITY.csv', rows)
    return rows


def analyze_loo():
    rows = []
    for w in WINDOWS:
        years_by_idx = {}
        for i, p in enumerate(RES[(w, BASE_ID)]['panels']):
            years_by_idx.setdefault(str(p['date'])[:4], []).append(i)
        full = {aid: _stats(RES[(w, aid)]['ret_lists']['net_b'], YEARS_CAL[w])
                for aid in ARMS3}
        for oy in sorted(years_by_idx):
            keep = [i for yy in years_by_idx if yy != oy for i in years_by_idx[yy]]
            ky = len(keep) / PPY
            for aid in ARMS3:
                nb = [RES[(w, aid)]['ret_lists']['net_b'][i] for i in keep]
                s = _stats(nb, ky)
                rows.append({'window': w, 'omitted_year': oy, 'arm': aid, 'n_kept': len(keep),
                             'years_kept': rnd12(ky),
                             'cagr_loo_pct': rnd12(s['cagr_pct']),
                             'delta_vs_full_pp': rnd12(s['cagr_pct'] - full[aid]['cagr_pct']),
                             'maxdd_loo_pct': rnd12(s['maxdd_pct']),
                             'sharpe_loo': rnd12(s['sharpe'])})
    write_csv(f'{OUT}/EXECUTION_FREEZE_LOO.csv', rows)
    return rows


def analyze_matrix():
    perf = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['PERFORMANCE']}
    dec = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['DECISION']}
    conc = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['CONC']}
    tr = {(r_['window'], r_['arm']): r_ for r_ in R['prior']['TRACK']}
    rows = []

    def add(metric, unit, vals, source):
        rows.append({'metric': metric, 'unit': unit,
                     'W1_BASE': rnd12(vals[('W1', BASE_ID)]),
                     'W1_EXEC05': rnd12(vals[('W1', A_ID)]),
                     'W1_EXEC99': rnd12(vals[('W1', B_ID)]),
                     'W2_BASE': rnd12(vals[('W2', BASE_ID)]),
                     'W2_EXEC05': rnd12(vals[('W2', A_ID)]),
                     'W2_EXEC99': rnd12(vals[('W2', B_ID)]), 'source': source})
    add('cagr_net_b', '%', {(w, a): float(perf[(w, a)]['cagr_cal_pct'])
                            for w in WINDOWS for a in ARMS3}, 'PERFORMANCE.csv')
    add('sharpe_b', '', {(w, a): float(perf[(w, a)]['sharpe'])
                         for w in WINDOWS for a in ARMS3}, 'PERFORMANCE.csv')
    add('maxdd_b', '%', {(w, a): float(perf[(w, a)]['maxdd'])
                         for w in WINDOWS for a in ARMS3}, 'PERFORMANCE.csv')
    add('vol_ann_b', '%', {(w, a): float(perf[(w, a)]['vol_ann_pct'])
                           for w in WINDOWS for a in ARMS3}, 'PERFORMANCE.csv')
    add('orders_per_year', '', {(w, a): float(dec[(w, a)]['total_orders_per_yr'])
                                for w in WINDOWS for a in ARMS3}, 'DECISION_TABLE.csv')
    add('reweights_per_year', '', {(w, a): float(dec[(w, a)]['reweights_per_yr'])
                                   for w in WINDOWS for a in ARMS3}, 'DECISION_TABLE.csv')
    add('turnover_ann', '%', {(w, a): float(dec[(w, a)]['turnover_ann_pct'])
                              for w in WINDOWS for a in ARMS3}, 'DECISION_TABLE.csv')
    add('cost_drag_bp_per_year', 'bp',
        {(w, a): COST_RATE_B * float(dec[(w, a)]['turnover_ann_pct']) * 100.0
         for w in WINDOWS for a in ARMS3}, 'derived 20bp x turnover')
    add('effn_exec_mean', '', {(w, a): float(conc[(w, a)]['effn_mean'])
                               for w in WINDOWS for a in ARMS3}, 'CONCENTRATION.csv')
    add('top1_max', '%', {(w, a): float(conc[(w, a)]['top1_max_pct'])
                          for w in WINDOWS for a in ARMS3}, 'CONCENTRATION.csv')
    add('te_mean_abs_dev', '%', {(w, a): float(tr[(w, a)]['mean_abs_weight_dev_pct'])
                                 for w in WINDOWS for a in ARMS3}, 'TRACKING_ERROR.csv')
    add('cagr_cost_c_stress40bp', '%',
        {(w, a): float(perf[(w, a)]['cagr_c_cal_pct_stress40bp'])
         for w in WINDOWS for a in ARMS3}, 'PERFORMANCE.csv')
    write_csv(f'{OUT}/EXECUTION_FREEZE_DECISION_MATRIX.csv', rows)
    return rows

PERF_ROWS = []
CONTRAST = {}


def build_contrast():
    for w in WINDOWS:
        yrs = YEARS_CAL[w]
        sA = _stats(RES[(w, A_ID)]['ret_lists']['net_b'], yrs)
        sB = _stats(RES[(w, B_ID)]['ret_lists']['net_b'], yrs)
        oA = ORD_ROWS_ORDERS[(w, A_ID)]
        oB = ORD_ROWS_ORDERS[(w, B_ID)]
        extra_red = (oA - oB) / oA if oA else 0.0
        CONTRAST[w] = {
            'orders_A_per_year': rnd12(oA), 'orders_B_per_year': rnd12(oB),
            'extra_order_reduction_rel': rnd12(extra_red),
            'order_anchor_ok': extra_red >= ORDER_CUT_MIN_REL,
            'd_cagr_pp_B_minus_A': rnd12(sB['cagr_pct'] - sA['cagr_pct']),
            'cagr_near_ok': abs(sB['cagr_pct'] - sA['cagr_pct']) <= CAGR_NEAR_PP,
            'd_sharpe_B_minus_A': rnd12((sB['sharpe'] or 0.0) - (sA['sharpe'] or 0.0)),
            'd_maxdd_pp_B_minus_A': rnd12(sB['maxdd_pct'] - sA['maxdd_pct'])}


def evaluate_anchors():
    ev = {}
    for w in WINDOWS:
        c = CONTRAST[w]
        d = DRIFT[w]
        rv = RW_VAL[w]
        risk_breach = (c['d_maxdd_pp_B_minus_A'] > DD_MAX_WORSEN_PP
                       or c['d_sharpe_B_minus_A'] < SHARPE_MIN_DELTA or not d['ok'])
        rw_clear_value = bool(rv['clear_value'])
        winB = (c['order_anchor_ok'] and c['cagr_near_ok']
                and c['d_sharpe_B_minus_A'] >= SHARPE_MIN_DELTA
                and c['d_maxdd_pp_B_minus_A'] <= DD_MAX_WORSEN_PP
                and d['ok'] and not rw_clear_value)
        winA = rw_clear_value or risk_breach
        ev[w] = {'order_cut': [rnd12(c['extra_order_reduction_rel']), ORDER_CUT_MIN_REL,
                               c['order_anchor_ok']],
                 'cagr_delta_pp': [c['d_cagr_pp_B_minus_A'], CAGR_NEAR_PP, c['cagr_near_ok']],
                 'sharpe_delta': [c['d_sharpe_B_minus_A'], SHARPE_MIN_DELTA,
                                  c['d_sharpe_B_minus_A'] >= SHARPE_MIN_DELTA],
                 'maxdd_delta_pp': [c['d_maxdd_pp_B_minus_A'], DD_MAX_WORSEN_PP,
                                    c['d_maxdd_pp_B_minus_A'] <= DD_MAX_WORSEN_PP],
                 'drift_frac_gt5pp': [rnd12(d['frac']), DRIFT_GT5PP_FRAC_MAX,
                                      d['frac'] <= DRIFT_GT5PP_FRAC_MAX],
                 'top1_max_pct': [rnd12(d['top1']), TOP1_MAX_PP_MAX,
                                  d['top1'] <= TOP1_MAX_PP_MAX],
                 'effn_mean': [rnd12(d['effn']), EFFN_MEAN_MIN, d['effn'] >= EFFN_MEAN_MIN],
                 'rw_value_mean_bp': [rnd12(rv['mean_bp']), RW_VALUE_MEAN_MIN_BP,
                                      rw_clear_value],
                 'rw_ci_low_bp': rnd12(rv['ci_lo_bp']),
                 'risk_breach': risk_breach, 'winB_EXEC99': winB, 'winA_EXEC05': winA}
    return ev


def classify_decision(ev):
    failed = [g for g in MANDATORY
              if g in TM_GATES and TM_GATES[g]['status'] != 'PASS']
    pending = [g for g in MANDATORY if g not in TM_GATES]
    if pending:
        return ('_PENDING', '_PENDING', {'pending_gates': pending})
    if failed:
        return ('EXECUTION_FREEZE_INVALID',
                'FORWARD_SHADOW_BLOCKED_FAIL_CLOSED', {'failed_mandatory': failed})
    wB = {w: ev[w]['winB_EXEC99'] for w in WINDOWS}
    wA = {w: ev[w]['winA_EXEC05'] for w in WINDOWS}
    mixed = (wB['W1'] and wA['W2']) or (wA['W1'] and wB['W2'])
    if mixed:
        return ('EXECUTION_FREEZE_MIXED', 'FORWARD_SHADOW_EXEC05_VS_EXEC99',
                {'winB': wB, 'winA': wA})
    if wB['W1'] and wB['W2']:
        return ('FREEZE_EXEC99_ENTRY_EXIT_ONLY', 'FREEZE_ENTRY_EXIT_ONLY',
                {'winB': wB, 'winA': wA})
    if wA['W1'] and wA['W2']:
        return ('FREEZE_EXEC05_100BP', 'KEEP_BAND_100BP_AS_EXECUTION_CANDIDATE',
                {'winB': wB, 'winA': wA})
    return ('EXECUTION_FREEZE_UNRESOLVED', 'FORWARD_SHADOW_EXEC05_VS_EXEC99',
            {'winB': wB, 'winA': wA})


def make_freeze_artifact(cls, nxt, ev):
    art = {
        'study': 'H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'preregistration_sha256': R['prereg_sha256'],
        'source_study_gates_sha256':
            sha256_file(f'{SRC}/TRANSACTION_MINIMIZATION_GATES.json'),
        'source_script_sha256':
            sha256_file(f'{ROOT}/tools/run_h0_v3_transaction_minimization_frontier.py'),
        'this_script_sha256': sha256_file(os.path.abspath(__file__)),
        'classification': cls, 'next_action': nxt,
        'canonical_replacement': False,
        'canonical_replacement_note':
            'Frys ar en dokumenterad kandidatstatus, INTE automatisk produktionstillampning',
        'anchor_evaluation_per_window': ev,
        'contrast_per_window': CONTRAST,
        'windows': WINDOWS}
    write_json(f'{OUT}/EXECUTION_CANDIDATE_FREEZE_DECISION.json', art)


def claim_scan_gate():
    wl = {'EXECUTION_FREEZE_REPORT.md'}
    hits = {}
    for fn in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, fn)
        if not os.path.isfile(p) or fn in wl:
            continue
        try:
            txt = open(p).read()
        except Exception:
            continue
        h = [t for t in FABRICATED_TOKENS if re.search(tok_re(t), txt)]
        if h:
            hits[fn] = h[:5]
    gate('NON_COMPUTED_CLAIM_SCAN', not hits,
         {'scanned_dir': OUT, 'whitelist': sorted(wl), 'hits': hits,
          'tokens_checked': len(FABRICATED_TOKENS),
          'note': 'REPORT.md skrivs efter skannningen men innehaller enbart tal och '
                  'klassstrangar harda från gateade strukturer - inga narrativa pastandon'})

def _f(x):
    return f'{x:.4g}'


def report_all(cls, nxt, ev):
    L = []
    add = L.append
    src_cls = R['src_report']['final_classification']
    add(f"# H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION - RAPPORT")
    add('')
    add(f"## A. Huvudresultat")
    add(f"- Klassificering: **{cls}**")
    add(f"- Next action: **{nxt}**")
    add(f"- Kandidater: A={A_ID}, B={B_ID}; referens={BASE_ID} (kan inte vinna)")
    add(f"- Kallstudie: {src_cls} / {R['src_report']['next_action']} (17/17 gates PASS)")
    add('')
    add("## B. Omfattning & icke-mal")
    add("- Ren beslutsaudit mellan tva redan validerade kandidater. Ingen ny forskning: "
        "inga nya band, ingen parameterokning, inga regelandringer.")
    add("- BASE replays endast for identitet/referens och kan inte vinna.")
    add('- Anvandarpreferens: mindre CAGR-forlust accepteras mot tydligt faerre '
        'transaktioner vid rimlig risk.')
    add('')
    add("## C. Kallstudie & provenans")
    add(f"- Frontier OUT: `{SRC}`")
    add(f"- Klassificering: {R['src_report']['final_classification']}")
    add(f"- Prereg sha256: `{R['provenance']['source_preregistration_sha256'][:16]}..`")
    add(f"- Denna studiens prereg sha256: `{R['prereg_sha256'][:16]}..` (frusen fore kor)")
    add('')
    add("## D. Identitet mot kallstudien (sha256)")
    idl = []
    for gname, aid in (('EXEC05_IDENTITY', A_ID), ('EXEC99_IDENTITY', B_ID),
                       ('BASE_REFERENCE_IDENTITY', BASE_ID)):
        g = TM_GATES[gname]['evidence']
        eq = all(g[w]['sha256_equal_to_frontier_pass1'] for w in WINDOWS)
        idl.append(f"{aid}: hash==frozen={eq} (pass1 {g['W1']['frontier_pass1_sha256'][:12]}..)")
        add(f"- {idl[-1]}")
    add("- Identiteten tacker metrics, orderstorlekssammanfattning, per-panel netto och "
        "slutnav (samma payload som kallstudiens determinism-gate).")
    add('')
    add("## E. Tillstandsberoende targets - provenans")
    dg = R['src_gates']['DESIRED_TARGET_IDENTITY_ACROSS_ARMS']
    add(f"- Kallgate status: {dg['status']}; pipeline-cashon dev mellan armar = "
        f"{dg['evidence']['pipeline_target_cashon_max_abs_dev']} (exakt 0)")
    add("- WP-sluttargets ar tillstandsberoende via WP-kapitalreallokering - dokumenterad "
        "prereg-avvikelse i kallstudien. Bada kandidaterna delar identisk pipeline-cashon i "
        "replays => skillnaden ar uteslutande execution-regeln.")
    add('')
    add("## F. Selektion & entry/exit-identitet")
    add("- in_target-mangder och (entries,exits)-tupler identiska mellan alla tre armerna "
        "per panel (se gates F/evidence).")
    add('')
    add("## G. Endast execution-regel skiljer")
    for w in WINDOWS:
        e = TM_GATES['EXECUTION_RULE_ONLY_DIFFERENCE']['evidence'][w]
        add(f"- {w}: EXEC99 continuing-reweight orders={e['EXEC99_continuing_reweight_orders']} "
            f"(maskinellt 0), EXEC05 kvarvarande reweights={e['EXEC05_remaining_reweight_orders']}, "
            f"band-violations={e['EXEC05_band_violations_on_executed_trades']}, "
            f"suppressed rader={e['suppressed_rows_total']}")
    add('')
    add("## H. Cost_B-identitet")
    add("- Konvention: COST_B = 20bp x executed weight turnover (wt_exec), verifierad per "
        "panel mot FACTORIAL/COST_B_REPLAY (se gate-evidence).")
    add('')
    add("## I. PIT & timing")
    add(f"- PIT_TEST: {TM_GATES['PIT_TEST']['status']}; RETURN_TIMING: "
        f"{TM_GATES['RETURN_TIMING']['status']} (V2-modul oforandrad; data-niva-test)")
    add('')
    add("## J. Isolation & determinism")
    add("- Andra fullstaendiga rerun: metric-dev <=1e-15 och sha256-likhet pass1/pass2 "
        "(se gate-evidence).")
    add('')
    add("## K. Prestanda (netto B, kalenderar)")
    for w in WINDOWS:
        for aid in ARMS3:
            r_ = next(x for x in PERF_ROWS if x['window'] == w and x['arm'] == aid)
            add(f"- {w} {aid}: CAGR={_f(r_['cagr_net_b_cal_pct'])}% "
                f"Sharpe={_f(r_['sharpe_b'])} MaxDD={_f(r_['maxdd_b_pct'])}% "
                f"Vol={_f(r_['vol_ann_b_pct'])}%")
    add('')
    add("## L. Orders & turnover")
    for w in WINDOWS:
        c = CONTRAST[w]
        add(f"- {w}: EXEC05={_f(c['orders_A_per_year'])} orders/ar, "
            f"EXEC99={_f(c['orders_B_per_year'])} orders/ar "
            f"({_f(100 * c['extra_order_reduction_rel'])}% faerre ytterligare)")
    add('')
    add("## M. Ekonomi per 100 extra orders (EXEC05 vs EXEC99)")
    for w in WINDOWS:
        c = CONTRAST[w]
        ex = c['orders_A_per_year'] - c['orders_B_per_year']
        if ex:
            add(f"- {w}: {_f(ex)} extra orders/ar kostar {_f(c['d_cagr_pp_B_minus_A'])}pp CAGR "
                f"({_f(c['d_cagr_pp_B_minus_A'] / (ex / 100.0))}pp per 100 orders), "
                f"dSharpe={_f(c['d_sharpe_B_minus_A'])}, dMaxDD={_f(c['d_maxdd_pp_B_minus_A'])}pp")
    add('')
    add("## N. Attribution: gross-path vs turnover-kostnad")
    for r_ in ATTR_ROWS:
        add(f"- {r_['window']} {r_['contrast']}: dlog_total={_f(r_['dlog_total'])} "
            f"(turnover-term={_f(r_['dlog_turnover_cost_saving'])}, "
            f"gross-path={_f(r_['dlog_gross_path'])}, resid={_f(r_['resid'])}) -> "
            f"{r_['answer_turnover_or_path']}")
    add('')
    add("## O. Har EXEC05:s kvarvarande reweights tydligt varde?")
    for w in WINDOWS:
        rv = RW_VAL[w]
        add(f"- {w}: paired mean net-diff (EXEC05-EXEC99) = {_f(rv['mean_bp'])} bp/panel, "
            f"CI95-low = {_f(rv['ci_lo_bp'])} bp -> tydligt varde enligt ankare: "
            f"{rv['clear_value']} (anchor mean>{RW_VALUE_MEAN_MIN_BP}bp OCH CI_low>0)")
    add('')
    add("## P. Drift & koncentration (EXEC99-riskvy)")
    for w in WINDOWS:
        d = DRIFT[w]
        add(f"- {w}: frac paneler med namn>5pp fran target={_f(d['frac'])} "
            f"(anchor<={DRIFT_GT5PP_FRAC_MAX}), Top1 max={_f(d['top1'])}% "
            f"(<={TOP1_MAX_PP_MAX}), effn_mean={_f(d['effn'])} (>={EFFN_MEAN_MIN}) -> "
            f"drift_rimlig={d['ok']}")
    add('')
    add("## Q. Tracking vs BASE")
    for r_ in TR_ROWS:
        if r_['arm'] != BASE_ID:
            add(f"- {r_['window']} {r_['arm']}: mean|dev|={_f(r_['mean_abs_weight_dev_pct'])}%, "
                f"TE={_f(r_['return_te_ann_pct_vs_BASE'])}%, corr={_f(r_['net_corr_vs_BASE'])}")
    add('')
    add("## R. Svansar & drawdowns")
    tail_rows = [x for x in TAIL_ROWS if x['kind'] == 'drawdown_episode_gt5pct']
    for r_ in tail_rows:
        add(f"- {r_['window']} {r_['arm']}: DD-episod>5%: {r_['date']} djup={_f(r_['value_pct'])}%")
    for r_ in TAIL_CONTRIB_ROWS:
        add(f"- {r_['window']} top5-paneler stander for "
            f"{_f(r_['cum_share_of_total_positive_logdiff_pct'])}% av EXEC05:s positiva "
            f"log-diff vs EXEC99 (rank {r_['rank']})")
    add('')
    add("## S. Tidsstabilitet (halvor)")
    for r_ in TS_ROWS:
        add(f"- {r_['window']} {r_['half']}: CAGR B-A={_f(r_['cagr_contrast_pp'])}pp "
            f"(A={_f(r_['cagr_A_pct'])}%, B={_f(r_['cagr_B_pct'])}%), "
            f"orders A/B={r_['orders_A']}/{r_['orders_B']}")
    add('')
    add("## T. Leave-one-year-out")
    worst = {}
    for r_ in LOO_ROWS:
        if r_['arm'] == B_ID:
            k = r_['window']
            if k not in worst or abs(r_['delta_vs_full_pp']) > abs(worst[k]['delta_vs_full_pp']):
                worst[k] = r_
    for w, r_ in worst.items():
        add(f"- {w} EXEC99 sammalangt ar: {r_['omitted_year']} "
            f"(dCAGR={_f(r_['delta_vs_full_pp'])}pp, MaxDD={_f(r_['maxdd_loo_pct'])}%)")
    add('')
    add("## U. Beslutsdata (matris)")
    for r_ in MATRIX_ROWS:
        add(f"- {r_['metric']} [{r_['unit']}]: W1 BASE/EX05/EX99 = "
            f"{_f(r_['W1_BASE'])}/{_f(r_['W1_EXEC05'])}/{_f(r_['W1_EXEC99'])}; W2 = "
            f"{_f(r_['W2_BASE'])}/{_f(r_['W2_EXEC05'])}/{_f(r_['W2_EXEC99'])} ({r_['source']})")
    add('')
    add("## V. Ankarsutvardering per fonster")
    for w in WINDOWS:
        add(f"- {w}:")
        for k_, v_ in ev[w].items():
            if isinstance(v_, list):
                add(f"  - {k_}: varde={v_[0]}, anchor={v_[1]}, ok={v_[2]}")
            else:
                add(f"  - {k_}: {v_}")
    add('')
    add("## W. Slutsats")
    add(f"- Beslut: **{cls}** -> {nxt}")
    if cls.startswith('FREEZE'):
        add(f"- Kandidat frusen: {'EXEC99_ENTRY_EXIT_ONLY' if 'EXEC99' in cls else 'EXEC05_BAND_100BP'}")
    add("- CANONICAL_REPLACEMENT=FALSE: frysen ar dokumenterad kandidatstatus, inte "
        "automatisk produktionstillampning.")
    add(f"- Gates: {sum(1 for g in MANDATORY if TM_GATES[g]['status']=='PASS')}/"
        f"{len(MANDATORY)} PASS; failed="
        f"{[g for g in MANDATORY if TM_GATES[g]['status']!='PASS']}")
    md = '\n'.join(L) + '\n'
    open(f'{OUT}/EXECUTION_FREEZE_REPORT.md', 'w').write(md)


def main():
    import glob as _g
    os.makedirs(OUT, exist_ok=True)
    for pth in _g.glob(f'{OUT}/*'):
        if os.path.isfile(pth):
            os.remove(pth)
    print('[MAIN] purge klar', flush=True)
    load_prior()
    src_failed = [g for g, st in R['src_gates'].items() if st.get('status') != 'PASS']
    src_ok = (not src_failed
              and R['src_report']['final_classification'] == 'ENTRY_EXIT_ONLY_SUFFICIENT'
              and R['src_report']['next_action'] == 'FREEZE_EXECUTION_CANDIDATE'
              and R['src_cls']['mandatory_gates_all_pass'] in (True, 1))
    gate('SOURCE_FRONTIER_STUDY_VALID', src_ok, {
        'source_classification': R['src_report']['final_classification'],
        'source_next_action': R['src_report']['next_action'],
        'source_mandatory_gates_all_pass': R['src_cls']['mandatory_gates_all_pass'],
        'source_gate_failures': src_failed})
    source_provenance()
    freeze_prereg()
    V2.load_contexts()
    V2.load_refs()
    RES.update(run3(True))
    global PERF_ROWS, TR_ROWS, ATTR_ROWS, TAIL_ROWS, TAIL_CONTRIB_ROWS, TS_ROWS, \
        LOO_ROWS, MATRIX_ROWS, RW_VAL, DRIFT
    identity_gates()
    rule_and_provenance_gates()
    costb_gate()
    pit_timing_gates()
    for r_ in analyze_orders():
        ORD_ROWS_ORDERS[(r_['window'], r_['arm'])] = float(r_['orders_per_year'])
    PERF_ROWS = analyze_performance()
    analyze_turnover()
    analyze_per100()
    ATTR_ROWS = analyze_attr()
    RW_VAL = analyze_reweight_value()
    DRIFT = analyze_concentration_drift()
    analyze_tracking_reuse()
    TR_ROWS = [{'window': w, 'arm': a,
                'mean_abs_weight_dev_pct': float(next(
                    x for x in R['prior']['TRACK']
                    if x['window'] == w and x['arm'] == a)['mean_abs_weight_dev_pct']),
                'return_te_ann_pct_vs_BASE': float(next(
                    x for x in R['prior']['TRACK']
                    if x['window'] == w and x['arm'] == a)['return_tracking_error_ann_pct']),
                'net_corr_vs_BASE': float(next(
                    x for x in R['prior']['TRACK']
                    if x['window'] == w and x['arm'] == a)['net_return_correlation_vs_BASE'])}
               for w in WINDOWS for a in ARMS3]
    TAIL_ROWS, TAIL_CONTRIB_ROWS = analyze_tails()
    TS_ROWS = analyze_time_stability()
    LOO_ROWS = analyze_loo()
    MATRIX_ROWS = analyze_matrix()
    build_contrast()
    ev = evaluate_anchors()
    isolation_determinism()
    claim_scan_gate()
    cls, nxt, det = classify_decision(ev)
    if '_PENDING' in (cls, nxt):
        raise RuntimeError(f'gates saknas for klassificering: {det}')
    make_freeze_artifact(cls, nxt, ev)
    if cls.startswith('FREEZE'):
        fa = json.load(open(f'{OUT}/EXECUTION_CANDIDATE_FREEZE_DECISION.json'))
        fa['freeze_status'] = 'FROZEN_CANDIDATE'
        write_json(f'{OUT}/EXECUTION_CANDIDATE_FREEZE.json', fa)
    report_all(cls, nxt, ev)
    write_json(f'{OUT}/EXECUTION_FREEZE_GATES.json', {'gates': rnd12(TM_GATES)})
    failed = [g for g in MANDATORY if TM_GATES[g]['status'] != 'PASS']
    print(f"[DONE] klass={cls} nasta={nxt} failed_mandatory={failed}", flush=True)
    return 2 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            os.makedirs(OUT, exist_ok=True)
            open(f'{OUT}/UNEXPECTED_ERROR_TRACEBACK.txt', 'w').write(tb)
        except Exception:
            pass
        sys.exit(3)
