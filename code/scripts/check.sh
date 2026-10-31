#!/usr/bin/env bash
# The checks before every push, in one command (run from anywhere):
#   1. all tests (no network, no LLM)
#   2. the wallet's and owner view's own tests pass and both still build (needs Node.js;
#      skipped with a warning without npm)
#   3. the whole real flow still runs end to end: scripts/demo_headless.py approved
#      (real LLM; skipped with a warning without an OpenAI key, or with --no-llm)
# Stops at the first failure and says which step failed.
#
# Usage: scripts/check.sh [--no-llm]
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
export PATH="$HOME/.local/node/bin:$PATH"  # user-level Node.js on the team server
NO_LLM=false
[[ "${1:-}" == "--no-llm" ]] && NO_LLM=true

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }
skipped=()

step "1/3 tests"
"$PYTHON" -m pytest -q || fail "tests"

step "2/3 apps: tests and build (wallet, owner)"
stale() { [ ! -f node_modules/.package-lock.json ] || [ package-lock.json -nt node_modules/.package-lock.json ]; }
if command -v npm >/dev/null; then
  for app in wallet owner; do
    (cd "apps/$app" && { ! stale || npm ci --no-audit --no-fund; } && npm test --silent && npm run build --silent) \
      || fail "$app tests or build"
  done
else
  echo "npm not found: app tests and builds skipped"; skipped+=("app builds")
fi

step "3/3 headless demo (real LLM)"
# Same key check as run_all.py; it never prints the key.
warning=$("$PYTHON" -c 'import sys; sys.path.insert(0, "scripts"); import run_all; print(run_all.key_warning() or "")')
if $NO_LLM; then
  echo "--no-llm: headless demo skipped"; skipped+=("headless demo")
elif [[ -n "$warning" ]]; then
  echo "$warning"; echo "headless demo skipped"; skipped+=("headless demo")
else
  out=$("$PYTHON" scripts/demo_headless.py approved 2>&1) || { echo "$out" | tail -30; fail "headless demo"; }
  echo "$out" | tail -12  # the end of the run: booking, payment and Tuttie's answer
fi

if (( ${#skipped[@]} )); then
  printf '\n\033[33mOK, but skipped: %s\033[0m\n' "$(IFS=,; echo "${skipped[*]}")"
else
  printf '\n\033[32mAll checks passed.\033[0m\n'
fi
