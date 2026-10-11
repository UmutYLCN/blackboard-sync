#!/usr/bin/env bash
# Saves a PNG of a page with headless Google Chrome:
#   shot.sh <url> <out.png> <width> <height>
# Chrome's headless mode writes the screenshot but does not always exit, so this
# waits for the file and then stops that Chrome.
set -euo pipefail

url="$1" file="$2" width="$3" height="$4"
chrome="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
profile="$(mktemp -d)"
tmp="$profile/shot.png"

"$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --user-data-dir="$profile" --window-size="$width,$height" --virtual-time-budget=3000 \
  --screenshot="$tmp" "$url" >/dev/null 2>&1 &
pid=$!
for _ in $(seq 1 300); do
  if [[ -s "$tmp" ]] || ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 0.1
done
sleep 0.5  # let Chrome finish writing
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
if [[ ! -s "$tmp" ]]; then
  echo "Chrome wrote no screenshot for $url" >&2
  rm -rf "$profile"
  exit 1
fi
mv "$tmp" "$file"
rm -rf "$profile"
