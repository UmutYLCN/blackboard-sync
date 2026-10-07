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
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

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
        self._claimed: dict[str, str] = {o["path"]: key for key, o in self.outputs.items()}
        self.recovery: str | None = None

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
        write_private_json(
            self.path,
            {"version": STATE_VERSION, "items": self.items, "outputs": self.outputs},
        )

    # -- items ----------------------------------------------------------
    def item_unchanged(self, key: str, modified: str | None, dest: Path, check_missing: bool) -> bool:
        entry = self.items.get(key)
        if entry is None or modified is None or entry.get("modified") != modified:
            return False
        if check_missing:
            for out_key in entry.get("outputs", []):
                out = self.outputs.get(out_key)
                if out is None or not (dest / out["path"]).exists():
                    return False
        return True

    def record_item(self, key: str, modified: str | None, outputs: list[str], title: str) -> None:
        self.items[key] = {"modified": modified, "outputs": outputs, "title": title}

    # -- outputs --------------------------------------------------------
    def output(self, key: str) -> dict | None:
        return self.outputs.get(key)

    def owner_of(self, rel_path: str) -> str | None:
        return self._claimed.get(rel_path)

    def record_output(self, key: str, rel_path: str, sha256: str, size: int) -> None:
        old = self.outputs.get(key)
        if old and self._claimed.get(old["path"]) == key:
            del self._claimed[old["path"]]
        self.outputs[key] = {"path": rel_path, "sha256": sha256, "size": size}
        self._claimed[rel_path] = key

    def move_output(self, old_key: str, new_key: str) -> None:
        """Hand a mirrored file over to a new key (the file was replaced upstream)."""
        entry = self.outputs.pop(old_key, None)
        if entry is None or new_key in self.outputs:
            if entry is not None:
                self.outputs[old_key] = entry
            return
        self.outputs[new_key] = entry
        self._claimed[entry["path"]] = new_key
