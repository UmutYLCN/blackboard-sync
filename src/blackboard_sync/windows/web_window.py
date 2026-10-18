"""The main window as a WebView2 page (pywebview), in place of the Tk window.

Three threads take part:

- the main thread runs pywebview's GUI loop (``WebHost.run``); the window is made
  hidden before it starts and only ever hidden again, never destroyed, until the
  app quits, because the loop ends with its last window;
- the app's thread runs ``loop.EventLoop`` with ``TrayApp`` and ``WebMainWindow``,
  which own all state, as the Tk root's thread does for the Tk window;
- pywebview runs each call from the page on a worker thread: ``Bridge`` checks the
  arguments and posts the work to the app's thread.

The page asks for new states itself (``Bridge.next_state`` waits until there is
one), so the app's thread never blocks on the GUI; only a question (``WebHost.ask``)
waits on it, for the student's answer, while the page keeps drawing. What the page
shows comes from ``webui_state``; a click names only an id from the last state,
checked here.
"""

from __future__ import annotations

import itertools
import logging
import os
import sys
import threading
from datetime import datetime

from blackboard_sync import deadlines, uninstall, updater
from blackboard_sync.i18n import LANGUAGES, language, tr
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.settings import THEME_DARK, THEME_LIGHT, THEME_SYSTEM, THEMES
from blackboard_sync.windows import webui_page, webui_state

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1120, 760  # what it opens with when the work area has room
MIN_WIDTH, MIN_HEIGHT = 860, 560
CHROME = 40  # title bar and borders Windows adds (pixels)
BACKGROUND = {True: "#F1F4F9", False: "#111317"}  # app.css --bg, light and dark: no white flash
STATE_WAIT = 20.0  # seconds a page's request for a new state waits before it asks again
QUIT_GRACE = 10.0  # seconds pywebview's loop gets to end after Quit before the process ends anyway
# What the page may ask the window to do (``Bridge.action``, ``Bridge.setting``).
ACTIONS = ("sync", "pause", "folder", "update", "home_action", "account")
SETTING_BUTTONS = ("account", "past_download", "update", "uninstall", "google_calendar", "google_calendar_sync",
                   "google_calendar_disconnect")
CALENDAR_ACTIONS = {"google_calendar": "calendar_connect", "google_calendar_sync": "calendar_sync",
                    "google_calendar_disconnect": "calendar_disconnect"}
MAX_ID = 4096  # an id is a path, a URL or a key; anything longer was not handed out
MAX_VISIBLE = 64
INTERVALS = tuple(minutes for minutes, _ in form.INTERVAL_OPTIONS)
LANGUAGE_CODES = tuple(code for code, _ in LANGUAGES)

# MessageBoxW flags (winuser.h)
MB_OK, MB_YESNO = 0x0, 0x4
MB_ICONERROR, MB_ICONQUESTION, MB_ICONWARNING, MB_ICONINFORMATION = 0x10, 0x20, 0x30, 0x40
MB_SETFOREGROUND = 0x10000
IDYES = 6
MESSAGE_ICONS = {"info": MB_ICONINFORMATION, "warning": MB_ICONWARNING, "error": MB_ICONERROR}
# ShowWindow / SetWindowPos (winuser.h), DwmSetWindowAttribute (dwmapi.h)
SW_RESTORE = 9
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x1, 0x2, 0x40
DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def initial_geometry(area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """(x, y, width, height): the default size, never larger than the work area, centred in it."""
    left, top, width, height = area
    inner_width = min(WIDTH, max(MIN_WIDTH, width - 40))
    inner_height = form.window_height(HEIGHT, CHROME, height) - CHROME
    return (left + max(0, (width - inner_width) // 2), top + max(0, (height - inner_height - CHROME) // 2),
            inner_width, inner_height)


def is_light(theme: str, windows_light: bool) -> bool:
    """Whether the window draws light: the chosen theme, or Windows' own for "System"."""
    return {THEME_LIGHT: True, THEME_DARK: False}.get(theme, windows_light)


def _text(value, limit: int = MAX_ID) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


def form_values(data) -> form.FormValues | None:
    """The page's edited form as ``FormValues``; None unless every field has the right type.

    The texts are validated by ``settings_form.submit`` like typed ones; only the type is checked here.
    """
    if not isinstance(data, dict):
        return None
    base_url, dest = data.get("base_url"), data.get("dest")
    interval, code = data.get("sync_interval_minutes"), data.get("language")
    switches = data.get("autostart"), data.get("check_updates")
    if not (isinstance(base_url, str) and len(base_url) <= 2048 and isinstance(dest, str) and len(dest) <= MAX_ID):
        return None
    if any(not isinstance(value, bool) for value in switches) or isinstance(interval, bool):
        return None
    if interval not in INTERVALS or code not in LANGUAGE_CODES:
        return None
    return form.FormValues(base_url, dest, switches[0], switches[1], interval, code)


class Bridge:
    """The page's ``window.pywebview.api``: every public method is callable from JavaScript.

    Runs on pywebview's worker threads; nothing here touches the app's state directly.
    """

    def __init__(self, host: "WebHost"):
        self._host = host

    def next_state(self, revision=0):
        """The newest state once it is newer than ``revision`` (or None after a while: ask again)."""
        return self._host.next_state(revision if isinstance(revision, int) else 0, STATE_WAIT)

    def navigate(self, section):
        if section in main.SECTIONS:
            self._host.post("select", section)

    def action(self, name):
        if name in ACTIONS:
            self._host.post("run_action", name)

    def open_file(self, ident):
        self._post_id("open_file", ident)

    def reveal_file(self, ident):
        self._post_id("reveal_file", ident)

    def announcement(self, ident):
        self._post_id("open_announcement", ident)

    def deadline(self, ident):
        self._post_id("open_deadline", ident)

    def attention(self, ident):
        self._post_id("run_attention", ident)

    def recent_visible(self, idents=(), active=False):
        if not isinstance(idents, list) or len(idents) > MAX_VISIBLE:
            idents = []
        self._host.post("recent_visible", [ident for ident in idents if _text(ident)], active is True)

    def toggle_course(self, ident, enabled):
        if _text(ident) and isinstance(enabled, bool):
            self._host.post("toggle_course", ident, enabled)

    def save(self, values, login=False):
        values = form_values(values)
        if values is not None and isinstance(login, bool):
            self._host.post("save", values, login)

    def cancel_form(self):
        self._host.post("cancel_form")

    def setting(self, key, value=""):
        if key in SETTING_BUTTONS and isinstance(value, str) and len(value) <= MAX_ID:
            self._host.post("run_setting", key, value)

    def set_theme(self, theme):
        if theme in THEMES:
            self._host.post("set_theme", theme)

    def choose_folder(self):
        """The native folder picker; the chosen path goes into the form (saved and checked on Save)."""
        return self._host.choose_folder()

    def dialog_answer(self, ident, button=None, checked=False):
        if _text(ident) and (button is None or _text(button)):
            self._host.answer(ident, button, checked is True)

    def _post_id(self, method, ident):
        ident = _text(ident)
        if ident is not None:
            self._host.post(method, ident)


class WebHost:
    """The pywebview window and what crosses between its threads and the app's."""

    def __init__(self, webview, loop, theme: str, windows_light: bool, area: tuple[int, int, int, int]):
        self.webview, self.loop = webview, loop
        self.windows_light = windows_light
        self.page = None  # the WebMainWindow, once the app shows the window
        self._condition = threading.Condition()
        self._revision = 0
        self._state = None
        self._quitting = False
        self._running = False  # pywebview's loop runs (``run``): Quit must end the process
        self._hwnd = None
        self._theme = theme
        self._question = None  # (id, threading.Event, [answer]) while the page asks something
        self._ids = itertools.count(1)
        x, y, width, height = initial_geometry(area)
        self.window = webview.create_window(
            main.T_WINDOW_TITLE, html=webui_page.document(lang=language(), theme=theme), js_api=Bridge(self),
            x=x, y=y, width=width, height=height, min_size=(MIN_WIDTH, MIN_HEIGHT), hidden=True,
            background_color=BACKGROUND[is_light(theme, windows_light)], text_select=False, zoomable=False)
        self.window.events.closing += self._closing
        self.window.events.before_show += self._remember_handle

    @classmethod
    def create(cls, loop, theme: str = THEME_SYSTEM):
        """Load WebView2 and make the hidden window; raises where WebView2 cannot run (use Tk then)."""
        from blackboard_sync.inapp_windows import _load_webview2
        from blackboard_sync.windows.main_window import work_area
        from blackboard_sync.windows.theme import windows_uses_light_theme

        return cls(_load_webview2(), loop, theme, windows_uses_light_theme(), work_area())

    def run(self, app_main) -> None:
        """Run pywebview's loop on this (the main) thread and ``app_main`` on the app's; returns at quit."""
        from blackboard_sync.inapp_windows import GUI

        def start():
            threading.Thread(target=app_main, name="app", daemon=True).start()

        self._running = True
        self.webview.start(start, gui=GUI, private_mode=True)

    # -- the app's thread asks ---------------------------------------------------
    def publish(self, state: dict) -> None:
        """Hand the page a new state; its waiting ``next_state`` returns it at once."""
        with self._condition:
            self._revision += 1
            self._state = state
            self._condition.notify_all()

    def show(self) -> None:
        self.window.show()
        if self._hwnd is not None:
            bring_to_front(self._hwnd)

    def hide(self) -> None:
        self.window.hide()

    def set_theme(self, theme: str) -> None:
        """The title bar follows the page's theme (Windows draws it light unless asked)."""
        self._theme = theme
        if self._hwnd is not None:
            dark_title_bar(self._hwnd, not is_light(theme, self.windows_light))

    def quit(self) -> None:
        """The app quits: let the window close and pywebview's loop end."""
        with self._condition:
            self._quitting = True
            self._condition.notify_all()
        self._release_question()
        if self._running:
            # Should the window not close (a window that never got shown), the app still ends.
            watchdog = threading.Timer(QUIT_GRACE, os._exit, (0,))
            watchdog.daemon = True
            watchdog.start()
        try:
            self.window.destroy()
        except Exception:
            log.debug("The window was already gone", exc_info=True)

    def ask(self, question: dict) -> tuple[str | None, bool] | None:
        """Show ``question`` as the page's dialog and wait for (button id, checkbox); None if it went away.

        Runs on the app's thread, which waits: pywebview's threads draw the page and bring the answer.
        """
        page = self.page
        if page is None or not page.state.open or self._quitting:
            return None
        ident = f"q{next(self._ids)}"
        event, answer = threading.Event(), []
        self._question = (ident, event, answer)
        page.dialog = {"id": ident, **question}
        page._draw()
        try:
            event.wait()
        finally:
            self._question = None
            page.dialog = None
            page._draw()
        return answer[0] if answer else None

    def ask_yes_no(self, title: str, message: str) -> bool:
        return message_box(title, message, MB_YESNO | MB_ICONQUESTION, self._owner()) == IDYES

    def show_message(self, kind: str, title: str, message: str) -> None:
        message_box(title, message, MB_OK | MESSAGE_ICONS[kind], self._owner())

    def ask_dest_choice(self, old, new, files):
        """Move the downloaded files to the new folder, download them again, or keep the old folder (None)."""
        buttons = [{"id": choice, "title": title, "style": "filled" if index == 0 else "gray", "default": index == 0}
                   for index, (choice, title) in enumerate(form.DEST_CHOICES)]
        answer = self.ask({"title": form.T_DEST_CHANGE_TITLE, "message": form.dest_change_message(old, new, files),
                           "buttons": [{"id": "cancel", "title": form.T_CANCEL, "style": "gray"}] + buttons})
        choice = answer[0] if answer else None
        return choice if choice in dict(form.DEST_CHOICES) else None

    def ask_uninstall(self, dest):
        """Whether to also delete the downloaded files; None keeps the app."""
        answer = self.ask({
            "title": uninstall.TITLE, "message": uninstall.MESSAGE,
            "checkbox": {"label": uninstall.CHECKBOX,
                         "detail": tr("The folder whose files go to the Recycle Bin:") + f"\n{dest}"},
            "buttons": [{"id": "cancel", "title": form.T_CANCEL, "style": "gray", "default": True},
                        {"id": "uninstall", "title": tr("Uninstall"), "style": "danger filled"}]})
        return answer[1] if answer and answer[0] == "uninstall" else None

    def ask_calendar_disconnect(self):
        """Whether to also delete the Blackboard Deadlines calendar; None stays connected."""
        answer = self.ask({
            "title": tr("Disconnect Google Calendar?"),
            "message": tr("Access will be revoked and local Calendar connection data removed."),
            "checkbox": {"label": tr("Also delete the Blackboard Deadlines calendar from Google"), "detail": ""},
            "buttons": [{"id": "cancel", "title": form.T_CANCEL, "style": "gray", "default": True},
                        {"id": "disconnect", "title": tr("Disconnect"), "style": "danger filled"}]})
        return answer[1] if answer and answer[0] == "disconnect" else None

    # -- pywebview's threads ask ---------------------------------------------------
    def next_state(self, known: int, timeout: float):
        with self._condition:
            if self._revision <= known and not self._quitting:
                self._condition.wait_for(lambda: self._revision > known or self._quitting, timeout)
            if self._revision > known and self._state is not None:
                return {"revision": self._revision, "state": self._state}
            return None

    def answer(self, ident: str, button: str | None, checked: bool) -> None:
        question = self._question
        if question is not None and question[0] == ident:
            question[2].append((button, checked))
            question[1].set()

    def choose_folder(self) -> str | None:
        try:
            chosen = self.window.create_file_dialog(self.webview.FileDialog.FOLDER)
        except Exception:
            log.exception("The folder picker failed")
            return None
        if isinstance(chosen, (list, tuple)):
            chosen = chosen[0] if chosen else None
        return chosen if isinstance(chosen, str) and chosen else None

    def post(self, method: str, *args) -> None:
        """Run ``WebMainWindow.<method>(*args)`` on the app's thread (dropped when no page is shown)."""
        def run():
            page = self.page
            if page is not None:
                getattr(page, method)(*args)
        try:
            self.loop.after(0, run)
        except RuntimeError:
            pass  # quitting

    def _closing(self):
        """The window's close button: hide it (the app lives on in the tray); False keeps it."""
        if self._quitting:
            return True
        self._release_question()  # a question in the closed window is answered "no"
        self.post("close")
        return False

    def _release_question(self):
        question = self._question
        if question is not None:
            question[1].set()

    def _remember_handle(self):
        try:
            self._hwnd = int(self.window.native.Handle.ToInt64())
            dark_title_bar(self._hwnd, not is_light(self._theme, self.windows_light))
        except Exception:
            log.debug("No window handle for dialogs and the title bar", exc_info=True)

    def _owner(self):
        page = self.page
        return self._hwnd if page is not None and page.state.open else None


def _user32():
    if sys.platform != "win32":
        raise RuntimeError("this needs Windows")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT)
    user32.IsIconic.argtypes = user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    return user32


def message_box(title: str, message: str, flags: int, owner=None) -> int:
    """A native Windows message box (any thread); modal over ``owner`` when given."""
    return _user32().MessageBoxW(owner, message, title, flags | MB_SETFOREGROUND)


def bring_to_front(hwnd: int) -> None:
    """Restore a minimized window (a maximized one stays so) and put it in front.

    Windows keeps a new window behind the active one (the installer, Explorer); topmost for a
    moment brings it forward, as the Tk window does. Plain Win32 calls: safe from any thread.
    """
    user32 = _user32()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    for where in (HWND_TOPMOST, HWND_NOTOPMOST):
        user32.SetWindowPos(hwnd, where, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    user32.SetForegroundWindow(hwnd)


def dark_title_bar(hwnd: int, dark: bool) -> None:
    """Draw the window's title bar dark or light (Windows 10 20H1 and later; ignored before)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    value = ctypes.c_int(1 if dark else 0)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE,
                                                   ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        log.debug("Could not set the title bar's theme", exc_info=True)


class WebMainWindow:
    """The main window for ``TrayApp``: the same calls as the Tk ``MainWindow``, drawn as a page.

    Lives on the app's thread. ``root`` is the app's ``EventLoop``; its ``host`` is the ``WebHost``.
    """

    def __init__(self, root, values, status, on_submit, on_action, on_close, on_values=None,
                 on_open=lambda path: None, on_courses=lambda: (),
                 on_course_toggle=lambda course_id, enabled: None, on_past_term=lambda name: None,
                 on_section=lambda section: None, on_deadlines=deadlines.DeadlinePage,
                 on_deadline=lambda target: None, recent_seen=None, on_seen=lambda: None,
                 on_announcements=lambda: (), on_open_announcement=lambda row: None,
                 on_reveal=lambda path: None, theme=lambda: THEME_SYSTEM, on_theme=lambda theme: None,
                 packaged=lambda: False, today=lambda: datetime.now().astimezone().date()):
        self.host = root.host
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_values = on_values or (lambda: values)
        self.on_open, self.on_reveal = on_open, on_reveal
        self.on_courses, self.on_course_toggle, self.on_past_term = on_courses, on_course_toggle, on_past_term
        self.on_section = on_section
        self.on_deadlines, self.on_deadline = on_deadlines, on_deadline
        self.recent_seen, self.on_seen = recent_seen, on_seen
        self.on_announcements, self.on_open_announcement = on_announcements, on_open_announcement
        self.theme, self.on_theme, self.packaged, self.today = theme, on_theme, packaged, today
        self.state = main.WindowState()
        self.status = status
        self.saved = values
        self.error = ("", "")  # the last Save's (message, field)
        self.dialog = None  # the question ``WebHost.ask`` shows
        self.window = self  # TrayApp's dialogs ask "in front of" ``window.window``
        self._generation = 0  # a new one drops the page's unsaved edits
        self._ids: dict[str, set[str]] = {}
        self._announcements: dict[str, object] = {}
        self._drawn = None
        self.host.page = self
        self._draw()

    # -- what TrayApp calls --------------------------------------------------------
    def show(self, section=None):
        """Open the window (or bring it forward) on ``section``; see ``WindowState.show``."""
        self.state.show(section)
        self._section_changed()
        self._draw()
        self.host.show()

    def select(self, section):
        self.state.select(section)
        self._section_changed()
        self._draw()
        self.on_section(section)

    def update_status(self, status):
        self.status = status
        self._draw()

    def close(self):
        """The close button: hide the window; unsaved edits are dropped, the app keeps running in the tray."""
        if not self.state.open:
            return
        self.host.hide()
        self.state.closed()
        if self.recent_seen is not None:
            self.recent_seen.hide()
        self._reset_form()
        self.on_close()

    def destroy(self):
        """Before uninstalling: the page goes; the window itself closes when the app quits."""
        self.state.closed()
        if self.recent_seen is not None:
            self.recent_seen.hide()
        self.host.hide()
        self.host.page = None

    def visible_page(self):
        section = self.state.section
        return "start" if section == main.OVERVIEW and self.status.first_run else section

    # -- what the page asks (through WebHost.post) -----------------------------------
    def run_action(self, name):
        status = self.status
        if name == "home_action":
            if status.home.action:
                self.on_action(status.home.action)
        elif name == "update":
            self.on_action(status.form.update_action)
        elif name == "account":
            self.account_pressed()
        else:
            self.on_action(name)

    def account_pressed(self):
        if self.status.form.account_action == "login":
            self.save(self.on_values(), True)  # sign in with the saved school address
        elif self.status.form.account_enabled:
            self.on_action(self.status.form.account_action)

    def run_setting(self, key, value):
        """A button on Settings, while it is on the page and enabled."""
        if key not in self._ids.get("button", ()):
            return
        if key == "account":
            self.account_pressed()
        elif key == "past_download":
            if value in self._ids.get("past_term", ()) and self.status.form.past_enabled:
                self.on_past_term(value)
        elif key == "update":
            self.on_action(self.status.form.update_action)
        elif key == "uninstall":
            self.on_action("uninstall")
        else:
            self.on_action(CALENDAR_ACTIONS[key])

    def save(self, values, login):
        """Save (or sign in from Get started); the window stays open either way."""
        error = self.on_submit(values, login)
        if error is None:
            self.saved = self.on_values()
            self.error = ("", "")
            self._generation += 1
        else:
            self.error = (error[0], error[1] or "base_url")
        self._draw()

    def cancel_form(self):
        self._reset_form()
        self._draw()

    def toggle_course(self, ident, enabled):
        if ident in self._ids.get("course", ()):
            self.on_course_toggle(ident, enabled)
            self._draw()

    def set_theme(self, theme):
        self.on_theme(theme)
        self.host.set_theme(theme)
        self._draw()

    def open_file(self, ident):
        if ident in self._ids.get("file", ()):
            self.on_open(ident)

    def reveal_file(self, ident):
        if ident in self._ids.get("file", ()):
            self.on_reveal(ident)

    def open_announcement(self, ident):
        if ident in self._ids.get("announcement", ()):
            self.on_open_announcement(self._announcements[ident])

    def open_deadline(self, ident):
        if ident in self._ids.get("deadline", ()):
            self.on_deadline(ident)

    def run_attention(self, ident):
        if ident in self._ids.get("attention", ()):
            self.on_action(ident)

    def recent_visible(self, idents, active):
        """The page's sample of the last files on screen, every half second while it has the focus."""
        if self.recent_seen is None:
            return
        active = active and self.state.open and self.visible_page() == main.OVERVIEW
        shown = set(idents) if active else set()
        visible = [(row.path, row.at) for row in self.status.recent if row.path in shown]
        if self.recent_seen.observe(visible, active):
            self.on_seen()

    # -- inside --------------------------------------------------------------------
    def _reset_form(self):
        self.saved = self.on_values()
        self.error = ("", "")
        self._generation += 1

    def _section_changed(self):
        if self.recent_seen is None:
            return
        if self.state.open and self.visible_page() == main.OVERVIEW:
            self.recent_seen.show()
        else:
            self.recent_seen.hide()

    def _draw(self):
        rows = tuple(self.on_announcements())
        self._announcements = {row.key: row for row in rows}
        state = webui_state.window_state(
            self.status, self.state.section, self.visible_page(), rows, self.on_deadlines(), self.today(),
            course_rows=tuple(self.on_courses()), values=self.saved, error=self.error,
            updates_enabled=updater.enabled(), packaged=self.packaged(), theme=self.theme(), dialog=self.dialog)
        state["settings"]["generation"] = self._generation
        self._ids = webui_state.ids(state)
        if state != self._drawn:
            self._drawn = state
            self.host.publish(state)
