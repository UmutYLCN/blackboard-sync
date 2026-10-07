"""Everything the menu bar app decides, kept free of any GUI code.

The GUI layer (``app.py``) only forwards events here (a timer tick, a finished
sync or sign-in, a click) and draws what this module returns: the icon state,
the menu model and the notifications to post. That keeps scheduling, session
expiry handling and all user-facing text testable without a GUI session.

User-facing strings are Turkish on purpose: the menu and notifications are
read by the student.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from blackboard_sync import __version__
from blackboard_sync.errors import EXIT_LOCKED, EXIT_LOGIN_REQUIRED, EXIT_OK
from blackboard_sync.inapp import INAPP
from blackboard_sync.settings import DEFAULT_SYNC_INTERVAL_MINUTES, Settings, normalize_sync_interval
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

# (report key, Turkish label). Turkish keeps the noun singular after a number:
# "2 yeni dosya".
CHANGE_LABELS = (
    ("new_files", "yeni dosya"),
    ("updated_files", "güncellenen dosya"),
    ("new_notes", "yeni not"),
    ("updated_notes", "güncellenen not"),
    ("new_announcements", "yeni duyuru"),
    ("updated_announcements", "güncellenen duyuru"),
)
# What "Son indirilenler" lists: things that appeared or changed locally.
RECENT_KEYS = ("new_files", "updated_files", "new_notes", "new_announcements")

STATUS_BY_EXIT = {EXIT_OK: "ok", EXIT_LOGIN_REQUIRED: "login_required", EXIT_LOCKED: "locked"}

# Menu text
T_SYNC_NOW = "Şimdi senkronize et"
T_SYNCING = "Senkronize ediliyor…"
T_REFETCH = "Silinenleri tekrar indir"
T_REFETCHING = "Silinenler indiriliyor…"
T_LOGIN = "Giriş yap"
T_LOGGING_IN = "Giriş bekleniyor…"
T_LOGOUT = "Hesaptan çıkış yap"
T_EXPIRED = "⚠ Oturum sona erdi — Giriş yap"
T_RECENT = "Son indirilenler"
T_RECENT_EMPTY = "Henüz yeni bir şey yok"
T_SETTINGS = "Ayarlar…"
T_QUIT = "Çık"
T_AUTO_SYNC_OFF = "otomatik senkron kapalı"
T_CHECK_NOW = "Şimdi denetle"
T_CHECKING_UPDATES = "Güncellemeler denetleniyor…"
T_DOWNLOADING_UPDATE = "Güncelleme indiriliyor…"


def open_folder_title(dest: Path) -> str:
    """The menu item that opens the destination, named after it: "University klasörünü aç"."""
    return f"{dest.name or dest} klasörünü aç"


# Update actions of the menu row and the settings window. "check_updates"
# checks right away; "update" downloads the release in
# ``AppModel.updates.available`` and installs it (macOS: open the .dmg,
# Windows: run the silent installer and quit).
UPDATE_ACTIONS = ("check_updates", "update")


# Jobs that run `blackboard-sync sync`; "refetch" also brings back files the
# student deleted locally. Scheduled runs and "Şimdi senkronize et" are plain
# "sync" runs, so they keep respecting deletions.
SYNC_JOBS = ("sync", "refetch")


def sync_arguments(job: str, settings: Settings) -> list[str]:
    """CLI arguments for a sync job with the settings from the settings window."""
    args = ["--base-url", settings.base_url, "sync", "--json", "--dest", str(settings.dest)]
    if job == "refetch":
        args.append("--refetch-missing")
    return args


def login_arguments(settings: Settings) -> list[str]:
    """CLI arguments for signing in to the school from the settings window."""
    return ["--base-url", settings.base_url, "login"]


class Icon(str, Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass
class CourseChange:
    code: str
    folder: str  # relative to dest
    counts: dict[str, int]
    recent_paths: list[str]  # relative to dest
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

    @property
    def changed(self) -> list[CourseChange]:
        return [c for c in self.courses if c.changes]

    @classmethod
    def from_report(cls, data: dict) -> "RunOutcome":
        courses = []
        for c in data.get("courses") or []:
            counts = {key: len(c.get(key) or []) for key, _ in CHANGE_LABELS}
            recent = [p for key in RECENT_KEYS for p in c.get(key) or []]
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
    """e.g. "CSE303: 2 yeni dosya, 1 yeni duyuru"."""
    return f"{course.code}: {counts_text(course.counts)}"


def counts_text(counts: dict[str, int]) -> str:
    parts = [f"{counts[key]} {label}" for key, label in CHANGE_LABELS if counts.get(key)]
    return ", ".join(parts) if parts else "yeni bir şey yok"


def format_time(when: datetime, now: datetime) -> str:
    """Local clock time; with the day when it was not today."""
    local, local_now = when.astimezone(), now.astimezone()
    if local.date() == local_now.date():
        return local.strftime("%H:%M")
    if local.date() == (local_now - timedelta(days=1)).date():
        return f"dün {local.strftime('%H:%M')}"
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
        title="Blackboard: yeni içerik",
        message="\n".join(course_line(c) for c in changed),
        data={"open": target},
    )


def update_notification(release: Release) -> Notification:
    return Notification(
        title=f"Blackboard Sync {release.version} hazır — Güncelle",
        message="Yeni sürümü indirmek için tıklayın.",
        data={"action": "update"},
    )


def login_waiting_line(method: str) -> str:
    """The status line while signing in, naming where: a browser or the app's window."""
    if method == INAPP:
        return "Açılan pencerede giriş yapmanız bekleniyor…"
    if method:
        return f"{method} penceresinde giriş yapmanız bekleniyor…"
    return "Tarayıcıda giriş yapmanız bekleniyor…"


def login_notification() -> Notification:
    return Notification(
        title="Blackboard oturumu sona erdi",
        message="Yeni dosyaları almak için menüden “Giriş yap”ı seçin.",
        data={"action": "login"},
    )


@dataclass
class UpdateState:
    """When to look for a new app version and what was found.

    ``checked_at``, ``notified`` and ``available`` are saved in menubar.json so
    a restart neither checks again before a day has passed nor repeats the
    notification for a version the student was already told about.
    """

    checked_at: datetime | None = None  # last check that got an answer
    notified: str = ""  # the version a notification was posted for
    available: Release | None = None
    not_before: datetime | None = None  # start-up delay or retry after a failed check
    busy: str | None = None  # "check" | "download"

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
                    "Güncellemeler denetlenemedi",
                    "İnternet bağlantınızı kontrol edip daha sonra tekrar deneyin.",
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
            return [Notification("Blackboard Sync güncel", f"Kullandığınız sürüm ({__version__}) en yenisi.", {})]
        return []

    def finish_download(self, error: str = "") -> list[Notification]:
        self.busy = None
        if error:
            return [Notification("Güncelleme yüklenemedi", error, {})]
        return []

    def menu_entry(self) -> MenuEntry | None:
        """The menu row, only while a new version is waiting or downloading."""
        if self.busy == "download":
            return MenuEntry(T_DOWNLOADING_UPDATE, enabled=False)
        if self.available is not None:
            return MenuEntry(f"Güncelleme var: {self.available.version} — Güncelle", "update")
        return None

    def saved_state(self) -> dict:
        return {
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "notified": self.notified,
            "available": self.available.to_dict() if self.available else None,
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
        return cls(
            checked_at=parse_iso(data.get("checked_at")),
            notified=notified if isinstance(notified, str) else "",
            available=available,
            not_before=now + UPDATE_FIRST_DELAY,
        )


@dataclass
class RecentItem:
    path: str  # relative to dest
    course: str
    at: str  # ISO timestamp

    @property
    def label(self) -> str:
        return shorten(f"{self.course} · {Path(self.path).name}", 60)


@dataclass
class MenuModel:
    status_lines: list[str]  # the two lines at the top (plus a transient note)
    sync_title: str
    sync_enabled: bool
    recent: list[tuple[str, str]]  # (label, path relative to dest)
    entries: list[MenuEntry] = field(default_factory=list)


def unique_labels(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Menu items are keyed by their text, so equal names get " (2)", " (3)"."""
    seen: dict[str, int] = {}
    result = []
    for label, value in entries:
        seen[label] = seen.get(label, 0) + 1
        result.append((label if seen[label] == 1 else f"{label} ({seen[label]})", value))
    return result


def open_target(dest: Path, rel_path: str, exists: Callable[[Path], bool] = Path.exists) -> Path | None:
    """What "Son indirilenler" opens: the file, else the nearest existing folder."""
    path = dest / rel_path
    while True:
        if exists(path):
            return path
        if path == dest or dest not in path.parents:
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
    ):
        self.dest = dest
        self.session = session
        self.session_expired = session_expired
        self.auth_failed_at = (last.finished_at or now) if last and last.status == "login_required" else None
        self.courses = courses if courses is not None else list(last.courses if last else [])
        self.configured = configured
        self.last = last
        self.recent = list(recent or [])
        self.login_prompted = login_prompted
        self.autostart = autostart
        self.busy: str | None = None  # "sync" | "refetch" | "login"
        self.login_method = ""  # while signing in: a browser's name, INAPP, or "" if unknown
        self.note = ""  # a transient extra line (lock held, sign-in failed, ...)
        self.sync_interval = sync_interval(sync_interval_minutes)  # None: only by hand
        self.next_run_at = self.schedule(now, FIRST_SYNC_DELAY)
        self.check_updates = check_updates  # the "Güncellemeleri otomatik denetle" setting
        self.updates = updates or UpdateState(not_before=now + UPDATE_FIRST_DELAY)

    # -- state ----------------------------------------------------------
    @property
    def health(self) -> str:
        return self.last.status if self.last else "ok"

    def icon(self) -> Icon:
        if self.busy in SYNC_JOBS:
            return Icon.SYNCING
        if self.health == "login_required":
            return Icon.EXPIRED
        if self.health == "error":
            return Icon.ERROR
        return Icon.IDLE

    # -- scheduling -----------------------------------------------------
    @property
    def retry_delay(self) -> timedelta | None:
        """Wait before trying again after an error; None when syncing is by hand only."""
        return None if self.sync_interval is None else min(RETRY_DELAY, self.sync_interval)

    def schedule(self, now: datetime, delay: timedelta | None) -> datetime | None:
        """The next automatic run; None (never) in manual mode."""
        return None if self.sync_interval is None or delay is None else now + delay

    def due(self, now: datetime) -> bool:
        return (
            self.configured
            and self.busy is None
            and self.next_run_at is not None
            and now >= self.next_run_at
        )

    def update_due(self, now: datetime) -> bool:
        """Time for the daily look for a new app version (never while it is switched off)."""
        return self.updates.due(now, self.check_updates)

    def begin(self, job: str) -> bool:
        """Claim the single job slot; False when something is already running."""
        if self.busy is not None:
            return False
        self.busy = job
        return True

    def finish_sync(self, outcome: RunOutcome, now: datetime) -> list[Notification]:
        job, self.busy = self.busy, None
        self.note = ""
        notes: list[Notification] = []
        if outcome.status == "locked":
            # Another sync (e.g. from the terminal) is running; keep what we
            # knew and look again soon. A retry is a normal sync, so a
            # refetch request has to be repeated by the student.
            self.note = (
                "Başka bir senkron sürüyor; birazdan tekrar deneyin."
                if job == "refetch"
                else "Başka bir senkron sürüyor; birazdan tekrar denenecek."
            )
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
            notification = changes_notification(outcome, self.dest)
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

    def finish_login(self, ok: bool, message: str, now: datetime) -> None:
        self.busy = None
        self.login_method = ""
        if ok:
            self.auth_failed_at = None
            self.session_expired = False
            self.note = ""
            self.next_run_at = self.schedule(now, timedelta(0))  # fetch what was missed right away
        else:
            self.note = shorten(f"Giriş tamamlanamadı: {message}", 80)

    def apply_settings(
        self,
        dest: Path,
        school_changed: bool,
        check_updates: bool | None = None,
        sync_interval_minutes: int | None = None,
        now: datetime | None = None,
    ) -> None:
        """The settings window was saved.

        A new sync interval moves the next run (see ``reschedule``).

        A new folder only affects future syncs, so "Son indirilenler" (paths in
        the old folder) starts over. A new school makes the last result and the
        old session meaningless: the student has to sign in again.
        """
        self.configured = True
        if check_updates is not None:
            self.check_updates = check_updates
        if sync_interval_minutes is not None:
            interval = sync_interval(sync_interval_minutes)
            if interval != self.sync_interval:
                self.sync_interval = interval
                self.reschedule(now or datetime.now(timezone.utc))
        if dest != self.dest:
            self.courses = []
            self.dest = dest
            self.recent = []
        if school_changed:
            self.session = None
            self.auth_failed_at = None
            self.courses = []
            self.last = None
            self.login_prompted = False
            self.note = "Yeni okul için giriş yapın."

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

    def remember(self, outcome: RunOutcome) -> None:
        at = (outcome.finished_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        fresh = [
            RecentItem(path=p, course=c.code, at=at)
            for c in outcome.courses
            for p in c.recent_paths
        ]
        seen = {item.path for item in fresh}
        self.recent = (fresh + [r for r in self.recent if r.path not in seen])[:RECENT_LIMIT]

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
        """When the last sync ran and how it went: "14:05 senkronize edildi".

        The clock time (not "17 dk önce") keeps the text, and so the menu, unchanged
        until something really happens; a relative label rebuilt the menu every minute.
        """
        if self.last is None:
            return "henüz senkronize edilmedi"
        when = format_time(self.last.finished_at or now, now)
        if self.last.status == "ok":
            return f"{when} senkronize edildi"
        if self.last.status == "login_required":
            return f"{when} denendi"
        return f"{when} denendi · hata"

    def activity(self) -> str:
        """What is going on instead of the usual schedule ("" when nothing special)."""
        if self.busy == "sync":
            return "Yeni içerik kontrol ediliyor…"
        if self.busy == "refetch":
            return "Silinen dosyalar tekrar indiriliyor…"
        if self.busy == "login":
            return login_waiting_line(self.login_method)
        if not self.configured:
            return f"Kurulumu tamamlamak için “{T_SETTINGS}”ı seçin"
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
            parts.append(f"sonraki: {format_time(self.next_run_at, now) if self.next_run_at > now else 'birazdan'}")
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
            sync_enabled=self.busy is None,
            recent=unique_labels([(f"{(parse_iso(item.at) or now).astimezone():%d.%m %H:%M} · {item.label}", item.path) for item in self.recent]),
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
                label += f" ({count} yeni)"
            course_items.append((label, course.folder))
        update = self.updates.menu_entry()
        sync = MenuEntry(menu.sync_title, "sync", enabled=menu.sync_enabled)
        status = [MenuEntry(line, enabled=False) for line in menu.status_lines]
        # Nothing syncs by itself in manual mode, so the button comes first.
        head = [*top, sync, *status, MenuEntry()] if self.sync_interval is None else [*top, *status, MenuEntry(), sync]
        menu.entries = [
            *head,
            MenuEntry("Dersler", children=[MenuEntry(label, "open", value=path) for label, path in unique_labels(course_items)] or [MenuEntry("Henüz ders yok", enabled=False)]),
            MenuEntry(T_RECENT, children=[MenuEntry(label, "open", value=path) for label, path in menu.recent] or [MenuEntry(T_RECENT_EMPTY, enabled=False)]),
            MenuEntry(open_folder_title(self.dest), "folder"),
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
            "updates": self.updates.saved_state(),
        }


def load_saved_state(data: dict | None) -> tuple[list[RecentItem], bool]:
    data = data or {}
    recent = []
    for item in data.get("recent") or []:
        try:
            recent.append(RecentItem(path=item["path"], course=item["course"], at=item["at"]))
        except (KeyError, TypeError):
            continue
    return recent[:RECENT_LIMIT], bool(data.get("login_prompted"))
