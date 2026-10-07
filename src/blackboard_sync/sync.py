"""Discover the current term's courses and mirror their content locally."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import requests

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.errors import AlreadyRunning, ApiError, LoginRequired
from blackboard_sync.htmltext import body_text, find_embedded_files
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
    fit_windows_path,
    join_rel,
    note_name,
    numbered_variant,
    sanitize_name,
)
from blackboard_sync.report import CourseReport, SyncReport
from blackboard_sync.state import State
from blackboard_sync.system import is_windows, try_lock

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


class Syncer:
    def __init__(
        self,
        client: BlackboardClient,
        config: Config,
        state: State,
        dry_run: bool = False,
        refetch_missing: bool = False,
        windows: bool | None = None,
    ):
        self.client = client
        self.config = config
        self.state = state
        self.dest = config.dest
        self.dry_run = dry_run
        self.refetch_missing = refetch_missing
        self.windows = is_windows() if windows is None else windows

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

        if all_terms:
            selected = list(terms.values())
        elif term_name:
            wanted = term_name.casefold()
            selected = [t for t in terms.values() if t.name.casefold() == wanted]
            if not selected:
                known = ", ".join(sorted(t.name for t in terms.values()))
                warnings.append(f"No term named {term_name!r}. Known terms: {known}")
        else:
            selected = choose_current_terms(list(terms.values()), now)

        courses: list[Course] = []
        filters = {f.casefold() for f in course_filters or []}
        for term in selected:
            used: set[str] = set()
            term_dir = sanitize_name(term.name, windows=self.windows)
            for course in sorted(term.courses, key=lambda c: (c.code, c.course_id)):
                if filters and not filters & {
                    course.code.casefold(),
                    course.course_id.casefold(),
                    course.id.casefold(),
                }:
                    continue
                folder = course_folder_name(course.course_id, course.name, windows=self.windows)
                if folder.casefold() in used:
                    folder = sanitize_name(f"{folder} ({course.course_id or course.id})", windows=self.windows)
                used.add(folder.casefold())
                course.rel_dir = join_rel(term_dir, folder)
                courses.append(course)
        return selected, courses

    # -- per course ----------------------------------------------------
    def course_url(self, course: Course, page: str = "outline") -> str:
        return f"{self.config.base_url}/ultra/courses/{course.id}/{page}"

    def course_label(self, course: Course) -> str:
        return PurePosixPath(course.rel_dir).name

    def sync_course(self, course: Course) -> CourseReport:
        code, title = course_code_and_title(course.course_id, course.name)
        report = CourseReport(code=code, name=title, folder=course.rel_dir)
        try:
            if not self.dry_run:
                (self.dest / course.rel_dir).mkdir(parents=True, exist_ok=True)
            roots = self.client.contents(course.id)
        except (ApiError, *ITEM_ERRORS) as exc:
            report.warnings.append(f"Could not read course content: {exc}")
        else:
            self.walk(course, roots, course.rel_dir, report)
        try:
            self.sync_announcements(course, report)
        except ITEM_ERRORS as exc:
            report.warnings.append(f"Could not sync announcements: {exc}")
        return report

    def walk(
        self,
        course: Course,
        items: list[dict],
        rel_dir: str,
        report: CourseReport,
        parent_title: str = "",
    ) -> None:
        for item in sorted(items, key=lambda i: i.get("position", 0)):
            if self.is_folder(item):
                sub_dir = join_rel(rel_dir, sanitize_name(item.get("title") or "Folder", windows=self.windows))
                try:
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
        # Bodies come fresh with every listing, so the signed file URLs in them are
        # still valid for the downloads below.
        embedded_files = find_embedded_files(body_text(item.get("body")))
        embedded_keys = [self.embedded_key(course, item, e) for e in embedded_files]
        previous_item = self.state.items.get(key) or {}
        # A replaced file shows up as a new id even when "modified" stays put.
        if set(embedded_keys) <= set(previous_item.get("outputs", [])) and self.state.item_unchanged(
            key, modified, self.dest, self.refetch_missing
        ):
            return
        ultra_body = self.is_ultra_body(item)
        # The hidden Ultra child stands for its parent document.
        title = (parent_title if ultra_body and parent_title else item.get("title")) or "Untitled"
        hid = handler_id(item)
        outputs: list[str] = []
        saved: list[str] = []

        if hid not in NO_ATTACHMENT_HANDLERS and not ultra_body:
            try:
                attachments = self.client.attachments(course.id, item["id"])
            except ApiError as exc:
                # Assignments, tests and tool links often have no attachment collection.
                no_attachments = exc.status in (403, 404) or (
                    exc.status == 400 and NO_ATTACHMENTS_MESSAGE in str(exc)
                )
                if hid == "resource/x-bb-file" or not no_attachments:
                    raise
                attachments = []
            for att in attachments:
                out_key = f"attachment:{course.id}:{att['id']}"
                name = sanitize_name(att.get("fileName") or att.get("name") or title, windows=self.windows)
                url = self.client.attachment_url(course.id, item["id"], att["id"])
                rel = self.fetch_file(out_key, join_rel(rel_dir, name), url, report)
                outputs.append(out_key)
                saved.append(PurePosixPath(rel).name)

        stale = [k for k in previous_item.get("outputs", []) if k.startswith("xid:") and k not in embedded_keys]
        for embedded, out_key in zip(embedded_files, embedded_keys):
            name = sanitize_name(embedded.name, windows=self.windows) if embedded.name else ""
            desired = join_rel(rel_dir, name) if name else ""
            replaces = next(
                (k for k in stale if desired and (self.state.output(k) or {}).get("path") == desired),
                None,
            )
            rel = self.fetch_file(
                out_key, desired, self.embedded_url(embedded), report, rel_dir, replaces=replaces
            )
            outputs.append(out_key)
            saved.append(PurePosixPath(rel).name)

        if needs_note(item):
            note_item = {**item, "title": title} if title != item.get("title") else item
            note = render_item_note(note_item, self.course_label(course), self.course_url(course), saved)
            out_key = f"note:{course.id}:{item['id']}"
            self.write_note(out_key, join_rel(rel_dir, note_name(title, windows=self.windows)), note, report, "notes")
            outputs.append(out_key)

        if not self.dry_run:
            self.state.record_item(key, modified, outputs, title)

    @staticmethod
    def embedded_key(course: Course, item: dict, embedded) -> str:
        return f"xid:{course.id}:{item['id']}:{embedded.xid}"

    @staticmethod
    def embedded_url(embedded) -> str:
        # Older bodies hold placeholders instead of a real host; rebuild the plain URL
        # unless the link carries Ultra's own path and signed query.
        if "?" in embedded.url and "/pid-" in embedded.url:
            return embedded.url
        return f"/bbcswebdav/xid-{embedded.xid}"

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
            modified = ann.get("modified")
            if self.state.item_unchanged(key, modified, self.dest, self.refetch_missing):
                continue
            title = ann.get("title") or "Announcement"
            date = announcement_date(ann)
            name = note_name(f"{date} {title}" if date else title, windows=self.windows)
            note = render_announcement_note(
                ann, self.course_label(course), self.course_url(course, "announcements")
            )
            out_key = f"announcement-note:{course.id}:{ann['id']}"
            try:
                self.write_note(out_key, join_rel(folder, name), note, report, "announcements")
            except OSError as exc:
                report.warnings.append(f"Skipped announcement {title!r}: {exc}")
                continue
            if not self.dry_run:
                self.state.record_item(key, modified, [out_key], title)

    # -- writing files -------------------------------------------------
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
        if replaces and not self.dry_run and self.state.output(out_key) is None:
            self.state.move_output(replaces, out_key)
        previous = self.state.output(out_key)
        if self.dry_run:
            if previous:
                return previous["path"]
            rel = desired_rel or join_rel(fallback_dir, out_key.rsplit(":", 1)[-1])
            report.new_files.append(rel)
            return rel
        target_dir = self.dest / (PurePosixPath(desired_rel).parent if desired_rel else fallback_dir)
        expected = PurePosixPath(desired_rel).name if desired_rel else ""
        download = self.client.download(url, target_dir, expected_name=expected)
        try:
            if not desired_rel:
                name = sanitize_name(download.filename or out_key.rsplit(":", 1)[-1], windows=self.windows)
                desired_rel = join_rel(fallback_dir, name)
            outcome, rel = self.place(out_key, desired_rel, download.path, download.sha256, download.size)
        finally:
            if download.path.exists():
                download.path.unlink()
        if outcome == "new":
            report.new_files.append(rel)
        elif outcome == "updated":
            report.updated_files.append(rel)
        return rel

    def write_note(
        self, out_key: str, desired_rel: str, text: str, report: CourseReport, kind: str
    ) -> str:
        new_list = getattr(report, f"new_{kind}")
        updated_list = getattr(report, f"updated_{kind}")
        data = text.encode("utf-8")
        sha = hashlib.sha256(data).hexdigest()
        previous = self.state.output(out_key)
        if self.dry_run:
            if previous is None:
                new_list.append(desired_rel)
            elif previous["sha256"] != sha:
                updated_list.append(previous["path"])
            return previous["path"] if previous else desired_rel
        target_dir = self.dest / PurePosixPath(desired_rel).parent
        target_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".bbsync-", suffix=".partial", dir=target_dir)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        tmp_path = Path(tmp)
        try:
            outcome, rel = self.place(out_key, desired_rel, tmp_path, sha, len(data))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        if outcome == "new":
            new_list.append(rel)
        elif outcome == "updated":
            updated_list.append(rel)
        return rel

    def place(self, out_key: str, desired_rel: str, tmp: Path, sha: str, size: int) -> tuple[str, str]:
        """Move a freshly fetched file into place without ever clobbering local work.

        Returns (outcome, relative path) with outcome "new", "updated" or "unchanged".
        * Same content as last time: nothing is written.
        * Changed on Blackboard and our copy is untouched: our copy is replaced.
        * Changed on Blackboard but the student edited/removed our copy: the new
          version is saved beside it as "name (2).ext"; nothing is deleted.
        * An identical file already sitting at the target is adopted as-is.
        """
        if self.windows:
            desired_rel = fit_windows_path(self.dest, desired_rel)
        previous = self.state.output(out_key)
        if previous:
            prev_abs = self.dest / previous["path"]
            if previous["sha256"] == sha:
                if not prev_abs.exists() and self.refetch_missing:
                    self._move_into(tmp, prev_abs)
                    return "new", previous["path"]
                return "unchanged", previous["path"]
            if prev_abs.is_file() and sha256_file(prev_abs) == previous["sha256"]:
                self._move_into(tmp, prev_abs)
                self.state.record_output(out_key, previous["path"], sha, size)
                return "updated", previous["path"]
            rel, adopt = self.free_path(out_key, desired_rel, sha)
            if not adopt:
                self._move_into(tmp, self.dest / rel)
            self.state.record_output(out_key, rel, sha, size)
            return "updated", rel

        rel, adopt = self.free_path(out_key, desired_rel, sha)
        if not adopt:
            self._move_into(tmp, self.dest / rel)
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
    def _move_into(tmp: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
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
) -> SyncReport:
    """One complete sync pass. Raises LoginRequired when the session is gone."""
    report = SyncReport(started_at=_now_iso(), dry_run=dry_run, dest=str(config.dest))
    state = State.load(config.state_file)
    syncer = Syncer(client, config, state, dry_run=dry_run, refetch_missing=refetch_missing)
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
    report.terms = [t.name for t in terms]
    if not courses:
        report.warnings.append("No courses found for the selected term.")
    try:
        for course in courses:
            log.info("Syncing %s", course.rel_dir)
            report.courses.append(syncer.sync_course(course))
            if not dry_run:
                state.save()  # keep progress even if a later course fails
    finally:
        if not dry_run:
            state.save()
        report.finished_at = _now_iso()
    return report
