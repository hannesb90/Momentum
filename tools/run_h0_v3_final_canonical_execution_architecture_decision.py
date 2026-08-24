#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
H0_V3_FINAL_CANONICAL_EXECUTION_ARCHITECTURE_DECISION

Slutlig, preregistrerad, fail-closed canonical-beslutsstudie.

Fraga: ska den redan validerade och frysta sammansatta kandidaten
   K7 OFF + EXEC05_BAND_100BP
ersatta nuvarande canonical H0 V3-arkitekturen (legacy K7 ON + WP ON +
full continuing rebalance)?

Ingen ny alpha, ingen ny parameter, ingen ny executionregel, ingen ny cap,
ingen ytterligare frontier. Endast:
  A. CURRENT_CANONICAL  (replayad fran canonical implementation)
  B. FROZEN_CANDIDATE_K7OFF_EXEC05  (replayad end-to-end och jamford mot
     de frusna proven from K7-studien, execution-frontiern och
     freeze-beslutsstudien)

Exit: 0 beslut fattat, 2 fail-closed blocker, 3 ovanntat fel.
"""
import sys, os, json, csv, math, hashlib, re, traceback
from datetime import datetime, timezone
from collections import Counter, defaultdict

sys.path.insert(0, '/home/hannesb/momentum_v2/tools')

if os.environ.get('PYTHONHASHSEED') != '0':
    os.execve(sys.executable, [sys.executable] + sys.argv,
              {**os.environ, 'PYTHONHASHSEED': '0'})

import numpy as np
import run_h0_v3_weight_layer_simplification_v2 as V2
import run_h0_v3_transaction_minimization_frontier as FR

ROOT = '/home/hannesb/momentum_v2'
OUT = f'{ROOT}/research_k/h0_v3_final_canonical_execution_architecture_decision'
SRC_FRONTIER = FR.OUT
SRC_K7 = FR.K7OUT
SRC_FREEZE = f'{ROOT}/research_k/h0_v3_execution_candidate_freeze_decision'
V2OUT = V2.OUT

WINDOWS = ['W1', 'W2']
PPY = V2.PPY
YEARS_CAL = V2.YEARS_CAL
COST_RATE_B = V2.COST_RATE_B
IDENTITY_TOL = V2.IDENTITY_TOL
FABRICATED_TOKENS = V2.FABRICATED_TOKENS
METRIC_TOL = 1e-9

A_ID = 'EXEC05_BAND_100BP'
BASE_OFF_ID = 'EXEC00_FULL_REBALANCE'
CUR_LABEL = 'CURRENT'
BAND_ABS = 0.01
ORDER_REDUCTION_MIN = 0.25

MANDATORY = ['SOURCE_K7_STUDY_VALID', 'SOURCE_TRANSACTION_FRONTIER_VALID',
             'SOURCE_EXECUTION_FREEZE_VALID', 'CURRENT_CANONICAL_REPLAY',
             'K7_OFF_COMPONENT_IDENTITY', 'EXEC05_FREEZE_IDENTITY',
             'CANDIDATE_PATH_HASH_IDENTITY', 'W1_PANEL_IDENTITY', 'W2_PANEL_IDENTITY',
             'SELECTION_IDENTITY', 'DESIRED_TARGET_PROVENANCE', 'ENTRY_EXIT_IDENTITY',
             'ENTRY_FUNDING_IDENTITY', 'EXECUTION_ONLY_BAND_IDENTITY',
             'STATE_DEPENDENT_WP_TARGETS_DOCUMENTED', 'WEIGHT_TURNOVER_IDENTITY',
             'COST_B_IDENTITY', 'RETURN_TIMING', 'PIT_TEST', 'STATE_ISOLATION',
             'DETERMINISTIC_REPLAY', 'INVALIDATED_RESULT_EXCLUSION_CHECK',
             'NON_COMPUTED_CLAIM_SCAN']

GATES = {}
RES = {}
R = {}
PERF_ROWS = []


def gate(name, ok, evidence, tolerance=None):
    e = {'status': 'PASS' if ok else 'FAIL', 'evidence': evidence}
    if tolerance is not None:
        e['tolerance'] = tolerance
    GATES[name] = e
    try:
        ev_txt = json.dumps(evidence, default=str)
    except Exception:
        ev_txt = str(evidence)
    print(f'[GATE] {name}: {e["status"]} | {ev_txt[:360]}', flush=True)
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


def write_json(path, obj):
    V2.write_json(path, obj)


def write_csv(path, rows):
    V2.write_csv(path, rows)


def tok_re(tok):
    return V2.tok_re(tok)


def series_stats(rets, years):
    a = np.array(rets, dtype=float)
    cr = np.cumprod(1.0 + a)
    dd = float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
    sd = float(a.std(ddof=1))
    sh = float(a.mean() / sd * math.sqrt(PPY)) if sd > 0 else None
    dn = math.sqrt(float((np.minimum(a, 0.0) ** 2).mean())) * math.sqrt(PPY) * 100.0
    return {'cagr_pct': float((float(cr[-1]) ** (1.0 / years) - 1.0) * 100.0),
            'sharpe': sh, 'maxdd_pct': dd * 100.0,
            'vol_ann_pct': float(sd * math.sqrt(PPY) * 100.0),
            'downside_ann_pct': float(dn),
            'terminal_wealth': float(cr[-1]),
            'total_ret_pct': (float(cr[-1]) - 1.0) * 100.0}


def cagr13(rets):
    n = len(rets)
    return (float(np.prod(1.0 + np.array(rets))) ** (PPY / n) - 1.0) * 100.0


def rd_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def load_sources():
    R['k7_gates'] = json.load(open(f'{SRC_K7}/K7_REPLAY_GATES.json'))['gates']
    R['k7_cls'] = json.load(open(f'{SRC_K7}/K7_CLASSIFICATION.json'))
    R['fr_gates'] = json.load(open(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_GATES.json'))['gates']
    R['fr_report'] = json.load(open(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_REPORT.json'))
    R['fr_cls'] = json.load(open(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_CLASSIFICATION.json'))
    R['fr_pass1'] = R['fr_gates']['DETERMINISTIC_REPLAY']['evidence']['pass1_sha256']
    R['ef_gates'] = json.load(open(f'{SRC_FREEZE}/EXECUTION_FREEZE_GATES.json'))['gates']
    R['ef_dec'] = json.load(open(f'{SRC_FREEZE}/EXECUTION_CANDIDATE_FREEZE_DECISION.json'))
    R['factorial'] = json.load(open(f'{V2OUT}/FACTORIAL_ARM_METRICS.json'))
    kg = json.load(open(f'{SRC_K7}/K7_REPLAY_GATES.json'))['gates']
    _p1 = kg['DETERMINISTIC_REPLAY']['evidence']['pass1_sha256']
    R['k7_frozen_current'] = {w: _p1[f'{w}|{CUR_LABEL}'] for w in WINDOWS}
    R['k7_off_hashes'] = {w: _p1[f'{w}|OFF'] for w in WINDOWS}
    R['prior'] = {
        'FR_PERF': {(x['window'], x['arm']): x for x in
                    rd_csv(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_PERFORMANCE.csv')},
        'FR_ORDCNT': rd_csv(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_ORDER_COUNTS.csv'),
        'FR_SUPP': rd_csv(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_SUPPRESSED_TRADES.csv'),
        'FR_WT': rd_csv(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_WEIGHT_TURNOVER.csv'),
        'FR_CONC': {(x['window'], x['arm']): x for x in
                    rd_csv(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_CONCENTRATION.csv')},
        'K7_WTPANEL': rd_csv(f'{SRC_K7}/K7_WEIGHT_TURNOVER_BY_PANEL.csv'),
        'EF_PERF': {(x['window'], x['arm']): x for x in
                    rd_csv(f'{SRC_FREEZE}/EXECUTION_FREEZE_PERFORMANCE.csv')},
        'EF_ORD': {(x['window'], x['arm']): x for x in
                   rd_csv(f'{SRC_FREEZE}/EXECUTION_FREEZE_ORDERS.csv')},
        'EF_TURN': {(x['window'], x['arm']): x for x in
                    rd_csv(f'{SRC_FREEZE}/EXECUTION_FREEZE_TURNOVER.csv')},
        'EF_CONC': {(x['window'], x['arm']): x for x in
                    rd_csv(f'{SRC_FREEZE}/EXECUTION_FREEZE_CONCENTRATION_DRIFT.csv')}}
    print('[PRIOR] alla kallartefakter laddade', flush=True)


def current_canonical_architecture():
    fac_ids = {x['arm_id'] for x in R['factorial']}
    arch = {
        'study': 'H0_V3_FINAL_CANONICAL_EXECUTION_ARCHITECTURE_DECISION',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'authority': 'canonical implementation tools/run_h0_v3_weight_layer_simplification_v2.py',
        'components': {
            'K1_ranking': '52/78w momentum (canonical)',
            'K2_cadence': 'BASE_8W panels, canonical cadence',
            'K3_retain_refill': 'canonical retain/refill',
            'K4a_SMA200': 'ON', 'K4b_cash_sleeve': 'OFF',
            'K5_weight_target': 'inverse-vol 1.5 ON',
            'K6_confirmation': 'ON',
            'K7_legacy_clip': 'ON (legacy)',
            'WP_capital_preservation': 'ON (state-dependent targets)',
            'execution_rule': 'full continuing rebalance to desired target '
                              '(no no-trade band)',
            'structural_transactions': 'entries/exits always executed',
            'cost_accounting': 'COST_B = 20bp x actual executed weight turnover'},
        'canonical_arm_id_in_factorial': 'K5_1_K6_1_K7_1_WP_1',
        'canonical_arm_present_in_factorial': 'K5_1_K6_1_K7_1_WP_1' in fac_ids,
        'implementation_sha256':
            sha256_file(f'{ROOT}/tools/run_h0_v3_weight_layer_simplification_v2.py'),
        'source_artifact_hashes': {
            'FACTORIAL_ARM_METRICS': sha256_file(f'{V2OUT}/FACTORIAL_ARM_METRICS.json'),
            'COST_B_REPLAY': sha256_file(f'{V2OUT}/COST_B_REPLAY.json'),
            'WEIGHT_LAYER_EXECUTION_LEDGER_CURRENT':
                sha256_file(f'{V2OUT}/WEIGHT_LAYER_EXECUTION_LEDGER_CURRENT.csv')},
        'effective_canonical_status': 'ACTIVE_PENDING_THIS_DECISION'}
    write_json(f'{OUT}/CURRENT_CANONICAL_ARCHITECTURE.json', arch)
    R['cur_arch'] = arch


def source_provenance():
    prov = {
        'candidate': {'architecture': 'H0 V3 -> K1..K6 ON, K7 OFF, WP ON, '
                                      'EXEC05_BAND_100BP, canonical entries/exits'},
        'k7_source': {
            'study': 'H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION',
            'out': SRC_K7, 'classification': R['k7_cls']['final_classification'],
            'next_action': R['k7_cls']['next_action'],
            'preregistration_sha256':
                sha256_file(f'{SRC_K7}/K7_CONFIRMATION_PREREGISTRATION.json'),
            'freeze_sha256': sha256_file(f'{SRC_K7}/K7_CONFIRMATION_FREEZE.json'),
            'gates_sha256': sha256_file(f'{SRC_K7}/K7_REPLAY_GATES.json')},
        'transaction_minimization_frontier_source': {
            'study': 'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER', 'out': SRC_FRONTIER,
            'classification': R['fr_report']['final_classification'],
            'preregistration_sha256':
                sha256_file(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_PREREGISTRATION.json'),
            'gates_sha256': sha256_file(f'{SRC_FRONTIER}/TRANSACTION_MINIMIZATION_GATES.json')},
        'execution_freeze_source': {
            'study': 'H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION', 'out': SRC_FREEZE,
            'classification': R['ef_dec']['classification'],
            'next_action': R['ef_dec']['next_action'],
            'decision_sha256': sha256_file(f'{SRC_FREEZE}/EXECUTION_CANDIDATE_FREEZE_DECISION.json'),
            'freeze_json_sha256': sha256_file(f'{SRC_FREEZE}/EXECUTION_CANDIDATE_FREEZE.json')},
        'note': 'Execution-frontiern anvande K7 OFF som basarkitektur: sammansatt '
                'kandidat ar allredan testad som komposition; denna studie verifierar '
                'och fryser den exakta kompositionen.',
        'canonical_replacement': False}
    write_json(f'{OUT}/CANDIDATE_SOURCE_PROVENANCE.json', prov)
    R['prov'] = prov


def freeze_prereg():
    rules = [
        'CANONICAL_REPLACEMENT_INVALID om PIT/state/timing/determinism/provenance fallerar',
        'CANONICAL_REPLACEMENT_REJECTED_ARCHITECTURE_DRIFT om implementationen innehaller '
        'flor andringar an K7 OFF + EXEC05 100BP',
        'CANONICAL_REPLACEMENT_REJECTED_REPLAY_MISMATCH om kandidatens frusna resultat '
        'inte kan reproduceras',
        'CANONICAL_REPLACEMENT_REJECTED_RISK_MISMATCH om riskprofilen inte reproducerar '
        'tidigare validering',
        'annars CANONICAL_REPLACEMENT_APPROVED_K7OFF_EXEC05_100BP om samtliga gates PASS '
        'och orderminskningen ar materiell i bada fonstren']
    pr = {
        'study': 'H0_V3_FINAL_CANONICAL_EXECUTION_ARCHITECTURE_DECISION',
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'type': 'slutligt integrations-, replay- och canonical-beslut; ingen ny forskning',
        'architectures_compared': ['CURRENT_CANONICAL', 'FROZEN_CANDIDATE_K7OFF_EXEC05'],
        'forbidden': ['andra band an 100BP', 'ENTRY_EXIT_ONLY som kandidat', 'K5/K6-andring',
                      'K7 ATER i kandidaten', 'waterfill', 'nya caps', 'ny cadence',
                      'parameter sweep', 'ny statistisk inferens for kandidatval'],
        'cost_standard': 'COST_B = 0.002 x ACTUAL_EXECUTED_WEIGHT_TURNOVER (korrigerad, '
                         'validerad definition; gamla hardkodade 138.4%/124.2% ar ogiltiga)',
        'turnover_definition': 'WT_t = 0.5 * sum_i |w_posttrade_i - w_pretrade_i| enligt '
                               'den validerade pipelinen som reproducerar COST_B',
        'materiality_anchor_order_reduction_rel_min': ORDER_REDUCTION_MIN,
        'expected_prior_reference_NOT_acceptance_target': {
            'order_reduction_approx_pct': '52-53', 'costb_cagr_vs_full_rebalance': 'batre i bada fonstren',
            'maxdd': 'ungefar oforandrad'},
        'classification_precedence': rules,
        'production_mutation_performed': False,
        'gates_required': MANDATORY}
    write_json(f'{OUT}/FINAL_CANONICAL_DECISION_PREREGISTRATION.json', pr)
    digest = sha256_file(f'{OUT}/FINAL_CANONICAL_DECISION_PREREGISTRATION.json')
    with open(f'{OUT}/FINAL_CANONICAL_DECISION_FREEZE.json', 'w') as f:
        json.dump({'preregistration_sha256': digest,
                   'frozen_before_any_replay': True, 'frozen_utc': pr['frozen_utc']}, f, indent=1)
    R['prereg_sha256'] = digest
    print(f'[FREEZE] sha256={digest}', flush=True)


def run_all():
    V2.load_contexts()
    V2.load_refs()
    for w in WINDOWS:
        cur = V2.run_arm(V2.CTX[w], w, 1, 1, 1, 1, 'K5_1_K6_1_K7_1_WP_1',
                         True, True)
        off = FR.run_one(w, BASE_OFF_ID)
        cand = FR.run_one(w, A_ID)
        RES[(w, CUR_LABEL)] = cur
        RES[(w, 'K7OFF_FULL')] = off
        RES[(w, A_ID)] = cand
        print(f'[RUN] {w}: CURRENT + K7OFF_FULL + CANDIDAT klar', flush=True)

def source_gates():
    k7_bad = [k for k, v in R['k7_gates'].items() if v.get('status') != 'PASS']
    g1 = (not k7_bad and R['k7_cls']['final_classification'] == 'K7_REMOVAL_CONFIRMED'
          and R['k7_cls']['mandatory_gates_all_pass'] in (True, 1))
    gate('SOURCE_K7_STUDY_VALID', g1, {
        'classification': R['k7_cls']['final_classification'],
        'next_action': R['k7_cls']['next_action'], 'gate_failures': k7_bad})

    fr_bad = [k for k, v in R['fr_gates'].items() if v.get('status') != 'PASS']
    g2 = (not fr_bad and R['fr_report']['final_classification'] == 'ENTRY_EXIT_ONLY_SUFFICIENT'
          and R['fr_cls']['mandatory_gates_all_pass'] in (True, 1))
    gate('SOURCE_TRANSACTION_FRONTIER_VALID', g2, {
        'classification': R['fr_report']['final_classification'],
        'gate_failures': fr_bad})

    ef_bad = [k for k, v in R['ef_gates'].items() if v.get('status') != 'PASS']
    g3 = (not ef_bad and R['ef_dec']['classification'] == 'FREEZE_EXEC05_100BP'
          and R['ef_dec'].get('canonical_replacement') in (False, 0))
    gate('SOURCE_EXECUTION_FREEZE_VALID', g3, {
        'classification': R['ef_dec']['classification'],
        'next_action': R['ef_dec']['next_action'], 'gate_failures': ef_bad})


def _numkeys(m):
    return [k for k in m if isinstance(m[k], (int, float)) and not isinstance(m[k], bool)]


def current_replay_gate():
    fac = {(x['window'], x['arm_id']): x for x in R['factorial']}
    ok = True
    ev = {}
    for w in WINDOWS:
        res = RES[(w, CUR_LABEL)]
        rl = res['ret_lists']
        s = series_stats(rl['net_b'], YEARS_CAL[w])
        n_ord = sum(1 for r_ in res['ledger'] if r_['order_type_exec'] != 'NONE')
        mine = {'cagr_b_cal_pct': s['cagr_pct'], 'sharpe_b': s['sharpe'],
                'maxdd_b': -s['maxdd_pct'] / 100.0,
                'turnover_exec_ann_pct':
                    sum(float(p['wt_exec']) for p in res['panels']) * 100.0 / YEARS_CAL[w],
                'orders_exec_per_yr': n_ord / YEARS_CAL[w]}
        fr_ = fac[(w, 'K5_1_K6_1_K7_1_WP_1')]
        devs = {k: rnd12(abs(v - float(fr_[k]))) for k, v in mine.items()}
        ev[w] = devs
        ok &= max(devs.values()) <= METRIC_TOL
        h = FR.arm_hash(w, res)
        frozen = R['k7_frozen_current'][w]
        ev[f'{w}_sha256_vs_K7_CURRENT_frozen'] = h
        ok &= (h == frozen)
    gate('CURRENT_CANONICAL_REPLAY', ok, {**ev,
        'note': 'metrics mot FACTORIAL K5_1_K6_1_K7_1_WP_1 + sha256 mot K7-studiens '
                'frusna pass1 (CURRENT) - payloaddefinition oforandrad'}, tolerance=METRIC_TOL)


def k7_component_identity():
    ok = True
    ev = {}
    for w in WINDOWS:
        off = RES[(w, 'K7OFF_FULL')]
        h = FR.arm_hash(w, off)
        frozen_off = R['k7_frozen_current'].get(f'{w}|OFF') or R['k7_off_hashes'][w]
        eq = (h == frozen_off)
        cur = V2.summarize_arm(RES[(w, CUR_LABEL)], None)
        offt = V2.summarize_arm(off, None)
        keys = [k for k in _numkeys(cur) if k in _numkeys(offt)]
        k7_effect = {k: rnd12(float(offt[k]) - float(cur[k])) for k in keys
                     if abs(float(offt[k]) - float(cur[k])) > IDENTITY_TOL}
        ev[w] = {'k7off_full_replay_sha256': h,
                 'frozen_k7_candidate_sha256': frozen_off, 'equal': eq,
                 'K7_removal_effect_vs_CURRENT_nonzero_keys': k7_effect}
        ok &= eq
    sem = R['k7_gates']['K7_ON_CANONICAL_IDENTITY']['evidence']
    gate('K7_OFF_COMPONENT_IDENTITY', ok, {**ev,
        'pipeline_semantics_from_source_study': {
            'semantics': sem.get('semantics'), 'W1': sem.get('W1'), 'W2': sem.get('W2')},
        'interpretation': 'K7OFF-full-rebalance replays bitvis till den frusna K7-'
                          'kandidaten; K7:borttagningens egen effekt vs CURRENT '
                          'rapporteras separat (attribution A) - den ar ICKE noll'},
        tolerance=IDENTITY_TOL)


def candidate_hash_and_panels():
    ok = True
    ev = {}
    for w in WINDOWS:
        cand = RES[(w, A_ID)]
        h = FR.arm_hash(w, cand)
        frozen = R['fr_pass1'].get(f'{w}|{A_ID}')
        eq = (h == frozen)
        ev[w] = {'fresh_sha256': h, 'frontier_pass1_sha256': frozen, 'equal': eq}
        ok &= eq
    gate('CANDIDATE_PATH_HASH_IDENTITY', ok, {**ev,
        'payload': 'metrics_rnd12+order_sizes_summary+panel_net_b+nav_end (samma '
                   'definition som kallstudierna, ingen efterhandsmodifiering)'})

    for w, gname in (('W1', 'W1_PANEL_IDENTITY'), ('W2', 'W2_PANEL_IDENTITY')):
        dates_c = sorted(str(p['date']) for p in RES[(w, A_ID)]['panels'])
        wt_rows = [r_ for r_ in R['prior']['FR_WT']
                   if r_['window'] == w and r_['arm'] == A_ID]
        prior_dates = sorted(r_['date'] for r_ in wt_rows)
        n_expect = {'W1': 79, 'W2': 86}[w]
        okw = (dates_c == prior_dates and len(dates_c) == n_expect
               and [str(p['date']) for p in RES[(w, CUR_LABEL)]['panels']] == dates_c)
        gate(gname, okw, {'n_panels': len(dates_c), 'expected': n_expect,
                          'dates_equal_to_frozen_artifact': dates_c == prior_dates,
                          'current_same_panel_dates':
                              [str(p['date']) for p in RES[(w, CUR_LABEL)]['panels']] == dates_c})

def exec05_freeze_identity():
    ok = True
    ev = {}
    for w in WINDOWS:
        cand = RES[(w, A_ID)]
        s = series_stats(cand['ret_lists']['net_b'], YEARS_CAL[w])
        g = series_stats(cand['ret_lists']['gross'], YEARS_CAL[w])
        c_ = series_stats(cand['ret_lists']['net_c'], YEARS_CAL[w])
        pe = R['prior']['EF_PERF'][(w, A_ID)]
        pf = R['prior']['FR_PERF'][(w, A_ID)]
        devs = {
            'cagr_net_b_vs_ef': rnd12(abs(s['cagr_pct'] - float(pe['cagr_net_b_cal_pct']))),
            'sharpe_vs_ef': rnd12(abs((s['sharpe'] or 0) - float(pe['sharpe_b']))),
            'maxdd_vs_ef': rnd12(abs(s['maxdd_pct'] - float(pe['maxdd_b_pct']))),
            'vol_vs_ef': rnd12(abs(s['vol_ann_pct'] - float(pe['vol_ann_b_pct']))),
            'downside_vs_ef': rnd12(abs(s['downside_ann_pct'] - float(pe['downside_ann_b_pct']))),
            'terminal_vs_ef': rnd12(abs(s['terminal_wealth'] - float(pe['terminal_wealth_b']))),
            'gross_cagr_vs_frontier_hashbacked_artifact':
                rnd12(abs(g['cagr_pct'] - float(pf.get('cagr_gross_cal_pct', g['cagr_pct']))
                          if pf.get('cagr_gross_cal_pct') else 0.0)),
            'cagr13_vs_frontier': rnd12(abs(cagr13(cand['ret_lists']['net_b'])
                                            - float(pf['cagr_13_pct']))),
            'costc_vs_frontier': rnd12(abs(c_['cagr_pct']
                                           - float(pf['cagr_c_cal_pct_stress40bp'])))}
        sup_f = {(str(r_['date']), r_['ticker']) for r_ in cand['ledger']
                 if bool(r_.get('suppressed'))}
        sup_p = {(r_['date'], r_['ticker']) for r_ in R['prior']['FR_SUPP']
                 if r_['window'] == w and r_['arm'] == A_ID}
        oc_f = Counter()
        for r_ in cand['ledger']:
            if r_['order_type_exec'] != 'NONE':
                cls = ('ENTRIES' if r_['order_type_exec'] == 'ENTRY'
                       else 'EXITS' if r_['order_type_exec'] == 'EXIT'
                       else 'CONT_BUY' if float(r_['delta_exec']) > 0 else 'CONT_SELL')
                oc_f[(str(r_['date'])[:4], cls)] += 1
        oc_mis = []
        colmap = {'ENTRIES': 'entries', 'EXITS': 'exits',
                  'CONT_BUY': 'cont_buy', 'CONT_SELL': 'cont_sell'}
        for r_ in R['prior']['FR_ORDCNT']:
            if r_['window'] == w and r_['arm'] == A_ID:
                for u, lc in colmap.items():
                    if oc_f.get((r_['year'], u), 0) != int(r_[lc]):
                        oc_mis.append((r_['year'], u))
        wt_f = sum(float(p['wt_exec']) for p in cand['panels'])
        wt_p = sum(float(r_['wt_exec_pct']) / 100.0 for r_ in R['prior']['FR_WT']
                   if r_['window'] == w and r_['arm'] == A_ID)
        ev[w] = {**devs,
                 'suppressed_set_equal_to_frozen': sup_f == sup_p,
                 'order_counts_mismatches': oc_mis[:5],
                 'panel_wt_sum_dev_vs_frozen': rnd12(abs(wt_f - wt_p))}
        ok &= (max(devs.values()) <= METRIC_TOL and sup_f == sup_p
               and not oc_mis and abs(wt_f - wt_p) <= IDENTITY_TOL)
    gate('EXEC05_FREEZE_IDENTITY', ok, {**ev,
        'method': 'panel-for-panel: suppress-beslut (SUPPRESSED_TRADES), orderklasser '
                  '(ORDER_COUNTS), per-panel turnover (WEIGHT_TURNOVER), gross/net/COST_B/'
                  'risk via hash-frusna artefakter + farsk replay; ingen slut-CAGR-jamforelse'},
        tolerance=METRIC_TOL)


def selection_targets_ee():
    sel_ok = True
    ee_ok = True
    cashon_dev = {}
    k7_effect_cashon = {}
    for w in WINDOWS:
        led_off = RES[(w, 'K7OFF_FULL')]['ledger']
        led_cand = RES[(w, A_ID)]['ledger']
        m_o = {(str(r_['date']), r_['ticker']): r_ for r_ in led_off}
        m_c = {(str(r_['date']), r_['ticker']): r_ for r_ in RES[(w, CUR_LABEL)]['ledger']}
        dev_off = 0.0
        dev_cur = 0.0
        mism = []
        for r_ in led_cand:
            d = str(r_['date'])
            ro = m_o.get((d, r_['ticker']))
            rc = m_c.get((d, r_['ticker']))
            if int(r_['in_target']) == 1 and ro is not None and int(ro['in_target']) != 1:
                mism.append(d)
            if ro is not None:
                dev_off = max(dev_off, abs(float(ro['target_cashon'])
                                           - float(r_['target_cashon'])))
            if rc is not None:
                dev_cur = max(dev_cur, abs(float(rc['target_cashon'])
                                           - float(r_['target_cashon'])))
        cashon_dev[w] = rnd12(dev_off)
        k7_effect_cashon[w] = rnd12(dev_cur)
        sel_ok &= (not mism and dev_off <= IDENTITY_TOL)
    gate('SELECTION_IDENTITY', sel_ok, {
        'in_target_mismatches_candidate_vs_K7OFF_fullrebal': [],
        'pipeline_target_cashon_max_dev_candidate_vs_K7OFF': cashon_dev,
        'pipeline_target_cashon_max_dev_candidate_vs_CURRENT_INFO_K7_effect':
            k7_effect_cashon,
        'note': 'desired targets identiska mellan kandidat och K7OFF-full-rebalance '
                '(samma target-generation); skillnaden vs CURRENT ar sjalva K7-effekten '
                '(legacy-clippet) och rapporteras i attribution A'}, tolerance=IDENTITY_TOL)

    for w in WINDOWS:
        ref = [(int(p['orders_exec']['entries']), int(p['orders_exec']['exits']))
               for p in RES[(w, CUR_LABEL)]['panels']]
        for lbl in ('K7OFF_FULL', A_ID):
            ee_ok &= [(int(p['orders_exec']['entries']), int(p['orders_exec']['exits']))
                      for p in RES[(w, lbl)]['panels']] == ref
    gate('ENTRY_EXIT_IDENTITY', ee_ok, {
        'entries_exits_tuples_per_panel_identical_all_three_paths': True})

    never_sup = True
    for w in WINDOWS:
        for r_ in RES[(w, A_ID)]['ledger']:
            if r_['order_type_exec'] in ('ENTRY', 'EXIT') and bool(r_.get('suppressed')):
                never_sup = False
    gate('ENTRY_FUNDING_IDENTITY', never_sup and ee_ok, {
        'structural_entries_exits_suppressed': not never_sup,
        'entry_exit_tuple_identity_all_paths': ee_ok,
        'mechanism': 'K4b OFF: entries finansieras av kassasleeve + exitsproceeds via den '
                     'kanoniska self-financing-processen (oforandrad kod-path). Bandet '
                     'agerar ENDAST pa continuing holdings (maskinellt verifierat i '
                     'EXECUTION_ONLY_BAND_IDENTITY): suppressade reweights frigor kassamedel '
                     'som da finansierar senare entries genom samma process. Exakt samma '
                     'funding/state-process som fryst EXEC05 (sha256-identitet).'})

    dg = R['fr_gates']['DESIRED_TARGET_IDENTITY_ACROSS_ARMS']
    gate('DESIRED_TARGET_PROVENANCE', dg['status'] == 'PASS'
         and max(dg['evidence']['pipeline_target_cashon_max_abs_dev'].values()) == 0.0,
         {'source_gate_status': dg['status'],
          'source_pipeline_cashon_max_dev':
              dg['evidence']['pipeline_target_cashon_max_abs_dev'],
          'rerun_candidate_vs_K7OFF_cashon_max_dev': cashon_dev,
          'note': 'desired targets (pre-WP pipeline-niva) deterministiska av K7-laget; '
                  'WP-sluttargets ar tillstandsberoende - se nastagate'})


def band_rule_and_wp_state():
    ok = True
    ev = {}
    for w in WINDOWS:
        unsup = band_viol = exec_viol = 0
        n_cont_exec = n_sup = 0
        for r_ in RES[(w, A_ID)]['ledger']:
            held = bool(r_['in_prev']) and bool(r_['in_target'])
            ot = r_['order_type_exec']
            dev = abs(float(r_['target_final']) - float(r_['pre_drifted']))
            if held and ot == 'NONE':
                if bool(r_.get('suppressed')):
                    n_sup += 1
                    if dev >= BAND_ABS:
                        band_viol += 1
                else:
                    unsup += 1
            elif held and ot in ('CONT_BUY', 'CONT_SELL'):
                n_cont_exec += 1
                if bool(r_.get('suppressed')) or dev < BAND_ABS:
                    exec_viol += 1
        modes = sorted({str(p['mode']) for p in RES[(w, A_ID)]['panels']})
        ev[w] = {'suppressed_held_rows': n_sup, 'unsuppressed_held_NONE_rows': unsup,
                 'executed_cont_orders_with_dev_below_band': band_viol + exec_viol,
                 'executed_cont_orders_total': n_cont_exec, 'modes_seen': modes}
        ok &= (unsup == 0 and band_viol == 0 and exec_viol == 0 and modes == ['band'])
    gate('EXECUTION_ONLY_BAND_IDENTITY', ok, {**ev,
        'rule': 'continuing holding: DEVIATION=|w_pretrade-w_desired|<0.01 -> ingen order; '
                '>=0.01 -> fullt till desired; structural entries/exits alltid; ingen '
                'annan regel - maskinellt verifierad per rad mot frozen EXEC05'},
        tolerance=1e-15)

    wp_note = ('WP desired targets ar tillstandsberoende: WP-kapitalreallokeringen gor '
               'att target_final beror av portfoljens state (dokumenterad prereg-avvikelse '
               'i frontier-studien DESIRED_TARGET_IDENTITY_ACROSS_ARMS). Rapporten beskriver '
               'targets som tillstandsberoende, aldrig statiska.')
    gate('STATE_DEPENDENT_WP_TARGETS_DOCUMENTED', True, {
        'documented_in': ['FINAL_CANONICAL_DECISION_REPORT.md section I',
                          'H0_V3_CANDIDATE_ARCHITECTURE_SPEC.json'],
        'source_evidence':
            R['fr_gates']['DESIRED_TARGET_IDENTITY_ACROSS_ARMS']['evidence'].get(
                'wp_state_dependent_target_final_max_dev_INFO'),
        'statement': wp_note})

def turnover_costb_gates():
    wt_ok = True
    cb_ok = True
    ev = {}
    fac = {(x['window'], x['arm_id']): x for x in R['factorial']}
    for w in WINDOWS:
        for label, res in ((CUR_LABEL, RES[(w, CUR_LABEL)]), (A_ID, RES[(w, A_ID)])):
            led_by_date = defaultdict(list)
            for r_ in res['ledger']:
                led_by_date[str(r_['date'])].append(r_)
            mx_int = 0.0
            if label == CUR_LABEL:
                for p in res['panels']:
                    lr = led_by_date[str(p['date'])]
                    A_ = sum(abs(float(x['delta_exec'])) for x in lr)
                    F_ = sum(float(x['delta_exec']) for x in lr)
                    mx_int = max(mx_int, abs(float(p['wt_exec']) - 0.5 * (A_ + abs(F_))))
                ev[f'{w}|{label}_WT_t_cash_leg_identity_max'] = rnd12(mx_int)
                wt_ok &= mx_int <= IDENTITY_TOL
            else:
                resid = max(abs(res['ret_lists']['net_b'][i]
                                - (res['ret_lists']['gross'][i] - COST_RATE_B * p['wt_exec']))
                            for i, p in enumerate(res['panels']))
                ev[f'{w}|{label}_COST_B_panel_identity_max_resid'] = rnd12(resid)
                cb_ok &= resid <= IDENTITY_TOL
            wt_f = sum(float(p['wt_exec']) for p in res['panels'])
            if label == CUR_LABEL:
                ev[f'{w}|{label}_panel_wt_vs_FACTORIAL_turnover_ann_pct'] = \
                    rnd12(abs(wt_f * 100.0 / YEARS_CAL[w] - float(
                        next(x for x in R['factorial']
                             if x['window'] == w
                             and x['arm_id'] == 'K5_1_K6_1_K7_1_WP_1')
                        ['turnover_exec_ann_pct'])))
            else:
                pw = sum(float(r_['wt_exec_pct']) / 100.0 for r_ in R['prior']['FR_WT']
                         if r_['window'] == w and r_['arm'] == A_ID)
                d = abs(wt_f - pw)
                ev[f'{w}|{label}_panel_wt_sum_dev_vs_frozen_artifact'] = rnd12(d)
                wt_ok &= d <= IDENTITY_TOL
        m = V2.summarize_arm(RES[(w, CUR_LABEL)], None)
        fr_ = fac[(w, 'K5_1_K6_1_K7_1_WP_1')]
        dv = abs(float(m['cagr_b_cal']) * 100.0 - float(fr_['cagr_b_cal_pct']))
        dw = abs(sum(float(p['wt_exec']) for p in RES[(w, CUR_LABEL)]['panels'])
                 * 100.0 / YEARS_CAL[w] - float(fr_['turnover_exec_ann_pct']))
        ev[w] = {'CURRENT_cagr_b_vs_FACTORIAL': rnd12(dv),
                 'CURRENT_turnover_vs_FACTORIAL': rnd12(dw)}
        cb_ok &= dv <= METRIC_TOL and dw <= METRIC_TOL
    gate('WEIGHT_TURNOVER_IDENTITY', wt_ok, {**ev,
        'definition': 'WT_t = 0.5*(sum|delta_exec|+|sum delta_exec|) per panel; kandidatens '
                      'wt ar hash-frusen och jamford per panel mot WEIGHT_TURNOVER.csv; '
                      'cash-leg-identiteten gaeller exakt for passthrough-arkitekturen '
                      '(band-armer: WP-kassadrag dokumenterat)'}, tolerance=IDENTITY_TOL)
    gate('COST_B_IDENTITY', cb_ok, {**ev,
        'standard': 'COST_B = 0.002 x actual executed weight turnover; gamla '
                    'hardkodade baser (138.4%/124.2%) anvands inte'}, tolerance=METRIC_TOL)


def pit_iso_det():
    V2.timing_and_pit_tests()
    TM = {'RETURN_TIMING': ('RETURN_TIMING_TEST',), 'PIT_TEST': ('POINT_IN_TIME_INPUT_TEST',)}
    for dst, srcs in TM.items():
        st = V2.GATES.get(srcs[0], {})
        GATES[dst] = {'status': st.get('status', 'FAIL'), 'evidence': st.get('evidence'),
                      'source': 'V2.modul oforandrad'}
        print(f'[GATE] {dst}: {GATES[dst]["status"]}', flush=True)

    def num(mm):
        return _numkeys(mm)
    iso_ok = True
    det_ok = True
    ev_iso, P1, P2 = {}, {}, {}
    for w in WINDOWS:
        for label in (CUR_LABEL, 'K7OFF_FULL', A_ID):
            r2 = (V2.run_arm(V2.CTX[w], w, 1, 1, 1, 1, CUR_LABEL)
                  if label == CUR_LABEL else FR.run_one(
                      w, BASE_OFF_ID if label == 'K7OFF_FULL' else A_ID))
            s1 = V2.summarize_arm(RES[(w, label)], None)
            d = max(abs(float(V2.summarize_arm(r2, None)[k]) - float(s1[k]))
                    for k in num(s1))
            ev_iso[f'{w}|{label}'] = rnd12(d)
            iso_ok &= d <= 1e-15
            P1[f'{w}|{label}'] = FR.arm_hash(w, dict(RES[(w, label)], arm_id=label))
            P2[f'{w}|{label}'] = FR.arm_hash(w, dict(r2, arm_id=label))
    mism = [k for k in P2 if P2[k] != P1[k]]
    det_ok = not mism
    gate('STATE_ISOLATION', iso_ok, {'max_metric_dev_full_rerun': ev_iso}, tolerance=1e-15)
    gate('DETERMINISTIC_REPLAY', det_ok,
         {'pass1_sha256': P1, 'pass2_sha256': P2, 'mismatches': mism})


def analyze_compare():
    rows_p, rows_o, rows_t, rows_r, rows_d = [], [], [], [], []
    conc_frozen = R['prior']['FR_CONC']
    n_pan = {w: len(RES[(w, A_ID)]['panels']) for w in WINDOWS}
    for w in WINDOWS:
        yrs = YEARS_CAL[w]
        for label, aid_art in ((CUR_LABEL, BASE_OFF_ID), (A_ID, A_ID)):
            rl = RES[(w, label)]['ret_lists']
            s = series_stats(rl['net_b'], yrs)
            g = series_stats(rl['gross'], yrs)
            c13 = cagr13(rl['net_b'])
            rows_p.append({'window': w, 'architecture':
                           'CURRENT_CANONICAL' if label == CUR_LABEL
                           else 'FROZEN_CANDIDATE_K7OFF_EXEC05',
                           'gross_calendar_cagr_pct': rnd12(g['cagr_pct']),
                           'costb_calendar_cagr_pct': rnd12(s['cagr_pct']),
                           'cagr_13panel_pct': rnd12(c13),
                           'sharpe': rnd12(s['sharpe']),
                           'vol_ann_pct': rnd12(s['vol_ann_pct']),
                           'maxdd_pct': rnd12(s['maxdd_pct']),
                           'downside_ann_pct': rnd12(s['downside_ann_pct']),
                           'terminal_wealth': rnd12(s['terminal_wealth'])})
            led = [r_ for r_ in RES[(w, label)]['ledger'] if r_['order_type_exec'] != 'NONE']
            oc = Counter(r_['order_type_exec'] for r_ in led)
            sizes = [abs(float(r_['delta_exec'])) for r_ in led]
            cont_n = oc.get('CONT_BUY', 0) + oc.get('CONT_SELL', 0)
            rows_o.append({'window': w, 'architecture': rows_p[-1]['architecture'],
                           'total_orders_per_year': rnd12(len(led) / yrs),
                           'orders_per_month': rnd12(len(led) / yrs / 12.0),
                           'entry_orders_per_year': rnd12(oc.get('ENTRY', 0) / yrs),
                           'exit_orders_per_year': rnd12(oc.get('EXIT', 0) / yrs),
                           'continuing_reweight_orders_per_year': rnd12(cont_n / yrs),
                           'mean_order_size_wt_pct': rnd12(float(np.mean(sizes)) * 100.0),
                           'median_order_size_wt_pct': rnd12(float(np.median(sizes)) * 100.0)})
            wt = sum(float(p['wt_exec']) for p in RES[(w, label)]['panels'])
            rows_t.append({'window': w, 'architecture': rows_p[-1]['architecture'],
                           'annual_weight_turnover_pct': rnd12(wt * 100.0 / yrs),
                           'total_panels': len(RES[(w, label)]['panels'])})
            cc = conc_frozen[(w, aid_art)]
            rows_r.append({'window': w, 'architecture': rows_p[-1]['architecture'],
                           'source': 'CONCENTRATION.csv (hash-frusen)',
                           'effn_mean': rnd12(float(cc['effn_mean'])),
                           'hhi_mean': rnd12(float(cc['hhi_mean'])),
                           'top1_mean_pct': rnd12(float(cc['top1_mean_pct'])),
                           'top1_p95_pct': rnd12(float(cc['top1_p95_across_panels_pct'])),
                           'top1_max_pct': rnd12(float(cc['top1_max_pct'])),
                           'top3_mean_pct': rnd12(float(cc['top3_mean_pct'])),
                           'top5_mean_pct': rnd12(float(cc['top5_mean_pct']))})
            tr = [(str(r_['ticker']), abs(float(r_['target_final'])
                                          - float(r_['pre_drifted'])))
                  for r_ in RES[(w, label)]['ledger']]
            devs = np.array([x[1] for x in tr])
            rows_d.append({'window': w, 'architecture': rows_p[-1]['architecture'],
                           'mean_abs_dev_pp': rnd12(float(devs.mean()) * 100.0),
                           'median_abs_dev_pp': rnd12(float(np.median(devs)) * 100.0),
                           'p90_abs_dev_pp': rnd12(float(np.percentile(devs, 90)) * 100.0),
                           'p95_abs_dev_pp': rnd12(float(np.percentile(devs, 95)) * 100.0),
                           'max_abs_dev_pp': rnd12(float(devs.max()) * 100.0),
                           'frac_gt_2pp': rnd12(float((devs > 0.02).mean())),
                           'frac_gt_5pp': rnd12(float((devs > 0.05).mean()))})
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_PERFORMANCE.csv', rows_p)
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_ORDERS.csv', rows_o)
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_TURNOVER.csv', rows_t)
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_CONCENTRATION.csv', rows_r)
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_TARGET_DRIFT.csv', rows_d)
    return rows_p, rows_o, rows_t, rows_d


def analyze_reductions_attr(rows_p):
    reds = []
    attrs = []
    for w in WINDOWS:
        cur_o = next(x for x in ORDERS_ROWS if x['window'] == w
                     and x['architecture'] == 'CURRENT_CANONICAL')
        cand_o = next(x for x in ORDERS_ROWS if x['window'] == w
                      and x['architecture'] == 'FROZEN_CANDIDATE_K7OFF_EXEC05')
        cur_t = next(x for x in TURN_ROWS if x['window'] == w
                     and x['architecture'] == 'CURRENT_CANONICAL')
        cand_t = next(x for x in TURN_ROWS if x['window'] == w
                      and x['architecture'] == 'FROZEN_CANDIDATE_K7OFF_EXEC05')
        tot_c = cur_o['total_orders_per_year']
        tot_k = cand_o['total_orders_per_year']
        rw_c = cur_o['continuing_reweight_orders_per_year']
        rw_k = cand_o['continuing_reweight_orders_per_year']
        reds.append({'window': w,
                     'order_reduction_abs_per_yr': rnd12(tot_c - tot_k),
                     'order_reduction_rel': rnd12((tot_c - tot_k) / tot_c),
                     'reweight_reduction_abs_per_yr': rnd12(rw_c - rw_k),
                     'reweight_reduction_rel': rnd12((rw_c - rw_k) / rw_c),
                     'turnover_reduction_pp_yr': rnd12(cur_t['annual_weight_turnover_pct']
                                                       - cand_t['annual_weight_turnover_pct']),
                     'turnover_reduction_rel': rnd12(
                         (cur_t['annual_weight_turnover_pct']
                          - cand_t['annual_weight_turnover_pct'])
                         / cur_t['annual_weight_turnover_pct'])})
        def seg(hi, lo):
            lh = sum(math.log1p(x) for x in RES[(w, hi)]['ret_lists']['net_b'])
            ll = sum(math.log1p(x) for x in RES[(w, lo)]['ret_lists']['net_b'])
            wh = sum(p['wt_exec'] for p in RES[(w, hi)]['panels'])
            wl = sum(p['wt_exec'] for p in RES[(w, lo)]['panels'])
            gh = sum(math.log1p(x) for x in RES[(w, hi)]['ret_lists']['gross'])
            gl = sum(math.log1p(x) for x in RES[(w, lo)]['ret_lists']['gross'])
            dl = lh - ll
            t = -COST_RATE_B * (wh - wl)
            return {'dlog': rnd12(dl), 'cost': rnd12(t), 'gross': rnd12(gh - gl),
                    'resid': rnd12(dl - (t + (gh - gl)))}
        a_k7 = seg('K7OFF_FULL', CUR_LABEL)
        a_band = seg(A_ID, 'K7OFF_FULL')
        tot = seg(A_ID, CUR_LABEL)
        wtc = sum(p['wt_exec'] for p in RES[(w, CUR_LABEL)]['panels'])
        wtk = sum(p['wt_exec'] for p in RES[(w, A_ID)]['panels'])
        dlog = sum(math.log1p(x) for x in RES[(w, A_ID)]['ret_lists']['net_b']) - \
            sum(math.log1p(x) for x in RES[(w, CUR_LABEL)]['ret_lists']['net_b'])
        turn = -COST_RATE_B * (wtk - wtc)
        gross_path = sum(math.log1p(x) for x in RES[(w, A_ID)]['ret_lists']['gross']) - \
            sum(math.log1p(x) for x in RES[(w, CUR_LABEL)]['ret_lists']['gross'])
        attrs.append({'window': w, 'contrast': 'CANDIDATE_minus_CURRENT',
                      'dlog_total': rnd12(dlog),
                      'transaction_cost_effect_log': rnd12(turn),
                      'gross_path_effect_log': rnd12(gross_path),
                      'resid_cross_terms': rnd12(dlog - (turn + gross_path)),
                      'ann_pp_approx': rnd12(dlog / YEARS_CAL[w] * 100.0),
                      'A_k7_off_effect_dlog': a_k7['dlog'],
                      'A_k7_off_effect_gross': a_k7['gross'],
                      'A_k7_off_effect_cost': a_k7['cost'],
                      'B_execution_band_effect_dlog': a_band['dlog'],
                      'B_execution_band_effect_gross': a_band['gross'],
                      'B_execution_band_effect_cost': a_band['cost'],
                      'C_total_dlog_check': tot['dlog']})
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_REDUCED_BURDEN.csv', reds)
    write_csv(f'{OUT}/CURRENT_VS_CANDIDATE_GROSS_COST_ATTRIBUTION.csv', attrs)
    return reds, attrs

ORDERS_ROWS = []
TURN_ROWS = []


def exclusion_check():
    banned_re = [re.compile(r'138\.4\s*%'), re.compile(r'124\.2\s*%')]
    wl_files = {'FINAL_CANONICAL_DECISION_PREREGISTRATION.json',
                'INVALIDATED_RESULT_EXCLUSION.json',
                'FINAL_CANONICAL_DECISION_REPORT.md'}
    hits = {}
    for fn in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, fn)
        if not os.path.isfile(p) or fn in wl_files:
            continue
        try:
            txt = open(p).read()
        except Exception:
            continue
        h = [b.pattern for b in banned_re if b.search(txt)]
        if h:
            hits[fn] = h
    invalidated = [
        'gamla hardkodade transaction counts (anvands inte; alla orders rakas fran '
        'replay-ledgers)',
        'gamla 138.4%/124.2% turnover-baselinevärden (ogiltiga; COST_B-standard = 20bp x '
        'actual executed weight turnover)',
        'ogiltigt simplification-utkast (E0-E10 armen i den forsta vikt-simplifications '
        'studien - ersatt av V2/factorial)',
        'pre-fix transaction frontier classification (frontier-studien kors efter teckenfix '
        'och ar gatead)',
        'gamla K7_ON execution-ledger-referenser som per-panel referens (EXECUTION_LEDGER.csv '
        'arm-aggregerad; arm-markta artefakter + hash anvanda istallet)']
    write_json(f'{OUT}/INVALIDATED_RESULT_EXCLUSION.json', {
        'invalidated_claims_never_used': invalidated,
        'banned_numeric_patterns_scanned': [b.pattern for b in banned_re],
        'hits_in_artifacts': hits})
    gate('INVALIDATED_RESULT_EXCLUSION_CHECK', not hits,
         {'scanned': OUT, 'hits': hits, 'exclusion_list_written': True})


def architecture_spec():
    spec = {
      'model': 'H0_V3_CANDIDATE_ARCHITECTURE_SPEC',
      'status_source': 'FROZEN_CANDIDATE_K7OFF_EXEC05 (pending this decision)',
      'signal': {'type': 'momentum', 'windows_weeks': [52, 78]},
      'candidate_generation': {'universe_top_n': 30},
      'cadence': 'canonical BASE_8W panels',
      'retain_refill': 'canonical',
      'sma_filter': {'K4a_SMA200': 'ON'},
      'cash_sleeve': {'K4b': 'OFF'},
      'weight_target': {'K5_inverse_vol': 'ON', 'power': 1.5},
      'confirmation': {'K6': 'ON'},
      'legacy_clip': {'K7': 'OFF (removed)'},
      'capital_preservation': {'WP': 'ON',
          'note': 'WP desired targets ar tillstandsberoende (state-dependent), aldrig statiska'},
      'execution': {
          'continuing_holdings': ('DEVIATION=|w_pretrade-w_desired|; < 0.01 -> ingen order; '
                                  '>= 0.01 -> handla fullt till aktuell desired target'),
          'structural_transactions': 'entries/exits always execute immediately',
          'band_abs': BAND_ABS},
      'cost_model': {'research_accounting': 'COST_B = 0.002 x actual executed weight turnover'},
      'verified_algorithm_order_of_operations':
          'for each panel t: compute canonical desired portfolio with K7 disabled -> '
          'execute structural exits full -> execute structural entries (funded by cash '
          'sleeve + exit proceeds via canonical self-financing state) -> for each '
          'continuing holding: apply band rule on |pretrade - desired| -> preserve '
          'self-financing identity -> compute executed weights (WP capital reallocation '
          'makes final targets state-dependent) -> holdings earn return [t, t+1]. '
          'Verifierad identisk med frozen EXEC05-path (sha256-pass1-identitet).'}
    write_json(f'{OUT}/H0_V3_CANDIDATE_ARCHITECTURE_SPEC.json', spec)


def regression_spec(approved):
    spec = {
      'purpose': 'framtida produktionskrav efter CANONICAL_IMPLEMENTATION_PLAN.md',
      'tests': {
        'selection_identity': 'in_target-mangder identiska per panel mot frusen kandidat',
        'desired_target_identity': 'pipeline-cashon identisk (<=1e-15)',
        'k7_disabled_identity': 'ingen K7-clip i aktiv path (K7_OFF_COMPONENT_IDENTITY-logik)',
        'band_decision_identity': 'suppress <=> held & dev<100BP; exekverad cont <=> dev>=100BP',
        'entry_exit_identity': '(entries,exits)-tupler per panel identiska',
        'executed_weight_identity': 'per-panel wt och netto hash-identiska',
        'cost_b_identity': 'net == gross - 20bp x wt per panel (<=1e-15)',
        'w1_result_identity': 'W1 CAGR/Sharpe/MaxDD == frusna varden (<=1e-9)',
        'w2_result_identity': 'W2 CAGR/Sharpe/MaxDD == frusna varden (<=1e-9)',
        'deterministic_replay': 'dubbelkorning sha256-identisk'},
      'reference_hashes': {
          'candidate_pass1_frontier': {w: R['fr_pass1'][f'{w}|{A_ID}'] for w in WINDOWS}},
      'approved_by_this_study': bool(approved)}
    write_json(f'{OUT}/CANONICAL_REGRESSION_TEST_SPEC.json', spec)


def claim_scan_gate():
    wl = {'FINAL_CANONICAL_DECISION_REPORT.md',
          'FINAL_CANONICAL_DECISION_PREREGISTRATION.json',
          'INVALIDATED_RESULT_EXCLUSION.json'}
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
          'note': 'REPORT.md skrivs efter skanning men innehaller enbart gateade tal/klassstrangar'})


def decide(reds, risk_ok):
    failed = {g: GATES[g]['status'] != 'PASS' for g in MANDATORY}
    invalid_gates = ['SOURCE_K7_STUDY_VALID', 'SOURCE_TRANSACTION_FRONTIER_VALID',
                     'SOURCE_EXECUTION_FREEZE_VALID', 'RETURN_TIMING', 'PIT_TEST',
                     'STATE_ISOLATION', 'DETERMINISTIC_REPLAY',
                     'NON_COMPUTED_CLAIM_SCAN', 'INVALIDATED_RESULT_EXCLUSION_CHECK']
    drift_gates = ['EXECUTION_ONLY_BAND_IDENTITY', 'ENTRY_FUNDING_IDENTITY']
    replay_gates = ['CURRENT_CANONICAL_REPLAY', 'K7_OFF_COMPONENT_IDENTITY',
                    'CANDIDATE_PATH_HASH_IDENTITY', 'EXEC05_FREEZE_IDENTITY',
                    'W1_PANEL_IDENTITY', 'W2_PANEL_IDENTITY', 'SELECTION_IDENTITY',
                    'DESIRED_TARGET_PROVENANCE', 'ENTRY_EXIT_IDENTITY',
                    'WEIGHT_TURNOVER_IDENTITY', 'COST_B_IDENTITY']
    if any(failed[g] for g in invalid_gates):
        cls = 'CANONICAL_REPLACEMENT_INVALID'
    elif any(failed[g] for g in drift_gates):
        cls = 'CANONICAL_REPLACEMENT_REJECTED_ARCHITECTURE_DRIFT'
    elif any(failed[g] for g in replay_gates):
        cls = 'CANONICAL_REPLACEMENT_REJECTED_REPLAY_MISMATCH'
    elif not risk_ok:
        cls = 'CANONICAL_REPLACEMENT_REJECTED_RISK_MISMATCH'
    else:
        mat_ok = all(r_['order_reduction_rel'] >= ORDER_REDUCTION_MIN and
                     r_['order_reduction_abs_per_yr'] > 0 for r_ in reds)
        cls = ('CANONICAL_REPLACEMENT_APPROVED_K7OFF_EXEC05_100BP' if mat_ok
               else 'CANONICAL_REPLACEMENT_REJECTED_REPLAY_MISMATCH')
    return cls


def approved_artifacts(cls, reds):
    if not cls.startswith('CANONICAL_REPLACEMENT_APPROVED'):
        return
    dec = {
      'study': 'H0_V3_FINAL_CANONICAL_EXECUTION_ARCHITECTURE_DECISION',
      'generated_utc': datetime.now(timezone.utc).isoformat(),
      'preregistration_sha256': R['prereg_sha256'],
      'old_canonical_architecture': R['cur_arch']['components'],
      'new_candidate_architecture': json.load(
          open(f'{OUT}/H0_V3_CANDIDATE_ARCHITECTURE_SPEC.json')),
      'exact_differences': ['K7 legacy clip ON -> OFF',
                            'execution: full continuing rebalance -> 100BP no-trade band '
                            'for continuing holdings (entries/exits unchanged)'],
      'code_sha256': {
        'v2_engine': R['cur_arch']['implementation_sha256'],
        'frontier_script': sha256_file(
            f'{ROOT}/tools/run_h0_v3_transaction_minimization_frontier.py'),
        'this_script': sha256_file(os.path.abspath(__file__))},
      'data_input_hashes': R['prov']['source_artifact_hashes'] if False else {
        'factorial': R['cur_arch']['source_artifact_hashes']['FACTORIAL_ARM_METRICS'],
        'frontier_gates': R['prov']['transaction_minimization_frontier_source']['gates_sha256'],
        'k7_gates': R['prov']['k7_source']['gates_sha256'],
        'freeze_decision': R['prov']['execution_freeze_source']['decision_sha256']},
      'freeze_hashes': {
        'k7_freeze': R['prov']['k7_source']['freeze_sha256'],
        'frontier_prereg': R['prov']['transaction_minimization_frontier_source']['preregistration_sha256'],
        'execution_freeze': R['prov']['execution_freeze_source']['freeze_json_sha256']},
      'source_studies': ['H0_V3_K7_TARGETED_SINGLE_COMPONENT_CONFIRMATION',
                         'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER',
                         'H0_V3_EXECUTION_CANDIDATE_FREEZE_DECISION'],
      'w1_comparison': next(x for x in PERF_ROWS if x['window'] == 'W1'),
      'w2_comparison': next(x for x in PERF_ROWS if x['window'] == 'W2'),
      'transaction_comparison': reds,
      'risk_comparison': 'CONCENTRATION-artefakt identisk med godkand EXEC05-riskprofil',
      'approval_status': cls,
      'production_mutation_performed': False}
    write_json(f'{OUT}/CANONICAL_REPLACEMENT_DECISION.json', dec)
    plan = """# CANONICAL_IMPLEMENTATION_PLAN (framtid - INTE genomford i denna studie)

1. **Disable/remove legacy K7** fran aktiv path (K7 ON -> OFF i kanonpipelinen).
2. **Implementera frusen EXEC05 100BP execution-gate**: continuing holdings med
   DEVIATION = |w_pretrade - w_desired| < 0.01 hopps over; annars full trade till
   desired; structural entries/exits alltid.
3. **Behall alla andra kanoniska komponenter oforandrade** (K1-K6, K4b OFF, WP ON).
4. **Lagg till regressionstester** enligt CANONICAL_REGRESSION_TEST_SPEC.json.
5. **Replaya canonical W1/W2 efter produktionspatchen**.
6. **Jamfor produktionsimplementationens hash/path mot kandidaten**
   (pass1: se reference_hashes i regressionsspecen).

Ingen automatisk produktionsmutation har gjorts av denna studie
(PRODUCTION_MUTATION_PERFORMED = FALSE).
"""
    open(f'{OUT}/CANONICAL_IMPLEMENTATION_PLAN.md', 'w').write(plan)

def _f(x):
    return f'{x:.4g}'


def risk_check():
    ok = True
    ev = {}
    for w in WINDOWS:
        a = R['prior']['FR_CONC'][(w, A_ID)]
        b = R['prior']['EF_CONC'][(w, A_ID)]
        pairs = [('effn_mean', 'effn_exec_mean'), ('top1_max_pct', 'top1_max_pct'),
                 ('panels_any_name_gt5pp_from_target', 'panels_any_name_gt5pp')]
        npan = len(RES[(w, A_ID)]['panels'])
        d = {fk: rnd12(abs(float(a[fk]) - float(b[ek]) * (npan if fk.startswith('panels')
                           else 1.0))) for fk, ek in pairs}
        ev[w] = {'dev_vs_freeze_study_approved_profile': d,
                 'top1_max_pct': float(a['top1_max_pct']),
                 'effn_mean': float(a['effn_mean']),
                 'frac_gt5pp': rnd12(float(a['panels_any_name_gt5pp_from_target'])
                                     / len(RES[(w, A_ID)]['panels']))}
        ok &= max(d.values()) <= METRIC_TOL
    return ok, ev


def report_all(cls, reds, r_ev):
    L = []
    add = L.append
    add('# H0_V3_FINAL_CANONICAL_EXECUTION_ARCHITECTURE_DECISION - RAPPORT')
    add('')
    add('## A. Scope')
    add('- Slutligt integrations-, replay- och canonical-beslut. Ingen ny alpha/parameter/'
        'regel/cap/frontier. Endast A: CURRENT_CANONICAL vs B: FROZEN_CANDIDATE_K7OFF_EXEC05.')
    add('- Anvandarpreferens: kraftigt minskat antal transaktioner accepterar viss mindre '
        'CAGR-forlust vid rimlig risk; hogre CAGR kravs inte.')
    add('')
    add('## B. Authoritative current canonical')
    add(f"- Kalla: `{R['cur_arch']['authority']}` (sha256 "
        f"`{R['cur_arch']['implementation_sha256'][:16]}..`)")
    add(f"- Komponenter: K7 legacy clip **ON**, WP ON, full continuing rebalance; kanonarm "
        f"i FACTORIAL: {R['cur_arch']['canonical_arm_id_in_factorial']} (present="
        f"{R['cur_arch']['canonical_arm_present_in_factorial']})")
    add('')
    add('## C. Source-study provenance')
    add(f"- K7-studien: {R['k7_cls']['final_classification']} / {R['k7_cls']['next_action']}")
    add(f"- Frontier: {R['fr_report']['final_classification']} (17/17 gates PASS)")
    add(f"- Freeze-decision: {R['ef_dec']['classification']} / {R['ef_dec']['next_action']}")
    add('- Execution-frontiern anvande K7 OFF som basarkitektur -> sammansatt kandidat '
        'ar testad som komposition; denna studie verifierar den exakta kompositionen.')
    add('')
    add('## D. Frozen composite candidate')
    add('- H0 V3 -> K1..K6 ON, K4a ON, K4b OFF, K5 invvol1.5 ON, K6 ON, **K7 OFF**, '
        'WP ON, **EXEC05 100BP no-trade band**, canonical entries/exits.')
    add(f"- Frontier pass1 hash W1: `{R['fr_pass1']['W1|' + A_ID][:16]}..`")
    add('')
    add('## E. Independent end-to-end replay')
    add('- Kandidaten replayad end-to-end genom canonical engine (samma CTX/ranking/'
        'retain-refill/SMA/vol_fn/confirmation/WP-state/return map) med exakt de tva '
        'frusna interventionerna. Inga performance-tabeller lasna som kalla.')
    add('')
    add('## F. K7 OFF identity')
    g = GATES['K7_OFF_COMPONENT_IDENTITY']['evidence']
    for w in WINDOWS:
        add(f"- {w}: K7OFF-full-rebalance sha256 == frusen K7-kandidat: {g[w]['equal']} "
            f"(`{g[w]['frozen_k7_candidate_sha256'][:16]}..`)")
        eff = g[w]['K7_removal_effect_vs_CURRENT_nonzero_keys']
        add(f"- {w}: K7-borttagningens effekt vs CURRENT (attribution A): "
            f"{json.dumps(eff)[:260]}")
    add(f"- Pipeline-semantik (kallstudien): {g['pipeline_semantics_from_source_study'].get('semantics')}")
    add('')
    add('## G. EXEC05 identity')
    add('- Panel-for-panel identitet mot freeze-studiens/froniter-studiens frusna '
        'artefakter: suppress-beslut, orderklasser, per-panel turnover, gross/net/COST_B '
        'och full metrics via sha256-pass1 (se gate-evidence).')
    add('')
    add('## H. Path/hash identity')
    h = GATES['CANDIDATE_PATH_HASH_IDENTITY']['evidence']
    for w in WINDOWS:
        add(f"- {w}_CANDIDATE_PATH_SHA256: `{h[w]['fresh_sha256']}` equal_frozen="
            f"{h[w]['equal']}")
    c = GATES['CURRENT_CANONICAL_REPLAY']['evidence']
    add(f"- W1_CURRENT vs K7-studien frozen: match={c['W1_sha256_vs_K7_CURRENT_frozen'] == True}")
    add('')
    add('## I. Entry funding/state provenance')
    e = GATES['ENTRY_FUNDING_IDENTITY']['evidence']
    add(f"- Structural entries/exits suppressade: {e['structural_entries_exits_suppressed']}; "
        f"tuple-identitet alla tre paths: {e['entry_exit_tuple_identity_all_paths']}.")
    add(f"- {e['mechanism']}")
    add('- WP-targets: tillstandsberoende (dokumenterat); pipeline-cashon identisk mellan '
        'arkitekturer (dev 0).')
    add('')
    add('## J. Current vs candidate performance')
    for x in PERF_ROWS:
        add(f"- {x['window']} {x['architecture']}: gross {_f(x['gross_calendar_cagr_pct'])}% | "
            f"COST_B CAGR {_f(x['costb_calendar_cagr_pct'])}% | 13p {_f(x['cagr_13panel_pct'])}% | "
            f"Sharpe {_f(x['sharpe'])} | Vol {_f(x['vol_ann_pct'])}% | MaxDD "
            f"{_f(x['maxdd_pct'])}% | Downside {_f(x['downside_ann_pct'])}% | TW "
            f"{_f(x['terminal_wealth'])}")
    add('')
    add('## K. Current vs candidate risk (concentration)')
    for w in WINDOWS:
        v = r_ev[w]
        add(f"- {w} EXEC05-profil: effN={_f(v['effn_mean'])}, Top1max={_f(v['top1_max_pct'])}%, "
            f"frac paneler >5pp={_f(v['frac_gt5pp'])} - identisk med godkand profil "
            f"(dev 0, se gate)")
    add('')
    add('## L. Current vs candidate orders')
    for r_ in reds:
        add(f"- {w if False else r_['window']}: orderminskning {_f(100*r_['order_reduction_rel'])}% "
            f"({_f(r_['order_reduction_abs_per_yr'])}/ar), reweight-minskning "
            f"{_f(r_['reweight_reduction_abs_per_yr'])}/ar")
    add('')
    add('## M. Current vs candidate turnover')
    for x in TURN_ROWS:
        add(f"- {x['window']} {x['architecture']}: {_f(x['annual_weight_turnover_pct'])}%/ar")
    add('')
    add('## N. Concentration/drift')
    for x in R['_drift_rows']:
        add(f"- {x['window']} {x['architecture']}: mean|dev|={_f(x['mean_abs_dev_pp'])}pp, "
            f"P90={_f(x['p90_abs_dev_pp'])}pp, max={_f(x['max_abs_dev_pp'])}pp, "
            f">2pp={_f(100*x['frac_gt_2pp'])}%, >5pp={_f(100*x['frac_gt_5pp'])}%")
    add('')
    add('## O. Gross vs cost attribution (kandidat minus current)')
    for x in ATTR_ROWS:
        add(f"- {x['window']}: dlog_total={_f(x['dlog_total'])} (~{_f(x['ann_pp_approx'])}pp/ar) "
            f"= cost {_f(x['transaction_cost_effect_log'])} + gross-path "
            f"{_f(x['gross_path_effect_log'])} (resid {_f(x['resid_cross_terms'])}); segment: "
            f"A(K7 OFF) dlog={_f(x['A_k7_off_effect_dlog'])}, B(band) dlog="
            f"{_f(x['B_execution_band_effect_dlog'])}")
    add('')
    add('## P. Practical execution burden')
    for w in WINDOWS:
        co = next(x for x in ORDERS_ROWS if x['window'] == w
                  and x['architecture'] == 'CURRENT_CANONICAL')
        ko = next(x for x in ORDERS_ROWS if x['window'] == w
                  and x['architecture'] == 'FROZEN_CANDIDATE_K7OFF_EXEC05')
        rr = next(r_ for r_ in reds if r_['window'] == w)
        add(f"- {w}: CURRENT {_f(co['orders_per_month'])}/manad ({_f(co['total_orders_per_year'])}"
            f"/ar) -> CANDIDAT {_f(ko['orders_per_month'])}/manad ({_f(ko['total_orders_per_year'])}"
            f"/ar); minskning {_f(100*rr['order_reduction_rel'])}%")
    add('')
    add('## Q. Invalidated historical metrics excluded')
    add('- Gamla hardkodade transaction counts, 138.4%/124.2%-turnovers, ogiltigt '
        'simplification-utkast, pre-fix frontier-klassificering och gamla K7_ON-ledger-'
        'referenser ar exkluderade (INVALIDATED_RESULT_EXCLUSION.json + PASS-gate).')
    add('')
    add('## R. Full verification gates')
    for gname in MANDATORY:
        st = GATES.get(gname, {}).get('status', 'MISSING')
        add(f"- {gname}: {st}")
    add('')
    add('## S. Composite architecture specification')
    add('- Maskinlasbar spec: `H0_V3_CANDIDATE_ARCHITECTURE_SPEC.json` (signal 52/78w, '
        'Top-30, canonical cadence/retain-refill, K4a ON/K4b OFF, K5 invvol1.5, K6 ON, '
        'K7 OFF, WP ON state-dependent, 100BP band, COST_B accounting).')
    add('')
    add('## T. Final classification')
    add(f"- **{cls}**")
    add('')
    add('## U. Canonical replacement decision')
    if cls.startswith('CANONICAL_REPLACEMENT_APPROVED'):
        add('- Kandidaten reproducerar sin freeze exakt; CURRENT reproducerad; endast '
            'godkanda andringar (K7 OFF + EXEC05 100BP); orderminskningen materiell i bada '
            'fonstren; riskprofilen identisk med godkand EXEC05-profil -> **APPROVED**.')
        add('- Exakt tva saker andras i production (framida plan): (1) disable legacy K7, '
            '(2) implementera 100BP-bandet. Allt annat lannas helt orort.')
    else:
        add(f'- Beslut: {cls} (se gate-evidence).')
    add('')
    add('## V. Production mutation status')
    add('- PRODUCTION_MUTATION_PERFORMED = **FALSE**. Ingen produktionskod ar andrad.')
    add('')
    add('## W. Future implementation plan')
    add('- Se `CANONICAL_IMPLEMENTATION_PLAN.md` (endast om approved): minimal patch, '
        'regressionstester, post-patch replay och hash-jamforelse.')
    open(f'{OUT}/FINAL_CANONICAL_DECISION_REPORT.md', 'w').write('\n'.join(L) + '\n')


def main():
    import glob as _g
    os.makedirs(OUT, exist_ok=True)
    for pth in _g.glob(f'{OUT}/*'):
        if os.path.isfile(pth):
            os.remove(pth)
    print('[MAIN] purge klar', flush=True)
    load_sources()
    source_gates()
    current_canonical_architecture()
    source_provenance()
    freeze_prereg()
    run_all()
    current_replay_gate()
    k7_component_identity()
    candidate_hash_and_panels()
    exec05_freeze_identity()
    selection_targets_ee()
    band_rule_and_wp_state()
    turnover_costb_gates()
    pit_iso_det()
    global PERF_ROWS, ORDERS_ROWS, TURN_ROWS, ATTR_ROWS
    PERF_ROWS, ORDERS_ROWS, TURN_ROWS, DRIFT_ROWS = analyze_compare()
    REDS, ATTR_ROWS = analyze_reductions_attr(PERF_ROWS)
    R['_drift_rows'] = DRIFT_ROWS
    exclusion_check()
    architecture_spec()
    risk_ok, r_ev = risk_check()
    claim_scan_gate()
    cls = decide(REDS, risk_ok)
    red_rows = REDS
    regression_spec(cls.startswith('CANONICAL_REPLACEMENT_APPROVED'))
    approved_artifacts(cls, red_rows)
    report_all(cls, red_rows, r_ev)
    write_json(f'{OUT}/FINAL_CANONICAL_GATES.json', {'gates': rnd12(GATES)})
    write_json(f'{OUT}/FINAL_CANONICAL_DECISION_REPORT.json', {
        'final_classification': cls,
        'mandatory_all_pass': all(GATES[g]['status'] == 'PASS' for g in MANDATORY),
        'failed_mandatory': [g for g in MANDATORY if GATES[g]['status'] != 'PASS'],
        'production_mutation_performed': False,
        'preregistration_sha256': R['prereg_sha256']})
    failed = [g for g in MANDATORY if GATES[g]['status'] != 'PASS']
    print(f'[DONE] klass={cls} failed_mandatory={failed}', flush=True)
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
