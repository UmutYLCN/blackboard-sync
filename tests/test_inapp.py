"""The in-app sign-in window: when it is used instead of a browser, and how its
cookies become the saved session. The window itself is replaced by a stub, so
these run on any OS without a display."""

import subprocess
import threading
from http.cookies import SimpleCookie
from types import SimpleNamespace

import pytest

from blackboard_sync import login as login_mod
from blackboard_sync.cli import build_parser
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.inapp import (
    CLOSED_MESSAGE,
    INAPP,
    Outcome,
    blackboard_cookies,
    cookies_from_nshttpcookies,
    cookies_from_simple_cookies,
    watch_for_session,
)
from blackboard_sync.login import (
    DEVTOOLS_PORT_FILE,
    NoSupportedBrowserError,
    choose_browser,
    login,
    login_method_label,
)
from blackboard_sync.session import load_session, save_session

from .conftest import BASE_URL, assert_owner_only

USER = {"id": "_900_1", "userName": "student.example", "name": {"given": "Ada", "family": "Yılmaz"}}
BB_COOKIES = [
    {"name": "BbRouter", "value": "expires:1,id:A", "domain": "blackboard.example.edu", "path": "/",
     "secure": True, "expires": None},
    {"name": "JSESSIONID", "value": "j", "domain": "blackboard.example.edu", "path": "/webapps",
     "secure": True, "expires": 4102444800.0},
]
IDP_COOKIE = {"name": "ESTSAUTH", "value": "idp", "domain": ".login.microsoftonline.com", "path": "/",
              "secure": True, "expires": None}


def _apps(tmp_path, *names):
    for name in names:
        (tmp_path / name / "Contents" / "MacOS").mkdir(parents=True)
    return [tmp_path]


class FakeWindow:
    """Stands in for ``inapp.sign_in``: records the call, returns a signed-in session."""

    def __init__(self, cookies=None):
        self.calls = []
        self.cookies = BB_COOKIES + [IDP_COOKIE] if cookies is None else cookies

    def __call__(self, url, base_url, timeout, check_user, profile_dir, platform=None):
        self.calls.append({"url": url, "base_url": base_url, "profile_dir": profile_dir, "platform": platform})
        cookies = blackboard_cookies(self.cookies, base_url)
        return check_user(base_url, cookies), cookies


def _no_browser(*args, **kwargs):
    raise AssertionError("no browser may be started")


def _accept(base_url, cookies):
    return USER


# -- which method -----------------------------------------------------------

def test_auto_uses_an_installed_browser_first(tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Opera.app"))
    assert choose_browser("auto", platform="darwin") == tmp_path / "Opera.app"
    assert login_method_label("auto", platform="darwin") == "Opera"


def test_auto_without_any_supported_browser_means_the_inapp_window(tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Safari.app", "Firefox.app"))
    assert choose_browser("auto", platform="darwin") is None
    assert login_method_label("auto", platform="darwin") == INAPP


def test_inapp_is_forced_even_with_a_browser_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))
    assert choose_browser(INAPP, platform="darwin") is None
    assert login_method_label(INAPP, platform="darwin") == INAPP


def test_a_browser_asked_for_by_name_must_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path))
    with pytest.raises(NoSupportedBrowserError) as caught:
        choose_browser("vivaldi", platform="darwin")
    assert caught.value.requested == "vivaldi"


def test_windows_without_a_browser_also_falls_back(monkeypatch):
    monkeypatch.setattr(login_mod, "windows_app_paths", lambda exe: [])
    monkeypatch.setattr(login_mod.os, "environ", {})
    assert choose_browser("auto", platform="win32") is None


def test_cli_accepts_browser_inapp():
    args = build_parser().parse_args(["login", "--browser", "inapp"])
    assert args.browser == INAPP


# -- login() ----------------------------------------------------------------

def test_login_without_a_browser_signs_in_in_the_window_and_saves_the_session(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path))
    window, lines = FakeWindow(), []
    user = login(config, platform="darwin", run=_no_browser, connect=_no_browser,
                 check_user=_accept, out=lines.append, inapp=window)

    assert user["userName"] == "student.example"
    assert window.calls == [{"url": BASE_URL + "/", "base_url": BASE_URL,
                             "profile_dir": config.inapp_profile_dir, "platform": "darwin"}]
    assert lines[0] == f"Opening the sign-in window on {BASE_URL} ..."
    saved = load_session(config.session_file, BASE_URL)
    # Only Blackboard's cookies; the identity provider's stay in the window.
    assert [c["name"] for c in saved["cookies"]] == ["BbRouter", "JSESSIONID"]
    assert saved["user"] == {"id": "_900_1", "userName": "student.example", "displayName": "Ada Yılmaz"}
    assert_owner_only(config.session_file)


def test_forced_inapp_never_starts_the_installed_browser(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))
    window = FakeWindow()
    login(config, browser=INAPP, platform="darwin", run=_no_browser, connect=_no_browser,
          check_user=_accept, out=lambda *_: None, inapp=window)
    assert len(window.calls) == 1


def test_a_named_browser_that_is_missing_does_not_fall_back(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path))
    window = FakeWindow()
    with pytest.raises(NoSupportedBrowserError, match="Could not find Brave"):
        login(config, browser="brave", platform="darwin", run=_no_browser, connect=_no_browser,
              check_user=_accept, out=lambda *_: None, inapp=window)
    assert window.calls == []


def test_auto_falls_back_to_the_window_when_the_browser_does_not_open(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))

    def failing_open(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "LSOpenURLsWithRole() failed")

    window, lines = FakeWindow(), []
    login(config, platform="darwin", run=failing_open, connect=_no_browser,
          check_user=_accept, out=lines.append, inapp=window)
    assert len(window.calls) == 1
    assert any("Could not open Google Chrome" in line and "own sign-in window" in line for line in lines)
    assert load_session(config.session_file, BASE_URL)["user"]["id"] == "_900_1"


def test_auto_falls_back_when_the_browser_cannot_be_reached(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))

    def opened(argv, **kwargs):
        profile = next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1]
        (login_mod.Path(profile) / DEVTOOLS_PORT_FILE).write_text("40000\n")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def refused(url):
        raise ConnectionRefusedError("connect ECONNREFUSED 127.0.0.1:40000")

    window, lines = FakeWindow(), []
    login(config, platform="darwin", run=opened, connect=refused,
          check_user=_accept, out=lines.append, inapp=window)
    assert len(window.calls) == 1
    assert any("Could not connect to Google Chrome" in line for line in lines)


def test_failures_after_the_sign_in_page_is_up_do_not_fall_back(config, tmp_path, monkeypatch):
    """A closed window or a timeout in the browser is the student's answer, not a broken browser."""
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))
    monkeypatch.setattr(login_mod, "_wait_for_sign_in",
                        lambda *a: (_ for _ in ()).throw(BlackboardSyncError("The browser was closed before sign-in finished.")))

    def opened(argv, **kwargs):
        profile = next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1]
        (login_mod.Path(profile) / DEVTOOLS_PORT_FILE).write_text("40000\n")
        return subprocess.CompletedProcess(argv, 0, "", "")

    browser = SimpleNamespace(new_browser_cdp_session=lambda: None, close=lambda: None)
    window = FakeWindow()
    with pytest.raises(BlackboardSyncError, match="closed before sign-in"):
        login(config, platform="darwin", run=opened, connect=lambda url: browser,
              check_user=_accept, out=lambda *_: None, inapp=window)
    assert window.calls == []


def test_window_errors_reach_the_caller_and_save_nothing(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path))

    def closed_window(*args, **kwargs):
        raise BlackboardSyncError(CLOSED_MESSAGE)

    with pytest.raises(BlackboardSyncError, match="window was closed"):
        login(config, platform="darwin", check_user=_accept, out=lambda *_: None, inapp=closed_window)
    assert not config.session_file.exists()


def test_both_methods_save_the_same_session_format(config, tmp_path, monkeypatch):
    browser_file = tmp_path / "browser-session.json"
    save_session(browser_file, BASE_URL, BB_COOKIES, USER)
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path / "none"))
    login(config, platform="darwin", check_user=_accept, out=lambda *_: None, inapp=FakeWindow())

    from_browser = load_session(browser_file, BASE_URL)
    from_window = load_session(config.session_file, BASE_URL)
    for data in (from_browser, from_window):
        data.pop("saved_at")
    assert from_window == from_browser


# -- cookies ----------------------------------------------------------------

def _simple_cookie(name, value, domain, expires, secure=True, path="/"):
    jar = SimpleCookie()
    jar[name] = value
    for key, val in (("domain", domain), ("path", path), ("expires", expires),
                     ("secure", secure), ("httponly", True)):
        jar[name][key] = val
    return jar


def test_webview2_cookies_convert_with_session_cookies_kept_as_session():
    jars = [
        _simple_cookie("BbRouter", "expires:1,id:A", "blackboard.example.edu", "Wed, 31 Dec 1969 23:59:59 GMT"),
        _simple_cookie("JSESSIONID", "j", "blackboard.example.edu", "Fri, 01 Jan 2100 00:00:00 GMT", path="/webapps"),
        _simple_cookie("AWSALB", "lb", "blackboard.example.edu", "Mon, 01 Jan 0001 00:00:00 GMT", secure=False),
        # -1 s formatted as local time in UTC+3: still a session cookie, not one expiring in 1970.
        _simple_cookie("AWSALBCORS", "lb", "blackboard.example.edu", "Thu, 01 Jan 1970 02:59:59 GMT"),
    ]
    assert cookies_from_simple_cookies(jars) == [
        {"name": "BbRouter", "value": "expires:1,id:A", "domain": "blackboard.example.edu", "path": "/",
         "secure": True, "expires": None},
        {"name": "JSESSIONID", "value": "j", "domain": "blackboard.example.edu", "path": "/webapps",
         "secure": True, "expires": 4102444800.0},
        {"name": "AWSALB", "value": "lb", "domain": "blackboard.example.edu", "path": "/",
         "secure": False, "expires": None},
        {"name": "AWSALBCORS", "value": "lb", "domain": "blackboard.example.edu", "path": "/",
         "secure": True, "expires": None},
    ]


class FakeNSDate:
    def __init__(self, seconds):
        self.seconds = seconds

    def timeIntervalSince1970(self):
        return self.seconds


class FakeNSHTTPCookie:
    def __init__(self, name, value, domain, path="/", secure=True, expires=None):
        self._data = (name, value, domain, path, secure, expires)

    def name(self): return self._data[0]
    def value(self): return self._data[1]
    def domain(self): return self._data[2]
    def path(self): return self._data[3]
    def isSecure(self): return self._data[4]
    def expiresDate(self): return None if self._data[5] is None else FakeNSDate(self._data[5])


def test_wkwebview_cookies_convert():
    cookies = cookies_from_nshttpcookies([
        FakeNSHTTPCookie("BbRouter", "expires:1,id:A", "blackboard.example.edu"),
        FakeNSHTTPCookie("JSESSIONID", "j", "blackboard.example.edu", "/webapps", expires=4102444800),
        FakeNSHTTPCookie("ESTSAUTH", "idp", ".login.microsoftonline.com"),
    ])
    assert cookies[:2] == BB_COOKIES
    assert blackboard_cookies(cookies, BASE_URL) == BB_COOKIES


def test_parent_domain_cookies_count_as_blackboard_cookies():
    shared = {"name": "AWSALB", "value": "x", "domain": ".example.edu", "path": "/", "secure": True, "expires": None}
    assert blackboard_cookies([shared, IDP_COOKIE], BASE_URL) == [shared]


# -- waiting in the window --------------------------------------------------

def test_watch_waits_until_blackboard_accepts_the_cookies():
    rounds = iter([[], [IDP_COOKIE], BB_COOKIES + [IDP_COOKIE], BB_COOKIES])
    checked = []

    def check_user(base_url, cookies):
        checked.append([c["name"] for c in cookies])
        return USER if len(checked) == 2 else None

    user, cookies = watch_for_session(lambda: next(rounds), BASE_URL, check_user, 60, threading.Event(), poll=0)
    assert user is USER
    assert cookies == BB_COOKIES
    # Only rounds with Blackboard cookies ask Blackboard; the identity provider's never leave.
    assert checked == [["BbRouter", "JSESSIONID"], ["BbRouter", "JSESSIONID"]]


def test_watch_stops_when_the_student_closes_the_window():
    closed = threading.Event()

    def fetch():
        closed.set()
        return BB_COOKIES

    with pytest.raises(BlackboardSyncError, match="window was closed"):
        watch_for_session(fetch, BASE_URL, lambda *_: None, 60, closed, poll=0)


def test_watch_gives_up_after_the_timeout():
    now = iter([0, 0, 301, 601, 601])
    with pytest.raises(BlackboardSyncError, match="within 10 minutes"):
        watch_for_session(lambda: None, BASE_URL, lambda *_: None, 600, threading.Event(),
                          poll=0, clock=lambda: next(now))


def test_outcome_hands_the_worker_result_or_error_to_the_gui_thread():
    done = []
    good = Outcome()
    good.run(lambda: (USER, BB_COOKIES), lambda: done.append("closed"))
    assert good.result() == (USER, BB_COOKIES)

    bad = Outcome()
    bad.run(lambda: (_ for _ in ()).throw(BlackboardSyncError("boom")), lambda: done.append("closed"))
    with pytest.raises(BlackboardSyncError, match="boom"):
        bad.result()
    assert done == ["closed", "closed"]  # the window is closed either way

    with pytest.raises(BlackboardSyncError, match="window was closed"):
        Outcome().result()  # the GUI loop ended without a result
