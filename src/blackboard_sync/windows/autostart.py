"""Per-user Windows login item; no administrator privileges required."""

import subprocess
import sys
from pathlib import Path

from blackboard_sync import runtime

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BlackboardSync"
# Started at login the app stays in the tray; started by the user it shows
# its window (see app.main).
BACKGROUND = "--background"


def command(python: str | None = None, background: bool = True) -> str:
    extra = [BACKGROUND] if background else []
    if python is None and runtime.is_frozen():
        # The installed app starts itself; there is no Python to invoke.
        return subprocess.list2cmdline([sys.executable, *extra])
    executable = Path(python or sys.executable)
    if python is None and executable.name.lower() == "python.exe":
        executable = executable.with_name("pythonw.exe")
    return subprocess.list2cmdline([str(executable), "-m", "blackboard_sync.windows", *extra])


def _value() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return None
    return value if kind == winreg.REG_SZ else None


def is_installed() -> bool:
    return _value() in (command(), command(background=False))


def upgrade_legacy() -> None:
    """Add --background to a login item written before 1.1.0."""
    if _value() == command(background=False):
        set_enabled(True)


def set_enabled(enabled: bool) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
