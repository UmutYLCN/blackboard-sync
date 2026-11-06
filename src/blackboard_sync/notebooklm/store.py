"""What NotebookLM needs on disk: the session, what was added and how the last run went.

Everything is in the ``notebooklm`` folder of the private data directory: never in the
repository or the course folder. ``session.json`` holds the Google cookies, so it is written
owner-only and never logged. ``state.json`` records per file what it looked like when it was
added, so a file goes up once however often the sync runs. It survives a disconnect: signing
in again does not add everything a second time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from blackboard_sync.config import Config
from blackboard_sync.session import write_private_json
from blackboard_sync.signout import _remove_tree

log = logging.getLogger(__name__)

NEW = "new"
UNCHANGED = "unchanged"
TOUCHED = "touched"  # the size or modification time differ, the content does not
MODIFIED = "modified"  # the content differs from what was added

STATE_VERSION = 1


def session_file(config: Config) -> Path:
    return config.notebooklm_dir / "session.json"


def state_file(config: Config) -> Path:
    return config.notebooklm_dir / "state.json"


def last_run_file(config: Config) -> Path:
    return config.notebooklm_dir / "last-run.json"


def lock_file(config: Config) -> Path:
    return config.notebooklm_dir / "run.lock"


def profile_dir(config: Config) -> Path:
    """The sign-in browser's private profile: it stays signed in to Google for the next sign-in."""
    return config.notebooklm_dir / "browser-profile"


def library_home(config: Config) -> Path:
    """``NOTEBOOKLM_HOME``, so the library stays away from a ``~/.notebooklm`` of the student's own."""
    return config.notebooklm_dir / "library"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


class UploadState:
    """Per course: its notebook and, for each file added, what it looked like then."""

    def __init__(self, path: Path, data: dict | None = None):
        self.path = path
        self.data = data or {"version": STATE_VERSION, "courses": {}}

    @classmethod
    def load(cls, path: Path) -> "UploadState":
        """A missing or unreadable file starts empty: same-titled sources are adopted, never added twice."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(path)
        except (OSError, ValueError) as exc:
            log.warning("Could not read %s: %s", path.name, exc)
            return cls(path)
        if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
            return cls(path)
        data.setdefault("courses", {})
        return cls(path, data)

    def save(self) -> None:
        write_private_json(self.path, self.data)

    def _course(self, course: str) -> dict:
        return self.data["courses"].setdefault(course, {"notebook_id": None, "files": {}})

    def notebook_id(self, course: str) -> str | None:
        return self.data["courses"].get(course, {}).get("notebook_id")

    def set_notebook(self, course: str, notebook_id: str) -> None:
        self._course(course)["notebook_id"] = notebook_id

    def get_file(self, course: str, rel: str) -> dict | None:
        return self.data["courses"].get(course, {}).get("files", {}).get(rel)

    def record(self, course: str, rel: str, *, notebook_id: str, source_id: str, size: int, mtime_ns: int,
               sha256: str) -> None:
        self._course(course)["files"][rel] = {
            "notebook_id": notebook_id,
            "source_id": source_id,
            "size": size,
            "mtime_ns": mtime_ns,
            "sha256": sha256,
            "added_at": utcnow_text(),
        }

    def refresh(self, course: str, rel: str, *, size: int, mtime_ns: int) -> None:
        entry = self._course(course)["files"][rel]
        entry["size"], entry["mtime_ns"] = size, mtime_ns


def classify(entry: dict | None, size: int, mtime_ns: int, hasher: Callable[[], str]) -> tuple[str, str | None]:
    """(verdict, the file's hash if it was needed): hashes only when size or time disagree with the record."""
    if entry is None:
        return NEW, None
    if entry["size"] == size and entry["mtime_ns"] == mtime_ns:
        return UNCHANGED, None
    digest = hasher()
    return (TOUCHED if digest == entry["sha256"] else MODIFIED), digest


def utcnow_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class NotebookLMStatus:
    """The connection and the last run, for the Home card."""

    connected: bool = False
    needs_login: bool = False  # Google rejected the session: only signing in again helps
    error: bool = False  # the last run did not finish
    finished_at: str = ""
    added: int = 0
    skipped: int = 0  # files NotebookLM does not take
    modified: int = 0  # changed since they were added; never replaced
    blocked: int = 0  # courses over the source limit: nothing was added to them
    failed: int = 0
    message: str = ""


def _read_last_run(config: Config) -> dict:
    try:
        data = json.loads(last_run_file(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def status(config: Config) -> NotebookLMStatus:
    data = _read_last_run(config)
    counts = {key: value for key in ("added", "skipped", "modified", "blocked", "failed")
              if isinstance(value := data.get(key), int)}
    return NotebookLMStatus(
        connected=session_file(config).is_file(),
        needs_login=data.get("status") == "login_required",
        error=data.get("status") == "error",
        finished_at=data.get("finished_at") if isinstance(data.get("finished_at"), str) else "",
        message=data.get("message") if isinstance(data.get("message"), str) else "",
        **counts,
    )


def save_last_run(config: Config, data: dict) -> None:
    write_private_json(last_run_file(config), data)


def mark_connected(config: Config) -> None:
    """A new sign-in clears what the last run said about the old session; its counts stay."""
    data = _read_last_run(config)
    if data.get("status") in ("login_required", "error"):
        save_last_run(config, {**data, "status": "ok", "message": ""})


def disconnect(config: Config) -> list[str]:
    """Delete the stored session and everything else that can act as this Google account.

    Returns what could not be removed. What was added stays in NotebookLM and in ``state.json``.
    """
    for path in session_file(config).parent.glob(session_file(config).name + "*"):  # with its .lock
        path.unlink(missing_ok=True)
    last_run_file(config).unlink(missing_ok=True)
    return [str(path) for path in (profile_dir(config), library_home(config)) if not _remove_tree(path)]

