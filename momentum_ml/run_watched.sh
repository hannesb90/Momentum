#!/usr/bin/env bash
# run_watched.sh – kör ett kommando men avbryter det (SIGTERM, sedan SIGKILL
# om det inte lyder) om systemets FAKTISKT lediga minne (/proc/meminfo
# MemAvailable) går under en tröskel, INNAN kärnans OOM-hantering hinner
# krascha hela Pi:n.
#
# VARFÖR: momentum-train.service:s MemoryMax/MemorySwapMax ser ut som ett
# skydd men gör INGENTING på den här Pi:n - cgroup_disable=memory är satt i
# /proc/cmdline, så ingen cgroup-minneskontroller finns
# (cat /sys/fs/cgroup/cgroup.controllers listar bara cpuset cpu io pids,
# aldrig "memory"). `ulimit -v` (RLIMIT_AS) duger inte heller för numpy/
# pandas/LightGBM-tunga jobb - den räknar reserverat virtuellt adressrum,
# inte faktiskt använt minne, och triggar på triviala allokeringar.
#
# Verkligt fall 2026-07-20: momentum-train.service kraschade hela Pi:n kl
# 02:14 (ledigt minne 972MB -> 180MB, swap 819MB -> 1844MB på tio minuter,
# se results/health.log) - ingen av de deklarerade minnesgränserna ingrep
# eftersom de aldrig var på riktigt. Hela nattens körning gick förlorad
# (ingen results/history/stats_2026-07-20.json skrevs).
#
# Dödar HELA processträdet (inte bara toppnivåprocessen) via `set -m` +
# processgrupp-kill (-$pid) - LightGBM/numpy kan spawna egna trådar/
# subprocesser som annars skulle fortsätta äta minne efter att huvud-
# processen dödats. Verifierat med en tre-nivåers testprocess.
#
#   run_watched.sh <kommando...>
#
# Miljövariabler (valfria):
#   RUN_WATCHED_MIN_MB   tröskel i MB ledigt minne innan avbrott (default 250 -
#                        samma härledda säkerhetsmarginal som health_monitor.sh:s
#                        egen <200MB-varningströskel, plus lite reaktionstid)
#   RUN_WATCHED_POLL_S   pollningsintervall i sekunder (default 5 - kraschen
#                        2026-07-20 tog ~10 min från första varningstecken till
#                        omstart, gott om marginal för 5s-polling)
set -uo pipefail
set -m   # jobbkontroll: bakgrundade processer får EGEN processgrupp (pgid=pid)

MIN_MB="${RUN_WATCHED_MIN_MB:-250}"
POLL_S="${RUN_WATCHED_POLL_S:-5}"

if [ "$#" -eq 0 ]; then
    echo "[run_watched] usage: run_watched.sh <kommando...>" >&2
    exit 2
fi

mem_avail_mb() {
    awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo
}

"$@" &
child_pid=$!

echo "[run_watched] startade pid $child_pid (min_mb=${MIN_MB} poll_s=${POLL_S}): $*"

killed_for_memory=0
while kill -0 "$child_pid" 2>/dev/null; do
    avail=$(mem_avail_mb)
    if [ -n "$avail" ] && [ "$avail" -lt "$MIN_MB" ]; then
        echo "[run_watched] KRITISKT: MemAvailable=${avail}MB < ${MIN_MB}MB - avbryter pid $child_pid (hela processgruppen) innan systemet kraschar" >&2
        kill -TERM -- "-$child_pid" 2>/dev/null
        sleep 5
        kill -KILL -- "-$child_pid" 2>/dev/null
        killed_for_memory=1
        break
    fi
    sleep "$POLL_S"
done

if [ "$killed_for_memory" -eq 1 ]; then
    wait "$child_pid" 2>/dev/null
    echo "[run_watched] avbruten pga lågt minne (MemAvailable < ${MIN_MB}MB)" >&2
    exit 137
fi

wait "$child_pid"
exit $?
