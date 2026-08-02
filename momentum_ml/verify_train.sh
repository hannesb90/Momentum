#!/usr/bin/env bash
# verify_train.sh – kontrollerar att nattens momentum-train.service faktiskt
# gav färska resultat för BÅDA segmenten, och kör om EN gång om inte.
#
# VARFÖR: momentum-train.service kan misslyckas tyst (minnesvakten avbryter
# ett segment, "-" framför ExecStart gör att systemd ändå rapporterar
# tjänsten som lyckad) - se run_watched.sh:s docstring för de tre kvällarna
# (2026-07-19/20/22) det hänt. En natt utan färska resultat upptäcktes
# tidigare bara om någon råkade titta i results/-katalogen manuellt. Detta
# är den PERMANENTA, återkommande kontrollen (körs varje natt via
# momentum-train-verify.timer, inte en engångsgrej för en specifik kväll).
#
# Körs som root (samma skäl som api_watchdog.sh: behöver systemctl-behörighet
# utan att bero på en specifik användares sudo-config).
set -uo pipefail

RESULTS_LARGE=/opt/momentum/momentum_ml/results/stats.json
RESULTS_SMALL=/opt/momentum/momentum_ml/results/small/stats.json
TODAY="$(date +%Y-%m-%d)"

is_fresh() {
    [ -f "$1" ] && [ "$(date -r "$1" +%Y-%m-%d)" = "$TODAY" ]
}

large_ok=0; small_ok=0
is_fresh "$RESULTS_LARGE" && large_ok=1
is_fresh "$RESULTS_SMALL" && small_ok=1

if [ "$large_ok" = "1" ] && [ "$small_ok" = "1" ]; then
    echo "[verify_train] OK - båda segmenten har färska resultat ($TODAY)."
    exit 0
fi

echo "[verify_train] Saknar färska resultat (large=$large_ok small=$small_ok) - kör om momentum-train.service."
journalctl -u momentum-train.service --since "02:00" --no-pager | tail -30

echo "[verify_train] Startar om (systemctl start blockerar tills hela körningen - large+small - är klar)."
systemctl start momentum-train.service
retry_status=$?

large_ok=0; small_ok=0
is_fresh "$RESULTS_LARGE" && large_ok=1
is_fresh "$RESULTS_SMALL" && small_ok=1

if [ "$large_ok" = "1" ] && [ "$small_ok" = "1" ]; then
    echo "[verify_train] Omkörningen lyckades (exit $retry_status) - båda segmenten har nu färska resultat."
    exit 0
fi

echo "[verify_train] VARNING: omkörningen räckte inte (exit $retry_status, large=$large_ok small=$small_ok) - undersök manuellt."
journalctl -u momentum-train.service --since "5 min ago" --no-pager | tail -30
exit 1
