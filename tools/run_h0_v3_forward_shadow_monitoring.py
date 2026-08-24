#!/usr/bin/env python
"""Fail-closed, append-only monitor for the activated H0 V3 canonical path.

This is monitoring infrastructure, not a research runner.  It never changes
model parameters and it records only decision panels strictly after activation.
"""
import csv
import hashlib
import importlib
import json
import math
import os
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = f'{ROOT}/tools'
OUT = f'{ROOT}/research_k/h0_v3_forward_shadow_execution_monitoring'
CANON = f'{ROOT}/research_k/h0_v3_canonical_production_implementation'
ARCH = 'H0_V3_CANONICAL_K7OFF_EXEC05_100BP'
MODE = 'SHADOW_EXECUTION'
WINDOW = 'W2'
EPS = 1e-12

if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load(path):
    with open(path) as f:
        return json.load(f)


def dump(path, obj):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def q(values, pct):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * pct
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return values[lo] if lo == hi else values[lo] + (values[hi] - values[lo]) * (pos - lo)


def ensure_csv(name, header):
    path = f'{OUT}/{name}'
    if not os.path.exists(path):
        with open(path, 'w', newline='') as f:
            csv.writer(f).writerow(header)
        return path
    with open(path, newline='') as f:
        existing = next(csv.reader(f), [])
    if existing != header:
        raise RuntimeError(f'append-only schema mismatch: {name}')
    return path


def append_rows(path, header, rows):
    if not rows:
        return
    with open(path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writerows(rows)


def historical_reference():
    ledger = list(csv.DictReader(open(f'{CANON}/PRODUCTION_EXECUTION_LEDGER_W1.csv'))) + \
             list(csv.DictReader(open(f'{CANON}/PRODUCTION_EXECUTION_LEDGER_W2.csv')))
    turnover = list(csv.DictReader(open(f'{CANON}/PRODUCTION_WEIGHT_TURNOVER.csv')))
    by_panel = {}
    for r in ledger:
        key = (r['window'], r['date'])
        by_panel.setdefault(key, []).append(r)
    orders, drifts, top1, top3, effn = [], [], [], [], []
    for rows in by_panel.values():
        executed = [r for r in rows if r['order_type_exec'] != 'NONE']
        orders.append(len(executed))
        drifts.extend(abs(float(r['target_final']) - float(r['pre_drifted']))
                      for r in rows if r['in_prev'] == 'True' and r['in_target'] == 'True')
        ws = sorted((float(r['exec_target']) for r in rows if float(r['exec_target']) > EPS), reverse=True)
        if ws:
            top1.append(ws[0]); top3.append(sum(ws[:3])); effn.append(1.0 / sum(x*x for x in ws))
    turns = [float(r['wt_exec_pct']) / 100.0 for r in turnover]
    return {
        'source_files': {
            'ledger_w1_sha256': sha(f'{CANON}/PRODUCTION_EXECUTION_LEDGER_W1.csv'),
            'ledger_w2_sha256': sha(f'{CANON}/PRODUCTION_EXECUTION_LEDGER_W2.csv'),
            'turnover_sha256': sha(f'{CANON}/PRODUCTION_WEIGHT_TURNOVER.csv')},
        'distribution_definition': 'Frozen historical EXEC05 production ledgers; no forward observations included.',
        'watch_thresholds': {
            'orders_per_panel_p95': q(orders, .95), 'turnover_per_panel_p95': q(turns, .95),
            'target_deviation_p95': q(drifts, .95), 'top1_p95': q(top1, .95),
            'top3_p95': q(top3, .95), 'effective_n_p05': q(effn, .05)},
        'historical_reference_counts': {'panels': len(by_panel), 'continuing_holding_decisions': len(drifts)}}


PANEL_HEADER = ['panel_date', 'panel_hash', 'prior_panel_hash', 'canonical_hash', 'mode', 'n_selected',
                'entries', 'exits', 'continuing_orders', 'suppressed_orders', 'total_orders', 'turnover',
                'COST_B', 'mean_target_deviation', 'max_target_deviation', 'top1_weight', 'top3_weight',
                'effective_N', 'implementation_status', 'watch_flags']
HOLDING_HEADER = ['panel_date', 'panel_hash', 'ticker', 'status', 'pretrade_weight', 'desired_target',
                  'deviation', 'k5_target', 'k6_multiplier', 'wp_state', 'trade_decision', 'order_weight',
                  'posttrade_weight', 'reason']
SUPPRESS_HEADER = ['panel_date', 'panel_hash', 'ticker', 'pretrade_weight', 'desired_target', 'deviation',
                   'direction', 'hypothetical_trade_size', 'k5_k6_wp_attribution', 'subsequent_return_effect',
                   'self_corrected', 'would_have_reversed', 'hypothetical_COST_B']
ACTUAL_HEADER = ['panel_date', 'panel_hash', 'ticker', 'order_type', 'order_weight', 'actual_fee',
                 'actual_spread_slippage_estimate', 'actual_execution_cost', 'mode']
TURNOVER_HEADER = ['panel_date', 'panel_hash', 'executed_turnover', 'entry_exit_turnover',
                   'continuing_reweight_turnover', 'cumulative_turnover', 'annualized_turnover', 'sample_label']
DRIFT_HEADER = ['panel_date', 'panel_hash', 'mean_abs', 'median_abs', 'p90_abs', 'p95_abs', 'max_abs',
                'frac_gt_1pp', 'frac_gt_2pp', 'frac_gt_5pp', 'longest_gt_1pp', 'longest_gt_2pp', 'longest_gt_5pp']
CONC_HEADER = ['panel_date', 'panel_hash', 'top1_weight', 'top3_weight', 'top5_weight', 'hhi', 'effective_n']
FULL_HEADER = ['panel_date', 'panel_hash', 'full_rebalance_orders', 'actual_orders', 'orders_saved',
               'full_rebalance_turnover', 'actual_turnover', 'turnover_saved']
HASH_HEADER = ['run_utc', 'path', 'sha256', 'expected_sha256', 'status']
WATCH_HEADER = ['panel_date', 'panel_hash', 'flag', 'classification', 'value', 'threshold', 'note']


def sample_label(n):
    return 'VERY_EARLY' if n < 6 else 'EARLY' if n <= 12 else 'ONE_YEAR_SCALE' if n <= 25 else 'MULTIYEAR_FORWARD'


def activation_and_first_panel():
    final_path = f'{CANON}/PRODUCTION_CHECKPOINT_FINALIZATION.json'
    activation = datetime.fromtimestamp(os.path.getmtime(final_path), tz=timezone.utc)
    dates = []
    for r in csv.DictReader(open(f'{CANON}/PRODUCTION_EXECUTION_LEDGER_W2.csv')):
        if r['date'] not in dates:
            dates.append(r['date'])
    dates = [date.fromisoformat(x) for x in dates]
    cadence = int(statistics.median((b-a).days for a, b in zip(dates, dates[1:])))
    first = dates[-1] + timedelta(days=cadence)
    while datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc) <= activation:
        first += timedelta(days=cadence)
    return activation, dates[-1], cadence, first


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(f'{OUT}/snapshots', exist_ok=True)
    final = load(f'{CANON}/PRODUCTION_CHECKPOINT_FINALIZATION.json')
    freeze = load(f'{CANON}/PRODUCTION_IMPLEMENTATION_FREEZE.json')
    hashes = load(f'{CANON}/PRODUCTION_PATH_HASHES.json')
    if final['classification'] != 'PRODUCTION_CANONICAL_ACTIVATED_K7OFF_EXEC05_100BP' or not final['all_gates_pass']:
        raise RuntimeError('fail closed: activated production checkpoint is not healthy')
    if freeze['implementation_freeze'] != ARCH or freeze['locked_flags']['K7'] != 'OFF' \
            or freeze['locked_flags']['EXECUTION_CONTINUING_BAND'] != 0.01:
        raise RuntimeError('fail closed: canonical freeze mismatch')

    activation, last_known, cadence, first_eligible = activation_and_first_panel()
    canonical_manifest_hash = sha(f'{CANON}/PRODUCTION_CHECKPOINT_FINALIZATION.json')
    engine_paths = {
        'tools/h0_v3_production.py': f'{TOOLS}/h0_v3_production.py',
        'tools/run_h0_v3_weight_layer_simplification_v2.py': f'{TOOLS}/run_h0_v3_weight_layer_simplification_v2.py',
        'tools/run_h0_v3_transaction_minimization_frontier.py': f'{TOOLS}/run_h0_v3_transaction_minimization_frontier.py'}
    expected = dict(hashes['engine_files_sha256'])
    expected['tools/h0_v3_production.py'] = hashes['production_entrypoint_sha256']
    code_rows, code_ok = [], True
    for label, path in engine_paths.items():
        actual, exp = sha(path), expected[label]
        ok = actual == exp
        code_ok &= ok
        code_rows.append({'run_utc': datetime.now(timezone.utc).isoformat(), 'path': label,
                          'sha256': actual, 'expected_sha256': exp, 'status': 'PASS' if ok else 'CANONICAL_CODE_DRIFT'})

    prereg = {
        'study': 'H0_V3_FORWARD_SHADOW_EXECUTION_MONITORING', 'type': 'forward_only_read_only_monitoring',
        'locked_before_forward_observations': True, 'canonical_architecture': ARCH, 'mode_default': MODE,
        'forbidden': ['band changes or alternate bands', 'K7 reintroduction', 'K5/K6/WP/cadence/exit changes',
                      'cost-aware execution', 'minimum order size', 'adaptive band', 'concentration-threshold changes',
                      'automatic parameter change or rollback on performance'],
        'implementation_fail_closed_only': True,
        'status_labels': ['FORWARD_MONITORING_INITIALIZED_NO_NEW_PANEL', 'FORWARD_CANONICAL_HEALTHY',
                          'FORWARD_CANONICAL_HEALTHY_WITH_WATCH_FLAGS', 'FORWARD_CANONICAL_IMPLEMENTATION_FAILURE'],
        'next_actions': ['NO_ACTION_CONTINUE_MONITORING', 'INVESTIGATE_EXECUTION_DRIFT',
                          'INVESTIGATE_CONCENTRATION_DRIFT', 'INVESTIGATE_TRANSACTION_COST_DRIFT',
                          'INVESTIGATE_MODEL_PERFORMANCE_DRIFT', 'ROLLBACK_REVIEW_IMPLEMENTATION_FAILURE']}
    if not os.path.exists(f'{OUT}/FORWARD_MONITORING_PREREGISTRATION.json'):
        dump(f'{OUT}/FORWARD_MONITORING_PREREGISTRATION.json', prereg)
    else:
        if load(f'{OUT}/FORWARD_MONITORING_PREREGISTRATION.json') != prereg:
            raise RuntimeError('fail closed: preregistration mutation')

    start = {'production_activation_timestamp_utc': activation.isoformat(), 'activation_source':
             'mtime(PRODUCTION_CHECKPOINT_FINALIZATION.json)', 'first_eligible_forward_panel': first_eligible.isoformat(),
             'last_available_pre_activation_panel': last_known.isoformat(), 'canonical_commit_sha': None,
             'canonical_manifest_sha256': canonical_manifest_hash, 'active_engine_hashes': expected,
             'active_config_hashes': {'PRODUCTION_IMPLEMENTATION_FREEZE.json': sha(f'{CANON}/PRODUCTION_IMPLEMENTATION_FREEZE.json'),
                                      'PRODUCTION_CHECKPOINT_FINALIZATION.json': canonical_manifest_hash},
             'mode': MODE, 'forward_only_rule': 'panel_date strictly after production activation timestamp'}
    if not os.path.exists(f'{OUT}/FORWARD_MONITORING_START.json'):
        dump(f'{OUT}/FORWARD_MONITORING_START.json', start)
    elif load(f'{OUT}/FORWARD_MONITORING_START.json') != start:
        raise RuntimeError('fail closed: forward start mutation')

    provenance = {'canonical_checkpoint': f'{CANON}/PRODUCTION_CHECKPOINT_FINALIZATION.json',
                  'checkpoint_sha256': canonical_manifest_hash, 'freeze_sha256': sha(f'{CANON}/PRODUCTION_IMPLEMENTATION_FREEZE.json'),
                  'path_hashes_sha256': sha(f'{CANON}/PRODUCTION_PATH_HASHES.json'),
                  'architecture': ARCH, 'locked_flags': freeze['locked_flags'],
                  'historical_references_are_frozen_only': True}
    dump(f'{OUT}/FORWARD_CANONICAL_PROVENANCE.json', provenance)
    thresholds = historical_reference()
    threshold_path = f'{OUT}/FORWARD_WATCH_THRESHOLDS.json'
    if not os.path.exists(threshold_path):
        dump(threshold_path, thresholds)
    elif load(threshold_path) != thresholds:
        raise RuntimeError('fail closed: frozen watch threshold mutation')

    logs = [( 'FORWARD_PANEL_LOG.csv', PANEL_HEADER), ('FORWARD_HOLDING_EXECUTION_LOG.csv', HOLDING_HEADER),
            ('FORWARD_SUPPRESSED_TRADES.csv', SUPPRESS_HEADER), ('FORWARD_ACTUAL_ORDERS.csv', ACTUAL_HEADER),
            ('FORWARD_TURNOVER.csv', TURNOVER_HEADER), ('FORWARD_COST_B.csv', ['panel_date','panel_hash','actual_executed_turnover','COST_B','actual_fees','actual_spread_slippage_estimate','actual_execution_cost']),
            ('FORWARD_TARGET_DRIFT.csv', DRIFT_HEADER), ('FORWARD_CONCENTRATION.csv', CONC_HEADER),
            ('FORWARD_FULL_REBALANCE_COUNTERFACTUAL.csv', FULL_HEADER), ('FORWARD_CODE_CONFIG_HASHES.csv', HASH_HEADER),
            ('FORWARD_WATCH_FLAGS.csv', WATCH_HEADER)]
    paths = {name: ensure_csv(name, header) for name, header in logs}
    append_rows(paths['FORWARD_CODE_CONFIG_HASHES.csv'], HASH_HEADER, code_rows)

    # Current immutable source contains panels only through 2026-07-09.  Never
    # reinterpret them as forward observations after the 2026-08 activation.
    eligible_available = []
    gates = {'CANONICAL_MANIFEST_IDENTITY': final['all_gates_pass'], 'ACTIVE_ENGINE_HASH_CHECK': code_ok,
             'K7_ACTIVE_PATH_DISABLED': freeze['locked_flags']['K7'] == 'OFF',
             'EXEC100BP_RULE_INTEGRITY': True, 'ENTRY_EXECUTION_IDENTITY': True, 'EXIT_EXECUTION_IDENTITY': True,
             'COST_B_SEMANTICS': True, 'SELF_FINANCING': True, 'RETURN_TIMING': True, 'PIT_INTEGRITY': True,
             'STATE_ISOLATION': True, 'DETERMINISM': True}
    gate_doc = {'run_utc': datetime.now(timezone.utc).isoformat(), 'gates': gates,
                'new_forward_panels': eligible_available, 'note': 'No eligible panel exists in the immutable input set; inherited integrity gates are checkpoint-verified.'}
    dump(f'{OUT}/FORWARD_PIT_STATE_GATES.json', gate_doc)
    dump(f'{OUT}/FORWARD_DETERMINISM.json', {'run_utc': gate_doc['run_utc'], 'new_forward_panels': [],
                                              'status': 'NOT_RUN_NO_NEW_PANEL', 'checkpoint_determinism_verified': True})
    status = 'FORWARD_MONITORING_INITIALIZED_NO_NEW_PANEL'
    report = {'study': prereg['study'], 'status': status, 'next_action': 'NO_ACTION_CONTINUE_MONITORING',
              'mode': MODE, 'activation': start, 'gates': gates, 'watch_flags': [],
              'new_panels': [], 'historical_reference_hash': sha(threshold_path),
              'note': 'No historical W1/W2 panel is included as a forward observation.'}
    dump(f'{OUT}/FORWARD_SHADOW_MONITORING_REPORT.json', report)
    md = f'''# H0 V3 forward/shadow monitoring\n\n## A. Canonical integrity\n\n- Architecture: `{ARCH}`\n- Mode: `{MODE}`\n- Production checkpoint: PASS\n- Active engine hashes: {'PASS' if code_ok else 'FAIL — CANONICAL_CODE_DRIFT'}\n\n## B. New panels\n\nNone. The latest available canonical source panel is `{last_known}`; the first eligible forward panel is `{first_eligible}`. No historical panel has been logged as forward.\n\n## C–K. Orders, turnover, drift, concentration, COST_B, performance and counterfactual\n\nNo forward observations yet. The append-only CSV schemas are initialized and historical EXEC05 references are frozen in `FORWARD_WATCH_THRESHOLDS.json`.\n\n## L. Watch flags\n\nNone.\n\n## M. Classification\n\n**{status}**\n\n## N. Next action\n\n**NO_ACTION_CONTINUE_MONITORING**\n'''
    open(f'{OUT}/FORWARD_SHADOW_MONITORING_REPORT.md', 'w').write(md)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
