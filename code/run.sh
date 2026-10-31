#!/usr/bin/env bash
# Start the whole agent web locally: registry, all nodes (and later the assistant).
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-.venv/bin/python}"
exec "$PYTHON" scripts/run_all.py
