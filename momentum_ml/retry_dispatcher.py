"""
retry_dispatcher.py – körs var 2:e minut (momentum-retry.timer). Läser
cache/claude_retry_queue.json (skriven av claude_headless.queue_retry() när
ett SCHEMALAGT jobb – portfolio_commentary.py/watchlist_sync.py/
insight_report.py/sync_montrose_holdings.py – misslyckas pga
prenumerationens kvot-/tidsgräns med en tolkningsbar "resets HH:MM"-tid) och
kör om exakt de skript vars retry_at passerat, i stället för att låta det
förlorade jobbet vänta till nästa ordinarie natt-timer (kan vara >20h bort).

    python retry_dispatcher.py
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

QUEUE_FILE = Path(config.anchor("cache/claude_retry_queue.json"))


def main():
    if not QUEUE_FILE.exists():
        return
    try:
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        print("[retry] trasig kö-fil – rör den inte, undersök manuellt.")
        return
    now = datetime.now(timezone.utc)
    remaining = []
    for entry in queue:
        script = entry.get("script")
        try:
            due = datetime.fromisoformat(entry["retry_at"])
        except Exception:  # noqa: BLE001
            continue
        if due > now:
            remaining.append(entry)
            continue
        args = entry.get("args") or []
        if not script or not Path(script).exists():
            print(f"[retry] hoppar över (skript saknas): {script}")
            continue
        print(f"[retry] kör om {Path(script).name} {args} "
              f"(kvot skulle fyllts på {entry.get('retry_at')})")
        try:
            subprocess.run([sys.executable, script, *args],
                            cwd=str(Path(script).parent), timeout=1800, check=False)
        except Exception as e:  # noqa: BLE001
            print(f"[retry] {Path(script).name} kraschade vid ombokad körning: {e}")
        # Tas bort ur kön oavsett utfall - ett förnyat kvotfel köar sig
        # självt på nytt (via queue_retry, med en ny retry_at längre fram),
        # så det finns ingen risk för en tight omkörnings-loop här.
    QUEUE_FILE.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
