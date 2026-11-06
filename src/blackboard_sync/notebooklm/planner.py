"""Which files go to NotebookLM: the courses as the last sync left them, then a plan per course.

The files come from what the sync recorded (``State.outputs``), never from walking the folder,
so a student's own files in a course folder stay private. Only the current-term courses that
are ticked in Dersler count. A note's hidden ``.md`` twin would be the same text twice, and
announcements would use up the per-notebook source limit, so neither is ever a candidate.

Everything here is pure local work: no network and no writes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from blackboard_sync.notebooklm import store
from blackboard_sync.notebooklm.store import nfc
from blackboard_sync.state import State

UPLOAD = "upload"
ADOPT = "adopt"  # already in the notebook (the state was lost): record it, do not add it again
UNCHANGED = "unchanged"
TOUCHED = "touched"
MODIFIED = "modified"  # changed since it was added: reported, never replaced
HOLD = "hold"  # it may be there already, but which source that is cannot be told: reported, not added

READY = "ready"
BLOCKED = "blocked-limit"
AMBIGUOUS = "ambiguous-notebook"
EMPTY = "empty"

SUPPORTED_EXT = frozenset({".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".epub"})
IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".tif"})
MAX_FILE_BYTES = 200 * 1024 * 1024  # NotebookLM's limit per source
# Output kinds (the part of ``State.outputs`` keys before the first ":") that are never sources.
NOT_SOURCES = frozenset({"note-md", "announcement-note", "announcement-note-md"})


def title_key(title: str) -> str:
    """A title or relative path, as it compares: composed, trimmed, without case."""
    return nfc(title).strip().casefold()


def name_key(title: str) -> str:
    """The file name in a title: NotebookLM keeps the bare name when the library's rename fails."""
    return title_key(title).rsplit("/", 1)[-1]


def name_variants(rel: str) -> tuple[str, str]:
    """What a title may have kept of a file's path: its name, or its name without the extension.

    Not the name under another extension: a .docx and its .pdf are two sources.
    """
    name = name_key(rel)
    return name, PurePosixPath(name).stem


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
    reason: str = ""  # for HOLD


@dataclass
class CoursePlan:
    course: CourseScan
    status: str
    notebook_id: str | None
    actions: list[FileAction] = field(default_factory=list)
    remote_count: int = 0
    limit: int = 50
    seen: frozenset[str] = frozenset()  # the sources that were there when the plan was made

    @property
    def uploads(self) -> list[FileAction]:
        return [a for a in self.actions if a.action == UPLOAD]

    @property
    def overflow(self) -> int:
        return max(0, self.remote_count + len(self.uploads) - self.limit)


def _digest(info: FileInfo) -> str | None:
    """None when the file cannot be read; the upload then reports that for this file."""
    try:
        return store.sha256_file(info.path)
    except OSError:
        return None


def place_new_files(files: list[FileInfo], sources: list, hashes: dict[str, str]) -> list[FileAction]:
    """Whether files without a record are in the notebook already. Never adds what might be there.

    ``hashes`` holds the content of the sources the record knows. NotebookLM gives no hash of
    its own, and a title is the full relative path only when the library's rename worked, so the
    evidence goes from strong to weak: the same content under a known source, then the full path
    in the title, then the file name alone, with or without its extension. A source known to
    hold other content is no match, whatever its title says: two files can share a name in two
    folders. One clear candidate is adopted. A title that names another folder is not clear:
    it may be a file of its own. Anything like that is held and reported, never uploaded.
    """
    hashes = dict(hashes)
    present = [source for source in sources if source.status != "error"]  # a failed copy is not there
    by_content = {hashes[source.id]: source.id for source in reversed(present) if source.id in hashes}
    by_title, by_name = defaultdict(list), defaultdict(list)
    for source in present:
        by_title[title_key(source.title)].append(source)
        by_name[name_key(source.title)].append(source)

    def candidates(found: list, digest: str | None) -> list:
        return [source for source in found if hashes.get(source.id) in (None, digest)]

    digests = {info.rel: _digest(info) for info in files}
    actions, waiting = [], []
    for info in files:
        digest = digests[info.rel]
        exact = candidates(by_title[title_key(info.rel)], digest)
        if digest in by_content:
            actions.append(FileAction(info, ADOPT, digest, by_content[digest]))
        elif len(exact) == 1:
            hashes[exact[0].id] = digest
            actions.append(FileAction(info, ADOPT, digest, exact[0].id))
        elif exact:
            actions.append(FileAction(info, HOLD, digest, reason="several sources have this title"))
        else:
            waiting.append(info)
    contents = defaultdict(set)
    for info in waiting:
        contents[name_key(info.rel)].add(digests[info.rel])
    uploading: dict[str, str] = {}
    for info in waiting:
        digest, name = digests[info.rel], name_key(info.rel)
        named = candidates([source for variant in name_variants(info.rel) for source in by_name[variant]], digest)
        if named and (len(named) > 1 or "/" in named[0].title or len(contents[name]) > 1):
            actions.append(FileAction(info, HOLD, digest, reason="other files or sources share this name"))
        elif named:
            hashes[named[0].id] = digest
            actions.append(FileAction(info, ADOPT, digest, named[0].id))
        elif digest in uploading:
            actions.append(FileAction(info, HOLD, digest, reason=f"same content as {uploading[digest]}"))
        else:
            if digest is not None:
                uploading[digest] = info.rel
            actions.append(FileAction(info, UPLOAD, digest))
    return actions


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
    plan = CoursePlan(course, READY, notebook_id, remote_count=len(sources), limit=limit,
                      seen=frozenset(source.id for source in sources))
    new = []
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
            new.append(info)
    known = {source_id: known.sha256 for source_id, known in state.known_sources(course.folder).items()}
    plan.actions.extend(place_new_files(new, sources, known))
    plan.actions.sort(key=lambda action: action.file.rel)
    if plan.overflow:
        plan.status = BLOCKED
    return plan
