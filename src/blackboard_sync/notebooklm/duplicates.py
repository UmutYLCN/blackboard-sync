"""Sources that are in a notebook twice, and taking out the extra copies this app added.

Listing changes nothing in NotebookLM. Removing is a separate step that the student confirms,
and the only thing in the app that deletes a source. It takes a copy only when all of this holds,
checked again on what the notebook holds at that moment, never on an earlier list:

- this app added it: its id is in the upload record, and it was not adopted or the old tool's;
- an older copy is there and ready, and the record shows the same content for both.

So a copy someone added by hand, the older copy and a newer version of a changed file all stay.
A file that changed on Blackboard is listed as such; which version to keep is the student's call.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Collection

from blackboard_sync.config import Config
from blackboard_sync.errors import (
    AlreadyRunning,
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMTransient,
)
from blackboard_sync.notebooklm import planner, runner, store
from blackboard_sync.notebooklm.store import KnownSource
from blackboard_sync.sync import run_lock
from blackboard_sync.system import make_private_dir

log = logging.getLogger(__name__)

IDENTICAL = "identical"  # the same content as the older copy, and this app added it: can be removed
CHANGED = "changed"  # the file changed since the older copy went up: both versions stay
NOT_ADDED_BY_APP = "not-added-by-app"  # never removed: nothing shows this app added it
UNVERIFIED = "unverified"  # the content or the age of the copies cannot be compared

DELETE_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class Copy:
    id: str
    title: str
    status: str
    created_at: str
    origin: str  # store.ORIGIN_*
    rel: str = ""  # the file it was added for, when the record knows
    verdict: str = ""  # for a newer copy: one of the values above
    removable: bool = False


@dataclass(frozen=True)
class Duplicate:
    name: str
    older: Copy
    newer: tuple[Copy, ...]


@dataclass
class CourseDuplicates:
    course: str
    folder: str
    notebook_id: str
    duplicates: list[Duplicate] = field(default_factory=list)

    @property
    def removable(self) -> list[tuple[Copy, Copy]]:
        """(the copy to remove, the older copy that stays)."""
        return [(copy, duplicate.older) for duplicate in self.duplicates for copy in duplicate.newer
                if copy.removable]


@dataclass
class Report:
    status: str = "ok"  # ok | login_required | locked | error
    message: str = ""
    courses: list[CourseDuplicates] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "event": "result",
            "status": self.status,
            "message": self.message,
            "duplicates": sum(len(course.duplicates) for course in self.courses),
            "removable": sum(len(course.removable) for course in self.courses),
            "removed": self.removed,
            "failed": self.failed,
            "courses": [{**asdict(course), "removable": len(course.removable)} for course in self.courses],
        }


def _different_files(first: KnownSource | None, second: KnownSource | None) -> bool:
    """Two files that happen to share a name, in two folders: that is no duplicate."""
    return bool(first and second and first.rel != second.rel and first.sha256 != second.sha256)


def _verdict(older, copy, known: dict[str, KnownSource]) -> str:
    first, second = known.get(older.id), known.get(copy.id)
    if second is None or second.origin != store.ORIGIN_APP:
        return NOT_ADDED_BY_APP
    if first is None:
        return UNVERIFIED
    if first.sha256 != second.sha256:
        return CHANGED
    if older.status != "ready" or not older.created_at or not older.created_at < copy.created_at:
        return UNVERIFIED
    return IDENTICAL


def _copy(source, known: dict[str, KnownSource], verdict: str = "") -> Copy:
    record = known.get(source.id)
    return Copy(source.id, source.title, source.status, source.created_at,
                record.origin if record else store.ORIGIN_OTHER, record.rel if record else "",
                verdict, verdict == IDENTICAL)


def find_in_notebook(sources: list, known: dict[str, KnownSource]) -> list[Duplicate]:
    """Sources sharing a file name, each group with its oldest copy first. Pure, no network."""
    names: dict[str, list] = {}
    for source in sorted(sources, key=lambda source: source.created_at or "~"):  # unknown age: last
        names.setdefault(planner.name_key(source.title), []).append(source)
    found = []
    for name, group in names.items():
        heads: dict[str, list] = {}  # the oldest copy of each distinct file of this name
        for source in group:
            head = next((id_ for id_, copies in heads.items()
                         if not _different_files(known.get(id_), known.get(source.id))), None)
            heads.setdefault(head or source.id, []).append(source)
        for copies in heads.values():
            if len(copies) > 1:
                older, *newer = copies
                found.append(Duplicate(group[0].title.rsplit("/", 1)[-1], _copy(older, known),
                                       tuple(_copy(copy, known, _verdict(older, copy, known)) for copy in newer)))
    return found


async def _scan(state: store.UploadState, gateway) -> list[CourseDuplicates]:
    courses = []
    for folder, course in state.data["courses"].items():
        if course.get("notebook_id"):
            sources = await gateway.list_sources(course["notebook_id"])
            courses.append(CourseDuplicates(PurePosixPath(folder).name, folder, course["notebook_id"],
                                            find_in_notebook(sources, state.known_sources(folder))))
    return courses


async def _remove(report: Report, state: store.UploadState, gateway, only: Collection[str]) -> None:
    for course in report.courses:
        for copy, older in course.removable:
            if copy.id not in only:
                continue
            label = f"{course.course}/{copy.rel or copy.title}"
            try:
                await gateway.delete_source(course.notebook_id, copy.id)
            except (NotebookLMTransient, NotebookLMPermanent) as exc:
                report.failed.append((label, str(exc)))
                continue
            state.repoint(course.folder, copy.id, older.id)
            state.save()
            report.removed.append(label)
            await asyncio.sleep(DELETE_DELAY_SECONDS)


async def _run(config: Config, only: Collection[str] | None) -> Report:
    state = store.UploadState.load(store.state_file(config))
    state.import_legacy(list(state.data["courses"]), config.notebooklm_legacy_state)
    gateway = await runner.open_gateway(config)
    report = Report()
    try:
        report.courses = await _scan(state, gateway)
        if only:
            await _remove(report, state, gateway, only)
    finally:
        state.save()
        await gateway.close()
    return report


def _guarded(config: Config, only: Collection[str] | None) -> Report:
    config.ensure_data_dir()
    make_private_dir(config.notebooklm_dir)
    try:
        with run_lock(store.lock_file(config)):
            if not store.session_file(config).is_file():
                raise NotebookLMLoginRequired()
            report = asyncio.run(_run(config, only))
            os.utime(store.session_file(config))
            return report
    except AlreadyRunning as exc:
        return Report(status="locked", message=str(exc))
    except NotebookLMLoginRequired as exc:
        return Report(status="login_required", message=str(exc))
    except (NotebookLMTransient, NotebookLMPermanent, OSError) as exc:
        return Report(status="error", message=str(exc))


def find(config: Config) -> Report:
    """List the duplicates. Deletes nothing."""
    return _guarded(config, None)


def remove(config: Config, source_ids: Collection[str]) -> Report:
    """Remove these confirmed copies, as far as the rules at the top of this module still allow."""
    return _guarded(config, set(source_ids))
