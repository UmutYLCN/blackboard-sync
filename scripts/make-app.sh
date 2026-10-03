#!/bin/sh
# Build "Blackboard Sync.app": a double-clickable launcher for the menu bar app
# that runs it from this checkout's .venv. Drag it to /Applications (or anywhere)
# afterwards. Rebuild it if you move this repository.
set -eu
cd "$(dirname "$0")/.."
REPO="$(pwd -P)"
if [ ! -x "$REPO/.venv/bin/python" ]; then
  echo "Run ./scripts/setup.sh first." >&2
  exit 1
fi
APP="${1:-$REPO/dist/Blackboard Sync.app}"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Blackboard Sync</string>
  <key>CFBundleIdentifier</key><string>io.github.umutylcn.blackboard-sync.launcher</string>
  <key>CFBundleExecutable</key><string>blackboard-sync-menubar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST
cat > "$APP/Contents/MacOS/blackboard-sync-menubar" <<LAUNCHER
#!/bin/sh
exec "$REPO/.venv/bin/python" -m blackboard_sync.menubar --detach
LAUNCHER
chmod +x "$APP/Contents/MacOS/blackboard-sync-menubar"
echo "Built $APP"
