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

from blackboard_sync.errors import EXIT_LOCKED, EXIT_LOGIN_REQUIRED, EXIT_OK

SYNC_INTERVAL = timedelta(hours=1)
FIRST_SYNC_DELAY = timedelta(seconds=30)
# After a network error or while another sync holds the lock, try again sooner
# than the hourly schedule (e.g. right after waking up the network may be down).
RETRY_DELAY = timedelta(minutes=10)
RECENT_LIMIT = 10

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
T_OPEN_FOLDER = "Okul klasörünü aç"
T_RECENT = "Son indirilenler"
T_RECENT_EMPTY = "Henüz yeni bir şey yok"
T_AUTOSTART = "Bilgisayar açılınca başlat"
T_QUIT = "Çıkış"


# Jobs that run `blackboard-sync sync`; "refetch" also brings back files the
# student deleted locally. Scheduled runs and "Şimdi senkronize et" are plain
# "sync" runs, so they keep respecting deletions.
SYNC_JOBS = ("sync", "refetch")


def sync_arguments(job: str) -> list[str]:
    """CLI arguments for a sync job."""
    args = ["sync", "--json"]
    if job == "refetch":
        args.append("--refetch-missing")
    return args


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


def login_notification() -> Notification:
    return Notification(
        title="Blackboard oturumu sona erdi",
        message="Yeni dosyaları almak için menüden “Giriş yap”ı seçin.",
        data={"action": "login"},
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
    status_lines: list[str]
    sync_title: str
    sync_enabled: bool
    refetch_title: str
    refetch_enabled: bool
    login_title: str
    login_enabled: bool
    recent: list[tuple[str, str]]  # (label, path relative to dest)
    autostart: bool


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
    were started elsewhere (exit status 4, retried later).
    """

    def __init__(
        self,
        dest: Path,
        now: datetime,
        last: RunOutcome | None = None,
        recent: list[RecentItem] | None = None,
        login_prompted: bool = False,
        autostart: bool = False,
    ):
        self.dest = dest
        self.last = last
        self.recent = list(recent or [])
        self.login_prompted = login_prompted
        self.autostart = autostart
        self.busy: str | None = None  # "sync" | "refetch" | "login"
        self.note = ""  # a transient extra line (lock held, sign-in failed, ...)
        self.next_run_at = now + FIRST_SYNC_DELAY

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
    def due(self, now: datetime) -> bool:
        return self.busy is None and now >= self.next_run_at

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
            self.next_run_at = now + RETRY_DELAY
            return notes
        self.last = outcome
        if outcome.status == "ok":
            self.login_prompted = False
            self.remember(outcome)
            self.next_run_at = now + SYNC_INTERVAL
            notification = changes_notification(outcome, self.dest)
            if notification:
                notes.append(notification)
        elif outcome.status == "login_required":
            self.next_run_at = now + SYNC_INTERVAL
            if not self.login_prompted:
                self.login_prompted = True
                notes.append(login_notification())
        else:
            self.next_run_at = now + RETRY_DELAY
        return notes

    def finish_login(self, ok: bool, message: str, now: datetime) -> None:
        self.busy = None
        if ok:
            self.note = ""
            self.next_run_at = now  # fetch what was missed right away
        else:
            self.note = shorten(f"Giriş tamamlanamadı: {message}", 80)

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
    def status_lines(self, now: datetime) -> list[str]:
        if self.busy == "sync":
            lines = ["Yeni içerik kontrol ediliyor…"]
        elif self.busy == "refetch":
            lines = ["Silinen dosyalar tekrar indiriliyor…"]
        elif self.busy == "login":
            lines = ["Tarayıcıda giriş yapmanız bekleniyor…"]
        elif self.last is None:
            lines = ["Henüz senkronize edilmedi"]
        else:
            when = format_time(self.last.finished_at or now, now)
            if self.last.status == "ok":
                totals: dict[str, int] = {}
                for course in self.last.courses:
                    for key, count in course.counts.items():
                        totals[key] = totals.get(key, 0) + count
                lines = [f"Son senkron: {when} · {counts_text(totals)}"]
            elif self.last.status == "login_required":
                lines = [f"Son deneme: {when} · oturum sona erdi, giriş yapın"]
            else:
                lines = [f"Son deneme: {when} · hata"]
                if self.last.message:
                    lines.append(shorten(self.last.message, 70))
        if self.note:
            lines.append(self.note)
        if self.busy is None:
            lines.append(f"Sonraki senkron: {format_time(max(self.next_run_at, now), now)}")
        return lines

    def menu(self, now: datetime) -> MenuModel:
        return MenuModel(
            status_lines=self.status_lines(now),
            sync_title=T_SYNCING if self.busy == "sync" else T_SYNC_NOW,
            sync_enabled=self.busy is None,
            refetch_title=T_REFETCHING if self.busy == "refetch" else T_REFETCH,
            refetch_enabled=self.busy is None,
            login_title=T_LOGGING_IN if self.busy == "login" else T_LOGIN,
            login_enabled=self.busy is None,
            recent=unique_labels([(item.label, item.path) for item in self.recent]),
            autostart=self.autostart,
        )

    # -- persistence ----------------------------------------------------
    def saved_state(self) -> dict:
        return {
            "login_prompted": self.login_prompted,
            "recent": [vars(item) for item in self.recent],
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
