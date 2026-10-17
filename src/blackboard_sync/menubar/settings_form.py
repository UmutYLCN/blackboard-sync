"""What the settings show and what saving them means, without any GUI code.

The settings live in the main window (``main_window_model``). Its Settings page
has five parts: Account (school address, who is signed in, sign in or out),
Folder (destination), Past terms (download a past term once), Sync (start
at login, sync interval, language) and Updates (automatic checks, check now,
version, uninstall). Dersler (``courses.py``) picks the courses that sync. The GUI layers (``main_window.py`` on macOS,
``windows/main_window.py``) only draw ``FormValues`` and ``WindowStatus`` and
report which button was pressed.

User-facing strings go through ``i18n.tr``: the window is read by the student.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blackboard_sync import __version__, uninstall
from blackboard_sync.i18n import DEFAULT_LANGUAGE, LANGUAGES, language_name, normalize_language, ntr, tr
from blackboard_sync.menubar.model import (
    DEST_MOVE,
    DEST_REFETCH,
    T_CHECK_NOW,
    T_LOGGING_IN,
    T_LOGIN,
    T_LOGOUT,
    T_PAST_LOADING,
    AppModel,
    login_waiting_line,
)
from blackboard_sync.settings import (
    SYNC_INTERVAL_CHOICES,
    Settings,
    display_path,
    normalize_base_url,
    normalize_dest,
    normalize_sync_interval,
)
from blackboard_sync.system import sync_root

T_INTERVAL_LABEL = tr("Automatic sync")
# (minutes, menu text); 0 means only by hand. Order is the order in the window.
INTERVAL_OPTIONS = (
    (30, tr("Every 30 minutes")),
    (60, tr("Every hour")),
    (180, tr("Every 3 hours")),
    (0, tr("Only manually")),
)
assert tuple(minutes for minutes, _ in INTERVAL_OPTIONS) == SYNC_INTERVAL_CHOICES


def interval_title(minutes: int) -> str:
    return dict(INTERVAL_OPTIONS)[normalize_sync_interval(minutes)]


T_LANGUAGE_LABEL = tr("Language")
# Each language is named in itself, so a student can find theirs in either language.
LANGUAGE_OPTIONS = LANGUAGES
T_LANGUAGE_RESTART_TITLE = tr("Restart Blackboard Sync to change the language?")
T_LANGUAGE_RESTART = tr("The new language is used once the app starts again.")
T_RESTART_NOW = tr("Restart now")
T_LATER = tr("Later")


def language_title(code: str) -> str:
    return language_name(code)


def language_code(title: str) -> str:
    return next((code for code, name in LANGUAGE_OPTIONS if name == title), LANGUAGE_OPTIONS[0][0])


T_SECTION_ACCOUNT = tr("Account")
T_SECTION_FOLDER = tr("Folder")
T_SECTION_PAST_TERMS = tr("Past terms")
T_SECTION_GENERAL = tr("Sync")
T_SECTION_UPDATES = tr("Updates")
T_URL_LABEL = tr("Your school's Blackboard address")
T_URL_PLACEHOLDER = tr("https://blackboard.school.edu")
T_URL_HINT = tr("If you change the address you need to sign in again for the new school.")
T_DEST_LABEL = tr("Folder to save files in")
# Under the folder field: what ``system.sync_root`` does with the chosen folder.
T_DEST_ROOT_NOTE = tr("Files are saved in the University folder inside the folder you choose.")
T_DEST_HINT = (
    T_DEST_ROOT_NOTE + " "
    + tr("If you change the folder you can move the downloaded files to the new one or "
         "download them again.")
)
T_PAST_DOWNLOAD = tr("Download past term")
T_PAST_DOWNLOADING = tr("Downloading…")
T_PAST_NOTE = tr("A past term is downloaded once and not updated.")
T_PAST_EMPTY = tr("No past terms to download.")
T_PAST_SIGN_IN = tr("Sign in to see past terms.")
T_UNINSTALL = uninstall.BUTTON_TITLE
T_AUTOSTART = tr("Start when the computer starts")
T_CHECK_UPDATES = tr("Check for updates automatically")
T_CHOOSE_FOLDER = tr("Choose…")
T_CHOOSE_FOLDER_PROMPT = tr("Use this folder")
T_CHOOSE_FOLDER_MESSAGE = tr("Choose the folder to save your course files in.")
T_SAVE = tr("Save")
T_CANCEL = tr("Cancel")
T_BUSY = tr("Wait for the running job to finish first.")
T_DEST_NOT_CHANGED = tr("The folder was not changed.")

# Asked when the folder changes and the old one holds downloaded files.
T_DEST_CHANGE_TITLE = tr("What should happen to the downloaded files?")
T_MOVE = tr("Move")
T_REDOWNLOAD = tr("Download again")
# (choice, button); the first one is the default.
DEST_CHOICES = ((DEST_MOVE, T_MOVE), (DEST_REFETCH, T_REDOWNLOAD))


# The window never grows past the screen: what does not fit scrolls inside it,
# above the Vazgeç/Kaydet bar. Heights include the title bar.
SCREEN_MARGIN = 40  # kept free between the window and the Dock, menu bar or taskbar
MIN_WINDOW_HEIGHT = 400  # the smallest height the student can resize the window to


def window_height(content: float, chrome: float, available: float) -> int:
    """The main window's opening height: everything when it fits on the screen.

    ``content`` is what the window's views need, ``chrome`` what the window
    adds around them (title bar, borders) and ``available`` the screen height
    left by the menu bar and Dock (the work area above the taskbar on Windows).
    """
    return int(min(content + chrome, max(available - SCREEN_MARGIN, MIN_WINDOW_HEIGHT)))


def dest_change_message(old: Path, new: Path, files: int) -> str:
    """The question under ``T_DEST_CHANGE_TITLE``; ``files`` were synced into ``old``.

    ``old`` and ``new`` are the chosen folders; the text names their University folders.
    """
    old, new = sync_root(old), sync_root(new)
    held = ntr("“{folder}” holds {n} file downloaded from Blackboard.",
               "“{folder}” holds {n} files downloaded from Blackboard.", files)
    return (
        held.format(folder=display_path(old), n=files) + "\n\n"
        + tr("{move}: the files are moved to “{folder}”, not downloaded again. "
             "Files you added yourself stay in the old folder.").format(move=T_MOVE, folder=display_path(new))
        + "\n"
        + tr("{redownload}: the files are downloaded again into the new folder; the old folder is not touched."
             ).format(redownload=T_REDOWNLOAD)
    )


@dataclass
class FormValues:
    """The window's inputs, as text the student can edit."""

    base_url: str
    dest: str
    autostart: bool
    check_updates: bool = True
    sync_interval_minutes: int = 60  # 0: only by hand
    language: str = DEFAULT_LANGUAGE


@dataclass(frozen=True)
class Submission:
    """Validated settings plus what the app has to do after saving them."""

    settings: Settings
    autostart: bool
    school_changed: bool  # the old session belongs to another host: sign in again
    # Future syncs go to another University folder; see ``DEST_CHOICES``. Choosing
    # ``~/X/University`` instead of ``~/X`` (or back) changes nothing.
    dest_changed: bool
    interval_changed: bool = False  # the next automatic run is recomputed
    language_changed: bool = False  # the app offers to restart in the new language

    def needs_login(self, login_pressed: bool) -> bool:
        return login_pressed or self.school_changed


@dataclass(frozen=True)
class WindowStatus:
    """The live part of the window: who is signed in and which buttons work now.

    Buttons that need the app's single job slot (sign in, sign out, download a
    past term, uninstall) are disabled while a sync or a sign-in runs.
    """

    account: str
    account_warning: bool
    account_title: str
    account_action: str  # "login" (saves the form first) | "logout"
    account_enabled: bool
    version: str
    update_title: str
    update_action: str  # "check_updates" | "update"
    update_enabled: bool
    # Eski dönemler: the terms in the list (newest first, never the current one),
    # the line under it (loading, empty, progress or result) and the button.
    past_terms: tuple[str, ...] = ()
    past_message: str = ""
    past_enabled: bool = False
    # A past term is downloading: the button says so, the list is locked and the illustration moves
    # until the download is complete.
    past_running: bool = False
    uninstall_enabled: bool = False


def past_term_status(model: AppModel) -> tuple[tuple[str, ...], str, bool]:
    """(terms, message, download enabled) for the Eski dönemler section."""
    if not model.configured or model.account()[0] is None:
        return (), T_PAST_SIGN_IN, False
    if model.busy == "past_terms" or (not model.past_terms_loaded and model.past_terms_retry_at is None):
        return (), T_PAST_LOADING, False
    if not model.past_terms_loaded:  # the last lookup met a running sync or failed; it repeats by itself
        return (), model.past_message or T_PAST_LOADING, False
    terms = tuple(model.past_terms)
    if model.busy == "past_term":
        message = model.activity()
    else:
        message = model.past_message or ("" if terms else T_PAST_EMPTY)
    return terms, message, model.can_download_past_term


def window_status(model: AppModel) -> WindowStatus:
    idle = model.busy is None
    name, expired = model.account()
    if model.busy == "login":
        account, title, action = login_waiting_line(model.login_method), T_LOGGING_IN, "login"
    elif name is not None:
        account, title, action = tr("Signed in as {name}").format(name=name), T_LOGOUT, "logout"
    elif expired:
        account, title, action = tr("Your session expired; sign in again."), T_LOGIN, "login"
    else:
        account, title, action = tr("Not signed in yet."), T_LOGIN, "login"
    updates = model.updates
    if updates.busy == "check":
        update_title, update_action = tr("Checking…"), "check_updates"
    elif updates.busy == "download":
        update_title, update_action = tr("Downloading…"), "update"
    elif updates.available is not None:
        update_title, update_action = tr("Update to {version}").format(version=updates.available.version), "update"
    else:
        update_title, update_action = T_CHECK_NOW, "check_updates"
    past_terms, past_message, past_enabled = past_term_status(model)
    return WindowStatus(
        account=account,
        account_warning=expired and model.busy != "login",
        account_title=title,
        account_action=action,
        account_enabled=idle,
        version=tr("Version {version}").format(version=__version__),
        update_title=update_title,
        update_action=update_action,
        update_enabled=updates.busy is None,
        past_terms=past_terms,
        past_message=past_message,
        past_enabled=past_enabled,
        past_running=model.busy == "past_term",
        uninstall_enabled=idle and updates.busy is None,
    )


def initial_values(saved: Settings | None, current: Settings, autostart: bool) -> FormValues:
    """Prefill the window with the saved settings, else what the app uses now.

    On the first launch "Start when the computer starts" is ticked: the app is
    meant to run in the background without the student thinking about it.
    """
    shown = saved or current
    return FormValues(
        base_url=shown.base_url,
        dest=display_path(shown.dest),
        autostart=autostart or saved is None,
        check_updates=shown.check_updates,
        sync_interval_minutes=shown.sync_interval_minutes,
        language=shown.language,
    )


def submit(values: FormValues, current: Settings) -> Submission:
    """Validate the inputs; raises ``SettingsError`` with a message for the student.

    ``current`` is what the app syncs with right now (the saved settings, or
    the defaults before the first save).
    """
    settings = Settings(
        base_url=normalize_base_url(values.base_url),
        dest=normalize_dest(values.dest),
        check_updates=values.check_updates,
        sync_interval_minutes=normalize_sync_interval(values.sync_interval_minutes),
        language=normalize_language(values.language),
    )
    return Submission(
        settings=settings,
        autostart=values.autostart,
        school_changed=settings.base_url != current.base_url.rstrip("/"),
        dest_changed=sync_root(settings.dest) != sync_root(current.dest),
        interval_changed=settings.sync_interval_minutes != current.sync_interval_minutes,
        language_changed=settings.language != current.language,
    )

