#!/bin/sh
# Sign "Blackboard Sync.app" or the .dmg with a Developer ID Application
# identity, under the hardened runtime and with a secure timestamp, as Apple's
# notary service requires. Used by scripts/build-app.sh when
# MACOS_SIGN_IDENTITY is set; see docs/SIGNING.md.
#
#   scripts/sign-macos.sh app "dist/Blackboard Sync.app" "Developer ID Application: ..."
#   scripts/sign-macos.sh dmg dist/Blackboard-Sync-1.2.3.dmg "Developer ID Application: ..."
#
# The identity "-" signs ad-hoc (no timestamp), which lets the hardened-runtime
# build be tried without a certificate.
#
# The app is signed inside out instead of with "codesign --deep", so every
# piece of code gets exactly the entitlements meant for it: Playwright's Node.js
# driver gets packaging/entitlements/node.plist, every other library or
# executable none, the app itself packaging/entitlements/app.plist.
set -eu
cd "$(dirname "$0")/.."

[ $# -eq 3 ] || { echo "usage: $0 app|dmg PATH IDENTITY" >&2; exit 2; }
KIND="$1"
TARGET="$2"
IDENTITY="$3"
ENTITLEMENTS="packaging/entitlements"

if [ "$IDENTITY" = "-" ]; then
  TIMESTAMP="--timestamp=none"
else
  TIMESTAMP="--timestamp"
fi

sign() {
  codesign --force --sign "$IDENTITY" "$TIMESTAMP" "$@"
}

case "$KIND" in
  dmg)
    sign "$TARGET"
    codesign --verify --strict --verbose=2 "$TARGET"
    ;;
  app)
    CONTENTS="$TARGET/Contents"
    MAIN="$CONTENTS/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$CONTENTS/Info.plist")"
    # Extended attributes (Finder info and the like) make codesign refuse to sign.
    xattr -cr "$TARGET"
    LIST="$(mktemp)"
    trap 'rm -f "$LIST"' EXIT
    # Every Mach-O file except the main executable, which is signed with the
    # bundle. Symlinks are skipped: their targets are in the list themselves.
    find "$CONTENTS" -type f ! -path "$MAIN" -print > "$LIST"
    while IFS= read -r file; do
      case "$(file -b "$file")" in
        Mach-O*) ;;
        *) continue ;;
      esac
      case "$file" in
        */playwright/driver/node) sign --options runtime --entitlements "$ENTITLEMENTS/node.plist" "$file" ;;
        *) sign --options runtime "$file" ;;
      esac
    done < "$LIST"
    # Nested frameworks (PyInstaller collects Python.framework) are bundles of
    # their own: sign each version after its contents.
    find "$CONTENTS" -type d -path '*.framework/Versions/*' ! -name Current -prune -print | while IFS= read -r version; do
      sign --options runtime "$version"
    done
    sign --options runtime --entitlements "$ENTITLEMENTS/app.plist" "$TARGET"
    codesign --verify --deep --strict --verbose=2 "$TARGET"
    ;;
  *)
    echo "usage: $0 app|dmg PATH IDENTITY" >&2
    exit 2
    ;;
esac
