#!/usr/bin/env bash
# Renders the Microsoft Store screenshots (1920x1080 PNG) from src/template.html
# with Node.js (shot manifest) and headless Chrome (../shot.sh; CHROME overrides
# its path).
#
#   ./store/microsoft/screenshots/render.sh           # Turkish, into screenshots/
#   ./store/microsoft/screenshots/render.sh --lang en # English, into screenshots/en/
#
# For each capture in src/shots.js the app image is src/windows/<id>.png (Turkish) or
# src/windows/<lang>/<id>.png, made by capture.py, when it exists
# (final image: <id>.png). Otherwise it is src/draft-input/<id>.png, or a
# placeholder when there is none, and the image is a draft: draft-<id>.png,
# marked DRAFT on the image.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
lang="tr"
if [[ "${1:-}" == "--lang" ]]; then lang="${2:?--lang needs tr, en, es, fr, de or ar}"; fi
case "$lang" in
  tr) out="$here"; windows="windows" ;;
  en|es|fr|de|ar) out="$here/$lang"; windows="windows/$lang" ;;
  *) echo "unknown language: $lang" >&2; exit 2 ;;
esac
mkdir -p "$out"

shots=$(node -e '
  global.window = {};
  require(process.argv[1]);
  for (const shot of window.SHOTS) console.log(shot.id);
' "$here/src/shots.js")
while IFS= read -r id; do
  query="shot=$id&lang=$lang"
  if [[ -f "$here/src/$windows/$id.png" ]]; then
    query+="&img=$windows/$id.png"
    file="$out/$id.png"
    rm -f "$out/draft-$id.png"
  else
    [[ -f "$here/src/draft-input/$id.png" ]] && query+="&img=draft-input/$id.png"
    query+="&draft=1"
    file="$out/draft-$id.png"
  fi
  "$here/../shot.sh" "file://$here/src/template.html?$query" "$file" 1920 1080
  echo "$file"
done <<< "$shots"
