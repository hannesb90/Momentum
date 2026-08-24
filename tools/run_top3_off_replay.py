"""Materialise deterministic frozen-H0/OFF decision logs for the Top3 pre-ON gate.

No selection hook is supplied.  Consequently this is strictly a BASE/OFF
reproduction run and does not evaluate, emit, or inspect an ON policy path.
"""
import hashlib, json
from pathlib import Path
from frozen_h0_v3_policy_adapter import run_window

OUT=Path('/home/hannesb/momentum_v2/research_k/h0_v3_top3_winner_protection_audit')

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=True)

def digest(obj): return hashlib.sha256(canonical(obj).encode()).hexdigest()

def main(number):
    decisions=[]
    for window in ('W1','W2'):
        rows,_=run_window(window, hook=None)
        for row in rows:
            decisions.append({
                'window':window, 'panel_index':row['panel_index'], 'decision_timestamp':str(row['date']),
                'panel_type':row['panel_type'],
                # In OFF mode the hook has no state and no protection decision.
                'available_completed_return_windows':[], 'incoming_policy_state':{'mode':'OFF'},
                'ranking_pre_sma_selection':row['selected_pre_sma'], 'protected_set':[],
                'ordinary_fresh_candidates':row['selected_pre_sma'] if row['panel_type']=='ORDINARY_PANEL' else [],
                'displacement':[], 'final_selection':row['holdings'],
                'outgoing_policy_state':{'mode':'OFF'},
            })
    payload={'mode':'FROZEN_H0_OFF','run_number':number,'policy_decisions':decisions,
             'n_decisions':len(decisions)}
    payload['policy_digest']=digest({'mode':payload['mode'],'policy_decisions':decisions})
    path=OUT/f'H0_REPLAY_{number}.json'
    path.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'path':str(path),'digest':payload['policy_digest'],'n':len(decisions)}))

if __name__=='__main__':
    import sys
    main(int(sys.argv[1]))
