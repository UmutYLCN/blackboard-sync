"""macOS: replace the running app with a downloaded release and restart it; no GUI code.

The way other Mac apps update (Sparkle), without Sparkle:

1. the release's .dmg is downloaded into a private temporary folder
   (``updater.download`` checks its SHA-256);
2. it is attached hidden and read-only to a private mount point;
3. the app on it is checked before anything on disk changes: the expected
   bundle identifier and version, a valid Developer ID signature of the same
   team as the running app, and Gatekeeper's notarization verdict - the
   checks ``install.sh`` makes;
4. it is copied with ``ditto`` to a hidden sibling of the running app
   (``.Blackboard Sync.app.new.<pid>``) and the image is detached;
5. a small detached shell helper waits for this process to exit, sets the old
   app aside, renames the new one into its place, deletes the old one (or
   restores it if a step fails, like ``install.sh``) and opens the app again.

The running app cannot be swapped by itself: its own files are in use until
it exits, and its sync jobs re-run its executable. Where none of this is safe
(no app bundle, an app run from a disk image or translocated by Gatekeeper, a
folder this user cannot write, an unsigned app) ``ManualUpdate`` says why, and
the menu bar app falls back to opening the .dmg for the student.
"""

from __future__ import annotations

import logging
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from blackboard_sync import updater
from blackboard_sync.errors import AlreadyRunning
from blackboard_sync.sync import run_lock
from blackboard_sync.updater import Release, UpdateError

log = logging.getLogger(__name__)

APP_NAME = "Blackboard Sync.app"
# The same values as install.sh (tests keep them in step): the bundle a release carries.
TEAM_ID = "H4JR94W8MJ"
BUNDLE_ID = "io.github.umutylcn.blackboard-sync"
HDIUTIL = "/usr/bin/hdiutil"
CODESIGN = "/usr/bin/codesign"
SPCTL = "/usr/sbin/spctl"
DITTO = "/usr/bin/ditto"
OPEN = "/usr/bin/open"
SH = "/bin/sh"
TOOL_TIMEOUT = 300  # spctl may ask Apple about the notarization ticket
QUIT_WAIT_SECONDS = 120

T_BUSY = (
    "Senkronizasyon veya klasör taşıma sürerken güncelleme yüklenemez; "
    "bittikten sonra tekrar deneyin."
)
T_KEPT = "mevcut sürüm korunuyor."
T_ATTACH = f"Güncellemenin disk görüntüsü açılamadı; {T_KEPT}"
T_NO_APP = f"Disk görüntüsünde Blackboard Sync bulunamadı; {T_KEPT}"
T_WRONG_APP = f"İndirilen güncelleme beklenen Blackboard Sync sürümü değil; {T_KEPT}"
T_BAD_SIGNATURE = f"Güncellemenin imzası geçersiz; {T_KEPT}"
T_OTHER_TEAM = f"Güncelleme Blackboard Sync geliştiricisi tarafından imzalanmamış; {T_KEPT}"
T_NOT_NOTARIZED = f"Güncelleme Apple tarafından onaylanmamış (notarization); {T_KEPT}"
T_COPY = f"Yeni sürüm kopyalanamadı; {T_KEPT}"
T_HANDOFF = f"Güncelleme başlatılamadı; {T_KEPT}"

# Why the app cannot replace itself; shown before the steps of the manual update.
T_FROM_IMAGE = "Blackboard Sync disk görüntüsünden çalıştığı için kendini güncelleyemiyor."
T_TRANSLOCATED = (
    "macOS, Blackboard Sync'i geçici bir konumdan çalıştırdığı için uygulama kendini güncelleyemiyor."
)
T_NOT_WRITABLE = (
    "Blackboard Sync'in bulunduğu klasöre yazılamadığı için uygulama kendini güncelleyemiyor."
)
T_UNSIGNED = "Bu sürüm imzasız olduğu için güncelleme otomatik doğrulanıp yüklenemiyor."

# Waits for the app (pid $1) to exit, swaps $3 into $2 with $4 as the old app's
# temporary name, then starts the app with $5 (``open``). Any failed step puts
# the old app back and starts it, so the student is never left without one.
SWAP_SCRIPT = """
pid=$1 app=$2 new=$3 old=$4 open=$5 wait=$6
say() { printf 'update helper: %s\\n' "$*"; }
i=0
while kill -0 "$pid" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt "$wait" ]; then
    say "the app did not quit; update cancelled"
    rm -rf "$new"
    exit 1
  fi
  sleep 1
done
rm -rf "$old"
if ! mv "$app" "$old"; then
  say "could not set the old app aside; nothing changed"
  rm -rf "$new"
  "$open" "$app"
  exit 1
fi
if [ -e "$app" ] || ! mv "$new" "$app"; then
  say "could not move the new app into place; restoring the old one"
  [ -e "$app" ] || mv "$old" "$app" || say "could not restore $old"
  rm -rf "$new"
  "$open" "$app"
  exit 1
fi
rm -rf "$old" || say "could not delete the old app: $old"
say "installed $app"
"$open" "$app"
"""

Run = Callable[[list[str]], subprocess.CompletedProcess]


class ManualUpdate(Exception):
    """The app cannot replace itself here; the message (Turkish) says why."""


@dataclass(frozen=True)
class Target:
    """The running app bundle and the Developer ID team that signed it."""

    bundle: Path
    team: str


def run_tool(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run one of Apple's tools; a tool that cannot start or hangs counts as failed."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TOOL_TIMEOUT
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def requirement(team: str) -> str:
    """A Developer ID Application certificate issued by Apple, of ``team``, for this bundle id."""
    return (
        "anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] exists "
        "and certificate leaf[field.1.2.840.113635.100.6.1.13] exists "
        f'and certificate leaf[subject.OU] = "{team}" and identifier "{BUNDLE_ID}"'
    )


def signing_team(app: Path, run: Run = run_tool) -> str | None:
    """The team of the Developer ID that signed ``app``; None when unsigned or ad-hoc signed."""
    result = run([CODESIGN, "-dv", "--verbose=2", str(app)])
    if result.returncode != 0:
        return None
    text = f"{result.stdout}\n{result.stderr}"
    if not re.search(r"^Authority=Developer ID Application:", text, re.MULTILINE):
        return None
    team = re.search(r"^TeamIdentifier=(\S+)$", text, re.MULTILINE)
    return team.group(1) if team and team.group(1) != "not set" else None


def mounted_images(run: Run = run_tool) -> list[Path]:
    """Mount points of the disk images attached right now."""
    result = run([HDIUTIL, "info", "-plist"])
    try:
        info = plistlib.loads(result.stdout.encode()) if result.returncode == 0 else {}
    except (plistlib.InvalidFileException, ValueError):
        return []
    return [
        Path(entity["mount-point"])
        for image in info.get("images", []) if isinstance(image, dict)
        for entity in image.get("system-entities", []) if isinstance(entity, dict) and entity.get("mount-point")
    ]


def find_target(
    bundle: Path | None,
    run: Run = run_tool,
    writable: Callable[[Path], bool] = lambda p: os.access(p, os.W_OK),
) -> Target:
    """The running app, if it can replace itself; raises ``ManualUpdate`` otherwise."""
    if bundle is None:
        raise ManualUpdate(T_NOT_WRITABLE)
    if "/AppTranslocation/" in str(bundle):
        raise ManualUpdate(T_TRANSLOCATED)
    if any(bundle.is_relative_to(mount) for mount in mounted_images(run)):
        raise ManualUpdate(T_FROM_IMAGE)
    if not (writable(bundle.parent) and writable(bundle)):
        raise ManualUpdate(T_NOT_WRITABLE)
    team = signing_team(bundle, run)
    if team is None:
        # Nothing to compare the new app's signature with.
        raise ManualUpdate(T_UNSIGNED)
    return Target(bundle, team)


@contextmanager
def attached(dmg: Path, mount_point: Path, run: Run = run_tool) -> Iterator[Path]:
    """Attach ``dmg`` read-only and hidden from Finder at ``mount_point``; always detach."""
    mount_point.mkdir(parents=True, exist_ok=True)
    result = run([
        HDIUTIL, "attach", "-readonly", "-nobrowse", "-noverify", "-noautoopen",
        "-mountpoint", str(mount_point), "-quiet", str(dmg),
    ])
    if result.returncode != 0:
        log.warning("hdiutil attach failed: %s", result.stderr.strip())
        raise UpdateError(T_ATTACH)
    try:
        yield mount_point
    finally:
        if run([HDIUTIL, "detach", str(mount_point), "-quiet"]).returncode != 0:
            run([HDIUTIL, "detach", str(mount_point), "-force", "-quiet"])


def verify(app: Path, team: str, version: str, run: Run = run_tool) -> None:
    """Refuse an app that is not this release, signed by ``team`` and notarized."""
    try:
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    except FileNotFoundError:
        raise UpdateError(T_NO_APP) from None
    except (OSError, plistlib.InvalidFileException, ValueError):
        raise UpdateError(T_WRONG_APP) from None
    if info.get("CFBundleIdentifier") != BUNDLE_ID or info.get("CFBundleShortVersionString") != version:
        raise UpdateError(T_WRONG_APP)
    if run([CODESIGN, "--verify", "--deep", "--strict", str(app)]).returncode != 0:
        raise UpdateError(T_BAD_SIGNATURE)
    if signing_team(app, run) != team or run(
        [CODESIGN, "--verify", f"--test-requirement=={requirement(team)}", str(app)]
    ).returncode != 0:
        raise UpdateError(T_OTHER_TEAM)
    status = run([SPCTL, "--status"])
    if "assessments disabled" in f"{status.stdout}{status.stderr}":
        log.warning("Gatekeeper is off on this Mac; notarization not checked, signature verified")
        return
    verdict = run([SPCTL, "--assess", "--type", "execute", "--verbose=2", str(app)])
    lines = f"{verdict.stdout}\n{verdict.stderr}".splitlines()
    if verdict.returncode != 0 or "source=Notarized Developer ID" not in lines:
        raise UpdateError(T_NOT_NOTARIZED)


def sibling(target: Target, kind: str, pid: int) -> Path:
    """``.Blackboard Sync.app.new.<pid>``: hidden, next to the app, so renames stay on one disk."""
    return target.bundle.parent / f".{target.bundle.name}.{kind}.{pid}"


def stage(app: Path, target: Target, pid: int, run: Run = run_tool) -> Path:
    """Copy the verified app next to the running one; the copy is checked again."""
    staged = sibling(target, "new", pid)
    shutil.rmtree(staged, ignore_errors=True)
    if (
        run([DITTO, str(app), str(staged)]).returncode != 0
        or run([CODESIGN, "--verify", "--deep", "--strict", str(staged)]).returncode != 0
    ):
        shutil.rmtree(staged, ignore_errors=True)
        raise UpdateError(T_COPY)
    return staged


def swap_command(target: Target, staged: Path, pid: int, open_cmd: str = OPEN,
                 wait: int = QUIT_WAIT_SECONDS) -> list[str]:
    return [
        SH, "-c", SWAP_SCRIPT, "blackboard-sync-update", str(pid), str(target.bundle),
        str(staged), str(sibling(target, "old", pid)), open_cmd, str(wait),
    ]


def hand_off(target: Target, staged: Path, pid: int, log_file: Path | None = None,
             popen: Callable[..., object] = subprocess.Popen) -> None:
    """Start the swap helper, detached: it outlives this process and its launchd job."""
    try:
        with open(log_file or os.devnull, "ab") as out:
            popen(
                swap_command(target, staged, pid), stdin=subprocess.DEVNULL, stdout=out,
                stderr=subprocess.STDOUT, close_fds=True, start_new_session=True,
            )
    except OSError as exc:
        shutil.rmtree(staged, ignore_errors=True)
        raise UpdateError(T_HANDOFF) from exc


def install(
    release: Release,
    target: Target,
    lock_file: Path,
    log_file: Path | None = None,
    get: updater.Getter = updater._get,
    run: Run = run_tool,
    popen: Callable[..., object] = subprocess.Popen,
    pid: int | None = None,
) -> None:
    """Download, verify and stage ``release``, then start the helper that swaps it in.

    Raises ``UpdateError`` (Turkish) with the running app untouched. On return
    the caller quits at once; the helper replaces the app and opens it again.
    Holds the run lock throughout, so it never overlaps a sync or folder move.
    """
    pid = os.getpid() if pid is None else pid
    try:
        with run_lock(lock_file), tempfile.TemporaryDirectory(
            prefix="blackboard-sync-update.", ignore_cleanup_errors=True
        ) as work:
            dmg = updater.download(release, Path(work), get)
            with attached(dmg, Path(work) / "mnt", run) as volume:
                app = volume / APP_NAME
                verify(app, target.team, release.version, run)
                staged = stage(app, target, pid, run)
            hand_off(target, staged, pid, log_file, popen)
    except AlreadyRunning as exc:
        raise UpdateError(T_BUSY) from exc
    log.info("update %s staged at %s; quitting for the swap", release.version, staged)
