#!/bin/sh
# Build the Gemini Notebook Safari Web Extension (packaging/safari-extension) into an app bundle's
# Contents/PlugIns, for the Mac App Store build. Unsigned: scripts/sign-mas.sh signs it.
#
#   ./scripts/build-safari-extension.sh "dist/Blackboard Sync.app"
#
# The extension takes its bundle id (the app's plus .SafariExtension), version and architectures
# from the app.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: scripts/build-safari-extension.sh APP_PATH}"
[ -f "$APP/Contents/Info.plist" ] || { echo "App bundle not found: $APP" >&2; exit 1; }

SRC="$ROOT/packaging/safari-extension"
plist() { /usr/libexec/PlistBuddy -c "Print :$1" "$APP/Contents/Info.plist"; }
APP_ID="$(plist CFBundleIdentifier)"
SHORT_VERSION="$(plist CFBundleShortVersionString)"
BUILD_VERSION="$(plist CFBundleVersion)"
MIN_MACOS="$(plist LSMinimumSystemVersion)"
MAIN="$APP/Contents/MacOS/$(plist CFBundleExecutable)"
ARCHS="$(lipo -archs "$MAIN" 2>/dev/null || uname -m)"

NAME="Blackboard Sync Extension"
EXEC="BlackboardSyncExtension"
APPEX="$APP/Contents/PlugIns/$NAME.appex"
rm -rf "$APPEX"
mkdir -p "$APPEX/Contents/MacOS" "$APPEX/Contents/Resources"

cat > "$APPEX/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>$APP_ID.SafariExtension</string>
<key>CFBundleName</key><string>$NAME</string>
<key>CFBundleDisplayName</key><string>Blackboard Sync for Gemini Notebook</string>
<key>CFBundleExecutable</key><string>$EXEC</string>
<key>CFBundlePackageType</key><string>XPC!</string>
<key>CFBundleShortVersionString</key><string>$SHORT_VERSION</string>
<key>CFBundleVersion</key><string>$BUILD_VERSION</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleSupportedPlatforms</key><array><string>MacOSX</string></array>
<key>LSMinimumSystemVersion</key><string>$MIN_MACOS</string>
<key>NSExtension</key><dict>
  <key>NSExtensionPointIdentifier</key><string>com.apple.Safari.web-extension</string>
  <key>NSExtensionPrincipalClass</key><string>SafariWebExtensionHandler</string>
</dict>
</dict></plist>
PLIST

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
SLICES=""
for arch in $ARCHS; do
  swiftc -O -target "$arch-apple-macos$MIN_MACOS" -application-extension -module-name "$EXEC" \
    -o "$BUILD/$EXEC-$arch" "$SRC/SafariWebExtensionHandler.swift" \
    -framework SafariServices -Xlinker -e -Xlinker _NSExtensionMain
  SLICES="$SLICES $BUILD/$EXEC-$arch"
done
# shellcheck disable=SC2086 # one path per architecture
lipo -create $SLICES -output "$APPEX/Contents/MacOS/$EXEC"

cp -R "$SRC/Resources/." "$APPEX/Contents/Resources/"
IMAGES="$APPEX/Contents/Resources/images"
mkdir -p "$IMAGES"
for size in 48 96 128 256 512; do
  sips -z "$size" "$size" "$ROOT/assets/icon/logo.png" --out "$IMAGES/icon-$size.png" >/dev/null
done
for size in 16 19 32 38; do
  sips -z "$size" "$size" "$ROOT/assets/icon/logo.png" --out "$IMAGES/toolbar-$size.png" >/dev/null
done
echo "Built Safari extension: $APPEX ($APP_ID.SafariExtension, $ARCHS)"
