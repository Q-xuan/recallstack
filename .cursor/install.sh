#!/usr/bin/env bash
# Idempotent dependency setup for RecallStack (Python backend + Vite frontend).
set -euo pipefail

cd "$(dirname "$0")/.."

# python3-venv is required to create the virtualenv on the default image.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# Backend: isolated virtualenv with editable install (web + dev extras).
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -e ".[web,dev]"

# Frontend: clean, reproducible install from the lockfile.
cd frontend
npm ci
