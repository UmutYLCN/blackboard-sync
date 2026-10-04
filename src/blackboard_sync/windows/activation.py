"""Per-user toast activation, forwarded to the single running tray instance."""

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


def request_update(config) -> None:
    # The data directory is already private. Repeated clicks coalesce; no paths
    # or commands from the URI are executed or stored.
    (config.data_dir / "update-request").touch()


def take_update_request(config) -> bool:
    try:
        (config.data_dir / "update-request").unlink()
        return True
    except FileNotFoundError:
        return False
