"""Platform defaults, private folders and the run lock (Windows logic injected)."""

import subprocess
import sys
from pathlib import Path

import pytest

from blackboard_sync import system
from blackboard_sync.config import Config

HOME = Path("/home/student")


def test_macos_paths_are_unchanged():
    assert system.default_data_dir("darwin", env={}, home=HOME) == (
        HOME / "Library" / "Application Support" / "blackboard-sync"
    )
    assert system.default_dest("darwin", home=HOME) == HOME / "Documents" / "Okul"


def test_windows_data_dir_lives_in_appdata():
    appdata = str(Path("C:/Users/student/AppData/Roaming"))
    assert system.default_data_dir("win32", env={"APPDATA": appdata}, home=HOME) == (
        Path(appdata) / "blackboard-sync"
    )
    assert system.default_data_dir("win32", env={}, home=HOME) == (
        HOME / "AppData" / "Roaming" / "blackboard-sync"
    )


def test_windows_dest_follows_a_moved_documents_folder():
    onedrive = Path("C:/Users/student/OneDrive/Documents")
    assert system.default_dest("win32", home=HOME, documents=lambda: onedrive) == onedrive / "Okul"
    assert system.default_dest("win32", home=HOME, documents=lambda: None) == HOME / "Documents" / "Okul"


def test_windows_private_dir_replaces_inherited_permissions(tmp_path):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")

    env = {"USERNAME": "öğrenci", "USERDOMAIN": "LAPTOP", "SystemRoot": "C:\\Windows"}
    target = tmp_path / "data"
    system.make_private_dir(target, platform="win32", run=run, env=env)
    assert target.is_dir()
    argv, kwargs = calls[0]
    assert argv[0].endswith("icacls.exe") and argv[1] == str(target)
    assert argv[2:] == [
        "/inheritance:r", "/grant:r", "LAPTOP\\öğrenci:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/q",
    ]
    assert kwargs["creationflags"] == system.CREATE_NO_WINDOW
    # Done once, when the folder is created.
    system.make_private_dir(target, platform="win32", run=run, env=env)
    assert len(calls) == 1


def test_windows_private_dir_is_best_effort(tmp_path):
    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 5, "Access is denied.", "")

    def missing(argv, **kwargs):
        raise OSError("icacls not found")

    env = {"USERNAME": "student"}
    assert system.make_private_dir(tmp_path / "a", platform="win32", run=failing, env=env).is_dir()
    assert system.make_private_dir(tmp_path / "b", platform="win32", run=missing, env=env).is_dir()
    assert system.make_private_dir(tmp_path / "c", platform="win32", env={}).is_dir()  # user unknown


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows ACLs")
def test_data_dir_acl_on_real_windows(tmp_path):
    config = Config(data_dir=tmp_path / "data")
    config.ensure_data_dir()
    acl = subprocess.run(["icacls", str(config.data_dir)], capture_output=True, text=True).stdout
    assert "(I)" not in acl  # nothing inherited from the parent folder any more
    assert "(OI)(CI)" in acl


def test_run_lock_is_exclusive(tmp_path):
    lock = tmp_path / "x.lock"
    first = open(lock, "w")
    second = open(lock, "w")
    try:
        assert system.try_lock(first)
        assert not system.try_lock(second)
    finally:
        first.close()
    try:
        assert system.try_lock(second)
    finally:
        second.close()
