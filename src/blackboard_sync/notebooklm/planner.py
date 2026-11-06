"""Which files go to NotebookLM: the courses as the last sync left them, then a plan per course.

The files come from what the sync recorded (``State.outputs``), never from walking the folder,
so a student's own files in a course folder stay private. Only the current-term courses that
are ticked in Dersler count. A note's hidden ``.md`` twin would be the same text twice, and
announcements would use up the per-notebook source limit, so neither is ever a candidate.

Everything here is pure local work: no network and no writes.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from blackboard_sync.notebooklm import store
from blackboard_sync.state import State

UPLOAD = "upload"
ADOPT = "adopt"  # already in the notebook (the state was lost): record it, do not add it again
UNCHANGED = "unchanged"
TOUCHED = "touched"
MODIFIED = "modified"  # changed since it was added: reported, never replaced

READY = "ready"
BLOCKED = "blocked-limit"
AMBIGUOUS = "ambiguous-notebook"
EMPTY = "empty"

SUPPORTED_EXT = frozenset({".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".epub"})
IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".tif"})
MAX_FILE_BYTES = 200 * 1024 * 1024  # NotebookLM's limit per source
# Output kinds (the part of ``State.outputs`` keys before the first ":") that are never sources.
NOT_SOURCES = frozenset({"note-md", "announcement-note", "announcement-note-md"})


def nfc(text: str) -> str:
    """macOS can hand back decomposed names; titles and state keys are composed."""
    return unicodedata.normalize("NFC", text)


@dataclass(frozen=True)
class FileInfo:
    rel: str  # relative to the course folder, the source's title
    path: Path
    size: int
    mtime_ns: int
    skip_reason: str = ""


@dataclass
class CourseScan:
    folder: str  # relative to the University folder; the state's key
    title: str  # the notebook's
    files: list[FileInfo] = field(default_factory=list)

    @property
    def uploadable(self) -> list[FileInfo]:
        return [f for f in self.files if not f.skip_reason]

    @property
    def skipped(self) -> list[FileInfo]:
        return [f for f in self.files if f.skip_reason]


def skip_reason(ext: str, size: int, include_images: bool = False) -> str:
    """Why a file cannot be a source; "" when it can."""
    if size == 0:
        return "empty file"
    if size > MAX_FILE_BYTES:
        return "over the 200 MB limit"
    if ext in SUPPORTED_EXT or (include_images and ext in IMAGE_EXT):
        return ""
    return "image" if ext in IMAGE_EXT else "unsupported format"


def notebook_titles(folders: list[str]) -> dict[str, str]:
    """Each course folder's notebook title: its name, with the term when two terms share that name."""
    names = Counter(PurePosixPath(folder).name for folder in folders)
    titles = {}
    for folder in folders:
        path = PurePosixPath(folder)
        titles[folder] = nfc(path.name if names[path.name] == 1 else f"{path.name} ({path.parent.name})")
    return titles


def scan_courses(state: State, root: Path, disabled: set[str] = frozenset(),
                 include_images: bool = False) -> list[CourseScan]:
    """The current courses and their synced files, by folder."""
    folders = sorted({course["folder"] for course_id, course in state.courses.items()
                      if course_id not in disabled and course.get("folder")})
    titles = notebook_titles(folders)
    scans = {folder: CourseScan(folder, titles[folder]) for folder in folders}
    for key, entry in state.outputs.items():
        if key.split(":")[0] in NOT_SOURCES:
            continue
        output = PurePosixPath(entry.get("path") or "")
        course = next((output.parents[index].as_posix() for index in range(len(output.parents))
                       if output.parents[index].as_posix() in scans), None)
        if course is None:
            continue
        rel = nfc(output.relative_to(course).as_posix())
        path = root / output
        try:
            info = path.stat()
        except OSError:
            scans[course].files.append(FileInfo(rel, path, 0, 0, "missing"))
            continue
        scans[course].files.append(FileInfo(rel, path, info.st_size, info.st_mtime_ns,
                                            skip_reason(path.suffix.lower(), info.st_size, include_images)))
    for scan in scans.values():
        scan.files.sort(key=lambda f: f.rel)
    return list(scans.values())


def has_new_files(course: CourseScan, state: store.UploadState) -> bool:
    """Whether the course has a file that was never added; an automatic run needs no network otherwise."""
    return any(state.get_file(course.folder, f.rel) is None for f in course.uploadable)


@dataclass
class FileAction:
    file: FileInfo
    action: str
    sha256: str | None = None
    source_id: str | None = None  # for ADOPT


@dataclass
class CoursePlan:
    course: CourseScan
    status: str
    notebook_id: str | None
    actions: list[FileAction] = field(default_factory=list)
    remote_count: int = 0
    limit: int = 50

    @property
    def uploads(self) -> list[FileAction]:
        return [a for a in self.actions if a.action == UPLOAD]

    @property
    def overflow(self) -> int:
        return max(0, self.remote_count + len(self.uploads) - self.limit)


def plan_course(course: CourseScan, state: store.UploadState, *, matches: list, sources: list | None,
                limit: int) -> CoursePlan:
    """What to do with one course, given the notebooks titled like it and the sources of the one found.

    The "stop, don't truncate" rule: when what is there plus what is new exceeds the account's
    limit, nothing is added to that notebook, rather than an arbitrary part of the course.
    """
    if not course.uploadable:
        return CoursePlan(course, EMPTY, None, limit=limit)
    if len(matches) > 1:
        return CoursePlan(course, AMBIGUOUS, None, limit=limit)
    notebook_id = matches[0].id if matches else None
    sources = sources or []
    remote = {source.title: source for source in sources}
    plan = CoursePlan(course, READY, notebook_id, remote_count=len(sources), limit=limit)
    for info in course.uploadable:
        entry = state.get_file(course.folder, info.rel)
        if entry and entry.get("notebook_id") != notebook_id:
            entry = None  # recorded against another notebook: not in this one
        verdict, digest = store.classify(entry, info.size, info.mtime_ns,
                                         lambda info=info: store.sha256_file(info.path))
        if verdict == store.UNCHANGED:
            plan.actions.append(FileAction(info, UNCHANGED))
        elif verdict == store.TOUCHED:
            plan.actions.append(FileAction(info, TOUCHED, digest))
        elif verdict == store.MODIFIED:
            plan.actions.append(FileAction(info, MODIFIED, digest))
        else:
            existing = remote.get(info.rel)
            if existing is not None and existing.status != "error":
                plan.actions.append(FileAction(info, ADOPT, source_id=existing.id))
            else:  # an earlier copy that failed processing is kept, not deleted
                plan.actions.append(FileAction(info, UPLOAD))
    if plan.overflow:
        plan.status = BLOCKED
    return plan
