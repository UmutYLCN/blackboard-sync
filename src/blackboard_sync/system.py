"""The few places where macOS and Windows differ: default folders, private
permissions and the single-run lock.

Everything here takes the platform as an optional argument so the Windows
logic can be tested on any machine. Nothing in this module (or in the core and
CLI) imports a macOS-only package.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path, PurePath
from typing import IO, Callable, Mapping, TypeVar

log = logging.getLogger(__name__)

APP_NAME = "blackboard-sync"
DEST_FOLDER = "University"
# subprocess.CREATE_NO_WINDOW exists only on Windows; keeps helper tools from
# flashing a console window when the caller has none (the tray app).
CREATE_NO_WINDOW = 0x08000000
# Well-known SID of the operating system account (LocalSystem).
SYSTEM_SID = "S-1-5-18"

P = TypeVar("P", bound=PurePath)


def is_windows(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "win32"


def default_data_dir(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """The private folder for the session and sync state.

    macOS (and anything that is not Windows): ``~/Library/Application Support/
    blackboard-sync``, unchanged so existing sessions and state are found.
    Windows: ``%APPDATA%\\blackboard-sync``.
    """
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if is_windows(platform):
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / APP_NAME
    return home / "Library" / "Application Support" / APP_NAME


def default_dest(
    platform: str | None = None,
    home: Path | None = None,
    documents: Callable[[], Path | None] | None = None,
) -> Path:
    """The course folder: ``University`` inside the user's Documents folder.

    On Windows the Documents folder can be moved (for example into OneDrive),
    so it is asked from the system instead of assumed to be ``~\\Documents``.
    """
    home = Path.home() if home is None else home
    if is_windows(platform):
        found = (documents or windows_documents_dir)()
        return (found or home / "Documents") / DEST_FOLDER
    return home / "Documents" / DEST_FOLDER


def sync_root(dest: P) -> P:
    """Where the term folders go: the ``University`` folder inside the chosen folder.

    A chosen folder that is already called University (in any case, like the
    default ``~/Documents/University``) is used as it is, never
    ``University/University``. The folder is created by the first download.
    """
    return dest if dest.name.casefold() == DEST_FOLDER.casefold() else dest / DEST_FOLDER


def windows_documents_dir() -> Path | None:
    """The current user's Documents folder (FOLDERID_Documents), or None."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_id = GUID(
            0xFDD39AD0, 0x238F, 0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)
        ]
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        raw = ctypes.c_void_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(raw)) != 0:
            return None
        try:
            return Path(ctypes.wstring_at(raw.value))
        finally:
            ole32.CoTaskMemFree(raw)
    except Exception:  # not Windows, or the call is unavailable
        return None


FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_NORMAL = 0x80


def set_hidden(path: Path, hidden: bool, platform: str | None = None) -> None:
    """Set or clear the Windows hidden attribute; best effort and a no-op elsewhere.

    Dot-files are only hidden on macOS, so temp files get the attribute on Windows.
    """
    if not is_windows(platform):
        return
    try:
        import ctypes

        attrs = FILE_ATTRIBUTE_HIDDEN if hidden else FILE_ATTRIBUTE_NORMAL
        ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)
    except Exception:  # hiding is cosmetic, never fail a download over it
        log.debug("Could not change the hidden attribute of %s", path)


def make_private_dir(
    path: Path,
    platform: str | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Create ``path`` (and parents) readable only by the current user.

    macOS: mode ``700``, re-applied every time.
    Windows has no mode bits; instead the folder's inherited permissions are
    replaced by full control for the current user (and the operating system
    account), which everything created inside inherits. That is done once, when
    the folder is first created, and is best effort: if it fails the folder
    keeps Windows' defaults, which under ``%APPDATA%`` already exclude other
    standard users.
    """
    if not is_windows(platform):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        return path
    if path.is_dir():
        return path
    path.mkdir(parents=True, exist_ok=True)
    command = windows_private_acl_command(path, env)
    if command is None:
        log.debug("Not restricting %s: current user unknown", path)
        return path
    try:
        result = run(command, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    except (OSError, ValueError) as exc:  # ValueError: creationflags off Windows
        log.debug("Could not restrict %s: %s", path, exc)
        return path
    if result.returncode != 0:
        log.debug("Could not restrict %s: %s", path, (result.stdout or result.stderr).strip())
    return path


def windows_private_acl_command(path: Path, env: Mapping[str, str] | None = None) -> list[str] | None:
    """The ``icacls`` call that makes a folder private to the current user."""
    env = os.environ if env is None else env
    user = env.get("USERNAME")
    if not user:
        return None
    domain = env.get("USERDOMAIN")
    account = f"{domain}\\{user}" if domain else user
    icacls = Path(env.get("SystemRoot") or env.get("SYSTEMROOT") or r"C:\Windows") / "System32" / "icacls.exe"
    return [
        str(icacls),
        str(path),
        "/inheritance:r",
        "/grant:r",
        f"{account}:(OI)(CI)F",
        f"*{SYSTEM_SID}:(OI)(CI)F",
        "/q",
    ]


def set_private_file_mode(fd: int, platform: str | None = None) -> None:
    """Make an open file owner-only (``600``) on macOS.

    On Windows a file gets its permissions from the folder it is created in
    (see ``make_private_dir``); there is no per-file mode to set.
    """
    if not is_windows(platform):
        os.fchmod(fd, 0o600)


def try_lock(fh: IO) -> bool:
    """Take an exclusive, non-blocking lock on an open file; False if held elsewhere.

    The lock is released when the file is closed (or the process exits).
    """
    if is_windows():
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True
