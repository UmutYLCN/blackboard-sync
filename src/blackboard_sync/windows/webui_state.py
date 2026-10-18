"""What the WebView2 main window draws, as plain data for JSON; no GUI code.

The page (``webui/app.js``) renders this and nothing else: every text comes from
here (through ``i18n.tr``), and a click sends back only an id this module handed
out. ``WebMainWindow`` checks such an id against the last state it drew before
acting on it, so the page can never name a file or address of its own.

The model is the same as the Tk window's and macOS's (``menubar/main_window_model``).
"""

from __future__ import annotations

from datetime import date

from blackboard_sync import __version__, announcements, deadlines
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar.model import T_RECENT_EMPTY

# The sidebar's icon for each section (Material Symbols names, see ``webui_page.ICONS``).
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
    card, form = status.account, status.form
    return {
        "shows_account": status.shows_account,
        "pause": {"title": status.pause_title, "paused": status.paused, "enabled": status.pause_enabled},
        "account": {
            "initials": card.initials,
            "name": card.title,
            "warning": card.warning,
            "header": form.account,
            "action": form.account_action,
            "action_title": form.account_title,
            "action_enabled": form.account_enabled,
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


def home_announcements(status: main.MainStatus, rows) -> tuple[list[dict], list[dict]]:
    """(what needs attention, the newest announcements): three rows at most, attention first."""
    items = status.attention[:main.HOME_ANNOUNCEMENT_ROWS]
    rows = tuple(rows)[:max(main.HOME_ANNOUNCEMENT_ROWS - len(items), 0)]
    attention = [{"id": item.action, "title": item.title, "detail": item.detail,
                  "action_title": item.action_title, "warning": item.warning} for item in items]
    return attention, [{"id": row.key, "title": row.title, "detail": row.detail} for row in rows]


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


def window_state(status: main.MainStatus, section: str, page: str, announcement_rows,
                 deadline_page: deadlines.DeadlinePage, today: date, course_count: str = "",
                 updates_enabled: bool = True) -> dict:
    """Everything the page draws. ``page`` is ``section`` except "start" before the first sign-in."""
    return {
        "section": section,
        "page": page,
        "text": texts(),
        "nav": nav(status, course_count),
        "chrome": chrome(status),
        "banner": banner(status, updates_enabled),
        "home": home(status, announcement_rows, deadline_page, today),
    }


def ids(state: dict) -> dict[str, set[str]]:
    """The ids a click may send back, by kind, from the state the page was given."""
    home_state = state["home"]
    return {
        "file": {row["id"] for row in home_state["recent"]},
        "announcement": {row["id"] for row in home_state["announcements"]},
        "deadline": {row["id"] for row in home_state["deadlines"]},
        "attention": {item["id"] for item in home_state["attention"] if item["id"]},
    }
