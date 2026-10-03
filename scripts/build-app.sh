#!/bin/sh
# Build the self-contained "Blackboard Sync.app" and a drag-to-Applications .dmg
# into dist/. Uses the project-local .venv (created by ./scripts/setup.sh) and
# bundles its own Python, so the result needs nothing installed on the Mac.
# The app is ad-hoc signed only (no paid Developer ID): users see the
# "developer cannot be verified" prompt once and open it with right-click > Open.
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Run ./scripts/setup.sh first." >&2
  exit 1
fi
.venv/bin/python -m pip install --quiet -r requirements-build.txt
VERSION="$(.venv/bin/python -c 'import blackboard_sync; print(blackboard_sync.__version__)')"
rm -rf build dist
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/blackboard_sync.spec
APP="dist/Blackboard Sync.app"
# PyInstaller already ad-hoc signs; re-sign the whole bundle consistently.
codesign --force --deep --sign - "$APP"

DMG="dist/Blackboard-Sync-$VERSION.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Blackboard Sync" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "Built $APP"
echo "Built $DMG ($(du -h "$DMG" | cut -f1))"
