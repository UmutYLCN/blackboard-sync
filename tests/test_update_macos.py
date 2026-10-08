"""The macOS in-place update with Apple's tools faked.

hdiutil, codesign, spctl and ditto are answered by ``FakeMac`` (the same
answers ``test_install_sh.py`` fakes for install.sh); the swap helper is the
real shell script, run against folders under ``tmp_path`` with a fake
``open``. Nothing touches the real /Applications.
"""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from blackboard_sync import update_macos
from blackboard_sync.menubar.model import AppModel, UpdateState
from blackboard_sync.sync import run_lock
from blackboard_sync.update_macos import ManualUpdate, Target
from blackboard_sync.updater import Release, UpdateError

from .conftest import FakeResponse

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the in-place update is macOS only")

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.5.0"
DMG = b"fake disk image" * 100
DMG_NAME = f"Blackboard-Sync-{VERSION}.dmg"
DMG_URL = f"https://github.com/UmutYLCN/blackboard-sync/releases/download/v{VERSION}/{DMG_NAME}"
TEAM = update_macos.TEAM_ID
PID = 4242
RELEASE = Release(
    version=VERSION,
    page_url="https://github.com/UmutYLCN/blackboard-sync/releases/tag/v" + VERSION,
    asset_name=DMG_NAME,
    asset_url=DMG_URL,
    asset_size=len(DMG),
)


def make_app(path: Path, text: str, version: str = VERSION, bundle_id: str = update_macos.BUNDLE_ID) -> Path:
    executable = path / "Contents" / "MacOS" / "Blackboard Sync"
    executable.parent.mkdir(parents=True)
    executable.write_text(text)
    (path / "Contents" / "Info.plist").write_bytes(plistlib.dumps(
        {"CFBundleIdentifier": bundle_id, "CFBundleShortVersionString": version}
    ))
    return path


def app_text(app: Path) -> str:
    return (app / "Contents" / "MacOS" / "Blackboard Sync").read_text()


class FakeMac:
    """Answers the commands ``update_macos`` runs; the attributes pick the answers."""

    def __init__(self, volume: Path, running: Path):
        self.volume = volume  # what "attaching" the image shows
        self.running = running
        self.running_team: str | None = TEAM
        self.new_signature = "devid"  # devid | adhoc | broken
        self.new_team = TEAM
        self.gatekeeper = "notarized"  # notarized | developer-id | rejected | disabled
        self.attach_fails = False
        self.ditto_fails = False
        self.images: list[Path] = []
        self.attached: list[Path] = []
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        tool, args = cmd[0], cmd[1:]
        handler = {
            update_macos.HDIUTIL: self.hdiutil, update_macos.CODESIGN: self.codesign,
            update_macos.SPCTL: self.spctl, update_macos.DITTO: self.ditto,
        }[tool]
        code, out, err = handler(args)
        return subprocess.CompletedProcess(cmd, code, out, err)

    def hdiutil(self, args):
        if args[0] == "info":
            info = {"images": [{"system-entities": [{"mount-point": str(m)} for m in self.images]}]}
            return 0, plistlib.dumps(info).decode(), ""
        if args[0] == "attach":
            assert {"-readonly", "-nobrowse"} <= set(args)
            if self.attach_fails:
                return 1, "", "hdiutil: attach failed - corrupt image"
            mount = Path(args[args.index("-mountpoint") + 1])
            shutil.copytree(self.volume, mount, dirs_exist_ok=True)
            self.attached.append(mount)
            return 0, "", ""
        if args[0] == "detach":
            mount = Path(args[1])
            shutil.rmtree(mount)
            self.attached.remove(mount)
            return 0, "", ""
        return 1, "", "unknown"

    def identity(self, path: Path) -> tuple[str, str | None]:
        if Path(path) == self.running:
            return ("devid" if self.running_team else "adhoc"), self.running_team
        return self.new_signature, self.new_team

    def codesign(self, args):
        app = Path(args[-1])
        signature, team = self.identity(app)
        if args[0] == "-dv":
            if signature == "adhoc":
                return 0, "", "Signature=adhoc\nTeamIdentifier=not set\n"
            return 0, "", (
                f"Authority=Developer ID Application: Someone ({team})\n"
                f"Authority=Developer ID Certification Authority\nTeamIdentifier={team}\n"
            )
        if args[0] == "--verify":
            if signature == "broken":
                return 1, "", f"{app}: invalid signature (code or signature have been modified)"
            if args[1].startswith("--test-requirement="):
                ok = signature == "devid" and f'subject.OU] = "{team}"' in args[1]
                return (0 if ok else 3), "", ""
            return 0, "", ""
        return 1, "", "unknown"

    def spctl(self, args):
        if args[0] == "--status":
            return 0, "assessments disabled\n" if self.gatekeeper == "disabled" else "assessments enabled\n", ""
        app = args[-1]
        if self.gatekeeper == "notarized":
            return 0, "", f"{app}: accepted\nsource=Notarized Developer ID\n"
        if self.gatekeeper == "developer-id":
            return 0, "", f"{app}: accepted\nsource=Developer ID\n"
        return 3, "", f"{app}: rejected\nsource=Unnotarized Developer ID\n"

    def ditto(self, args):
        source, dest = Path(args[0]), Path(args[1])
        if self.ditto_fails:  # a full disk: half a copy
            (dest / "Contents").mkdir(parents=True)
            (dest / "Contents" / "partial").write_text("half")
            return 1, "", "ditto: No space left on device"
        shutil.copytree(source, dest, symlinks=True)
        return 0, "", ""


class Popen:
    """Records the helper's command instead of starting it."""

    def __init__(self):
        self.commands = []

    def __call__(self, cmd, **kwargs):
        assert kwargs["start_new_session"] and kwargs["stdin"] == subprocess.DEVNULL
        self.commands.append(cmd)


@pytest.fixture
def mac(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(update_macos.tempfile, "tempdir", None)
    apps = tmp_path / "Applications"
    running = make_app(apps / update_macos.APP_NAME, "old version", version="1.4.0")
    volume = tmp_path / "volume"
    make_app(volume / update_macos.APP_NAME, "new version")
    fake = FakeMac(volume, running)
    fake.apps = apps
    fake.lock_file = tmp_path / "data" / "sync.lock"
    fake.popen = Popen()
    fake.downloads = []
    return fake


def get(downloads):
    def fake_get(url, **kwargs):
        downloads.append(url)
        assert url == DMG_URL
        return FakeResponse(200, "https://objects.githubusercontent.com/x/dmg", content=DMG)
    return fake_get


def install(mac, release=RELEASE):
    target = update_macos.find_target(mac.running, run=mac)
    update_macos.install(release, target, mac.lock_file, get=get(mac.downloads), run=mac,
                         popen=mac.popen, pid=PID)


def hidden_leftovers(mac) -> list[str]:
    return sorted(p.name for p in mac.apps.iterdir() if p.name != update_macos.APP_NAME)


def assert_old_app_kept(mac):
    assert app_text(mac.running) == "old version"
    assert hidden_leftovers(mac) == []
    assert mac.popen.commands == []
    assert mac.attached == []
    assert list((mac.apps.parent / "tmp").iterdir()) == []  # the .dmg and mount point are gone


@pytest.fixture
def fake_open(tmp_path):
    log = tmp_path / "opened"
    tool = tmp_path / "fake-open"
    tool.write_text(f'#!/bin/sh\necho "$*" >> "{log}"\n')
    tool.chmod(0o755)
    return tool, log


def exited_pid() -> int:
    child = subprocess.Popen(["true"])
    child.wait()
    return child.pid


def run_helper(command: list[str], open_tool: Path, pid: int | None = None, wait: int | None = None):
    """Run the recorded helper command now, with a fake ``open`` and a process that has exited."""
    command = list(command)
    command[4] = str(exited_pid() if pid is None else pid)
    command[8] = str(open_tool)
    if wait is not None:
        command[9] = str(wait)
    return subprocess.run(command, capture_output=True, text=True, timeout=30)


# -- the whole update -----------------------------------------------------------

def test_update_verifies_swaps_and_relaunches(mac, fake_open):
    install(mac)
    assert mac.downloads == [DMG_URL]
    assert mac.attached == []  # detached again
    assert list((mac.apps.parent / "tmp").iterdir()) == []
    # Staged next to the old app, which is untouched until this process exits.
    assert app_text(mac.running) == "old version"
    staged = mac.apps / f".{update_macos.APP_NAME}.new.{PID}"
    assert app_text(staged) == "new version"
    [command] = mac.popen.commands
    assert command[:2] == ["/bin/sh", "-c"]
    assert command[4:8] == [str(PID), str(mac.running), str(staged), str(mac.apps / f".{update_macos.APP_NAME}.old.{PID}")]
    assert command[8] == "/usr/bin/open"

    tool, opened = fake_open
    result = run_helper(command, tool)
    assert result.returncode == 0, result.stdout + result.stderr
    assert app_text(mac.running) == "new version"
    assert hidden_leftovers(mac) == []
    assert opened.read_text().splitlines() == [str(mac.running)]


def test_checks_run_on_the_hidden_read_only_image_before_anything_is_copied(mac):
    install(mac)
    attach = mac.calls.index(next(c for c in mac.calls if c[:2] == [update_macos.HDIUTIL, "attach"]))
    ditto = mac.calls.index(next(c for c in mac.calls if c[0] == update_macos.DITTO))
    assert attach < ditto
    before_copy = mac.calls[attach:ditto]
    assert any(c[:2] == [update_macos.SPCTL, "--assess"] for c in before_copy)
    assert any(arg.startswith("--test-requirement=") for c in before_copy for arg in c)


@pytest.mark.parametrize(
    "knob, value, message",
    [
        ("new_signature", "broken", update_macos.T_BAD_SIGNATURE),
        ("new_signature", "adhoc", update_macos.T_OTHER_TEAM),
        ("new_team", "OTHERTEAM1", update_macos.T_OTHER_TEAM),
        ("gatekeeper", "rejected", update_macos.T_NOT_NOTARIZED),
        ("gatekeeper", "developer-id", update_macos.T_NOT_NOTARIZED),
        ("attach_fails", True, update_macos.T_ATTACH),
    ],
)
def test_failed_verification_refuses_and_keeps_the_old_app(mac, knob, value, message):
    setattr(mac, knob, value)
    with pytest.raises(UpdateError) as exc:
        install(mac)
    assert str(exc.value) == message
    assert_old_app_kept(mac)
    assert not any(c[0] == update_macos.DITTO for c in mac.calls)


def test_gatekeeper_switched_off_still_requires_the_signature(mac):
    mac.gatekeeper = "disabled"
    install(mac)
    assert len(mac.popen.commands) == 1
    assert not any(c[:2] == [update_macos.SPCTL, "--assess"] for c in mac.calls)


@pytest.mark.parametrize(
    "change",
    [
        lambda volume: shutil.rmtree(volume / update_macos.APP_NAME),
        lambda volume: (shutil.rmtree(volume / update_macos.APP_NAME),
                        make_app(volume / update_macos.APP_NAME, "older", version="1.3.0")),
        lambda volume: (shutil.rmtree(volume / update_macos.APP_NAME),
                        make_app(volume / update_macos.APP_NAME, "other", bundle_id="com.example.other")),
    ],
    ids=["no app", "other version", "other bundle"],
)
def test_image_without_this_release_is_refused(mac, change):
    change(mac.volume)
    with pytest.raises(UpdateError) as exc:
        install(mac)
    assert str(exc.value) in (update_macos.T_NO_APP, update_macos.T_WRONG_APP)
    assert_old_app_kept(mac)


def test_failed_copy_removes_the_half_copy_and_keeps_the_old_app(mac):
    mac.ditto_fails = True
    with pytest.raises(UpdateError) as exc:
        install(mac)
    assert str(exc.value) == update_macos.T_COPY
    assert_old_app_kept(mac)


def test_helper_that_cannot_start_leaves_nothing_behind(mac):
    def broken(cmd, **kwargs):
        raise OSError("no /bin/sh")
    mac.popen = broken
    with pytest.raises(UpdateError) as exc:
        install(mac)
    assert str(exc.value) == update_macos.T_HANDOFF
    assert app_text(mac.running) == "old version"
    assert hidden_leftovers(mac) == []


def test_no_update_while_a_sync_or_move_holds_the_run_lock(mac):
    with run_lock(mac.lock_file):
        with pytest.raises(UpdateError) as exc:
            install(mac)
    assert str(exc.value) == update_macos.T_BUSY
    assert mac.downloads == []
    assert_old_app_kept(mac)


def test_failed_download_changes_nothing(mac):
    with pytest.raises(UpdateError):
        update_macos.install(
            RELEASE, Target(mac.running, TEAM), mac.lock_file,
            get=lambda url, **kw: FakeResponse(404, url), run=mac, popen=mac.popen, pid=PID,
        )
    assert_old_app_kept(mac)
    assert mac.calls == []


# -- the swap helper ------------------------------------------------------------

def test_swap_failure_restores_the_old_app(mac, fake_open):
    install(mac)
    [command] = mac.popen.commands
    shutil.rmtree(command[6])  # the staged copy vanished: moving it into place fails
    tool, opened = fake_open
    result = run_helper(command, tool)
    assert result.returncode == 1
    assert "restoring the old one" in result.stdout
    assert app_text(mac.running) == "old version"
    assert hidden_leftovers(mac) == []
    assert opened.read_text().splitlines() == [str(mac.running)]  # the old app runs again


def test_helper_gives_up_when_the_app_does_not_quit(mac, fake_open):
    install(mac)
    [command] = mac.popen.commands
    tool, opened = fake_open
    result = run_helper(command, tool, pid=os.getpid(), wait=1)
    assert result.returncode == 1
    assert app_text(mac.running) == "old version"
    assert hidden_leftovers(mac) == []
    assert not opened.exists()


# -- when the app cannot replace itself -----------------------------------------

def test_running_from_source_has_no_bundle():
    with pytest.raises(ManualUpdate):
        update_macos.find_target(None)


def test_translocated_app_is_updated_by_hand(mac):
    translocated = Path("/private/var/folders/x/T/AppTranslocation/ABC/d") / update_macos.APP_NAME
    with pytest.raises(ManualUpdate) as exc:
        update_macos.find_target(translocated, run=mac, writable=lambda p: True)
    assert str(exc.value) == update_macos.T_TRANSLOCATED


def test_app_on_the_mounted_image_is_updated_by_hand(mac):
    mac.images = [mac.apps]
    with pytest.raises(ManualUpdate) as exc:
        update_macos.find_target(mac.running, run=mac)
    assert str(exc.value) == update_macos.T_FROM_IMAGE


@pytest.mark.parametrize("locked", ["folder", "app"])
def test_folder_this_user_cannot_write_is_updated_by_hand(mac, locked):
    readonly = mac.apps if locked == "folder" else mac.running
    with pytest.raises(ManualUpdate) as exc:
        update_macos.find_target(mac.running, run=mac, writable=lambda p: p != readonly)
    assert str(exc.value) == update_macos.T_NOT_WRITABLE


def test_unsigned_app_is_updated_by_hand(mac):
    mac.running_team = None
    with pytest.raises(ManualUpdate) as exc:
        update_macos.find_target(mac.running, run=mac)
    assert str(exc.value) == update_macos.T_UNSIGNED


def test_signed_app_in_a_writable_folder_updates_itself(mac):
    assert update_macos.find_target(mac.running, run=mac) == Target(mac.running, TEAM)


def test_trusts_the_same_team_and_bundle_as_install_sh():
    script = (ROOT / "install.sh").read_text()
    team = re.search(r'^TEAM_ID="([^"]+)"$', script, re.MULTILINE).group(1)
    bundle = re.search(r'^BUNDLE_ID="([^"]+)"$', script, re.MULTILINE).group(1)
    req = re.search(r'^REQUIREMENT="(.+)"$', script, re.MULTILINE).group(1)
    assert (team, bundle) == (update_macos.TEAM_ID, update_macos.BUNDLE_ID)
    expected = req.replace('\\"', '"').replace("$TEAM_ID", team).replace("$BUNDLE_ID", bundle)
    assert update_macos.requirement(team) == expected


# -- after the restart ----------------------------------------------------------

def test_restarted_app_reports_the_update_once():
    state = UpdateState(installing=VERSION)
    [note] = state.finish_install(current=VERSION)
    assert note.title == f"Blackboard Sync {VERSION} sürümüne güncellendi"
    assert state.finish_install(current=VERSION) == []


def test_restarted_old_app_says_the_update_did_not_take_effect():
    state = UpdateState(installing=VERSION)
    [note] = state.finish_install(current="1.4.0")
    assert note.title == "Güncelleme yüklenemedi"
    assert "1.4.0" in note.message


def test_installing_version_survives_the_restart(tmp_path):
    from datetime import datetime, timezone

    now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    state = UpdateState(installing=VERSION)
    loaded = UpdateState.load(state.saved_state(), now, current=VERSION)
    assert loaded.installing == VERSION
    assert UpdateState.load({}, now).installing == ""


def test_no_job_starts_while_an_update_downloads(tmp_path):
    from datetime import datetime, timezone

    model = AppModel(tmp_path, datetime(2026, 10, 8, tzinfo=timezone.utc))
    model.updates.available = RELEASE
    assert model.updates.begin("download")
    assert not model.begin("sync")
    assert not model.begin("move")
    model.updates.finish_download("")
    assert model.begin("sync")
