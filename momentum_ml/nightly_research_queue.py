"""Sequential, resumable overnight validation/research queue.

The queue waits for an already-running Small training job, executes every
registered command serially, continues after failures/timeouts, and records a
machine-generated status entry in both project journals after every item.

Research outputs are diagnostic while the P0 PIT/data gates in
docs/UTVECKLINGSLOGG.md remain unresolved; the runner never adopts parameters.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / "momentum_ml"
PYTHON = ROOT / ".allocation-test-venv" / "bin" / "python"
RUN_DIR = ROOT / "results" / "nightly_queue_2026-07-31"
STATE = RUN_DIR / "state.json"
DEVLOG = ROOT / "docs" / "UTVECKLINGSLOGG.md"
HANDOVER = ROOT / "docs" / "niva3_status_handoff.md"
TIMEOUT_S = 6 * 60 * 60


QUEUE = [
    ("omx30_pit_build", [str(PYTHON), "build_omx30_pit.py"]),
    ("omx30_pit_validate", [str(PYTHON), "omx30_pit.py"]),
    ("idx_mix_pit_omx30", [str(PYTHON), "tune_idx_mix.py"]),
    ("anchor_exit", [str(PYTHON), "tune_anchor_exit.py"]),
    ("pytest_full", [str(PYTHON), "-m", "pytest", "-q"]),
    ("feature_sanity", [str(PYTHON), "tune_feature_sanity_checks.py"]),
    ("horizon_52_plus_13", [str(PYTHON), "tune_horizon_ensemble.py"]),
    ("model_disagreement", [str(PYTHON), "tune_disagreement_filter.py"]),
    ("lambdarank_robustness", [str(PYTHON), "tune_lambdarank_robustness.py"]),
    ("risk_adjusted_momentum", [str(PYTHON), "tune_riskadj_momentum_ablation.py"]),
    ("concentration_cap", [str(PYTHON), "tune_concentration_cap.py"]),
    ("dynamic_positions", [str(PYTHON), "tune_dynamic_positions_backtest.py"]),
    ("large_small_allocation", [str(PYTHON), "tune_large_small_allocation.py"]),
    ("takeprofit_diagnostic_only", [str(PYTHON), "tune_takeprofit.py"]),
]

BLOCKED = [
    ("new_lockbox", "kan inte skapas retroaktivt; kräver orörd framtida data/ny period"),
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"created_at": now(), "items": {}}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE)


def journal(name: str, status: str, seconds: float, log_path: Path, detail: str = "") -> None:
    rel = log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path
    extra = f" — {detail}" if detail else ""
    entry = (
        f"\n- `{now()}` **NATTKÖ `{name}`: {status}** "
        f"({seconds / 60:.1f} min), logg: `{rel}`{extra}.\n"
    )
    for path in (DEVLOG, HANDOVER):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(entry)


def small_training_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "[m]ain.py --segment small"],
        cwd=ML,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def run_item(name: str, command: list[str], state: dict) -> None:
    previous = state["items"].get(name, {})
    if previous.get("status") == "PASS":
        return

    log_path = RUN_DIR / f"{name}.log"
    started = time.monotonic()
    state["items"][name] = {"status": "RUNNING", "started_at": now(), "command": command}
    save_state(state)
    status = "ERROR"
    detail = ""
    returncode = None

    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{now()}] START {command!r}\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=ML,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=TIMEOUT_S)
            status = "PASS" if returncode == 0 else "FAIL"
            detail = f"exit={returncode}"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            status = "TIMEOUT"
            detail = f"> {TIMEOUT_S // 3600} h"
        except Exception as exc:  # keep the overnight queue moving
            detail = f"{type(exc).__name__}: {exc}"
            log.write(f"\nRUNNER ERROR: {detail}\n")

    elapsed = time.monotonic() - started
    state["items"][name] = {
        "status": status,
        "finished_at": now(),
        "duration_seconds": round(elapsed, 3),
        "returncode": returncode,
        "log": str(log_path.relative_to(ROOT)),
        "detail": detail,
    }
    save_state(state)
    journal(name, status, elapsed, log_path, detail)


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    wait_log = RUN_DIR / "wait_for_small.log"
    wait_started = time.monotonic()
    while small_training_running():
        wait_log.write_text(
            f"{now()} väntar på pågående Small-träning innan nattkön startar\n",
            encoding="utf-8",
        )
        time.sleep(30)
    state["small_wait_finished_at"] = now()
    save_state(state)

    for name, command in QUEUE:
        run_item(name, command, state)

    for name, reason in BLOCKED:
        if state["items"].get(name, {}).get("status") == "BLOCKED":
            continue
        log_path = RUN_DIR / f"{name}.log"
        log_path.write_text(reason + "\n", encoding="utf-8")
        state["items"][name] = {
            "status": "BLOCKED", "finished_at": now(), "detail": reason,
            "log": str(log_path.relative_to(ROOT)),
        }
        save_state(state)
        journal(name, "BLOCKED", 0.0, log_path, reason)

    state["finished_at"] = now()
    save_state(state)
    journal("queue_complete", "DONE", time.monotonic() - wait_started, STATE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
