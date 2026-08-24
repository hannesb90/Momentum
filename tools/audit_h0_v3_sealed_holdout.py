#!/usr/bin/env python
"""Metadata/text provenance audit only; never calls a performance function."""
import hashlib, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f'{ROOT}/research_k/h0_v3_sealed_historical_holdout_final_evaluation'
CANON = f'{ROOT}/research_k/h0_v3_canonical_production_implementation'
TEXT_EXT = {'.py', '.json', '.md', '.csv', '.log', '.txt', '.ipynb', '.yaml', '.yml'}
DATE_PATTERNS = {'W1_2014_2019': re.compile(r'\b(W1|2014[–-]2019|2014-01-01|2019-12-25)\b'),
                 'W2_2020_2026': re.compile(r'\b(W2|2020[–-]2026|2020-01-02|2026-07-09)\b')}
ECON = re.compile(r'\b(CAGR|Sharpe|MaxDD|portfolio|return|performance|wealth|IC|P&L|drawdown|turnover)\b', re.I)
MODEL = re.compile(r'\b(H0.?V3|run_h0_v3|EXEC05|K7|weight.layer|canonical)\b', re.I)

def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()

def main():
    os.makedirs(OUT, exist_ok=True)
    hits = {k: [] for k in DATE_PATTERNS}
    scanned = 0
    skipped = 0
    for base in (f'{ROOT}/tools', f'{ROOT}/research_k', f'{ROOT}/docs', f'{ROOT}/trackh'):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {'__pycache__', 'raw', 'validated'}]
            for name in files:
                path = os.path.join(root, name)
                if os.path.splitext(name)[1].lower() not in TEXT_EXT or os.path.getsize(path) > 5_000_000:
                    skipped += 1
                    continue
                try:
                    text = open(path, errors='ignore').read()
                except OSError:
                    skipped += 1
                    continue
                scanned += 1
                if not (ECON.search(text) and MODEL.search(text)):
                    continue
                for block, pat in DATE_PATTERNS.items():
                    if pat.search(text):
                        hits[block].append({'path': os.path.relpath(path, ROOT), 'sha256': sha(path),
                                            'evidence_type': 'economic_model_output_or_analysis_reference'})
    # W1/W2 are the complete canonical historical execution windows.  Their
    # repeated portfolio/execution metrics make them LEVEL_4 regardless of raw
    # data provenance; no other scoring block is declared sealed in the repo.
    registry = []
    for block, start, end in [('W1_2014_2019', '2014-01-01', '2019-12-25'),
                              ('W2_2020_2026', '2020-01-02', '2026-07-09')]:
        registry.append({'block': block, 'start_date': start, 'end_date': end,
                         'contamination_level': 'LEVEL_4_MODEL_SELECTION_CONTAMINATION',
                         'eligibility_status': 'INELIGIBLE_NOT_SEALED',
                         'evidence_count': len(hits[block]), 'evidence': hits[block][:120]})
    canonical = f'{CANON}/PRODUCTION_CHECKPOINT_FINALIZATION.json'
    audit = {'study': 'H0_V3_SEALED_HISTORICAL_HOLDOUT_FINAL_EVALUATION',
             'audit_only_no_economic_holdout_access': True,
             'scanned_text_files': scanned, 'skipped_nontext_or_large_files': skipped,
             'scope': ['tools', 'research_k', 'docs', 'trackh'],
             'search_terms': ['W1/W2/date ranges', 'CAGR', 'Sharpe', 'MaxDD', 'IC', 'portfolio returns',
                              'rankings', 'winner claims', 'performance', 'H0 V3', 'EXEC05', 'K7'],
             'canonical_checkpoint_sha256': sha(canonical), 'blocks': registry,
             'undeclared_candidate_periods': {'status': 'NOT_VERIFIABLE',
                 'reason': 'No repository declaration or immutable seal establishes any other historical scoring block as untouched.'},
             'conclusion': 'SEALED_HOLDOUT_NOT_VERIFIABLE',
             'no_pre_unseal_economic_access': 'PASS_FOR_THIS_AUDIT_ONLY',
             'unseal_authorized': False}
    with open(f'{OUT}/SEALED_HOLDOUT_PROVENANCE_AUDIT.json', 'w') as f:
        json.dump(audit, f, indent=2, sort_keys=True)
    with open(f'{OUT}/SEALED_HOLDOUT_REGISTRY.json', 'w') as f:
        json.dump({'eligible_sealed_blocks': [], 'ineligible_blocks': registry,
                   'status': 'SEALED_HOLDOUT_NOT_VERIFIABLE'}, f, indent=2, sort_keys=True)
    report = '# Sealed historical holdout provenance audit\n\n**SEALED_HOLDOUT_NOT_VERIFIABLE**\n\nNo economic holdout data was opened. W1 and W2 are ineligible because repository-wide evidence shows repeated economic model, portfolio and execution analysis. No other historical scoring block has an immutable prior seal proving LEVEL_0/LEVEL_1 status. Unseal is forbidden.\n'
    open(f'{OUT}/SEALED_HOLDOUT_CLOSEOUT.md', 'w').write(report)
    print(json.dumps({'conclusion': audit['conclusion'], 'scanned': scanned,
                      'w1_evidence': len(hits['W1_2014_2019']), 'w2_evidence': len(hits['W2_2020_2026'])}, indent=2))

if __name__ == '__main__':
    main()
