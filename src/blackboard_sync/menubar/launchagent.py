"""The per-user LaunchAgent behind "Bilgisayar açılınca başlat".

Installing only writes a plist to ``~/Library/LaunchAgents``; macOS starts the
app from it at the next login. Nothing is loaded into launchd right away (the
app is already running), and no root rights are needed.
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

from blackboard_sync import runtime

LABEL = "io.github.umutylcn.blackboard-sync.menubar"
DEFAULT_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
# Settings the app should keep when started by launchd instead of a shell.
PASSED_ENV = ("BBSYNC_BASE_URL", "BBSYNC_DEST", "BBSYNC_DATA_DIR", "BBSYNC_ANNOUNCEMENTS_FOLDER")


def plist_path(agents_dir: Path = DEFAULT_AGENTS_DIR) -> Path:
    return agents_dir / f"{LABEL}.plist"


def build_plist(program: list[str], log_file: Path, env: dict[str, str] | None = None) -> dict:
    env = os.environ if env is None else env
    plist = {
        "Label": LABEL,
        # Lets macOS attribute the background item to the app's name and icon.
        "AssociatedBundleIdentifiers": ["io.github.umutylcn.blackboard-sync"],
        "ProgramArguments": program,
        "RunAtLoad": True,
        # Restart after a crash, but not after the student chose "Çıkış".
        "KeepAlive": {"SuccessfulExit": False},
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }
    passed = {key: env[key] for key in PASSED_ENV if env.get(key)}
    if passed:
        plist["EnvironmentVariables"] = passed
    return plist


def is_installed(agents_dir: Path = DEFAULT_AGENTS_DIR) -> bool:
    return plist_path(agents_dir).is_file()


def install(log_file: Path, agents_dir: Path = DEFAULT_AGENTS_DIR, python: str | None = None) -> Path:
    path = plist_path(agents_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plistlib.dumps(build_plist(runtime.menubar_command(python), log_file))
    try:
        if path.read_bytes() == data:
            return path
    except FileNotFoundError:
        pass
    tmp = path.with_suffix(".plist.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def remove(agents_dir: Path = DEFAULT_AGENTS_DIR) -> bool:
    try:
        plist_path(agents_dir).unlink()
    except FileNotFoundError:
        return False
    return True
