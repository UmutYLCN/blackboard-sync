"""What the main window shows and when it opens, without any GUI code.

The main window is what a student sees when they open Blackboard Sync from
Applications, Launchpad or the Start menu, also while the app already runs; the
"Ayarlar…" menu item opens it on Ayarlar. It is laid out like Google Drive's desktop
window: "Klasörü aç" and a sidebar on the left, and a row of round buttons at the top
right (Duraklat / Devam et, Ayarlar and the account). The sidebar switches between:

- Başlangıç, until the student first signs in: three steps and the sign-in form
  (school address, folder, start at login, "Giriş yap").
- Home afterwards, a compact summary: the sync state (an illustration while a sync runs),
  the last files, what needs attention with the newest announcements, and the next due dates.
- Sync activity: every file, note and announcement a sync brought, newest first, with its
  size and status.
- Dersler: one checkbox per current course; an unticked course is not synced
  and stays out of view (``courses``). The folder mirrors Blackboard.
- Takvim: cached grade-column due dates, grouped by local day (``deadlines``).
- Announcements: what needs attention (sign in again, an update, a failed sync) above all
  synced current-term announcements (``announcements``); Drive's notifications page and
  Duyurular in one.
- Ayarlar (the gear, not in the sidebar): the settings form (``settings_form``). Its
  Vazgeç/Kaydet bar appears only once something was changed, and saving keeps the window open.

Closing the window never stops the app: the menu bar / tray icon, the timers
and a running job go on, and the Dock icon (macOS) or taskbar button (Windows)
leaves with the window. The start at login stays quiet (no window).

The GUI layers (``main_window.py`` on macOS, ``windows/main_window.py``) draw
``MainStatus`` and report clicks. The page names Home, Sync activity and Announcements
follow Google Drive's. Every text goes through ``i18n.tr`` (English or Turkish).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from pathlib import Path, PurePosixPath

from blackboard_sync import __version__, announcements, courses, deadlines, updater
from blackboard_sync.i18n import ntr, tr
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    T_LOGGING_IN,
    T_LOGIN,
    T_PAUSE,
    T_RESUME,
    T_SYNC_NOW,
    T_SYNCING,
    AppModel,
    courses_text,
    files,
    login_waiting_line,
    warnings_text,
    parse_iso,
    shorten,
)
from blackboard_sync.menubar.settings_form import T_SAVE, FormValues, WindowStatus, window_status

OVERVIEW, GENERAL, COURSES, CALENDAR, ANNOUNCEMENTS = "overview", "general", "courses", "calendar", "announcements"
ACTIVITY = "activity"
# The sidebar, top to bottom; Ayarlar (GENERAL) is the gear at the top right instead.
NAV_SECTIONS = (OVERVIEW, ACTIVITY, ANNOUNCEMENTS, COURSES, CALENDAR)
SECTIONS = (*NAV_SECTIONS, GENERAL)

T_WINDOW_TITLE = tr("Blackboard Sync")
T_NAV_START = tr("Get started")
T_NAV_OVERVIEW = tr("Home")
T_NAV_ACTIVITY = tr("Sync activity")
T_NAV_GENERAL = tr("Settings")
T_NAV_COURSES = courses.T_TAB
T_NAV_CALENDAR = deadlines.T_TAB

# Başlangıç
T_START_TITLE = tr("Your course files start here.")
T_START_INTRO = (
    tr("Connect your Blackboard account and your course files come to this computer by themselves; "
    "no more checking the site every time.")
)
START_STEPS = (
    (tr("Choose your school and folder"), tr("You decide where the files are saved.")),
    (tr("Sign in to Blackboard"), tr("Your school's sign-in page opens. The first sync starts after you sign in.")),
    (tr("Your files stay up to date"),
     tr("Every hour by default. You can change how often in Settings.")),
)
T_START_FORM = tr("Let's get started")


def reopen_hint(where: str) -> str:
    """How to find the window again: ``where`` is "Applications or Launchpad" or "the Start menu"."""
    return tr("You can close this window. To see it again, open Blackboard Sync from {where}.").format(where=where)


# Genel bakış
T_OPEN_FOLDER = tr("Open folder")
T_NEW = tr("NEW")
T_UPDATE = tr("Update")
T_UPDATE_INTRO = tr("Update to get the latest version.")
T_SYNC_RUNNING = tr("Syncing")
T_EXPIRED = tr("Session expired")
T_SIGNED_OUT = tr("Not signed in")
T_WAITING = tr("Waiting for sign-in")
T_NEVER_SYNCED = tr("Not synced yet")
# The one line under the illustration on the very first sync.
T_FIRST_SYNC = tr("Downloading your files for the first time…")
# The sidebar's account card; Tk cuts long names itself (AppKit truncates).
SIDEBAR_NAME_LIMIT = 20
# Genel: the bar with Vazgeç / Kaydet, only while something is not saved.
T_UNSAVED = tr("Unsaved changes")

# Home's status card, the headline and what it stands for.
STATE_SYNCED, STATE_SYNCING, STATE_PAUSED, STATE_ATTENTION, STATE_ERROR = (
    "synced", "syncing", "paused", "attention", "error")
T_STATE_TITLES = {
    STATE_SYNCED: tr("Up to date"),
    STATE_SYNCING: tr("Syncing…"),
    STATE_PAUSED: tr("Paused"),
    STATE_ATTENTION: tr("Sign-in needed"),
    STATE_ERROR: tr("Sync did not finish"),
}
T_VIEW_ALL = tr("View all")
T_OPEN_FILE = tr("Open")
T_SHOW_IN_FOLDER = tr("Show in folder")
T_HOME_RECENT = tr("Recent downloads")
T_HOME_ANNOUNCEMENTS = announcements.T_TAB
T_HOME_CALENDAR = tr("Upcoming deadlines")
T_OPEN_CALENDAR = tr("Open calendar")
T_ALL_GOOD = tr("You're all caught up!")
T_ALL_GOOD_DETAIL = tr("Things that need your attention will show up here.")
T_NO_DEADLINES = tr("No upcoming deadlines.")
T_ACTIVITY_EMPTY = tr("Nothing downloaded yet.")
T_NEEDS_ATTENTION = tr("Needs your attention")
T_NAME, T_SIZE, T_STATUS = tr("Name"), tr("File size"), tr("Status")
T_PAUSE_SHORT = tr("Pause")
HOME_RECENT_ROWS = 4  # files listed on Home before "View all"
HOME_ANNOUNCEMENT_ROWS = 3  # attention items first, then the newest announcements
HOME_DEADLINE_ROWS = 4

# Jobs that change files: the account card says a sync is running.
SYNC_RUNNING_JOBS = ("sync", "past_term", MOVE_JOB)
# How the illustration shows while one of them runs.
SCENE_FIRST = "first"  # nothing downloaded yet: large, in place of the empty list
SCENE_COMPACT = "compact"  # small, above the list


def day_time(when: datetime, now: datetime) -> str:
    """Local "today 14:05", "yesterday 18:20" or "03.10.2026 09:15"."""
    local, today = when.astimezone(), now.astimezone().date()
    if local.date() == today:
        return tr("today {time}").format(time=f"{local:%H:%M}")
    if local.date() == today - timedelta(days=1):
        return tr("yesterday {time}").format(time=f"{local:%H:%M}")
    return f"{local:%d.%m.%Y %H:%M}"


def last_sync_text(model: AppModel, now: datetime) -> str:
    """When the last sync finished; a failed one is called an attempt ("Last attempt")."""
    last = model.last
    if last is None:
        return T_NEVER_SYNCED
    when = day_time(last.finished_at or now, now)
    return (tr("Last synced: {time}") if last.status == "ok" else tr("Last attempt: {time}")).format(time=when)


# Home's heading follows the local hour: morning until 12:00, afternoon until 18:00, then evening.
AFTERNOON_FROM_HOUR = 12
EVENING_FROM_HOUR = 18


# Letters only Turkish spells with: a word holding one of them lower-cases I as ı.
TURKISH_LETTERS = frozenset("ÇĞİÖŞÜçğıöşü")


def name_case(word: str) -> str:
    """"UMUT" -> "Umut": a word Blackboard wrote in capitals, in title case; others stay as they are.

    I has two lower-case forms. A word with a letter only Turkish has ("IŞIK", "İLKER") takes
    the Turkish ı/i ("Işık", "İlker"); any other ("WILLIAM", "ISMAIL") the English i.
    """
    if len(word) < 2 or not word.isupper():
        return word
    rest = word[1:]
    if TURKISH_LETTERS & set(word):
        rest = rest.replace("I", "ı").replace("İ", "i")
    return word[0] + rest.lower()


def first_name(name: str) -> str:
    """The first word of the signed-in name ("" without a name); capitals become title case."""
    words = name.split()
    return name_case(words[0]) if words else ""


def greeting(name: str, now: datetime, zone: tzinfo | None = None) -> str:
    """"Good morning, Umut" by the local hour of ``now``; without a name just "Good morning"."""
    hour = now.astimezone(zone).hour
    if hour < AFTERNOON_FROM_HOUR:
        text = tr("Good morning")
    elif hour < EVENING_FROM_HOUR:
        text = tr("Good afternoon")
    else:
        text = tr("Good evening")
    first = first_name(name)
    return f"{text}, {first}" if first else text


def deadline_subtitle(page: deadlines.DeadlinePage, now: datetime, zone: tzinfo | None = None) -> str:
    """"1 deadline today · 3 this week"; "" while no due dates were synced yet.

    "This week" is the next 7 days (``deadlines.THIS_WEEK``) and includes today. Nothing today
    shows only the week's count, and when every one of them is today only today's.
    """
    if page.message == deadlines.T_NOT_SYNCED:
        return ""
    today, week = deadlines.count_due(page, now, zone)
    if not week:
        return tr("No deadlines this week")
    if not today:
        return ntr("{n} deadline this week", "{n} deadlines this week", week).format(n=week)
    text = ntr("{n} deadline today", "{n} deadlines today", today).format(n=today)
    if week > today:
        text += " · " + tr("{n} this week").format(n=week)
    return text


def home_header(name: str | None, overview_title: str, page: deadlines.DeadlinePage | None, now: datetime,
                zone: tzinfo | None = None) -> tuple[str, str]:
    """(heading, subtitle) of the Home page; the plain title and no subtitle when nobody is signed in
    or no due dates were synced yet."""
    if name is None or page is None:
        return overview_title, ""
    subtitle = deadline_subtitle(page, now, zone)
    if not subtitle:
        return overview_title, ""
    return greeting(name, now, zone), subtitle


def initials(name: str) -> str:
    return "".join(word[0] for word in name.split()[:2]).upper() or "?"


@dataclass(frozen=True)
class AccountCard:
    """Who is signed in and how syncing goes, at the bottom of the sidebar.

    ``message`` shows on Genel bakış, above the list: the sidebar is too narrow for it.
    """

    initials: str
    title: str
    detail: str  # the last sync (also while a new one runs), or where to sign in
    badge: str = ""
    warning: bool = False
    message: str = ""  # a note or the last error
    action_title: str = ""  # "Sign in" when nobody is signed in
    action_enabled: bool = False


@dataclass(frozen=True)
class RecentRow:
    name: str
    detail: str  # "SWE305 · today 14:05"
    path: str  # relative to the University folder, for ``open_target``
    kind: str  # "PDF", "DOCX", ... (empty without an extension)
    at: str = ""  # download version, for the visibility tracker
    is_new: bool = False


@dataclass(frozen=True)
class HomeState:
    """Home's status card: what the sync is doing, in a word, and when it last finished."""

    kind: str  # one of the STATE_* values
    title: str
    detail: str  # "Last synced: today 14:05", or the running job's line
    action: str = ""  # a window action the card offers: "login"
    action_title: str = ""

    @property
    def shows_sync(self) -> bool:
        """"Sync now" when the card offers nothing else; a pause is lifted from the top bar, like Drive."""
        return not self.action and self.kind != STATE_PAUSED


@dataclass(frozen=True)
class ActivityRow:
    name: str
    course: str
    detail: str  # "CSE303 · today 14:05"
    status: str  # "Successfully downloaded"
    size: str  # "14 KB", "—" for a note without a measurable file
    path: str  # relative to the University folder, for ``open_target``
    kind: str  # "PDF", "MD", ...


@dataclass(frozen=True)
class AttentionItem:
    """Something Notifications lists above the history; ``action`` is a window action."""

    title: str
    detail: str
    action: str = ""
    action_title: str = ""
    warning: bool = True


def format_size(size: int | None) -> str:
    """Drive's style: "14 KB", "1.2 MB"; "—" when there is no size."""
    if size is None:
        return "—"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" or value >= 10 else f"{value:.1f} {unit}"
        value /= 1024
    return "—"  # not reached


@dataclass(frozen=True)
class UpdateBanner:
    title: str
    button_title: str
    enabled: bool


def update_banner(model: AppModel) -> UpdateBanner | None:
    """Only an actionable newer release; Store updates have no detection path."""
    updates = model.updates
    release = updates.available
    if not updater.enabled() or release is None or not updater.is_newer(release.version, __version__):
        return None
    return UpdateBanner(
        title=tr("Blackboard Sync {version} is ready").format(version=release.version),
        button_title=tr("Downloading…") if updates.busy == "download" else T_UPDATE,
        enabled=updates.busy is None,
    )


@dataclass(frozen=True)
class MainStatus:
    first_run: bool  # Başlangıç instead of Genel bakış
    account: AccountCard
    sync_title: str
    sync_enabled: bool
    recent: tuple[RecentRow, ...]
    form: WindowStatus
    # Başlangıç: the button under the form and the line under it.
    start_title: str = T_LOGIN
    start_login: bool = True  # False: only save (signed in already, e.g. from the terminal)
    start_enabled: bool = True
    start_message: str = ""
    # Genel bakış while files change: SCENE_FIRST / SCENE_COMPACT ("" otherwise) and its one line.
    scene: str = ""
    scene_line: str = ""
    update_banner: UpdateBanner | None = None
    home: HomeState = HomeState(STATE_SYNCED, T_STATE_TITLES[STATE_SYNCED], "")
    paused: bool = False
    pause_title: str = T_PAUSE  # the button at the top right
    pause_enabled: bool = False
    activity: tuple[ActivityRow, ...] = ()
    attention: tuple[AttentionItem, ...] = ()
    # The Home page's own header (the sidebar keeps ``overview_title``): a greeting and one line
    # about the next due dates; the plain title and no line without them.
    home_heading: str = ""
    home_subtitle: str = ""

    @property
    def overview_title(self) -> str:
        return T_NAV_START if self.first_run else T_NAV_OVERVIEW

    @property
    def shows_account(self) -> bool:
        """The sidebar's account card waits for the first sign-in: Başlangıç has its own form for it."""
        return not self.first_run


def is_first_run(model: AppModel) -> bool:
    """Başlangıç until the settings were saved and the student signed in or synced once."""
    name, expired = model.account()
    return not model.configured or (name is None and not expired and model.last is None and not model.recent)


def account_card(model: AppModel, now: datetime) -> AccountCard:
    name, expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    message = model.note
    warning = False
    if not message and model.last is not None and model.last.status == "error" and model.busy is None:
        message, warning = shorten(tr("Sync did not finish: {error}").format(error=model.last.message), 120), True
    if model.busy == "login":
        return AccountCard("…", T_WAITING, login_waiting_line(model.login_method), message=message)
    if name is None:
        return AccountCard("!", T_EXPIRED if expired else T_SIGNED_OUT, last_sync_text(model, now),
                           warning=True, message=message, action_title=T_LOGIN, action_enabled=idle)
    # Only a running sync gets a badge; signed in and idle needs no word of its own.
    badge = T_SYNC_RUNNING if model.busy in SYNC_RUNNING_JOBS else ""
    return AccountCard(initials(name), name, last_sync_text(model, now), badge=badge, warning=warning,
                       message=message)


def sync_scene(model: AppModel) -> tuple[str, str]:
    """(how the illustration shows, its line) while a job changes files; ("", "") otherwise."""
    if model.busy not in SYNC_RUNNING_JOBS:
        return "", ""
    line = T_FIRST_SYNC if model.busy == "sync" and model.last is None else model.activity()
    return (SCENE_COMPACT if model.recent else SCENE_FIRST), line


def home_state(model: AppModel, now: datetime) -> HomeState:
    """The one word on Home's status card: syncing, paused, signed out, failed, or up to date."""
    detail = last_sync_text(model, now)
    name, _expired = model.account()
    if model.busy in SYNC_RUNNING_JOBS:
        return HomeState(STATE_SYNCING, T_STATE_TITLES[STATE_SYNCING],
                         sync_scene(model)[1] or model.activity() or detail)
    if model.paused:
        return HomeState(STATE_PAUSED, T_STATE_TITLES[STATE_PAUSED], detail)
    if name is None:
        return HomeState(STATE_ATTENTION, T_STATE_TITLES[STATE_ATTENTION], detail, "login", T_LOGIN)
    if model.last is not None and model.last.status == "error":
        return HomeState(STATE_ERROR, T_STATE_TITLES[STATE_ERROR], shorten(model.last.message, 100) or detail)
    return HomeState(STATE_SYNCED, T_STATE_TITLES[STATE_SYNCED], detail)


def attention_items(model: AppModel) -> tuple[AttentionItem, ...]:
    """What needs the student, most pressing first; empty is "Her şey yolunda!". (A pause is shown on Home's card.)"""
    if is_first_run(model):
        return ()
    items: list[AttentionItem] = []
    if model.calendar.needs_reconnect:
        items.append(AttentionItem(tr("Google Calendar needs to be reconnected"),
                                   tr("Open Settings to reconnect your calendar."), "calendar_settings", tr("Reconnect")))
    elif model.calendar.last_error:
        items.append(AttentionItem(tr("Google Calendar error"), model.calendar.last_error,
                                   "calendar_settings", tr("Settings")))
    name, expired = model.account()
    if name is None and model.busy != "login":
        items.append(AttentionItem(T_EXPIRED if expired else T_SIGNED_OUT,
                                   tr("Sign in to get new files."), "login", T_LOGIN))
    banner = update_banner(model)
    if banner is not None:
        items.append(AttentionItem(banner.title, T_UPDATE_INTRO, "update", banner.button_title, warning=False))
    last = model.last
    if last is not None and last.status == "error" and last.message:
        items.append(AttentionItem(T_STATE_TITLES[STATE_ERROR], shorten(last.message, 160)))
    elif last is not None and last.status == "ok":
        if last.unreadable_courses:
            items.append(AttentionItem(tr("Could not read {courses}").format(courses=courses_text(last.unreadable_courses)),
                                       tr("Blackboard did not return the content; the next sync tries again.")))
        elif last.warning_count:
            items.append(AttentionItem(warnings_text(last.warning_count).capitalize(),
                                       tr("Some files could not be downloaded; the next sync tries again.")))
    if model.note and model.busy is None:
        items.append(AttentionItem(tr("Note"), model.note, warning=False))
    return tuple(items)


def activity_rows(model: AppModel, now: datetime) -> tuple[ActivityRow, ...]:
    rows = []
    for item in model.visible_activity():
        name = PurePosixPath(item.path).name
        when = parse_iso(item.at)
        detail = f"{item.course} · {day_time(when, now)}" if when else item.course
        rows.append(ActivityRow(name, item.course, detail, item.label, format_size(item.size), item.path,
                                Path(name).suffix[1:].upper()[:4]))
    return tuple(rows)


def sidebar_name(card: AccountCard) -> str:
    return shorten(card.title, SIDEBAR_NAME_LIMIT)


def recent_rows(model: AppModel, now: datetime) -> tuple[RecentRow, ...]:
    rows = []
    for item in model.visible_recent():
        name = PurePosixPath(item.path).name
        when = parse_iso(item.at)
        detail = f"{item.course} · {day_time(when, now)}" if when else item.course
        rows.append(RecentRow(name, detail, item.path, Path(name).suffix[1:].upper()[:4], item.at,
                              model.recent_seen.is_new(item.path, item.at, now)))
    return tuple(rows)


def main_status(model: AppModel, now: datetime, deadlines_page: deadlines.DeadlinePage | None = None,
                zone: tzinfo | None = None) -> MainStatus:
    name, _expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    if model.busy == "login":
        start_message = login_waiting_line(model.login_method)
    else:
        start_message = model.note
    scene, scene_line = sync_scene(model)
    first_run = is_first_run(model)
    heading, subtitle = home_header(name, T_NAV_START if first_run else T_NAV_OVERVIEW, deadlines_page, now, zone)
    return MainStatus(
        first_run=first_run,
        account=account_card(model, now),
        sync_title=T_SYNCING if model.busy == "sync" else T_SYNC_NOW,
        sync_enabled=idle and model.configured and name is not None and not model.paused,
        recent=recent_rows(model, now),
        form=window_status(model),
        start_title=T_LOGGING_IN if model.busy == "login" else T_LOGIN if name is None else T_SAVE,
        start_login=name is None,
        start_enabled=idle,
        start_message=start_message,
        scene=scene,
        scene_line=scene_line,
        update_banner=update_banner(model),
        home=home_state(model, now),
        paused=model.paused,
        pause_title=T_RESUME if model.paused else T_PAUSE,
        pause_enabled=model.configured and not is_first_run(model),
        activity=activity_rows(model, now),
        attention=attention_items(model),
        home_heading=heading,
        home_subtitle=subtitle,
    )


def recent_count(rows: tuple[RecentRow, ...]) -> str:
    """The count in the corner of the recent files: "3 files" (empty without any)."""
    return files(len(rows)) if rows else ""


def course_title(row: courses.CourseRow) -> str:
    """A Dersler row: "CSE303 Algorithm Analysis" (the code alone when there is no title)."""
    return " ".join(part for part in (row.code, row.title) if part) or row.id


def course_detail(row: courses.CourseRow) -> str:
    """The line under it: the term, and whether the course syncs."""
    return " · ".join(part for part in (row.term, tr("syncing") if row.enabled else tr("not syncing")) if part)


def enabled_count(rows: tuple[courses.CourseRow, ...]) -> str:
    """The count beside Dersler in the sidebar: "4/5" while some course is unticked."""
    enabled = sum(row.enabled for row in rows)
    return f"{enabled}/{len(rows)}" if enabled != len(rows) else ""


def has_changes(saved: FormValues, current: FormValues) -> bool:
    """Whether Genel shows its Vazgeç/Kaydet bar: only once a field differs from what is saved."""
    return current != saved


def shows_window_at_launch(background: bool, configured: bool) -> bool:
    """Every start opens the window except a quiet one (at login, or after a silent update).

    The very first launch always does: nothing syncs before the student set it up.
    """
    return not background or not configured


class WindowState:
    """Whether the main window is open (and so in the Dock / taskbar) and which section it shows.

    A minimized window still counts as open. Starting the app again keeps the
    section in view while the window is open and starts at the overview once
    it was closed; "Ayarlar…" asks for Genel.
    """

    def __init__(self) -> None:
        self.open = False
        self.section = OVERVIEW

    def show(self, section: str | None = None) -> str:
        """Open or bring forward the window; returns the section to show."""
        if section is not None:
            self.select(section)
        elif not self.open:
            self.section = OVERVIEW
        self.open = True
        return self.section

    def select(self, section: str) -> None:
        if section not in SECTIONS:
            raise ValueError(f"unknown section {section!r}")
        self.section = section

    def closed(self) -> None:
        self.open = False
