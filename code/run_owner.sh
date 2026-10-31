#!/usr/bin/env bash
# Try the owner view on its own: one business node (Gästehaus am Rhein, port 4009) and the page's
# dev server with hot reload (port 4042). Needs no OpenAI key and none of the other services.
# Sign in with the token below (default "demo"; set OWNER_TOKEN to use another one).
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-.venv/bin/python}"
export PATH="$HOME/.local/node/bin:$PATH"  # user-level Node.js on the team server
export OWNER_TOKEN="${OWNER_TOKEN:-demo}"

[ -d apps/owner/node_modules ] || (cd apps/owner && npm ci --no-audit --no-fund)

"$PYTHON" -m node.server --config data/nodes/guesthouse-am-rhein.json &
trap 'kill $!' EXIT  # stop the node with the dev server (Ctrl+C)
echo "Owner view: http://localhost:4042/owner/   token: $OWNER_TOKEN"
cd apps/owner && npm run dev
