"""Moving the mirrored files when the student picks another destination folder.

The settings window asks what to do with the files already downloaded; "Taşı"
lands here. Every file the sync recorded in ``state.json`` (attachments,
embedded files, notes) is moved from the old folder to the same relative path
in the new one. Recorded paths are relative to the destination, so the state
stays valid as it is and nothing is downloaded again.

On Windows deep folder names are shortened to fit the path limit, and how much
depends on the length of the destination path (``fit_windows_folder``). The
folders below each course are therefore named again for the new destination,
from the full names the state recorded, exactly as a sync there would name
them; long file names are shortened if needed, and the recorded paths follow.

Nothing is ever overwritten or lost:

* a file already at the target with other content is a conflict: both stay
  where they are and the file is reported;
* a file that cannot be moved (open in another program on Windows, no
  permission) stays in the old folder and is reported;
* between drives a file is copied first and the original removed only once the
  copy is in place; if the original cannot be removed the copy is dropped again;
* the student's own files in the old folder are never touched, and old folders
  are only removed once they are empty and every file moved (empty course
  folders are recreated in the new folder).

A file left behind is treated as deleted in the new folder until it is moved by
hand or brought back with "Silinenleri tekrar indir".
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from blackboard_sync.api import PARTIAL_PREFIX, PARTIAL_SUFFIX
from blackboard_sync.errors import AlreadyRunning
from blackboard_sync.paths import fit_windows_folder, fit_windows_path, join_rel
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock, sha256_file
from blackboard_sync.system import is_windows, set_hidden

log = logging.getLogger(__name__)

# Files the operating system leaves in folders the student opened; a folder with
# only these in it counts as empty.
SYSTEM_JUNK = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
# Windows reports a move between drives as ERROR_NOT_SAME_DEVICE.
_WINDOWS_NOT_SAME_DEVICE = 17

# "<term>/<course>": these folder names do not depend on the destination.
COURSE_DEPTH = 2

CONFLICT = "exists"  # the new folder already has a different file of that name
FAILED = "error"  # moving raised an error (locked, no permission, ...)


@dataclass
class MoveResult:
    status: str = "ok"  # "ok" | "locked" | "error"
    moved: int = 0
    # (path relative to the destination, CONFLICT or FAILED) of every file left in the old folder.
    kept: list[tuple[str, str]] = field(default_factory=list)
    old_removed: bool = False  # the old folder was empty afterwards and is gone
    message: str = ""


def synced_files(state: State, dest: Path) -> list[str]:
    """Recorded files (relative paths) that are present under ``dest``."""
    paths = sorted({entry["path"] for entry in state.outputs.values()})
    return [rel for rel in paths if (dest / rel).is_file()]


def count_synced_files(state_file: Path, dest: Path) -> int:
    """How many mirrored files ``dest`` holds; 0 also when the state cannot be read."""
    try:
        state = State.load(state_file, backup=False)
        return len(synced_files(state, dest))
    except OSError as exc:
        log.warning("Could not look for synced files in %s: %s", dest, exc)
        return 0


def move_destination(state_file: Path, lock_file: Path, old: Path, new: Path) -> MoveResult:
    """Move the mirrored files from ``old`` to ``new`` while holding the run lock.

    The lock keeps a sync started from the terminal from writing into either
    folder meanwhile; ``status`` is "locked" when one is running.
    """
    try:
        with run_lock(lock_file):
            state = State.load(state_file, backup=False)
            result = move_files(state, old, new)
            state.save()  # only writes when Windows paths were renamed
            return result
    except AlreadyRunning:
        return MoveResult(status="locked")
    except OSError as exc:
        log.warning("Could not move the files from %s to %s: %s", old, new, exc)
        return MoveResult(status="error", message=exc.strerror or str(exc))


def move_files(state: State, old: Path, new: Path, windows: bool | None = None) -> MoveResult:
    result = MoveResult()
    if _same_folder(old, new):
        return result
    place = Placement(state, new, is_windows() if windows is None else windows)
    present = synced_files(state, old)
    for rel in present:
        src, dst = old / rel, new / place.file(rel)
        try:
            if dst.exists() or dst.is_symlink():
                if dst.exists() and src.samefile(dst):  # reached through a link: already there
                    continue
                if not (dst.is_file() and sha256_file(src) == sha256_file(dst)):
                    log.warning("Kept %s: %s already holds a different file", src, dst)
                    result.kept.append((rel, CONFLICT))
                    continue
                src.unlink()  # the very same file is already in the new folder
            else:
                _move_file(src, dst)
        except OSError as exc:
            log.warning("Kept %s: could not move it to %s (%s)", src, dst, exc)
            result.kept.append((rel, FAILED))
            continue
        result.moved += 1
    if not result.kept:
        result.old_removed = _move_empty_folders(present, old, new, place)
    place.record()
    log.info("Moved %d file(s) from %s to %s; %d kept", result.moved, old, new, len(result.kept))
    return result


class Placement:
    """Where a recorded path goes in the new destination (the same path, except on Windows)."""

    def __init__(self, state: State, new: Path, windows: bool):
        self.state, self.new, self.windows = state, new, windows
        self._folders: dict[str, str] = {}

    def folder(self, rel_dir: str) -> str:
        if not self.windows or rel_dir in ("", "."):
            return "" if rel_dir == "." else rel_dir
        if rel_dir not in self._folders:
            parent = str(PurePosixPath(rel_dir).parent)
            if len(PurePosixPath(rel_dir).parts) <= COURSE_DEPTH:
                fitted = rel_dir
            else:
                new_parent = self.folder(parent)
                fitted = join_rel(new_parent, fit_windows_folder(self.new, new_parent, self.state.folder_name(rel_dir)))
            self._folders[rel_dir] = fitted
        return self._folders[rel_dir]

    def file(self, rel: str) -> str:
        if not self.windows:
            return rel
        path = PurePosixPath(rel)
        return fit_windows_path(self.new, join_rel(self.folder(str(path.parent)), path.name))

    def record(self) -> None:
        """Point the state at the new names: every recorded file, moved or not, and every folder."""
        if not self.windows:
            return
        for path in sorted({entry["path"] for entry in self.state.outputs.values()}):
            target = self.file(path)
            if target != path:
                self.state.move_file(path, target)
        folders = {self.folder(rel): name for rel, name in self.state.folders.items()}
        folders = {rel: name for rel, name in folders.items() if PurePosixPath(rel).name != name}
        if folders != self.state.folders:
            self.state.folders = folders
            self.state.dirty = True


def _same_folder(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))
    except OSError:
        return False


def _move_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)  # Windows refuses an existing target; it was checked just before
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != _WINDOWS_NOT_SAME_DEVICE:
            raise
        _copy_then_remove(src, dst)


def _copy_then_remove(src: Path, dst: Path) -> None:
    """Move between drives: copy beside the target, put it in place, then drop the original."""
    fd, name = tempfile.mkstemp(prefix=PARTIAL_PREFIX, suffix=PARTIAL_SUFFIX, dir=dst.parent)
    tmp = Path(name)
    try:
        # Written through the open handle: Windows refuses to open a hidden file for
        # writing again, which ``shutil.copy2`` would do.
        set_hidden(tmp, True)
        with os.fdopen(fd, "wb") as out, open(src, "rb") as data:
            shutil.copyfileobj(data, out, 1 << 20)
        shutil.copystat(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            raise OSError(errno.EIO, "the copy is incomplete", str(dst))
        if dst.exists():
            raise FileExistsError(errno.EEXIST, "the target appeared meanwhile", str(dst))
        set_hidden(tmp, False)  # the attribute would otherwise follow the file to its final name
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    try:
        src.unlink()
    except OSError:
        dst.unlink()  # our own copy: the original stays the only one
        raise


def _move_empty_folders(rel_paths: list[str], old: Path, new: Path, place: Placement) -> bool:
    """Carry the folder structure over and remove the old folders once they are empty.

    Only the term folders the sync created are walked, so folders elsewhere in
    ``old`` are never touched; an empty folder there (a week with nothing in it
    yet) is created in ``new``. A folder that still holds anything besides
    system leftovers stays. Returns whether ``old`` itself went.
    """
    tops = {old / PurePosixPath(rel).parts[0] for rel in rel_paths if len(PurePosixPath(rel).parts) > 1}
    for top in sorted(tops):
        for dirpath, _dirs, _files in os.walk(top, topdown=False):
            folder = Path(dirpath)
            if folder == new or new in folder.parents or folder in new.parents:
                continue
            if _remove_if_empty(folder):
                (new / place.folder(folder.relative_to(old).as_posix())).mkdir(parents=True, exist_ok=True)
    if old.is_dir() and old not in new.parents:
        _remove_if_empty(old)
    return not old.exists()


def _remove_if_empty(folder: Path) -> bool:
    try:
        entries = list(folder.iterdir())
        if any(entry.name not in SYSTEM_JUNK or not entry.is_file() for entry in entries):
            return False
        for entry in entries:
            entry.unlink()
        folder.rmdir()
        return True
    except OSError as exc:
        log.info("Left folder %s in place: %s", folder, exc)
        return False
