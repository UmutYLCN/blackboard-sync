"""Per-user Windows login item; no administrator privileges required.

The installer build writes a value under HKCU\\...\\Run. The MSIX (Store) build
cannot: its login item is the ``desktop`` startup task declared in
``packaging/msix/AppxManifest.xml.in`` (TaskId ``TASK_ID``), which the user also
controls in Task Manager and Settings > Apps > Startup. Windows starts the task
without arguments, so instead of ``--background`` the packaged app asks Windows
how it was started (``started_at_login``).
"""

import logging
import subprocess
import sys
from pathlib import Path

from blackboard_sync import runtime

from . import package

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "BlackboardSync"
# Started at login the app stays in the tray; started by the user it shows
# its window (see app.main).
BACKGROUND = "--background"
# The startup task in packaging/msix/AppxManifest.xml.in.
TASK_ID = "BlackboardSyncStartup"


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
    if package.is_packaged():
        return package.startup_task_state(TASK_ID) in package.ENABLED_STATES
    return _value() in (command(), command(background=False))


def upgrade_legacy() -> None:
    """Add --background to a login item written before 1.1.0."""
    if package.is_packaged():
        return  # the startup task has no command line
    if _value() == command(background=False):
        set_enabled(True)


def started_at_login() -> bool:
    """The packaged app was started by its startup task. Call once, early.

    The installer build learns this from ``--background`` instead.
    """
    if not package.is_packaged():
        return False
    try:
        return package.activation_kind() == package.STARTUP_TASK_ACTIVATION
    except OSError:
        log.exception("Could not read how the app was started")
        return False


def set_enabled(enabled: bool) -> None:
    if package.is_packaged():
        state = package.set_startup_task(TASK_ID, enabled)
        if (state in package.ENABLED_STATES) != enabled:
            # Turned off by the user in Task Manager / Settings, or set by policy:
            # only they can change it. is_installed() shows the real state.
            log.warning("Start at login stays %s (startup task state %d)", "off" if enabled else "on", state)
        return

    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def check_package() -> str:
    """CI's ``--check-package`` on the installed MSIX: identity and the startup task.

    Turns start-at-login on and off again when it was off, leaving it as it was.
    """
    from blackboard_sync import updater
    from . import notifications

    name = package.full_name()
    if name is None:
        raise RuntimeError("the process has no package identity")
    if updater.enabled() or updater.check().status != "store":
        raise RuntimeError("the packaged self-updater is enabled")
    identity = notifications.check_identity()
    if identity != package.app_user_model_id():
        raise RuntimeError("the toast identity is not the packaged app's AUMID")
    before = package.startup_task_state(TASK_ID)
    if before == package.DISABLED:
        set_enabled(True)
        if not is_installed():
            raise RuntimeError("enabling the startup task did not take")
        set_enabled(False)
        if is_installed():
            raise RuntimeError("disabling the startup task did not take")
    return f"package ok ({name}, startup task state {before}, updater off, toast identity {identity})"
