#!/usr/bin/env bash
# Kör ett Python-testskript med hårda minnes-/tids-gränser så en skenande
# körning kraschar sig själv (MemoryError) istället för att låsa hela Pi:n.
#
# Bakgrund: minnes-cgroup är avstängd på kärnnivå (cgroup_disable=memory i
# /proc/cmdline) så systemd-run -p MemoryMax gör ingenting här. ulimit -v
# (RLIMIT_AS) är en per-process kernel-rlimit och funkar oavsett cgroups.
#
# Användning: ./run_limited.sh tune_pead.py [args...]

set -euo pipefail

MAX_VMEM_KB=900000   # ~880 MB virtuellt adressrum per process
MAX_SECONDS=600       # walltime-backstop

ulimit -v "$MAX_VMEM_KB"

exec nice -n 19 ionice -c3 timeout "$MAX_SECONDS" \
    /opt/momentum/venv/bin/python3 "$@"
