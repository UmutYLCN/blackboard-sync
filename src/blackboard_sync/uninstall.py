"""Uninstall local app data and, optionally, recorded course files.

Course files go through the OS Trash API. No recursive destination deletion:
only safe state paths and their empty parent folders are candidates.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath

from blackboard_sync import runtime, signout
from blackboard_sync.windows import package
from blackboard_sync.config import Config
from blackboard_sync.errors import AlreadyRunning, BlackboardSyncError
from blackboard_sync.relocate import migration_pending
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock
from blackboard_sync.system import try_lock

TITLE = "Uninstall Blackboard Sync?"
BUTTON_TITLE = "Uninstall app…"  # in the settings window, under Updates
CHECKBOX = "Also delete the downloaded course files"
MESSAGE = (
    "The app and all of its records, logs, settings and sign-in data are removed, "
    "and so is its start-at-login entry. Downloaded course files are kept unless "
    "you tick this option."
)
BUSY = "Wait for the sync or the folder move to finish before uninstalling."
STORE_REMOVAL = "You can uninstall Blackboard Sync from Windows Settings → Apps."


def trash(path: Path) -> None:
    if sys.platform == "win32":
        from blackboard_sync.windows.trash import recycle

        recycle(path)
        return
    from send2trash import send2trash

    send2trash(str(path))


def remove_startup() -> None:
    if sys.platform == "win32":
        from blackboard_sync.windows.autostart import set_enabled

        set_enabled(False)
    elif sys.platform == "darwin":
        from blackboard_sync.menubar.launchagent import remove

        remove()


def app_bundle(executable: Path | None = None) -> Path | None:
    """Find the running bundle, never guess an app in /Applications."""
    if executable is None and not runtime.is_frozen():
        return None
    executable = Path(executable or sys.executable).absolute()
    for parent in executable.parents:
        if parent.suffix == ".app" and (parent / "Contents" / "MacOS") in executable.parents:
            return parent
    return None


def remove_app() -> list[str]:
    if package.is_packaged():
        return [STORE_REMOVAL]
    if not runtime.is_frozen():
        # A source checkout has no installed app bundle/uninstaller.
        return []
    if sys.platform == "darwin":
        bundle = app_bundle()
        if bundle is not None:
            try:
                trash(bundle)
                return []
            except OSError:
                return [f"The app could not be moved to the Trash. Delete it in Finder yourself: {bundle}"]
    elif sys.platform == "win32":
        installer = Path(sys.executable).parent / "unins000.exe"
        if installer.is_file():
            try:
                # Inno stops the app, so start it only after all data cleanup.
                subprocess.Popen([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                                 stdin=subprocess.DEVNULL)
                return []
            except OSError:
                pass
        return ["The uninstaller could not be started. Uninstall Blackboard Sync from Windows "
                f"Settings → Apps; if needed, delete this folder yourself: {installer.parent}"]
    return ["Remove the app's files yourself."]


def _recorded_path(root: Path, value) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        return None
    rel = PurePosixPath(value)
    if rel.is_absolute() or PureWindowsPath(value).drive or any(p in (".", "..") for p in value.split("/")):
        return None
    path = root.joinpath(*rel.parts)
    # Refuse symlinks/junctions at any level below the University folder.
    # resolve() also catches Windows reparse points and paths escaping it.
    resolved = root.resolve()
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink() or candidate.resolve() != resolved / candidate.relative_to(root):
            return None
    return path


def trash_course_files(config: Config, send_to_trash=trash) -> list[str]:
    state = State.load(config.state_file, backup=False)
    warnings = []
    if state.recovery:
        return ["The download records could not be read; the course files were kept to be safe."]
    folders: set[Path] = set()
    paths = {entry.get("path") for entry in state.outputs.values() if isinstance(entry, dict)
             and isinstance(entry.get("path"), str)}
    # The files are in the University folder; until an older version's files were
    # moved in (``relocate.migrate_to_root``) they are still directly in the chosen folder.
    roots = [config.root, *([config.dest] if migration_pending(state, config.dest) else [])]
    for root in roots:
        for rel in sorted(paths):
            path = _recorded_path(root, rel)
            if path is None:
                continue
            # The state records files, never permission to remove a directory tree.
            if path.exists() and not path.is_file():
                continue
            parent = path.parent
            while parent != root:
                folders.add(parent)
                parent = parent.parent
            if path.is_file():
                try:
                    send_to_trash(path)
                except OSError as exc:
                    warnings.append(f"Could not move a file to the Trash: {path} ({exc})")
    if config.root != config.dest:
        folders.add(config.root)  # created by the app; removed only once empty
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                send_to_trash(folder)
        except OSError as exc:
            warnings.append(f"Could not move an empty folder to the Trash: {folder} ({exc})")
    return warnings


@contextmanager
def _app_lock(config: Config, owned: bool):
    """CLI requires the GUI to be closed so it cannot recreate cleaned records."""
    if owned:
        yield
        return
    handle = open(config.data_dir / "menubar.lock", "a+")
    try:
        if not try_lock(handle):
            raise AlreadyRunning("Quit Blackboard Sync first, or use Uninstall app… in its settings.")
        yield
    finally:
        handle.close()


def uninstall(config: Config, delete_course_files: bool = False, *,
              send_to_trash=trash, clear_web=None, startup_cleanup=remove_startup,
              app_cleanup=remove_app, before_cleanup=None, owns_app_lock=False) -> list[str]:
    """Finish cleanup even if one step fails; return actionable warnings.

    Hooks make platform operations testable without touching real user folders.
    GUI callers stop timers and close their lifetime/log handles in before_cleanup,
    which runs only after the shared sync/move lock was acquired.
    """
    if package.is_packaged():
        return [STORE_REMOVAL]
    data = config.data_dir.resolve()
    dest = config.dest.resolve()
    if data == data.parent or data == Path.home().resolve() or data == dest or data in dest.parents:
        raise BlackboardSyncError("The app data folder contains the download folder or the home folder; uninstall cancelled.")
    for name in ("sync.lock", "menubar.lock"):
        if (config.data_dir / name).is_symlink():
            raise BlackboardSyncError("A lock file is a link; the app could not be removed safely.")
    warnings: list[str] = []
    try:
        with run_lock(config.lock_file):
            with _app_lock(config, owns_app_lock):
                if before_cleanup:
                    before_cleanup()
                if delete_course_files:
                    try:
                        warnings.extend(trash_course_files(config, send_to_trash))
                    except OSError as exc:
                        warnings.append(f"Could not move the course files to the Trash: {exc}")
                try:
                    warnings.extend(signout.sign_out(config, clear_web=clear_web))
                except OSError as exc:
                    warnings.append(f"Could not clear the sign-in data: {exc}")
                try:
                    startup_cleanup()
                except OSError as exc:
                    warnings.append(f"Could not remove the start-at-login entry: {exc}")
                # Open lock files cannot be unlinked on Windows. Remove them only
                # after both handles close; everything else is removed under lock.
                try:
                    for path in config.data_dir.iterdir():
                        if path.name not in ("sync.lock", "menubar.lock"):
                            if not signout._remove_tree(path):
                                warnings.append(f"Uygulama verisi silinemedi: {path}")
                except OSError as exc:
                    warnings.append(f"Could not clear the app data folder: {config.data_dir} ({exc})")
    except AlreadyRunning as exc:
        if "Another blackboard-sync" in str(exc):
            raise AlreadyRunning(BUSY) from exc
        raise
    for name in ("sync.lock", "menubar.lock"):
        try:
            (config.data_dir / name).unlink(missing_ok=True)
        except OSError as exc:
            warnings.append(f"Could not delete a lock file: {name} ({exc})")
    try:
        warnings.extend(app_cleanup())
    except OSError as exc:
        warnings.append(f"The app could not be removed; delete it yourself: {exc}")
    return list(dict.fromkeys(warnings))


def close_file_logs() -> None:
    """Release Windows file handles and prevent handlers reopening deleted logs."""
    loggers = [logging.getLogger(), *(logger for logger in logging.Logger.manager.loggerDict.values()
                                     if isinstance(logger, logging.Logger))]
    for logger in loggers:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()
