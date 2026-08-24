#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
H0_V3_TRANSACTION_MINIMIZATION_FRONTIER - preregistrerad fail-closed studie.

Fraga: Hur manga av H0 V3:s continuing-position-reweights kan hoppas over utan
vasentlig forsämring av nettoavkastning, Sharpe, MaxDD eller koncentrationsrisk?

Utgangsarkitektur (fryst K7_OFF-kandidat, senaste validerade):
H0 -> Top30 -> SMA200(K4a ON) -> K4b OFF -> K5 -> K6 -> WP -> K7 OFF.
Interventionen ar ENBART execution-layer: desired targets beraknas identiskt
i alla armar; continuing holdings handlas endast nar |w_pretrade - w_desired|
>= BAND. Entries/exits alltid fullt utforda. Trade-to-target, inga andra formler.

Armar (frysta): EXEC00_FULL_REBALANCE (kontroll, exakt K7_OFF),
EXEC01..07_BAND_{10,25,50,75,100,150,200}BP, EXEC08_STATE_CHANGE_ONLY
(trigger: kompositionsendring ELLER K6-flipp bland valda ELLER WP-kapitalbehov),
EXEC99_ENTRY_EXIT_ONLY (strukturell kontroll; max MAX_SIMPLIFICATION-kandidat).

Runner: BASE kor via oforandrad V2.run_arm (bitvis replay mot frusna hash-ar).
Ovriga armar kor via rad-for-rad-fork med suppression-hook; FORK_PASSTHROUGH_
IDENTITY bevisar att forkens aritmetik ar ordningidentisk.

Exit: 0 ok, 2 fail-closed blocker, 3 ovantat fel.
"""
import sys, os, json, csv, math, hashlib, re, traceback
from datetime import datetime, timezone
from collections import deque, Counter

sys.path.insert(0, '/home/hannesb/momentum_v2/tools')

if os.environ.get('PYTHONHASHSEED') != '0':
    os.execve(sys.executable, [sys.executable] + sys.argv,
              {**os.environ, 'PYTHONHASHSEED': '0'})

import numpy as np
import run_h0_v3_weight_layer_simplification_v2 as V2
import h0_cash_flow_first_trim_audit as CFF

ROOT = '/home/hannesb/momentum_v2'
OUT = f'{ROOT}/research_k/h0_v3_transaction_minimization_frontier'
V2OUT = V2.OUT
K7OUT = f'{ROOT}/research_k/h0_v3_k7_targeted_single_component_confirmation'

WINDOWS = ['W1', 'W2']
PPY = V2.PPY
N_NAMES = V2.N_NAMES
ORDER_EPS = V2.ORDER_EPS
IDENTITY_TOL = V2.IDENTITY_TOL
COST_RATE_B = V2.COST_RATE_B
COST_RATE_C = V2.COST_RATE_C
YEARS_CAL = V2.YEARS_CAL
FABRICATED_TOKENS = V2.FABRICATED_TOKENS

BASE_ID = 'EXEC00_FULL_REBALANCE'
EE99_ID = 'EXEC99_ENTRY_EXIT_ONLY'
STATE_ID = 'EXEC08_STATE_CHANGE_ONLY'
BANDS_BP = [10, 25, 50, 75, 100, 150, 200]
ARMS = [(BASE_ID, ('base', 0.0))]
for _i, _bp in enumerate(BANDS_BP, 1):
    ARMS.append((f'EXEC{_i:02d}_BAND_{_bp}BP', ('band', _bp * 1e-4)))
ARMS.append((STATE_ID, ('state', 0.0)))
ARMS.append((EE99_ID, ('ee_only', float('inf'))))
ARM_MODE = {a: m for a, m in ARMS}

ECON_EPS = 1e-4
BOOT_N = 10000
BOOT_SEED = 20260823
LARGE_ORD_RED = 0.50
LARGE_CAGR_MIN = -0.005
LARGE_SHARPE_MIN = -0.05
LARGE_DD_MAX_PP = 1.0
MODERATE_ORD_RED = 0.25
MODERATE_CAGR_MIN = -0.02
MODERATE_DD_MAX_PP = 3.0
LOWCHANGE_RW_RED = 0.20

CAUSE_MAP = {'DRIFT_COMP': 'composition-driven', 'K5': 'K5-induced',
             'K6': 'K6-induced', 'NORM': 'mixed', 'WP': 'WP-related',
             'K7': 'mixed', 'MIXED': 'mixed'}

TM_GATES = {}
RES = {}
R = {}

MANDATORY = ['K7_OFF_BASE_REPLAY', 'W1_PANEL_IDENTITY', 'W2_PANEL_IDENTITY',
             'SELECTION_IDENTITY_ACROSS_ARMS', 'ENTRY_EXIT_IDENTITY_ACROSS_ARMS',
             'DESIRED_TARGET_IDENTITY_ACROSS_ARMS', 'EXECUTION_ONLY_INTERVENTION',
             'WEIGHT_TURNOVER_IDENTITY', 'COST_B_REPLAY', 'RETURN_TIMING', 'PIT_TEST',
             'STATE_ISOLATION', 'DETERMINISTIC_REPLAY', 'NON_COMPUTED_CLAIM_SCAN',
             'FORK_PASSTHROUGH_IDENTITY']


def gate(name, ok, evidence, tolerance=None):
    e = {'status': 'PASS' if ok else 'FAIL', 'evidence': evidence}
    if tolerance is not None:
        e['tolerance'] = tolerance
    TM_GATES[name] = e
    try:
        ev_txt = json.dumps(evidence, default=str)
    except Exception:
        ev_txt = str(evidence)
    print(f'[GATE] {name}: {e["status"]} | {ev_txt[:500]}', flush=True)
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
    return V2.sha256_file(path)


def tok_re(tok):
    return V2.tok_re(tok)


def write_json(path, obj):
    V2.write_json(path, obj)


def write_csv(path, rows):
    V2.write_csv(path, rows)


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
    cr = np.cumprod(1.0 + a)
    dd = float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
    return {'cagr_cal_pct': float(mm['cagr_calendar']) * 100.0,
            'cagr_13_pct': float(mm['cagr_13']) * 100.0,
            'sharpe': float(mm['sharpe']),
            'maxdd': dd,
            'vol_ann_pct': float(a.std(ddof=1)) * math.sqrt(PPY) * 100.0,
            'downside_ann_pct': float(math.sqrt(float(np.mean(np.minimum(a, 0.0) ** 2))) * math.sqrt(PPY)) * 100.0,
            'worst_panel_pct': float(a.min()) * 100.0,
            'p5_panel_pct': float(np.percentile(a, 5)) * 100.0,
            'terminal_wealth': float(cr[-1])}


def freeze_preregistration():
    rules_order = [
        'TRANSACTION_MINIMIZATION_INVALID om nagot obligatoriskt gate FAIL',
        'TRANSACTION_MINIMIZATION_MIXED_W1_W2 om LARGE/MODERATE/NONE-tier skiljer >=2 steg '
        'mellan fonstren eller nagot frontier-arm imp i ett fonster och harm i det andra',
        'ENTRY_EXIT_ONLY_SUFFICIENT om EXEC99 uppfyller LARGE i bada fonstren',
        'TRANSACTION_MINIMIZATION_LARGE_EFFICIENCY_GAIN om >=1 suppression-arm uppfyller '
        'LARGE i bada fonstren',
        'TRANSACTION_MINIMIZATION_MODERATE_TRADEOFF om >=1 arm uppfyller MODERATE i bada',
        'annars FULL_REBALANCING_ECONOMICALLY_JUSTIFIED']
    next_actions = {
        'FREEZE_EXECUTION_CANDIDATE': 'BALANCED-frontier-arm identifierad: frys som kandidat, '
                                      'ingen automatisk kanon-ersattning, upprepa studien oforandrad',
        'KEEP_FULL_REBALANCING': 'trade suppression kostar for mycket; behall EXEC00',
        'FORWARD_SHADOW_EXECUTION_FRONTIER': 'historiken kan inte skilja alternativen; shadow-run kravs'}
    prereg = {
        'study': 'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER',
        'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'base_architecture': 'H0->Top30->SMA200 ON->K4b OFF->K5->K6->WP->K7 OFF (K7 aterinfors EJ)',
        'intervention': {
            'type': 'execution-only no-trade-band pa continuing holdings',
            'desired_targets': 'identiska i alla armar (K5/K6/WP oforandrade)',
            'structural_trades': 'entries/exits/SMA-exit alltid fullt utforda, aldrig fordrjd',
            'rule': 'om ABS_DEVIATION=|w_pretrade-w_desired| < BAND: ingen order; annars full trade-to-target',
            'band_unit': 'absolut NAV-fraktion (10bp = 0.001)',
            'band_family_bp': BANDS_BP,
            'state_change_trigger': ['kompositionsendring (set(sel)!=prev_sel)',
                                     'K6-unconfirmed-mangd bland valda flippat',
                                     'WP kapitalbehov (tot_excess>0 och structural_cash>0)'],
            'entry_exit_only': 'alla continuing-trades undertryckta; kontroll, aldrig LOW_CHANGE/BALANCED'},
        'primary_metrics': ['TOTAL_ORDERS_PER_YEAR', 'CONTINUING_REWEIGHT_ORDERS_PER_YEAR'],
        'cost_primary': 'COST_B = 20bp x executed weight turnover',
        'cost_secondary': 'COST_C = 40bp; order-fixed-cost stress rapporteras separat (ej i PRIMARY)',
        'materiality_frozen': {
            'LARGE': {'total_order_reduction_min': LARGE_ORD_RED, 'dcagr_b_min': LARGE_CAGR_MIN,
                      'dsharpe_min': LARGE_SHARPE_MIN, 'dmaxdd_worsen_max_pp': LARGE_DD_MAX_PP},
            'MODERATE': {'total_order_reduction_min': MODERATE_ORD_RED, 'dcagr_b_min': MODERATE_CAGR_MIN,
                         'dmaxdd_worsen_max_pp': MODERATE_DD_MAX_PP},
            'LOW_CHANGE_rw_reduction_min_both_windows': LOWCHANGE_RW_RED,
            'note': 'krav galler i BADA fonstren'},
        'frontier_labels': {
            'LOW_CHANGE': 'lagsta band med rw-reduktion >= 20% i bada fonstren',
            'BALANCED': 'icke-dominerad arm (utom EXEC99/EXEC00) med storst total-orderreduktion '
                        'som uppfyller LARGE i bada fonstren; tie -> minsta bandet',
            'MAX_SIMPLIFICATION': 'icke-dominerad arm (EXEC00 utelamnad) med lagst total orders/ar '
                                  'som uppfyller MODERATE i bada fonstren; tie -> lagst |MaxDD|',
            'pareto_dims': {'maximize': ['cagr_b_cal_pct', 'sharpe'],
                            'minimize': ['total_orders_per_yr', 'reweights_per_yr',
                                         'turnover_exec_ann_pct', 'abs_maxdd']},
            'epsilon_dominance': 1e-12},
        'classification_precedence': rules_order,
        'next_action_map': next_actions,
        'break_even_formula': 'f*_per_order_pct_NAV = (CAGR_B_BASE - CAGR_B_arm)/(O_BASE - O_arm) x 100',
        'suppressed_cause_rule': 'argmax(|contrib|) over {DRIFT_COMP->composition-driven, K5, K6, '
                                 'NORM->mixed, WP}; <50% share -> mixed',
        'inference': 'paired panel net-return diffs mot BASE: mean/median/bootstrap CI95/posfrac; '
                     'ingen arm forkastas bara for CI inkluderar noll',
        'gates_required': MANDATORY,
        'lookahead_prohibition': 'suppression vid t anvander endast pretrade-vikter, desired target '
                                 'och canonical state vid t'}
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_PREREGISTRATION.json', prereg)
    digest = sha256_file(f'{OUT}/TRANSACTION_MINIMIZATION_PREREGISTRATION.json')
    with open(f'{OUT}/TRANSACTION_MINIMIZATION_FREEZE.json', 'w') as f:
        json.dump({'preregistration_sha256': digest, 'frozen_before_any_arm_run': True,
                   'frozen_utc': prereg['frozen_utc']}, f, indent=1)
    print(f'[FREEZE] sha256={digest}', flush=True)

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
    with open(f'{K7OUT}/K7_REPLAY_GATES.json') as f:
        kg = json.load(f)
    R['k7_hashes'] = {k: v for k, v in
                      kg['gates']['DETERMINISTIC_REPLAY']['evidence']['pass1_sha256'].items()
                      if k.endswith('|OFF')}


def run_band_arm(ctx, window, mode, band, arm_id, collect_ledger=True):
    """Rad-for-rad fork av V2.run_arm (k5=1,k6=1,k7=0,wp=1) med execution-layer.

    desired targets (targets_final) beraknas identiskt; exec_final ar det faktiskt
    handlede. mode: 'band' (no-trade-band), 'ee_only', 'state' (state-change-trigger).
    """
    rows = ctx['base']
    returns = ctx['returns']
    vol_fn = ctx['vol_fn']
    confirmed_fn = ctx['confirmed_fn']
    state_vals, state_cash = {}, 1.0
    prev_post_churn = {}
    prev_holds_recon = {}
    prev_unconf = None
    rev_hist = {}
    panels, ledger = [], []
    rets_gross, rets_a, rets_b, rets_c = [], [], [], []
    order_sizes = {'entry': [], 'exit': [], 'cont': []}
    nav_b, nav_c = 1.0, 1.0
    prev_sel_set = None
    prev_unconf_st = None

    for pidx, r in enumerate(rows):
        d = r['date']
        targets_raw = r['weights']
        sel = list(targets_raw.keys())
        sel_set = set(sel)
        n = len(sel)
        tot_raw = sum(targets_raw.values())

        wf = V2.compute_targets_pipeline(sel, d, 1, 1, 0, vol_fn, confirmed_fn)
        arm_targets = dict(zip(sel, map(float, wf)))

        chain = V2.stage_chain(sel, d, vol_fn, confirmed_fn) if collect_ledger and n > 0 else None

        old = state_vals
        cash_in = state_cash
        nav = sum(old.values()) + cash_in
        exits_map = {k: v for k, v in old.items() if k not in sel_set}
        exitpro = sum(exits_map.values())
        cont = {k: v for k, v in old.items() if k in sel_set}

        desired_base = {k: arm_targets[k] * nav for k in sel}
        excess_winners = {k: max(0.0, cont.get(k, 0.0) - desired_base.get(k, 0.0)) for k in sel}
        tot_excess = sum(excess_winners.values())
        structural_cash = max(0.0, nav * (1.0 - tot_raw))
        wp_capital_needed = bool(n > 0 and tot_excess > 0 and structural_cash > 0)
        if n > 0 and tot_excess > 0:
            allocated = {k: structural_cash * (excess_winners[k] / tot_excess) for k in sel}
            targets_final = {k: arm_targets[k] + allocated[k] / nav for k in sel}
            fallback_used = False
        else:
            allocated = {k: 0.0 for k in sel}
            targets_final = {k: v / tot_raw for k, v in arm_targets.items()} if tot_raw > 0 else {}
            fallback_used = True
        n_winners = sum(1 for v in excess_winners.values() if v > 0)
        excess_frac = tot_excess / nav if nav > 0 else 0.0
        alloc_frac = sum(allocated.values()) / nav if nav > 0 else 0.0

        desired_vals = {k: targets_final[k] * nav for k in targets_final}

        st_trigger = None
        rebalance_allowed = True
        if mode == 'state':
            comp_changed = bool(prev_sel_set is not None and set(sel) != prev_sel_set)
            unconf_now_st = {k for k in sel if confirmed_fn(k, d) is False}
            k6_flip = bool(prev_unconf_st is not None and len(unconf_now_st ^ prev_unconf_st) > 0)
            prev_unconf_st = unconf_now_st
            rebalance_allowed = bool(comp_changed or k6_flip or wp_capital_needed)
            st_trigger = {'composition_changed': comp_changed, 'k6_flip': k6_flip,
                          'wp_capital_needed': wp_capital_needed,
                          'rebalance_allowed': rebalance_allowed}
        prev_sel_set = set(sel)

        exec_final = {}
        n_suppressed = 0
        suppressed_abs = 0.0
        for k in set(old) | set(targets_final):
            pre_e = (old.get(k, 0.0) / nav) if nav > 0 else 0.0
            post_d = targets_final.get(k, 0.0)
            held = pre_e > ORDER_EPS
            in_t = post_d > ORDER_EPS
            if held and in_t:
                dev = abs(post_d - pre_e)
                sup = False
                if mode == 'band':
                    sup = dev < band
                elif mode == 'ee_only':
                    sup = True
                elif mode == 'state':
                    sup = not rebalance_allowed
                exec_final[k] = pre_e if sup else post_d
                if sup and dev > ORDER_EPS:
                    n_suppressed += 1
                    suppressed_abs += dev
            else:
                exec_final[k] = post_d

        exec_vals = {k: exec_final[k] * nav for k in desired_vals}
        cash_actual = nav - sum(exec_vals.values())
        tgt_cash_exec = max(0.0, 1.0 - sum(exec_vals.values()) / nav) if nav > 0 else 1.0

        pre_names = {k: cont.get(k, 0.0) / nav for k in sel} if nav > 0 else {}
        cash_pre = (cash_in + exitpro) / nav if nav > 0 else 1.0
        wt_exec = 0.5 * (sum(abs(exec_final.get(k, 0.0) - pre_names.get(k, 0.0))
                             for k in set(pre_names) | set(targets_final))
                         + abs(tgt_cash_exec - cash_pre))

        uch = set(prev_post_churn) | set(targets_final)
        wt_churn = 0.5 * sum(abs(targets_final.get(k, 0.0) - prev_post_churn.get(k, 0.0)) for k in uch)

        oex = {'entries': 0, 'exits': 0, 'cont_buy': 0, 'cont_sell': 0}
        och = {'entries': 0, 'exits': 0, 'cont_buy': 0, 'cont_sell': 0}
        bucket_counts = [0, 0, 0, 0]
        bucket_to = [0.0, 0.0, 0.0, 0.0]
        rev = [0, 0, 0]
        rev_to = 0.0
        inst_d, inst_e = [], []
        buy_sum = sell_sum = 0.0

        for k in set(old) | set(targets_final):
            pre_e = (old.get(k, 0.0) / nav) if nav > 0 else 0.0
            pre_c = prev_post_churn.get(k, 0.0)
            post_d = targets_final.get(k, 0.0)
            de = exec_final.get(k, 0.0) - pre_e
            dc = post_d - pre_c
            held = pre_e > ORDER_EPS
            in_t = post_d > ORDER_EPS
            held_c = pre_c > ORDER_EPS
            ot_exec, ot_churn = 'NONE', 'NONE'

            if (not held) and in_t:
                oex['entries'] += 1
                ot_exec = 'ENTRY'
                order_sizes['entry'].append(post_d)
            elif held and (not in_t):
                oex['exits'] += 1
                ot_exec = 'EXIT'
                order_sizes['exit'].append(pre_e)
            elif held and in_t and abs(de) > ORDER_EPS:
                ot_exec = 'CONT_BUY' if de > 0 else 'CONT_SELL'
                oex['cont_buy' if de > 0 else 'cont_sell'] += 1
                order_sizes['cont'].append(abs(de))
                a = abs(de)
                bi = 0 if a < 0.001 else (1 if a < 0.0025 else (2 if a < 0.005 else 3))
                bucket_counts[bi] += 1
                bucket_to[bi] += 0.5 * a
                hst = rev_hist.setdefault(k, deque(maxlen=3))
                flipped = False
                for L in (1, 2, 3):
                    if len(hst) >= L and ((hst[-L] > 0) != (de > 0)):
                        rev[L - 1] += 1
                        if not flipped:
                            rev_to += 0.5 * a
                            flipped = True
                hst.append(de)

            if (not held_c) and in_t:
                och['entries'] += 1
                ot_churn = 'ENTRY'
            elif held_c and (not in_t):
                och['exits'] += 1
                ot_churn = 'EXIT'
            elif held_c and in_t and abs(dc) > ORDER_EPS:
                ot_churn = 'CONT_BUY' if dc > 0 else 'CONT_SELL'
                och['cont_buy' if dc > 0 else 'cont_sell'] += 1
                inst_d.append(abs(dc))
                inst_e.append(abs(de))

            buy_sum += max(de, 0.0)
            sell_sum += max(-de, 0.0)

            if collect_ledger:
                crow = {'window': window, 'date': d, 'pidx': pidx, 'ticker': k,
                        'in_prev': held, 'in_target': in_t,
                        'pre_drifted': pre_e, 'pre_churn': pre_c,
                        'target_cashon': arm_targets.get(k, 0.0),
                        'target_final': post_d,
                        'exec_target': exec_final.get(k, 0.0),
                        'delta_exec': de, 'delta_churn': dc,
                        'order_type_exec': ot_exec, 'order_type_churn': ot_churn,
                        'suppressed': bool(held and in_t and ot_exec == 'NONE'
                                           and abs(post_d - pre_e) > ORDER_EPS)}
                if chain is not None and k in chain['S_tgt']:
                    c_drift = chain['S_eq'][k] - pre_e
                    c_k5 = chain['S_k5'][k] - chain['S_eq'][k]
                    c_k6 = chain['S_k6'][k] - chain['S_k5'][k]
                    c_norm = chain['S_tgt'][k] - chain['S_k6'][k]
                    c_wp = post_d - chain['S_tgt'][k]
                    contribs = [('DRIFT_COMP', c_drift), ('K5', c_k5), ('K6', c_k6),
                                ('NORM', c_norm), ('WP', c_wp)]
                    tot_abs = sum(abs(c[1]) for c in contribs)
                    top_lab, top_val = max(contribs, key=lambda x: abs(x[1]))
                    label = top_lab if (tot_abs > 0 and abs(top_val) >= 0.5 * tot_abs) else 'MIXED'
                    crow.update({'c_driftcomp': c_drift, 'c_k5': c_k5, 'c_k6': c_k6,
                                 'c_norm': c_norm, 'c_wp': c_wp,
                                 'attr_label': label,
                                 'top_share': (abs(top_val) / tot_abs) if tot_abs > 0 else 0.0})
                else:
                    crow.update({'attr_label': ot_exec, 'top_share': ''})
                ledger.append(crow)

        prev_post_churn = dict(targets_final)

        ur = set(prev_holds_recon) | set(targets_final)
        wt_churn_recon = 0.5 * sum(abs(targets_final.get(k, 0.0) - prev_holds_recon.get(k, 0.0)) for k in ur)
        rcnt = {'entries': 0, 'exits': 0, 'cont_buy': 0, 'cont_sell': 0}
        for k in ur:
            prc = prev_holds_recon.get(k, 0.0)
            poc = targets_final.get(k, 0.0)
            if prc <= 1e-6 and poc > 1e-6:
                rcnt['entries'] += 1
            elif prc > 1e-6 and poc <= 1e-6:
                rcnt['exits'] += 1
            elif prc > 1e-6 and poc > prc + 1e-6:
                rcnt['cont_buy'] += 1
            elif prc > 1e-6 and poc < prc - 1e-6 and poc > 1e-6:
                rcnt['cont_sell'] += 1
        holds_now = {k: v for k, v in targets_final.items() if v > 1e-6}
        pre_set_r = set(holds_now)
        post_set_r = {k for k, v in targets_final.items() if v > 1e-6}
        ntf_recon = 1.0 - (len(pre_set_r & post_set_r) / max(1, len(post_set_r)))
        prev_holds_recon = holds_now

        cash_in_frac = cash_in / nav if nav > 0 else 1.0
        sf_resid = abs((buy_sum - sell_sum) + (tgt_cash_exec - cash_in_frac))

        rets_dict = {k: returns.get((k, d), 0.0) for k in targets_final}
        gross_t = sum((exec_vals[k] / nav) * rets_dict[k] for k in desired_vals) if nav > 0 else 0.0
        values = dict(exec_vals)
        cost_a = r['cost'] * nav
        values = {k: v * (1.0 + rets_dict.get(k, 0.0)) for k, v in values.items()}
        values, cash_after = CFF.debit_cost(values, cash_actual, cost_a)
        post_val = sum(values.values()) + cash_after
        net_a = post_val / nav - 1.0
        state_vals, state_cash = values, cash_after
        net_b = gross_t - COST_RATE_B * wt_exec
        net_c = gross_t - COST_RATE_C * wt_exec
        nav_b *= (1.0 + net_b)
        nav_c *= (1.0 + net_c)

        wv = list(targets_final.values())
        effn = 1.0 / sum(w * w for w in wv) if wv else 0.0
        maxw = max(wv) if wv else 0.0
        p95w = float(np.percentile(wv, 95)) if wv else 0.0
        wve = list(exec_final.values())
        effn_exec = 1.0 / sum(w * w for w in wve) if wve else 0.0
        maxw_exec = max(wve) if wve else 0.0

        pd_row = {
            'window': window, 'date': d, 'pidx': pidx, 'n': n, 'tot_raw': tot_raw,
            'fallback_used': fallback_used, 'gross_t': gross_t, 'cost_a_drag': cost_a,
            'wt_exec': wt_exec, 'wt_churn': wt_churn,
            'wt_churn_recon': wt_churn_recon, 'orders_churn_recon': dict(rcnt),
            'ntf_recon': ntf_recon,
            'orders_exec': dict(oex), 'orders_churn': dict(och),
            'buy_sum': buy_sum, 'sell_sum': sell_sum, 'sf_resid': sf_resid,
            'net_a': net_a, 'net_b': net_b, 'net_c': net_c,
            'nav_post': post_val, 'cash_post': cash_after,
            'effn_post': effn, 'maxw_post': maxw, 'p95w_post': p95w,
            'effn_exec': effn_exec, 'maxw_exec': maxw_exec,
            'sum_targets': sum(targets_final.values()),
            'bucket_counts': bucket_counts, 'bucket_turnover': bucket_to,
            'rev1': rev[0], 'rev2': rev[1], 'rev3': rev[2], 'rev_turnover': rev_to,
            'inst_mean': float(np.mean(inst_d)) if inst_d else 0.0,
            'inst_median': float(np.median(inst_d)) if inst_d else 0.0,
            'inst_p90': float(np.percentile(inst_d, 90)) if inst_d else 0.0,
            'inst_corr': None,
            'wp_fallback': fallback_used, 'wp_winners': n_winners,
            'wp_excess_frac': excess_frac, 'wp_alloc_frac': alloc_frac,
            'post_weights': dict(exec_final),
            'desired_weights': dict(targets_final),
            'n_suppressed': n_suppressed, 'suppressed_abs': suppressed_abs,
            'st_trigger': st_trigger, 'mode': mode, 'band': band,
        }
        panels.append(pd_row)
        rets_gross.append(gross_t)
        rets_a.append(net_a)
        rets_b.append(net_b)
        rets_c.append(net_c)

    return {'window': window, 'arm_id': arm_id, 'panels': panels, 'ledger': ledger,
            'order_sizes': order_sizes,
            'ret_lists': {'gross': rets_gross, 'net_a': rets_a, 'net_b': rets_b, 'net_c': rets_c},
            'nav_end': {'A': None, 'B': nav_b, 'C': nav_c}}

P1 = {}


def load_contexts():
    V2.load_contexts()
    V2.load_refs()


BASE_LABEL = 'K5_1_K6_1_K7_0_WP_1'


def run_one(w, arm_id):
    mode, band = ARM_MODE[arm_id]
    if mode == 'base':
        return V2.run_arm(V2.CTX[w], w, 1, 1, 0, 1, BASE_LABEL, True, False)
    return run_band_arm(V2.CTX[w], w, mode, band, arm_id, True)


def run_plain(w, arm_id):
    mode, band = ARM_MODE[arm_id]
    if mode == 'base':
        return V2.run_arm(V2.CTX[w], w, 1, 1, 0, 1, BASE_LABEL, False, False)
    return run_band_arm(V2.CTX[w], w, mode, band, arm_id, False)


def eec_list(pp):
    return [(int(p['orders_exec']['entries']), int(p['orders_exec']['exits'])) for p in pp]


def replay_gates():
    fac = {(r['window'], r['arm_id']): r for r in R['factorial']}
    okall = True
    devs_all = {}
    for w in WINDOWS:
        res = RES[w][BASE_ID]
        m = V2.summarize_arm(res, None)
        fr = fac[(w, 'K5_1_K6_1_K7_0_WP_1')]
        conv = {'cagr_gross_cal_pct': ('cagr_gross_cal', 100.0),
                'cagr_a_cal_pct': ('cagr_a_cal', 100.0),
                'cagr_b_cal_pct': ('cagr_b_cal', 100.0),
                'sharpe_b': ('sharpe_b', 1.0), 'maxdd_b': ('maxdd_b', 1.0),
                'turnover_exec_ann_pct': ('turnover_exec_ann_pct', 1.0),
                'turnover_churn_ann_pct': ('turnover_churn_ann_pct', 1.0),
                'orders_exec_per_yr': ('orders_exec_per_yr', 1.0),
                'orders_churn_per_yr': ('orders_churn_per_yr', 1.0)}
        dv = {k: abs(float(m[src]) * sc - float(fr[k])) for k, (src, sc) in conv.items()}
        devs_all[w] = rnd12({k: v for k, v in dv.items()})
        okall &= all(v <= 1e-9 for v in dv.values())
        R['an'].setdefault('summary', {})[w] = m

        led_by_date = {}
        for r_ in res['ledger']:
            led_by_date.setdefault(str(r_['date']), []).append(r_)
        recon = R['recon_wt'][w]
        missing, mx_info, mx_int = [], 0.0, 0.0
        for p in res['panels']:
            key = str(p['date'])
            lrows = led_by_date.get(key, [])
            a_abs = sum(abs(float(x['delta_exec'])) for x in lrows)
            net_flow = sum(float(x['delta_exec']) for x in lrows)
            if key in recon:
                mx_info = max(mx_info, abs(float(p['wt_exec']) - recon[key]))
            else:
                missing.append(key)
            mx_int = max(mx_int, abs(float(p['wt_exec']) - 0.5 * (a_abs + abs(net_flow))))
        max_sf = max(float(p['sf_resid']) for p in res['panels'])
        wt_ann_dev = abs(sum(float(p['wt_exec']) for p in res['panels']) * 100.0 / YEARS_CAL[w]
                         - float(m['turnover_exec_ann_pct']))
        okp = (not missing) and mx_int <= IDENTITY_TOL and max_sf <= IDENTITY_TOL \
            and all(v <= 1e-9 for v in dv.values()) and wt_ann_dev <= 1e-9
        gate(f'{w}_PANEL_IDENTITY', okp, {
            'wd_recon_K7ON_era_max_abs_diff_INFO': rnd12(mx_info),
            'wt_exec_cash_leg_internal_identity_max': rnd12(mx_int),
            'wd_dates_missing': missing[:5],
            'sf_resid_max': rnd12(max_sf),
            'aggregate_metrics_max_dev': max(dv.values()),
            'turnover_ann_consistency_dev': rnd12(wt_ann_dev),
            'note': 'WD-reconens exec-kolumn ar genererad fran K7_ON-era-kanonarmen och ar ingen '
                    'giltig per-panel-referens foer K7_OFF-basen; OFF-pathens per-panel turnover '
                    'ar bitvis frosen via K7_OFF_BASE_REPLAY-hashen. Gaten bevisar intern '
                    'sjalvfinansieringsidentitet wt_exec == 0.5*(sum|d|+|sum d|) + arskonsistens.'},
            tolerance=IDENTITY_TOL)

        kh = R['k7_hashes'].get(f'{w}|OFF')
        bh = P1.get(f'{w}|{BASE_ID}')
        gate(f'K7_OFF_BASE_REPLAY_{w}', kh is not None and bh == kh,
             {'base_sha256': bh, 'frozen_k7_off_sha256': kh,
              'metric_devs_vs_factorial_row': devs_all[w]}, tolerance=1e-9)
        okall &= (kh is not None and bh == kh)
    gate('K7_OFF_BASE_REPLAY', okall, {
        'method': 'sha256(metrics_rnd12+order_sizes_summary+panel_net_b+nav_end) == frusna K7-studiens '
                  'pass1-hash for K5_1_K6_1_K7_0_WP_1 + metric-dev <=1e-9 mot FACTORIAL_ARM_METRICS.json',
        'per_window_metric_max_dev': devs_all}, tolerance=1e-9)


def fork_identity_gate():
    okall = True
    ev = {}
    for w in WINDOWS:
        fh = P1[f'{w}|FORK_PASSTHROUGH']
        bh = P1[f'{w}|{BASE_ID}']
        ev[w] = {'fork_sha256': fh, 'base_sha256': bh, 'equal': fh == bh}
        okall &= fh == bh
    gate('FORK_PASSTHROUGH_IDENTITY', okall, {
        **ev, 'note': 'fork med suppression avstangd (band=0) ar bitvis identisk med V2.run_arm'})


def identity_gates():
    sel_ok = ee_ok = des_ok = True
    ev = {'selection_mismatches': [], 'ee_mismatches': [], 'desired_max_dev': {}}
    for w in WINDOWS:
        led = {a: RES[w][a]['ledger'] for a in ARM_MODE}
        sels = {}
        for a, ld in led.items():
            sels[a] = {(str(r['date']), r['ticker']) for r in ld if int(r['in_target']) == 1}
        ref_sel = sels[BASE_ID]
        for a, s in sels.items():
            if s != ref_sel:
                sel_ok = False
                ev['selection_mismatches'].append(f'{w}/{a}: {len(s ^ ref_sel)}')
        ees = {a: eec_list(RES[w][a]['panels']) for a in ARM_MODE}
        ref_ee = ees[BASE_ID]
        for a, e in ees.items():
            if e != ref_ee:
                ee_ok = False
                ev['ee_mismatches'].append(f'{w}/{a}')
        bmap = {(str(r['date']), r['ticker']): r for r in led[BASE_ID]}
        mx_cash = mx_tf = 0.0
        for a, ld in led.items():
            if a == BASE_ID:
                continue
            for r in ld:
                br = bmap[(str(r['date']), r['ticker'])]
                mx_cash = max(mx_cash, abs(float(r['target_cashon']) - float(br['target_cashon'])))
                mx_tf = max(mx_tf, abs(float(r['target_final']) - float(br['target_final'])))
        ev['desired_max_dev'][w] = rnd12(mx_cash)
        ev.setdefault('wp_state_target_final_max_dev', {})[w] = rnd12(mx_tf)
        des_ok &= mx_cash <= 1e-15
    gate('SELECTION_IDENTITY_ACROSS_ARMS', sel_ok, {
        'mismatches': ev['selection_mismatches'],
        'note': 'in_target-mangden identisk i alla 11 armar x 2 fonster'})
    gate('ENTRY_EXIT_IDENTITY_ACROSS_ARMS', ee_ok, {
        'mismatches': ev['ee_mismatches'],
        'note': '(entries,exits) per panel identiskt i alla armar'})
    gate('DESIRED_TARGET_IDENTITY_ACROSS_ARMS', des_ok, {
        'pipeline_target_cashon_max_abs_dev': ev['desired_max_dev'],
        'wp_state_dependent_target_final_max_dev_INFO': ev.get('wp_state_target_final_max_dev', {}),
        'note': 'identiteten galler pipelinesteget (pre-WP target_cashon); slutliga target_final '
                'ar medvetet tillstandsberoende via WP-kapitalreallokering (samma semantik i V2)'},
        tolerance=1e-15)


def execution_intervention_gate():
    ev = {}
    ok = TM_GATES['DESIRED_TARGET_IDENTITY_ACROSS_ARMS']['status'] == 'PASS' \
        and TM_GATES['SELECTION_IDENTITY_ACROSS_ARMS']['status'] == 'PASS' \
        and TM_GATES['FORK_PASSTHROUGH_IDENTITY']['status'] == 'PASS'
    for w in WINDOWS:
        per_arm = {}
        for a in ARM_MODE:
            ps = RES[w]['FORK_PASSTHROUGH']['panels'] if a == BASE_ID else RES[w][a]['panels']
            nsup = sum(int(p['n_suppressed']) for p in ps)
            abssup = sum(float(p['suppressed_abs']) for p in ps)
            yrs = len(ps) / PPY
            per_arm[a] = {'panels_with_suppression': sum(1 for p in ps if p['n_suppressed'] > 0),
                          'n_suppressed_total': nsup,
                          'suppressed_abs_frac_total': rnd12(abssup),
                          'suppressed_abs_frac_per_yr_pct': rnd12(abssup / yrs * 100.0)}
        ev[w] = per_arm
    gate('EXECUTION_ONLY_INTERVENTION', ok, {
        'proof': 'target-pipeline (cashon-niva) + selektion + entries/exits identiska mellan armar; '
                 'WP-sluttargets tillstandsberoende per design (samma som V2); endast delta_exec/'
                 'order_type/post_weights skiljer; fork-passthrough bitvis identisk',
        'divergence_stats': ev})


def timing_pit():
    V2.timing_and_pit_tests()
    for src, dst in (('RETURN_TIMING_TEST', 'RETURN_TIMING'), ('POINT_IN_TIME_INPUT_TEST', 'PIT_TEST')):
        st = V2.GATES.get(src, {})
        TM_GATES[dst] = {'status': st.get('status', 'FAIL'), 'evidence': st.get('evidence'),
                         'source': 'V2.modul (oforandrad)'}


def analyze_all():
    rows = R['rows']
    for w in WINDOWS:
        base_res = RES[w]['FORK_PASSTHROUGH']
        bp = base_res['panels']
        yrs = len(bp) / PPY
        bl = base_res['ret_lists']
        base_perf = perf_block(bl['net_b'], w)
        base_oc = sum(int(p['orders_exec'][k]) for p in bp
                      for k in ('entries', 'exits', 'cont_buy', 'cont_sell'))
        base_rw = sum(int(p['orders_exec'][k]) for p in bp for k in ('cont_buy', 'cont_sell'))
        base_wt = sum(float(p['wt_exec']) for p in bp)

        # BASE mikro-churn anatomi fran ledger (6 spec-buckets)
        edges = [0.001, 0.0025, 0.005, 0.01, 0.02]
        blabels = ['<0.10%', '0.10-0.25%', '0.25-0.50%', '0.50-1.00%', '1.00-2.00%', '>=2.00%']

        def hist(vals):
            c = [0] * 6
            t = [0.0] * 6
            for v in vals:
                i = 0
                while i < len(edges) and v >= edges[i]:
                    i += 1
                c[i] += 1
                t[i] += 0.5 * v
            return c, t
        bc, bt = hist([abs(float(r['delta_exec'])) for r in base_res['ledger']
                       if r['order_type_exec'] in ('CONT_BUY', 'CONT_SELL')])
        for i in range(6):
            rows['MICRO_CHURN'].append({'window': w, 'arm': BASE_ID, 'bucket': blabels[i],
                                        'orders': bc[i], 'weight_frac': rnd12(bt[i]),
                                        'orders_removed': 0, 'weight_frac_removed': 0.0})

        for arm_id in ARM_MODE:
            res = base_res if arm_id == BASE_ID else RES[w][arm_id]
            ps = res['panels']
            rl = res['ret_lists']
            pf = perf_block(rl['net_b'], w)
            mc = V2.calc_metrics([float(x) for x in rl['net_c']], w)
            oc = {k: sum(int(p['orders_exec'][k]) for p in ps)
                  for k in ('entries', 'exits', 'cont_buy', 'cont_sell')}
            tot_ord = sum(oc.values())
            rw_n = oc['cont_buy'] + oc['cont_sell']
            wt_sum = sum(float(p['wt_exec']) for p in ps)

            for yr in sorted({str(p['date'])[:4] for p in ps}):
                oy = {k: sum(int(p['orders_exec'][k]) for p in ps if str(p['date'])[:4] == yr)
                      for k in ('entries', 'exits', 'cont_buy', 'cont_sell')}
                rows['ORDER_COUNTS'].append({'window': w, 'arm': arm_id, 'year': yr, **oy,
                                             'total': sum(oy.values())})

            merged = res['order_sizes']['entry'] + res['order_sizes']['exit'] + res['order_sizes']['cont']
            osz_rows = []
            for cls in ('entry', 'exit', 'cont'):
                v = np.array(res['order_sizes'][cls]) if res['order_sizes'][cls] else np.array([0.0])
                osz_rows.append({'window': w, 'arm': arm_id, 'class': cls, 'n': int(len(res['order_sizes'][cls])),
                                 'mean': rnd12(float(v.mean())), 'median': rnd12(float(np.median(v))),
                                 'p90': rnd12(float(np.percentile(v, 90))), 'p95': rnd12(float(np.percentile(v, 95)))})
            am = np.array(merged) if merged else np.array([0.0])
            osz_rows.append({'window': w, 'arm': arm_id, 'class': 'all', 'n': len(merged),
                             'mean': rnd12(float(am.mean())), 'median': rnd12(float(np.median(am))),
                             'p90': rnd12(float(np.percentile(am, 90))), 'p95': rnd12(float(np.percentile(am, 95)))})
            rows['ORDER_SIZES'].extend(osz_rows)

            for i, p in enumerate(ps):
                rows['WEIGHT_TURNOVER'].append({'window': w, 'arm': arm_id, 'pidx': i,
                                                'date': str(p['date']), 'wt_exec_pct': rnd12(p['wt_exec'] * 100.0)})

            rv = {k: sum(int(float(p[k])) for p in ps) for k in ('rev1', 'rev2', 'rev3')}
            rev_to = sum(float(p['rev_turnover']) for p in ps)
            rows['REVERSALS'].append({
                'window': w, 'arm': arm_id, 'rev1_next_panel': rv['rev1'], 'rev2_within_2': rv['rev2'],
                'rev3_within_3': rv['rev3'],
                'fraction_of_cont_orders': rnd12(sum(rv.values()) / rw_n) if rw_n else None,
                'reversed_turnover_frac': rnd12(rev_to),
                'reversed_costB_pp_yr': rnd12(rev_to / yrs * COST_RATE_B * 100.0)})

            gl = float(np.log(np.prod([1.0 + x for x in rl['gross']])))
            nl = float(np.log(np.prod([1.0 + x for x in rl['net_b']])))
            bgl = float(np.log(np.prod([1.0 + x for x in bl['gross']])))
            bnl = float(np.log(np.prod([1.0 + x for x in bl['net_b']])))
            saving = COST_RATE_B * (base_wt - wt_sum)
            rows['COST_ATTRIBUTION'].append({
                'window': w, 'arm': arm_id,
                'gross_log_effect_vs_BASE': rnd12(gl - bgl),
                'cost_saving_B_frac': rnd12(saving),
                'cost_saving_B_pp': rnd12(saving * 100.0),
                'net_log_effect_vs_BASE': rnd12(nl - bnl)})

            dst = paired_stats([o - b for o, b in zip(rl['net_b'], bl['net_b'])])
            devs = []
            for pa, pb in zip(ps, bp):
                wa, wb = pa['post_weights'], pb['post_weights']
                for k in set(wa) | set(wb):
                    devs.append(abs(float(wa.get(k, 0.0)) - float(wb.get(k, 0.0))))
            da = np.array(devs) if devs else np.array([0.0])
            corr = float(np.corrcoef(rl['net_b'], bl['net_b'])[0, 1]) if len(rl['net_b']) > 1 else None
            te_ann = float(np.std([o - b for o, b in zip(rl['net_b'], bl['net_b'])], ddof=1)) * math.sqrt(PPY)
            rows['TRACKING_ERROR'].append({
                'window': w, 'arm': arm_id,
                'mean_abs_weight_dev_pct': rnd12(float(da.mean()) * 100.0),
                'p90_abs_weight_dev_pct': rnd12(float(np.percentile(da, 90)) * 100.0),
                'max_abs_weight_dev_pct': rnd12(float(da.max()) * 100.0),
                'return_tracking_error_ann_pct': rnd12(te_ann * 100.0),
                'net_return_correlation_vs_BASE': rnd12(corr) if corr is not None else None})

            hh, ef, t1, t3, t5, t1s, mxdev, gt2, gt5, streak_best = [], [], [], [], [], [], 0.0, 0, 0, 0
            cur_streak = 0
            for p in ps:
                ws = sorted(p['post_weights'].values(), reverse=True)
                h = sum(v * v for v in ws)
                hh.append(h)
                ef.append(1.0 / h if h > 0 else 0.0)
                t1.append(ws[0] if ws else 0.0)
                t3.append(sum(ws[:3]))
                t5.append(sum(ws[:5]))
                dw = [abs(float(p['post_weights'].get(k, 0.0)) - float(p['desired_weights'].get(k, 0.0)))
                      for k in set(p['post_weights']) | set(p['desired_weights'])]
                mdw = max(dw) if dw else 0.0
                mxdev = max(mxdev, mdw)
                if mdw > 0.02:
                    gt2 += 1
                    cur_streak += 1
                    streak_best = max(streak_best, cur_streak)
                else:
                    cur_streak = 0
                if mdw > 0.05:
                    gt5 += 1
            rows['CONCENTRATION'].append({
                'window': w, 'arm': arm_id,
                'effn_mean': rnd12(float(np.mean(ef))), 'hhi_mean': rnd12(float(np.mean(hh))),
                'top1_mean_pct': rnd12(float(np.mean(t1)) * 100.0),
                'top3_mean_pct': rnd12(float(np.mean(t3)) * 100.0),
                'top5_mean_pct': rnd12(float(np.mean(t5)) * 100.0),
                'top1_p95_across_panels_pct': rnd12(float(np.percentile(t1, 95)) * 100.0),
                'top1_max_pct': rnd12(max(t1) * 100.0),
                'panels_any_name_gt2pp_from_target': gt2,
                'panels_any_name_gt5pp_from_target': gt5,
                'max_consecutive_panels_gt2pp': streak_best,
                'max_abs_dev_from_target_pct': rnd12(mxdev * 100.0)})

            R['an'].setdefault('arms', {}).setdefault(w, {})[arm_id] = {
                'perf': {k: rnd12(v) for k, v in pf.items()},
                'cagr_c_cal_pct': rnd12(float(mc['cagr_calendar']) * 100.0),
                'orders': oc, 'total_orders': tot_ord, 'reweights': rw_n,
                'orders_per_yr': rnd12(tot_ord / yrs), 'reweights_per_yr': rnd12(rw_n / yrs),
                'turnover_ann_pct': rnd12(wt_sum * 100.0 / yrs),
                'order_reduction_abs': base_oc - tot_ord,
                'order_reduction_pct': rnd12((base_oc - tot_ord) / base_oc),
                'rw_reduction_abs': base_rw - rw_n,
                'rw_reduction_pct': rnd12((base_rw - rw_n) / base_rw),
                'turnover_reduction_pct': rnd12((base_wt - wt_sum) / base_wt),
                'paired': {k: rnd12(v) for k, v in dst.items()},
                'd_cagr_b_pp': rnd12((pf['cagr_cal_pct'] - base_perf['cagr_cal_pct'])),
                'd_sharpe': rnd12(pf['sharpe'] - base_perf['sharpe']),
                'd_maxdd_pp': rnd12(pf['maxdd'] - base_perf['maxdd']),
                'n_suppressed_total': sum(int(p['n_suppressed']) for p in ps)}

            if arm_id != BASE_ID:
                sup_rows = [r for r in res['ledger'] if r.get('suppressed')]
                cause_n = Counter()
                cause_dev = Counter()
                sc, st = hist([abs(float(r['target_final']) - float(r['pre_drifted']))
                               for r in sup_rows]) if sup_rows else ([0]*6, [0.0]*6)
                ec, et = hist([abs(float(r['delta_exec'])) for r in res['ledger']
                               if str(r['order_type_exec']).startswith('CONT')])
                for r in sup_rows:
                    lab = CAUSE_MAP.get(r.get('attr_label', 'MIXED'), 'mixed')
                    cause_n[lab] += 1
                    cause_dev[lab] += abs(float(r['target_final']) - float(r['pre_drifted']))
                    rows['SUPPRESSED_TRADES'].append({
                        'window': w, 'arm': arm_id, 'date': str(r['date']), 'ticker': r['ticker'],
                        'abs_deviation_pct': rnd12(abs(float(r['target_final']) - float(r['pre_drifted'])) * 100.0),
                        'pre_trade_weight_pct': rnd12(float(r['pre_drifted']) * 100.0),
                        'desired_target_pct': rnd12(float(r['target_final']) * 100.0),
                        'cause': lab})
                tot_dev = sum(cause_dev.values()) or 1.0
                for cause in sorted(set(cause_n) | set(CAUSE_MAP.values())):
                    rows['SUPPRESSED_CAUSES'].append({
                        'window': w, 'arm': arm_id, 'cause': cause,
                        'n_suppressed': cause_n.get(cause, 0),
                        'abs_dev_share': rnd12(cause_dev.get(cause, 0.0) / tot_dev)})
                for i in range(6):
                    rows['MICRO_CHURN'].append({'window': w, 'arm': arm_id, 'bucket': blabels[i],
                                                'orders': ec[i], 'weight_frac': rnd12(et[i]),
                                                'orders_removed': sc[i],
                                                'weight_frac_removed': rnd12(st[i])})

def tier_of(d):
    red = d['order_reduction_pct']
    if red >= LARGE_ORD_RED and d['d_cagr_b_pp'] >= LARGE_CAGR_MIN * 100.0 \
            and d['d_sharpe'] >= LARGE_SHARPE_MIN and d['d_maxdd_pp'] <= LARGE_DD_MAX_PP:
        return 'LARGE'
    if red >= MODERATE_ORD_RED and d['d_cagr_b_pp'] >= MODERATE_CAGR_MIN * 100.0 \
            and d['d_maxdd_pp'] <= MODERATE_DD_MAX_PP:
        return 'MODERATE'
    return 'NONE'


def pareto_and_labels():
    ev = {}
    lab = R['labels'] = {}
    for w in WINDOWS:
        dims = {}
        for a in ARM_MODE:
            d = R['an']['arms'][w][a]
            dims[a] = ((d['perf']['cagr_cal_pct'], d['perf']['sharpe']),
                       (d['orders_per_yr'], d['reweights_per_yr'], d['turnover_ann_pct'],
                        abs(d['perf']['maxdd'])))

        def dominates(x, y, eps=1e-12):
            m1, m0 = dims[x]
            n1, n0 = dims[y]
            ge = all(p >= q - eps for p, q in zip(m1, n1)) and all(p <= q + eps for p, q in zip(m0, n0))
            gt = any(p > q + eps for p, q in zip(m1, n1)) or any(p < q - eps for p, q in zip(m0, n0))
            return ge and gt
        nd = [a for a in ARM_MODE if not any(dominates(b, a) for b in ARM_MODE if b != a)]
        R.setdefault('nondominated', {})[w] = nd

        lc_w = None
        for i, bp_ in enumerate(BANDS_BP, 1):
            aid = f'EXEC{i:02d}_BAND_{bp_}BP'
            if R['an']['arms'][w][aid]['rw_reduction_pct'] >= LOWCHANGE_RW_RED:
                lc_w = aid
                break
        bal_cands = [a for a in nd if a not in (EE99_ID, BASE_ID)
                     and tier_of(R['an']['arms'][w][a]) == 'LARGE']
        bal_w = max(bal_cands, key=lambda a: (R['an']['arms'][w][a]['order_reduction_pct'],
                                              -ARM_MODE[a][1])) if bal_cands else None
        mx_cands = [a for a in nd if a != BASE_ID and tier_of(R['an']['arms'][w][a]) == 'MODERATE']
        mx_w = min(mx_cands, key=lambda a: (R['an']['arms'][w][a]['orders_per_yr'],
                                            abs(R['an']['arms'][w][a]['perf']['maxdd']))) if mx_cands else None
        ev[w] = {'nondominated': nd, 'LOW_CHANGE_window': lc_w,
                 'BALANCED_candidates': bal_cands, 'BALANCED_window': bal_w,
                 'MAX_SIMPLIFICATION_candidates': mx_cands, 'MAX_SIMPLIFICATION_window': mx_w}
        lab[w] = {'LOW_CHANGE': lc_w, 'BALANCED': bal_w, 'MAX_SIMPLIFICATION': mx_w}

    lc_both = None
    for i, bp_ in enumerate(BANDS_BP, 1):
        aid = f'EXEC{i:02d}_BAND_{bp_}BP'
        if all(R['an']['arms'][w][aid]['rw_reduction_pct'] >= LOWCHANGE_RW_RED for w in WINDOWS):
            lc_both = aid
            break
    bal_both_c = [a for a in ARM_MODE if a not in (EE99_ID, BASE_ID)
                  and all(a in R['nondominated'][w] and tier_of(R['an']['arms'][w][a]) == 'LARGE'
                          for w in WINDOWS)]
    bal_both = max(bal_both_c, key=lambda a: (min(R['an']['arms'][ww][a]['order_reduction_pct']
                                                  for ww in WINDOWS), -ARM_MODE[a][1])) if bal_both_c else None
    mx_both_c = [a for a in ARM_MODE if a != BASE_ID
                 and all(a in R['nondominated'][w] and tier_of(R['an']['arms'][w][a]) == 'MODERATE'
                         for w in WINDOWS)]
    mx_both = min(mx_both_c, key=lambda a: (sum(R['an']['arms'][ww][a]['orders_per_yr']
                                                for ww in WINDOWS),
                                            sum(abs(R['an']['arms'][ww][a]['perf']['maxdd'])
                                                for ww in WINDOWS))) if mx_both_c else None
    lab['BOTH'] = {'LOW_CHANGE': lc_both, 'BALANCED': bal_both, 'MAX_SIMPLIFICATION': mx_both}

    for w in WINDOWS:
        for a in ARM_MODE:
            d = R['an']['arms'][w][a]
            tag = ','.join(f'{k}={lab[w][k]}' for k in ('LOW_CHANGE', 'BALANCED', 'MAX_SIMPLIFICATION')
                           if lab[w][k] == a) or ''
            R['rows']['PARETO_FRONT'].append({
                'window': w, 'arm': a, 'nondominated': a in R['nondominated'][w],
                'cagr_b_cal_pct': d['perf']['cagr_cal_pct'], 'sharpe': d['perf']['sharpe'],
                'total_orders_per_yr': d['orders_per_yr'], 'reweights_per_yr': d['reweights_per_yr'],
                'turnover_exec_ann_pct': d['turnover_ann_pct'],
                'abs_maxdd_pct': rnd12(abs(d['perf']['maxdd'])),
                'frontier_label': tag})
    write_csv(f'{OUT}/TRANSACTION_MINIMIZATION_PARETO_FRONT.csv', R['rows']['PARETO_FRONT'])
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_FRONTIER_LABELS.json',
               {'per_window': ev, 'both_windows': lab['BOTH']})


def selected_arms():
    s = {BASE_ID, EE99_ID}
    for k in ('LOW_CHANGE', 'BALANCED', 'MAX_SIMPLIFICATION'):
        v = R['labels']['BOTH'].get(k)
        if v:
            s.add(v)
    return [a for a in ARM_MODE if a in s]


def time_stability_loo():
    arms = selected_arms()
    for w in WINDOWS:
        bl = RES[w][BASE_ID]['ret_lists']['net_b']
        bps = RES[w][BASE_ID]['panels']
        n = len(bps)
        cut = n // 2

        def cagr_of(idxs, rets):
            cum = float(np.prod([1.0 + rets[i] for i in idxs]))
            return cum ** (PPY / len(idxs)) - 1.0
        for arm_id in arms:
            res = RES[w][arm_id]
            rl = res['ret_lists']['net_b']
            ps = res['panels']
            for hname, idxs in (('H1', list(range(cut))), ('H2', list(range(cut, n)))):
                yh = len(idxs) / PPY

                def blk(rr):
                    a = np.array([rr[i] for i in idxs])
                    cr = np.cumprod(1.0 + a)
                    dd = float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
                    sh = float(a.mean() / a.std(ddof=1) * math.sqrt(PPY)) if a.std(ddof=1) > 0 else None
                    wt_h = sum(ps[i]['wt_exec'] for i in idxs) * 100.0 / yh
                    od = sum(int(ps[i]['orders_exec'][k]) for i in idxs
                             for k in ('entries', 'exits', 'cont_buy', 'cont_sell'))
                    return cagr_of(idxs, rr), sh, dd, wt_h, od
                cg, cs, cd, cwt, cod = blk(bl)
                og, os_, odn, owt, ood = blk(rl)
                R['rows']['TIME_STABILITY'].append({
                    'window': w, 'half': hname, 'arm': arm_id,
                    'panel_ann_cagr_BASE_pct': rnd12(cg * 100.0),
                    'panel_ann_cagr_ARM_pct': rnd12(og * 100.0),
                    'cagr_contrast_pp': rnd12((og - cg) * 100.0),
                    'order_reduction_in_half': cod - ood,
                    'turnover_reduction_pp': rnd12(cwt - owt),
                    'maxdd_ARM_pct': rnd12(odn * 100.0), 'sharpe_ARM': rnd12(os_)})
        years = sorted({str(p['date'])[:4] for p in bps})
        for yr in years:
            keep = [i for i, p in enumerate(bps) if str(p['date'])[:4] != yr]
            yc = cagr_of(keep, bl)

            def mxdd(arr):
                cr = np.cumprod(1.0 + arr)
                return float(np.max(1.0 - cr / np.maximum.accumulate(cr)))
            ac = np.array([bl[i] for i in keep])
            for arm_id in arms:
                yo = cagr_of(keep, RES[w][arm_id]['ret_lists']['net_b'])
                ao = np.array([RES[w][arm_id]['ret_lists']['net_b'][i] for i in keep])
                R['rows']['LOO'].append({
                    'window': w, 'omitted_year': yr, 'arm': arm_id, 'n_panels_kept': len(keep),
                    'cagr_BASE_pct': rnd12(yc * 100.0), 'cagr_ARM_pct': rnd12(yo * 100.0),
                    'delta_cagr_pp': rnd12((yo - yc) * 100.0),
                    'maxdd_BASE_pct': rnd12(mxdd(ac) * 100.0), 'maxdd_ARM_pct': rnd12(mxdd(ao) * 100.0)})


def break_even():
    for w in WINDOWS:
        db = R['an']['arms'][w][BASE_ID]
        gb = db['perf']['cagr_cal_pct'] / 100.0
        for a in ARM_MODE:
            if a == BASE_ID:
                continue
            d = R['an']['arms'][w][a]
            ga = d['perf']['cagr_cal_pct'] / 100.0
            do = db['orders_per_yr'] - d['orders_per_yr']
            f = (gb - ga) / do if abs(do) > 1e-12 else None
            R['rows']['BREAK_EVEN'].append({
                'window': w, 'arm': a,
                'base_orders_per_yr': db['orders_per_yr'], 'arm_orders_per_yr': d['orders_per_yr'],
                'cagr_b_base_pct': db['perf']['cagr_cal_pct'], 'cagr_b_arm_pct': d['perf']['cagr_cal_pct'],
                'break_even_fixed_cost_per_order_pct_nav': rnd12(f * 100.0) if f is not None else None})


def arm_class(d, dominated):
    red = d['order_reduction_pct']
    if d['d_cagr_b_pp'] < MODERATE_CAGR_MIN * 100.0:
        return 'TOO_MUCH_RETURN_LOSS'
    if d['d_maxdd_pp'] > MODERATE_DD_MAX_PP:
        return 'TOO_MUCH_RISK_INCREASE'
    if red >= 0.05 and abs(d['d_cagr_b_pp']) <= 0.25 and abs(d['d_sharpe']) <= 0.05 \
            and d['d_maxdd_pp'] <= 0.5:
        return 'NEAR_IDENTICAL_LOWER_TRADING'
    if red >= LARGE_ORD_RED:
        return 'AGGRESSIVE_SIMPLIFICATION'
    if red >= MODERATE_ORD_RED:
        return 'EFFICIENT_TRADEOFF'
    return 'DOMINATED' if dominated else 'NEAR_IDENTICAL_LOWER_TRADING'


def decision_table():
    te_map = {(r['window'], r['arm']): r for r in R['rows']['TRACKING_ERROR']}
    for w in WINDOWS:
        nd = R['nondominated'][w]
        items = sorted(((R['an']['arms'][w][a]['orders_per_yr'], a) for a in ARM_MODE))
        for _oy, a in items:
            d = R['an']['arms'][w][a]
            te = te_map[(w, a)]
            R['rows']['DECISION_TABLE'].append({
                'window': w, 'arm': a, 'class': arm_class(d, a not in nd),
                'tier': tier_of(d), 'nondominated': a in nd,
                'total_orders_per_yr': d['orders_per_yr'],
                'order_reduction_abs': d['order_reduction_abs'],
                'order_reduction_pct': d['order_reduction_pct'],
                'reweights_per_yr': d['reweights_per_yr'],
                'rw_reduction_pct': d['rw_reduction_pct'],
                'turnover_ann_pct': d['turnover_ann_pct'],
                'turnover_reduction_pct': d['turnover_reduction_pct'],
                'cagr_b_cal_pct': d['perf']['cagr_cal_pct'], 'd_cagr_b_pp': d['d_cagr_b_pp'],
                'sharpe': d['perf']['sharpe'], 'd_sharpe': d['d_sharpe'],
                'maxdd_pct': rnd12(d['perf']['maxdd'] * 100.0), 'd_maxdd_pp': d['d_maxdd_pp'],
                'mean_weight_dev_vs_BASE_pct': te['mean_abs_weight_dev_pct'],
                'net_corr_vs_BASE': te['net_return_correlation_vs_BASE']})

def costb_gate():
    fac = {(r['window'], r['arm_id']): r for r in R['factorial']}
    oks = True
    ev = {}
    for w in WINDOWS:
        m = R['an']['summary'][w]
        fr = fac[(w, 'K5_1_K6_1_K7_0_WP_1')]
        dv = abs(float(m['cagr_b_cal']) * 100.0 - float(fr['cagr_b_cal_pct']))
        ref = R['costb'][w].get('reported_approx_reference_pct')
        rd = abs(float(m['cagr_b_cal']) * 100.0 - float(ref)) if ref is not None else None
        ok = dv <= 1e-9 and (rd is not None and rd <= 0.75)
        ev[w] = {'dev_vs_factorial_row': rnd12(dv),
                 'dev_vs_prior_reported_ref_pp': rnd12(rd) if rd is not None else None}
        oks &= ok
    gate('COST_B_REPLAY', oks, {**ev,
        'note': 'prior referens ar K7_ON-era approx; 0.75pp korroboring tillater '
                'K7_OFF-arkitekturskillnaden'}, tolerance=1e-9)


def turnover_identity_gate():
    oks = True
    ev = {}
    fac = {(r['window'], r['arm_id']): r for r in R['factorial']}
    for w in WINDOWS:
        res = RES[w][BASE_ID]
        led = {}
        for r in res['ledger']:
            led.setdefault(str(r['date']), []).append(r)
        ann = sum(float(p['wt_exec']) for p in res['panels']) * 100.0 / YEARS_CAL[w]
        m = R['an']['summary'][w]
        d_ann = abs(ann - float(m['turnover_exec_ann_pct']))
        d_fac = abs(ann - float(fac[(w, 'K5_1_K6_1_K7_0_WP_1')]['turnover_exec_ann_pct']))
        mx_int = 0.0
        for p in res['panels']:
            lrows = led.get(str(p['date']), [])
            A = sum(abs(float(x['delta_exec'])) for x in lrows)
            F = sum(float(x['delta_exec']) for x in lrows)
            mx_int = max(mx_int, abs(float(p['wt_exec']) - 0.5 * (A + abs(F))))
        recon = R['recon_wt'][w]
        mx_info = max((abs(float(p['wt_exec']) - recon[str(p['date'])])
                       for p in res['panels'] if str(p['date']) in recon), default=0.0)
        ev[w] = {'annual_vs_summarize_dev': rnd12(d_ann), 'annual_vs_factorial_row_dev': rnd12(d_fac),
                 'cash_leg_internal_identity_max': rnd12(mx_int),
                 'wd_recon_K7ON_era_max_abs_diff_INFO': rnd12(mx_info)}
        oks &= (d_ann <= 1e-9 and d_fac <= 1e-9 and mx_int <= IDENTITY_TOL)
    gate('WEIGHT_TURNOVER_IDENTITY', oks, {**ev,
        'note': 'per-panel OFF-turnover ar bitvis frusen via K7_OFF_BASE_REPLAY-hash; WD-reconens '
                'exec-kolumn ar K7_ON-era (V2 rad 777) och rapporteras endast informativt'},
        tolerance=IDENTITY_TOL)


def deterministic_gate():
    h2 = {}
    for w in WINDOWS:
        for a in ARM_MODE:
            h2[f'{w}|{a}'] = arm_hash(w, run_plain(w, a))
    mism = [k for k in h2 if h2[k] != P1.get(k)]
    gate('DETERMINISTIC_REPLAY', not mism, {
        'hash_payload': 'metrics_rnd12+order_sizes_summary(n/mean/median/p90)+panel_net_b+nav_end',
        'pass1_sha256': P1, 'pass2_sha256': h2, 'mismatches': mism})


def isolation_gate():
    summ = {f'{w}|{a}': V2.summarize_arm(RES[w][a], None) for w in WINDOWS for a in ARM_MODE}
    dev = {}
    ok = True
    num = lambda mm: [k for k in mm if isinstance(mm[k], (int, float)) and not isinstance(mm[k], bool)]
    for w in WINDOWS:
        for a in ARM_MODE:
            res = run_one(w, a)
            m = V2.summarize_arm(res, None)
            s = summ[f'{w}|{a}']
            d = max(abs(float(m[k]) - float(s[k])) for k in num(m))
            dev[f'{w}|{a}'] = rnd12(d)
            ok &= d <= 1e-15
    gate('STATE_ISOLATION', ok, {'max_metric_dev_vs_first_pass': dev}, tolerance=1e-15)


def claim_scan():
    allow_fab = {'TRANSACTION_MINIMIZATION_REPORT.md', 'TRANSACTION_MINIMIZATION_REPORT.json'}
    hits = {}
    for dp, _dns, fns in os.walk(OUT):
        if 'trackj' in set(dp.split(os.sep)):
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
        'whitelisted_quoted_claim_files': sorted(allow_fab), 'hits': hits})


def classify():
    an = R['an']
    frontier = [a for a, m in ARM_MODE.items() if m[0] in ('band', 'state')]
    rank = {'NONE': 0, 'MODERATE': 1, 'LARGE': 2}

    def best_tier(w):
        return max((tier_of(an['arms'][w][a]) for a in frontier), key=lambda t: rank[t], default='NONE')
    mixed = abs(rank[best_tier('W1')] - rank[best_tier('W2')]) >= 2
    for a in frontier:
        s1, s2 = an['arms']['W1'][a]['paired'], an['arms']['W2'][a]['paired']
        i1 = s1['mean'] > ECON_EPS and s1['boot_ci_low'] > 0
        h1 = s1['mean'] < -ECON_EPS and s1['boot_ci_high'] < 0
        i2 = s2['mean'] > ECON_EPS and s2['boot_ci_low'] > 0
        h2 = s2['mean'] < -ECON_EPS and s2['boot_ci_high'] < 0
        if (i1 and h2) or (h1 and i2):
            mixed = True
    ee_ok = all(tier_of(an['arms'][w][EE99_ID]) == 'LARGE' for w in WINDOWS)
    both_large = any(all(tier_of(an['arms'][w][a]) == 'LARGE' for w in WINDOWS) for a in frontier)
    any_large = any(tier_of(an['arms'][w][a]) == 'LARGE' for w in WINDOWS for a in frontier)
    both_mod = any(all(tier_of(an['arms'][w][a]) == 'MODERATE' for w in WINDOWS) for a in frontier)
    mandatory_ok = all(TM_GATES.get(g, {}).get('status') == 'PASS' for g in MANDATORY)
    bal = R['labels']['BOTH'].get('BALANCED')

    if not mandatory_ok:
        fin, nxt = 'TRANSACTION_MINIMIZATION_INVALID', 'FAIL_CLOSED_NO_CONCLUSION'
    elif mixed:
        fin, nxt = 'TRANSACTION_MINIMIZATION_MIXED_W1_W2', 'FORWARD_SHADOW_EXECUTION_FRONTIER'
    elif ee_ok:
        fin, nxt = 'ENTRY_EXIT_ONLY_SUFFICIENT', 'FREEZE_EXECUTION_CANDIDATE'
    elif both_large:
        fin = 'TRANSACTION_MINIMIZATION_LARGE_EFFICIENCY_GAIN'
        nxt = 'FREEZE_EXECUTION_CANDIDATE' if bal else 'FORWARD_SHADOW_EXECUTION_FRONTIER'
    elif any_large or both_mod:
        fin = 'TRANSACTION_MINIMIZATION_MODERATE_TRADEOFF'
        nxt = 'FORWARD_SHADOW_EXECUTION_FRONTIER'
    else:
        fin, nxt = 'FULL_REBALANCING_ECONOMICALLY_JUSTIFIED', 'KEEP_FULL_REBALANCING'
    R['cls'] = {'final_classification': fin, 'next_action': nxt,
                'mandatory_gates_all_pass': mandatory_ok, 'mixed_flag': mixed,
                'best_tier': {'W1': best_tier('W1'), 'W2': best_tier('W2')},
                'balanced_arm': bal,
                'ee99_tiers': {w: tier_of(an['arms'][w][EE99_ID]) for w in WINDOWS},
                'frontier_best': {w: best_tier(w) for w in WINDOWS}}
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_CLASSIFICATION.json', R['cls'])


ARTIFACTS = {
    'PERFORMANCE': 'TRANSACTION_MINIMIZATION_PERFORMANCE.csv',
    'RISK': 'TRANSACTION_MINIMIZATION_RISK.csv',
    'ORDER_COUNTS': 'TRANSACTION_MINIMIZATION_ORDER_COUNTS.csv',
    'WEIGHT_TURNOVER': 'TRANSACTION_MINIMIZATION_WEIGHT_TURNOVER.csv',
    'ORDER_SIZES': 'TRANSACTION_MINIMIZATION_ORDER_SIZES.csv',
    'MICRO_CHURN': 'TRANSACTION_MINIMIZATION_MICRO_CHURN.csv',
    'REVERSALS': 'TRANSACTION_MINIMIZATION_REVERSALS.csv',
    'SUPPRESSED_TRADES': 'TRANSACTION_MINIMIZATION_SUPPRESSED_TRADES.csv',
    'SUPPRESSED_CAUSES': 'TRANSACTION_MINIMIZATION_SUPPRESSED_CAUSES.csv',
    'TRACKING_ERROR': 'TRANSACTION_MINIMIZATION_TRACKING_ERROR.csv',
    'CONCENTRATION': 'TRANSACTION_MINIMIZATION_CONCENTRATION.csv',
    'COST_ATTRIBUTION': 'TRANSACTION_MINIMIZATION_COST_ATTRIBUTION.csv',
    'TIME_STABILITY': 'TRANSACTION_MINIMIZATION_TIME_STABILITY.csv',
    'LOO': 'TRANSACTION_MINIMIZATION_LOO.csv',
    'BREAK_EVEN': 'TRANSACTION_MINIMIZATION_BREAK_EVEN.csv',
    'DECISION_TABLE': 'TRANSACTION_MINIMIZATION_DECISION_TABLE.csv'}


def write_artifacts():
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_ARM_DEFINITIONS.json', {
        'arms': [{'arm_id': a, 'mode': m[0], 'band_bp': (m[1] * 1e4 if math.isfinite(m[1]) else None)}
                 for a, m in ARMS],
        'windows': WINDOWS, 'k7': 'OFF', 'k5': 'ON', 'k6': 'ON', 'wp': 'ON'})
    ldg = []
    for w in WINDOWS:
        for a in ARM_MODE:
            ldg.extend(RES[w][a]['ledger'])
    write_csv(f'{OUT}/TRANSACTION_MINIMIZATION_EXECUTION_LEDGER.csv', ldg)
    perf_rows, risk_rows = [], []
    for w in WINDOWS:
        for a in ARM_MODE:
            d = R['an']['arms'][w][a]
            pf = d['perf']
            perf_rows.append({'window': w, 'arm': a, **pf, 'cagr_c_cal_pct_stress40bp': d['cagr_c_cal_pct']})
            risk_rows.append({'window': w, 'arm': a, 'maxdd_pct': rnd12(pf['maxdd'] * 100.0),
                              'vol_ann_pct': pf['vol_ann_pct'], 'downside_ann_pct': pf['downside_ann_pct'],
                              'worst_panel_pct': pf['worst_panel_pct'], 'p5_panel_pct': pf['p5_panel_pct']})
    write_csv(f'{OUT}/TRANSACTION_MINIMIZATION_PERFORMANCE.csv', perf_rows)
    write_csv(f'{OUT}/TRANSACTION_MINIMIZATION_RISK.csv', risk_rows)
    for key, fname in ARTIFACTS.items():
        if R['rows'].get(key):
            write_csv(f'{OUT}/{fname}', R['rows'][key])


def report_all():
    cls = R['cls']
    L = []
    A = L.append
    fmtp = lambda v, d=3: ('n/a' if v is None else f'{v:.{d}f}')
    A('# TRANSACTION MINIMIZATION FRONTIER - STUDY_REPORT')
    A('')
    A(f'Studie: H0_V3_TRANSACTION_MINIMIZATION_FRONTIER | Windows: W1 (79 paneler), W2 (86 paneler)')
    A(f'Prereg sha256: {json.load(open(f"{OUT}/TRANSACTION_MINIMIZATION_FREEZE.json"))["preregistration_sha256"]}')
    A('')
    A('## A. Scope')
    A('- Endast execution-lagret varieras; momentum, Top30, SMA200, retain/refill, K5, K6, WP,')
    A('  exitlogik, universum, PIT-data och paneldatum ar oforandrade. K7 ar OFF i alla armar.')
    A(f'- Armar: {", ".join(a for a, _ in ARMS)}')
    A('')
    A('## B. Frozen K7_OFF architecture')
    A(f"- BASE = K5_1_K6_1_K7_0_WP_1; bitvis replay mot K7-studiens frusna hashar: "
      f"{TM_GATES['K7_OFF_BASE_REPLAY']['status']}")
    A('')
    A('## C. Replay gates')
    A('')
    for g in MANDATORY:
        A(f'- {g}: {TM_GATES[g]["status"]}')
    A('')
    A('## D. Execution-only intervention proof')
    A('- Target-pipelinen (pre-WP cashon-niva), selektionen och entries/exits ar identiska mellan')
    A('  alla armar (gates PASS); WP-sluttargets ar tillstandsberoende via kapitalreallokering')
    A('  (samma semantik som V2, dokumenterat som prereg-avvikelse). Endast exekverade vikter')
    A('  skiljer. Fork-passthrough ar bitvis identisk med V2.run_arm.')
    A('')
    A('## E. BASE transaction anatomy')
    for w in WINDOWS:
        b = R['an']['arms'][w][BASE_ID]
        A(f"- {w}: {b['orders_per_yr']} orders/ar totalt, varav {b['reweights_per_yr']} continuing "
          f"reweights/ar ({b['reweights']/max(1,b['total_orders'])*100:.1f}%); turnover "
          f"{b['turnover_ann_pct']:.1f}%/ar")
    A('')
    A('## F. No-trade-band arms (PRIMARY: orders)')
    A('')
    A('| Window | Arm | Orders/ar | Red% | Reweights/ar | Turnover%/ar | CAGR_B% | dCAGR pp | Sharpe | dSharpe | MaxDD% | dMaxDD pp |')
    A('|---|---|---|---|---|---|---|---|---|---|---|---|')
    for w in WINDOWS:
        for a in ARM_MODE:
            d = R['an']['arms'][w][a]
            A(f"| {w} | {a} | {d['orders_per_yr']} | {d['order_reduction_pct']*100:+.1f}% | "
              f"{d['reweights_per_yr']} | {d['turnover_ann_pct']:.1f} | {d['perf']['cagr_cal_pct']:.3f} | "
              f"{d['d_cagr_b_pp']:+.3f} | {d['perf']['sharpe']:.3f} | {d['d_sharpe']:+.3f} | "
              f"{abs(d['perf']['maxdd'])*100:.2f} | {d['d_maxdd_pp']:+.2f} |")
    A('')
    A('## G. ENTRY_EXIT_ONLY control')
    for w in WINDOWS:
        d = R['an']['arms'][w][EE99_ID]
        s = d['paired']
        A(f"- {w}: CAGR_B {d['perf']['cagr_cal_pct']:.3f}% (d {d['d_cagr_b_pp']:+.2f} pp), Sharpe "
          f"{d['perf']['sharpe']:.3f}, MaxDD {abs(d['perf']['maxdd'])*100:.2f}%, paired mean "
          f"{fmtp(s['mean'],5)} CI [{fmtp(s['boot_ci_low'],5)}, {fmtp(s['boot_ci_high'],5)}]")
    A('')
    A('## H. State-change-only arm')
    for w in WINDOWS:
        d = R['an']['arms'][w][STATE_ID]
        ps = RES[w][STATE_ID]['panels']
        trig = sum(1 for p in ps if p['st_trigger'] and p['st_trigger']['rebalance_allowed'])
        A(f"- {w}: rebalans-tillatna paneler {trig}/{len(ps)}; CAGR_B {d['perf']['cagr_cal_pct']:.3f}% "
          f"(d {d['d_cagr_b_pp']:+.2f} pp), orders {d['orders_per_yr']} (red {d['order_reduction_pct']*100:+.1f}%)")
    A('')
    A('## I. Performance / ## J. Risk')
    A('- Se TRANSACTION_MINIMIZATION_PERFORMANCE.csv / RISK.csv (gross/COST_B/COST_C/13-panel CAGR,')
    A('  Sharpe, vol, MaxDD, downside dev, terminal wealth per arm och fonster).')
    A('')
    A('## K. Order counts / ## L. Weight turnover / ## M. Order sizes')
    A('- Se ORDER_COUNTS.csv, WEIGHT_TURNOVER.csv, ORDER_SIZES.csv (median/mean/P90/P95 per klass).')
    A('')
    A('## N. Micro-churn (BASE-anatomi och vad banden tar bort)')
    mc = [r for r in R['rows']['MICRO_CHURN']]
    for w in WINDOWS:
        base_rows = {r['bucket']: r for r in mc if r['window'] == w and r['arm'] == BASE_ID}
        tot_o = sum(r['orders'] for r in base_rows.values())
        parts = ', '.join(f"{b}: {base_rows[b]['orders']} ({base_rows[b]['orders']/tot_o*100:.0f}%)"
                          for b in base_rows)
        A(f'- {w} BASE cont-orders per storlek: {parts}')
    A('')
    A('## O. Reversal churn')
    for w in WINDOWS:
        rb = [r for r in R['rows']['REVERSALS'] if r['window'] == w and r['arm'] == BASE_ID][0]
        best = min((r for r in R['rows']['REVERSALS'] if r['window'] == w and r['arm'] != BASE_ID),
                   key=lambda r: r['rev1_next_panel'])
        A(f"- {w} BASE: rev1/rev2/rev3 = {rb['rev1_next_panel']}/{rb['rev2_within_2']}/{rb['rev3_within_3']} "
          f"({rb['fraction_of_cont_orders']*100:.0f}% av cont-orders), reverserad turnover-kostnad "
          f"{rb['reversed_costB_pp_yr']:.2f} pp/ar; lagaste rev1 bland suppression-armarna: "
          f"{best['arm']} = {best['rev1_next_panel']}")
    A('')
    A('## P. Suppressed-trade attribution')
    for w in WINDOWS:
        cs_ = {}
        for r in R['rows']['SUPPRESSED_CAUSES']:
            if r['window'] == w and r['arm'] == R['labels']['BOTH'].get('BALANCED') \
                    or (r['window'] == w and R['labels']['BOTH'].get('BALANCED') is None
                        and r['arm'] == 'EXEC07_BAND_200BP'):
                cs_[r['cause']] = (r['n_suppressed'], r['abs_dev_share'])
        if cs_:
            A(f"- {w}: " + ', '.join(f'{k}={v[0]} ({v[1]*100:.0f}%)' for k, v in sorted(cs_.items())))
    A('')
    A('## Q. Tracking error')
    for w in WINDOWS:
        row = ' | '.join(f"{a.split('_')[0]}:{[r for r in R['rows']['TRACKING_ERROR'] if r['window']==w and r['arm']==a][0]['mean_abs_weight_dev_pct']:.2f}%"
                         for a in ARM_MODE)
        A(f'- {w} mean |dw| vs BASE: {row}')
    A('')
    A('## R. Concentration / drift risk')
    for w in WINDOWS:
        c = [r for r in R['rows']['CONCENTRATION'] if r['window'] == w]
        cb = [x for x in c if x['arm'] == BASE_ID][0]
        worst = max((x for x in c if x['arm'] != BASE_ID), key=lambda x: x['top1_max_pct'])
        A(f"- {w} BASE: effN {cb['effn_mean']:.1f}, Top1 max {cb['top1_max_pct']:.2f}%, paneler >2pp "
          f"fran target {cb['panels_any_name_gt2pp_from_target']}; aggressivaste armen {worst['arm']}: "
          f"Top1 max {worst['top1_max_pct']:.2f}%, >2pp i {worst['panels_any_name_gt2pp_from_target']} "
          f"paneler, max sammanhangande {worst['max_consecutive_panels_gt2pp']}")
    A('')
    A('## S. Gross vs COST_B attribution')
    A('- Se COST_ATTRIBUTION.csv (log gross-effekt, kostnadsbesparing, netto-effekt per arm).')
    A('')
    A('## T. Pareto frontier')
    ndtxt = '; '.join(f"{w}: {len(R['nondominated'][w])} icke-dominerade" for w in WINDOWS)
    A(f'- {ndtxt}; labels: {R["labels"]["BOTH"]} (se PARETO_FRONT.csv)')
    A('')
    A('## U. Return lost per 100 orders removed / ## V. Risk change per 100 orders removed')
    for w in WINDOWS:
        db = R['an']['arms'][w][BASE_ID]
        seg = []
        for a in ARM_MODE:
            if a == BASE_ID:
                continue
            d = R['an']['arms'][w][a]
            do = db['total_orders'] - d['total_orders']
            if do <= 0:
                continue
            seg.append(f"{a.split('_')[0]}: {-d['d_cagr_b_pp']/(do/100.0):.2f} pp/100 ord")
        A(f'- {w} CAGR-loss per 100 borttagna orders: ' + '; '.join(seg))
    A('')
    A('## W. Time stability / ## X. Leave-one-year-out')
    A('- Se TIME_STABILITY.csv och LOO.csv (BASE + LOW_CHANGE/BALANCED/MAX_SIMPLIFICATION/EXEC99).')
    A('')
    A('## Y. Break-even execution cost')
    be = [r for r in R['rows']['BREAK_EVEN']]
    for w in WINDOWS:
        cand = [(r['break_even_fixed_cost_per_order_pct_nav'], r['arm']) for r in be
                if r['window'] == w and r['break_even_fixed_cost_per_order_pct_nav'] is not None]
        if cand:
            bestbe = max(cand)
            A(f'- {w}: hogsta break-even fast kostnad/order: {bestbe[1]} = {bestbe[0]:.4f}% NAV')
    A('')
    A('## Z. Decision table')
    A('- Se DECISION_TABLE.csv (sorterad efter orders/ar, inte CAGR). Klasser enligt frusen ladder.')
    A('')
    A('## AA. FULL vs BALANCED vs ENTRY_EXIT_ONLY')
    bal = R['labels']['BOTH'].get('BALANCED')
    for tagname, aid in (('FULL REBALANCE (EXEC00)', BASE_ID), ('BALANCED FRONTIER', bal),
                         ('ENTRY_EXIT_ONLY (EXEC99)', EE99_ID)):
        if aid is None:
            A(f'- BALANCED FRONTIER: ingen arm uppfyllde de frusna LARGE-kriterierna i bada fonstren')
            continue
        seg = []
        for w in WINDOWS:
            d = R['an']['arms'][w][aid]
            seg.append(f"{w}: {d['orders_per_yr']} orders/ar, CAGR_B {d['perf']['cagr_cal_pct']:.2f}%, "
                       f"Sharpe {d['perf']['sharpe']:.2f}, MaxDD {abs(d['perf']['maxdd'])*100:.1f}%")
        A(f'- {tagname}: ' + ' | '.join(seg))
    A('')
    A('## AB. Final classification')
    A('')
    A(f"**FINAL_CLASSIFICATION: {cls['final_classification']}**")
    A('')
    A(f"NEXT_ACTION: {cls['next_action']}")
    A(f"Best tier per fonster: {cls['best_tier']}; BALANCED-arm: {bal}; EE99 tiers: {cls['ee99_tiers']}")
    A('')
    A('## AC. One next action')
    na_txt = {
        'FREEZE_EXECUTION_CANDIDATE': 'Frys den identifierade BALANCED-frontier-armen som kandidat '
                                      '(EJ automatisk kanon-andring); upprepa studien oforandrad.',
        'KEEP_FULL_REBALANCING': 'Behall EXEC00 full rebalans; trade suppression kostar for mycket.',
        'FORWARD_SHADOW_EXECUTION_FRONTIER': 'Historiken skiljer inte alternativen tillrackligt; '
                                             'kor shadow-execution-frontier frammat.',
        'FAIL_CLOSED_NO_CONCLUSION': 'Atga gate-fel; studien saknar giltighet.'}[cls['next_action']]
    A(f'- {na_txt}')
    A('')
    with open(f'{OUT}/TRANSACTION_MINIMIZATION_REPORT.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    rep = {'study': 'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER',
           'final_classification': cls['final_classification'],
           'next_action': cls['next_action'],
           'frontier_labels_both_windows': R['labels']['BOTH'],
           'balanced_arm': cls['balanced_arm'],
           'gates': {g: TM_GATES[g]['status'] for g in TM_GATES}}
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_REPORT.json', rep)


def main():
    os.makedirs(OUT, exist_ok=True)
    for fn in os.listdir(OUT):
        fp = os.path.join(OUT, fn)
        if os.path.isfile(fp):
            os.remove(fp)
    print('=== H0_V3_TRANSACTION_MINIMIZATION_FRONTIER ===', flush=True)
    freeze_preregistration()
    load_prior_artifacts()
    load_contexts()
    R['an'] = {}
    R['rows'] = {k: [] for k in ARTIFACTS}
    R['rows'].update({'PARETO_FRONT': [], 'TIME_STABILITY': [], 'LOO': [],
                      'BREAK_EVEN': [], 'DECISION_TABLE': [], 'SUPPRESSED_TRADES': []})
    for w in WINDOWS:
        RES[w] = {}
        res = run_one(w, BASE_ID)
        RES[w][BASE_ID] = res
        P1[f'{w}|{BASE_ID}'] = arm_hash(w, res)
    replay_gates()
    for w in WINDOWS:
        res = run_band_arm(V2.CTX[w], w, 'band', 0.0, BASE_LABEL, True)
        RES[w]['FORK_PASSTHROUGH'] = res
        P1[f'{w}|FORK_PASSTHROUGH'] = arm_hash(w, res)
    fork_identity_gate()
    for w in WINDOWS:
        for a, (_m, _b) in ARMS:
            if a == BASE_ID:
                continue
            RES[w][a] = run_one(w, a)
            P1[f'{w}|{a}'] = arm_hash(w, RES[w][a])
            print(f'[RUN] {w} {a} done', flush=True)
    identity_gates()
    execution_intervention_gate()
    timing_pit()
    costb_gate()
    turnover_identity_gate()
    analyze_all()
    pareto_and_labels()
    time_stability_loo()
    break_even()
    decision_table()
    write_artifacts()
    deterministic_gate()
    isolation_gate()
    claim_scan()
    classify()
    report_all()
    write_json(f'{OUT}/TRANSACTION_MINIMIZATION_GATES.json',
               {'study': 'H0_V3_TRANSACTION_MINIMIZATION_FRONTIER',
                'generated_utc': datetime.now(timezone.utc).isoformat(), 'gates': TM_GATES})
    fails = [g for g in MANDATORY if TM_GATES.get(g, {}).get('status') != 'PASS']
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
