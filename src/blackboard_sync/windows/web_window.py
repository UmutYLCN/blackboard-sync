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
one), so the app's thread never blocks on the GUI. What the page shows comes
from ``webui_state``; a click names only an id from the last state, checked here.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime

from blackboard_sync import deadlines, updater
from blackboard_sync.i18n import language
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar import settings_form as form
from blackboard_sync.windows import webui_page, webui_state

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1120, 760  # what it opens with when the work area has room
MIN_WIDTH, MIN_HEIGHT = 860, 560
CHROME = 40  # title bar and borders Windows adds (pixels)
BACKGROUND = {True: "#F1F4F9", False: "#111317"}  # app.css --bg, light and dark: no white flash
STATE_WAIT = 20.0  # seconds a page's request for a new state waits before it asks again
QUIT_GRACE = 10.0  # seconds pywebview's loop gets to end after Quit before the process ends anyway
# What the page may ask the window to do (``Bridge.action``).
ACTIONS = ("sync", "pause", "folder", "update", "home_action", "account")
MAX_ID = 4096  # an id is a path, a URL or a key; anything longer was not handed out
MAX_VISIBLE = 64

# MessageBoxW flags (winuser.h)
MB_OK, MB_YESNO = 0x0, 0x4
MB_ICONERROR, MB_ICONQUESTION, MB_ICONWARNING, MB_ICONINFORMATION = 0x10, 0x20, 0x30, 0x40
MB_SETFOREGROUND = 0x10000
IDYES = 6
# ShowWindow / SetWindowPos (winuser.h)
SW_RESTORE = 9
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x1, 0x2, 0x40
MESSAGE_ICONS = {"info": MB_ICONINFORMATION, "warning": MB_ICONWARNING, "error": MB_ICONERROR}


def initial_geometry(area: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """(x, y, width, height): the default size, never larger than the work area, centred in it."""
    left, top, width, height = area
    inner_width = min(WIDTH, max(MIN_WIDTH, width - 40))
    inner_height = form.window_height(HEIGHT, CHROME, height) - CHROME
    return (left + max(0, (width - inner_width) // 2), top + max(0, (height - inner_height - CHROME) // 2),
            inner_width, inner_height)


def _text(value, limit: int = MAX_ID) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


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

    def _post_id(self, method, ident):
        ident = _text(ident)
        if ident is not None:
            self._host.post(method, ident)


class WebHost:
    """The pywebview window and what crosses between its threads and the app's."""

    def __init__(self, webview, loop, light: bool, area: tuple[int, int, int, int]):
        self.webview, self.loop = webview, loop
        self.page = None  # the WebMainWindow, once the app shows the window
        self._condition = threading.Condition()
        self._revision = 0
        self._state = None
        self._quitting = False
        self._running = False  # pywebview's loop runs (``run``): Quit must end the process
        self._hwnd = None
        x, y, width, height = initial_geometry(area)
        self.window = webview.create_window(
            main.T_WINDOW_TITLE, html=webui_page.document(lang=language()), js_api=Bridge(self),
            x=x, y=y, width=width, height=height, min_size=(MIN_WIDTH, MIN_HEIGHT), hidden=True,
            background_color=BACKGROUND[light], text_select=False, zoomable=False)
        self.window.events.closing += self._closing
        self.window.events.before_show += self._remember_handle

    @classmethod
    def create(cls, loop):
        """Load WebView2 and make the hidden window; raises where WebView2 cannot run (use Tk then)."""
        from blackboard_sync.inapp_windows import _load_webview2
        from blackboard_sync.windows.main_window import work_area
        from blackboard_sync.windows.theme import windows_uses_light_theme

        return cls(_load_webview2(), loop, windows_uses_light_theme(), work_area())

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

    def quit(self) -> None:
        """The app quits: let the window close and pywebview's loop end."""
        with self._condition:
            self._quitting = True
            self._condition.notify_all()
        if self._running:
            # Should the window not close (a window that never got shown), the app still ends.
            watchdog = threading.Timer(QUIT_GRACE, os._exit, (0,))
            watchdog.daemon = True
            watchdog.start()
        try:
            self.window.destroy()
        except Exception:
            log.debug("The window was already gone", exc_info=True)

    def ask_yes_no(self, title: str, message: str) -> bool:
        return message_box(title, message, MB_YESNO | MB_ICONQUESTION, self._owner()) == IDYES

    def show_message(self, kind: str, title: str, message: str) -> None:
        message_box(title, message, MB_OK | MESSAGE_ICONS[kind], self._owner())

    def ask_dest_choice(self, old, new, files):
        # The page's own dialog comes with the Settings page; until then nothing changes the folder here.
        log.warning("Folder change asked without the Settings page; not changing it")
        return None

    def ask_uninstall(self, dest):
        log.warning("Uninstall asked without the Settings page; not uninstalling")
        return None

    # -- pywebview's threads ask ---------------------------------------------------
    def next_state(self, known: int, timeout: float):
        with self._condition:
            if self._revision <= known and not self._quitting:
                self._condition.wait_for(lambda: self._revision > known or self._quitting, timeout)
            if self._revision > known and self._state is not None:
                return {"revision": self._revision, "state": self._state}
            return None

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
        self.post("close")
        return False

    def _remember_handle(self):
        try:
            self._hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:
            log.debug("No window handle for dialogs", exc_info=True)

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
                 on_reveal=lambda path: None, today=lambda: datetime.now().astimezone().date()):
        self.host = root.host
        self.on_submit, self.on_action, self.on_close = on_submit, on_action, on_close
        self.on_values = on_values or (lambda: values)
        self.on_open, self.on_reveal = on_open, on_reveal
        self.on_courses, self.on_course_toggle, self.on_past_term = on_courses, on_course_toggle, on_past_term
        self.on_section = on_section
        self.on_deadlines, self.on_deadline = on_deadlines, on_deadline
        self.recent_seen, self.on_seen = recent_seen, on_seen
        self.on_announcements, self.on_open_announcement = on_announcements, on_open_announcement
        self.today = today
        self.state = main.WindowState()
        self.status = status
        self.window = self  # TrayApp's dialogs ask "in front of" ``window.window``
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
        """The close button: hide the window; the app keeps running in the tray."""
        if not self.state.open:
            return
        self.host.hide()
        self.state.closed()
        if self.recent_seen is not None:
            self.recent_seen.hide()
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
            error = self.on_submit(self.on_values(), True)  # sign in with the saved school address
            if error is not None:
                log.info("Sign-in from the account menu refused: %s", error[0])
        elif self.status.form.account_enabled:
            self.on_action(self.status.form.account_action)

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
            course_count=main.enabled_count(tuple(self.on_courses())), updates_enabled=updater.enabled())
        self._ids = webui_state.ids(state)
        if state != self._drawn:
            self._drawn = state
            self.host.publish(state)
