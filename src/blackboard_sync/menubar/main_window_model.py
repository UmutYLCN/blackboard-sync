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
follow Google Drive's; the rest of the window is Turkish on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from blackboard_sync import __version__, announcements, courses, deadlines, updater
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    T_LOGGING_IN,
    T_LOGIN,
    T_PAUSE,
    T_RESUME,
    T_SYNC_NOW,
    T_SYNCING,
    AppModel,
    login_waiting_line,
    parse_iso,
    shorten,
)
from blackboard_sync.menubar.settings_form import T_SAVE, FormValues, WindowStatus, window_status

OVERVIEW, GENERAL, COURSES, CALENDAR, ANNOUNCEMENTS = "overview", "general", "courses", "calendar", "announcements"
ACTIVITY = "activity"
# The sidebar, top to bottom; Ayarlar (GENERAL) is the gear at the top right instead.
NAV_SECTIONS = (OVERVIEW, ACTIVITY, ANNOUNCEMENTS, COURSES, CALENDAR)
SECTIONS = (*NAV_SECTIONS, GENERAL)

T_WINDOW_TITLE = "Blackboard Sync"
T_NAV_START = "Başlangıç"
T_NAV_OVERVIEW = "Home"
T_NAV_ACTIVITY = "Sync activity"
T_NAV_GENERAL = "Ayarlar"
T_NAV_COURSES = courses.T_TAB
T_NAV_CALENDAR = deadlines.T_TAB

# Başlangıç
T_START_TITLE = "Ders dosyalarınız burada başlayacak."
T_START_INTRO = (
    "Blackboard hesabınıza bağlanın. Ders dosyalarınız otomatik olarak bu bilgisayara insin; "
    "her seferinde siteyi kontrol etmeniz gerekmesin."
)
START_STEPS = (
    ("Okulunuzu ve klasörünüzü seçin", "Dosyaların nereye kaydedileceğini siz belirleyin."),
    ("Blackboard'a giriş yapın", "Okulunuzun giriş ekranı açılır. Girişten sonra ilk senkron başlar."),
    ("Dosyalarınız kendiliğinden güncellensin",
     "Varsayılan olarak her saat. Sıklığı Ayarlar'dan değiştirebilirsiniz."),
)
T_START_FORM = "Başlayalım"


def reopen_hint(where: str) -> str:
    """How to find the window again: ``where`` is "Applications veya Launchpad'den" or "Başlat menüsünden"."""
    return f"Bu pencereyi kapatabilirsiniz. Tekrar görmek için {where} Blackboard Sync'i açmanız yeterli."


# Genel bakış
T_OPEN_FOLDER = "Klasörü aç"
T_NEW = "YENİ"
T_UPDATE = "Güncelle"
T_UPDATE_INTRO = "En yeni sürüme geçmek için güncelleyin."
T_SYNC_RUNNING = "Senkron sürüyor"
T_EXPIRED = "Oturum sona erdi"
T_SIGNED_OUT = "Giriş yapılmadı"
T_WAITING = "Giriş bekleniyor"
T_NEVER_SYNCED = "Henüz senkronize edilmedi"
# The one line under the illustration on the very first sync.
T_FIRST_SYNC = "Dosyalarınız ilk kez indiriliyor…"
# The sidebar's account card; Tk cuts long names itself (AppKit truncates).
SIDEBAR_NAME_LIMIT = 20
# Genel: the bar with Vazgeç / Kaydet, only while something is not saved.
T_UNSAVED = "Kaydedilmemiş değişiklikler"

# Home's status card, the headline and what it stands for.
STATE_SYNCED, STATE_SYNCING, STATE_PAUSED, STATE_ATTENTION, STATE_ERROR = (
    "synced", "syncing", "paused", "attention", "error")
T_STATE_TITLES = {
    STATE_SYNCED: "Güncel",
    STATE_SYNCING: "Senkronize ediliyor…",
    STATE_PAUSED: "Duraklatıldı",
    STATE_ATTENTION: "Giriş gerekli",
    STATE_ERROR: "Senkron tamamlanamadı",
}
T_VIEW_ALL = "Tümünü gör"
T_HOME_RECENT = "Son indirilenler"
T_HOME_ANNOUNCEMENTS = announcements.T_TAB
T_HOME_CALENDAR = "Yaklaşan teslimler"
T_OPEN_CALENDAR = "Takvimi aç"
T_ALL_GOOD = "Her şey yolunda!"
T_ALL_GOOD_DETAIL = "Dikkatinizi gerektiren bir şey burada görünecek."
T_NO_DEADLINES = "Yaklaşan teslim yok."
T_ACTIVITY_EMPTY = "Henüz indirilen bir şey yok."
T_NEEDS_ATTENTION = "Dikkat gerektirenler"
T_NAME, T_SIZE, T_STATUS = "Ad", "Boyut", "Durum"
T_RESUME_SHORT = "Sürdür"
T_PAUSE_SHORT = "Duraklat"
HOME_RECENT_ROWS = 4  # files listed on Home before "Tümünü gör"
HOME_ANNOUNCEMENT_ROWS = 3  # attention items first, then the newest announcements
HOME_DEADLINE_ROWS = 4

# Jobs that change files: the account card says a sync is running.
SYNC_RUNNING_JOBS = ("sync", "past_term", MOVE_JOB)
# How the illustration shows while one of them runs.
SCENE_FIRST = "first"  # nothing downloaded yet: large, in place of the empty list
SCENE_COMPACT = "compact"  # small, above the list


def day_time(when: datetime, now: datetime) -> str:
    """Local "bugün 14:05", "dün 18:20" or "03.10.2026 09:15"."""
    local, today = when.astimezone(), now.astimezone().date()
    if local.date() == today:
        return f"bugün {local:%H:%M}"
    if local.date() == today - timedelta(days=1):
        return f"dün {local:%H:%M}"
    return f"{local:%d.%m.%Y %H:%M}"


def last_sync_text(model: AppModel, now: datetime) -> str:
    """When the last sync finished; a failed one is called an attempt ("Son deneme")."""
    last = model.last
    if last is None:
        return T_NEVER_SYNCED
    when = day_time(last.finished_at or now, now)
    return f"Son senkron: {when}" if last.status == "ok" else f"Son deneme: {when}"


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
    action_title: str = ""  # "Giriş yap" when nobody is signed in
    action_enabled: bool = False


@dataclass(frozen=True)
class RecentRow:
    name: str
    detail: str  # "SWE305 · bugün 14:05"
    path: str  # relative to the University folder, for ``open_target``
    kind: str  # "PDF", "DOCX", ... (empty without an extension)
    at: str = ""  # download version, for the visibility tracker
    is_new: bool = False


@dataclass(frozen=True)
class HomeState:
    """Home's status card: what the sync is doing, in a word, and when it last finished."""

    kind: str  # one of the STATE_* values
    title: str
    detail: str  # "Son senkron: bugün 14:05", or the running job's line
    action: str = ""  # a window action the card offers: "login" or "pause" (Devam et)
    action_title: str = ""


@dataclass(frozen=True)
class ActivityRow:
    name: str
    course: str
    detail: str  # "CSE303 · bugün 14:05"
    status: str  # "Başarıyla indirildi"
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
        title=f"Blackboard Sync {release.version} hazır",
        button_title="İndiriliyor…" if updates.busy == "download" else T_UPDATE,
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
        message, warning = shorten(f"Senkron tamamlanamadı: {model.last.message}", 120), True
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
        return HomeState(STATE_PAUSED, T_STATE_TITLES[STATE_PAUSED], detail, "pause", T_RESUME_SHORT)
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
    name, expired = model.account()
    if name is None and model.busy != "login":
        items.append(AttentionItem(T_EXPIRED if expired else T_SIGNED_OUT,
                                   "Yeni dosyaları almak için giriş yapın.", "login", T_LOGIN))
    banner = update_banner(model)
    if banner is not None:
        items.append(AttentionItem(banner.title, T_UPDATE_INTRO, "update", banner.button_title, warning=False))
    last = model.last
    if last is not None and last.status == "error" and last.message:
        items.append(AttentionItem(T_STATE_TITLES[STATE_ERROR], shorten(last.message, 160)))
    elif last is not None and last.status == "ok":
        if last.unreadable_courses:
            items.append(AttentionItem(f"{last.unreadable_courses} dersin içeriği okunamadı",
                                       "Blackboard içeriği vermedi; sonraki senkronda yeniden denenecek."))
        elif last.warning_count:
            items.append(AttentionItem(f"{last.warning_count} uyarı",
                                       "Bazı dosyalar indirilemedi; sonraki senkronda yeniden denenecek."))
    if model.note and model.busy is None:
        items.append(AttentionItem("Not", model.note, warning=False))
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


def main_status(model: AppModel, now: datetime) -> MainStatus:
    name, _expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    if model.busy == "login":
        start_message = login_waiting_line(model.login_method)
    else:
        start_message = model.note
    scene, scene_line = sync_scene(model)
    return MainStatus(
        first_run=is_first_run(model),
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
    )


def recent_count(rows: tuple[RecentRow, ...]) -> str:
    """The count in the corner of Son indirilenler: "3 dosya" (empty without any)."""
    return f"{len(rows)} dosya" if rows else ""


def course_title(row: courses.CourseRow) -> str:
    """A Dersler row: "CSE303 Algorithm Analysis" (the code alone when there is no title)."""
    return " ".join(part for part in (row.code, row.title) if part) or row.id


def course_detail(row: courses.CourseRow) -> str:
    """The line under it: the term, and whether the course syncs."""
    return " · ".join(part for part in (row.term, "senkronize ediliyor" if row.enabled else "senkronize edilmiyor") if part)


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
