#!/bin/bash
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

branch="$(git rev-parse --abbrev-ref HEAD)"

if [ "$branch" = "HEAD" ]; then
  exit 0
fi

git fetch origin "$branch" 2>&1 || exit 0
git pull --ff-only origin "$branch" 2>&1 || {
  echo "[session-start] git pull --ff-only misslyckades (lokala ändringar/divergerad historik) - hoppar över automatisk pull." >&2
  exit 0
}
