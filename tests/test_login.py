"""Sign-in launches the browser through LaunchServices (regression for keyboard focus)."""

import subprocess

import pytest

from blackboard_sync import login as login_mod
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.login import (
    DEVTOOLS_PORT_FILE,
    find_browser,
    launch_command,
    login,
    session_user,
    wait_for_devtools_port,
)
from blackboard_sync.session import load_session

from .conftest import BASE_URL

COOKIES = [{"name": "BbRouter", "value": "x", "domain": "blackboard.example.edu", "path": "/",
            "secure": True, "expires": -1}]


def _apps(tmp_path, *names):
    for name in names:
        (tmp_path / name / "Contents" / "MacOS").mkdir(parents=True)
    return [tmp_path]


def test_find_browser_returns_app_bundles(tmp_path):
    both = _apps(tmp_path, "Google Chrome.app", "Brave Browser.app")
    assert find_browser("auto", both) == tmp_path / "Google Chrome.app"
    assert find_browser("brave", both) == tmp_path / "Brave Browser.app"


def test_find_browser_falls_back_to_brave_and_reports_missing(tmp_path):
    assert find_browser("auto", _apps(tmp_path / "a", "Brave Browser.app")).name == "Brave Browser.app"
    with pytest.raises(BlackboardSyncError, match="Could not find"):
        find_browser("chrome", _apps(tmp_path / "b"))


def test_browser_is_started_by_launchservices_not_as_a_child_process(tmp_path):
    app = tmp_path / "Brave Browser.app"
    argv = launch_command(app, tmp_path / "profile", "https://bb.example.edu/")
    # `open` hands the launch to macOS, which makes it a normal frontmost app that
    # takes keyboard input even when login runs in a background terminal session.
    assert argv[:4] == ["/usr/bin/open", "-n", "-a", str(app)]
    args = argv[argv.index("--args") + 1:]
    assert f"--user-data-dir={tmp_path / 'profile'}" in args
    assert "--remote-debugging-port=0" in args
    assert args[-1] == "https://bb.example.edu/"
    # No automation-mode launch flags (those come from driving the binary directly).
    assert not any(a.startswith(("--enable-automation", "--remote-debugging-pipe", "--use-mock-keychain"))
                   for a in args)


def test_wait_for_devtools_port(tmp_path, monkeypatch):
    (tmp_path / DEVTOOLS_PORT_FILE).write_text("53123\n/devtools/browser/abc\n")
    assert wait_for_devtools_port(tmp_path, timeout=1) == 53123
    (tmp_path / DEVTOOLS_PORT_FILE).unlink()
    with pytest.raises(BlackboardSyncError, match="did not start"):
        wait_for_devtools_port(tmp_path, timeout=0.3)


class FakeContext:
    def __init__(self, cookie_rounds, pages=1):
        self.cookie_rounds = list(cookie_rounds)
        self.pages = ["page"] * pages

    def cookies(self, url):
        return self.cookie_rounds.pop(0) if len(self.cookie_rounds) > 1 else self.cookie_rounds[0]


class FakeCdpSession:
    def __init__(self, browser):
        self.browser = browser

    def send(self, method):
        self.browser.sent.append(method)
        self.browser.connected = False


class FakeBrowser:
    def __init__(self, context):
        self.contexts = [context]
        self.connected = True
        self.sent = []

    def is_connected(self):
        return self.connected

    def new_browser_cdp_session(self):
        return FakeCdpSession(self)

    def close(self):
        pass


def _fake_open(calls, port="40000"):
    def run(argv, **kwargs):
        calls.append(argv)
        profile = next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1]
        (login_mod.Path(profile) / DEVTOOLS_PORT_FILE).write_text(f"{port}\n/devtools/browser/x\n")
        return subprocess.CompletedProcess(argv, 0, "", "")
    return run


def test_login_waits_for_sign_in_saves_cookies_and_closes_browser(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "POLL_SECONDS", 0)
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))
    config.ensure_data_dir()
    config.profile_dir.mkdir()
    (config.profile_dir / DEVTOOLS_PORT_FILE).write_text("9999\n")  # stale, from an old run
    calls, connected_to = [], []
    browser = FakeBrowser(FakeContext([[], COOKIES]))
    users = iter([None, {"id": "_900_1", "userName": "student.example"}])

    def connect(url):
        connected_to.append(url)
        return browser

    user = login(config, run=_fake_open(calls), connect=connect,
                 check_user=lambda base, cookies: next(users), out=lambda *_: None)

    assert user["userName"] == "student.example"
    assert calls[0][0] == "/usr/bin/open"
    assert connected_to == ["http://127.0.0.1:40000"]  # the fresh port, not the stale one
    assert browser.sent == ["Browser.close"]
    saved = load_session(config.session_file, BASE_URL)
    assert [c["name"] for c in saved["cookies"]] == ["BbRouter"]
    assert (config.session_file.stat().st_mode & 0o777) == 0o600


def test_login_stops_when_window_is_closed(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "POLL_SECONDS", 0)
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Brave Browser.app"))
    context = FakeContext([[]])
    browser = FakeBrowser(context)

    def check_user(base, cookies):
        context.pages = []  # student closes the window
        return None

    context.cookies = lambda url: COOKIES
    with pytest.raises(BlackboardSyncError, match="closed before sign-in"):
        login(config, run=_fake_open([]), connect=lambda url: browser,
              check_user=check_user, out=lambda *_: None)
    assert browser.sent == ["Browser.close"]
    assert not config.session_file.exists()


def test_login_reports_open_failure(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))

    def failing_open(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "LSOpenURLsWithRole() failed")

    with pytest.raises(BlackboardSyncError, match="Could not open Google Chrome"):
        login(config, run=failing_open, connect=lambda url: None, out=lambda *_: None)


def test_session_user_accepts_only_a_real_user(fake_bb):
    assert session_user(BASE_URL, COOKIES, http=fake_bb)["id"] == "_900_1"
    fake_bb.expired = True
    assert session_user(BASE_URL, COOKIES, http=fake_bb) is None
