"""Per-user Windows login item; no administrator privileges required."""

import subprocess
import sys
from pathlib import Path

from blackboard_sync import runtime

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BlackboardSync"


def command(python: str | None = None) -> str:
    if python is None and runtime.is_frozen():
        # The installed app starts itself; there is no Python to invoke.
        return subprocess.list2cmdline([sys.executable])
    executable = Path(python or sys.executable)
    if python is None and executable.name.lower() == "python.exe":
        executable = executable.with_name("pythonw.exe")
    return subprocess.list2cmdline([str(executable), "-m", "blackboard_sync.windows"])


def is_installed() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return kind == winreg.REG_SZ and value == command()
    except FileNotFoundError:
        return False


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
