"""install.sh with the network, the disk image and Apple's signing tools faked.

curl, hdiutil, codesign, spctl, xattr and the process tools are small shell
scripts placed first on PATH; ``FAKE_*`` variables pick what each one reports.
The real codesign requirement and spctl output were checked against a notarized
Developer ID app; what these tests check is which answer installs and which refuses.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="install.sh is the macOS installer")

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = ROOT / "install.sh"
DMG_NAME = "Blackboard-Sync-1.3.0.dmg"
DMG = b"fake disk image" * 100
TEAM_ID = "H4JR94W8MJ"

FAKES = {
    # curl -fsSL -o FILE URL: serves the dmg and SHA256SUMS.txt from $FAKE_RELEASE.
    "curl": """
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift 2 ;; -*) shift ;; *) url="$1"; shift ;; esac
done
cp "$FAKE_RELEASE/${url##*/}" "$out"
""",
    # attach ... -mountpoint DIR ... IMAGE: "mounts" the app from $FAKE_RELEASE/volume.
    "hdiutil": """
if [ "$1" = attach ]; then
  while [ $# -gt 0 ]; do [ "$1" = -mountpoint ] && mnt="$2"; shift; done
  cp -R "$FAKE_RELEASE/volume/." "$mnt/"
fi
""",
    # FAKE_SIGNATURE: adhoc | devid | devid-other-team | devid-broken
    "codesign": """
case "$1" in
  -dv)
    case "$FAKE_SIGNATURE" in
      adhoc) echo "Signature=adhoc" >&2 ;;
      devid*) echo "Authority=Developer ID Application: Someone ($FAKE_TEAM)" >&2
              echo "Authority=Developer ID Certification Authority" >&2 ;;
    esac
    exit 0 ;;
  --verify)
    [ "$FAKE_SIGNATURE" = devid-broken ] && exit 1
    case "$2" in
      --test-requirement=*) case "$2" in *"subject.OU] = \\"$FAKE_TEAM\\""*) exit 0 ;; *) exit 3 ;; esac ;;
    esac
    exit 0 ;;
esac
exit 1
""",
    # FAKE_GATEKEEPER: notarized | developer-id | rejected | disabled
    "spctl": """
if [ "$1" = --status ]; then
  [ "$FAKE_GATEKEEPER" = disabled ] && echo "assessments disabled" || echo "assessments enabled"
  exit 0
fi
case "$FAKE_GATEKEEPER" in
  notarized) printf '%s: accepted\\nsource=Notarized Developer ID\\n' "$5" >&2 ;;
  developer-id) printf '%s: accepted\\nsource=Developer ID\\n' "$5" >&2 ;;
  *) printf '%s: rejected\\nsource=Unnotarized Developer ID\\n' "$5" >&2; exit 3 ;;
esac
""",
    "xattr": 'echo "$*" >> "$FAKE_LOG/xattr"',
    # FAKE_DITTO_FAIL=1: writes half of the app and fails, like a full disk.
    "ditto": """
if [ "${FAKE_DITTO_FAIL:-}" = 1 ]; then
  mkdir -p "$2/Contents"; echo "half" > "$2/Contents/partial"; exit 1
fi
exec /usr/bin/ditto "$@"
""",
    "pgrep": "exit 1",
    "open": 'echo "$*" >> "$FAKE_LOG/open"',
    "osascript": "exit 0",
}


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\n" + body)
        tool.chmod(0o755)
    release = tmp_path / "release"
    executable = release / "volume" / "Blackboard Sync.app" / "Contents" / "MacOS" / "Blackboard Sync"
    executable.parent.mkdir(parents=True)
    executable.write_text("new version")
    (release / DMG_NAME).write_bytes(DMG)
    (release / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(DMG).hexdigest()}  {DMG_NAME}\n")
    log = tmp_path / "log"
    log.mkdir()
    apps = tmp_path / "Applications"
    old = apps / "Blackboard Sync.app" / "Contents" / "MacOS" / "Blackboard Sync"
    old.parent.mkdir(parents=True)
    old.write_text("old version")
    return {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "BBSYNC_SYSTEM_APPLICATIONS": str(tmp_path / "system-apps"),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "FAKE_RELEASE": str(release),
        "FAKE_LOG": str(log),
        "FAKE_SIGNATURE": "adhoc",
        "FAKE_TEAM": TEAM_ID,
        "FAKE_GATEKEEPER": "notarized",
        "BBSYNC_INSTALL_DIR": str(apps),
    }


def run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(INSTALL_SH)], env=env, capture_output=True, text=True, timeout=60)


def installed(env: dict) -> str:
    return (Path(env["BBSYNC_INSTALL_DIR"]) / "Blackboard Sync.app/Contents/MacOS/Blackboard Sync").read_text()


def logged(env: dict, tool: str) -> str:
    path = Path(env["FAKE_LOG"]) / tool
    return path.read_text() if path.exists() else ""


def test_unsigned_release_installs_as_before(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert installed(env) == "new version"
    assert "imzasız" in result.stdout
    assert "com.apple.quarantine" in logged(env, "xattr")
    assert "Blackboard Sync.app" in logged(env, "open")


def test_signed_notarized_release_installs_without_touching_quarantine(env):
    env["FAKE_SIGNATURE"] = "devid"
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert installed(env) == "new version"
    assert "Apple onayı" in result.stdout
    assert "imzasız" not in result.stdout
    assert logged(env, "xattr") == ""


@pytest.mark.parametrize(
    "signature, team, gatekeeper",
    [
        ("devid-broken", TEAM_ID, "notarized"),  # modified after signing
        ("devid", "OTHERTEAM1", "notarized"),  # someone else's Developer ID
        ("devid", TEAM_ID, "rejected"),  # not notarized
        ("devid", TEAM_ID, "developer-id"),  # accepted, but not as notarized
    ],
)
def test_signed_release_that_fails_a_check_is_not_installed(env, signature, team, gatekeeper):
    env.update(FAKE_SIGNATURE=signature, FAKE_TEAM=team, FAKE_GATEKEEPER=gatekeeper)
    result = run(env)
    assert result.returncode != 0
    assert "kurulum iptal edildi" in result.stderr
    assert installed(env) == "old version"
    assert logged(env, "xattr") == ""
    assert logged(env, "open") == ""


def test_signed_release_with_gatekeeper_off_still_needs_a_valid_signature(env):
    env.update(FAKE_SIGNATURE="devid", FAKE_GATEKEEPER="disabled")
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert installed(env) == "new version"
    assert "Gatekeeper bu Mac'te kapalı" in result.stdout

    env["FAKE_TEAM"] = "OTHERTEAM1"
    (Path(env["FAKE_RELEASE"]) / "volume/Blackboard Sync.app/Contents/MacOS/Blackboard Sync").write_text("other")
    assert run(env).returncode != 0
    assert installed(env) == "new version"


def test_checksum_mismatch_is_not_installed(env):
    (Path(env["FAKE_RELEASE"]) / DMG_NAME).write_bytes(b"tampered")
    result = run(env)
    assert result.returncode != 0
    assert "Sağlama toplamı uyuşmuyor" in result.stderr
    assert installed(env) == "old version"


def leftovers(env: dict) -> list[str]:
    return sorted(p.name for p in Path(env["BBSYNC_INSTALL_DIR"]).iterdir() if p.name != "Blackboard Sync.app")


def test_failed_copy_keeps_the_old_app_and_removes_the_temporary_copy(env):
    env["FAKE_DITTO_FAIL"] = "1"
    result = run(env)
    assert result.returncode != 0
    assert "kopyalanamadı" in result.stderr
    assert installed(env) == "old version"
    assert leftovers(env) == []
    assert logged(env, "open") == ""


def test_successful_install_replaces_the_app_and_leaves_no_temporary_copy(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert installed(env) == "new version"
    assert leftovers(env) == []


def test_fresh_install_without_an_old_app(env):
    old = Path(env["BBSYNC_INSTALL_DIR"]) / "Blackboard Sync.app"
    subprocess.run(["rm", "-rf", str(old)], check=True)
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert installed(env) == "new version"
    assert leftovers(env) == []


def test_refused_signature_leaves_no_temporary_copy(env):
    env.update(FAKE_SIGNATURE="devid-broken")
    assert run(env).returncode != 0
    assert installed(env) == "old version"
    assert leftovers(env) == []


def test_other_location_copy_is_reported_and_not_deleted(env, tmp_path):
    # /Applications (faked) is not writable, so the app goes to ~/Applications.
    system = tmp_path / "system-apps"
    stale = system / "Blackboard Sync.app" / "Contents"
    stale.mkdir(parents=True)
    system.chmod(0o555)
    try:
        del env["BBSYNC_INSTALL_DIR"]
        result = run(env)
    finally:
        system.chmod(0o755)
    assert result.returncode == 0, result.stderr
    user_app = tmp_path / "home/Applications/Blackboard Sync.app/Contents/MacOS/Blackboard Sync"
    assert user_app.read_text() == "new version"
    assert stale.exists()
    assert f"{system}/Blackboard Sync.app içinde başka bir kopya var" in result.stdout
    assert f"güncel sürüm {tmp_path}/home/Applications/Blackboard Sync.app" in result.stdout


def test_no_warning_when_there_is_no_other_copy(env):
    result = run(env)
    assert "başka bir kopya" not in result.stdout
