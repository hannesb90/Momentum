"""Source-level resolution for the corrected drawdown-exit P0 candidate.

No portfolio result is computed: the locked historical factorial selected no
DD policy, so choosing a threshold/replacement for a frozen-H0 replay would be
post-hoc intervention selection.
"""
import csv, hashlib, json
from pathlib import Path

ROOT=Path('/home/hannesb/momentum_v2')
GATE=ROOT/'research_k/h0_v3_architecture_revalidation_gate'
OUT=GATE/'P0_CORRECTED_DRAWDOWN_EXIT_REVALIDATION'
OLD=ROOT/'research_k/dd_heterogeneity_closure'
FACT=ROOT/'research_k/exit_architecture_factorial'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
    OUT.mkdir(exist_ok=True)
    decision=json.loads((FACT/'SELECTION_DECISION.json').read_text())
    verdict=json.loads((OLD/'SLUTDOM.json').read_text())
    evidence=[
      {'source':'dd_heterogeneity_closure/SLUTDOM.json','sha256':sha(OLD/'SLUTDOM.json'),'role':'authoritative canonical closure artifact','finding':'Overall event-level result: forward information exists, but no statistically supported/portfolio-material overall exit support; final verdict DD_CLOSED_NO_OVERALL_SUPPORT_BUT_HETEROGENEITY_SIGNAL.'},
      {'source':'dd_heterogeneity_closure/DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE_PREREGISTRATION.json','sha256':sha(OLD/'DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE_PREREGISTRATION.json'),'role':'corrected state and diagnostic definition','finding':'Peak since entry across holding period; T+1 execution; cash to next ordinary rebalance. This artifact is diagnostic and states BASE_MODELS_MODIFIED=NO.'},
      {'source':'exit_architecture_factorial/EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json','sha256':sha(FACT/'EXIT_ARCHITECTURE_FACTORIAL_PREREGISTRATION.json'),'role':'old portfolio factorial intervention family','finding':'Locked family DD10/DD20/DD30/DD40 x CASH/NEXT_RANKED, top-20/equal-weight custom motor and no frozen intermediate retain/refill or post-selection SMA architecture.'},
      {'source':'exit_architecture_factorial/SELECTION_DECISION.json','sha256':sha(FACT/'SELECTION_DECISION.json'),'role':'intervention selection gate','finding':f"Decision {decision['BESLUT']}; qualifying arms {decision['kvalificerande_armar']}; W2 run {decision['VALIDATION_KORD']}. Hence no individual corrected portfolio policy was locked for validation."},
      {'source':'exit_architecture_factorial/results_SELECTION.json','sha256':sha(FACT/'results_SELECTION.json'),'role':'old W1 result','finding':'W1 factorial only; not a frozen H0 V3 portfolio test.'},
    ]
    with (OUT/'SOURCE_EVIDENCE_MAP.csv').open('w',newline='') as f:
        q=csv.DictWriter(f,fieldnames=list(evidence[0]));q.writeheader();q.writerows(evidence)
    (OUT/'ESTIMAND_RESOLUTION.md').write_text('''# Corrected drawdown-exit estimand resolution

## A — DRAWDOWN_FORWARD_INFORMATION

At a first daily adjusted-price drawdown crossing for a currently held name, does its forward return from T+1 to the frozen horizon indicate adverse future information? The old source uses DD10/20/30/40 and reports several predeclared horizons. It is **PARTIAL** with respect to frozen H0: event return calculation is PIT/daily and does not use portfolio turnover accounting, but the old event population came from S1/S2/S3 top-20/equal-weight selection rather than frozen H0 V3 holdings.

## B — CORRECTED_DRAWDOWN_PORTFOLIO_EXIT

Does selling at the corrected daily drawdown crossing, holding cash to the next ordinary rebalance (or using the separately specified NEXT_RANKED arm), improve frozen H0 V3? This is **MATERIAL** architecture-dependent.

The historical portfolio artifact has no single policy to replay: it locked a factorial family, then selected **NO_EXIT_ARCHITECTURE_SELECTED** in W1 and explicitly prohibited W2. Selecting DD20, any other threshold, CASH, or NEXT_RANKED now would be a post-hoc new policy. Therefore no policy rerun is authorized by the frozen historical protocol.

## C — DRAWDOWN_HETEROGENEITY_DIAGNOSTIC

Predeclared volatility, size, sector, profitability, and liquidity diagnostics of forward event returns. It remains diagnostic-only; no interaction survived Holm, and the profitability signal has the source-documented survivorship limitation. It cannot rescue an overall policy.

`BUGGY_LEGACY_DRAWDOWN_EXIT` remains `INVALID_LEGACY_IMPLEMENTATION` and is not rerun.
''')
    prereg={'study':'CORRECTED_DRAWDOWN_EXIT_ARCHITECTURE_REVALIDATION_RESOLUTION','status':'BLOCKED_BEFORE_EMPIRICAL_POLICY_RERUN','reason':'The locked corrected factorial selected NO_EXIT_ARCHITECTURE_SELECTED; no historical single policy exists to replay without post-hoc choice.','permitted_actions':['source-level estimand split','architecture-dependence classification','canonical update proposal only'],'forbidden_actions':['choose DD threshold','choose cash vs next-ranked','run W2 policy after old W1 stop','run portfolio policy','change frozen H0 V3']}
    dump(OUT/'PREREGISTRATION.json',prereg)
    (OUT/'PREREGISTRATION.md').write_text('# Corrected drawdown-exit architecture revalidation\n\nThis is a source-resolution stop, not an empirical portfolio rerun. The historical corrected factorial selected no intervention; no threshold or replacement policy may be chosen post hoc.\n')
    freeze={'prereg_sha256':sha(OUT/'PREREGISTRATION.json'),'frozen_h0_source_sha256':sha(ROOT/'tools/h0_v3_kor.py'),'adapter_sha256':sha(ROOT/'tools/frozen_h0_v3_policy_adapter.py'),'selection_decision_sha256':sha(FACT/'SELECTION_DECISION.json'),'no_empirical_policy_rerun':True,'no_parameter_changes':True,'no_subgroup_rescue':True}
    dump(OUT/'PLAN_FREEZE.json',freeze)
    dump(OUT/'BASE_REPRODUCTION.json',{'BASE_ARCHITECTURE_REPRODUCTION_PASS':None,'status':'NOT_RUN__NO_FROZEN_PORTFOLIO_INTERVENTION_EXISTS','reason':prereg['reason']})
    with (OUT/'EVENT_IDENTITY_RECONCILIATION.csv').open('w') as f:
        f.write('window,old_event_count,frozen_event_count,matched_events,dropped_events,newly_added_events,status\\n')
        f.write('W1,,,,,,NOT_RUN__no_predeclared_individual_policy\\nW2,,,,,,NOT_RUN__old_W1_gate_prohibited_W2\\n')
    dump(OUT/'FORWARD_INFORMATION_RESULT.json',{'verdict':'FORWARD_INFORMATION_REQUIRES_FROZEN_H0_SAME_ESTIMAND_REPLICATION','old_artifact_verdict':verdict['PRIMARY_OVERALL']['TOLKNING'],'architecture_dependence':'PARTIAL','portfolio_rerun_performed':False})
    dump(OUT/'PORTFOLIO_RESULT.json',{'verdict':'ARCHITECTURE_REVALIDATED__DD_EXIT_BLOCKED','reason':prereg['reason'],'old_selection_decision':decision['BESLUT'],'W2_policy_run_prohibited_by_old_gate':not decision['VALIDATION_KORD']})
    dump(OUT/'HETEROGENEITY_RESULT.json',{'status':'UNCHANGED_DIAGNOSTIC_ONLY','old_final_status':verdict['SECONDARY_HETEROGENEITY']['profitability']['klass'],'changes_overall_verdict':False,'overall_verdict':verdict['DEL10_SLUTDOM']})
    with (OUT/'DD_EVENT_LEDGER.csv').open('w') as f: f.write('status,reason\nNOT_RUN,No predeclared individual corrected portfolio policy exists\n')
    with (OUT/'CORRECTED_DD_OLD_VS_REVALIDATED.csv').open('w') as f: f.write('metric,old_W1,new_W1,delta_W1,old_W2,new_W2,delta_W2\npolicy_selection,NO_EXIT_ARCHITECTURE_SELECTED,NOT_RUN,,,,\n')
    result={'mechanism':'CORRECTED_DRAWDOWN_EXIT','status':'ARCHITECTURE_REVALIDATION_BLOCKED','buggy_legacy_status':'INVALID_LEGACY_IMPLEMENTATION','forward_information_architecture_dependence':'PARTIAL','portfolio_architecture_dependence':'MATERIAL','old_authoritative_artifact':'research_k/dd_heterogeneity_closure/SLUTDOM.json','old_portfolio_verdict':'CLOSED_CLEAN_NULL (canonical interpretation, now pending architecture revalidation for portfolio component)','old_forward_information_verdict':verdict['PRIMARY_OVERALL']['TOLKNING'],'old_factorial_selection_decision':decision['BESLUT'],'old_factorial_w2_run':decision['VALIDATION_KORD'],'blocking_condition':prereg['reason'],'proposed_canonical_status':'PENDING_ARCHITECTURE_REVALIDATION__NO_FROZEN_HISTORICAL_INTERVENTION_TO_REPLAY','canonical_master_modified':False}
    dump(OUT/'RESULT.json',result)
    (OUT/'SUMMARY.md').write_text('# Corrected drawdown-exit architecture revalidation\n\n**Blocked before any policy computation.** The old corrected factorial was a frozen DD10/20/30/40 × CASH/NEXT_RANKED family, not a single intervention. Its locked W1 selection decision was `NO_EXIT_ARCHITECTURE_SELECTED`, so W2 was prohibited. A frozen-H0 rerun needs a separately authorized preregistration selecting a single new policy; this study did not do that.\n')
    # Append a non-destructive proposal only.
    p=GATE/'ARCHITECTURE_REVALIDATION_CANONICAL_UPDATE_PROPOSAL.csv'; rows=list(csv.DictReader(p.open()))
    rows=[r for r in rows if r['mechanism']!='CORRECTED_DRAWDOWN_EXIT']
    rows.append({'mechanism':'CORRECTED_DRAWDOWN_EXIT','old_canonical_status':'CLOSED_CLEAN_NULL (portfolio component)','new_revalidation_evidence':'Source-level resolution: historical corrected factorial selected NO_EXIT_ARCHITECTURE_SELECTED; no W2 policy run and no single frozen intervention exists to replay.','proposed_new_status':'PENDING_ARCHITECTURE_REVALIDATION__NO_FROZEN_HISTORICAL_INTERVENTION_TO_REPLAY','reason':'Portfolio closure cannot be labelled frozen-H0 evidence, but choosing a policy now would be post-hoc. Forward/heterogeneity evidence remains separately diagnostic.','canonical_map_modified':'FALSE'})
    fields=['mechanism','old_canonical_status','new_revalidation_evidence','proposed_new_status','reason','canonical_map_modified']
    with p.open('w',newline='') as f:q=csv.DictWriter(f,fieldnames=fields);q.writeheader();q.writerows(rows)
    gate_result_path=GATE/'GATE_RESULT.json'
    gate_result=json.loads(gate_result_path.read_text())
    gate_result['corrected_drawdown_exit_revalidation']={
        'completed_source_resolution':True,
        'empirical_policy_rerun_performed':False,
        'status':result['status'],
        'result_sha256':sha(OUT/'RESULT.json'),
        'prereg_sha256':sha(OUT/'PREREGISTRATION.json'),
        'reason':result['blocking_condition'],
        'canonical_master_modified':False,
        'stop_after_this_mechanism':True,
    }
    dump(gate_result_path,gate_result)
    (GATE/'SUMMARY.md').write_text('# H0 V3 architecture revalidation gate\n\n'
        'Completed empirical P0 reruns: `REENTRY_SCORE_IMPROVEMENT` and `EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER`. '
        '`CORRECTED_DRAWDOWN_EXIT` completed source-level resolution but is blocked before a portfolio rerun: its historical corrected factorial chose '
        '`NO_EXIT_ARCHITECTURE_SELECTED`, so no individual legacy policy may be selected post hoc. No canonical master was modified and no further P0 ran.\n')

if __name__=='__main__': main()
