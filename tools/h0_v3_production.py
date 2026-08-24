"""H0 V3 CANONICAL PRODUCTION ENTRYPOINT.

Architecture ID : H0_V3_CANONICAL_K7OFF_EXEC05_100BP
Activated by    : CANONICAL_REPLACEMENT_APPROVED_K7OFF_EXEC05_100BP
Source decision : research_k/h0_v3_final_canonical_execution_architecture_decision/
                  CANONICAL_REPLACEMENT_DECISION.json

Active architecture:
  K1 52/78w momentum -> K2 canonical cadence -> K3 retain/refill -> K4a SMA200
  -> K4b OFF -> K5 inverse-vol^1.5 -> K6 confirmation -> K7 OFF (legacy
  clip/renormalization bypassed) -> Weight Preservation ON (state-dependent)
  -> EXEC05_BAND_100BP no-trade band on continuing holdings
  -> canonical entries/exits (always execute).

Approved behavioral changes vs superseded architecture (exactly two):
  1. K7 legacy clip/renormalization disabled on the active target path.
  2. EXEC05 100BP no-trade band for continuing holdings
     (absolute pre-trade weight deviation >= 0.01 executes to desired target,
      < 0.01 suppressed; boundary deviation == 0.01 executes).

Engine reuse (no parallel implementations): the production path calls the
validated frozen candidate engine functions directly:
  targets   : run_h0_v3_weight_layer_simplification_v2.compute_targets_pipeline
              invoked with k7=0 (identical to frozen K7_OFF candidate path)
  execution : run_h0_v3_transaction_minimization_frontier.run_band_arm
              mode='band', band=0.01 (the exact frozen EXEC05 implementation)
"""

import argparse
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

V2 = importlib.import_module('run_h0_v3_weight_layer_simplification_v2')
FR = importlib.import_module('run_h0_v3_transaction_minimization_frontier')

ARCHITECTURE_ID = 'H0_V3_CANONICAL_K7OFF_EXEC05_100BP'
CANDIDATE_ARM_ID = 'EXEC05_BAND_100BP'
K7_ACTIVE = False
K4B_ACTIVE = False
K5_ACTIVE = True
K6_ACTIVE = True
WP_ACTIVE = True
EXECUTION_BAND_ACTIVE = True
EXECUTION_BAND_ABS_WEIGHT = 0.01
TRADE_TO_TARGET_WHEN_TRIGGERED = True
ENTRIES_ALWAYS_EXECUTE = True
EXITS_ALWAYS_EXECUTE = True


def load_engine():
    FR.load_contexts()
    return V2.CTX


def replay(window):
    assert not K7_ACTIVE
    assert EXECUTION_BAND_ABS_WEIGHT == 0.01 and EXECUTION_BAND_ACTIVE
    assert ENTRIES_ALWAYS_EXECUTE and EXITS_ALWAYS_EXECUTE and TRADE_TO_TARGET_WHEN_TRIGGERED
    ctx = V2.CTX[window]
    res = FR.run_band_arm(ctx, window, 'band', EXECUTION_BAND_ABS_WEIGHT,
                          CANDIDATE_ARM_ID, collect_ledger=True)
    return res


def path_hash(window, res):
    return {'window': window, 'sha256': FR.arm_hash(window, res),
            'arm_id': res['arm_id'], 'architecture': ARCHITECTURE_ID}


def metrics(window, res):
    m = V2.summarize_arm(res, None)
    years = V2.YEARS_CAL[window]
    oe = sum(p['orders_exec']['entries'] + p['orders_exec']['exits']
             + p['orders_exec']['cont_buy'] + p['orders_exec']['cont_sell']
             for p in res['panels'])
    cw = sum(p['orders_exec']['cont_buy'] + p['orders_exec']['cont_sell']
             for p in res['panels'])
    return {'architecture': ARCHITECTURE_ID, 'window': window,
            'cagr_gross_pct': 100.0 * ((1.0 + sum(res['ret_lists']['gross']) /
                                        len(res['ret_lists']['gross'])) ** (V2.PPY / len(res['ret_lists']['gross'])) - 1.0),
            'cagr_net_b_pct': 100.0 * ((1.0 + sum(res['ret_lists']['net_b']) /
                                        len(res['ret_lists']['net_b'])) ** (V2.PPY / len(res['ret_lists']['net_b'])) - 1.0),
            'sharpe_b': m['sharpe_b'], 'maxdd_b_pct': 100.0 * m['maxdd_b'],
            'orders_per_yr': oe / years, 'continuing_reweights_per_yr': cw / years,
            'turnover_ann_pct': 100.0 * sum(p['wt_exec'] for p in res['panels']) / years}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('windows', nargs='*', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    wins = a.windows or ['W1', 'W2']
    load_engine()
    out = {'architecture': ARCHITECTURE_ID, 'replays': {}}
    for w in wins:
        res = replay(w)
        h = path_hash(w, res)
        mt = metrics(w, res)
        out['replays'][w] = {'path_sha256': h['sha256'], **mt}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
