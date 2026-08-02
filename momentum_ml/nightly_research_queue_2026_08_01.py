"""Second sequential, resumable research queue (2026-08-01).

Only already implemented, still-unresolved diagnostics are included.  The
runner never changes production parameters.  Results that inspect the old
holdout are evidence/audit only and may not be used as a fresh selection set.
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
RUN_DIR = ROOT / "results" / "nightly_queue_2026-08-01"
STATE = RUN_DIR / "state.json"
DEVLOG = ROOT / "docs" / "UTVECKLINGSLOGG.md"
HANDOVER = ROOT / "docs" / "niva3_status_handoff.md"
TIMEOUT_S = 6 * 60 * 60

# Ordered by dependency and research value.  OMX membership is a prerequisite
# for IDX-MIX. Remaining jobs are diagnostics against the frozen model/signals.
QUEUE = [
    ("pytest_preflight", [str(PYTHON), "-m", "pytest", "-q"]),
    ("omx30_pit_build_retry", [str(PYTHON), "build_omx30_pit.py"]),
    ("omx30_pit_validate", [str(PYTHON), "omx30_pit.py"]),
    ("idx_mix_pit_omx30", [str(PYTHON), "tune_idx_mix.py"]),
    ("reentry_threshold_production", [str(PYTHON), "tune_reentry_threshold_production.py"]),
    ("individual_dd_floor_rotate", [str(PYTHON), "tune_individual_drawdown_floor_rotate.py"]),
    ("regime_exposure_large", [str(PYTHON), "tune_regime_exposure.py", "large"]),
    ("slippage_vix_large", [str(PYTHON), "tune_slippage_vix.py", "large"]),
    ("statistical_power_large", [str(PYTHON), "tune_statistical_power.py", "large"]),
    ("voltarget_large_revalidation", [str(PYTHON), "tune_voltarget.py", "large"]),
]

DEFERRED = [
    ("metalabel", "gammalt skript väljer på förbrukad holdout; kräver DEV-only omskrivning"),
    ("pead", "gammalt skript väljer på förbrukad holdout; kräver PIT-rapportdata och DEV-only design"),
    ("small_replications", "Small har 100% saknade fundamenta och är inte beslutsdugligt"),
    ("new_signal_families", "A3–A6/B1–B7/C2–C9 saknar färdig PIT-säker implementation/data"),
    ("stress_harness", "fem identifierade stresscenarier kräver separat simulatorimplementation"),
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
    rel = log_path.relative_to(ROOT)
    suffix = f" — {detail}" if detail else ""
    entry = (f"\n- `{now()}` **NATTKÖ 2 `{name}`: {status}** "
             f"({seconds / 60:.1f} min), logg: `{rel}`{suffix}.\n")
    for path in (DEVLOG, HANDOVER):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(entry)


def run_item(name: str, command: list[str], state: dict) -> None:
    if state["items"].get(name, {}).get("status") == "PASS":
        return
    log_path = RUN_DIR / f"{name}.log"
    started = time.monotonic()
    state["items"][name] = {"status": "RUNNING", "started_at": now(), "command": command}
    save_state(state)
    status, detail, returncode = "ERROR", "", None
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{now()}] START {command!r}\n")
        log.flush()
        process = subprocess.Popen(command, cwd=ML, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
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
            status, detail = "TIMEOUT", f"> {TIMEOUT_S // 3600} h"
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log.write(f"\nRUNNER ERROR: {detail}\n")
    elapsed = time.monotonic() - started
    state["items"][name] = {"status": status, "finished_at": now(),
                            "duration_seconds": round(elapsed, 3),
                            "returncode": returncode,
                            "log": str(log_path.relative_to(ROOT)), "detail": detail}
    save_state(state)
    journal(name, status, elapsed, log_path, detail)


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    for name, command in QUEUE:
        run_item(name, command, state)
    for name, reason in DEFERRED:
        if name in state["items"]:
            continue
        log_path = RUN_DIR / f"deferred_{name}.log"
        log_path.write_text(reason + "\n", encoding="utf-8")
        state["items"][name] = {"status": "DEFERRED", "finished_at": now(),
                                "detail": reason, "log": str(log_path.relative_to(ROOT))}
        save_state(state)
        journal(name, "DEFERRED", 0, log_path, reason)
    state["finished_at"] = now()
    save_state(state)
    journal("queue_complete", "DONE", 0, STATE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
