"""Per-user toast activation, forwarded to the single running tray instance."""

import os
from pathlib import Path
import subprocess
import sys

from blackboard_sync import runtime

UPDATE_URI = "blackboard-sync://update"
PROTOCOL_KEY = r"Software\Classes\blackboard-sync"


def protocol_command() -> str:
    executable = Path(sys.executable)
    if runtime.is_frozen():
        args = [str(executable)]
    else:
        if executable.name.lower() == "python.exe":
            executable = executable.with_name("pythonw.exe")
        args = [str(executable), "-m", "blackboard_sync.windows"]
    return subprocess.list2cmdline([*args, "--notification"]) + ' "%1"'


def register() -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Blackboard Sync")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PROTOCOL_KEY + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, protocol_command())


UPDATE_REQUEST = "update-request"
WINDOW_REQUEST = "window-request"
ASFW_ANY = -1


def request_update(config) -> None:
    # The data directory is already private. Repeated clicks coalesce; no paths
    # or commands from the URI are executed or stored.
    (config.data_dir / UPDATE_REQUEST).touch()


def take_update_request(config) -> bool:
    return _take(config, UPDATE_REQUEST)


def request_window(config) -> None:
    """Ask the running copy to show its main window (the app was started again)."""
    try:
        import ctypes

        # Only the process the user just started may bring a window to the
        # front; pass that right on to the running copy.
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    except (ImportError, AttributeError, OSError):
        pass
    (config.data_dir / WINDOW_REQUEST).touch()


def take_window_request(config) -> bool:
    return _take(config, WINDOW_REQUEST)


def _take(config, name) -> bool:
    try:
        (config.data_dir / name).unlink()
        return True
    except FileNotFoundError:
        return False


def take_requests(config) -> tuple[bool, bool]:
    """(update, window) requests found, consumed. One directory scan when idle."""
    names = {UPDATE_REQUEST, WINDOW_REQUEST}
    with os.scandir(config.data_dir) as entries:
        found = {entry.name for entry in entries} & names
    return (UPDATE_REQUEST in found and _take(config, UPDATE_REQUEST),
            WINDOW_REQUEST in found and _take(config, WINDOW_REQUEST))
