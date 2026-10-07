#!/bin/sh
# One-line installer for macOS:
#   curl -fsSL https://raw.githubusercontent.com/UmutYLCN/blackboard-sync/main/install.sh | sh
# Downloads the latest release (no API calls, so no rate limit), verifies its SHA-256 and, for a signed
# release, its Developer ID signature and notarization, then copies the app to /Applications (or
# ~/Applications; BBSYNC_INSTALL_DIR overrides both). Never uses sudo and installs nothing else.
set -eu

REPO="UmutYLCN/blackboard-sync"
APP="Blackboard Sync.app"
# A signed app must come from this Apple Developer team with this bundle identifier. The release
# workflow refuses to sign with a certificate of another team (docs/SIGNING.md).
TEAM_ID="H4JR94W8MJ"
BUNDLE_ID="io.github.umutylcn.blackboard-sync"
# Developer ID Application certificate issued by Apple, of TEAM_ID, for BUNDLE_ID.
REQUIREMENT="anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] exists and certificate leaf[field.1.2.840.113635.100.6.1.13] exists and certificate leaf[subject.OU] = \"$TEAM_ID\" and identifier \"$BUNDLE_ID\""

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

# Releases signed with the Developer ID must pass every check, or nothing is installed. Older
# releases are unsigned (ad-hoc signed only) and are installed as before.
SIGNED=0
if codesign -dv --verbose=2 "$MNT/$APP" 2>&1 | grep -q '^Authority=Developer ID Application:'; then
  SIGNED=1
  say "==> İmza ve Apple onayı (notarization) doğrulanıyor..."
  codesign --verify --deep --strict "$MNT/$APP" >/dev/null 2>&1 \
    || die "Uygulamanın imzası geçersiz, kurulum iptal edildi."
  codesign --verify --test-requirement="=$REQUIREMENT" "$MNT/$APP" >/dev/null 2>&1 \
    || die "Uygulama Blackboard Sync geliştiricisi tarafından imzalanmamış, kurulum iptal edildi."
  if spctl --status 2>/dev/null | grep -q 'assessments disabled'; then
    say "    Uyarı: Gatekeeper bu Mac'te kapalı; Apple onayı denetlenemedi, imza doğrulandı."
  else
    gatekeeper="$(spctl --assess --type execute --verbose=2 "$MNT/$APP" 2>&1)" || gatekeeper=""
    printf '%s\n' "$gatekeeper" | grep -q '^source=Notarized Developer ID$' \
      || die "Uygulama Apple tarafından onaylanmamış (notarization), kurulum iptal edildi."
  fi
  say "    Doğrulandı."
fi

if [ -n "${BBSYNC_INSTALL_DIR:-}" ]; then
  dest_dir="$BBSYNC_INSTALL_DIR"
  mkdir -p "$dest_dir"
else
  dest_dir="/Applications"
fi
if [ ! -w "$dest_dir" ]; then
  dest_dir="$HOME/Applications"
  mkdir -p "$dest_dir"
  say "    /Applications yazılabilir değil, $dest_dir kullanılıyor."
fi
rm -rf "${dest_dir:?}/$APP" 2>/dev/null || die "Eski sürüm silinemedi: $dest_dir/$APP"
ditto "$MNT/$APP" "$dest_dir/$APP" || die "Uygulama $dest_dir klasörüne kopyalanamadı."

hdiutil detach "$MNT" -quiet >/dev/null 2>&1 && MOUNTED=0

if [ "$SIGNED" = 0 ]; then
  # An unsigned release. Only the quarantine flag of the copy we just installed is
  # removed, so macOS does not ask for the right-click > Open step.
  say "==> Not: Bu sürüm imzasız olduğu için yalnızca bu uygulamanın karantina işareti (com.apple.quarantine) kaldırılıyor;"
  say "    böylece sağ tık → Aç adımı gerekmez. Başka hiçbir şeye dokunulmuyor."
  xattr -dr com.apple.quarantine "$dest_dir/$APP" 2>/dev/null || true
fi

say "==> Blackboard Sync açılıyor..."
open "$dest_dir/$APP"
say "Kurulum tamamlandı: $dest_dir/$APP"
