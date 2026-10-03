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
from pathlib import Path

from blackboard_sync.session import write_private_json

STATE_VERSION = 1


class State:
    def __init__(self, path: Path, data: dict | None = None):
        self.path = path
        data = data or {}
        self.items: dict[str, dict] = data.get("items", {})
        self.outputs: dict[str, dict] = data.get("outputs", {})
        self._claimed: dict[str, str] = {o["path"]: key for key, o in self.outputs.items()}

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != STATE_VERSION:
            raise ValueError(f"Unsupported state file version in {path}")
        return cls(path, data)

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
