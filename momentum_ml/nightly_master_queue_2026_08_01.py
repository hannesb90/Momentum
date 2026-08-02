"""Unattended, resumable queue for every remaining deduplicated research mechanism.

Fail-closed rules:
* validate N2 and N3 recursively before and after every item;
* snapshot production artifacts and reject any mutation;
* a successful economic runner must advance N3 by exactly one child manifest;
* unavailable current-method runners are BLOCKED_IMPLEMENTATION, never PASS;
* continue after FAIL/BLOCKED/TIMEOUT and journal every outcome atomically.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, signal, subprocess, time
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; ML=ROOT/'momentum_ml'; PY=ROOT/'.allocation-test-venv/bin/python'
RUN_DIR=ROOT/'results/nightly_master_2026-08-01'; STATE=RUN_DIR/'state.json'
QUEUE_CSV=ROOT/'results/research_master_queue_2026_08_01_v2.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
TIMEOUT=6*3600
PRODUCTION=(ROOT/'results/lgbm_model.pkl',ROOT/'results/lstm_model.pt',ROOT/'results/signals.csv',ROOT/'results/stats.json')
COMPLETED={'baseline_pipeline_parity','conditional_52_13','regime_cross_section_interaction','generic_model_gate','statistical_reality_check'}
# Add only runners explicitly rewritten against the current frozen N3 contract.
RUNNERS={}

def now(): return dt.datetime.now().astimezone().isoformat(timespec='seconds')
def sha(p):
    if not p.exists(): return None
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()
def production_hashes(): return {str(p.relative_to(ROOT)):sha(p) for p in PRODUCTION}
def atomic_json(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');os.replace(tmp,path)
def load_state(): return json.loads(STATE.read_text()) if STATE.exists() else {'created_at':now(),'items':{},'production_hashes_at_start':production_hashes()}
def chain():
    code=("from pathlib import Path;from niva3_stage_control import verify_latest;"
          "from niva2_stage_control import verify_manifest as v2;import json;"
          "n3=verify_latest();n2=v2(Path('results/niva2_stages/07_forward_preregistration.json'));"
          "print(json.dumps({'n3_stage':n3['stage'],'n3_hash':n3['manifest_sha256'],'n2_hash':n2['manifest_sha256']}))")
    p=subprocess.run([str(PY),'-c',code],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ML)},capture_output=True,text=True,check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])
def journal(name,status,seconds,log,detail,before=None,after=None):
    line=(f"\n- `{now()}` **MASTER-NATTKÖ `{name}`: {status}** ({seconds/60:.1f} min), "
          f"logg: `{log.relative_to(ROOT)}` — {detail}; N3 "
          f"`{(before or {}).get('n3_hash','?')[:12]}`→`{(after or {}).get('n3_hash','?')[:12]}`.\n")
    for doc in DOCS:
        with doc.open('a',encoding='utf-8') as f:f.write(line)
def finish_item(state,name,status,start,log,detail,before,after=None,rc=None):
    sec=time.monotonic()-start;state['items'][name]={'status':status,'finished_at':now(),'duration_seconds':round(sec,3),'returncode':rc,'log':str(log.relative_to(ROOT)),'detail':detail,'chain_before':before,'chain_after':after};atomic_json(STATE,state);journal(name,status,sec,log,detail,before,after)
def run_one(row,state):
    name=row.mechanism_key
    if state['items'].get(name,{}).get('status') in {'PASS','COMPLETED_BEFORE_QUEUE','BLOCKED_DATA_GATE','BLOCKED_IMPLEMENTATION'}: return
    start=time.monotonic();log=RUN_DIR/f'{int(row.queue_order):02d}_{name}.log';before=chain()
    state['items'][name]={'status':'RUNNING','started_at':now(),'queue_order':int(row.queue_order),'sr_links':row.sr_links,'chain_before':before};atomic_json(STATE,state)
    if name in COMPLETED:
        log.write_text('Covered by current frozen N3 stages or current methodology gates before this queue.\n',encoding='utf-8')
        return finish_item(state,name,'COMPLETED_BEFORE_QUEUE',start,log,'already frozen/current; no duplicate run',before,before)
    if row.status=='BLOCKED_DATA_GATE':
        log.write_text(f'Data gate unresolved. Historical scripts: {row.historical_scripts}\n',encoding='utf-8')
        return finish_item(state,name,'BLOCKED_DATA_GATE',start,log,'PIT/event data prerequisite unresolved',before,before)
    runner=RUNNERS.get(name)
    if runner is None:
        log.write_text(f'No current-contract runner. Historical scripts are retained but stale:\n{row.historical_scripts}\n',encoding='utf-8')
        return finish_item(state,name,'BLOCKED_IMPLEMENTATION',start,log,'requires current N3 method rewrite; stale script not executed',before,before)
    cmd=[str(PY),str(ML/runner)];rc=None
    with log.open('a',encoding='utf-8') as f:
        f.write(f'[{now()}] START {cmd!r}\n');f.flush();p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONPATH':str(ML),'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        try: rc=p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30);after=chain();return finish_item(state,name,'TIMEOUT',start,log,'>6h',before,after)
    after=chain();prod=production_hashes()
    if prod!=state['production_hashes_at_start']:
        return finish_item(state,name,'CONTAMINATION_FAIL',start,log,'production artifact hash changed; queue stopped fail-closed',before,after,rc)
    if rc!=0:return finish_item(state,name,'FAIL',start,log,f'exit={rc}',before,after,rc)
    if after['n3_hash']==before['n3_hash']:return finish_item(state,name,'FAIL_NO_FREEZE',start,log,'runner exited 0 without advancing frozen N3 chain',before,after,rc)
    return finish_item(state,name,'PASS',start,log,'runner passed, froze one current-contract child stage',before,after,rc)
def main():
    RUN_DIR.mkdir(parents=True,exist_ok=True);state=load_state();atomic_json(STATE,state)
    q=pd.read_csv(QUEUE_CSV).sort_values('queue_order')
    for row in q.itertuples(index=False):
        run_one(row,state)
        if state['items'].get(row.mechanism_key,{}).get('status')=='CONTAMINATION_FAIL':break
    state['finished_at']=now();state['final_chain']=chain();state['production_hashes_at_end']=production_hashes();atomic_json(STATE,state)
    summary=RUN_DIR/'queue_complete.log';summary.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8');journal('queue_complete','DONE',0,summary,'all runnable items attempted; blockers retained',state.get('final_chain'),state.get('final_chain'))
    return 0
if __name__=='__main__':raise SystemExit(main())
