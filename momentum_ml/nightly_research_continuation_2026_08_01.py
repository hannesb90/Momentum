"""Continuation queue: waits for queue 2, then runs gates, retries and ready backlog."""
from __future__ import annotations
import datetime as dt, json, os, signal, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; ML = ROOT / "momentum_ml"
PYTHON = ROOT / ".allocation-test-venv/bin/python"
RUN_DIR = ROOT / "results/nightly_continuation_2026-08-01"
STATE = RUN_DIR / "state.json"; TIMEOUT = 6 * 3600
DOCS = [ROOT / "docs/UTVECKLINGSLOGG.md", ROOT / "docs/niva3_status_handoff.md"]

QUEUE = [
    ("pytest_after_patches", [str(PYTHON), "-m", "pytest", "-q"]),
    ("omx30_build_retest", [str(PYTHON), "build_omx30_pit.py"]),
    ("omx30_validate_retest", [str(PYTHON), "omx30_pit.py"]),
    ("idx_mix_retest", [str(PYTHON), "tune_idx_mix.py"]),
    ("slippage_vix_retest", [str(PYTHON), "tune_slippage_vix.py", "large"]),
    ("statistical_power_retest", [str(PYTHON), "tune_statistical_power.py", "large"]),
    ("voltarget_retest", [str(PYTHON), "tune_voltarget.py", "large"]),
    ("sr9_baseline_parity", [str(PYTHON), "gate_baseline_parity.py"]),
    ("sr10_corporate_actions", [str(PYTHON), "gate_corporate_actions.py"]),
    ("sr43_placebo_leakage", [str(PYTHON), "gate_placebo_leakage.py"]),
    ("sr44_multiple_testing", [str(PYTHON), "gate_multiple_testing.py"]),
    ("correlation_filter_frequency", [str(PYTHON), "tune_correlation_filter_freq.py"]),
    ("residual_momentum_solo_ic", [str(PYTHON), "tune_resid_mom_ic.py"]),
    ("riskadjusted_momentum_solo_ic", [str(PYTHON), "tune_riskadj_momentum_ic.py"]),
    ("abstention_gate_revalidation", [str(PYTHON), "tune_abstention_gate.py"]),
    ("objective_comparison", [str(PYTHON), "tune_objective_comparison.py"]),
    ("quality_momentum_interaction", [str(PYTHON), "tune_quality_momentum_interact.py"]),
    ("integrated_backtest", [str(PYTHON), "tune_integrated_backtest.py"]),
]

DEFERRED = {
    "sr1_sr8_sr11_sr42": "second-review alpha designs not implemented yet",
    "small_retests": "blocked by missing PIT fundamentals",
    "meta_pead": "must be rewritten DEV-only; old holdout is consumed",
}

def now(): return dt.datetime.now().astimezone().isoformat(timespec="seconds")
def save(s):
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, indent=2), encoding="utf-8"); os.replace(tmp, STATE)
def journal(name, status, sec, log, detail=""):
    line = f"\n- `{now()}` **FORTSÄTTNINGSKÖ `{name}`: {status}** ({sec/60:.1f} min), logg: `{log.relative_to(ROOT)}` — {detail}.\n"
    for doc in DOCS:
        with doc.open("a", encoding="utf-8") as fh: fh.write(line)
def old_queue_running():
    p = subprocess.run(["pgrep", "-f", "[n]ightly_research_queue_2026_08_01.py"], stdout=subprocess.DEVNULL)
    return p.returncode == 0
def run(name, cmd, state):
    if state["items"].get(name, {}).get("status") == "PASS": return
    log = RUN_DIR / f"{name}.log"; start = time.monotonic()
    state["items"][name] = {"status":"RUNNING", "started_at":now(), "command":cmd}; save(state)
    rc = None; status = "ERROR"; detail = ""
    with log.open("a", encoding="utf-8") as fh:
        p = subprocess.Popen(cmd, cwd=ML, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        try: rc=p.wait(timeout=TIMEOUT); status="PASS" if rc==0 else "FAIL"; detail=f"exit={rc}"
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM); status="TIMEOUT"; detail=">6h"
    sec=time.monotonic()-start; state["items"][name]={"status":status,"finished_at":now(),"returncode":rc,"duration_seconds":round(sec,3),"log":str(log.relative_to(ROOT)),"detail":detail}; save(state); journal(name,status,sec,log,detail)
def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True); state=json.loads(STATE.read_text()) if STATE.exists() else {"created_at":now(),"items":{}}
    while old_queue_running(): time.sleep(30)
    state["queue2_finished_seen_at"] = now(); save(state)
    for name,cmd in QUEUE: run(name,cmd,state)
    for name,detail in DEFERRED.items():
        if name not in state["items"]:
            log=RUN_DIR/f"deferred_{name}.log"; log.write_text(detail+"\n"); state["items"][name]={"status":"DEFERRED","detail":detail,"log":str(log.relative_to(ROOT))}; save(state); journal(name,"DEFERRED",0,log,detail)
    state["finished_at"]=now(); save(state); return 0
if __name__ == "__main__": raise SystemExit(main())
