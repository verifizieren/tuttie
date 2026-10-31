#!/usr/bin/env bash
# Start the whole agent web locally: registry, all nodes and the assistant (which serves the apps).
# If Node.js is available, the React apps (apps/wallet, apps/owner) are built first.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-.venv/bin/python}"
export PATH="$HOME/.local/node/bin:$PATH"  # user-level Node.js on the team server

if command -v npm >/dev/null; then
  for app in wallet owner; do
    (cd "apps/$app" && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build --silent)
  done
else
  echo "warning: npm not found, serving the last app builds (apps/*/dist) if there are any" >&2
fi
exec "$PYTHON" scripts/run_all.py
