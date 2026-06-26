#!/usr/bin/env bash
# health_monitor.sh – Lättviktig övervakning av temperatur/spänning/minne under
# träning. Körs med korta intervall via momentum-health.timer och skriver bara
# en rad per körning till en egen loggfil (lätt att grep:a/larma på i efterhand,
# tyngre än så behövs inte på en Pi).
#
# vcgencmd get_throttled bitmask (se https://www.raspberrypi.com/documentation
# /computers/os.html#vcgencmd):
#   bit 0  (0x1)      under-voltage NU
#   bit 1  (0x2)      ARM frequency capped NU
#   bit 2  (0x4)      currently throttled NU
#   bit 16 (0x10000)  under-voltage har inträffat sedan boot
#   bit 17 (0x20000)  frequency capping har inträffat sedan boot
#   bit 18 (0x40000)  throttling har inträffat sedan boot
set -euo pipefail

LOG_DIR=/opt/momentum/momentum_ml/results
LOG_FILE="$LOG_DIR/health.log"
mkdir -p "$LOG_DIR"

timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
temp_raw="$(vcgencmd measure_temp 2>/dev/null || echo 'temp=0.0C')"
temp="${temp_raw#temp=}"
temp="${temp%\'C*}"
throttled="$(vcgencmd get_throttled 2>/dev/null || echo 'throttled=0x0')"
throttled_hex="${throttled#throttled=}"
mem_avail_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
mem_avail_mb=$((mem_avail_kb / 1024))
swap_used_kb="$(awk '/SwapTotal/ {t=$2} /SwapFree/ {f=$2} END {print t-f}' /proc/meminfo)"
swap_used_mb=$((swap_used_kb / 1024))

flags=""
throttled_int=$((throttled_hex))
if (( throttled_int & 0x1 ));     then flags="$flags UNDERVOLT_NOW";       fi
if (( throttled_int & 0x4 ));     then flags="$flags THROTTLED_NOW";       fi
if (( throttled_int & 0x10000 )); then flags="$flags undervolt_since_boot"; fi
if (( throttled_int & 0x40000 )); then flags="$flags throttled_since_boot"; fi

echo "$timestamp temp=${temp}C throttled=${throttled_hex} mem_avail=${mem_avail_mb}MB swap_used=${swap_used_mb}MB${flags:+ FLAGS:$flags}" >> "$LOG_FILE"

# Larm-tröskel: hög temp eller aktiv undervoltage/throttling just nu, eller
# minnet börjar ta slut. Skriv till stderr (syns i journalctl -u
# momentum-health.service) så det går att grep:a fram varningar separat.
if awk -v t="$temp" 'BEGIN { exit !(t >= 78) }'; then
    echo "[VARNING] Hög temperatur: ${temp}C" >&2
fi
if (( throttled_int & 0x5 )); then
    echo "[VARNING] Undervoltage/throttling pågår NU (throttled=${throttled_hex})" >&2
fi
if (( mem_avail_mb < 200 )); then
    echo "[VARNING] Lågt ledigt minne: ${mem_avail_mb}MB" >&2
fi

# Håll loggen från att växa obegränsat - max ~10000 rader (~1 vecka vid 1/min).
tail -n 10000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
