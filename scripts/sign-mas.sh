#!/bin/sh
# Sign the Mac App Store ("mas") build of "Blackboard Sync.app" inside-out with
# App Sandbox entitlements, optionally embed a provisioning profile, and build a
# signed productbuild .pkg for App Store Connect / Transporter.
#
# Local sandbox testing (ad-hoc, no certificates or profile needed):
#   ./scripts/sign-mas.sh "dist/Blackboard Sync.app"
#
# App Store submission (.pkg):
#   ./scripts/sign-mas.sh "dist/Blackboard Sync.app" \
#     --app-identity "Apple Distribution: Your Name (TEAMID)" \
#     --installer-identity "3rd Party Mac Developer Installer: Your Name (TEAMID)" \
#     --provisioning-profile /path/to/Blackboard_Sync_MAS.provisionprofile \
#     --extension-provisioning-profile /path/to/Blackboard_Sync_MAS_Safari_Extension.provisionprofile \
#     --pkg-output "dist/Blackboard-Sync-1.7.2-mas.pkg"
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
usage: scripts/sign-mas.sh APP_PATH [options]

Options:
  --app-identity IDENTITY         App signing identity ("Apple Distribution: ..." or
                                  "3rd Party Mac Developer Application: ...", or "-" for ad-hoc)
  --installer-identity IDENTITY   Installer identity ("3rd Party Mac Developer Installer: ...")
  --provisioning-profile PATH     Mac App Store .provisionprofile to embed at
                                  Contents/embedded.provisionprofile
  --extension-provisioning-profile PATH
                                  The Safari extension's own .provisionprofile (its bundle id is
                                  the app's plus .SafariExtension), embedded in the .appex
  --pkg-output PATH               Build a productbuild .pkg at PATH (requires --installer-identity
                                  unless --unsigned-pkg is also given)
  --unsigned-pkg                  Allow building an unsigned .pkg for packaging dry-runs
EOF
  exit 2
}

[ $# -ge 1 ] || usage
TARGET="$1"
shift

APP_IDENTITY="${MAS_APP_IDENTITY:--}"
INSTALLER_IDENTITY="${MAS_INSTALLER_IDENTITY:-}"
PROFILE_PATH="${MAS_PROVISIONING_PROFILE:-}"
EXTENSION_PROFILE_PATH="${MAS_EXTENSION_PROVISIONING_PROFILE:-}"
PKG_OUTPUT=""
UNSIGNED_PKG=0

while [ $# -gt 0 ]; do
  case "$1" in
    --app-identity)
      [ $# -ge 2 ] || usage
      APP_IDENTITY="$2"
      shift 2
      ;;
    --installer-identity)
      [ $# -ge 2 ] || usage
      INSTALLER_IDENTITY="$2"
      shift 2
      ;;
    --provisioning-profile)
      [ $# -ge 2 ] || usage
      PROFILE_PATH="$2"
      shift 2
      ;;
    --extension-provisioning-profile)
      [ $# -ge 2 ] || usage
      EXTENSION_PROFILE_PATH="$2"
      shift 2
      ;;
    --pkg-output)
      [ $# -ge 2 ] || usage
      PKG_OUTPUT="$2"
      shift 2
      ;;
    --unsigned-pkg)
      UNSIGNED_PKG=1
      shift
      ;;
    *)
      usage
      ;;
  esac
done

[ -d "$TARGET/Contents" ] || { echo "App bundle not found: $TARGET" >&2; exit 1; }

ENTITLEMENTS_APP="$ROOT/packaging/entitlements/mas.plist"
ENTITLEMENTS_INHERIT="$ROOT/packaging/entitlements/mas-inherit.plist"
ENTITLEMENTS_EXTENSION="$ROOT/packaging/entitlements/mas-safari-extension.plist"
CONTENTS="$TARGET/Contents"
EXEC_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$CONTENTS/Info.plist")"
MAIN="$CONTENTS/MacOS/$EXEC_NAME"

if [ -n "$PROFILE_PATH" ]; then
  [ -f "$PROFILE_PATH" ] || { echo "Provisioning profile not found: $PROFILE_PATH" >&2; exit 1; }
  cp "$PROFILE_PATH" "$CONTENTS/embedded.provisionprofile"
  chmod 0644 "$CONTENTS/embedded.provisionprofile"
fi

if [ "$APP_IDENTITY" = "-" ]; then
  TIMESTAMP="--timestamp=none"
else
  TIMESTAMP="--timestamp"
fi

sign() {
  codesign --force --sign "$APP_IDENTITY" "$TIMESTAMP" "$@"
}

# Remove Finder / quarantine extended attributes so codesign accepts every file.
xattr -cr "$TARGET"

LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT

# Sign every inner Mach-O library and helper executable before frameworks and the main bundle.
# App extensions (Contents/PlugIns) are bundles with their own sandbox: they are signed below.
find "$CONTENTS" -type f ! -path "$MAIN" ! -path "$CONTENTS/PlugIns/*" -print > "$LIST"
while IFS= read -r file; do
  desc="$(file -b "$file")"
  case "$desc" in
    Mach-O*executable*)
      sign --entitlements "$ENTITLEMENTS_INHERIT" "$file"
      ;;
    Mach-O*)
      sign "$file"
      ;;
    *)
      continue
      ;;
  esac
done < "$LIST"

# Nested frameworks (e.g. Python.framework) are signed after their inner contents.
find "$CONTENTS" -type d -path '*.framework/Versions/*' ! -name Current -prune -print | while IFS= read -r version; do
  sign "$version"
done

# The Gemini Notebook Safari extension (scripts/build-safari-extension.sh), with its own
# entitlements and, for the App Store, its own provisioning profile.
for appex in "$CONTENTS"/PlugIns/*.appex; do
  [ -d "$appex" ] || continue
  if [ -n "$EXTENSION_PROFILE_PATH" ]; then
    [ -f "$EXTENSION_PROFILE_PATH" ] || { echo "Provisioning profile not found: $EXTENSION_PROFILE_PATH" >&2; exit 1; }
    cp "$EXTENSION_PROFILE_PATH" "$appex/Contents/embedded.provisionprofile"
    chmod 0644 "$appex/Contents/embedded.provisionprofile"
  fi
  sign --entitlements "$ENTITLEMENTS_EXTENSION" "$appex"
done

sign --entitlements "$ENTITLEMENTS_APP" "$TARGET"
codesign --verify --deep --strict --verbose=2 "$TARGET"

if [ -n "$PKG_OUTPUT" ]; then
  mkdir -p "$(dirname "$PKG_OUTPUT")"
  rm -f "$PKG_OUTPUT"
  if [ -n "$INSTALLER_IDENTITY" ]; then
    productbuild --component "$TARGET" /Applications --sign "$INSTALLER_IDENTITY" "$PKG_OUTPUT"
    pkgutil --check-signature "$PKG_OUTPUT"
  elif [ "$UNSIGNED_PKG" -eq 1 ]; then
    productbuild --component "$TARGET" /Applications "$PKG_OUTPUT"
  else
    echo "Refusing to build $PKG_OUTPUT without --installer-identity (or pass --unsigned-pkg for a dry-run)." >&2
    exit 1
  fi
  echo "Built $PKG_OUTPUT"
fi
