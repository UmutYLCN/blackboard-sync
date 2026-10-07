"""The local record of what has already been mirrored.

``state.json`` (in the private data directory) maps stable Blackboard keys to
what was written locally:

* ``items``   - one entry per content item or announcement, keyed by
  ``<kind>:<course id>:<blackboard id>``, holding the ``modified`` timestamp
  seen when it was last processed and the output keys it produced. An item
  whose ``modified`` is unchanged is skipped entirely on the next run.
* ``outputs`` - one entry per local file (attachment, embedded file or note),
  keyed by Blackboard attachment/file id, holding the path relative to the
  destination folder, its SHA-256 and size. This is what prevents
  re-downloads and protects files the student changed locally.
* ``folders`` - Windows only: the full Blackboard name of every folder whose
  name was shortened to fit the path limit, keyed by its relative path. Moving
  to another destination folder needs it to give the folders the names a sync
  there would choose.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from blackboard_sync.session import write_private_json

STATE_VERSION = 1


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
    def __init__(self, path: Path, data: dict | None = None):
        self.path = path
        data = data or {}
        self.items: dict[str, dict] = data.get("items", {})
        self.outputs: dict[str, dict] = data.get("outputs", {})
        self.folders: dict[str, str] = data.get("folders", {})
        self._claimed: dict[str, str] = {o["path"]: key for key, o in self.outputs.items()}
        self.recovery: str | None = None
        self.dirty = False  # True while there are changes not yet written to disk

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
        if self.folders:
            data["folders"] = self.folders
        write_private_json(self.path, data)
        self.dirty = False

    # -- items ----------------------------------------------------------
    def item_unchanged(self, key: str, modified: str | None, dest: Path, check_missing: bool) -> bool:
        entry = self.items.get(key)
        if entry is None or modified is None or entry.get("modified") != modified or entry.get("partial"):
            return False
        if check_missing:
            for out_key in entry.get("outputs", []):
                out = self.outputs.get(out_key)
                if out is None or not (dest / out["path"]).exists():
                    return False
        return True

    def record_item(
        self, key: str, modified: str | None, outputs: list[str], title: str, partial: bool = False
    ) -> None:
        """``partial`` marks an item some of whose files failed: it is retried next run."""
        entry = {"modified": modified, "outputs": outputs, "title": title}
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

    def record_output(self, key: str, rel_path: str, sha256: str, size: int) -> None:
        old = self.outputs.get(key)
        if old and self._claimed.get(old["path"]) == key:
            del self._claimed[old["path"]]
        entry = {"path": rel_path, "sha256": sha256, "size": size}
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
        changed = False
        for entry in self.outputs.values():
            if entry["path"] == old_rel:
                entry["path"] = new_rel
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
