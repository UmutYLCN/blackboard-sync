#!/bin/sh
# Notarize a Developer ID signed "Blackboard Sync.app" or .dmg with Apple,
# staple the ticket to it and check Gatekeeper accepts it; see docs/SIGNING.md.
#   scripts/notarize-macos.sh "dist/Blackboard Sync.app"
#   scripts/notarize-macos.sh dist/Blackboard-Sync-1.2.3.dmg
#
# Credentials come from the environment, an App Store Connect API key:
#   MACOS_NOTARY_KEY_PATH (the AuthKey_*.p8 file), MACOS_NOTARY_KEY_ID, MACOS_NOTARY_ISSUER_ID
# or an Apple ID with an app-specific password:
#   MACOS_NOTARY_APPLE_ID, MACOS_NOTARY_PASSWORD, MACOS_NOTARY_TEAM_ID
set -eu

[ $# -eq 1 ] || { echo "usage: $0 APP_OR_DMG" >&2; exit 2; }
TARGET="${1%/}"

if [ -n "${MACOS_NOTARY_KEY_PATH:-}" ]; then
  set -- --key "$MACOS_NOTARY_KEY_PATH" --key-id "${MACOS_NOTARY_KEY_ID:?}" --issuer "${MACOS_NOTARY_ISSUER_ID:?}"
elif [ -n "${MACOS_NOTARY_APPLE_ID:-}" ]; then
  set -- --apple-id "$MACOS_NOTARY_APPLE_ID" --password "${MACOS_NOTARY_PASSWORD:?}" --team-id "${MACOS_NOTARY_TEAM_ID:?}"
else
  echo "No notarization credentials: set MACOS_NOTARY_KEY_PATH/_KEY_ID/_ISSUER_ID or MACOS_NOTARY_APPLE_ID/_PASSWORD/_TEAM_ID." >&2
  exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# notarytool takes a .dmg, .pkg or .zip; an app is sent as a zip of itself.
case "$TARGET" in
  *.app)
    UPLOAD="$WORK/$(basename "$TARGET" .app).zip"
    ditto -c -k --sequesterRsrc --keepParent "$TARGET" "$UPLOAD"
    ;;
  *.dmg) UPLOAD="$TARGET" ;;
  *) echo "Not an .app or .dmg: $TARGET" >&2; exit 2 ;;
esac

echo "Submitting $(basename "$TARGET") for notarization (this usually takes a few minutes)..."
xcrun notarytool submit "$UPLOAD" "$@" --wait --timeout 2h --output-format json > "$WORK/result.json" || true
ID="$(plutil -extract id raw -o - "$WORK/result.json" 2>/dev/null || true)"
STATUS="$(plutil -extract status raw -o - "$WORK/result.json" 2>/dev/null || true)"
echo "Submission ${ID:-<none>}: ${STATUS:-<no status>}"
if [ "$STATUS" != "Accepted" ]; then
  cat "$WORK/result.json" >&2 || true
  # The log lists every file Apple rejected and why.
  [ -z "$ID" ] || xcrun notarytool log "$ID" "$@" >&2 || true
  exit 1
fi

xcrun stapler staple "$TARGET"
xcrun stapler validate "$TARGET"

# What a downloaded copy will meet: Gatekeeper must accept it as notarized.
case "$TARGET" in
  *.app) spctl --assess --type execute --verbose=4 "$TARGET" 2> "$WORK/spctl.txt" || true ;;
  *.dmg) spctl --assess --type open --context context:primary-signature --verbose=4 "$TARGET" 2> "$WORK/spctl.txt" || true ;;
esac
cat "$WORK/spctl.txt"
if ! grep -q ": accepted$" "$WORK/spctl.txt" || ! grep -q "^source=Notarized Developer ID$" "$WORK/spctl.txt"; then
  echo "Gatekeeper does not accept $TARGET as notarized." >&2
  exit 1
fi
