#!/bin/sh
# Pack "Blackboard Sync.app" into a drag-to-Applications .dmg:
#   scripts/make-dmg.sh "dist/Blackboard Sync.app" dist/Blackboard-Sync-1.2.3.dmg
# Used by scripts/build-app.sh and, for signed releases, by the release workflow.
set -eu
[ $# -eq 2 ] || { echo "usage: $0 APP DMG" >&2; exit 2; }
APP="$1"
DMG="$2"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Blackboard Sync" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
