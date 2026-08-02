#!/usr/bin/env bash
# api_watchdog.sh – Startar om momentum-api om HÄLSO-endpointen inte svarar OK.
#
# Varför räcker inte systemd:s Restart=always? Det fångar bara när PROCESSEN dör.
# Ett 500/hängt uvicorn-tillstånd (t.ex. efter en trasig läsning eller en läckande
# tråd) håller processen vid liv men servar fel → systemd ser inget att starta om.
# Den här vakthunden mäter faktisk hälsa (HTTP 200 på /api/health) och startar om
# tjänsten om den är sjuk två gånger i rad (undviker flaxande på en enstaka miss).
#
# Körs som root via momentum-api-watchdog.timer (var 30:e sekund).
set -uo pipefail

URL="http://127.0.0.1:8001/api/health"
STATE="/opt/momentum/momentum_ml/results/.api_health_fails"
mkdir -p "$(dirname "$STATE")"

code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$URL" 2>/dev/null || echo 000)"

if [ "$code" = "200" ]; then
    echo 0 > "$STATE"
    exit 0
fi

fails=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$fails" > "$STATE"
logger -t momentum-api-watchdog "hälsokoll misslyckades (code=$code, fails=$fails)"

if [ "$fails" -ge 2 ]; then
    logger -t momentum-api-watchdog "startar om momentum-api efter $fails misslyckanden"
    systemctl restart momentum-api
    echo 0 > "$STATE"
fi
