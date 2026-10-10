"""What the main window shows and when it opens, without any GUI code.

The main window is what a student sees when they open Blackboard Sync from
Applications, Launchpad or the Start menu, also while the app already runs; the
"Ayarlar…" menu item opens it on Genel. A sidebar switches between:

- Başlangıç, until the student first signs in: three steps and the sign-in form
  (school address, folder, start at login, "Giriş yap").
- Genel bakış afterwards: the account with the last sync, "Şimdi senkronize
  et", "Klasörü aç" and the recently downloaded files.
- Genel: the settings form (``settings_form``). Its Vazgeç/Kaydet bar appears
  only once something was changed, and saving keeps the window open.
- Silinenler: deleted files to bring back (``deleted``).

Closing the window never stops the app: the menu bar / tray icon, the timers
and a running job go on, and the Dock icon (macOS) or taskbar button (Windows)
leaves with the window. The start at login stays quiet (no window).

The GUI layers (``main_window.py`` on macOS, ``windows/main_window.py``) draw
``MainStatus`` and report clicks. User-facing strings are Turkish on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from blackboard_sync import deleted
from blackboard_sync.menubar.model import (
    MOVE_JOB,
    T_LOGGING_IN,
    T_LOGIN,
    T_SYNC_NOW,
    T_SYNCING,
    AppModel,
    login_waiting_line,
    parse_iso,
    shorten,
)
from blackboard_sync.menubar.settings_form import T_SAVE, FormValues, WindowStatus, window_status

OVERVIEW, GENERAL, DELETED = "overview", "general", "deleted"
SECTIONS = (OVERVIEW, GENERAL, DELETED)

T_WINDOW_TITLE = "Blackboard Sync"
T_NAV_START = "Başlangıç"
T_NAV_OVERVIEW = "Genel bakış"
T_NAV_GENERAL = "Genel"
T_NAV_DELETED = deleted.T_TAB

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
     "Varsayılan olarak her saat. Sıklığı Genel bölümünden değiştirebilirsiniz."),
)
T_START_FORM = "Başlayalım"


def reopen_hint(where: str) -> str:
    """How to find the window again: ``where`` is "Applications veya Launchpad'den" or "Başlat menüsünden"."""
    return f"Bu pencereyi kapatabilirsiniz. Tekrar görmek için {where} Blackboard Sync'i açmanız yeterli."


# Genel bakış
T_OPEN_FOLDER = "Klasörü aç"
T_CONNECTED = "Bağlı"
T_SYNC_RUNNING = "Senkron sürüyor"
T_EXPIRED = "Oturum sona erdi"
T_SIGNED_OUT = "Giriş yapılmadı"
T_WAITING = "Giriş bekleniyor"
T_NEVER_SYNCED = "Henüz senkronize edilmedi"
# Genel: the bar with Vazgeç / Kaydet, only while something is not saved.
T_UNSAVED = "Kaydedilmemiş değişiklikler"

# Jobs that change files: the account card says a sync is running.
SYNC_RUNNING_JOBS = ("sync", "refetch", "past_term", MOVE_JOB)


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
    """Who is signed in and how syncing goes, at the top of Genel bakış."""

    initials: str
    title: str
    detail: str  # the last sync (also while a new one runs), or where to sign in
    badge: str = ""
    warning: bool = False
    message: str = ""  # a note or the last error, under the detail
    action_title: str = ""  # "Giriş yap" when nobody is signed in
    action_enabled: bool = False


@dataclass(frozen=True)
class RecentRow:
    name: str
    detail: str  # "SWE305 · bugün 14:05"
    path: str  # relative to the University folder, for ``open_target``
    kind: str  # "PDF", "DOCX", ... (empty without an extension)


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

    @property
    def overview_title(self) -> str:
        return T_NAV_START if self.first_run else T_NAV_OVERVIEW


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
    if model.busy in SYNC_RUNNING_JOBS:
        badge = T_SYNC_RUNNING
    elif warning:
        badge = ""
    else:
        badge = T_CONNECTED
    return AccountCard(initials(name), name, last_sync_text(model, now), badge=badge, warning=warning,
                       message=message)


def recent_rows(model: AppModel, now: datetime) -> tuple[RecentRow, ...]:
    rows = []
    for item in model.recent:
        name = PurePosixPath(item.path).name
        when = parse_iso(item.at)
        detail = f"{item.course} · {day_time(when, now)}" if when else item.course
        rows.append(RecentRow(name, detail, item.path, Path(name).suffix[1:].upper()[:4]))
    return tuple(rows)


def main_status(model: AppModel, now: datetime) -> MainStatus:
    name, _expired = model.account()
    idle = model.busy is None and model.updates.busy != "download"
    if model.busy == "login":
        start_message = login_waiting_line(model.login_method)
    else:
        start_message = model.note
    return MainStatus(
        first_run=is_first_run(model),
        account=account_card(model, now),
        sync_title=T_SYNCING if model.busy == "sync" else T_SYNC_NOW,
        sync_enabled=idle and model.configured and name is not None,
        recent=recent_rows(model, now),
        form=window_status(model),
        start_title=T_LOGGING_IN if model.busy == "login" else T_LOGIN if name is None else T_SAVE,
        start_login=name is None,
        start_enabled=idle,
        start_message=start_message,
    )


def recent_count(rows: tuple[RecentRow, ...]) -> str:
    """The count in the corner of Son indirilenler: "3 dosya" (empty without any)."""
    return f"{len(rows)} dosya" if rows else ""


def deleted_detail(row: deleted.MissingOutput) -> str:
    """The folder of a deleted file: "2026-2027 Güz · CSE301 Algorithms · Week 3"."""
    return " · ".join(PurePosixPath(row.folder).parts)


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
