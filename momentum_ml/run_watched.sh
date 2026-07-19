#!/usr/bin/env bash
# Kör ett tungt kommando (t.ex. full main.py-träning) och dödar det om
# systemets VERKLIGA tillgängliga minne (MemAvailable, /proc/meminfo) blir
# farligt lågt - i stället för ulimit -v (RLIMIT_AS), som räknar reserverat
# virtuellt adressrum och därför slår till långt innan systemet faktiskt är i
# fara för numpy/pandas/BLAS-tung kod (se run_limited.sh-historiken: en
# 1.4 GB-gräns small trippade på en 1.3 MiB-allokering).
#
# Bakgrund: minnes-cgroup är avstängd på kärnnivå (cgroup_disable=memory),
# så det finns ingen exakt kernelspärr att luta sig mot - det här är en
# pollande approximation, inte en garanti.
#
# Användning: ./run_watched.sh -- <kommando> [args...]

set -uo pipefail

MIN_AVAILABLE_MB=150   # döda om ledigt minne går under detta
POLL_SECONDS=2

if [[ "${1:-}" == "--" ]]; then shift; fi

nice -n 19 ionice -c3 "$@" &
pid=$!

while kill -0 "$pid" 2>/dev/null; do
    avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
    avail_mb=$((avail_kb / 1024))
    if (( avail_mb < MIN_AVAILABLE_MB )); then
        echo "run_watched.sh: MemAvailable ${avail_mb}MB < ${MIN_AVAILABLE_MB}MB - dödar PID $pid" >&2
        kill -TERM "$pid" 2>/dev/null
        sleep 3
        kill -KILL "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null
        exit 137
    fi
    sleep "$POLL_SECONDS"
done

wait "$pid"
exit $?
