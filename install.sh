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
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "This command is for macOS only. For Windows, see the README."

TMP="$(mktemp -d "${TMPDIR:-/tmp}/blackboard-sync.XXXXXX")"
MNT="$TMP/mnt"
MOUNTED=0
cleanup() {
  if [ "$MOUNTED" = 1 ]; then hdiutil detach "$MNT" -quiet >/dev/null 2>&1 || hdiutil detach "$MNT" -force -quiet >/dev/null 2>&1 || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM HUP

BASE="https://github.com/$REPO/releases/latest/download"

say "==> Looking for the latest version..."
curl -fsSL -o "$TMP/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt" || die "Could not download SHA256SUMS.txt. Check your internet connection."
dmg_name="$(awk '{n=$2; sub(/^\*/, "", n)} n ~ /^Blackboard-Sync-.*\.dmg$/ {print n; exit}' "$TMP/SHA256SUMS.txt")"
[ -n "$dmg_name" ] || die "The latest release has no .dmg."

say "==> Downloading $dmg_name..."
curl -fSL --progress-bar -o "$TMP/$dmg_name" "$BASE/$dmg_name" || die "The download failed."

say "==> Verifying the checksum..."
expected="$(awk -v f="$dmg_name" '{n=$2; sub(/^\*/, "", n)} n == f {print $1; exit}' "$TMP/SHA256SUMS.txt")"
[ -n "$expected" ] || die "$dmg_name is not listed in SHA256SUMS.txt."
actual="$(shasum -a 256 "$TMP/$dmg_name" | awk '{print $1}')"
[ "$expected" = "$actual" ] || die "The checksum does not match; installation cancelled."
say "    Verified."

if pgrep -x "Blackboard Sync" >/dev/null 2>&1; then
  say "==> Quitting the running Blackboard Sync..."
  osascript -e 'tell application "Blackboard Sync" to quit' >/dev/null 2>&1 || true
  i=0
  while pgrep -x "Blackboard Sync" >/dev/null 2>&1 && [ "$i" -lt 10 ]; do sleep 1; i=$((i + 1)); done
  pkill -x "Blackboard Sync" >/dev/null 2>&1 || true
  sleep 1
fi

say "==> Installing..."
mkdir -p "$MNT"
hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint "$MNT" -quiet "$TMP/$dmg_name" \
  || die "Could not open the disk image."
MOUNTED=1
[ -d "$MNT/$APP" ] || die "$APP was not found in the disk image."

# Releases signed with the Developer ID must pass every check, or nothing is installed. Older
# releases are unsigned (ad-hoc signed only) and are installed as before.
SIGNED=0
if codesign -dv --verbose=2 "$MNT/$APP" 2>&1 | grep -q '^Authority=Developer ID Application:'; then
  SIGNED=1
  say "==> Verifying the signature and Apple notarization..."
  codesign --verify --deep --strict "$MNT/$APP" >/dev/null 2>&1 \
    || die "The app's signature is not valid; installation cancelled."
  codesign --verify --test-requirement="=$REQUIREMENT" "$MNT/$APP" >/dev/null 2>&1 \
    || die "The app is not signed by the Blackboard Sync developer; installation cancelled."
  if spctl --status 2>/dev/null | grep -q 'assessments disabled'; then
    say "    Warning: Gatekeeper is off on this Mac; notarization could not be checked, the signature was verified."
  else
    gatekeeper="$(spctl --assess --type execute --verbose=2 "$MNT/$APP" 2>&1)" || gatekeeper=""
    printf '%s\n' "$gatekeeper" | grep -q '^source=Notarized Developer ID$' \
      || die "The app is not notarized by Apple; installation cancelled."
  fi
  say "    Verified."
fi

# BBSYNC_SYSTEM_APPLICATIONS only exists so the tests do not touch the real /Applications.
SYSTEM_APPS="${BBSYNC_SYSTEM_APPLICATIONS:-/Applications}"
USER_APPS="$HOME/Applications"
if [ -n "${BBSYNC_INSTALL_DIR:-}" ]; then
  dest_dir="$BBSYNC_INSTALL_DIR"
  mkdir -p "$dest_dir"
else
  dest_dir="$SYSTEM_APPS"
fi
if [ ! -w "$dest_dir" ]; then
  dest_dir="$USER_APPS"
  mkdir -p "$dest_dir"
  say "    $SYSTEM_APPS is not writable; using $dest_dir."
fi

# The new copy is built next to the old app and swapped in only once it is complete, so a failed
# or interrupted copy never leaves the machine without an app. The old app is set aside under a
# temporary name for the swap and deleted only after the new one is in place.
new_app="$dest_dir/.$APP.new.$$"
old_app="$dest_dir/.$APP.old.$$"
rm -rf "$new_app" "$old_app" 2>/dev/null || true
ditto "$MNT/$APP" "$new_app" || { rm -rf "$new_app"; die "Could not copy the app to $dest_dir; the current version was not changed."; }
if [ -e "$dest_dir/$APP" ]; then
  mv "$dest_dir/$APP" "$old_app" || { rm -rf "$new_app"; die "Could not set the old version aside: $dest_dir/$APP; the current version was not changed."; }
fi
if ! mv "$new_app" "$dest_dir/$APP"; then
  [ ! -e "$old_app" ] || mv "$old_app" "$dest_dir/$APP" || true
  rm -rf "$new_app"
  die "Could not put the new version in place; the old version was restored."
fi
rm -rf "$old_app" 2>/dev/null || say "    Warning: could not delete the temporary copy of the old version: $old_app"

# An app in the other standard folder is not touched, but it may be the one that gets opened.
for other_dir in "$SYSTEM_APPS" "$USER_APPS"; do
  [ "$other_dir" != "$dest_dir" ] || continue
  if [ -e "$other_dir/$APP" ]; then
    say "    Warning: there is another copy in $other_dir/$APP and it was not updated; the current version is in $dest_dir/$APP."
    say "    To avoid confusion you can delete the old copy yourself: $other_dir/$APP"
  fi
done

hdiutil detach "$MNT" -quiet >/dev/null 2>&1 && MOUNTED=0

if [ "$SIGNED" = 0 ]; then
  # An unsigned release. Only the quarantine flag of the copy we just installed is
  # removed, so macOS does not ask for the right-click > Open step.
  say "==> Note: this version is unsigned, so only this app's quarantine flag (com.apple.quarantine) is removed;"
  say "    that way the right-click → Open step is not needed. Nothing else is touched."
  xattr -dr com.apple.quarantine "$dest_dir/$APP" 2>/dev/null || true
fi

say "==> Opening Blackboard Sync..."
open "$dest_dir/$APP"
say "Installation complete: $dest_dir/$APP"
