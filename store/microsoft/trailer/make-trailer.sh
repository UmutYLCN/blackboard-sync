#!/usr/bin/env bash
# Builds the Microsoft Store trailer from the vertical promo video (1080x1350):
#   ../out/trailer-1920x1080.mp4    the trailer to upload (MP4, 1920x1080)
#   ../out/trailer-thumbnail.png    its thumbnail (PNG, 1920x1080, a still at 21 s)
#
#   ./store/microsoft/trailer/make-trailer.sh [promo.mp4]
#
# Without an argument it downloads the promo video from the README's GitHub
# link into ../out/promo.mp4. The video is centred at 800x1000 on
# src/background.html. It is cut at 54.15 s, where the LinkedIn "Link
# yorumlarda" line appears, and its last frame is held for 2.5 s with a fade.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
out="$here/../out"
mkdir -p "$out"
promo="${1:-$out/promo.mp4}"
if [[ ! -f "$promo" ]]; then
  curl -fL -o "$promo" https://github.com/user-attachments/assets/d7e1e0a7-a25b-4412-824b-52ee71d25b03
fi

"$here/../shot.sh" "file://$here/src/background.html" "$out/trailer-background.png" 1920 1080

cut=54.15 hold=2.5
total=$(echo "$cut + $hold" | bc)
ffmpeg -v error -y -loop 1 -framerate 30 -i "$out/trailer-background.png" -i "$promo" \
  -filter_complex "\
[1:v]trim=0:$cut,setpts=PTS-STARTPTS,scale=800:1000:flags=lanczos,tpad=stop_mode=clone:stop_duration=${hold}[v];\
[0:v][v]overlay=560:40:shortest=1,fps=30,format=yuv420p,fade=t=out:st=$(echo "$total - 0.6" | bc):d=0.6[vout];\
[1:a]atrim=0:$cut,asetpts=PTS-STARTPTS,apad=pad_dur=$hold,afade=t=out:st=$(echo "$total - 2" | bc):d=2,\
aresample=48000,pan=stereo|c0=c0|c1=c0[aout]" \
  -map "[vout]" -map "[aout]" -t "$total" \
  -c:v libx264 -profile:v high -preset slow -crf 12 -maxrate 50M -bufsize 50M \
  -g 15 -keyint_min 15 -sc_threshold 0 -flags +cgop -bf 2 -pix_fmt yuv420p \
  -c:a aac -b:a 384k -ar 48000 -ac 2 \
  -movflags +faststart "$out/trailer-1920x1080.mp4"

ffmpeg -v error -y -ss 21 -i "$out/trailer-1920x1080.mp4" -frames:v 1 "$out/trailer-thumbnail.png"
echo "$out/trailer-1920x1080.mp4"
echo "$out/trailer-thumbnail.png"
