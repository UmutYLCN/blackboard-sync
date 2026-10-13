"""Discover the current term's courses and mirror their content locally."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Container

import requests

from blackboard_sync.api import PARTIAL_PREFIX, PARTIAL_SUFFIX, BlackboardClient, is_media
from blackboard_sync.announcements import metadata as announcement_metadata
from blackboard_sync.config import Config
from blackboard_sync.deadlines import column_deadline
from blackboard_sync.errors import AlreadyRunning, ApiError, BlackboardSyncError, LoginRequired, SkippedMedia
from blackboard_sync.htmltext import body_text, find_embedded_files
from blackboard_sync.notepdf import render_pdf
from blackboard_sync.notes import (
    announcement_date,
    handler_id,
    needs_note,
    render_announcement_note,
    render_item_note,
)
from blackboard_sync.paths import (
    course_code_and_title,
    course_folder_name,
    fit_windows_folder,
    fit_windows_path,
    fold_course_key,
    join_rel,
    legacy_course_folder_name,
    markdown_twin,
    note_name,
    numbered_variant,
    sanitize_name,
)
from blackboard_sync.report import CourseReport, SyncReport
from blackboard_sync.state import State
from blackboard_sync.system import is_windows, set_hidden, try_lock

log = logging.getLogger(__name__)

FOLDER_HANDLERS = {"resource/x-bb-folder", "resource/x-bb-lesson", "resource/x-bb-module-page"}
# Items that can never carry attachments; skip the extra request.
NO_ATTACHMENT_HANDLERS = {"resource/x-bb-externallink", "resource/x-bb-courselink"}
LEAF_HANDLERS = {"resource/x-bb-file", "resource/x-bb-document", "resource/x-bb-externallink"}
# Ultra stores a document's text and files in one hidden child of that name.
ULTRA_BODY_TITLE = "ultraDocumentBody"
NO_ATTACHMENTS_MESSAGE = "does not support file attachments"
NO_TERM = "No term"
# Courses usually open a little before the term officially starts.
TERM_LEAD_TIME = timedelta(days=30)
# One failing file or request must not stop the rest of the sync: it becomes a warning.
ITEM_ERRORS = (OSError, requests.RequestException)


@dataclass
class Course:
    id: str  # Blackboard primary key, e.g. "_13004_1"
    course_id: str  # e.g. "CSE303-1"
    name: str
    term_id: str | None
    term_name: str
    rel_dir: str  # "<term>/<code> <title>" relative to the destination
    code: str
    created: str | None = None
    # Where versions with ASCII-only course codes put this course, when that differs.
    legacy_rel_dir: str = ""


@dataclass
class Term:
    id: str | None
    name: str
    start: datetime | None = None
    end: datetime | None = None
    courses: list[Course] = field(default_factory=list)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def term_dates(term: dict | None) -> tuple[datetime | None, datetime | None]:
    duration = ((term or {}).get("availability") or {}).get("duration") or {}
    if duration.get("type") not in (None, "DateRange"):
        return None, None
    return parse_time(duration.get("start")), parse_time(duration.get("end"))


def choose_current_terms(terms: list[Term], now: datetime) -> list[Term]:
    """Pick the term(s) a student means by "this term".

    1. Terms whose date range contains today (opening a month early, because
       courses usually appear before the first lecture).
    2. Otherwise the most recently started term.
    3. Without any dates, the term holding the most recently created course.
    Courses without a term are never "current"; use ``--all-terms`` for them.
    """
    dated = [t for t in terms if t.id and t.start and t.end]
    current = [t for t in dated if t.start - TERM_LEAD_TIME <= now <= t.end]
    if current:
        return current
    started = [t for t in terms if t.id and t.start and t.start <= now]
    if started:
        return [max(started, key=lambda t: t.start)]
    candidates = [t for t in terms if t.id and t.courses]
    if not candidates:
        return []

    def newest_course(t: Term) -> datetime:
        stamps = [parse_time(c.created) for c in t.courses]
        return max((s for s in stamps if s), default=datetime.min.replace(tzinfo=timezone.utc))

    return [max(candidates, key=newest_course)]


def markdown_key(out_key: str) -> str:
    """The key of the hidden Markdown copy of the note recorded as ``out_key``.

    "note:<course>:<item>" -> "note-md:<course>:<item>"; the course id stays second.
    """
    kind, rest = out_key.split(":", 1)
    return f"{kind}-md:{rest}"


def is_markdown_key(key: str) -> bool:
    return key.split(":", 1)[0].endswith("-md")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_past_terms(terms: list[Term], now: datetime) -> list[Term]:
    """Terms with accessible courses, excluding every term normal sync selects."""
    current_ids = {term.id for term in choose_current_terms(terms, now)}
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(
        (term for term in terms if term.id and term.courses and term.id not in current_ids),
        key=lambda term: (
            term.start or max((parse_time(c.created) or floor for c in term.courses), default=floor),
            term.name,
        ),
        reverse=True,
    )


@contextmanager
def run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        if not try_lock(fh):
            raise AlreadyRunning("Another blackboard-sync run is already in progress.")
        yield
    finally:
        fh.close()


# A live download refreshes its temp file with every chunk and gives up after the
# 60 second read timeout, so one untouched for this long belongs to a run that was
# killed. Used only when the run lock is not held; under the lock every one is leftover.
STALE_PARTIAL_AGE = timedelta(minutes=10)


def remove_stale_partials(dest: Path, now: float | None = None, max_age: timedelta = STALE_PARTIAL_AGE) -> int:
    """Delete leftover ``.bbsync-*.partial`` files under *dest*; returns how many went.

    Under the run lock no other sync is writing, so every one is leftover: pass
    ``max_age=timedelta(0)``. Without the lock the age check keeps a concurrent
    run's live temp file safe.
    """
    cutoff = (time.time() if now is None else now) - max_age.total_seconds()
    removed = 0
    for path in dest.rglob(f"{PARTIAL_PREFIX}*{PARTIAL_SUFFIX}"):
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime <= cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            log.warning("Could not remove leftover %s: %s", path, exc)
    if removed:
        log.info("Removed %d leftover partial download(s)", removed)
    return removed


class _OnDisk:
    """A set-like view of the keys for which ``check`` holds."""

    def __init__(self, check):
        self.check = check

    def __contains__(self, key: str) -> bool:
        return self.check(key)


class Syncer:
    def __init__(
        self,
        client: BlackboardClient,
        config: Config,
        state: State,
        dry_run: bool = False,
        refetch_missing: bool = False,
        windows: bool | None = None,
        refetch_keys: set[str] | None = None,
        missing_only: bool = False,
    ):
        self.client = client
        self.config = config
        self.state = state
        self.dest = config.root  # every path below is relative to the University folder
        self.dry_run = dry_run
        self.refetch_missing = refetch_missing
        self.refetch_keys = refetch_keys
        self.windows = is_windows() if windows is None else windows
        self.missing_only = missing_only
        self.deadline_content_ids: dict[str, str] = {}

    def checkpoint(self) -> None:
        """Save progress so far (throttled) so a run that is killed keeps what it finished."""
        if not self.dry_run:
            self.state.checkpoint()

    def checkpoint_now(self) -> None:
        """Save progress now: at the end of a course and of the run."""
        if not self.dry_run:
            self.state.checkpoint(force=True)

    def should_refetch(self, key: str) -> bool:
        previous = self.state.output(key)
        return bool(self.refetch_missing and previous and not previous.get("dismissed")
                    and (self.refetch_keys is None or key in self.refetch_keys))

    def skip_output(self, key: str) -> bool:
        previous = self.state.output(key)
        if previous and previous.get("dismissed"):
            return True
        if self.refetch_keys is not None:
            if previous is None:
                # Only a note output handed over to a new key this run (``hide_legacy_note``).
                return key not in self.refetch_keys
            return not self.should_refetch(key) or (self.dest / previous["path"]).exists()
        if self.missing_only and previous:
            return (self.dest / previous["path"]).exists()
        return False

    # -- course discovery ----------------------------------------------
    def discover(
        self,
        user_id: str,
        term_name: str | None = None,
        all_terms: bool = False,
        course_filters: list[str] | None = None,
        now: datetime | None = None,
        warnings: list[str] | None = None,
    ) -> tuple[list[Term], list[Course]]:
        """Return (selected terms, their courses) for this student."""
        warnings = warnings if warnings is not None else []
        now = now or datetime.now(timezone.utc)
        terms: dict[str | None, Term] = {}
        for membership in self.client.memberships(user_id):
            if (membership.get("availability") or {}).get("available") == "No":
                continue
            course = membership.get("course")
            if not course:
                try:
                    course = self.client.course(membership["courseId"])
                except ApiError as exc:
                    warnings.append(f"Skipped course {membership.get('courseId')}: {exc}")
                    continue
            if (course.get("availability") or {}).get("available") == "No":
                continue  # private / not yet opened by the instructor
            term_id = course.get("termId")
            if term_id not in terms:
                raw = self.client.term(term_id) if term_id else None
                if term_id and raw is None:
                    warnings.append(f"Could not read term {term_id}; using its id as folder name.")
                name = (raw or {}).get("name") or (f"Term {term_id}" if term_id else NO_TERM)
                start, end = term_dates(raw)
                terms[term_id] = Term(term_id, name, start, end)
            term = terms[term_id]
            code, _ = course_code_and_title(course.get("courseId", ""), course.get("name", ""))
            term.courses.append(
                Course(
                    id=course["id"],
                    course_id=course.get("courseId", ""),
                    name=course.get("name", ""),
                    term_id=term_id,
                    term_name=term.name,
                    rel_dir="",
                    code=code,
                    created=course.get("created"),
                )
            )

        self.current_course_ids = [
            c.id for t in choose_current_terms(list(terms.values()), now)
            if t.id not in self.state.past_terms for c in t.courses
        ]
        if all_terms:
            selected = list(terms.values())
        elif term_name is not None:
            wanted = term_name.casefold()
            selected = [t for t in terms.values() if t.name.casefold() == wanted]
            if not selected:
                raise BlackboardSyncError(f"{term_name!r} adlı dönem bulunamadı.")
            past_ids = {t.id for t in choose_past_terms(list(terms.values()), now)}
            if len(selected) != 1 or selected[0].id not in past_ids:
                raise BlackboardSyncError(
                    "Yalnızca tek bir eski dönem indirilebilir; "
                    "güncel dönemi indirmek için normal senkronu kullanın."
                )
        else:
            selected = choose_current_terms(list(terms.values()), now)

        courses: list[Course] = []
        filters = {fold_course_key(f) for f in course_filters or []}
        for term in selected:
            used: set[str] = set()
            legacy_used: set[str] = set()
            term_dir = sanitize_name(term.name, windows=self.windows)
            for course in sorted(term.courses, key=lambda c: (c.code, c.course_id)):
                if filters and not filters & {
                    fold_course_key(course.code),
                    fold_course_key(course.course_id),
                    fold_course_key(course.id),
                }:
                    continue
                folder = self.unique_folder(course, course_folder_name, used)
                legacy = self.unique_folder(course, legacy_course_folder_name, legacy_used)
                course.rel_dir = join_rel(term_dir, folder)
                if legacy != folder:
                    course.legacy_rel_dir = join_rel(term_dir, legacy)
                courses.append(course)
        return selected, courses

    def unique_folder(self, course: Course, folder_name, used: set[str]) -> str:
        folder = folder_name(course.course_id, course.name, windows=self.windows)
        if folder.casefold() in used:
            folder = sanitize_name(f"{folder} ({course.course_id or course.id})", windows=self.windows)
        used.add(folder.casefold())
        return folder

    def migrate_course_folder(self, course: Course, warnings: list[str]) -> None:
        """Rename a folder an older version named differently ("İNG101-1 İNG101 ...")."""
        course.rel_dir = self.move_folder(course.legacy_rel_dir, course.rel_dir, warnings)

    def move_folder(self, old_rel: str, new_rel: str, warnings: list[str]) -> str:
        """Rename folder ``old_rel`` to ``new_rel``; return the folder to use from now on.

        The folder is moved in one step and the recorded paths follow it, so
        nothing is downloaded again. When the new name is already taken or the
        move fails (a file open on Windows), the old folder is kept and used as
        before; the next run tries again. A run interrupted right after the move
        only has to update the recorded paths, which happens when the old folder
        is gone.
        """
        if self.dry_run or not old_rel or old_rel == new_rel:
            return new_rel
        old, new = self.dest / old_rel, self.dest / new_rel
        if not old.is_dir():
            if self.state.move_tree(old_rel, new_rel):
                log.info("Recorded files of %s now live in %s", old_rel, new_rel)
            return new_rel
        if new.exists() and not self._same_entry(old, new):
            warnings.append(
                f"Kept folder {old_rel!r}: could not rename it to {new_rel!r} because that "
                "folder already exists. Move your files into one of them to finish."
            )
            return old_rel
        try:
            os.rename(old, new)
        except OSError as exc:
            warnings.append(f"Kept folder {old_rel!r}: could not rename it to {new_rel!r} ({exc}).")
            return old_rel
        self.state.move_tree(old_rel, new_rel)
        log.info("Renamed %s to %s", old_rel, new_rel)
        return new_rel

    def folder_path(self, rel_dir: str, title: str, warnings: list[str]) -> str:
        """Where the Blackboard folder ``title`` inside ``rel_dir`` is mirrored.

        On Windows a long name is shortened so deep trees stay within the path
        limit (``fit_windows_folder``) and the full name is recorded in the state;
        a folder an older version created with the full name is renamed to the
        shortened one.
        """
        name = sanitize_name(title, windows=self.windows)
        if not self.windows:
            return join_rel(rel_dir, name)
        fitted = join_rel(rel_dir, fit_windows_folder(self.dest, rel_dir, name))
        used = self.move_folder(join_rel(rel_dir, name), fitted, warnings)
        if not self.dry_run:
            # Moving to another destination folder fits the full name again (``relocate``).
            self.state.remember_folder(used, name)
        return used

    def migrate_item_outputs(self, previous_item: dict, old_dir: str, new_dir: str) -> None:
        """Move this item's recorded flat files into its instruction folder.

        Keep the recorded hashes and validators, including for locally edited or
        deleted files. Conflicting destination files use the usual numbered names;
        successful moves update state immediately so retries need no downloads.
        """
        if self.dry_run:
            return
        # Imported here because relocation also uses the sync lock and file hash.
        from blackboard_sync.relocate import _move_file

        for out_key in previous_item.get("outputs", []):
            previous = self.state.output(out_key)
            if not previous or str(PurePosixPath(previous["path"]).parent) != old_dir:
                continue
            old_rel = previous["path"]
            desired = join_rel(new_dir, PurePosixPath(old_rel).name)
            if self.windows:
                desired = fit_windows_path(self.dest, desired)
            source = self.dest / old_rel
            if source.is_file():
                desired, adopt = self.free_path(out_key, desired, sha256_file(source))
                if adopt:
                    source.unlink()  # an identical copy is already at the destination
                else:
                    _move_file(source, self.dest / desired)
            elif source.exists():
                raise OSError(f"Could not move recorded file {old_rel!r}: it is no longer a file.")
            else:
                # A missing source stays missing; an interrupted move can adopt its
                # identical destination without touching any unrelated file there.
                desired, _ = self.free_path(out_key, desired, previous["sha256"])
            self.state.move_file(old_rel, desired)

    @staticmethod
    def _same_entry(a: Path, b: Path) -> bool:
        # A name that differs only in case is the same folder on macOS and Windows.
        try:
            return a.samefile(b)
        except OSError:
            return False

    # -- per course ----------------------------------------------------
    def course_url(self, course: Course, page: str = "outline") -> str:
        return f"{self.config.base_url}/ultra/courses/{course.id}/{page}"

    def course_label(self, course: Course) -> str:
        return PurePosixPath(course.rel_dir).name

    def sync_course(self, course: Course) -> CourseReport:
        code, title = course_code_and_title(course.course_id, course.name)
        report = CourseReport(code=code, name=title, folder=course.rel_dir)
        self.deadline_content_ids = {}
        try:
            if not self.dry_run:
                (self.dest / course.rel_dir).mkdir(parents=True, exist_ok=True)
            roots = self.client.contents(course.id)
        except (ApiError, *ITEM_ERRORS) as exc:
            report.warnings.append(f"Could not read course content: {exc}")
        else:
            self.walk(course, roots, course.rel_dir, report)
        if not self.dry_run and self.refetch_keys is None and not self.missing_only:
            self.sync_deadlines(course, report)
        try:
            self.sync_announcements(course, report)
        except ITEM_ERRORS as exc:
            report.warnings.append(f"Could not sync announcements: {exc}")
        return report

    def sync_deadlines(self, course: Course, report: CourseReport) -> None:
        previous = self.state.deadline_courses.get(course.id, {})
        try:
            # Materialize all pages before replacing the cache: a failed second
            # page must not remove deadlines saved by an earlier sync.
            columns = self.client.grade_columns(course.id)
        except (ApiError, *ITEM_ERRORS) as exc:
            report.warnings.append(f"Could not read due dates: {exc}")
            entry = {**previous, "name": self.course_label(course), "unavailable": True}
        else:
            items = [parsed for column in columns if (parsed := column_deadline(
                column, course.id, self.config.base_url, self.deadline_content_ids)) is not None]
            entry = {"name": self.course_label(course), "items": items, "unavailable": False}
            old_data = {key: value for key, value in previous.items() if key != "updated_at"}
            entry["updated_at"] = (previous["updated_at"] if entry == old_data and previous.get("updated_at")
                                   else _now_iso())
        if entry != previous:
            self.state.deadline_courses[course.id] = entry
            self.state.dirty = True

    def walk(
        self,
        course: Course,
        items: list[dict],
        rel_dir: str,
        report: CourseReport,
        parent_title: str = "",
    ) -> None:
        for item in sorted(items, key=lambda i: i.get("position", 0)):
            column_id = (item.get("contentHandler") or {}).get("gradeColumnId")
            if column_id:
                self.deadline_content_ids[column_id] = item["id"]
            if self.is_folder(item):
                try:
                    sub_dir = self.folder_path(rel_dir, item.get("title") or "Folder", report.warnings)
                    if not self.dry_run:
                        (self.dest / sub_dir).mkdir(parents=True, exist_ok=True)
                    children = self.client.children(course.id, item["id"])
                except (ApiError, *ITEM_ERRORS) as exc:
                    report.warnings.append(f"Could not open folder {item.get('title')!r}: {exc}")
                    continue
                self.walk(course, children, sub_dir, report, item.get("title") or "")
            else:
                try:
                    self.process_item(course, item, rel_dir, report, parent_title)
                except (ApiError, *ITEM_ERRORS) as exc:
                    report.warnings.append(f"Skipped {item.get('title')!r}: {exc}")
                self.checkpoint()

    @staticmethod
    def is_folder(item: dict) -> bool:
        hid = handler_id(item)
        if hid in FOLDER_HANDLERS:
            return True
        return bool(item.get("hasChildren")) and hid not in LEAF_HANDLERS

    @staticmethod
    def is_ultra_body(item: dict) -> bool:
        return item.get("title") == ULTRA_BODY_TITLE and handler_id(item) == "resource/x-bb-document"

    def process_item(
        self, course: Course, item: dict, rel_dir: str, report: CourseReport, parent_title: str = ""
    ) -> None:
        key = f"content:{course.id}:{item['id']}"
        modified = item.get("modified")
        if self.refetch_keys is not None and not any(
            self.should_refetch(k) and not (self.dest / self.state.outputs[k]["path"]).exists()
            for k in self.state.items.get(key, {}).get("outputs", [])
        ):
            return
        # Bodies come fresh with every listing, so the signed file URLs in them are
        # still valid for the downloads below.
        # Ultra assignments and tests expose instructor instructions in the public
        # content listing, not in body or the attachment collection. Read only that
        # explicit field; assessment attempts, feedback and submissions are unrelated.
        instructions = body_text((item.get("contentHandler") or {}).get("instructions"))
        instruction_files = find_embedded_files(instructions)
        # The description is rendered in the note too, so files linked from it are saved.
        embedded_files = find_embedded_files(
            "\n".join((body_text(item.get("description")), body_text(item.get("body")), instructions))
        )
        embedded_keys = [self.embedded_key(course, item, e) for e in embedded_files]
        previous_item = self.state.items.get(key) or {}
        ultra_body = self.is_ultra_body(item)
        # The hidden Ultra child stands for its parent document.
        title = (parent_title if ultra_body and parent_title else item.get("title")) or "Untitled"
        if instruction_files:
            # Keep all of the item's files and its note together. Empty assessments
            # keep their note in the containing folder and create no extra folder.
            item_dir = self.folder_path(rel_dir, title, report.warnings)
            self.migrate_item_outputs(previous_item, rel_dir, item_dir)
            rel_dir = item_dir
        # A replaced file shows up as a new id even when "modified" stays put. Videos and
        # audio left as links have no output but count as handled.
        handled = set(previous_item.get("outputs", [])) | set(previous_item.get("media", []))
        if set(embedded_keys) <= handled and self.state.item_unchanged(
            key, modified, self.dest, self.refetch_missing, self.refetch_keys
        ):
            return
        if instruction_files and not self.dry_run:
            (self.dest / rel_dir).mkdir(parents=True, exist_ok=True)
        hid = handler_id(item)
        outputs: list[str] = []
        saved: list[str] = []
        media: list[tuple[str, str, str]] = []  # (key, name, link) of videos and audio not downloaded
        # After a partial failure the files that did arrive are not downloaded again
        # while the item is unchanged.
        kept = self.kept_attachments(previous_item, modified)
        failure: Exception | None = None

        if hid not in NO_ATTACHMENT_HANDLERS and not ultra_body:
            try:
                attachments = self.client.attachments(course.id, item["id"])
            except ApiError as exc:
                # Assignments, tests and tool links often have no attachment collection.
                no_attachments = exc.status in (400, 403, 404) and NO_ATTACHMENTS_MESSAGE in str(exc).lower()
                if hid == "resource/x-bb-file":
                    raise
                if not no_attachments:
                    # Independent instruction links can still be fetched, but a
                    # failed collection must warn and remain eligible for retry.
                    failure = exc
                attachments = []
            for att in attachments:
                out_key = f"attachment:{course.id}:{att['id']}"
                if out_key in kept:
                    outputs.append(out_key)
                    saved.append(PurePosixPath(self.state.outputs[out_key]["path"]).name)
                    continue
                name = sanitize_name(att.get("fileName") or att.get("name") or title, windows=self.windows)
                url = self.client.attachment_url(course.id, item["id"], att["id"])
                try:
                    rel = self.fetch_or_link(
                        media, out_key, att.get("fileName") or att.get("name") or title, att.get("mimeType"),
                        self.client.url(url), join_rel(rel_dir, name), url, report,
                    )
                except (ApiError, *ITEM_ERRORS) as exc:
                    # Keep going so the files that did arrive are recorded and not fetched
                    # again next run; only this attachment is retried.
                    failure = failure or exc
                    continue
                if rel is None:
                    continue
                outputs.append(out_key)
                saved.append(PurePosixPath(rel).name)

        stale = [k for k in previous_item.get("outputs", []) if k.startswith("xid:") and k not in embedded_keys]
        for embedded, out_key in zip(embedded_files, embedded_keys):
            if out_key in kept:
                outputs.append(out_key)
                saved.append(PurePosixPath(self.state.outputs[out_key]["path"]).name)
                continue
            name = sanitize_name(embedded.name, windows=self.windows) if embedded.name else ""
            desired = join_rel(rel_dir, name) if name else ""
            replaces = next(
                (k for k in stale if desired and (self.state.output(k) or {}).get("path") == desired),
                None,
            )
            try:
                rel = self.fetch_or_link(
                    media, out_key, embedded.name or title, embedded.mime, self.embedded_link(embedded),
                    desired, self.embedded_url(embedded), report, rel_dir, replaces=replaces,
                )
            except (ApiError, *ITEM_ERRORS) as exc:
                failure = failure or exc
                continue
            if rel is None:
                continue
            outputs.append(out_key)
            saved.append(PurePosixPath(rel).name)

        media_keys = [m[0] for m in media]
        if failure is not None:
            if not self.dry_run and self.refetch_keys is None:
                self.state.record_item(key, modified, outputs, title, partial=True, media=media_keys)
            raise failure

        if needs_note(item, bool(media)):
            note_item = {**item, "title": title} if title != item.get("title") else item
            note = render_item_note(
                note_item, self.course_label(course), self.course_url(course), saved,
                [(name, link) for _, name, link in media],
            )
            out_key = f"note:{course.id}:{item['id']}"
            self.write_note(out_key, join_rel(rel_dir, note_name(title, windows=self.windows)), note, report, "notes")
            outputs += [out_key, markdown_key(out_key)]

        if not self.dry_run and self.refetch_keys is None:
            self.state.record_item(key, modified, outputs, title, media=media_keys)

    def kept_attachments(self, previous_item: dict, modified: str | None) -> Container[str]:
        """The files of this item that are on disk from an earlier run and need no download.

        That is the files of an item that partly failed and has not changed since,
        and, for an item with no record at all, every recorded file: a run that was
        killed mid-item saved those files but never the item. A replaced file gets
        a new id, so a recorded id with its file on disk is the same file.
        """
        if self.dry_run or modified is None:
            return set()
        if previous_item:
            if not previous_item.get("partial") or previous_item.get("modified") != modified:
                return set()
            return {k for k in previous_item.get("outputs", []) if self.on_disk(k)}
        return _OnDisk(self.on_disk)

    def on_disk(self, out_key: str) -> bool:
        out = self.state.output(out_key)
        return bool(out_key.startswith(("attachment:", "xid:")) and out and (self.dest / out["path"]).exists())

    @staticmethod
    def embedded_key(course: Course, item: dict, embedded) -> str:
        return f"xid:{course.id}:{item['id']}:{embedded.xid}"

    @staticmethod
    def embedded_url(embedded) -> str:
        # Older bodies hold placeholders instead of a real host; rebuild the plain URL
        # unless the link carries Ultra's own path and signed query, or refers
        # to a session upload that has no content-collection URL.
        if embedded.xid.startswith("upload-") or ("?" in embedded.url and "/pid-" in embedded.url):
            return embedded.url
        return f"/bbcswebdav/xid-{embedded.xid}"

    def embedded_link(self, embedded) -> str:
        """Where a student opens an embedded file in Blackboard (not the short-lived signed URL)."""
        return self.client.url(embedded.url if embedded.xid.startswith("upload-") else f"/bbcswebdav/xid-{embedded.xid}")

    def sync_announcements(self, course: Course, report: CourseReport) -> None:
        try:
            announcements = self.client.announcements(course.id)
        except ApiError as exc:
            report.warnings.append(f"Could not read announcements: {exc}")
            return
        folder = join_rel(course.rel_dir, sanitize_name(self.config.announcements_folder, windows=self.windows))
        for ann in announcements:
            if ann.get("draft"):
                continue
            key = f"announcement:{course.id}:{ann['id']}"
            out_key = f"announcement-note:{course.id}:{ann['id']}"
            # Backfill older states even when the note itself is unchanged.
            if not self.dry_run:
                code, title = course_code_and_title(course.course_id, course.name)
                self.state.record_announcement(key, announcement_metadata(
                    ann, course.id, f"{code} {title}".strip(),
                    f"/ultra/courses/{course.id}/announcements", out_key,
                ))
            previous_item = self.state.items.get(key) or {}
            if self.refetch_keys is not None and not any(
                self.should_refetch(k)
                for k in [out_key, *(k for k in previous_item.get("outputs", []) if k.startswith("xid:"))]
            ):
                continue
            modified = ann.get("modified")
            # Announcement ids live apart from content ids, so keep their file keys apart too.
            embedded_files = find_embedded_files(body_text(ann.get("body")))
            embedded_keys = [self.embedded_key(course, {"id": f"announcement:{ann['id']}"}, e) for e in embedded_files]
            handled = set(previous_item.get("outputs", [])) | set(previous_item.get("media", []))
            if set(embedded_keys) <= handled and self.state.item_unchanged(
                key, modified, self.dest, self.refetch_missing, self.refetch_keys
            ):
                continue
            title = ann.get("title") or "Announcement"
            date = announcement_date(ann)
            name = note_name(f"{date} {title}" if date else title, windows=self.windows)
            outputs: list[str] = []
            saved: list[str] = []
            media: list[tuple[str, str, str]] = []
            kept = self.kept_attachments(previous_item, modified)
            failure: Exception | None = None
            if embedded_files and not self.dry_run:
                (self.dest / folder).mkdir(parents=True, exist_ok=True)
            for embedded, file_key in zip(embedded_files, embedded_keys):
                if file_key in kept:
                    outputs.append(file_key)
                    saved.append(PurePosixPath(self.state.outputs[file_key]["path"]).name)
                    continue
                file_name = sanitize_name(embedded.name, windows=self.windows) if embedded.name else ""
                try:
                    rel = self.fetch_or_link(
                        media, file_key, embedded.name or title, embedded.mime, self.embedded_link(embedded),
                        join_rel(folder, file_name) if file_name else "", self.embedded_url(embedded),
                        report, folder,
                    )
                except (ApiError, *ITEM_ERRORS) as exc:
                    # The announcement text matters more than one missing file: write the
                    # note anyway and retry only the failed file next run.
                    failure = failure or exc
                    continue
                if rel is None:
                    continue
                outputs.append(file_key)
                saved.append(PurePosixPath(rel).name)
            if failure is not None:
                report.warnings.append(f"Could not download a file in announcement {title!r}: {failure}")
            note = render_announcement_note(
                ann, self.course_label(course), self.course_url(course, "announcements"), saved,
                [(name, link) for _, name, link in media],
            )
            try:
                self.write_note(out_key, join_rel(folder, name), note, report, "announcements")
            except OSError as exc:
                report.warnings.append(f"Skipped announcement {title!r}: {exc}")
                continue
            outputs += [out_key, markdown_key(out_key)]
            if not self.dry_run and self.refetch_keys is None:
                self.state.record_item(
                    key, modified, outputs, title, partial=failure is not None, media=[m[0] for m in media]
                )
                self.checkpoint()

    # -- writing files -------------------------------------------------
    def fetch_or_link(
        self,
        media: list[tuple[str, str, str]],
        out_key: str,
        name: str,
        mime: str | None,
        link: str,
        desired_rel: str,
        url: str,
        report: CourseReport,
        fallback_dir: str = "",
        replaces: str | None = None,
    ) -> str | None:
        """``fetch_file``, except that a video or audio file is never downloaded.

        The type is judged from what the listing says (*mime*, *name*) before any request,
        and again from the response headers inside ``BlackboardClient.download``. Such a
        file is added to *media* as (key, name, link) and None is returned. A copy saved by
        an older version stays where it is and is returned as before.
        """
        try:
            if self.state.output(out_key) is None and is_media(mime, name, PurePosixPath(desired_rel).name):
                raise SkippedMedia(url, name, mime or "")
            return self.fetch_file(out_key, desired_rel, url, report, fallback_dir, replaces=replaces)
        except SkippedMedia as skipped:
            previous = self.state.output(out_key)
            if previous:
                return previous["path"]
            media.append((out_key, skipped.name or name, link))
            return None

    def fetch_file(
        self,
        out_key: str,
        desired_rel: str,
        url: str,
        report: CourseReport,
        fallback_dir: str = "",
        replaces: str | None = None,
    ) -> str:
        """Download one file unless it is already mirrored; return its local path."""
        if replaces and self.refetch_keys is None and not self.dry_run and self.state.output(out_key) is None:
            self.state.move_output(replaces, out_key)
        previous = self.state.output(out_key)
        if self.skip_output(out_key):
            return previous["path"] if previous else desired_rel
        if self.dry_run:
            if previous:
                if self.missing_only:
                    report.new_files.append(previous["path"])
                return previous["path"]
            rel = desired_rel or join_rel(fallback_dir, out_key.rsplit(":", 1)[-1])
            report.new_files.append(rel)
            return rel
        target_dir = self.dest / (PurePosixPath(desired_rel).parent if desired_rel else fallback_dir)
        expected = PurePosixPath(desired_rel).name if desired_rel else ""
        known = None
        if previous and (previous.get("etag") or previous.get("last_modified")):
            # A recorded copy that is gone from disk must be fetched again when asked to.
            if (self.dest / previous["path"]).exists() or not self.should_refetch(out_key):
                known = previous
        download = self.client.download(url, target_dir, expected_name=expected, known=known)
        if download.unchanged:
            return previous["path"]
        try:
            if not desired_rel:
                name = sanitize_name(download.filename or out_key.rsplit(":", 1)[-1], windows=self.windows)
                desired_rel = join_rel(fallback_dir, name)
            outcome, rel = self.place(out_key, desired_rel, download.path, download.sha256, download.size)
            self.state.set_validators(out_key, download.etag, download.last_modified)
        finally:
            if download.path.exists():
                download.path.unlink()
        # A long item may be cut off after this file; the next run then skips it.
        self.checkpoint()
        if outcome == "new" or (self.missing_only and outcome == "updated"):
            report.new_files.append(rel)
        elif outcome == "updated":
            report.updated_files.append(rel)
        return rel

    def write_note(
        self, out_key: str, desired_rel: str, text: str, report: CourseReport, kind: str
    ) -> str:
        """Save a note as a PDF and a hidden Markdown copy beside it; return the PDF's path.

        The Markdown text is the note's source: the PDF is drawn from it, and it is
        kept (hidden, see ``markdown_twin``) for features that read notes. Only the
        PDF counts in the report. A note an older version saved as a visible ``.md``
        is hidden the first time it is written again, never deleted.
        """
        md_key = markdown_key(out_key)
        if not self.dry_run:
            self.hide_legacy_note(out_key, md_key)
        rel = self.write_output(out_key, desired_rel, lambda: render_pdf(text), report, kind)
        self.write_output(md_key, markdown_twin(rel), lambda: text.encode("utf-8"), None, kind, hidden=True)
        return rel

    def hide_legacy_note(self, out_key: str, md_key: str) -> None:
        """Turn the visible "Name.md" an older version recorded as ``out_key`` into the hidden copy.

        The file is renamed to ".Name.md" and its record moves to ``md_key``, so the
        PDF is written as a new file and the in-place update applies to the copy.
        """
        previous = self.state.output(out_key)
        if not previous or not previous["path"].endswith(".md") or self.state.output(md_key):
            return
        # Without a PDF to take its place the old note stays as it is: one the student
        # removed from the list, or one not chosen in a restore of deleted files.
        if previous.get("dismissed") or (self.refetch_keys is not None and out_key not in self.refetch_keys):
            return
        old_rel = previous["path"]
        hidden = markdown_twin(old_rel)
        source = self.dest / old_rel
        if source.is_file():
            hidden, adopt = self.free_path(md_key, hidden, sha256_file(source))
            if adopt:
                source.unlink()  # an identical hidden copy is already there
            else:
                os.rename(source, self.dest / hidden)
                set_hidden(self.dest / hidden, True)
        self.state.move_output(out_key, md_key)
        self.state.move_file(old_rel, hidden)
        if self.refetch_keys is not None and out_key in self.refetch_keys:
            self.refetch_keys.add(md_key)  # restoring the note restores both files

    def write_output(
        self,
        out_key: str,
        desired_rel: str,
        render,
        report: CourseReport | None,
        kind: str,
        hidden: bool = False,
    ) -> str:
        """Write generated content (``render()`` gives its bytes) as ``out_key``; return its path.

        Unlike downloads, a changed note replaces the recorded file in place. With
        ``report`` None nothing is reported; ``hidden`` hides the file on Windows.
        """
        if self.skip_output(out_key):
            previous = self.state.output(out_key)
            return previous["path"] if previous else desired_rel
        data = render()
        sha = hashlib.sha256(data).hexdigest()
        previous = self.state.output(out_key)
        if self.dry_run:
            if previous and PurePosixPath(previous["path"]).suffix != PurePosixPath(desired_rel).suffix:
                previous = None  # an older version's Markdown note, not this PDF
            if report is not None:
                if previous is None or self.missing_only:
                    getattr(report, f"new_{kind}").append(previous["path"] if previous else desired_rel)
                elif previous["sha256"] != sha:
                    getattr(report, f"updated_{kind}").append(previous["path"])
            return previous["path"] if previous else desired_rel
        target_dir = self.dest / PurePosixPath(desired_rel).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=PARTIAL_PREFIX, suffix=PARTIAL_SUFFIX, dir=target_dir)
        set_hidden(Path(tmp), True)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        tmp_path = Path(tmp)
        try:
            outcome, rel = self.place(
                out_key, desired_rel, tmp_path, sha, len(data), replace_in_place=True, hidden=hidden
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        if report is not None:
            if outcome == "new" or (self.missing_only and outcome == "updated"):
                getattr(report, f"new_{kind}").append(rel)
            elif outcome == "updated":
                getattr(report, f"updated_{kind}").append(rel)
        return rel

    def place(
        self,
        out_key: str,
        desired_rel: str,
        tmp: Path,
        sha: str,
        size: int,
        replace_in_place: bool = False,
        hidden: bool = False,
    ) -> tuple[str, str]:
        """Move a freshly fetched file into place without ever clobbering local work.

        Returns (outcome, relative path) with outcome "new", "updated" or "unchanged".
        * Same content as last time: nothing is written.
        * Changed on Blackboard and our copy is untouched: our copy is replaced.
        * Changed on Blackboard but the student edited/removed our copy: the new
          version is saved beside it as "name (2).ext"; nothing is deleted.
          With replace_in_place (notes) the new version instead replaces the
          recorded path, or recreates it there if it was deleted.
        * An identical file already sitting at the target is adopted as-is.
        ``hidden`` keeps the placed file hidden on Windows (the Markdown copy of a note).
        """
        if self.windows:
            desired_rel = fit_windows_path(self.dest, desired_rel)
        previous = self.state.output(out_key)
        if previous:
            prev_abs = self.dest / previous["path"]
            if previous["sha256"] == sha:
                if not prev_abs.exists() and self.should_refetch(out_key):
                    self._move_into(tmp, prev_abs, hidden)
                    return "new", previous["path"]
                return "unchanged", previous["path"]
            if prev_abs.is_file() and sha256_file(prev_abs) == previous["sha256"]:
                self._move_into(tmp, prev_abs, hidden)
                self.state.record_output(out_key, previous["path"], sha, size)
                return "updated", previous["path"]
            if replace_in_place and not prev_abs.is_dir():
                self._move_into(tmp, prev_abs, hidden)
                self.state.record_output(out_key, previous["path"], sha, size)
                return "updated", previous["path"]
            rel, adopt = self.free_path(out_key, desired_rel, sha)
            if not adopt:
                self._move_into(tmp, self.dest / rel, hidden)
            self.state.record_output(out_key, rel, sha, size)
            return "updated", rel

        rel, adopt = self.free_path(out_key, desired_rel, sha)
        if not adopt:
            self._move_into(tmp, self.dest / rel, hidden)
        self.state.record_output(out_key, rel, sha, size)
        return ("unchanged" if adopt else "new"), rel

    def free_path(self, out_key: str, desired_rel: str, sha: str) -> tuple[str, bool]:
        """First "name", "name (2)", ... that is free; (path, adopt-existing-identical)."""
        n = 1
        candidate = desired_rel
        while True:
            owner = self.state.owner_of(candidate)
            target = self.dest / candidate
            if owner is None or owner == out_key:
                if not target.exists():
                    return candidate, False
                if owner is None and target.is_file() and sha256_file(target) == sha:
                    return candidate, True
            n += 1
            candidate = numbered_variant(desired_rel, n, windows=self.windows)

    @staticmethod
    def _move_into(tmp: Path, target: Path, hidden: bool = False) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        set_hidden(tmp, hidden)  # the attribute follows the file to its final name
        os.replace(tmp, target)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_sync(
    config: Config,
    client: BlackboardClient,
    term_name: str | None = None,
    all_terms: bool = False,
    course_filters: list[str] | None = None,
    dry_run: bool = False,
    refetch_missing: bool = False,
    user_id: str | None = None,
    now: datetime | None = None,
    refetch_keys: set[str] | None = None,
    lock_held: bool = False,
) -> SyncReport:
    """Sync current courses, or download one named past term's missing files.

    ``lock_held`` says the caller holds ``run_lock``, so no other sync is running and
    every ``.bbsync-*.partial`` file in the destination is left over from a run that
    was killed. Without it only the old ones are removed.
    """
    if term_name is not None and (not term_name.strip() or all_terms or refetch_keys is not None):
        raise BlackboardSyncError("İndirilecek tek bir eski dönem adı belirtin.")
    report = SyncReport(started_at=_now_iso(), dry_run=dry_run, dest=str(config.root), past_term=term_name or "")
    state = State.load(config.state_file, backup=not dry_run)
    if state.recovery:
        report.warnings.append(state.recovery)
    if not dry_run:
        remove_stale_partials(config.root, max_age=timedelta(0) if lock_held else STALE_PARTIAL_AGE)
    selected: set[str] = set()
    if refetch_keys is not None:
        from blackboard_sync.deleted import missing_outputs
        selected = refetch_keys & {row.key for row in missing_outputs(state, config.root)}
        # A restored note brings back its hidden Markdown copy too, if that is gone.
        refetch_keys = selected | {markdown_key(k) for k in selected if markdown_key(k) in state.outputs}
        all_terms = True
        term_name = None
        course_filters = sorted({key.split(":")[1] for key in refetch_keys})
        if not refetch_keys:
            report.message = "Seçilen dosyalar zaten mevcut veya listeden kaldırılmış."
            report.finished_at = _now_iso()
            return report
    syncer = Syncer(client, config, state, dry_run=dry_run,
                    refetch_missing=refetch_missing or bool(term_name), refetch_keys=refetch_keys,
                    missing_only=bool(term_name))
    me = client.me()  # also the cheapest way to prove the session still works
    user_id = me.get("id") or user_id
    if not user_id:
        raise LoginRequired("Blackboard did not identify the signed-in user.")
    terms, courses = syncer.discover(
        user_id,
        term_name=term_name,
        all_terms=all_terms,
        course_filters=course_filters,
        now=now,
        warnings=report.warnings,
    )
    if not term_name and not all_terms:
        # An archived term stays frozen even if older memberships later become
        # the fallback of choose_current_terms (e.g. current courses disappear).
        courses = [c for c in courses if c.term_id not in state.past_terms]
        terms = [t for t in terms if t.id not in state.past_terms]
    report.terms = [t.name for t in terms]
    if not dry_run and not term_name and not all_terms and not course_filters:
        current_ids = {c.id for c in courses}
        active = {key: value for key, value in state.deadline_courses.items() if key in current_ids}
        if active != state.deadline_courses:
            state.deadline_courses = active
            state.dirty = True
    if term_name:
        report.past_term = terms[0].name
        if not dry_run:
            state.record_past_term(terms[0].id, terms[0].name, [c.id for c in courses])
    if not dry_run:
        state.record_current_courses(syncer.current_course_ids)
    for course in courses:
        syncer.migrate_course_folder(course, report.warnings)
    if not dry_run:
        state.checkpoint(force=True)  # a renamed folder must never be left with stale recorded paths
    if not courses:
        report.warnings.append("No courses found for the selected term.")
    try:
        for course in courses:
            log.info("Syncing %s", course.rel_dir)
            report.courses.append(syncer.sync_course(course))
            syncer.checkpoint_now()  # keep progress even if a later course fails
    finally:
        syncer.checkpoint_now()
        if state.save_error:
            report.warnings.append(
                f"Could not save progress to {state.path.name} ({state.save_error}); "
                "files downloaded in this run may be fetched again next time."
            )
        report.finished_at = _now_iso()
    if refetch_keys is not None:
        remaining = sum(not (config.root / state.outputs[key]["path"]).exists() for key in selected)
        report.message = f"{len(selected) - remaining} dosya indirildi."
        if remaining:
            report.message += f" {remaining} dosya indirilemedi; listede tutuldu."
    return report
