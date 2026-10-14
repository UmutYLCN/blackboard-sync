"""The local record of what has already been mirrored.

``state.json`` (in the private data directory) maps stable Blackboard keys to
what was written locally:

* ``items``   - one entry per content item or announcement, keyed by
  ``<kind>:<course id>:<blackboard id>``, holding the ``modified`` timestamp
  seen when it was last processed and the output keys it produced. An item
  whose ``modified`` is unchanged is skipped entirely on the next run. Embedded
  videos and audio that were left as links are listed under ``media``; files
  skipped for size are listed in ``large_files`` with their reported byte count.
* ``outputs`` - one entry per local file (attachment, embedded file or note),
  keyed by Blackboard attachment/file id, holding the path relative to the
  destination folder, its SHA-256, size and (since files are restored) the
  modification time it had when written. This is what prevents re-downloads,
  brings back files that went missing or broke (``intact``) and protects files
  the student changed locally. Versions before that had ``dismissed`` flags
  (files taken off the Silinenler list); they are dropped on load, so those
  files come back once.
* ``folders`` - Windows only: the full Blackboard name of every folder whose
  name was shortened to fit the path limit, keyed by its relative path. Moving
  to another destination folder needs it to give the folders the names a sync
  there would choose.
* ``past_terms`` - term ids explicitly downloaded as one-time archives; normal
  sync leaves their content alone. Missing files are restored only on request.
  ``downloaded_at`` is when a download last read every course; ``incomplete``
  marks one whose last download could not read a course's content.
* ``courses`` - the current term's courses the last normal sync found, keyed
  by Blackboard course primary key: code, title, term and folder. The Dersler
  section lists them (``courses.py``), the unticked ones too.
* ``deadline_courses`` - student-visible grade-column due dates, grouped by
  course, with content ids for note lookup and an availability flag. A failed
  fetch keeps the previous complete list; successful lists replace it.
* ``announcements`` - cached course, title, date, preview and note output key for
  the announcements page. ``current_courses`` limits that page to current terms.
* ``university_folder`` - true once the files of versions that wrote straight
  into the chosen folder were moved into its University folder
  (``relocate.migrate_to_root``), so that happens only once.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from blackboard_sync.session import write_private_json

STATE_VERSION = 1
log = logging.getLogger(__name__)
_monotonic = time.monotonic  # a seam for tests


def intact(path: Path, entry: dict) -> bool:
    """Whether the file recorded as ``entry`` is at ``path`` and not clearly broken.

    Only the file's metadata is read: hashing every file on each run would be
    slow and would download every file a cloud drive (iCloud, OneDrive) keeps
    online only. Broken means zero bytes where more was recorded, or another
    size while the modification time is still the one recorded when the file
    was written, so the student never touched it. A file changed since then is
    the student's edit and counts as intact; so does anything that is not a
    regular file, and a file iCloud moved to the cloud as ``.name.icloud``.
    """
    try:
        info = path.stat()
    except OSError:
        return (path.parent / f".{path.name}.icloud").exists()
    if not stat.S_ISREG(info.st_mode):
        return True
    size = entry.get("size")
    if info.st_size == 0 and size:
        return False
    return not (entry.get("mtime_ns") == info.st_mtime_ns and size is not None and info.st_size != size)


def untouched(path: Path, entry: dict) -> bool:
    """The file still has the modification time recorded when it was written."""
    try:
        return entry.get("mtime_ns") is not None and path.stat().st_mtime_ns == entry["mtime_ns"]
    except OSError:
        return False


def _set_aside(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    n = 1
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
    os.replace(path, target)
    return target


class State:
    # A run saves its progress as it goes, but at most once per this many seconds.
    save_interval = 5.0

    def __init__(self, path: Path, data: dict | None = None):
        self.path = path
        # A new state only ever records files in the University folder.
        in_university_folder = data is None
        data = data or {}
        self.items: dict[str, dict] = data.get("items", {})
        self.outputs: dict[str, dict] = data.get("outputs", {})
        self.folders: dict[str, str] = data.get("folders", {})
        self.past_terms: dict[str, dict] = data.get("past_terms", {})
        self.deadline_courses: dict[str, dict] = data.get("deadline_courses", {})
        self.announcements: dict[str, dict] = data.get("announcements", {})
        self.current_courses: list[str] = data.get("current_courses", [])
        self.courses: dict[str, dict] = data.get("courses", {})
        self.in_university_folder: bool = in_university_folder or data.get("university_folder") is True
        self._claimed: dict[str, str] = {o["path"]: key for key, o in self.outputs.items()}
        self.recovery: str | None = None
        self.dirty = False  # True while there are changes not yet written to disk
        for entry in self.outputs.values():
            if entry.pop("dismissed", None) is not None:
                self.dirty = True  # every file is restored now; written with the next save
        self.save_error: str | None = None  # why the last write by ``checkpoint`` failed
        self._last_attempt: float | None = None

    @classmethod
    def load(cls, path: Path, backup: bool = True) -> "State":
        """Read the state file; never fail because of its content.

        A file that is not valid JSON, has the wrong shape or comes from another
        state version is set aside as ``<name>.corrupt-<timestamp>`` (kept, never
        deleted) and the sync continues with an empty state. That is safe because
        a re-fetched file that is byte-identical to the one on disk is adopted
        (no duplicate, no overwrite), so the state rebuilds itself. ``recovery`` then describes what happened so it can be reported.
        With ``backup=False`` (dry runs) the file is left untouched.
        """
        if not path.exists():
            return cls(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("state file is not a JSON object")
            if data.get("version") != STATE_VERSION:
                raise ValueError(f"unsupported state file version {data.get('version')!r}")
            return cls(path, data)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            state = cls(path)
            if backup:
                saved = _set_aside(path)
                state.recovery = (
                    f"Could not read {path.name} ({exc}); moved it to {saved.name} "
                    "and continued with an empty state. Files already on disk that match "
                    "Blackboard's copy are kept as they are, not duplicated."
                )
            else:
                state.recovery = f"Could not read {path.name} ({exc}); it would be set aside on a real sync."
            return state

    def save(self) -> None:
        """Write the state file, but only if something changed since the last write."""
        if not self.dirty:
            return
        data = {"version": STATE_VERSION, "items": self.items, "outputs": self.outputs}
        if self.announcements:
            data["announcements"] = self.announcements
        if self.current_courses:
            data["current_courses"] = self.current_courses
        if self.folders:
            data["folders"] = self.folders
        if self.past_terms:
            data["past_terms"] = self.past_terms
        if self.deadline_courses:
            data["deadline_courses"] = self.deadline_courses
        if self.courses:
            data["courses"] = self.courses
        if self.in_university_folder:
            data["university_folder"] = True
        write_private_json(self.path, data)
        self.dirty = False

    def checkpoint(self, force: bool = False) -> bool:
        """Write pending changes during a run; unlike ``save`` it never raises.

        Without ``force`` the write is skipped when one was attempted less than
        ``save_interval`` seconds ago, so a run that processes many small items does
        not rewrite the file for each. A failed write leaves the changes pending, is
        retried by a later checkpoint and is described by ``save_error``. Returns
        False when a write failed.
        """
        if not self.dirty:
            return True
        now = _monotonic()
        if not force and self._last_attempt is not None and now - self._last_attempt < self.save_interval:
            return True
        self._last_attempt = now
        try:
            self.save()
        except Exception as exc:  # a full disk or a locked file must not stop the sync
            self.save_error = f"{type(exc).__name__}: {exc}"
            log.warning("Could not save %s: %s", self.path.name, self.save_error)
            return False
        self.save_error = None
        return True

    def record_past_term(self, term_id: str, name: str, course_ids: list[str], complete: bool = True) -> None:
        """Archive metadata is additive; version-1 items and outputs keep their keys.

        Only a ``complete`` download (every course's content was read) sets
        ``downloaded_at``; any other keeps the time of the last complete one.
        """
        entry = {"name": name, "courses": course_ids}
        previous = (self.past_terms.get(term_id) or {}).get("downloaded_at")
        if complete:
            entry["downloaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        else:
            if previous:
                entry["downloaded_at"] = previous
            entry["incomplete"] = True
        self.past_terms[term_id] = entry
        self.dirty = True

    # -- items ----------------------------------------------------------
    def record_announcement(self, key: str, entry: dict) -> None:
        if self.announcements.get(key) != entry:
            self.announcements[key] = entry
            self.dirty = True

    def record_current_courses(self, course_ids: list[str]) -> None:
        course_ids = sorted(course_ids)
        if self.current_courses != course_ids:
            self.current_courses = course_ids
            self.dirty = True

    def item_unchanged(self, key: str, modified: str | None, present: Callable[[str], bool]) -> bool:
        """Nothing to do for this item: same ``modified`` and every file it produced is ``present``."""
        entry = self.items.get(key)
        if entry is None or modified is None or entry.get("modified") != modified or entry.get("partial"):
            return False
        return all(present(out_key) for out_key in entry.get("outputs", []))

    def record_item(
        self,
        key: str,
        modified: str | None,
        outputs: list[str],
        title: str,
        partial: bool = False,
        media: list[str] | None = None,
        large_files: dict[str, int] | None = None,
    ) -> None:
        """``partial`` marks an item some of whose files failed: it is retried next run.

        ``media`` lists the keys of embedded video/audio files that were not downloaded
        (they are links in the note); they count as handled, but own no local file.
        """
        entry = {"modified": modified, "outputs": outputs, "title": title}
        if media:
            entry["media"] = media
        if large_files:
            entry["large_files"] = large_files
        if partial:
            entry["partial"] = True
        if self.items.get(key) != entry:
            self.items[key] = entry
            self.dirty = True

    # -- outputs --------------------------------------------------------
    def output(self, key: str) -> dict | None:
        return self.outputs.get(key)

    def owner_of(self, rel_path: str) -> str | None:
        return self._claimed.get(rel_path)

    def record_output(self, key: str, rel_path: str, sha256: str, size: int, mtime_ns: int | None = None) -> None:
        """``mtime_ns`` is the file's modification time right after it was written (``intact``)."""
        old = self.outputs.get(key)
        if old and self._claimed.get(old["path"]) == key:
            del self._claimed[old["path"]]
        entry = {"path": rel_path, "sha256": sha256, "size": size}
        if mtime_ns is not None:
            entry["mtime_ns"] = mtime_ns
        if old != entry:
            self.outputs[key] = entry
            self.dirty = True
        self._claimed[rel_path] = key

    def set_validators(self, key: str, etag: str | None, last_modified: str | None) -> None:
        """Remember the HTTP validators of the copy recorded under ``key``.

        They let the next run skip the body of a download the server says is unchanged.
        """
        entry = self.outputs.get(key)
        if entry is None:
            return
        before = dict(entry)
        for field, value in (("etag", etag), ("last_modified", last_modified)):
            if value:
                entry[field] = value
            else:
                entry.pop(field, None)
        if entry != before:
            self.dirty = True

    def move_tree(self, old_dir: str, new_dir: str) -> int:
        """Point every output recorded under ``old_dir`` at ``new_dir``; returns how many."""
        prefix = old_dir.rstrip("/") + "/"
        moved = 0
        for entry in self.outputs.values():
            path = entry["path"]
            if path.startswith(prefix):
                entry["path"] = new_dir.rstrip("/") + "/" + path[len(prefix):]
                moved += 1
        if moved:
            self._claimed = {o["path"]: key for key, o in self.outputs.items()}
            self.dirty = True
        folders = {
            new_dir.rstrip("/") + rel[len(old_dir.rstrip("/")):] if rel == old_dir or rel.startswith(prefix) else rel: name
            for rel, name in self.folders.items()
        }
        if folders != self.folders:
            self.folders = folders
            self.dirty = True
        return moved

    def move_file(self, old_rel: str, new_rel: str) -> None:
        """Point the output recorded at ``old_rel`` at ``new_rel`` (the file was moved)."""
        self.move_paths({old_rel: new_rel})

    def move_paths(self, paths: dict[str, str]) -> None:
        """Update paths together, without applying one file's rename to another."""
        changed = False
        for entry in self.outputs.values():
            target = paths.get(entry["path"], entry["path"])
            if entry["path"] != target:
                entry["path"] = target
                changed = True
        if changed:
            self._claimed = {o["path"]: key for key, o in self.outputs.items()}
            self.dirty = True

    # -- folders (Windows) ----------------------------------------------
    def remember_folder(self, rel_dir: str, name: str) -> None:
        """Record that folder ``rel_dir`` stands for the Blackboard folder ``name``."""
        if PurePosixPath(rel_dir).name == name:
            if self.folders.pop(rel_dir, None) is not None:
                self.dirty = True
        elif self.folders.get(rel_dir) != name:
            self.folders[rel_dir] = name
            self.dirty = True

    def folder_name(self, rel_dir: str) -> str:
        """The full name of folder ``rel_dir``: what was recorded, else its own name."""
        return self.folders.get(rel_dir, PurePosixPath(rel_dir).name)

    def move_output(self, old_key: str, new_key: str) -> None:
        """Hand a mirrored file over to a new key (the file was replaced upstream)."""
        entry = self.outputs.pop(old_key, None)
        if entry is None or new_key in self.outputs:
            if entry is not None:
                self.outputs[old_key] = entry
            return
        self.outputs[new_key] = entry
        self._claimed[entry["path"]] = new_key
        self.dirty = True
