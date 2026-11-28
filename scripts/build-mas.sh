#!/bin/sh
# Build the Mac App Store ("mas") flavor of "Blackboard Sync.app" into dist/,
# sign it with App Sandbox entitlements, and (when installer credentials are
# provided) package it into a signed productbuild .pkg for App Store Connect.
#
# Local sandboxed build (ad-hoc signed, runs inside ~/Library/Containers/<bundle-id>):
#   ./scripts/build-mas.sh
#
# Signed App Store submission .pkg:
#   MAS_APP_IDENTITY="Apple Distribution: Your Name (TEAMID)" \
#   MAS_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: Your Name (TEAMID)" \
#   MAS_PROVISIONING_PROFILE=/path/to/Blackboard_Sync_MAS.provisionprofile \
#   MAS_EXTENSION_PROVISIONING_PROFILE=/path/to/Blackboard_Sync_MAS_Safari_Extension.provisionprofile \
#     ./scripts/build-mas.sh
#
# Override PYTHON=/path/to/python to build from an isolated build venv.
set -eu
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "Python not found at $PYTHON; run ./scripts/setup.sh first or set PYTHON." >&2
  exit 1
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  "$PYTHON" -m pip install --quiet -r requirements-build.txt
fi

VERSION="$(PYTHONPATH=src "$PYTHON" -c 'import re, blackboard_sync; print(re.match(r"(\d+\.\d+\.\d+)", blackboard_sync.__version__).group(1))')"
rm -rf build dist

BBSYNC_DISTRIBUTION=mas PYTHONPATH=src "$PYTHON" -m PyInstaller --noconfirm --clean packaging/blackboard_sync_mas.spec
APP="dist/Blackboard Sync.app"
# Gemini Notebook goes through the app's own Safari extension in this build.
./scripts/build-safari-extension.sh "$APP"

if [ -n "${MAS_INSTALLER_IDENTITY:-}" ]; then
  PKG="dist/Blackboard-Sync-$VERSION-mas.pkg"
  ./scripts/sign-mas.sh "$APP" --pkg-output "$PKG" "$@"
else
  ./scripts/sign-mas.sh "$APP" "$@"
fi

echo "Built MAS app: $APP"
