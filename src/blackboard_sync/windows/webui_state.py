"""What the WebView2 main window draws, as plain data for JSON; no GUI code.

The page (``webui/app.js``) renders this and nothing else: every text comes from
here (through ``i18n.tr``), and a click sends back only an id this module handed
out. ``WebMainWindow`` checks such an id against the last state it drew before
acting on it (``ids``), so the page can never name a file or address of its own.

The model is the same as the Tk window's and macOS's (``menubar/main_window_model``,
``menubar/settings_form``).
"""

from __future__ import annotations

from datetime import date

from blackboard_sync import __version__, announcements, courses, deadlines, uninstall, updater
from blackboard_sync.i18n import tr
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.menubar.model import T_RECENT_EMPTY
from blackboard_sync.settings import THEME_SYSTEM

# The sidebar's icon for each section (Material Symbols names in ``webui/icons``).
NAV_ICONS = {
    main.OVERVIEW: "home",
    main.ACTIVITY: "sync",
    main.ANNOUNCEMENTS: "campaign",
    main.COURSES: "school",
    main.CALENDAR: "calendar_month",
}

# A file's extension (``RecentRow.kind``) -> the colored chip in front of its name.
FILE_KINDS = {
    "pdf": ("PDF",),
    "slides": ("PPT", "PPTX", "PPS", "PPSX", "KEY", "ODP"),
    "doc": ("DOC", "DOCX", "ODT", "RTF", "TXT", "PAGE"),
    "sheet": ("XLS", "XLSX", "XLSM", "CSV", "ODS", "NUMB"),
    "archive": ("ZIP", "RAR", "7Z", "TAR", "GZ"),
    "image": ("PNG", "JPG", "JPEG", "GIF", "SVG", "WEBP", "HEIC", "BMP"),
    "note": ("MD", "HTML", "HTM"),
}
_KIND_BY_EXTENSION = {extension: kind for kind, extensions in FILE_KINDS.items() for extension in extensions}

# In the Microsoft Store build the Store owns updates and removal: no switch, no buttons.
PACKAGED_HIDDEN_ROWS = ("check_updates",)


def file_kind(extension: str) -> str:
    """"PDF" -> "pdf", "PPTX" -> "slides"; "other" for anything else (also no extension)."""
    return _KIND_BY_EXTENSION.get(extension.upper(), "other")


def texts() -> dict[str, str]:
    """The fixed words of the page, in the app's language."""
    return {
        "window_title": main.T_WINDOW_TITLE,
        "version": __version__,
        "open_folder": main.T_OPEN_FOLDER,
        "settings": main.T_NAV_GENERAL,
        "view_all": main.T_VIEW_ALL,
        "open_calendar": main.T_OPEN_CALENDAR,
        "open": main.T_OPEN_FILE,
        "show_in_folder": main.T_SHOW_IN_FOLDER,
        "recent_empty": T_RECENT_EMPTY,
        "announcements": main.T_HOME_ANNOUNCEMENTS,
        "upcoming": main.T_HOME_CALENDAR,
        "all_good": main.T_ALL_GOOD,
        "all_good_detail": main.T_ALL_GOOD_DETAIL,
        "new": main.T_NEW,
        "update_intro": main.T_UPDATE_INTRO,
        "unsaved": main.T_UNSAVED,
        "save": form.T_SAVE,
        "cancel": form.T_CANCEL,
    }


def nav(status: main.MainStatus, course_count: str = "") -> list[dict]:
    """The sidebar, top to bottom; a count beside Announcements (attention) and Courses ("4/5")."""
    titles = {
        main.OVERVIEW: status.overview_title,
        main.ACTIVITY: main.T_NAV_ACTIVITY,
        main.ANNOUNCEMENTS: announcements.T_TAB,
        main.COURSES: main.T_NAV_COURSES,
        main.CALENDAR: deadlines.T_TAB,
    }
    badges = {main.ANNOUNCEMENTS: str(len(status.attention)) if status.attention else "",
              main.COURSES: course_count}
    return [{"id": section, "title": titles[section], "icon": NAV_ICONS[section], "badge": badges.get(section, "")}
            for section in main.NAV_SECTIONS]


def chrome(status: main.MainStatus) -> dict:
    """The round buttons at the top right and the account menu behind the initials."""
    card, status_form = status.account, status.form
    return {
        "shows_account": status.shows_account,
        "pause": {"title": status.pause_title, "paused": status.paused, "enabled": status.pause_enabled},
        "account": {
            "initials": card.initials,
            "name": card.title,
            "warning": card.warning,
            "header": status_form.account,
            "action": status_form.account_action,
            "action_title": status_form.account_title,
            "action_enabled": status_form.account_enabled,
        },
    }


def banner(status: main.MainStatus, enabled: bool) -> dict | None:
    """The "new version" card above Home; ``enabled`` is ``updater.enabled()`` (never in the Store build)."""
    update = status.update_banner
    if update is None or not enabled:
        return None
    return {"title": update.title, "button": update.button_title, "enabled": update.enabled}


def home_button(status: main.MainStatus) -> dict | None:
    """At most one button on the status card: what the state asks for (Sign in), else "Sync now".

    Paused has none: the play button at the top right resumes, as in Drive.
    """
    home = status.home
    if home.action:
        return {"id": "home_action", "title": home.action_title, "enabled": True}
    if home.shows_sync:
        return {"id": "sync", "title": status.sync_title, "enabled": status.sync_enabled}
    return None


def recent(rows: tuple[main.RecentRow, ...]) -> list[dict]:
    return [{"id": row.path, "name": row.name, "detail": row.detail, "kind": file_kind(row.kind),
             "extension": row.kind, "new": row.is_new}
            for row in rows[:main.HOME_RECENT_ROWS]]


def attention_items(items) -> list[dict]:
    return [{"id": item.action, "title": item.title, "detail": item.detail,
             "action_title": item.action_title, "warning": item.warning} for item in items]


def home_announcements(status: main.MainStatus, rows) -> tuple[list[dict], list[dict]]:
    """(what needs attention, the newest announcements): three rows at most, attention first."""
    items = status.attention[:main.HOME_ANNOUNCEMENT_ROWS]
    rows = tuple(rows)[:max(main.HOME_ANNOUNCEMENT_ROWS - len(items), 0)]
    return attention_items(items), [{"id": row.key, "title": row.title, "detail": row.detail} for row in rows]


def home_deadlines(page: deadlines.DeadlinePage, today: date) -> tuple[list[dict], str]:
    """(the next due dates, the line shown without any)."""
    rows = deadlines.upcoming_rows(page, main.HOME_DEADLINE_ROWS)
    return ([{"id": row.target, "title": row.title, "detail": f"{deadlines.when_text(row, today)} · {row.course}"}
             for row in rows],
            "" if rows else page.message or main.T_NO_DEADLINES)


def home(status: main.MainStatus, announcement_rows, deadline_page: deadlines.DeadlinePage, today: date) -> dict:
    """Home: the greeting, the status card with the last files, Announcements and the next due dates."""
    state = status.home
    attention, rows = home_announcements(status, announcement_rows)
    upcoming, upcoming_message = home_deadlines(deadline_page, today)
    return {
        "heading": status.home_heading or status.overview_title,
        "subtitle": status.home_subtitle,
        "state": state.kind,
        "title": state.title,
        "detail": state.detail,
        "button": home_button(status),
        "message": status.account.message,
        "message_warning": status.account.warning,
        "scene": status.scene,
        "scene_line": status.scene_line,
        "recent": recent(status.recent),
        "recent_count": main.recent_count(status.recent),
        "attention": attention,
        "announcements": rows,
        "deadlines": upcoming,
        "deadlines_message": upcoming_message,
    }


def start(status: main.MainStatus, error: str) -> dict:
    """Get started, before the first sign-in: three steps and the school/folder form."""
    return {
        "title": main.T_START_TITLE,
        "intro": main.T_START_INTRO,
        "steps": [{"title": title, "text": text} for title, text in main.START_STEPS],
        "reopen": main.reopen_hint(tr("the Start menu")),
        "form_title": main.T_START_FORM,
        "url_label": form.T_URL_LABEL,
        "url_placeholder": form.T_URL_PLACEHOLDER,
        "dest_label": form.T_DEST_LABEL,
        "dest_note": form.T_DEST_ROOT_NOTE,
        "choose": form.T_CHOOSE_FOLDER,
        "autostart": form.T_AUTOSTART,
        "button": {"title": status.start_title, "enabled": status.start_enabled, "login": status.start_login},
        "message": error or status.start_message,
        "message_warning": bool(error),
    }


def activity(status: main.MainStatus) -> dict:
    """Sync activity: the state over every file, note and announcement a sync brought."""
    state = status.home
    return {
        "state": state.kind,
        "title": state.title,
        "detail": state.detail,
        "columns": [main.T_NAME, main.T_SIZE, main.T_STATUS],
        "rows": [{"id": row.path, "name": row.name, "detail": row.detail, "kind": file_kind(row.kind),
                  "size": row.size, "status": row.status} for row in status.activity],
        "empty": main.T_ACTIVITY_EMPTY,
    }


def announcements_page(status: main.MainStatus, rows) -> dict:
    """Announcements: what needs attention, then every synced announcement, newest first."""
    return {
        "hint": announcements.T_HINT,
        "attention_title": main.T_NEEDS_ATTENTION,
        "attention": attention_items(status.attention),
        "rows": [{"id": row.key, "title": row.title, "detail": row.detail, "preview": row.preview} for row in rows],
        "empty": announcements.T_EMPTY,
        "open": announcements.T_OPEN,
    }


def courses_page(rows) -> dict:
    """Courses: one switch per current course; an unticked course is not synced."""
    return {
        "hint": courses.T_HINT,
        "untick": courses.T_UNTICK_HINT,
        "empty": courses.T_EMPTY,
        "rows": [{"id": row.id, "title": main.course_title(row), "detail": main.course_detail(row),
                  "enabled": row.enabled} for row in rows],
    }


def calendar_page(page: deadlines.DeadlinePage) -> dict:
    """Calendar: due dates by day, upcoming first; past ones in their own section."""
    return {
        "hint": deadlines.T_HINT,
        "message": page.message,
        "empty": deadlines.T_EMPTY,
        "upcoming": deadlines.T_UPCOMING,
        "past": deadlines.T_PAST,
        "past_hint": deadlines.T_PAST_HINT,
        "days": [{"title": day.title, "past": day.past,
                  "rows": [{"id": row.target, "time": row.time, "title": row.title, "course": row.course}
                           for row in day.rows]}
                 for day in page.days],
    }


def _choices(key: str, status_form: form.WindowStatus) -> list[dict]:
    if key == "interval":
        return [{"value": minutes, "title": title} for minutes, title in form.INTERVAL_OPTIONS]
    if key == "language":
        return [{"value": code, "title": name} for code, name in form.LANGUAGE_OPTIONS]
    if key == "theme":
        return [{"value": value, "title": title} for value, title in form.THEME_OPTIONS]
    if key == "past_term":
        return [{"value": name, "title": name} for name in status_form.past_terms]
    return []


def _row(definition: form.SettingRow, state: form.RowState | None, status_form: form.WindowStatus,
         packaged: bool) -> dict:
    state = state or form.RowState()
    title = definition.title if state.title is None else state.title
    detail = definition.detail if state.detail is None else state.detail
    button = definition.button if state.button is None else state.button
    has_control = not (packaged and definition.key == "update")
    return {
        "key": definition.key,
        "title": title,
        "detail": detail.strip(),
        "control": definition.control if has_control else "",
        "field": definition.field,
        "button": button,
        "placeholder": definition.placeholder,
        "destructive": definition.destructive,
        "enabled": state.enabled,
        "warning": state.warning,
        "running": state.running,
        "choices": _choices(definition.key, status_form),
        "hidden": False,
    }


CONTROL_BUTTONS = "buttons"  # a row with several buttons (Google Calendar)


def _calendar_rows(rows: list[dict], status_form: form.WindowStatus) -> None:
    """One row: the connection's state on the left, the buttons that apply now on the right."""
    shown = form.calendar_presentation(status_form.calendar, status_form.calendar_busy, status_form.calendar_paused)
    by_key = {row["key"]: row for row in rows}
    buttons = []
    for key, visible in (("google_calendar", shown.show_connect), ("google_calendar_sync", shown.show_sync),
                         ("google_calendar_disconnect", shown.show_disconnect)):
        row = by_key[key]
        if key != "google_calendar":
            row["hidden"] = True
        if visible:
            buttons.append({"key": key, "title": row["button"], "enabled": row["enabled"],
                            "destructive": key == "google_calendar_disconnect"})
    status_row = by_key["google_calendar"]
    status_row["control"] = CONTROL_BUTTONS
    status_row["buttons"] = buttons


def settings(status_form: form.WindowStatus, values: form.FormValues, error: tuple[str, str], packaged: bool,
             theme: str) -> dict:
    """Settings: sections of rows, the saved form values the page edits, and the last save's error."""
    states = form.row_states(status_form)
    sections = []
    for section in form.settings_sections(appearance=True):
        if packaged and section.danger:
            continue  # the Store removes the app; the Updates card says so
        rows = [_row(definition, states.get(definition.key), status_form, packaged) for definition in section.rows
                if not (packaged and definition.key in PACKAGED_HIDDEN_ROWS)]
        if section.key == form.SECTION_CALENDAR:
            _calendar_rows(rows, status_form)
        notes = [updater.STORE_UPDATES, uninstall.STORE_REMOVAL] if packaged and section.key == form.SECTION_UPDATES else []
        sections.append({"key": section.key, "title": section.title, "rows": rows, "footer": section.footer,
                         "danger": section.danger, "notes": notes})
    message, field = error
    return {
        "sections": sections,
        "values": {"base_url": values.base_url, "dest": values.dest, "autostart": values.autostart,
                   "check_updates": values.check_updates, "sync_interval_minutes": values.sync_interval_minutes,
                   "language": values.language},
        "theme": theme,
        "error": message,
        "error_field": field,
    }


def window_state(status: main.MainStatus, section: str, page: str, announcement_rows=(),
                 deadline_page: deadlines.DeadlinePage | None = None, today: date | None = None,
                 course_rows=(), values: form.FormValues | None = None, error: tuple[str, str] = ("", ""),
                 updates_enabled: bool = True, packaged: bool = False, theme: str = THEME_SYSTEM,
                 dialog: dict | None = None) -> dict:
    """Everything the page draws. ``page`` is ``section`` except "start" before the first sign-in."""
    deadline_page = deadline_page or deadlines.DeadlinePage()
    today = today or date.today()
    announcement_rows, course_rows = tuple(announcement_rows), tuple(course_rows)
    values = values or form.FormValues("", "", False)
    return {
        "section": section,
        "page": page,
        "theme": theme,
        "text": texts(),
        "nav": nav(status, main.enabled_count(course_rows)),
        "chrome": chrome(status),
        "banner": banner(status, updates_enabled),
        "home": home(status, announcement_rows, deadline_page, today),
        "start": start(status, error[0]),
        "activity": activity(status),
        "announcements": announcements_page(status, announcement_rows),
        "courses": courses_page(course_rows),
        "calendar": calendar_page(deadline_page),
        "settings": settings(status.form, values, error, packaged, theme),
        "dialog": dialog,
    }


def ids(state: dict) -> dict[str, set[str]]:
    """The ids a click may send back, by kind, from the state the page was given."""
    home_state = state["home"]
    settings_state = state["settings"]
    rows = [row for section in settings_state["sections"] for row in section["rows"]]
    return {
        "file": {row["id"] for row in home_state["recent"]} | {row["id"] for row in state["activity"]["rows"]},
        "announcement": ({row["id"] for row in home_state["announcements"]}
                         | {row["id"] for row in state["announcements"]["rows"]}),
        "deadline": ({row["id"] for row in home_state["deadlines"]}
                     | {row["id"] for day in state["calendar"]["days"] for row in day["rows"]}),
        "attention": ({item["id"] for item in home_state["attention"] if item["id"]}
                      | {item["id"] for item in state["announcements"]["attention"] if item["id"]}),
        "course": {row["id"] for row in state["courses"]["rows"]},
        "past_term": {choice["value"] for row in rows if row["key"] == "past_term" for choice in row["choices"]},
        # A settings button that is on the page and enabled.
        "button": ({row["key"] for row in rows
                    if row["control"] == form.CONTROL_BUTTON and row["enabled"] and not row["hidden"]}
                   | {button["key"] for row in rows for button in row.get("buttons", ()) if button["enabled"]}),
    }
