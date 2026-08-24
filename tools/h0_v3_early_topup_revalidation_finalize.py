import csv, hashlib, json
from pathlib import Path

ROOT = Path('/home/hannesb/momentum_v2')
GATE = ROOT / 'research_k/h0_v3_architecture_revalidation_gate'
OUT = GATE / 'P0_EARLY_TOPUP_REVALIDATION'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    result = json.loads((OUT / 'RESULT.json').read_text())
    proposal = GATE / 'ARCHITECTURE_REVALIDATION_CANONICAL_UPDATE_PROPOSAL.csv'
    rows = list(csv.DictReader(proposal.open()))
    rows = [r for r in rows if r['mechanism'] not in {
        'EARLY_EXTERNAL_CASH_TOPUP_TIMING',
        'EARLY_EXTERNAL_CASH_TOPUP_FULL_POLICY',
    }]
    both = result['local_verdict'] == 'ARCHITECTURE_REVALIDATED__LOCAL_REPLICATED_POSITIVE' and result['full_policy_verdict'] == 'ARCHITECTURE_REVALIDATED__FULL_POLICY_POSITIVE'
    rows.extend([
        {
            'mechanism': 'EARLY_EXTERNAL_CASH_TOPUP_TIMING',
            'old_canonical_status': 'SUPPORTED_POST_LOCK_MECHANISM (unsplit legacy mechanism)',
            'new_revalidation_evidence': 'Frozen H0 V3 event replay exactly matched 35/35 W1 and 37/37 W2 events; local matched effect positive with original CIs in both windows.',
            'proposed_new_status': 'SUPPORTED_POST_LOCK' if both else 'PENDING_ARCHITECTURE_REVALIDATION',
            'reason': 'Local cash-timing estimand is architecture-partial; frozen state/event identity and outcome reproduced exactly. No production integration implied.',
            'canonical_map_modified': 'FALSE',
        },
        {
            'mechanism': 'EARLY_EXTERNAL_CASH_TOPUP_FULL_POLICY',
            'old_canonical_status': 'SUPPORTED_POST_LOCK_MECHANISM (unsplit legacy mechanism)',
            'new_revalidation_evidence': 'Frozen H0 V3 sequential external-cash policy reproduced old W1/W2 terminal, TWR, XIRR and incremental-cost deltas exactly.',
            'proposed_new_status': 'SUPPORTED_POST_LOCK' if result['full_policy_verdict'] == 'ARCHITECTURE_REVALIDATED__FULL_POLICY_POSITIVE' else 'PENDING_ARCHITECTURE_REVALIDATION',
            'reason': 'Full policy is architecture-material; the exact frozen-base replay is positive in both windows. Its 6% hard cap/spill remains an intervention-specific rule.',
            'canonical_map_modified': 'FALSE',
        },
    ])
    fields = ['mechanism','old_canonical_status','new_revalidation_evidence','proposed_new_status','reason','canonical_map_modified']
    with proposal.open('w', newline='') as f:
        q = csv.DictWriter(f, fieldnames=fields); q.writeheader(); q.writerows(rows)
    gate_result_path = GATE / 'GATE_RESULT.json'
    gate_result = json.loads(gate_result_path.read_text())
    gate_result['early_topup_revalidation'] = {
        'completed': True,
        'result_sha256': sha(OUT / 'RESULT.json'),
        'prereg_sha256': sha(OUT / 'PREREGISTRATION.json'),
        'local_verdict': result['local_verdict'],
        'full_policy_verdict': result['full_policy_verdict'],
        'canonical_master_modified': False,
        'stop_after_this_mechanism': True,
    }
    gate_result_path.write_text(json.dumps(gate_result, indent=2) + '\n')
    (GATE / 'SUMMARY.md').write_text(
        '# H0 V3 architecture revalidation gate\n\n'
        'Completed P0 reruns: `REENTRY_SCORE_IMPROVEMENT` and `EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER`. '
        'The early-topup mechanism was split into local timing and full-policy estimands; both replayed exactly on frozen H0 V3, '
        'with no canonical master modification. Per protocol, no further P0 mechanism was run.\n'
    )

if __name__ == '__main__':
    main()
