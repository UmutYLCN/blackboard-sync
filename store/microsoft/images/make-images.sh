#!/usr/bin/env bash
# Renders the Store listing images that are not screenshots:
#   hero-art.png        16:9 Super hero art, 1920x1080 (src/hero-art.html)
#   poster-art.png      portrait poster art, 1440x2160 (src/brand-art.html)
#   box-art.png         1:1 box art, 2160x2160 (src/brand-art.html)
#   store-logo-*.png    1:1 app tile icons, 300, 150 and 71 px (assets/icon/logo.png)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
"$here/../shot.sh" "file://$here/src/hero-art.html" "$here/hero-art.png" 1920 1080
"$here/../shot.sh" "file://$here/src/brand-art.html" "$here/poster-art.png" 1440 2160
"$here/../shot.sh" "file://$here/src/brand-art.html" "$here/box-art.png" 2160 2160
for size in 300 150 71; do
  sips -z "$size" "$size" "$here/../../../assets/icon/logo.png" --out "$here/store-logo-$size.png" >/dev/null
  echo "$here/store-logo-$size.png"
done
echo "$here/hero-art.png"
echo "$here/poster-art.png"
echo "$here/box-art.png"
