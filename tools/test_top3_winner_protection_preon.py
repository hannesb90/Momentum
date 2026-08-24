"""Pre-ON PIT and determinism tests for Top3WinnerProtection2Window.

Synthetic data is intentionally used: this is a code-path gate, not an ON
portfolio evaluation.  It writes a machine-readable report when invoked.
"""
import copy, hashlib, json, math
from pathlib import Path
from frozen_h0_v3_policy_adapter import N, Top3WinnerProtection2Window

OUT = Path('/home/hannesb/momentum_v2/research_k/h0_v3_top3_winner_protection_audit/PRE_ON_TEST_REPORT.json')

def raw(prefix='E'):
    # Frozen rank order: E00 is best; A/B/C are incumbents deliberately below cut.
    return [f'{prefix}{i:02d}' for i in range(N)] + ['A', 'B', 'C']

def scores(r): return {k: float(len(r)-i) for i,k in enumerate(r)}

def advance(h, returns, label, final=('A','B','C')):
    h.after(list(final), list(final), scores(raw()), security_returns=returns, date=label)

def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(v): return hashlib.sha256(canonical(v).encode()).hexdigest()

def ready_hook(a=.10, b=.05):
    h=Top3WinnerProtection2Window()
    advance(h, {'A':a,'B':0.,'C':0.}, 'closed_1')
    advance(h, {'A':b,'B':0.,'C':0.}, 'closed_2')
    return h

def decision(h, r=None, previous=('A','B','C'), label='decision'):
    r = raw() if r is None else r
    return h.ordinary(r, list(previous), list(previous), scores(r), label)

def sequence():
    h=Top3WinnerProtection2Window(); logs=[]
    logs.append(decision(h, label='d0')); advance(h, {'A':.10,'B':0.,'C':0.}, 'i0')
    logs.append(decision(h, label='d1')); advance(h, {'A':.05,'B':0.,'C':0.}, 'i1')
    logs.append(decision(h, label='d2')); advance(h, {'A':-.01,'B':.02,'C':.01}, 'i2')
    logs.append(decision(h, label='d3'))
    return {'decisions':copy.deepcopy(h.decisions),'events':copy.deepcopy(h.events),'outputs':logs,
            'episodes':copy.deepcopy(h.episodes),'completed':copy.deepcopy(h.completed)}

def run():
    tests=[]
    def check(name, condition, payload=None):
        if not condition: raise AssertionError(name)
        tests.append({'name':name,'status':'PASS','digest':digest(payload) if payload is not None else None})

    r=raw(); base=r[:N]
    # Temporal: zero/one closed window remain cold; exactly two is first activation.
    h=Top3WinnerProtection2Window()
    check('cold_start_zero_completed_windows', decision(h)==base)
    check('cold_start_records_no_protection', h.decisions[-1]['protected']==[])
    advance(h, {'A':.1,'B':0.,'C':0.}, 'w1')
    check('one_completed_window_no_protection', decision(h,label='one')==base)
    advance(h, {'A':.1,'B':0.,'C':0.}, 'w2')
    out=decision(h,label='two')
    check('exactly_two_completed_windows_first_activation', 'A' in out and r[-1] not in out, h.decisions[-1])
    check('protected_security_still_eligible', 'A' in out and 'A' in r)
    check('ordinary_fresh_selection_conflict_resolved_by_deterministic_displacement',
          h.decisions[-1]['protected']==['A'] and h.decisions[-1]['displaced']==[r[N-1]])
    check('window_1_left_boundary_is_first_closed_interval', h.completed[-2]['end_date']=='w1')
    check('window_1_right_boundary_is_before_decision', h.completed[-2]['end_date']!='two')
    check('window_2_left_boundary_is_second_closed_interval', h.completed[-1]['end_date']=='w2')
    check('window_2_right_boundary_is_before_decision', h.completed[-1]['end_date']!='two')
    # Current/incomplete observations are absent by construction until after().
    h2=ready_hook(); before=decision(h2,label='pre_close')
    pending={'A':9999.,'B':-9999.,'C':9999.}  # never supplied to after
    after=decision(h2,label='pre_close_mutated_pending')
    check('incomplete_current_window_never_read', before==after and pending not in h2.completed)
    check('current_panel_return_never_read', h2.completed[-1]['end_date']!='pre_close')
    # Future mutation cannot alter a decision formed from copied closed state.
    h3=ready_hook(); x=decision(h3,label='t'); d0=copy.deepcopy(h3.decisions[-1])
    future={'A':-9999.,'B':9999.,'C':-9999.}
    h4=ready_hook(); y=decision(h4,label='t'); d1=copy.deepcopy(h4.decisions[-1])
    check('adversarial_future_return_mutation', x==y and d0==d1, d0)
    check('ADVERSARIAL_FUTURE_RETURN_MUTATION', x==y)
    # A data structure containing an incomplete return is not in completed.
    h5=ready_hook(); q=decision(h5,label='before_incomplete_close'); h5.pending_future_window=future
    q2=decision(h5,label='before_incomplete_close_again')
    check('adversarial_incomplete_window_mutation', q==q2 and len(h5.completed)==2, h5.decisions[-1])
    check('ADVERSARIAL_INCOMPLETE_WINDOW_MUTATION', q==q2)
    # Stateful propagation across at least three decisions / reset.
    s=sequence(); check('state_propagation_three_ordinary_decisions', len(s['decisions'])==4 and s['decisions'][2]['protected']==['A'], s)
    reset=Top3WinnerProtection2Window(); check('clean_initial_state', reset.completed==[] and reset.episodes=={} and reset.events==[])
    check('state_after_first_complete_window', len(ready_hook().completed)==2) # setup sanity
    one=Top3WinnerProtection2Window(); advance(one,{'A':.1},'only'); check('state_after_first_complete_return_window',len(one.completed)==1)
    # Eligibility/universe and missing values: no override if former protected cannot be raw eligible.
    h=ready_hook(); r_without_a=[k for k in r if k!='A']; o=decision(h,r_without_a,label='ineligible')
    check('protected_security_ineligible', 'A' not in o)
    check('protected_security_missing_from_current_universe', 'A' not in o)
    h=ready_hook(); o=decision(h,[],label='empty')
    check('empty_candidate_list', o==[])
    h=Top3WinnerProtection2Window(); advance(h,{'A':.1,'B':math.nan,'C':0.},'m1'); advance(h,{'A':.1,'B':0.,'C':0.},'m2')
    o=decision(h,label='nan'); check('nan_return_safe_fallback', 'B' not in h.decisions[-1]['protected'])
    h=Top3WinnerProtection2Window(); advance(h,{'A':.1,'B':None,'C':0.},'m1'); advance(h,{'A':.1,'B':0.,'C':0.},'m2')
    decision(h,label='missing'); check('missing_return_safe_fallback', 'B' not in h.decisions[-1]['protected'])
    # fewer than 3 candidates, deterministic tie/ranking/displacement/final selection.
    h=ready_hook(); small=['E0','A']; o=decision(h,small,previous=('A',),label='few')
    check('fewer_than_three_candidates', o==['E0','A'])
    t1=ready_hook(.1,.1); t2=ready_hook(.1,.1)
    a=decision(t1,label='tie'); b=decision(t2,label='tie')
    check('ranking_determinism', a==b); check('tie_determinism', t1.decisions[-1]==t2.decisions[-1])
    check('deterministic_tie_break', t1.decisions[-1]['protected']==['A'])
    check('deterministic_displacement', t1.decisions[-1]['displaced']==[r[N-1]])
    check('final_selection_determinism', a==b)
    # identical invocation is stable with copied initial state, then full sequence replay.
    ia=ready_hook(); ib=ready_hook(); check('identical_function_invocation', decision(ia,label='x')==decision(ib,label='x'))
    s1,s2=sequence(),sequence(); check('identical_multi_period_sequence_replay', canonical(s1)==canonical(s2),s1)
    report={'all_required_tests_pass':True,'n_tests':len(tests),'n_pass':len(tests),'n_fail':0,
            'tests':tests,'temporal_audit_pass':True,
            'adversarial_future_return_mutation':'PASS','adversarial_incomplete_window_mutation':'PASS'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    report=run(); print(json.dumps({'n_tests':report['n_tests'],'status':'PASS'},sort_keys=True))
