"""The per-user LaunchAgent behind "Start when the computer starts".

Direct macOS builds write a plist to ``~/Library/LaunchAgents``; macOS starts the
app from it at the next login, with ``--background`` so it stays in the menu bar
without opening its window.

Mac App Store (``mas``) builds run under App Sandbox and cannot touch
``~/Library/LaunchAgents``; they use ``SMAppService.mainApp`` (macOS 13+) instead.
"""

from __future__ import annotations

import functools
import logging
import os
import plistlib
from pathlib import Path
from typing import Callable, Mapping

from blackboard_sync import licensing, runtime

log = logging.getLogger(__name__)

LABEL = "io.github.umutylcn.blackboard-sync.menubar"
DEFAULT_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
# Settings the app should keep when started by launchd instead of a shell.
PASSED_ENV = ("BBSYNC_BASE_URL", "BBSYNC_DEST", "BBSYNC_DATA_DIR", "BBSYNC_ANNOUNCEMENTS_FOLDER")
# The start at login is quiet: the menu bar icon only, no main window.
BACKGROUND = "--background"

# SMAppServiceStatus values (ServiceManagement.framework, macOS 13+).
SM_NOT_REGISTERED = 0
SM_ENABLED = 1
SM_REQUIRES_APPROVAL = 2
SM_NOT_FOUND = 3

# AppleEvent constants sent by LoginWindow / SMAppService when launching a login item.
_AE_OPEN_APP = 0x6F617070  # 'oapp'
_AE_PROP_DATA = 0x70726474  # 'prdt'
_AE_LAUNCHED_AS_LOGIN_ITEM = 0x6C676974  # 'lgit'


@functools.cache
def _sm_app_service_class():
    import objc

    for selector in (b"registerAndReturnError:", b"unregisterAndReturnError:"):
        objc.registerMetaDataForSelector(
            b"SMAppService",
            selector,
            {"retval": {"type": objc._C_NSBOOL}, "arguments": {2: {"type_modifier": objc._C_OUT}}},
        )
    namespace: dict[str, object] = {}
    objc.loadBundle(
        "ServiceManagement",
        namespace,
        bundle_path="/System/Library/Frameworks/ServiceManagement.framework",
    )
    return namespace["SMAppService"]


def _default_main_app_service():
    return _sm_app_service_class().mainAppService()


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


def is_installed(
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    *,
    env: Mapping[str, str] | None = None,
    service_factory: Callable[[], object] | None = None,
) -> bool:
    if licensing.is_mas(env=env):
        try:
            service = (service_factory or _default_main_app_service)()
            return int(service.status()) == SM_ENABLED
        except Exception as exc:
            log.debug("Could not query SMAppService status: %s", exc)
            return False
    return plist_path(agents_dir).is_file()


def install(
    log_file: Path,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    python: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    service_factory: Callable[[], object] | None = None,
) -> Path:
    if licensing.is_mas(env=env):
        try:
            service = (service_factory or _default_main_app_service)()
            if int(service.status()) == SM_ENABLED:
                return Path("SMAppService.mainApp")
            ok, error = service.registerAndReturnError_(None)
        except Exception as exc:
            raise OSError(f"SMAppService register failed: {exc}") from exc
        if not ok:
            raise OSError(str(error) if error is not None else "SMAppService register refused")
        return Path("SMAppService.mainApp")
    path = plist_path(agents_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plistlib.dumps(build_plist([*runtime.menubar_command(python), BACKGROUND], log_file))
    try:
        if path.read_bytes() == data:
            return path
    except FileNotFoundError:
        pass
    tmp = path.with_suffix(".plist.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def remove(
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    *,
    env: Mapping[str, str] | None = None,
    service_factory: Callable[[], object] | None = None,
) -> bool:
    if licensing.is_mas(env=env):
        try:
            service = (service_factory or _default_main_app_service)()
            status = int(service.status())
            if status not in (SM_ENABLED, SM_REQUIRES_APPROVAL):
                return False
            ok, error = service.unregisterAndReturnError_(None)
        except Exception as exc:
            raise OSError(f"SMAppService unregister failed: {exc}") from exc
        if not ok and int(service.status()) == SM_ENABLED:
            raise OSError(str(error) if error is not None else "SMAppService unregister refused")
        return True
    try:
        plist_path(agents_dir).unlink()
    except FileNotFoundError:
        return False
    return True


def refresh_if_installed(
    log_file: Path,
    agents_dir: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    """Refresh legacy LaunchAgent plists in direct builds; no-op for SMAppService in MAS builds."""
    if licensing.is_mas(env=env):
        return
    if agents_dir is None and env is None:
        if is_installed():
            install(log_file)
        return
    target_dir = DEFAULT_AGENTS_DIR if agents_dir is None else agents_dir
    installed = is_installed(target_dir) if env is None else is_installed(target_dir, env=env)
    if installed:
        if env is None:
            install(log_file, target_dir)
        else:
            install(log_file, target_dir, env=env)


def launched_as_login_item(*, env: Mapping[str, str] | None = None) -> bool:
    """True when macOS started the MAS app at login via ``SMAppService.mainApp``."""
    if not licensing.is_mas(env=env):
        return False
    try:
        from Foundation import NSAppleEventManager

        event = NSAppleEventManager.sharedAppleEventManager().currentAppleEvent()
        if event is None or int(event.eventID()) != _AE_OPEN_APP:
            return False
        prop = event.paramDescriptorForKeyword_(_AE_PROP_DATA)
        return prop is not None and int(prop.enumCodeValue()) == _AE_LAUNCHED_AS_LOGIN_ITEM
    except Exception:
        return False
