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
- Announcements: all synced current-term announcements (``announcements``).
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

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from hashlib import sha1
from pathlib import Path, PurePosixPath

from blackboard_sync import __version__, ai_launcher, announcements, courses, deadlines, updater
from blackboard_sync.i18n import ntr, tr
from blackboard_sync.licensing import LicenseKind
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    NOTEBOOKLM_CONNECT,
    NOTEBOOKLM_SYNC,
    T_LOGGING_IN,
    T_LOGIN,
    T_PAUSE,
    T_RESUME,
    T_SYNC_NOW,
    T_SYNCING,
    AppModel,
    files,
    login_waiting_line,
    parse_iso,
    shorten,
)
from blackboard_sync.menubar.settings_form import T_SAVE, FormValues, WindowStatus, window_status
from blackboard_sync.notebooklm.store import NotebookLMStatus
from blackboard_sync.paths import course_code_and_title, fold_course_key

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
T_SESSION_REFRESHED = tr("Session refreshed automatically")
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
T_NO_DEADLINES = tr("No upcoming deadlines.")
T_ACTIVITY_EMPTY = tr("Nothing downloaded yet.")
T_NAME, T_SIZE, T_STATUS = tr("Name"), tr("File size"), tr("Status")
T_PAUSE_SHORT = tr("Pause")
SESSION_NOTE_FOR = timedelta(hours=2)  # how long Home's card mentions a background sign-in
HOME_RECENT_ROWS = 4  # files listed on Home before "View all"
HOME_RECENT_MIN_ROWS = 2  # ...and what stays when the window is short; the page scrolls below that
HOME_ANNOUNCEMENT_ROWS = 3  # attention items first, then the newest announcements
HOME_DEADLINE_ROWS = 4

# Jobs that change files: the account card says a sync is running.
SYNC_RUNNING_JOBS = ("sync", MOVE_JOB)
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
    return tr("{greeting}, {name}").format(greeting=text, name=first) if first else text  # Arabic: "،"


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
    course_code: str = ""
    when: str = ""
    color: int | None = None


# Indexed by the persisted course color. Keep the WebView2 CSS tokens in the same order.
# Each entry is ((light fill, light ink), (dark fill, dark ink)).
COURSE_PALETTE = (
    (("#e3edfd", "#1a56c4"), ("#1d2b42", "#9cc0ff")),
    (("#e3f4e8", "#137333"), ("#1b3224", "#7fd69a")),
    (("#feefe0", "#9a4a00"), ("#3a2b1c", "#ffb871")),
    (("#f0eefa", "#5b4bb7"), ("#2a2640", "#c2b8ff")),
    (("#fdecf6", "#a02a6e"), ("#3a2232", "#ff9fd3")),
    (("#e0f4f4", "#00696b"), ("#16302f", "#7fd8d4")),
    (("#fde8e7", "#b3261e"), ("#3a2224", "#ff9e97")),
    (("#f4f1dc", "#625200"), ("#33301a", "#e3cf6b")),
)


def load_course_colors(data: object) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    return {key: index for key, index in data.items()
            if isinstance(key, str) and key and type(index) is int and 0 <= index < len(COURSE_PALETTE)}


def course_color_index(colors: Mapping[str, int], code: str) -> int | None:
    return colors.get(fold_course_key(code))


def course_name_without_code(course: str, code: str) -> str:
    """Course title for a row that already shows ``code`` as a badge."""
    text = " ".join((course or "").split())
    if not text or not code:
        return text
    code_key = fold_course_key(code)
    parsed_code, parsed_title = course_code_and_title("", text)
    if parsed_code != "Course" and fold_course_key(parsed_code) == code_key:
        if parsed_title == text or fold_course_key(parsed_title) == code_key:
            return ""
        return parsed_title
    if fold_course_key(text) == code_key:
        return ""
    if text.casefold().startswith(code.casefold()):
        rest = text[len(code):]
        if not rest or rest[0] in " -_:|":
            rest = rest.strip(" -_:|")
            return "" if fold_course_key(rest) == code_key else rest
    return text


def assign_course_colors(model: AppModel, current_codes: Iterable[str], other_codes: Iterable[str]) -> None:
    """Seed current courses in order, and keep prior assignments even after a course leaves."""
    current = dict.fromkeys(filter(None, map(fold_course_key, current_codes)))
    other = dict.fromkeys(filter(None, map(fold_course_key, other_codes)))
    colors = model.course_colors
    active = current or other
    usage = Counter(colors[key] for key in active if key in colors)
    size = len(COURSE_PALETTE)
    for key in (*current, *other):
        if key in colors:
            continue
        # Start at a stable offset when several colors are equally available.
        start = int(sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest(), 16) % size
        index = min(((start + offset) % size for offset in range(size)), key=usage.__getitem__)
        colors[key] = index
        if key in active:
            usage[index] += 1
        model.course_colors_dirty = True


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


# The NotebookLM card's states.
NOTEBOOKLM_OFF, NOTEBOOKLM_IDLE, NOTEBOOKLM_RUNNING, NOTEBOOKLM_ATTENTION = "off", "idle", "running", "attention"
T_NOTEBOOKLM = "Gemini Notebook"  # the card's title: Google's name for NotebookLM
T_NOTEBOOKLM_CONNECT = tr("Connect Gemini Notebook")
# The card is titled with the name, so its buttons do not repeat it: they must fit one row in every language.
T_NOTEBOOKLM_SYNC = T_SYNC_NOW
T_NOTEBOOKLM_OPEN = T_OPEN_FILE
T_NOTEBOOKLM_INTRO = tr("Your course files are added after each sync.")
T_NOTEBOOKLM_CHECKING = tr("Checking what is already in Gemini Notebook…")
T_NOTEBOOKLM_WAITING = tr("Sign in to Google in the browser window.")
T_NOTEBOOKLM_VERIFYING = tr("Checking the connection…")
T_NOTEBOOKLM_READING = tr("Gemini Notebook is reading the new files…")


@dataclass(frozen=True)
class NotebookLMCard:
    """The card under Home's status card, always titled ``T_NOTEBOOKLM``: its pill leaves no room for
    more, so ``detail`` says what is going on. ``action`` is a window action."""

    kind: str  # one of the NOTEBOOKLM_* values
    detail: str
    secondary: str = ""  # time of the last check, or the course being uploaded
    notice: str = ""  # why something was left out
    action: str = ""
    action_title: str = ""
    enabled: bool = True
    open_action: bool = False  # the "Open NotebookLM" pill beside the action
    progress: float | None = None  # 0 to 1 while files go up; None: no telling, the bar just moves
    warning_counts: str = ""  # "1 course blocked · 2 held back · 3 failed"

    @property
    def warning(self) -> bool:
        return self.kind == NOTEBOOKLM_ATTENTION

    @property
    def running(self) -> bool:
        return self.kind == NOTEBOOKLM_RUNNING


@dataclass(frozen=True)
class NotebookLMProgress:
    """Where a running job is: its line, the course it is at and how far the bar has come."""

    text: str
    course: str = ""
    fraction: float | None = None


# The AI study session card's states (under NotebookLM on Home).
AI_OFF, AI_READY, AI_LAUNCHING, AI_ATTENTION = "off", "ready", "launching", "attention"
T_AI_TITLE = tr("AI study session")
T_AI_LOOKING = tr("Looking for AI tools…")
# What the card's tool buttons ask for: the prefix, then the key.
AI_OPEN_PREFIX = "ai_open:"


@dataclass(frozen=True)
class AiButton:
    """One installed AI tool on the card: a button showing the tool's logo."""

    key: str  # settings.AI_CLIS
    label: str  # "Open in Claude Code": the button's accessible name and tooltip
    current: bool = False  # the tool used last, highlighted

    @property
    def action(self) -> str:
        return AI_OPEN_PREFIX + self.key


@dataclass(frozen=True)
class AiCard:
    """The card under Home's NotebookLM card: opens the current term's folder with an AI tool."""

    kind: str  # one of the AI_* values
    detail: str
    action: str = ""  # "ai_install" | "sync"
    action_title: str = ""
    enabled: bool = True
    secondary_action: str = ""  # "ai_detect"
    secondary_title: str = ""
    secondary_enabled: bool = True
    title: str = T_AI_TITLE
    tools: tuple[AiButton, ...] = ()  # the installed tools
    tools_enabled: bool = True  # False while a terminal is opening

    @property
    def warning(self) -> bool:
        return self.kind == AI_ATTENTION


@dataclass(frozen=True)
class ActivityRow:
    name: str
    course: str
    detail: str  # "CSE303 · today 14:05"
    status: str  # "Successfully downloaded"
    size: str  # "14 KB", "—" for a note without a measurable file
    path: str  # relative to the University folder, for ``open_target``
    kind: str  # "PDF", "MD", ...
    course_code: str = ""
    course_title: str = ""
    color: int | None = None


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


LICENSE_TRIAL, LICENSE_EXPIRED = "trial", "expired"
LICENSE_BUY_ACTION, LICENSE_RESTORE_ACTION = "license_buy", "license_restore"


@dataclass(frozen=True)
class LicenseCard:
    """Home's compact trial line (``LICENSE_TRIAL``) or expired-trial buy card (``LICENSE_EXPIRED``)."""

    kind: str  # LICENSE_TRIAL | LICENSE_EXPIRED
    title: str
    detail: str
    buy_action: str = LICENSE_BUY_ACTION
    buy_title: str = ""
    buy_enabled: bool = True
    restore_action: str = ""
    restore_title: str = ""
    restore_enabled: bool = True
    notice: str = ""


def trial_remaining_text(expires_at: datetime, now: datetime) -> str:
    """Remaining trial time formatted for any Partner Center trial duration."""
    seconds = max(0, int((expires_at - now).total_seconds()))
    if seconds < 3600:
        minutes = min(59, max(1, (seconds + 59) // 60))
        return ntr("{n} minute left", "{n} minutes left", minutes).format(n=minutes)
    hours = (seconds + 3599) // 3600
    if hours <= 48:
        return ntr("{n} hour left", "{n} hours left", hours).format(n=hours)
    days = (seconds + 86399) // 86400
    return ntr("{n} day left", "{n} days left", days).format(n=days)


def license_card(model: AppModel, now: datetime) -> LicenseCard | None:
    """The trial line while a trial runs, the buy card once it ended, or None (full / offline grace)."""
    state = model.license
    busy = model.license_busy
    price = state.formatted_price.strip()
    if state.is_expired(now):
        detail = (
            tr("Buy Blackboard Sync once ({price}) to keep syncing your courses. "
               "Your downloaded files are still in your folder.").format(price=price)
            if price else
            tr("Buy Blackboard Sync once to keep syncing your courses. "
               "Your downloaded files are still in your folder.")
        )
        buy_title = (tr("Opening Store…") if busy == "buy"
                     else tr("Buy for {price}").format(price=price) if price
                     else tr("Buy"))
        restore_title = tr("Checking…") if busy == "restore" else tr("I already bought it")
        return LicenseCard(
            kind=LICENSE_EXPIRED,
            title=tr("Your free trial has ended"),
            detail=detail,
            buy_title=buy_title,
            buy_enabled=busy is None,
            restore_action=LICENSE_RESTORE_ACTION,
            restore_title=restore_title,
            restore_enabled=busy is None,
            notice=model.license_notice,
        )
    if state.kind == LicenseKind.TRIAL:
        line = (tr("Free trial · {remaining}").format(remaining=trial_remaining_text(state.expires_at, now))
                if state.expires_at is not None else tr("Free trial"))
        buy_title = tr("Opening Store…") if busy == "buy" else tr("Buy")
        return LicenseCard(
            kind=LICENSE_TRIAL,
            title="",
            detail=line,
            buy_title=buy_title,
            buy_enabled=busy is None,
            notice=model.license_notice,
        )
    return None


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
    # The Home page's own header (the sidebar keeps ``overview_title``): a greeting and one line
    # about the next due dates; the plain title and no line without them.
    home_heading: str = ""
    home_subtitle: str = ""
    notebooklm: NotebookLMCard = NotebookLMCard(NOTEBOOKLM_OFF, T_NOTEBOOKLM_INTRO)
    ai: AiCard = AiCard(AI_OFF, T_AI_LOOKING)
    course_colors: Mapping[str, int] = field(default_factory=dict)
    license: LicenseCard | None = None

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


def sync_problem_line(last: RunOutcome) -> str:
    """What a finished sync could not do, as one line for Home's status card; "" when nothing."""
    parts = []
    if last.failed_files:
        count = len(last.failed_files)
        parts.append(ntr("{n} file could not be downloaded", "{n} files could not be downloaded",
                         count).format(n=count))
    if last.unreadable_courses:
        count = last.unreadable_courses
        parts.append(ntr("{n} course could not be read", "{n} courses could not be read", count).format(n=count))
    # A bad connection or an unnamed warning only gets the line when there is nothing more exact to say.
    if not parts and last.unstable_network:
        parts.append(tr("Your internet connection seems unstable"))
    if not parts and (last.warnings or last.warning_count):
        parts.append(tr("Something went wrong during the last sync"))
    return " · ".join(parts)


def account_card(model: AppModel, now: datetime) -> AccountCard:
    name, expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    message = model.note
    warning = False
    if not message and model.last is not None and model.last.status == "error" and model.busy is None:
        message, warning = shorten(tr("Sync did not finish: {error}").format(error=model.last.message), 120), True
    elif not message and model.last is not None and model.last.status == "ok" and model.busy is None:
        message = sync_problem_line(model.last)
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
    if model.license_expired(now):
        return HomeState(STATE_ATTENTION, tr("Free trial ended"), detail)
    if model.paused:
        return HomeState(STATE_PAUSED, T_STATE_TITLES[STATE_PAUSED], detail)
    if name is None:
        return HomeState(STATE_ATTENTION, T_STATE_TITLES[STATE_ATTENTION], detail, "login", T_LOGIN)
    if model.last is not None and model.last.status == "error":
        return HomeState(STATE_ERROR, T_STATE_TITLES[STATE_ERROR], shorten(model.last.message, 100) or detail)
    refreshed = model.session_care.refreshed_at
    if refreshed is not None and timedelta(0) <= now - refreshed < SESSION_NOTE_FOR:
        detail = f"{detail} · {T_SESSION_REFRESHED}"
    return HomeState(STATE_SYNCED, T_STATE_TITLES[STATE_SYNCED], detail)


def notebooklm_progress(event: dict) -> NotebookLMProgress:
    """The running card's state for an event of ``blackboard-sync notebooklm``."""
    kind = event.get("event")
    if kind == "progress":
        file, total = str(event.get("file", "")), event.get("total") or 0
        return NotebookLMProgress(
            tr("Adding {done} of {total}: {file}").format(done=event.get("done"), total=total, file=file.rsplit("/")[-1]),
            str(event.get("course", "")), min(event.get("finished", 0) / total, 1.0) if total else None)
    if kind == "processing":
        return NotebookLMProgress(T_NOTEBOOKLM_READING)
    if kind == "sign_in":
        return NotebookLMProgress(T_NOTEBOOKLM_VERIFYING)
    return NotebookLMProgress(T_NOTEBOOKLM_CHECKING)


def notebooklm_warning_counts(status: NotebookLMStatus) -> str:
    """Summarize the files or courses that need attention."""
    parts = []
    if status.blocked:
        parts.append(ntr("{n} course blocked", "{n} courses blocked", status.blocked).format(n=status.blocked))
    if status.held:
        parts.append(tr("{n} held back").format(n=status.held))
    if status.failed:
        parts.append(tr("{n} failed").format(n=status.failed))
    return " · ".join(parts)


def notebooklm_card(model: AppModel, now: datetime) -> NotebookLMCard:
    """Not connected, signing in, running, needing the student, or idle with the last run's result."""
    status, busy = model.notebooklm, model.notebooklm_busy
    connect = {"action": "notebooklm_connect", "action_title": T_NOTEBOOKLM_CONNECT}
    sync = {"action": "notebooklm_sync", "action_title": T_NOTEBOOKLM_SYNC, "enabled": not model.paused,
            "open_action": True}
    progress = model.notebooklm_progress
    if busy == NOTEBOOKLM_CONNECT:
        return NotebookLMCard(NOTEBOOKLM_RUNNING, progress.text if progress else T_NOTEBOOKLM_WAITING,
                              **{**connect, "enabled": False})
    if busy == NOTEBOOKLM_SYNC:
        progress = progress or NotebookLMProgress(T_NOTEBOOKLM_CHECKING)
        return NotebookLMCard(NOTEBOOKLM_RUNNING, progress.text, progress.course, progress=progress.fraction,
                              **{**sync, "enabled": False})
    if not status.connected:
        if status.error:
            return NotebookLMCard(NOTEBOOKLM_ATTENTION, status.message, **connect)
        return NotebookLMCard(NOTEBOOKLM_OFF, T_NOTEBOOKLM_INTRO, **connect)
    if status.needs_login:
        return NotebookLMCard(NOTEBOOKLM_ATTENTION, status.message, action="notebooklm_connect", action_title=T_LOGIN)
    if status.error:
        return NotebookLMCard(NOTEBOOKLM_ATTENTION, tr("Sync did not finish: {error}").format(error=status.message),
                              **sync)
    finished = parse_iso(status.finished_at)
    if finished is None:
        return NotebookLMCard(NOTEBOOKLM_IDLE, T_NEVER_SYNCED, **sync)
    detail = tr("No new files were added")
    if status.added:
        detail = ntr("{n} new file added to your notebooks", "{n} new files added to your notebooks",
                     status.added).format(n=status.added)
    checked = tr("Last checked: {time}").format(time=day_time(finished, now))
    return NotebookLMCard(NOTEBOOKLM_IDLE, detail, secondary=checked, notice=status.message,
                          warning_counts=notebooklm_warning_counts(status), **sync)


def ai_card(model: AppModel, sync_title: str | None = None, sync_enabled: bool = True) -> AiCard:
    """The installed AI tools to open the term folder with, launching, how to install one when
    there is none, or why the last click did not open a terminal."""
    title = tr("AI study session")
    installed = model.ai_installed
    if installed is None:
        return AiCard(AI_OFF, tr("Looking for AI tools…"), title=title)
    install = {"action": "ai_install", "action_title": tr("How to install"),
               "secondary_action": "ai_detect", "secondary_title": tr("Try again")}
    tools = tuple(AiButton(key, tr("Open in {name}").format(name=tool.name), key == model.ai_cli)
                  for key, tool in ai_launcher.TOOLS.items() if key in installed)
    if not tools:
        return AiCard(AI_ATTENTION,
                      tr("No AI tool is installed. Install Claude Code, Gemini CLI, Codex or Antigravity, then try again."),
                      title=title, **install)
    shown = {"title": title, "tools": tools}
    if model.ai_launching:
        return AiCard(AI_LAUNCHING, tr("Opening…"), tools_enabled=False, **shown)
    term = model.current_ai_term()
    result = model.ai_result
    failure = None if result is None else result.failure
    if failure == ai_launcher.Failure.CLI_MISSING and result.tool is not None and result.tool.key not in installed:
        return AiCard(AI_ATTENTION,
                      tr("{name} is not installed. Install it, then try again.").format(name=result.tool.name),
                      **install, **shown)
    if failure == ai_launcher.Failure.FOLDER_MISSING:
        folder_name = (result.folder.name or str(result.folder)) if result.folder is not None else term
        return AiCard(
            AI_ATTENTION,
            tr("The {term} folder isn't there yet. Sync first.").format(term=folder_name),
            action="sync",
            action_title=tr("Sync now") if sync_title is None else sync_title,
            enabled=sync_enabled,
            **shown,
        )
    if failure == ai_launcher.Failure.TERMINAL_FAILED:
        error = shorten(result.error, 140) if result.error else ""
        detail = (tr("Could not open a terminal: {error}").format(error=error) if error
                  else tr("Could not open a terminal."))
        return AiCard(AI_ATTENTION, detail, **shown)
    if model.ai_resume:
        detail = tr("Click a tool to open {term}, continuing your last session there.").format(term=term)
    else:
        detail = tr("Click a tool to open {term} in a new session.").format(term=term)
    return AiCard(AI_READY, detail, **shown)


def home_recent_rows(available: float, fixed: float, row: float, rows: int) -> int:
    """How many files Home lists when ``available`` points of page must also hold ``fixed`` points of the rest.

    A short window gives up rows before anything is pushed out of view.
    """
    fitting = int((available - fixed) // row)
    return min(rows, max(min(fitting, HOME_RECENT_ROWS), HOME_RECENT_MIN_ROWS))


def activity_rows(model: AppModel, now: datetime) -> tuple[ActivityRow, ...]:
    course_titles = {fold_course_key(c.code): course_name_without_code(c.name, c.code)
                     for c in model.courses if c.code}
    rows = []
    for item in model.visible_activity():
        name = PurePosixPath(item.path).name
        code = item.course.strip()
        when = parse_iso(item.at)
        when_text = day_time(when, now) if when else ""
        detail = " · ".join(filter(None, (code, when_text)))
        title = course_titles.get(fold_course_key(code), "") if code else ""
        color = course_color_index(model.course_colors, code) if code else None
        rows.append(ActivityRow(name, code, detail, item.label, format_size(item.size), item.path,
                                Path(name).suffix[1:].upper()[:4], code, title, color))
    return tuple(rows)


def sidebar_name(card: AccountCard) -> str:
    return shorten(card.title, SIDEBAR_NAME_LIMIT)


def recent_rows(model: AppModel, now: datetime) -> tuple[RecentRow, ...]:
    rows = []
    for item in model.visible_recent():
        name = PurePosixPath(item.path).name
        at = parse_iso(item.at)
        when = day_time(at, now) if at else ""
        detail = " · ".join(filter(None, (item.course, when)))
        rows.append(RecentRow(name, detail, item.path, Path(name).suffix[1:].upper()[:4], item.at,
                              model.recent_seen.is_new(item.path, item.at, now), item.course, when,
                              course_color_index(model.course_colors, item.course)))
    return tuple(rows)


def main_status(model: AppModel, now: datetime, deadlines_page: deadlines.DeadlinePage | None = None,
                zone: tzinfo | None = None, *, current_course_codes: Iterable[str] = ()) -> MainStatus:
    assign_course_colors(
        model,
        current_course_codes,
        (*(item.course for item in model.visible_recent()), *(item.course for item in model.visible_activity())),
    )
    name, _expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    if model.busy == "login":
        start_message = login_waiting_line(model.login_method)
    else:
        start_message = model.note
    scene, scene_line = sync_scene(model)
    first_run = is_first_run(model)
    expired_license = model.license_expired(now)
    heading, subtitle = home_header(name, T_NAV_START if first_run else T_NAV_OVERVIEW, deadlines_page, now, zone)
    sync_title = T_SYNCING if model.busy == "sync" else T_SYNC_NOW
    sync_enabled = idle and model.configured and name is not None and not model.paused and not expired_license
    return MainStatus(
        first_run=first_run,
        account=account_card(model, now),
        sync_title=sync_title,
        sync_enabled=sync_enabled,
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
        pause_enabled=model.configured and not first_run and not expired_license,
        activity=activity_rows(model, now),
        home_heading=heading,
        home_subtitle=subtitle,
        notebooklm=notebooklm_card(model, now),
        ai=ai_card(model, sync_title=sync_title, sync_enabled=sync_enabled),
        course_colors=model.course_colors.copy(),
        license=license_card(model, now),
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
