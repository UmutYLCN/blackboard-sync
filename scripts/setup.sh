#!/bin/sh
# Create the project-local virtual environment and install pinned dependencies.
# Nothing is installed globally, and no browser is downloaded: `login` drives the
# Chromium-based browser (Chrome, Edge, Brave, ...) already in /Applications.
set -eu
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.lock
.venv/bin/python -m pip install --quiet --no-deps -e .
echo "Ready: .venv/bin/blackboard-sync --help"
