#!/usr/bin/env bash
# Start the whole agent web locally: registry, all nodes and the assistant (which serves the apps).
# If Node.js is available, the React wallet (apps/wallet) is built first.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-.venv/bin/python}"
export PATH="$HOME/.local/node/bin:$PATH"  # user-level Node.js on the team server

if command -v npm >/dev/null; then
  (cd apps/wallet && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build --silent)
else
  echo "warning: npm not found, serving the last wallet build (apps/wallet/dist) if there is one" >&2
fi
exec "$PYTHON" scripts/run_all.py
