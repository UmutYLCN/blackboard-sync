"""The WebView2 main window's threads and checks, with a fake pywebview (no Windows needed)."""

import threading
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from blackboard_sync import deadlines
from blackboard_sync.announcements import AnnouncementRow
from blackboard_sync.config import Config
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.menubar.settings_form import FormValues, WindowStatus
from blackboard_sync.settings import Settings
from blackboard_sync.windows import web_window
from blackboard_sync.windows.loop import EventLoop
from blackboard_sync.windows.web_window import Bridge, WebHost, WebMainWindow


# -- EventLoop ---------------------------------------------------------------------

def run_loop(loop):
    thread = threading.Thread(target=loop.mainloop, daemon=True)
    thread.start()
    return thread


def test_loop_runs_timers_in_order_and_events_from_other_threads():
    loop = EventLoop()
    ran, threads = [], set()
    done = threading.Event()
    loop.bind("<<wake>>", lambda event: ran.append(("wake", event)) or threads.add(threading.current_thread()))
    loop.after(30, lambda: ran.append("late"))
    loop.after(0, lambda: ran.append("soon"))
    cancelled = loop.after(10, lambda: ran.append("cancelled"))
    loop.after_cancel(cancelled)
    loop.after(60, done.set)
    thread = run_loop(loop)
    threading.Thread(target=lambda: loop.event_generate("<<wake>>", when="tail")).start()
    assert done.wait(2)
    assert ran.index("soon") < ran.index("late")
    assert ("wake", None) in ran and "cancelled" not in ran
    assert threads == {thread}  # every callback on the loop's own thread
    loop.destroy()
    thread.join(2)
    assert not thread.is_alive()


def test_loop_reports_a_failing_callback_and_keeps_going():
    loop = EventLoop()
    reported, done = [], threading.Event()
    loop.report_callback_exception = lambda kind, value, tb: reported.append(kind)
    loop.after(0, lambda: 1 / 0)
    loop.after(5, done.set)
    thread = run_loop(loop)
    assert done.wait(2) and reported == [ZeroDivisionError]
    loop.destroy()
    thread.join(2)


def test_destroy_runs_shutdown_once_and_refuses_new_events_like_tk():
    loop = EventLoop()
    shut = []
    loop.on_destroy.append(lambda: shut.append(1))
    loop.destroy()
    loop.destroy()
    assert shut == [1] and loop.destroyed
    with pytest.raises(RuntimeError):
        loop.event_generate("<<wake>>")
    loop.mainloop()  # returns at once


# -- WebHost and Bridge ----------------------------------------------------------------

class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    def __init__(self, **options):
        self.options = options
        self.events = SimpleNamespace(closing=FakeEvent(), before_show=FakeEvent())
        self.calls = []
        self.on_top = False

    def show(self):
        self.calls.append("show")

    def hide(self):
        self.calls.append("hide")

    def destroy(self):
        self.calls.append("destroy")


class FakeWebview:
    def __init__(self):
        self.windows = []

    def create_window(self, title, **options):
        window = FakeWindow(title=title, **options)
        self.windows.append(window)
        return window


class ImmediateLoop:
    """Runs posted work at once (the tests are the app's thread)."""

    def __init__(self):
        self.destroyed = False

    def after(self, ms, callback, *args):
        if self.destroyed:
            raise RuntimeError("gone")
        callback(*args)


def make_host(loop=None):
    loop = loop or ImmediateLoop()
    host = WebHost(FakeWebview(), loop, light=True, area=(0, 0, 1920, 1040))
    loop.host = host
    return host


def test_window_starts_hidden_with_the_page_and_the_bridge():
    host = make_host()
    options = host.window.options
    assert options["hidden"] is True
    assert isinstance(options["js_api"], Bridge)
    assert "Content-Security-Policy" in options["html"] and "window.app" in options["html"]
    assert options["background_color"] == web_window.BACKGROUND[True]
    assert (options["width"], options["height"]) == (web_window.WIDTH, web_window.HEIGHT)
    assert options["min_size"] == (web_window.MIN_WIDTH, web_window.MIN_HEIGHT)


def test_bridge_exposes_only_its_calls():
    public = {name for name in dir(Bridge(make_host())) if not name.startswith("_")}
    assert public == {"next_state", "navigate", "action", "open_file", "reveal_file", "announcement", "deadline",
                      "attention", "recent_visible"}


@pytest.mark.parametrize("area, expected", [
    ((0, 0, 1920, 1040), (400, 120, 1120, 760)),
    ((0, 0, 900, 600), (20, 20, 860, 520)),  # a small screen: never wider than it allows, never under the minimum
])
def test_initial_geometry_fits_and_centres(area, expected):
    assert web_window.initial_geometry(area) == expected


def test_closing_hides_instead_and_only_quitting_closes():
    host = make_host()
    closed = []
    host.page = SimpleNamespace(close=lambda: closed.append(1), state=SimpleNamespace(open=True))
    (closing,) = host.window.events.closing.handlers
    assert closing() is False and closed == [1]  # False keeps the window: the app lives on in the tray
    host.quit()
    assert closing() is True and host.window.calls == ["destroy"]


def test_next_state_waits_for_a_newer_state_and_quit_releases_it():
    host = make_host()
    assert host.next_state(0, 0.01) is None  # nothing drawn yet
    host.publish({"page": "overview"})
    assert host.next_state(0, 0.01) == {"revision": 1, "state": {"page": "overview"}}
    assert host.next_state(1, 0.01) is None
    answers = []
    waiter = threading.Thread(target=lambda: answers.append(host.next_state(1, 5)))
    waiter.start()
    time.sleep(0.05)
    host.publish({"page": "calendar"})
    waiter.join(2)
    assert answers == [{"revision": 2, "state": {"page": "calendar"}}]
    waiter = threading.Thread(target=lambda: answers.append(host.next_state(2, 5)))
    waiter.start()
    started = time.monotonic()
    host.quit()
    waiter.join(2)
    assert answers[-1] is None and time.monotonic() - started < 1


def test_bridge_checks_every_argument_before_posting():
    host = make_host()
    calls = []

    class Page:
        def __getattr__(self, name):
            return lambda *args: calls.append((name, *args))

    host.page = Page()
    bridge = Bridge(host)
    bridge.navigate("calendar")
    bridge.navigate("../../etc")
    bridge.action("sync")
    bridge.action("quit")  # not something the page may ask for
    bridge.open_file("Term/CSE303/a.pdf")
    bridge.open_file({"path": "x"})
    bridge.open_file("x" * 5000)
    bridge.recent_visible(["a", 3, "b"], True)
    bridge.recent_visible("not a list", "yes")
    assert calls == [("select", "calendar"), ("run_action", "sync"), ("open_file", "Term/CSE303/a.pdf"),
                     ("recent_visible", ["a", "b"], True), ("recent_visible", [], False)]


def test_posting_after_the_loop_is_gone_is_dropped():
    loop = ImmediateLoop()
    host = make_host(loop)
    host.page = SimpleNamespace(select=lambda section: pytest.fail("ran after quit"))
    loop.destroyed = True
    Bridge(host).navigate("calendar")


# -- WebMainWindow ---------------------------------------------------------------------

FORM = WindowStatus(account="Signed in as Umut", account_warning=False, account_title="Sign out",
                    account_action="logout", account_enabled=True, version="1.6.1", update_title="Check now",
                    update_action="check_updates", update_enabled=True)
RECENT = (main.RecentRow("a.pdf", "CSE303 · today", "Term/CSE303/a.pdf", "PDF", "2026-10-18T09:00:00Z", True),
          main.RecentRow("b.pdf", "CSE303 · today", "Term/CSE303/b.pdf", "PDF", "2026-10-18T09:01:00Z", False))
ROWS = (AnnouncementRow("k1", "CSE301", "Exercise", "15.10.2026", "", "notes/k1.pdf", ""),)


def status(**changes):
    base = main.MainStatus(first_run=False, account=main.AccountCard("U", "Umut", ""), sync_title="Sync now",
                           sync_enabled=True, recent=RECENT, form=FORM,
                           home=main.HomeState(main.STATE_SYNCED, "Up to date", ""), pause_enabled=True,
                           attention=(main.AttentionItem("Update", "", "update", "Update", warning=False),))
    return replace(base, **changes)


class Seen:
    def __init__(self, changed=False):
        self.calls, self.changed = [], changed

    def show(self):
        self.calls.append("show")

    def hide(self):
        self.calls.append("hide")

    def observe(self, visible, active):
        self.calls.append(("observe", visible, active))
        return self.changed and active  # as RecentSeen: nothing is seen while inactive


def make_window(**overrides):
    host = make_host()
    events = []
    due = datetime(2026, 10, 18, 20, tzinfo=timezone.utc)
    page = deadlines.DeadlinePage((deadlines.DeadlineDay(due.date(), "", False, (
        deadlines.DeadlineRow("Proposal", "CSE301", due, "https://bb.example/p"),)),), "")
    options = dict(
        on_values=lambda: FormValues("https://bb.example", "C:/Users/u/Documents", True, True, 60, "en"),
        on_open=lambda path: events.append(("open", path)), on_reveal=lambda path: events.append(("reveal", path)),
        on_deadlines=lambda: page, on_deadline=lambda target: events.append(("deadline", target)),
        on_announcements=lambda: ROWS, on_open_announcement=lambda row: events.append(("announcement", row.key)),
        on_section=lambda section: events.append(("section", section)), recent_seen=Seen(),
        on_seen=lambda: events.append("seen"), today=lambda: date(2026, 10, 18))
    options.update(overrides)
    window = WebMainWindow(host.loop, None, status(),
                           lambda values, login: events.append(("submit", login)),
                           lambda action: events.append(("action", action)), lambda: events.append("closed"),
                           **options)
    return window, host, events


def test_the_window_publishes_what_it_draws_and_shows_on_request():
    window, host, events = make_window()
    first = host.next_state(0, 0.01)
    assert first["state"]["page"] == main.OVERVIEW and first["state"]["home"]["recent"][0]["id"] == "Term/CSE303/a.pdf"
    window.update_status(status())  # the same picture: nothing new for the page
    assert host.next_state(1, 0.01) is None
    window.show()
    assert host.window.calls[:1] == ["show"] and window.state.open
    assert window.recent_seen.calls == ["show"]  # Home is in view: the badges freeze for this visit
    window.select(main.CALENDAR)
    assert host.next_state(1, 0.01)["state"]["section"] == main.CALENDAR
    assert events[-1] == ("section", main.CALENDAR) and window.recent_seen.calls[-1] == "hide"


def test_clicks_act_only_on_ids_the_page_was_given():
    window, host, events = make_window()
    window.open_file("Term/CSE303/a.pdf")
    window.open_file("C:/Windows/System32/calc.exe")
    window.reveal_file("Term/CSE303/b.pdf")
    window.open_deadline("https://bb.example/p")
    window.open_deadline("https://evil.example/")
    window.open_announcement("k1")
    window.open_announcement("k2")
    window.run_attention("update")
    window.run_attention("uninstall")
    assert events == [("open", "Term/CSE303/a.pdf"), ("reveal", "Term/CSE303/b.pdf"),
                      ("deadline", "https://bb.example/p"), ("announcement", "k1"), ("action", "update")]


def test_actions_map_to_the_tray_app():
    window, host, events = make_window()
    for name in ("sync", "pause", "folder", "update", "home_action"):
        window.run_action(name)
    assert events == [("action", "sync"), ("action", "pause"), ("action", "folder"), ("action", "check_updates")]
    window.status = status(home=main.HomeState(main.STATE_ATTENTION, "Sign-in needed", "", "login", "Sign in"))
    window.run_action("home_action")
    assert events[-1] == ("action", "login")
    window.run_action("account")
    assert events[-1] == ("action", "logout")
    window.status = status(form=replace(FORM, account_action="login", account_title="Sign in"))
    window.run_action("account")
    assert events[-1] == ("submit", True)  # signs in with the saved school


def test_recent_badges_count_only_while_home_is_in_view_with_the_focus():
    seen = Seen(changed=True)
    window, host, events = make_window(recent_seen=seen)
    window.recent_visible(["Term/CSE303/a.pdf", "not/drawn.pdf"], True)
    assert seen.calls[-1] == ("observe", [], False)  # the window is not open yet
    window.show()
    window.recent_visible(["Term/CSE303/a.pdf", "not/drawn.pdf"], True)
    assert seen.calls[-1] == ("observe", [("Term/CSE303/a.pdf", "2026-10-18T09:00:00Z")], True)
    assert events.count("seen") == 1


def test_close_hides_and_tells_the_tray_app_once():
    window, host, events = make_window()
    window.show()
    window.close()
    window.close()
    assert host.window.calls.count("hide") == 1 and events.count("closed") == 1 and not window.state.open


# -- TrayApp in WebView2 mode ----------------------------------------------------------

def make_app(tmp_path):
    from blackboard_sync.windows.app import TrayApp

    app = TrayApp.__new__(TrayApp)
    app.config = Config(data_dir=tmp_path, dest=tmp_path / "old")
    app.settings = Settings("https://old.school.edu", tmp_path / "old")
    app.login_after_job = False
    app.uninstalling = False
    app.model = AppModel(app.settings.dest, datetime.now(timezone.utc))
    app.save = lambda: None
    app.refresh = lambda: None
    app.window = None
    app.root = None
    return app


def test_tray_app_asks_through_native_boxes_with_the_web_window(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import jobs

    app = make_app(tmp_path)
    asked = []
    app.web = SimpleNamespace(ask_yes_no=lambda title, message: asked.append(title) or True,
                              show_message=lambda kind, title, message: asked.append((kind, message)))
    removed = []
    monkeypatch.setattr(jobs, "logout", removed.append)
    app.dispatch("logout")
    assert asked == ["Sign out?"] and len(removed) == 1
    app.model.begin("sync")
    app.dispatch("quit")
    assert asked[-1][0] == "info"  # busy: says so instead of quitting


def test_web_mode_falls_back_to_tk_where_webview2_cannot_run(tmp_path, monkeypatch):
    from blackboard_sync.windows import app as tray

    def unavailable(loop):
        raise RuntimeError("no WebView2")

    monkeypatch.setattr(WebHost, "create", classmethod(lambda cls, loop: unavailable(loop)))
    assert tray.run_web(Config(data_dir=tmp_path, dest=tmp_path), True, lock=None) is False
