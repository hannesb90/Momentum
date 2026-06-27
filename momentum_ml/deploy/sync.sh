#!/usr/bin/env bash
# Auto-sync: pullar repo, kopierar ändrade delar till deploy-katalogerna,
# bygger om frontend och/eller startar om API:t vid behov.
# Körs periodiskt via momentum-sync.timer.
set -euo pipefail

SRC_DIR=/opt/momentum/src
BRANCH=claude/pr-momentum-wr0x1f

# Kör git som den INLOGGADE användaren, inte root. Servicen/scriptet körs ofta
# med sudo (för systemctl/rsync nedan), men då saknar root ~/.ssh/config med
# 'github-momentum'-aliaset → "Could not resolve hostname github-momentum" och
# pullen misslyckas tyst. Vi kör därför alla git-anrop som $SUDO_USER (faller
# tillbaka på aktuell användare om scriptet körs utan sudo).
RUN_AS="${SUDO_USER:-$(id -un)}"
git_as() { sudo -u "$RUN_AS" -H git -C "$SRC_DIR" "$@"; }

before=$(git_as rev-parse HEAD)
git_as fetch origin "$BRANCH"
git_as merge --ff-only "origin/$BRANCH"
after=$(git_as rev-parse HEAD)

cd "$SRC_DIR"

if [ "$before" = "$after" ]; then
    echo "Inga nya ändringar ($before)."
    exit 0
fi

echo "Ny(a) commit(s): $before -> $after"
changed=$(git_as diff --name-only "$before" "$after")

if echo "$changed" | grep -q '^momentum_ml/requirements\.txt$'; then
    echo "[VARNING] requirements.txt har ändrats - kör pip install manuellt:"
    echo "  /opt/momentum/venv/bin/pip install --no-cache-dir -r /opt/momentum/momentum_ml/requirements.txt"
fi

if echo "$changed" | grep -q '^momentum_ml/'; then
    echo "Backend ändrad - synkar och startar om API."
    rsync -a --delete \
        --exclude 'cache/' --exclude 'results/' --exclude '__pycache__/' \
        --exclude 'deploy/' \
        "$SRC_DIR/momentum_ml/" /opt/momentum/momentum_ml/
    sudo systemctl restart momentum-api.service
fi

if echo "$changed" | grep -q '^frontend/'; then
    echo "Frontend ändrad - synkar och bygger om."
    rsync -a --delete \
        --exclude 'node_modules/' --exclude 'dist/' \
        "$SRC_DIR/frontend/" /opt/momentum/frontend/
    cd /opt/momentum/frontend
    npm ci
    npm run build
fi

if echo "$changed" | grep -q '^momentum_ml/deploy/'; then
    echo "[INFO] deploy/-filer ändrade (systemd-units etc) - dessa kopieras inte"
    echo "       automatiskt. Kör vid behov:"
    echo "  cp -r $SRC_DIR/momentum_ml/deploy /opt/momentum/momentum_ml/"
    echo "  sudo cp /opt/momentum/momentum_ml/deploy/*.service /opt/momentum/momentum_ml/deploy/*.timer /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
fi

echo "Synk klar: $before -> $after"
