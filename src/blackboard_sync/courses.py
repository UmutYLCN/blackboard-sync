"""Which courses the app keeps in sync: the Dersler section of the main window.

Every current-term course is synced unless the student unticked it, except the
courses without a term (guidance or orientation pages), which are off until
ticked, unless the school has no terms at all. The choice is saved as the
Blackboard course primary keys (``_13004_1``, never the name) the student
switched off (``disabled``) or switched on among the termless ones
(``enabled``), in ``courses.json`` beside ``state.json``, so a course that
shows up later is on by default. The app writes the file and every
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
from typing import Iterable, Mapping

from blackboard_sync.i18n import tr
from blackboard_sync.config import Config
from blackboard_sync.session import write_private_json
from blackboard_sync.state import State

NO_TERM = "No term"  # what 1.7.1 recorded as the term of a course without one (``sync.NO_TERM``)

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
T_TERMLESS_HINT = tr("Courses without a term, such as guidance or orientation pages, are not synced unless you tick them.")
T_EMPTY = tr("Your courses are listed here after the first sync.")


@dataclass(frozen=True)
class CourseRow:
    id: str  # Blackboard primary key, e.g. "_13004_1"
    code: str
    title: str
    term: str
    enabled: bool
    termless: bool = False  # Blackboard gives it no term


def _read(config: Config) -> tuple[set[str], set[str]]:
    """The saved (unticked, ticked-on-purpose) course ids; an unreadable file counts as none."""
    try:
        data = json.loads(config.courses_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), set()
    except (OSError, ValueError) as exc:
        log.warning("Could not read %s: %s", config.courses_file.name, exc)
        return set(), set()
    if not isinstance(data, dict):
        return set(), set()

    def ids(key: str) -> set[str]:
        value = data.get(key)
        return {course_id for course_id in value if isinstance(course_id, str)} if isinstance(value, list) else set()

    return ids("disabled"), ids("enabled")  # a version 1 file has no "enabled"


def _write(config: Config, disabled: Iterable[str], enabled: Iterable[str]) -> None:
    config.ensure_data_dir()
    write_private_json(config.courses_file, {"version": 2, "disabled": sorted(set(disabled)),
                                             "enabled": sorted(set(enabled))})


def load_disabled(config: Config) -> set[str]:
    """The course ids the student unticked; not what a sync skips (``effective_disabled``)."""
    return _read(config)[0]


def save_disabled(config: Config, disabled: Iterable[str]) -> None:
    _write(config, disabled, _read(config)[1])


def is_termless(info: dict) -> bool:
    """A course without a Blackboard term; ``state.json`` from 1.7.1 only has the folder name for it."""
    if "termless" in info:
        return bool(info["termless"])
    return info.get("term") == NO_TERM


def default_off(known: Mapping[str, dict]) -> set[str]:
    """Courses without a term that are off until the student ticks them.

    Guidance and orientation pages have no term and nobody asked for them. They only
    sync by themselves at a school that has no terms at all, where nothing else would.
    """
    termless = {course_id for course_id, info in known.items() if is_termless(info)}
    return termless if len(termless) < len(known) else set()


def effective_disabled(config: Config, known: Mapping[str, dict]) -> set[str]:
    """Every course id a sync, the calendar, Announcements and NotebookLM leave out.

    ``known`` is ``State.courses``: the current courses the last sync found.
    """
    disabled, enabled = _read(config)
    return disabled | (default_off(known) - enabled)


def set_enabled(config: Config, course_id: str, enabled: bool) -> None:
    disabled, on_purpose = _read(config)
    if enabled:
        disabled.discard(course_id)
        if is_termless(State.load(config.state_file, backup=False).courses.get(course_id, {})):
            on_purpose.add(course_id)
    else:
        disabled.add(course_id)
        on_purpose.discard(course_id)
    _write(config, disabled, on_purpose)


def course_rows(state: State, disabled: set[str]) -> tuple[CourseRow, ...]:
    rows = (CourseRow(course_id, info.get("code") or "", info.get("title") or "", info.get("term") or "",
                      course_id not in disabled, is_termless(info))
            for course_id, info in state.courses.items())
    # The courses without a term come last, under the hint that explains them.
    return tuple(sorted(rows, key=lambda r: (r.termless, r.term.casefold(), r.code.casefold(), r.title.casefold(), r.id)))


def termless_hint(rows: Iterable[CourseRow]) -> str:
    """The note under the courses without a term; empty when they sync like any course (a school without terms)."""
    rows = tuple(rows)
    return T_TERMLESS_HINT if any(r.termless for r in rows) and not all(r.termless for r in rows) else ""


def hidden_folders(state: State, disabled: set[str]) -> tuple[str, ...]:
    """The folders (relative to University) of the unticked courses, for hiding their files."""
    return tuple(sorted(info["folder"] for course_id, info in state.courses.items()
                        if course_id in disabled and info.get("folder")))


def load_rows(config: Config) -> tuple[CourseRow, ...]:
    state = State.load(config.state_file, backup=False)
    return course_rows(state, effective_disabled(config, state.courses))


def load_hidden_folders(config: Config) -> tuple[str, ...]:
    state = State.load(config.state_file, backup=False)
    return hidden_folders(state, effective_disabled(config, state.courses))
