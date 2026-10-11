#!/usr/bin/env bash
# Renders the Store listing images that are not screenshots:
#   hero-art.png        16:9 Super hero art, 1920x1080 (src/hero-art.html)
#   store-logo-300.png  1:1 app tile icon, 300x300 (assets/icon/logo.png)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
"$here/../shot.sh" "file://$here/src/hero-art.html" "$here/hero-art.png" 1920 1080
sips -z 300 300 "$here/../../../assets/icon/logo.png" --out "$here/store-logo-300.png" >/dev/null
echo "$here/hero-art.png"
echo "$here/store-logo-300.png"
