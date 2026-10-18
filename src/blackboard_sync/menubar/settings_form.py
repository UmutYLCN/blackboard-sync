"""What the settings show and what saving them means, without any GUI code.

The settings live in the main window (``main_window_model``). Its Settings page
is one scrolling page of sections, each a card of rows (``SECTIONS``, in the order of
``SECTION_ORDER``): Account (school address, who is signed in, sign in or out), Sync
(sync interval, start at login, language), Folder (destination), Past terms (download a
past term once), Updates (automatic checks, check now, version) and, last, a Danger
zone (uninstall). Calendar connection actions sit between Sync and Folder. Dersler (``courses.py``) picks the courses that sync. The GUI layers (``main_window.py`` on macOS,
``windows/main_window.py``) only draw ``FormValues`` and ``WindowStatus`` and
report which button was pressed.

User-facing strings go through ``i18n.tr``: the window is read by the student.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blackboard_sync import __version__, uninstall
from blackboard_sync.gcal import CalendarStatus
from blackboard_sync.deadlines import parse_due
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
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
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
T_DEST_CHANGE_NOTE = tr("If you change the folder you can move the downloaded files to the new one or "
                        "download them again.")
T_DEST_HINT = T_DEST_ROOT_NOTE + " " + T_DEST_CHANGE_NOTE
T_PAST_DOWNLOAD = tr("Download past term")
T_COMING_SOON = tr("Coming soon")
T_PAST_COMING_SOON = tr("Past-term downloads are being redesigned and will return soon.")
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


# -- the Settings page: sections of rows -----------------------------------------------------------
# A row is a title and a secondary description on the left and its control on the right. The
# controls of rows with a ``field`` edit that ``FormValues`` field (saved with Save, dropped with
# Cancel); the others act at once (a button) or only choose (the past term).
SECTION_ACCOUNT, SECTION_SYNC, SECTION_CALENDAR, SECTION_FOLDER = "account", "sync", "calendar", "folder"
SECTION_PAST_TERMS, SECTION_UPDATES, SECTION_DANGER = "past_terms", "updates", "danger"
SECTION_APPEARANCE = "appearance"  # the Windows WebView2 window only (``settings_sections(appearance=True)``)
# Top to bottom; Calendar actions are immediate, outside the saved form.
SECTION_ORDER = (SECTION_ACCOUNT, SECTION_SYNC, SECTION_APPEARANCE, SECTION_CALENDAR, SECTION_FOLDER,
                 SECTION_PAST_TERMS, SECTION_UPDATES, SECTION_DANGER)

CONTROL_FIELD, CONTROL_POPUP, CONTROL_SWITCH, CONTROL_BUTTON = "field", "popup", "switch", "button"

T_SECTION_DANGER = tr("Danger zone")
T_PAST_TERM_LABEL = tr("Term")
T_PAST_DOWNLOAD_LABEL = tr("Download the selected term")
T_INTERVAL_DETAIL = tr("How often Blackboard is checked for new files.")
T_AUTOSTART_DETAIL = tr("Keeps syncing in the background after you sign in to the computer.")
T_CHECK_UPDATES_DETAIL = tr("Looks for a new version once a day.")
T_UNINSTALL_LABEL = tr("Uninstall Blackboard Sync")
T_SECTION_APPEARANCE = tr("Appearance")
T_THEME_LABEL = tr("Theme")
T_THEME_DETAIL = tr("System follows the light or dark mode chosen in Windows.")
# (value, menu text); applies at once, outside the Save/Cancel form.
THEME_OPTIONS = ((THEME_SYSTEM, tr("System")), (THEME_LIGHT, tr("Light")), (THEME_DARK, tr("Dark")))


@dataclass(frozen=True)
class SettingRow:
    key: str
    title: str  # "" when the row's state supplies it (``row_states``)
    detail: str = ""
    control: str = CONTROL_BUTTON
    field: str = ""  # the ``FormValues`` field the control edits; "" for a control that acts at once
    button: str = ""  # a button's title; beside a field or popup it is a second control ("Choose…")
    placeholder: str = ""
    destructive: bool = False


@dataclass(frozen=True)
class SettingsSection:
    key: str
    title: str
    rows: tuple[SettingRow, ...]
    footer: str = ""  # small text under the card
    danger: bool = False


SECTIONS = {section.key: section for section in (
    SettingsSection(SECTION_ACCOUNT, T_SECTION_ACCOUNT, (
        SettingRow("base_url", T_URL_LABEL, T_URL_HINT, CONTROL_FIELD, field="base_url",
                   placeholder=T_URL_PLACEHOLDER),
        SettingRow("account", "", control=CONTROL_BUTTON),  # "Signed in as …" and Sign in / Sign out
    )),
    SettingsSection(SECTION_SYNC, T_SECTION_GENERAL, (
        SettingRow("interval", T_INTERVAL_LABEL, T_INTERVAL_DETAIL, CONTROL_POPUP, field="sync_interval_minutes"),
        SettingRow("autostart", T_AUTOSTART, T_AUTOSTART_DETAIL, CONTROL_SWITCH, field="autostart"),
        SettingRow("language", T_LANGUAGE_LABEL, T_LANGUAGE_RESTART, CONTROL_POPUP, field="language"),
    )),
    SettingsSection(SECTION_APPEARANCE, T_SECTION_APPEARANCE, (
        SettingRow("theme", T_THEME_LABEL, T_THEME_DETAIL, CONTROL_POPUP),
    )),
    SettingsSection(SECTION_CALENDAR, tr("Google Calendar"), (
        SettingRow("google_calendar", "", detail=" ", button=tr("Connect Google Calendar")),
        SettingRow("google_calendar_sync", tr("Sync calendar now"), button=tr("Sync calendar now")),
        SettingRow("google_calendar_disconnect", tr("Disconnect Google Calendar"), button=tr("Disconnect")),
    ), footer=tr("Sends deadlines to a dedicated Blackboard Deadlines calendar. Your other calendars stay private.")),
    SettingsSection(SECTION_FOLDER, T_SECTION_FOLDER, (
        SettingRow("dest", T_DEST_LABEL, T_DEST_ROOT_NOTE, CONTROL_FIELD, field="dest", button=T_CHOOSE_FOLDER),
    ), footer=T_DEST_CHANGE_NOTE),
    SettingsSection(SECTION_PAST_TERMS, T_SECTION_PAST_TERMS, (
        SettingRow("past_term", T_PAST_TERM_LABEL, T_PAST_NOTE, CONTROL_POPUP),
        SettingRow("past_download", T_PAST_DOWNLOAD_LABEL, "", CONTROL_BUTTON, button=T_PAST_DOWNLOAD),
    )),
    SettingsSection(SECTION_UPDATES, T_SECTION_UPDATES, (
        SettingRow("check_updates", T_CHECK_UPDATES, T_CHECK_UPDATES_DETAIL, CONTROL_SWITCH, field="check_updates"),
        SettingRow("update", "", control=CONTROL_BUTTON, button=T_CHECK_NOW),  # the version and Check now / Update
    )),
    SettingsSection(SECTION_DANGER, T_SECTION_DANGER, (
        SettingRow("uninstall", T_UNINSTALL_LABEL, uninstall.MESSAGE, CONTROL_BUTTON, button=T_UNINSTALL,
                   destructive=True),
    ), danger=True),
)}


def settings_sections(appearance: bool = False) -> tuple[SettingsSection, ...]:
    """The sections the page shows, in order; Appearance only where the window can change its theme."""
    return tuple(SECTIONS[key] for key in SECTION_ORDER
                 if key in SECTIONS and (appearance or key != SECTION_APPEARANCE))


@dataclass(frozen=True)
class RowState:
    """What changes in a row while the app runs; ``None`` keeps the definition's text."""

    title: str | None = None
    detail: str | None = None
    button: str | None = None
    enabled: bool = True
    warning: bool = False  # the title in the warning color
    running: bool = False  # the past term is downloading: the illustration moves


def row_states(status: "WindowStatus") -> dict[str, RowState]:
    """The live part of the rows (who is signed in, past terms, the update button, uninstall)."""
    calendar = calendar_presentation(status.calendar, status.calendar_busy, status.calendar_paused)
    return {
        "google_calendar": RowState(title=calendar.title, detail=calendar.detail, button=calendar.button,
                                     enabled=calendar.enabled, warning=calendar.warning),
        "google_calendar_sync": RowState(button=calendar.sync_button, enabled=calendar.sync_enabled),
        "google_calendar_disconnect": RowState(enabled=calendar.disconnect_enabled),
        "account": RowState(title=status.account, button=status.account_title, enabled=status.account_enabled,
                            warning=status.account_warning),
        "past_term": RowState(enabled=status.past_available and bool(status.past_terms) and not status.past_running),
        "past_download": RowState(detail=status.past_message,
                                  button=(T_COMING_SOON if not status.past_available else
                                          T_PAST_DOWNLOADING if status.past_running else T_PAST_DOWNLOAD),
                                  enabled=status.past_available and status.past_enabled,
                                  running=status.past_available and status.past_running),
        "update": RowState(title=status.version, button=status.update_title, enabled=status.update_enabled),
        "uninstall": RowState(enabled=status.uninstall_enabled),
    }


@dataclass(frozen=True)
class CalendarPresentation:
    """One stable card: status, explanation, and only the relevant actions."""
    title: str
    detail: str
    button: str
    enabled: bool = True
    warning: bool = False
    show_connect: bool = True
    show_sync: bool = False
    show_disconnect: bool = False
    sync_button: str = ""
    sync_enabled: bool = False
    disconnect_enabled: bool = False


def calendar_presentation(status: CalendarStatus, busy: str | None = None,
                          paused: bool = False) -> CalendarPresentation:
    reconnect = status.needs_reconnect or bool(status.last_error)
    connect = not status.connected or reconnect or busy == "connect"
    controls = dict(show_connect=connect, show_sync=status.connected and not connect,
                    show_disconnect=status.connected,
                    sync_button=tr("Syncing…") if busy == "sync" else tr("Sync calendar now"),
                    sync_enabled=status.connected and not reconnect and not busy and not paused,
                    disconnect_enabled=status.connected and not busy)
    if busy:
        return CalendarPresentation(tr("Google Calendar operation in progress…"),
                                    tr("You can cancel while authorization is waiting in the browser.")
                                    if busy == "connect" else tr("Please wait for the calendar operation to finish."),
                                    tr("Cancel"), busy == "connect", **controls)
    if reconnect:
        return CalendarPresentation(tr("Google Calendar needs to be reconnected") if status.needs_reconnect
                                    else tr("Google Calendar error"), status.last_error or "",
                                    tr("Reconnect"), warning=True, **controls)
    if status.connected:
        instant = parse_due(status.last_sync)
        when = instant.astimezone().strftime("%Y-%m-%d %H:%M") if instant else None
        return CalendarPresentation(tr("Connected"),
                                    tr("Last calendar sync: {time}").format(time=when)
                                    if when else tr("Calendar has not synced yet."),
                                    "", False, **controls)
    return CalendarPresentation(tr("Not connected"),
                                tr("Connect to see Blackboard deadlines in Google Calendar."),
                                tr("Connect Google Calendar"), **controls)


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
    past_available: bool = False
    uninstall_enabled: bool = False
    calendar: CalendarStatus = CalendarStatus()
    calendar_busy: str | None = None
    calendar_paused: bool = False


def past_term_status(model: AppModel) -> tuple[tuple[str, ...], str, bool]:
    """(terms, message, download enabled) for the Eski dönemler section."""
    if not model.past_terms_available:
        return (T_COMING_SOON,), T_PAST_COMING_SOON, False
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
        calendar=model.calendar, calendar_busy=model.calendar_busy, calendar_paused=model.paused,
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
        past_running=model.past_terms_available and model.busy == "past_term",
        past_available=model.past_terms_available,
        uninstall_enabled=idle and updates.busy is None and model.calendar_busy is None,
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
        theme=current.theme,  # chosen apart from the form (``Settings.theme``)
    )
    return Submission(
        settings=settings,
        autostart=values.autostart,
        school_changed=settings.base_url != current.base_url.rstrip("/"),
        dest_changed=sync_root(settings.dest) != sync_root(current.dest),
        interval_changed=settings.sync_interval_minutes != current.sync_interval_minutes,
        language_changed=settings.language != current.language,
    )

