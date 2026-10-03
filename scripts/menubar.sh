#!/bin/sh
# Start the Blackboard Sync menu bar app in the background and return at once;
# the terminal can be closed afterwards. Run ./scripts/setup.sh first.
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Run ./scripts/setup.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m blackboard_sync.menubar --detach
