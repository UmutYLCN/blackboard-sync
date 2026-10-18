"""Everything the menu bar app decides, kept free of any GUI code.

The GUI layer (``app.py``) only forwards events here (a timer tick, a finished
sync or sign-in, a click) and draws what this module returns: the icon state,
the menu model and the notifications to post. That keeps scheduling, session
expiry handling and all user-facing text testable without a GUI session.

User-facing strings go through ``i18n.tr``: English, or Turkish when the
student chose it in Settings.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from blackboard_sync import __version__
from blackboard_sync.errors import EXIT_LOCKED, EXIT_LOGIN_REQUIRED, EXIT_OK
from blackboard_sync.i18n import ntr, tr
from blackboard_sync.inapp import INAPP
from blackboard_sync.settings import DEFAULT_SYNC_INTERVAL_MINUTES, Settings, normalize_sync_interval
from blackboard_sync.system import sync_root
from blackboard_sync.updater import CheckResult, Release, is_newer

# The default interval; the student picks another one in the settings window.
SYNC_INTERVAL = timedelta(minutes=DEFAULT_SYNC_INTERVAL_MINUTES)
FIRST_SYNC_DELAY = timedelta(seconds=30)
# After a network error or while another sync holds the lock, try again sooner
# than the regular schedule (e.g. right after waking up the network may be down);
# never later than the interval itself.
RETRY_DELAY = timedelta(minutes=10)
RECENT_LIMIT = 10
# Looking for a new app version: once a day, not right at start-up, and after
# a failed check (offline, rate limited) again an hour later.
UPDATE_INTERVAL = timedelta(days=1)
UPDATE_FIRST_DELAY = timedelta(minutes=2)
UPDATE_RETRY_DELAY = timedelta(hours=1)

# (report key, label after one, label after more): "1 new file", "2 new files".
CHANGE_LABELS = (
    ("new_files", tr("new file"), tr("new files")),
    ("updated_files", tr("updated file"), tr("updated files")),
    ("new_notes", tr("new note"), tr("new notes")),
    ("updated_notes", tr("updated note"), tr("updated notes")),
    ("new_announcements", tr("new announcement"), tr("new announcements")),
    ("updated_announcements", tr("updated announcement"), tr("updated announcements")),
    ("skipped_large_files", tr("large file not downloaded"), tr("large files not downloaded")),
)
# Report key -> what happened, for Sync activity (the same words the window shows).
ENTRY_KINDS = {
    "new_files": "new_file",
    "updated_files": "updated_file",
    "new_notes": "new_note",
    "updated_notes": "updated_note",
    "new_announcements": "new_announcement",
    "updated_announcements": "updated_announcement",
}
ENTRY_LABELS = {
    "new_file": tr("Successfully downloaded"),
    "updated_file": tr("Updated"),
    "new_note": tr("Note saved"),
    "updated_note": tr("Note updated"),
    "new_announcement": tr("Announcement saved"),
    "updated_announcement": tr("Announcement updated"),
}
ACTIVITY_LIMIT = 300

# What "Recent downloads" lists: things that appeared or changed locally.
RECENT_KEYS = ("new_files", "updated_files", "new_notes", "new_announcements")

STATUS_BY_EXIT = {EXIT_OK: "ok", EXIT_LOGIN_REQUIRED: "login_required", EXIT_LOCKED: "locked"}

# Menu text
T_SYNC_NOW = tr("Sync now")
T_SYNCING = tr("Syncing…")
T_PAST_LOADING = tr("Loading past terms…")
T_LOGIN = tr("Sign in")
T_LOGGING_IN = tr("Waiting for sign-in…")
T_LOGOUT = tr("Sign out")
T_EXPIRED = tr("⚠ Session expired — Sign in")
T_RECENT = tr("Recent downloads")
T_RECENT_EMPTY = tr("Nothing new yet")
T_PAUSE = tr("Pause syncing")
T_RESUME = tr("Resume syncing")
T_PAUSED = tr("Paused")
T_SETTINGS = tr("Settings…")
T_QUIT = tr("Quit")
T_AUTO_SYNC_OFF = tr("automatic sync off")
T_CHECK_NOW = tr("Check now")
T_CHECKING_UPDATES = tr("Checking for updates…")
T_DOWNLOADING_UPDATE = tr("Downloading update…")
T_UPDATE_WAIT = tr("Wait for the running job to finish before updating, then try again.")


def open_folder_title(root: Path) -> str:
    """The menu item that opens the folder the files are in, named after it: "Open University folder"."""
    return tr("Open {folder} folder").format(folder=root.name or root)


# Update actions of the menu row and the settings window. "check_updates"
# checks right away; "update" downloads the release in
# ``AppModel.updates.available`` and installs it (macOS: swap the app in and
# restart it, or open the .dmg where it cannot; Windows: run the silent
# installer and quit).
UPDATE_ACTIONS = ("check_updates", "update")


# Sync and discovery jobs. Every "sync" mirrors Blackboard: files that were
# deleted or broke are downloaded again (``sync.Syncer.present``).
SYNC_JOBS = ("sync", "past_term", "past_terms")
# Temporarily unavailable in the desktop apps while the archive flow is redesigned.
PAST_TERMS_AVAILABLE = False
# Moves the downloaded files into a new destination folder (``relocate.py``); with
# ``move_from`` equal to ``dest`` it only moves the files of an older version
# from the chosen folder into its University folder (``relocate.migrate_to_root``).
MOVE_JOB = "move"

# After a past-term lookup that met a running sync or failed, when to try again (Genel in view).
PAST_RETRY_DELAYS = {"locked": timedelta(seconds=15), "error": timedelta(seconds=60)}

# What happens to the downloaded files when the destination folder changes:
# move them over, or download them again into the new folder (the old one is
# left alone; a sync fills the new folder as soon as the student is signed in).
DEST_MOVE, DEST_REFETCH = "move", "refetch"


def sync_arguments(job: str, settings: Settings, term_name: str = "", term_id: str = "") -> list[str]:
    """CLI arguments for a sync job with the settings from the settings window.

    A past term is passed by its Blackboard id when the list gave one: its name
    can be shared by another term or change with Blackboard's language.
    """
    args = ["--base-url", settings.base_url, "sync", "--json", "--dest", str(settings.dest)]
    if job == "past_term":
        if term_id:
            args.extend(["--term-id", term_id])
        elif term_name:
            args.extend(["--term", term_name])
        else:
            raise ValueError("No past term was chosen.")
    return args


def login_arguments(settings: Settings) -> list[str]:
    """CLI arguments for signing in to the school from the settings window."""
    return ["--base-url", settings.base_url, "login"]


class Icon(str, Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    EXPIRED = "expired"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class CourseChange:
    code: str
    folder: str  # relative to the University folder (``AppModel.root``)
    counts: dict[str, int]
    recent_paths: list[str]  # relative to the University folder
    name: str = ""

    @property
    def changes(self) -> int:
        return sum(self.counts.values())


@dataclass
class RunOutcome:
    """The result of one ``blackboard-sync sync --json`` run."""

    status: str  # ok | login_required | locked | error
    message: str = ""
    finished_at: datetime | None = None
    dest: str = ""
    courses: list[CourseChange] = field(default_factory=list)
    past_term: str = ""
    warning_count: int = 0
    unreadable_courses: int = 0  # courses whose content could not be read at all
    # The sync first moved files of an older version into the University folder.
    moved_into_root: int = 0
    left_outside_root: int = 0  # ...and these could not be moved
    # Every file, note and announcement the run brought: (course code, path, kind) with a kind of ENTRY_KINDS.
    entries: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def changed(self) -> list[CourseChange]:
        return [c for c in self.courses if c.changes]

    @classmethod
    def from_report(cls, data: dict) -> "RunOutcome":
        courses = []
        entries: list[tuple[str, str, str]] = []
        for c in data.get("courses") or []:
            counts = {
                key: (int(c.get(key) or 0) if key == "skipped_large_files" else len(c.get(key) or []))
                for key, _one, _many in CHANGE_LABELS
            }
            recent = [p for key in RECENT_KEYS for p in c.get(key) or []]
            code = c.get("code") or c.get("name") or "?"
            entries.extend((code, p, kind) for key, kind in ENTRY_KINDS.items() for p in c.get(key) or [])
            courses.append(
                CourseChange(
                    name=c.get("name") or "",
                    code=c.get("code") or c.get("name") or "?",
                    folder=c.get("folder") or "",
                    counts=counts,
                    recent_paths=recent,
                )
            )
        return cls(
            status=data.get("status") or "error",
            message=data.get("message") or "",
            finished_at=parse_iso(data.get("finished_at")),
            dest=data.get("dest") or "",
            courses=courses,
            past_term=data.get("past_term") or "",
            warning_count=len(data.get("warnings") or []) + sum(
                len(c.get("warnings") or []) for c in data.get("courses") or []),
            unreadable_courses=sum(1 for c in data.get("courses") or [] if c.get("content_error")),
            moved_into_root=data.get("moved_into_root") or 0,
            left_outside_root=len(data.get("left_outside_root") or []),
            entries=entries,
        )


def sync_interval(minutes: int) -> timedelta | None:
    """The scheduling interval for a setting value; None for 0 (only by hand)."""
    minutes = normalize_sync_interval(minutes)
    return timedelta(minutes=minutes) if minutes else None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_sync_output(stdout: str, returncode: int, stderr: str, now: datetime) -> RunOutcome:
    """Turn the output of ``sync --json`` into a RunOutcome.

    The JSON summary is authoritative; the exit code is the fallback when the
    process died before printing it (e.g. a crash or a missing install).
    """
    try:
        data = json.loads(stdout)
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("status"):
        outcome = RunOutcome.from_report(data)
    else:
        lines = [line for line in (stderr or "").strip().splitlines() if line.strip()]
        outcome = RunOutcome(
            status=STATUS_BY_EXIT.get(returncode, "error"),
            message=lines[-1] if lines else f"blackboard-sync exited with status {returncode}",
        )
    if outcome.finished_at is None:
        outcome.finished_at = now
    return outcome


def course_line(course: CourseChange) -> str:
    """e.g. "CSE303: 2 new files, 1 new announcement"."""
    return f"{course.code}: {counts_text(course.counts)}"


def counts_text(counts: dict[str, int]) -> str:
    parts = [f"{counts[key]} {one if counts[key] == 1 else many}"
             for key, one, many in CHANGE_LABELS if counts.get(key)]
    return ", ".join(parts) if parts else tr("nothing new")


def format_time(when: datetime, now: datetime) -> str:
    """Local clock time; with the day when it was not today."""
    local, local_now = when.astimezone(), now.astimezone()
    if local.date() == local_now.date():
        return local.strftime("%H:%M")
    if local.date() == (local_now - timedelta(days=1)).date():
        return tr("yesterday {time}").format(time=local.strftime("%H:%M"))
    return local.strftime("%d.%m %H:%M")


@dataclass
class MenuEntry:
    title: str = ""  # empty means separator
    action: str | None = None
    value: str = ""
    enabled: bool = True
    checked: bool = False
    warning: bool = False
    children: list["MenuEntry"] = field(default_factory=list)


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class Notification:
    title: str
    message: str
    data: dict  # passed back on click: {"open": path} or {"action": "login"}


def changes_notification(outcome: RunOutcome, dest: Path) -> Notification | None:
    """One notification per run with new items; None when nothing is new.

    Clicking it opens the course folder, or the folder that contains all the
    changed courses (normally the term folder) when several courses changed.
    """
    changed = outcome.changed
    if outcome.status != "ok" or not changed:
        return None
    folders = [str(dest / c.folder) for c in changed]
    target = folders[0] if len(folders) == 1 else os.path.commonpath(folders)
    return Notification(
        title=tr("Blackboard: new content"),
        message="\n".join(course_line(c) for c in changed),
        data={"open": target},
    )


def update_notification(release: Release) -> Notification:
    return Notification(
        title=tr("Blackboard Sync {version} is ready — Update").format(version=release.version),
        message=tr("Click to download the new version."),
        data={"action": "update"},
    )


def login_waiting_line(method: str) -> str:
    """The status line while signing in, naming where: a browser or the app's window."""
    if method == INAPP:
        return tr("Waiting for you to sign in in the window that opened…")
    if method:
        return tr("Waiting for you to sign in in {browser}…").format(browser=method)
    return tr("Waiting for you to sign in in the browser…")


def files(count: int) -> str:
    """ "1 file", "12 files"."""
    return ntr("{n} file", "{n} files", count).format(n=count)


def courses_text(count: int) -> str:
    return ntr("{n} course", "{n} courses", count).format(n=count)


def warnings_text(count: int) -> str:
    return ntr("{n} warning", "{n} warnings", count).format(n=count)


def move_summary(moved: int, kept: int) -> str:
    """ "12 files moved to the new folder." plus what stayed behind, if anything."""
    text = tr("{files} moved to the new folder.").format(files=files(moved)) if moved else tr("No files were moved.")
    if kept:
        text += " " + tr("{files} could not be moved and stayed in the old folder.").format(files=files(kept))
    return text


def root_move_summary(moved: int, kept: int, root: Path) -> str:
    """ "12 files moved to the University folder." plus what stayed behind, if anything."""
    name = root.name or str(root)
    text = (tr("{files} moved to the {folder} folder.").format(files=files(moved), folder=name) if moved
            else tr("No files were moved."))
    if kept:
        text += " " + tr("{files} could not be moved and stayed where they were.").format(files=files(kept))
    return text


def login_notification() -> Notification:
    return Notification(
        title=tr("Blackboard session expired"),
        message=tr("Choose “Sign in” in the menu to get new files."),
        data={"action": "login"},
    )


@dataclass
class UpdateState:
    """When to look for a new app version and what was found.

    ``checked_at``, ``notified`` and ``available`` are saved in menubar.json so
    a restart neither checks again before a day has passed nor repeats the
    notification for a version the student was already told about.
    ``installing`` is the version the macOS app quit to swap in; the app it
    restarts reads it back to tell whether the swap took effect.
    """

    checked_at: datetime | None = None  # last check that got an answer
    notified: str = ""  # the version a notification was posted for
    available: Release | None = None
    not_before: datetime | None = None  # start-up delay or retry after a failed check
    busy: str | None = None  # "check" | "download" (until the app quits to install)
    installing: str = ""

    def due(self, now: datetime, enabled: bool) -> bool:
        if not enabled or self.busy is not None:
            return False
        if self.not_before is not None and now < self.not_before:
            return False
        # A check time in the future means the clock was changed: check anyway.
        return self.checked_at is None or not self.checked_at <= now < self.checked_at + UPDATE_INTERVAL

    def begin(self, job: str) -> bool:
        if self.busy is not None or (job == "download" and self.available is None):
            return False
        self.busy = job
        return True

    def finish_check(self, result: CheckResult, now: datetime, manual: bool) -> list[Notification]:
        """Record a check; scheduled checks notify once per version, manual ones always answer."""
        self.busy = None
        if result.status == "unknown":
            self.not_before = now + UPDATE_RETRY_DELAY
            if manual:
                return [Notification(
                    tr("Could not check for updates"),
                    tr("Check your internet connection and try again later."),
                    {},
                )]
            return []
        self.checked_at = now
        self.not_before = None
        self.available = result.release
        release = result.release
        if release is not None and (manual or release.version != self.notified):
            self.notified = release.version
            return [update_notification(release)]
        if manual and release is None:
            return [Notification(tr("Blackboard Sync is up to date"),
                                 tr("You have the latest version ({version}).").format(version=__version__), {})]
        return []

    def finish_download(self, error: str = "") -> list[Notification]:
        self.busy = None
        if error:
            return [Notification(tr("Could not install the update"), error, {})]
        return []

    def finish_install(self, current: str = __version__) -> list[Notification]:
        """After the restart that followed an in-place update: did it take effect?"""
        version, self.installing = self.installing, ""
        if not version:
            return []
        if version == current:
            return [Notification(
                tr("Blackboard Sync was updated to {version}").format(version=version),
                tr("Your settings and downloaded course files were kept."),
                {},
            )]
        return [Notification(
            tr("Could not install the update"),
            tr("Blackboard Sync {version} could not be put in place; version {current} is still in use.").format(
                version=version, current=current),
            {},
        )]

    def menu_entry(self) -> MenuEntry | None:
        """The menu row, only while a new version is waiting or downloading."""
        if self.busy == "download":
            return MenuEntry(T_DOWNLOADING_UPDATE, enabled=False)
        if self.available is not None:
            return MenuEntry(tr("Update available: {version} — Update").format(version=self.available.version), "update")
        return None

    def saved_state(self) -> dict:
        return {
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "notified": self.notified,
            "available": self.available.to_dict() if self.available else None,
            "installing": self.installing,
        }

    @classmethod
    def load(cls, data: dict | None, now: datetime, current: str = __version__) -> "UpdateState":
        data = data if isinstance(data, dict) else {}
        available = None
        try:
            if data.get("available"):
                available = Release.from_dict(data["available"])
        except (TypeError, ValueError):
            available = None
        if available is not None and not is_newer(available.version, current):
            available = None  # already installed
        notified = data.get("notified")
        installing = data.get("installing")
        return cls(
            checked_at=parse_iso(data.get("checked_at")),
            notified=notified if isinstance(notified, str) else "",
            installing=installing if isinstance(installing, str) else "",
            available=available,
            not_before=now + UPDATE_FIRST_DELAY,
        )


@dataclass
class RecentItem:
    path: str  # relative to the University folder
    course: str
    at: str  # ISO timestamp

    @property
    def label(self) -> str:
        return shorten(f"{self.course} · {Path(self.path).name}", 60)


@dataclass
class ActivityItem:
    """One line of Sync activity: something a sync brought, newest first."""

    path: str  # relative to the University folder
    course: str
    at: str  # ISO timestamp
    kind: str  # a value of ENTRY_KINDS
    size: int | None = None  # bytes, when the file was there to measure

    @property
    def label(self) -> str:
        return ENTRY_LABELS.get(self.kind, ENTRY_LABELS["new_file"])


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


class RecentSeen:
    """Unread download versions, with badges frozen for one overview visit.

    Per-row markers keep downloads below the fold unread. A new download of
    the same path has a new timestamp, so it becomes unread again.
    """

    def __init__(self, saved=None, clock: Callable[[], float] = time.monotonic):
        self.seen = {path: at for path, at in (saved.items() if isinstance(saved, dict) else [])
                     if isinstance(path, str) and isinstance(at, str) and parse_iso(at)}
        self.clock = clock
        self.snapshot: dict[str, str] | None = None
        self.started: dict[tuple[str, str], float] = {}
        self.last_sample: float | None = None

    def show(self) -> None:
        if self.snapshot is None:
            self.snapshot = dict(self.seen)
            self.reset_exposure()

    def hide(self) -> None:
        self.snapshot = None
        self.reset_exposure()

    def reset_exposure(self) -> None:
        self.started.clear()
        self.last_sample = None

    def is_new(self, path: str, at: str, now: datetime) -> bool:
        when = parse_iso(at)
        markers = self.seen if self.snapshot is None else self.snapshot
        return bool(when and timedelta(0) <= now - when <= timedelta(days=7)
                    and markers.get(path) != at)

    def observe(self, visible: list[tuple[str, str]], active: bool) -> bool:
        """Sample on-screen rows every 250 ms; return whether storage changed.

        Focus loss, scrolling away, and a stalled timer (including sleep) break
        continuous exposure. Seeing a row persists it without changing this
        visit's snapshot, so its badge remains until the list is shown again.
        """
        if not active or self.snapshot is None:
            self.reset_exposure()
            return False
        now = self.clock()
        if self.last_sample is not None and now - self.last_sample > 1:
            self.started.clear()
        self.last_sample = now
        keys = set(visible)
        self.started = {key: start for key, start in self.started.items() if key in keys}
        changed = False
        for path, at in keys:
            if self.seen.get(path) == at:
                continue
            start = self.started.setdefault((path, at), now)
            if now - start >= 3:
                self.seen[path] = at
                changed = True
        return changed

    def opened(self, item: RecentItem) -> bool:
        changed = self.seen.get(item.path) != item.at
        self.seen[item.path] = item.at
        if self.snapshot is not None:
            self.snapshot[item.path] = item.at
        return changed

    def saved_state(self, recent: list[RecentItem]) -> dict[str, str]:
        # The list is capped at ten rows; don't accumulate old markers forever.
        return {item.path: item.at for item in recent if self.seen.get(item.path) == item.at}


@dataclass
class MenuModel:
    status_lines: list[str]  # the two lines at the top (plus a transient note)
    sync_title: str
    sync_enabled: bool
    recent: list[tuple[str, str]]  # (label, path relative to the University folder)
    entries: list[MenuEntry] = field(default_factory=list)


def unique_labels(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Menu items are keyed by their text, so equal names get " (2)", " (3)"."""
    seen: dict[str, int] = {}
    result = []
    for label, value in entries:
        seen[label] = seen.get(label, 0) + 1
        result.append((label if seen[label] == 1 else f"{label} ({seen[label]})", value))
    return result


def open_target(root: Path, rel_path: str, exists: Callable[[Path], bool] = Path.exists) -> Path | None:
    """What "Son indirilenler" opens: the file, else the nearest existing folder."""
    path = root / rel_path
    while True:
        if exists(path):
            return path
        if path == root or root not in path.parents:
            return None
        path = path.parent


class AppModel:
    """State machine behind the menu bar app.

    Only one job (a sync or a sign-in) runs at a time; the scheduler never
    starts a sync while one is busy, and the CLI's lock file covers syncs that
    were started elsewhere (exit status 4, retried later). Until the settings
    window has been saved once (``configured``), nothing is synced on a
    schedule.
    """

    def __init__(
        self,
        dest: Path,
        now: datetime,
        last: RunOutcome | None = None,
        recent: list[RecentItem] | None = None,
        login_prompted: bool = False,
        autostart: bool = False,
        configured: bool = True,
        session: dict | None = None,
        session_expired: bool = False,
        courses: list[CourseChange] | None = None,
        check_updates: bool = True,
        updates: UpdateState | None = None,
        sync_interval_minutes: int = DEFAULT_SYNC_INTERVAL_MINUTES,
        recent_seen: RecentSeen | None = None,
    ):
        self.dest = dest  # the folder the student chose; the files are in ``root``
        self.session = session
        self.session_expired = session_expired
        self.auth_failed_at = (last.finished_at or now) if last and last.status == "login_required" else None
        self.courses = courses if courses is not None else list(last.courses if last else [])
        self.configured = configured
        self.last = last
        self.recent = list(recent or [])
        self.recent_seen = recent_seen or RecentSeen()
        # The folders of the courses unticked in Dersler; their files stay out of view.
        self.hidden_folders: tuple[str, ...] = ()
        self.login_prompted = login_prompted
        self.autostart = autostart
        from blackboard_sync.gcal import CalendarStatus
        self.calendar = CalendarStatus()
        self.calendar_busy: str | None = None
        self.busy: str | None = None  # "sync" | "login" | "move" | ...
        self.past_term = ""  # only for the active one-time job; never saved as a default
        self.past_term_id = ""  # ...and the Blackboard id of that term
        self.past_terms: list[str] = []  # what the list shows
        self.past_term_ids: dict[str, str] = {}  # entry of that list -> term id
        # Genel in the main window lists the past terms; they are looked up once
        # per sign-in and opening of the window, and ``past_message`` says how
        # the last lookup or one-time download went.
        self.past_terms_loaded = False
        self.past_message = ""
        self.past_lookup_stale = False  # the school changed while the lookup ran
        # A lookup that found the lock taken or failed is repeated by itself, not only when the window reopens.
        self.past_terms_retry_at: datetime | None = None
        # A job asked for by a destination change, started as soon as the slot is free:
        # MOVE_JOB (from ``move_from``) or "sync" (download into the new folder).
        self.pending: str | None = None
        self.move_from: Path | None = None
        # Teslim tarihi hatırlatmaları already shown (``deadlines.due_reminders``) and when they were last looked for.
        self.reminders_sent: dict[str, dict] = {}
        self.paused = False  # Duraklat: nothing syncs by itself, a running sync was stopped
        self.activity_log: list[ActivityItem] = []  # Sync activity, newest first (ACTIVITY_LIMIT)
        self.reminders_checked_at: datetime | None = None
        self.login_method = ""  # while signing in: a browser's name, INAPP, or "" if unknown
        self.note = ""  # a transient extra line (lock held, sign-in failed, ...)
        self.sync_interval = sync_interval(sync_interval_minutes)  # None: only by hand
        self.next_run_at = self.schedule(now, FIRST_SYNC_DELAY)
        self.check_updates = check_updates  # the "Check for updates automatically" setting
        self.updates = updates or UpdateState(not_before=now + UPDATE_FIRST_DELAY)

    # -- state ----------------------------------------------------------
    @property
    def root(self) -> Path:
        """The University folder in ``dest`` that holds the term folders."""
        return sync_root(self.dest)

    @property
    def migrating(self) -> bool:
        """The queued or running move only brings an older version's files into ``root``."""
        return self.move_from is not None and self.move_from == self.dest

    @property
    def health(self) -> str:
        return self.last.status if self.last else "ok"

    def icon(self) -> Icon:
        if self.busy in SYNC_JOBS or self.busy == MOVE_JOB:
            return Icon.SYNCING
        if self.health == "login_required":
            return Icon.EXPIRED
        if self.health == "error":
            return Icon.ERROR
        if self.paused:
            return Icon.PAUSED
        return Icon.IDLE

    # -- scheduling -----------------------------------------------------
    @property
    def retry_delay(self) -> timedelta | None:
        """Wait before trying again after an error; None when syncing is by hand only."""
        return None if self.sync_interval is None else min(RETRY_DELAY, self.sync_interval)

    def schedule(self, now: datetime, delay: timedelta | None) -> datetime | None:
        """The next automatic run; None (never) in manual mode."""
        return None if self.sync_interval is None or delay is None else now + delay

    def pause(self) -> None:
        """Duraklat: no scheduled sync until ``resume``. (The app also stops a running one.)"""
        self.paused = True

    def resume(self, now: datetime) -> None:
        """Devam et: syncing goes on, and one runs right away unless sync is by hand only."""
        self.paused = False
        self.note = ""
        self.next_run_at = self.schedule(now, timedelta(0))

    def due(self, now: datetime) -> bool:
        return (
            self.configured
            and not self.paused
            and self.busy is None
            and self.next_run_at is not None
            and now >= self.next_run_at
        )

    def update_due(self, now: datetime) -> bool:
        """Time for the daily look for a new app version (never while it is switched off)."""
        return self.updates.due(now, self.check_updates)

    def pending_job(self) -> str | None:
        """The job a destination change asked for, if it can start now.

        It goes before any scheduled sync. A sync waits until the student is
        signed in (it would only fail otherwise); a move needs no session.
        """
        if not self.configured or self.busy is not None or self.pending is None:
            return None
        if self.pending == "sync" and (self.session is None or self.paused):
            return None
        return self.pending

    def begin(self, job: str) -> bool:
        """Claim the single job slot; False when something is already running.

        Nothing starts while an update downloads: it may end with the app quitting.
        """
        if job in ("past_terms", "past_term") and not self.past_terms_available:
            return False
        if self.busy is not None or self.updates.busy == "download":
            return False
        self.busy = job
        if job == self.pending:
            self.pending = None
        return True

    @property
    def past_terms_available(self) -> bool:
        return PAST_TERMS_AVAILABLE

    def past_terms_due(self, now: datetime | None = None) -> bool:
        """The past-term list still has to be looked up (once Genel is in view)."""
        now = now or datetime.now(timezone.utc)
        return (
            self.past_terms_available
            and not self.past_terms_loaded
            and (self.past_terms_retry_at is None or now >= self.past_terms_retry_at)
            and self.configured
            and self.account()[0] is not None
            and self.busy is None
            and self.updates.busy != "download"
        )

    def reload_past_terms(self) -> None:
        """Look the past terms up again the next time Genel is shown."""
        if self.busy != "past_terms":
            self.past_terms_loaded = False
            self.past_terms_retry_at = None
            self.past_message = ""

    def finish_past_terms(self, names: list[str] | dict[str, str], outcome: RunOutcome,
                          now: datetime | None = None) -> None:
        """``names`` are the list's entries, or a dict of each entry to its term id.

        A lookup that met a running sync (the lock) or failed is not the answer "no past
        terms": the list stays unloaded and is looked up again after a short wait.
        """
        now = now or datetime.now(timezone.utc)
        self.busy = None
        if self.past_lookup_stale:  # the old school's terms: look again
            self.past_lookup_stale = False
            return
        retry = PAST_RETRY_DELAYS.get(outcome.status)
        self.past_terms_loaded = retry is None
        self.past_terms_retry_at = now + retry if retry is not None else None
        self.past_terms = list(names) if outcome.status == "ok" else []
        self.past_term_ids = dict(names) if outcome.status == "ok" and isinstance(names, dict) else {}
        if outcome.status == "login_required":
            self.auth_failed_at = outcome.finished_at or now
            self.note = tr("Sign in and try again to see past terms.")
        elif outcome.status == "locked":
            self.note = tr("Another sync is running; past terms will load again shortly.")
        else:
            # The lookup runs by itself when Genel is shown: it keeps
            # another job's note.
            self.note = self.note if outcome.status == "ok" else shorten(outcome.message, 100)
        self.past_message = "" if outcome.status == "ok" else self.note

    def select_past_term(self, name: str) -> bool:
        if not self.can_download_past_term or name not in self.past_terms:
            return False
        self.past_term = name
        self.past_term_id = self.past_term_ids.get(name, "")
        return True

    @property
    def can_download_past_term(self) -> bool:
        return self.past_terms_available and self.busy is None and self.updates.busy != "download" and bool(self.past_terms)

    def finish_sync(self, outcome: RunOutcome, now: datetime) -> list[Notification]:
        notes = self._finish_sync(outcome, now)
        return [*self.root_move_notifications(outcome.moved_into_root, outcome.left_outside_root), *notes]

    def root_move_notifications(self, moved: int, kept: int) -> list[Notification]:
        """Files of an older version were moved from the chosen folder into the University folder."""
        if not moved and not kept:
            return []
        summary = root_move_summary(moved, kept, self.root)
        if kept and not self.note:
            self.note = shorten(summary, 80)
        title = (tr("Files moved to the {folder} folder").format(folder=self.root.name or self.root) if not kept
                 else tr("Some files could not be moved"))
        return [Notification(title, summary, {"open": str(self.root)})]

    def _finish_sync(self, outcome: RunOutcome, now: datetime) -> list[Notification]:
        job, self.busy = self.busy, None
        self.note = ""
        notes: list[Notification] = []
        if outcome.status == "paused":
            # Duraklat stopped the run: nothing it had not finished counts, and the schedule waits.
            if job == "past_term":
                self.past_term = self.past_term_id = ""
                self.past_message = tr("The past term download was paused; download it again.")
            return notes
        if job == "past_term":
            term = outcome.past_term or self.past_term
            self.past_term = self.past_term_id = ""
            if outcome.status == "ok":
                count = sum(c.counts.get(key, 0) for c in outcome.courses
                            for key in ("new_files", "new_notes", "new_announcements"))
                self.note = tr("{term} · {files} downloaded (past term).").format(term=term, files=files(count))
                if outcome.unreadable_courses:
                    # Not "nothing new": Blackboard refused the content, so the term is not complete.
                    self.note += " " + tr("Could not read the content of {courses}; the past term is not complete, "
                                          "try again.").format(courses=courses_text(outcome.unreadable_courses))
                elif outcome.warning_count:
                    self.note += " " + tr("{warnings}; try again for what is missing.").format(
                        warnings=warnings_text(outcome.warning_count))
                self.remember(outcome)
                notes.append(Notification(tr("Blackboard: past term"), self.note,
                                          {"open": str(self.root / Path(outcome.courses[0].folder).parent)
                                           if outcome.courses else str(self.root)}))
            elif outcome.status == "locked":
                self.note = tr("Another sync is running; try again to download the past term.")
            elif outcome.status == "login_required":
                self.auth_failed_at = outcome.finished_at or now
                self.note = tr("Sign in and try again to download the past term.")
                notes.append(login_notification())
            else:
                self.note = shorten(tr("Could not download the past term: {error}").format(error=outcome.message), 100)
            self.past_message = self.note
            return notes
        if outcome.status == "locked":
            # Another sync (e.g. from the terminal) is running; keep what we
            # knew and look again soon.
            self.note = tr("Another sync is running; trying again shortly.")
            self.next_run_at = self.schedule(now, self.retry_delay)
            return notes
        self.last = outcome
        if outcome.status == "ok":
            self.login_prompted = False
            self.session_expired = False
            self.auth_failed_at = None
            self.courses = outcome.courses
            self.remember(outcome)
            self.next_run_at = self.schedule(now, self.sync_interval)
            notification = changes_notification(outcome, self.root)
            if notification:
                notes.append(notification)
        elif outcome.status == "login_required":
            self.auth_failed_at = outcome.finished_at or now
            self.next_run_at = self.schedule(now, self.sync_interval)
            if not self.login_prompted:
                self.login_prompted = True
                notes.append(login_notification())
        else:
            self.next_run_at = self.schedule(now, self.retry_delay)
        return notes

    def finish_move(self, status: str, moved: int, kept: int, message: str = "") -> list[Notification]:
        """The files were moved from ``move_from`` to ``dest`` (``relocate.MoveResult``)."""
        self.busy = None
        migrating = self.migrating
        if status == "locked":
            # A sync from the terminal holds the folders; move once it is done,
            # still before any sync into the new folder.
            self.pending = MOVE_JOB
            self.note = tr("Another sync is running; the files will be moved shortly.")
            return []
        self.move_from = None
        if status != "ok":
            self.note = shorten(tr("Could not move the files: {error}").format(error=message), 80)
            return []
        if migrating:
            self.note = ""
            return self.root_move_notifications(moved, kept)
        summary = move_summary(moved, kept)
        self.note = shorten(summary, 80) if kept else ""
        if not moved and not kept:
            return []
        return [Notification(tr("Files moved") if not kept else tr("Some files could not be moved"),
                             summary, {"open": str(self.root)})]

    def finish_login(self, ok: bool, message: str, now: datetime) -> None:
        self.busy = None
        self.login_method = ""
        if ok:
            self.past_terms_loaded = False  # the settings window lists them for this account
            self.auth_failed_at = None
            self.session_expired = False
            self.note = ""
            self.next_run_at = self.schedule(now, timedelta(0))  # fetch what was missed right away
        else:
            self.note = shorten(tr("Sign-in did not finish: {error}").format(error=message), 80)

    def apply_settings(
        self,
        dest: Path,
        school_changed: bool,
        check_updates: bool | None = None,
        sync_interval_minutes: int | None = None,
        now: datetime | None = None,
        dest_choice: str | None = None,
    ) -> None:
        """The settings window was saved.

        A new sync interval moves the next run (see ``reschedule``).

        A new folder gets what the student chose for the files already
        downloaded (``dest_choice``, None when there were none): DEST_MOVE
        queues moving them over, so "Son indirilenler" stays valid; DEST_REFETCH
        queues a sync that downloads them again. Without a move the recent list
        (paths in the old folder) starts over. A new school makes the last
        result and the old session meaningless: the student has to sign in again.
        """
        self.configured = True
        if check_updates is not None:
            self.check_updates = check_updates
        if sync_interval_minutes is not None:
            interval = sync_interval(sync_interval_minutes)
            if interval != self.sync_interval:
                self.sync_interval = interval
                self.reschedule(now or datetime.now(timezone.utc))
        if sync_root(dest) != self.root:
            self.pending, self.move_from = None, None
            if dest_choice == DEST_MOVE:
                self.pending, self.move_from = MOVE_JOB, self.dest
            else:
                self.courses = []
                self.recent = []
                self.recent_seen.seen.clear()
                if self.recent_seen.snapshot is not None:
                    self.recent_seen.snapshot.clear()
                self.recent_seen.reset_exposure()
                if dest_choice == DEST_REFETCH:
                    self.pending = "sync"
        self.dest = dest
        if school_changed:
            self.past_terms = []
            self.past_term_ids = {}
            self.past_term = self.past_term_id = ""
            self.past_terms_loaded = False
            self.past_message = ""
            self.past_lookup_stale = self.busy == "past_terms"
            self.session = None
            self.auth_failed_at = None
            self.courses = []
            self.last = None
            self.login_prompted = False
            self.note = tr("Sign in for the new school.")

    def reschedule(self, now: datetime) -> None:
        """Recompute the next run after the interval changed.

        It counts from the end of the last sync (after an error: the shorter
        retry delay). A run that would already be overdue starts 30 seconds
        from now instead of immediately, so saving the window never fires a
        sync at once.
        """
        if self.sync_interval is None:
            self.next_run_at = None
            return
        if self.last is None or self.last.finished_at is None:
            self.next_run_at = now + FIRST_SYNC_DELAY
            return
        delay = self.retry_delay if self.last.status == "error" else self.sync_interval
        next_run = self.last.finished_at + delay
        self.next_run_at = next_run if next_run > now else now + FIRST_SYNC_DELAY

    def visible_recent(self) -> list[RecentItem]:
        """Son indirilenler without the files of the courses unticked in Dersler."""
        return [item for item in self.recent
                if not any(item.path == folder or item.path.startswith(folder + "/") for folder in self.hidden_folders)]

    def remember(self, outcome: RunOutcome) -> None:
        at = (outcome.finished_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        fresh = [
            RecentItem(path=p, course=c.code, at=at)
            for c in outcome.courses
            for p in c.recent_paths
        ]
        seen = {item.path for item in fresh}
        self.recent = (fresh + [r for r in self.recent if r.path not in seen])[:RECENT_LIMIT]
        self.record_activity(outcome, at)

    def record_activity(self, outcome: RunOutcome, at: str, size_of=file_size) -> None:
        """Add what a run brought to Sync activity (newest first, the oldest fall off)."""
        added = [ActivityItem(path, course, at, kind, size_of(self.root / path))
                 for course, path, kind in outcome.entries]
        self.activity_log = (added + self.activity_log)[:ACTIVITY_LIMIT]

    def visible_activity(self) -> list[ActivityItem]:
        """Sync activity without the files of the courses unticked in Dersler."""
        return [item for item in self.activity_log
                if not any(item.path == folder or item.path.startswith(folder + "/")
                           for folder in self.hidden_folders)]


    # -- presentation ---------------------------------------------------
    def account(self) -> tuple[str | None, bool]:
        """(signed-in name, session expired); the name is None when not signed in."""
        expired = self.session_expired
        if self.auth_failed_at:
            saved_at = (self.session or {}).get("saved_at", 0)
            expired = expired or saved_at <= self.auth_failed_at.timestamp()
        if not self.session or expired:
            return None, expired
        user = self.session.get("user") or {}
        return shorten(user.get("displayName") or user.get("userName") or user.get("id") or "Blackboard", 50), False

    def headline(self, now: datetime) -> str:
        """When the last sync ran and how it went: "synced at 14:05".

        The clock time (not "17 min ago") keeps the text, and so the menu, unchanged
        until something really happens; a relative label rebuilt the menu every minute.
        """
        if self.last is None:
            return tr("not synced yet")
        when = format_time(self.last.finished_at or now, now)
        if self.last.status == "ok":
            return tr("synced at {time}").format(time=when)
        if self.last.status == "login_required":
            return tr("tried at {time}").format(time=when)
        return tr("tried at {time} · error").format(time=when)

    def activity(self) -> str:
        """What is going on instead of the usual schedule ("" when nothing special)."""
        if self.busy == "sync":
            return tr("Checking for new content…")
        if self.busy == "past_terms":
            return T_PAST_LOADING
        if self.busy == "past_term":
            return tr("Downloading {term} (past term)…").format(term=self.past_term)
        if self.busy == "login":
            return login_waiting_line(self.login_method)
        if self.busy == MOVE_JOB:
            if self.migrating:
                return tr("Moving files to the {folder} folder…").format(folder=self.root.name or self.root)
            return tr("Moving files to the new folder…")
        if not self.configured:
            return tr("Choose “{settings}” to finish setting up").format(settings=T_SETTINGS)
        if self.paused:
            return T_PAUSED
        return ""

    def detail(self, now: datetime) -> list[str]:
        """What the last sync brought and when the next one runs."""
        parts = []
        if self.last is not None and self.last.status == "ok":
            totals: dict[str, int] = {}
            for course in self.last.courses:
                for key, count in course.counts.items():
                    totals[key] = totals.get(key, 0) + count
            parts.append(counts_text(totals))
        elif self.last is not None and self.last.status == "error" and self.last.message:
            parts.append(shorten(self.last.message, 50))
        # Overdue: a fixed word, since the current clock time would change the menu every minute.
        if self.next_run_at is None:
            parts.append(T_AUTO_SYNC_OFF)
        else:
            parts.append(tr("next: {time}").format(
                time=format_time(self.next_run_at, now) if self.next_run_at > now else tr("soon")))
        return parts

    def status_lines(self, now: datetime) -> list[str]:
        """The disabled lines at the top of the menu.

        Signed in, the first line names the student and the last sync and the
        second says what it brought; otherwise the first row is the clickable
        sign-in item and a single line sums up the rest.
        """
        name, _expired = self.account()
        activity = self.activity()
        if name is not None:
            lines = [f"✓ {name} · {self.headline(now)}", activity or capitalize(" · ".join(self.detail(now)))]
        elif activity:
            lines = [activity]
        else:
            lines = [capitalize(" · ".join([self.headline(now), *self.detail(now)]))]
        if self.note:
            lines.append(self.note)
        return lines

    def menu(self, now: datetime) -> MenuModel:
        menu = MenuModel(
            status_lines=self.status_lines(now),
            sync_title=T_SYNCING if self.busy == "sync" else T_SYNC_NOW,
            sync_enabled=self.busy is None and not self.paused,
            recent=unique_labels([(f"{(parse_iso(item.at) or now).astimezone():%d.%m %H:%M} · {item.label}", item.path)
                                  for item in self.visible_recent()]),
        )
        name, expired = self.account()
        if name is None:
            title = T_LOGGING_IN if self.busy == "login" else T_EXPIRED if expired else T_LOGIN
            top = [MenuEntry(title, "login", enabled=self.busy is None, warning=expired)]
        else:
            top = []
        course_items = []
        for course in self.courses:
            label = course.name if course.name.startswith(course.code) else f"{course.code} {course.name}".strip()
            count = sum(course.counts.get(key, 0) for key in ("new_files", "new_notes", "new_announcements"))
            if count:
                label += " " + tr("({n} new)").format(n=count)
            course_items.append((label, course.folder))
        update = self.updates.menu_entry()
        sync = MenuEntry(menu.sync_title, "sync", enabled=menu.sync_enabled)
        pause = MenuEntry(T_RESUME if self.paused else T_PAUSE, "pause", enabled=self.configured)
        status = [MenuEntry(line, enabled=False) for line in menu.status_lines]
        # Nothing syncs by itself in manual mode, so the button comes first.
        head = ([*top, sync, pause, *status, MenuEntry()] if self.sync_interval is None
                else [*top, *status, MenuEntry(), sync, pause])
        menu.entries = [
            *head,
            MenuEntry(tr("Courses"), children=[MenuEntry(label, "open", value=path) for label, path in unique_labels(course_items)] or [MenuEntry(tr("No courses yet"), enabled=False)]),
            MenuEntry(T_RECENT, children=[MenuEntry(label, "open", value=path) for label, path in menu.recent] or [MenuEntry(T_RECENT_EMPTY, enabled=False)]),
            MenuEntry(open_folder_title(self.root), "folder"),
            MenuEntry(),
            *([update] if update else []),
            MenuEntry(T_SETTINGS, "settings"),
            MenuEntry(T_QUIT, "quit"),
        ]
        return menu

    # -- persistence ----------------------------------------------------
    def saved_state(self) -> dict:
        return {
            "auth_failed_at": self.auth_failed_at.isoformat() if self.auth_failed_at else None,
            "courses": [vars(course) for course in self.courses],
            "login_prompted": self.login_prompted,
            "recent": [vars(item) for item in self.recent],
            "recent_seen": self.recent_seen.saved_state(self.recent),
            "updates": self.updates.saved_state(),
            "pending": self.saved_pending(),
            "calendar": vars(self.calendar),
            "reminders": self.reminders_sent,
            "paused": self.paused,
            "activity": [vars(item) for item in self.activity_log],
        }

    def saved_pending(self) -> dict | None:
        """The job a folder change asked for, so a restart does not forget it.

        A move that is running counts as pending until it is done: if the app quits in the
        middle, the next start moves what is left (moving is safe to repeat).
        """
        job = MOVE_JOB if self.busy == MOVE_JOB else self.pending
        if job is None:
            return None
        return {"job": job, "move_from": str(self.move_from) if self.move_from is not None else None}

    def restore_pending(self, data: object) -> None:
        """Take back what ``saved_pending`` wrote; anything unreadable is ignored."""
        if self.pending is not None or not isinstance(data, dict):
            return
        job, move_from = data.get("job"), data.get("move_from")
        if job == MOVE_JOB and isinstance(move_from, str) and move_from:
            self.pending, self.move_from = MOVE_JOB, Path(move_from)
        elif job == "sync":
            self.pending = "sync"


def load_activity(data: object) -> list[ActivityItem]:
    """The Sync activity a restart keeps; entries that do not read are dropped."""
    items = []
    for item in data if isinstance(data, list) else []:
        try:
            size = item.get("size")
            items.append(ActivityItem(path=str(item["path"]), course=str(item["course"]), at=str(item["at"]),
                                      kind=str(item["kind"]), size=size if isinstance(size, int) else None))
        except (KeyError, TypeError, AttributeError):
            continue
    return items[:ACTIVITY_LIMIT]


def load_saved_state(data: dict | None) -> tuple[list[RecentItem], bool]:
    data = data or {}
    recent = []
    for item in data.get("recent") or []:
        try:
            recent.append(RecentItem(path=item["path"], course=item["course"], at=item["at"]))
        except (KeyError, TypeError):
            continue
    return recent[:RECENT_LIMIT], bool(data.get("login_prompted"))
