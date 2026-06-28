#!/usr/bin/env bash
# Auto-sync: pullar repo, kopierar ändrade delar till deploy-katalogerna,
# bygger om frontend och/eller startar om API:t vid behov.
# Körs periodiskt via momentum-sync.timer.
#
# Robusthet: rsync:en mot deploy-katalogerna körs ALLTID (den är snabb och
# flyttar bara diffar), och beslut om API-omstart/frontend-bygge fattas på vad
# rsync FAKTISKT överförde – inte på git-HEAD. Tidigare gatades rsync:en på
# "before != after" i git-pullen, vilket gav en tyst skip-fälla: om src redan
# låg på rätt commit (t.ex. en avbruten tidigare synk eller en manuell pull)
# men deploy-kopian inte matchade, så uppdaterades deploy-kopian aldrig. Nu kan
# de två inte glida isär.
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
    echo "Git: inga nya commits ($before). Verifierar ändå att deploy-kopiorna matchar."
else
    echo "Git: ny(a) commit(s): $before -> $after"
fi

# Hjälpare: itemize-rad som representerar en faktisk fil-överföring/-radering
# (inte bara katalog-tidsstämpel). Tom utdata = deploy-kopian var redan i synk.
real_changes() { grep -E '^(>|<|\*|c|h)' | grep -vE '/$' || true; }

# ── Backend ────────────────────────────────────────────────────────────────
# Kör ALLTID. cache/ och results/ (körningsdata) samt deploy/ (systemd-units,
# kopieras manuellt) exkluderas.
backend_out=$(rsync -ai --delete \
    --exclude 'cache/' --exclude 'results/' --exclude '__pycache__/' \
    --exclude 'deploy/' \
    "$SRC_DIR/momentum_ml/" /opt/momentum/momentum_ml/)
backend_changed=$(printf '%s\n' "$backend_out" | real_changes)

if [ -n "$backend_changed" ]; then
    echo "Backend uppdaterad - startar om API. Ändrade filer:"
    printf '%s\n' "$backend_changed" | sed 's/^/  /'
    if printf '%s\n' "$backend_changed" | grep -q 'requirements\.txt'; then
        echo "[VARNING] requirements.txt har ändrats - kör pip install manuellt:"
        echo "  /opt/momentum/venv/bin/pip install --no-cache-dir -r /opt/momentum/momentum_ml/requirements.txt"
    fi
    sudo systemctl restart momentum-api.service
else
    echo "Backend: redan i synk."
fi

# ── Frontend ───────────────────────────────────────────────────────────────
frontend_out=$(rsync -ai --delete \
    --exclude 'node_modules/' --exclude 'dist/' \
    "$SRC_DIR/frontend/" /opt/momentum/frontend/)
frontend_changed=$(printf '%s\n' "$frontend_out" | real_changes)

if [ -n "$frontend_changed" ]; then
    echo "Frontend uppdaterad - bygger om. Ändrade filer:"
    printf '%s\n' "$frontend_changed" | sed 's/^/  /'
    cd /opt/momentum/frontend
    npm ci
    npm run build
    cd "$SRC_DIR"
else
    echo "Frontend: redan i synk."
fi

# ── deploy/ (systemd-units etc) ──────────────────────────────────────────────
# Exkluderas medvetet ur rsync:en ovan (rör /etc och systemd) - kan bara
# upptäckas via git-diffen. Visas bara som info när nya commits faktiskt kom in.
if [ "$before" != "$after" ] && git_as diff --name-only "$before" "$after" | grep -q '^momentum_ml/deploy/'; then
    echo "[INFO] deploy/-filer ändrade (systemd-units etc) - dessa kopieras inte"
    echo "       automatiskt. Kör vid behov:"
    echo "  cp -r $SRC_DIR/momentum_ml/deploy /opt/momentum/momentum_ml/"
    echo "  sudo cp /opt/momentum/momentum_ml/deploy/*.service /opt/momentum/momentum_ml/deploy/*.timer /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload"
fi

echo "Synk klar (git $before -> $after)."
