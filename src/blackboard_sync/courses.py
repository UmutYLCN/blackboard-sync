"""Which courses the app keeps in sync: the Dersler section of the main window.

Every current-term course is synced unless the student unticked it. The choice
is saved as the Blackboard course primary keys (``_13004_1``, never the name)
the student switched off, in ``courses.json`` beside ``state.json``, so a
course that shows up later is on by default. The app writes the file and every
sync, also one started from the terminal, reads it before each course: an
unticked course gets no requests at all (no contents, attachments,
announcements or due dates) and its files stay on disk as they are. Ticking it
again fills in what is missing on the next sync.

The list itself is what the last normal sync found (``State.courses``).
User-facing strings are Turkish on purpose.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterable

from blackboard_sync.i18n import tr
from blackboard_sync.config import Config
from blackboard_sync.session import write_private_json
from blackboard_sync.state import State

log = logging.getLogger(__name__)

T_TAB = tr("Courses")
T_HINT = (
    tr("This folder is a copy of Blackboard: the files of the ticked courses are matched to "
    "Blackboard on every sync, and deleted or damaged files are downloaded again. To keep files "
    "your own way, copy them to another folder.")
)
T_UNTICK_HINT = (
    tr("A course you untick is no longer synced and does not show in Calendar or Announcements. "
    "Its downloaded files are not deleted. Tick it again and its missing files come right away.")
)
T_EMPTY = tr("Your courses are listed here after the first sync.")


@dataclass(frozen=True)
class CourseRow:
    id: str  # Blackboard primary key, e.g. "_13004_1"
    code: str
    title: str
    term: str
    enabled: bool


def load_disabled(config: Config) -> set[str]:
    """The unticked course ids; an unreadable file counts as none (every course syncs)."""
    try:
        data = json.loads(config.courses_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as exc:
        log.warning("Could not read %s: %s", config.courses_file.name, exc)
        return set()
    disabled = data.get("disabled") if isinstance(data, dict) else None
    if not isinstance(disabled, list):
        return set()
    return {course_id for course_id in disabled if isinstance(course_id, str)}


def save_disabled(config: Config, disabled: Iterable[str]) -> None:
    config.ensure_data_dir()
    write_private_json(config.courses_file, {"version": 1, "disabled": sorted(set(disabled))})


def set_enabled(config: Config, course_id: str, enabled: bool) -> None:
    disabled = load_disabled(config)
    if enabled:
        disabled.discard(course_id)
    else:
        disabled.add(course_id)
    save_disabled(config, disabled)


def course_rows(state: State, disabled: set[str]) -> tuple[CourseRow, ...]:
    rows = (CourseRow(course_id, info.get("code") or "", info.get("title") or "", info.get("term") or "",
                      course_id not in disabled)
            for course_id, info in state.courses.items())
    return tuple(sorted(rows, key=lambda r: (r.term.casefold(), r.code.casefold(), r.title.casefold(), r.id)))


def hidden_folders(state: State, disabled: set[str]) -> tuple[str, ...]:
    """The folders (relative to University) of the unticked courses, for hiding their files."""
    return tuple(sorted(info["folder"] for course_id, info in state.courses.items()
                        if course_id in disabled and info.get("folder")))


def load_rows(config: Config) -> tuple[CourseRow, ...]:
    return course_rows(State.load(config.state_file, backup=False), load_disabled(config))


def load_hidden_folders(config: Config) -> tuple[str, ...]:
    return hidden_folders(State.load(config.state_file, backup=False), load_disabled(config))
