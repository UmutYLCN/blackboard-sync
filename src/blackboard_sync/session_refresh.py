"""Staying signed in without the student: a background sign-in and a keep-alive.

A Blackboard session ends after a while, but the school's single sign-on usually
outlives it. So when the session is gone, or about to go, the sign-in browser is
started again on its private profile with no window at all. Blackboard sends it
to the school's sign-on page, which finds its own cookies in that profile and
sends it straight back signed in; the new cookies are saved and the browser quits.

Nothing here ever types, reads or stores a password, and no form is ever touched.
When the school wants the student (a password, a code, an account to pick), the
attempt just ends with a reason and the app asks for "Sign in" as it always did.

The browser's own session cookies are restored (``--restore-last-session``), or
Chromium would drop them at start: a sign-on that lasts only "until the browser
closes" lives in them.

Between syncs ``keep_alive`` makes the one light request ``login.session_user``
makes, which also tells early that the session is gone.

Only the macOS menu bar app uses this so far. No GUI here, so that Windows and the
iPad can share the decisions (``SessionCare``) later.
"""

from __future__ import annotations

import json
import logging
import plistlib
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.errors import AlreadyRunning, BlackboardSyncError, LoginRequired
from blackboard_sync.login import (
    BROWSERS,
    DEVTOOLS_PORT_FILE,
    BrowserStartError,
    ProfileBusy,
    _close_browser,
    _connector,
    discover_browser,
    profile_in_use,
    profile_lock,
    session_user,
    wait_for_devtools_port,
)
from blackboard_sync.session import (
    host_of,
    http_session,
    load_session,
    refresh_saved_cookies,
    save_session,
    session_expires_at,
)
from blackboard_sync.sync import run_lock
from blackboard_sync.system import is_windows

log = logging.getLogger("blackboard_sync.session_refresh")

SILENT_TIMEOUT = 45.0  # seconds; a sign-on that needs nobody takes a few
BROWSER_START_TIMEOUT = 20.0
BROWSER_QUIT_TIMEOUT = 8.0
POLL_SECONDS = 1.0
# Longer than ``SILENT_TIMEOUT`` plus starting and closing the browser; the app's guard against a hang.
SILENT_HARD_TIMEOUT = 120.0
KEEP_ALIVE_EVERY = timedelta(minutes=25)
# Over ``KEEP_ALIVE_EVERY``: the look before last must not be the last chance to act in time.
EXPIRY_MARGIN = timedelta(minutes=30)
FAILED_RETRY_AFTER = timedelta(minutes=10)

# How a background sign-in ended (for the log; never holds anything secret).
REFRESHED = "refreshed"
NEEDS_INTERACTION = "sso-needs-interaction"  # the school wants the student
TIMED_OUT = "timeout"
BROWSER_MISSING = "browser-missing"
BROWSER_FAILED = "browser-failed"
PROFILE_BUSY = "profile-busy"
NOT_SIGNED_IN = "not-signed-in"  # nothing to refresh, or signed in another way (no browser profile)
LOCKED = "locked"  # a sync holds the session
FAILED = "error"

# How a keep-alive ended.
ALIVE, EXPIRED, UNREACHABLE = "alive", "expired", "unreachable"

# "Headless" is not a background mode everywhere: Arc may reuse the student's running
# window whatever it is told (see ``login.AUTO_ORDER``).
NO_SILENT_START = (BROWSERS["arc"],)
PASSWORD_FIELD = "input[type=password]:visible"


@dataclass(frozen=True)
class RefreshResult:
    reason: str
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.reason == REFRESHED


@dataclass(frozen=True)
class KeepAlive:
    status: str  # ALIVE | EXPIRED | UNREACHABLE | NOT_SIGNED_IN | LOCKED
    expires_at: float | None = None  # ``session.session_expires_at``

    def wants_refresh(self, now: datetime) -> bool:
        """The session is gone, or ends before the next look."""
        if self.status == EXPIRED:
            return True
        return (self.status == ALIVE and self.expires_at is not None
                and self.expires_at - now.timestamp() < EXPIRY_MARGIN.total_seconds())


@dataclass
class SessionCare:
    """When to look at the session and when another background sign-in may start."""

    enabled: bool = True  # the "Automatic re-sign-in" setting
    checked_at: datetime | None = None  # the last keep-alive or finished sync
    failed_at: datetime | None = None  # the last background sign-in that did not work
    refreshed_at: datetime | None = None

    def keep_alive_due(self, now: datetime) -> bool:
        # A time in the future means the clock was changed: look anyway.
        return self.enabled and not (self.checked_at is not None
                                     and self.checked_at <= now < self.checked_at + KEEP_ALIVE_EVERY)

    def may_refresh(self, now: datetime) -> bool:
        """Not again right after a failure: a dead sign-on must not keep starting the browser."""
        return self.enabled and not (self.failed_at is not None
                                     and self.failed_at <= now < self.failed_at + FAILED_RETRY_AFTER)

    def record(self, result: RefreshResult, now: datetime) -> None:
        if result.ok:
            self.refreshed_at, self.failed_at = now, None
        else:
            self.failed_at = now


def browser_executable(app: Path, platform: str | None = None) -> Path:
    """The program inside the app bundle (on Windows ``app`` already is one).

    Started directly, not through LaunchServices as ``login`` does: this browser has
    no window to give focus to, and only its own process can be ended for sure.
    """
    if is_windows(platform):
        return app
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    return app / "Contents" / "MacOS" / info["CFBundleExecutable"]


def silent_flags(profile_dir: Path) -> list[str]:
    return [
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--headless=new",  # the real browser, without a window, a Dock icon or focus
        "--restore-last-session",  # see the module's description
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]


def _session_saved(config: Config) -> bool:
    """A session of this school was saved, whether it still works or not."""
    try:
        data = json.loads(config.session_file.read_text(encoding="utf-8"))
        return data.get("base_url", "").rstrip("/") == config.base_url.rstrip("/")
    except (OSError, ValueError, AttributeError):
        return False


def _stop_browser(process, timeout: float = BROWSER_QUIT_TIMEOUT) -> None:
    """Make sure it is gone: nothing else may be left running on the profile."""
    for stop in (None, process.terminate, process.kill):
        if stop is not None:
            stop()
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue


def _wants_student(page) -> bool:
    """The page shows a password field. It is only looked at, never touched."""
    try:
        return page.locator(PASSWORD_FIELD).count() > 0
    except Exception:  # the page is changing to the next one
        return False


def _page_host(page) -> str:
    try:
        return urlsplit(page.url).hostname or ""
    except Exception:
        return ""


def _wait_for_session(cdp_browser, base_url: str, timeout: float, check_user) -> tuple[str, dict | None, list[dict]]:
    """Open Blackboard and wait; returns (a reason, the user, their cookies).

    The old Blackboard cookies go first: they may still work for a few minutes, and
    saving those again would refresh nothing. The sign-on cookies stay.
    """
    contexts = cdp_browser.contexts
    if not contexts:
        return BROWSER_FAILED, None, []
    context = contexts[0]
    context.clear_cookies(domain=host_of(base_url))
    page = context.pages[0] if context.pages else context.new_page()
    deadline = time.monotonic() + timeout
    try:
        page.goto(base_url + "/", wait_until="commit", timeout=timeout * 1000)
    except Exception as exc:  # also a redirect that interrupts it: the watching below decides
        log.debug("opening Blackboard: %s", type(exc).__name__)
    while time.monotonic() < deadline:
        # Also how Playwright hears about the page: it only listens during its own calls.
        cookies = context.cookies(base_url)
        user = check_user(base_url, cookies) if cookies else None
        if user:
            return REFRESHED, user, cookies
        if _wants_student(page):
            return NEEDS_INTERACTION, None, []
        time.sleep(POLL_SECONDS)
    away = _page_host(page) not in ("", "about", host_of(base_url))
    return (NEEDS_INTERACTION if away else TIMED_OUT), None, []


def silent_sign_in(
    config: Config,
    timeout: float = SILENT_TIMEOUT,
    spawn: Callable[..., object] = subprocess.Popen,
    connect: Callable[[str], object] | None = None,
    check_user: Callable[[str, list[dict]], dict | None] = session_user,
    app_dirs: list[Path] | None = None,
    platform: str | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> RefreshResult:
    """Try to sign in again with no window; never raises for an expected failure."""
    started = clock()
    if not _session_saved(config):
        return RefreshResult(NOT_SIGNED_IN)
    if not config.profile_dir.is_dir():
        return RefreshResult(NOT_SIGNED_IN)
    app = discover_browser("auto", app_dirs, platform=platform)
    if app is None or app.name in NO_SILENT_START:
        return RefreshResult(BROWSER_MISSING)
    try:
        with run_lock(config.lock_file), profile_lock(config):
            if profile_in_use(config.profile_dir):
                return RefreshResult(PROFILE_BUSY)
            reason = _sign_in_with_profile(config, app, timeout, spawn, connect, check_user, platform)
    except AlreadyRunning:
        return RefreshResult(LOCKED)
    except ProfileBusy:
        return RefreshResult(PROFILE_BUSY)
    except BrowserStartError as exc:
        log.info("background sign-in: %s", type(exc).__name__)
        return RefreshResult(BROWSER_FAILED)
    except (BlackboardSyncError, OSError, KeyError, ValueError) as exc:
        log.info("background sign-in: %s", type(exc).__name__)
        return RefreshResult(FAILED)
    return RefreshResult(reason, clock() - started)


def _sign_in_with_profile(config, app, timeout, spawn, connect, check_user, platform) -> str:
    stale = config.profile_dir / DEVTOOLS_PORT_FILE
    if stale.exists():
        stale.unlink()
    process = spawn(
        [str(browser_executable(app, platform)), *silent_flags(config.profile_dir)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        port = wait_for_devtools_port(config.profile_dir, timeout=BROWSER_START_TIMEOUT)
        with _connector(connect) as connect_fn:
            try:
                cdp_browser = connect_fn(f"http://127.0.0.1:{port}")
            except Exception as exc:
                raise BrowserStartError(type(exc).__name__) from exc
            try:
                reason, user, cookies = _wait_for_session(cdp_browser, config.base_url, timeout, check_user)
                if reason == REFRESHED:
                    save_session(config.session_file, config.base_url, cookies, user)
                return reason
            finally:
                _close_browser(cdp_browser)
    finally:
        _stop_browser(process)


def keep_alive(config: Config) -> KeepAlive:
    """One light request with the saved session; cookies it rotates are saved."""
    try:
        with run_lock(config.lock_file):
            session_data = load_session(config.session_file, config.base_url)
            client = BlackboardClient(config.base_url, http_session(session_data), timeout=15)
            client.me()
            refresh_saved_cookies(config.session_file, session_data, client.http)
            return KeepAlive(ALIVE, session_expires_at(load_session(config.session_file, config.base_url)))
    except AlreadyRunning:
        return KeepAlive(LOCKED)  # a running sync is its own keep-alive
    except LoginRequired:
        return KeepAlive(EXPIRED if config.session_file.exists() else NOT_SIGNED_IN)
    except (BlackboardSyncError, requests.RequestException, OSError) as exc:
        log.info("keep-alive: %s", type(exc).__name__)
        return KeepAlive(UNREACHABLE)
