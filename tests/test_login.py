"""Sign-in: LaunchServices on macOS (regression for keyboard focus), the installed
browser executable on Windows. Platform-specific logic is injected, so every test
runs on any OS."""

import subprocess

import pytest

from blackboard_sync import login as login_mod
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.login import (
    CREATE_NEW_PROCESS_GROUP,
    DETACHED_PROCESS,
    DEVTOOLS_PORT_FILE,
    browser_label,
    find_browser,
    launch_command,
    login,
    session_user,
    wait_for_devtools_port,
    windows_browser_candidates,
)
from blackboard_sync.session import load_session

from .conftest import BASE_URL, assert_owner_only

COOKIES = [{"name": "BbRouter", "value": "x", "domain": "blackboard.example.edu", "path": "/",
            "secure": True, "expires": -1}]


def _apps(tmp_path, *names):
    for name in names:
        (tmp_path / name / "Contents" / "MacOS").mkdir(parents=True)
    return [tmp_path]


def test_find_browser_returns_app_bundles(tmp_path):
    both = _apps(tmp_path, "Google Chrome.app", "Brave Browser.app")
    assert find_browser("auto", both, platform="darwin") == tmp_path / "Google Chrome.app"
    assert find_browser("brave", both, platform="darwin") == tmp_path / "Brave Browser.app"


def test_find_browser_falls_back_to_brave_and_reports_missing(tmp_path):
    found = find_browser("auto", _apps(tmp_path / "a", "Brave Browser.app"), platform="darwin")
    assert found.name == "Brave Browser.app"
    with pytest.raises(BlackboardSyncError, match="Could not find"):
        find_browser("chrome", _apps(tmp_path / "b"), platform="darwin")


def test_browser_is_started_by_launchservices_not_as_a_child_process(tmp_path):
    app = tmp_path / "Brave Browser.app"
    argv = launch_command(app, tmp_path / "profile", "https://bb.example.edu/", platform="darwin")
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

    user = login(config, run=_fake_open(calls), connect=connect, platform="darwin",
                 check_user=lambda base, cookies: next(users), out=lambda *_: None)

    assert user["userName"] == "student.example"
    assert calls[0][0] == "/usr/bin/open"
    assert connected_to == ["http://127.0.0.1:40000"]  # the fresh port, not the stale one
    assert browser.sent == ["Browser.close"]
    saved = load_session(config.session_file, BASE_URL)
    assert [c["name"] for c in saved["cookies"]] == ["BbRouter"]
    assert_owner_only(config.session_file)


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
        login(config, run=_fake_open([]), connect=lambda url: browser, platform="darwin",
              check_user=check_user, out=lambda *_: None)
    assert browser.sent == ["Browser.close"]
    assert not config.session_file.exists()


def test_login_reports_open_failure(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "APP_DIRS", _apps(tmp_path, "Google Chrome.app"))

    def failing_open(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "LSOpenURLsWithRole() failed")

    with pytest.raises(BlackboardSyncError, match="Could not open Google Chrome"):
        login(config, run=failing_open, connect=lambda url: None, platform="darwin", out=lambda *_: None)


def test_session_user_accepts_only_a_real_user(fake_bb):
    assert session_user(BASE_URL, COOKIES, http=fake_bb)["id"] == "_900_1"
    fake_bb.expired = True
    assert session_user(BASE_URL, COOKIES, http=fake_bb) is None


# -- Windows ----------------------------------------------------------------

def _windows_install(base, *parts):
    exe = base.joinpath(*parts)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    return exe


def _windows_env(tmp_path):
    return {
        "ProgramFiles": str(tmp_path / "Program Files"),
        "ProgramFiles(x86)": str(tmp_path / "Program Files (x86)"),
        "LOCALAPPDATA": str(tmp_path / "Local"),
    }


def test_windows_finds_chrome_first_then_edge_then_brave(tmp_path):
    env = _windows_env(tmp_path)
    no_registry = lambda exe: []
    edge = _windows_install(tmp_path / "Program Files (x86)", "Microsoft", "Edge", "Application", "msedge.exe")
    brave = _windows_install(tmp_path / "Local", "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    found = find_browser("auto", platform="win32", env=env, registry=no_registry)
    assert found == edge  # every Windows has Edge; Brave only when asked or as a last resort
    assert find_browser("brave", platform="win32", env=env, registry=no_registry) == brave
    chrome = _windows_install(tmp_path / "Local", "Google", "Chrome", "Application", "chrome.exe")
    assert find_browser("auto", platform="win32", env=env, registry=no_registry) == chrome
    assert browser_label(chrome) == "Google Chrome"
    assert browser_label(edge) == "Microsoft Edge"


def test_windows_prefers_the_registered_install_location(tmp_path):
    custom = _windows_install(tmp_path / "D", "Apps", "Chrome", "chrome.exe")
    _windows_install(tmp_path / "Program Files", "Google", "Chrome", "Application", "chrome.exe")
    registry = lambda exe: [str(custom)] if exe == "chrome.exe" else []
    env = _windows_env(tmp_path)
    assert windows_browser_candidates("chrome", env, registry)[0] == custom
    assert find_browser("chrome", platform="win32", env=env, registry=registry) == custom


def test_windows_reports_a_missing_browser(tmp_path):
    with pytest.raises(BlackboardSyncError, match="Could not find Google Chrome, Microsoft Edge or Brave"):
        find_browser("auto", platform="win32", env=_windows_env(tmp_path), registry=lambda exe: [])
    with pytest.raises(BlackboardSyncError, match="Unknown browser"):
        find_browser("firefox", platform="win32", env={}, registry=lambda exe: [])


def test_windows_starts_the_browser_executable_directly(tmp_path):
    exe = tmp_path / "msedge.exe"
    argv = launch_command(exe, tmp_path / "profile", "https://bb.example.edu/", platform="win32")
    assert argv[0] == str(exe)
    assert f"--user-data-dir={tmp_path / 'profile'}" in argv
    assert "--remote-debugging-port=0" in argv
    assert argv[-1] == "https://bb.example.edu/"
    assert not any(a.startswith(("--enable-automation", "--remote-debugging-pipe")) for a in argv)


def test_windows_login_spawns_a_detached_browser_and_saves_the_session(config, tmp_path, monkeypatch):
    monkeypatch.setattr(login_mod, "POLL_SECONDS", 0)
    edge = _windows_install(tmp_path / "PF", "Microsoft", "Edge", "Application", "msedge.exe")
    monkeypatch.setattr(login_mod, "find_browser", lambda browser, platform=None: edge)
    spawned = []

    def spawn(argv, **kwargs):
        spawned.append((argv, kwargs))
        _fake_open([])(argv)  # the browser writes its DevTools port
        return object()

    def no_run(*args, **kwargs):
        raise AssertionError("Windows must not go through `open`")

    browser = FakeBrowser(FakeContext([COOKIES]))
    user = login(config, run=no_run, spawn=spawn, connect=lambda url: browser, platform="win32",
                 check_user=lambda base, cookies: {"id": "_900_1", "userName": "student.example"},
                 out=lambda *_: None)
    assert user["id"] == "_900_1"
    argv, kwargs = spawned[0]
    assert argv[0] == str(edge)
    assert kwargs["creationflags"] == DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    assert browser.sent == ["Browser.close"]
    assert load_session(config.session_file, BASE_URL)["user"]["userName"] == "student.example"


def test_windows_login_reports_a_browser_that_cannot_start(config, tmp_path, monkeypatch):
    edge = tmp_path / "msedge.exe"
    monkeypatch.setattr(login_mod, "find_browser", lambda browser, platform=None: edge)

    def spawn(argv, **kwargs):
        raise OSError("The system cannot find the file specified")

    with pytest.raises(BlackboardSyncError, match="Could not open Microsoft Edge"):
        login(config, spawn=spawn, connect=lambda url: None, platform="win32", out=lambda *_: None)


def test_check_runtime_starts_and_stops_the_driver(monkeypatch):
    import sys, types
    events = []

    class Driver:
        chromium = types.SimpleNamespace(connect_over_cdp=None)
        def stop(self):
            events.append("stop")

    class Manager:
        def start(self):
            events.append("start")
            return Driver()

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = Manager
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    from blackboard_sync import login
    login.check_runtime()
    assert events == ["start", "stop"]
