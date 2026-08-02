"""Resume adapter: reopens blockers when a current-contract runner appears."""
from __future__ import annotations
import json
from pathlib import Path
import nightly_master_queue_2026_08_01 as queue

def main():
    state=queue.load_state()
    table=__import__('pandas').read_csv(queue.QUEUE_CSV)
    changed=False
    for row in table.itertuples(index=False):
        candidate=f"run_{row.mechanism_key}_current.py"
        path=queue.ML/candidate
        if path.exists():
            queue.RUNNERS[row.mechanism_key]=candidate
            old=state.get('items',{}).get(row.mechanism_key,{})
            if old.get('status')=='BLOCKED_IMPLEMENTATION':
                state['items'].pop(row.mechanism_key,None);changed=True
    if changed:
        state.pop('finished_at',None);state.pop('final_chain',None);state.pop('production_hashes_at_end',None)
        queue.atomic_json(queue.STATE,state)
    return queue.main()
if __name__=='__main__':raise SystemExit(main())
