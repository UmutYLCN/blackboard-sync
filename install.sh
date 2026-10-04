#!/bin/sh
# One-line installer for macOS:
#   curl -fsSL https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.sh | sh
# Downloads the latest release (no API calls, so no rate limit), verifies its SHA-256 and copies the app to
# /Applications (or ~/Applications). Never uses sudo and installs nothing else.
set -eu

REPO="UmutYLCN/blackboard-sync"
APP="Blackboard Sync.app"

say() { printf '%s\n' "$*"; }
die() { printf 'Hata: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "Bu komut yalnızca macOS içindir. Windows için README'ye bak."

TMP="$(mktemp -d "${TMPDIR:-/tmp}/blackboard-sync.XXXXXX")"
MNT="$TMP/mnt"
MOUNTED=0
cleanup() {
  if [ "$MOUNTED" = 1 ]; then hdiutil detach "$MNT" -quiet >/dev/null 2>&1 || hdiutil detach "$MNT" -force -quiet >/dev/null 2>&1 || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM HUP

BASE="https://github.com/$REPO/releases/latest/download"

say "==> Son sürüm aranıyor..."
curl -fsSL -o "$TMP/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt" || die "SHA256SUMS.txt indirilemedi. İnternet bağlantını kontrol et."
dmg_name="$(awk '{n=$2; sub(/^\*/, "", n)} n ~ /^Blackboard-Sync-.*\.dmg$/ {print n; exit}' "$TMP/SHA256SUMS.txt")"
[ -n "$dmg_name" ] || die "Son sürümde .dmg bulunamadı."

say "==> $dmg_name indiriliyor..."
curl -fSL --progress-bar -o "$TMP/$dmg_name" "$BASE/$dmg_name" || die "İndirme başarısız oldu."

say "==> Sağlama toplamı doğrulanıyor..."
expected="$(awk -v f="$dmg_name" '{n=$2; sub(/^\*/, "", n)} n == f {print $1; exit}' "$TMP/SHA256SUMS.txt")"
[ -n "$expected" ] || die "SHA256SUMS.txt içinde $dmg_name bulunamadı."
actual="$(shasum -a 256 "$TMP/$dmg_name" | awk '{print $1}')"
[ "$expected" = "$actual" ] || die "Sağlama toplamı uyuşmuyor, kurulum iptal edildi."
say "    Doğrulandı."

if pgrep -x "Blackboard Sync" >/dev/null 2>&1; then
  say "==> Çalışan Blackboard Sync kapatılıyor..."
  osascript -e 'tell application "Blackboard Sync" to quit' >/dev/null 2>&1 || true
  i=0
  while pgrep -x "Blackboard Sync" >/dev/null 2>&1 && [ "$i" -lt 10 ]; do sleep 1; i=$((i + 1)); done
  pkill -x "Blackboard Sync" >/dev/null 2>&1 || true
  sleep 1
fi

say "==> Kuruluyor..."
mkdir -p "$MNT"
hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint "$MNT" -quiet "$TMP/$dmg_name" \
  || die "Disk görüntüsü açılamadı."
MOUNTED=1
[ -d "$MNT/$APP" ] || die "Disk görüntüsünde $APP bulunamadı."

dest_dir="/Applications"
if [ ! -w "$dest_dir" ]; then
  dest_dir="$HOME/Applications"
  mkdir -p "$dest_dir"
  say "    /Applications yazılabilir değil, $dest_dir kullanılıyor."
fi
rm -rf "${dest_dir:?}/$APP" 2>/dev/null || die "Eski sürüm silinemedi: $dest_dir/$APP"
ditto "$MNT/$APP" "$dest_dir/$APP" || die "Uygulama $dest_dir klasörüne kopyalanamadı."

hdiutil detach "$MNT" -quiet >/dev/null 2>&1 && MOUNTED=0

# The app is unsigned. Only the quarantine flag of the copy we just installed is
# removed, so macOS does not ask for the right-click > Open step.
say "==> Not: Uygulama imzasız olduğu için yalnızca bu uygulamanın karantina işareti (com.apple.quarantine) kaldırılıyor;"
say "    böylece sağ tık → Aç adımı gerekmez. Başka hiçbir şeye dokunulmuyor."
xattr -dr com.apple.quarantine "$dest_dir/$APP" 2>/dev/null || true

say "==> Blackboard Sync açılıyor..."
open "$dest_dir/$APP"
say "Kurulum tamamlandı: $dest_dir/$APP"
