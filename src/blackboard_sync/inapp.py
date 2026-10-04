"""Sign-in inside the app's own window, for computers without a supported browser.

The window is the operating system's web component: WKWebView on macOS
(``inapp_macos``), Microsoft Edge WebView2 on Windows (``inapp_windows``). It
opens the school's Blackboard address, the student signs in there exactly as in
a browser (single sign-on, two-factor), and this module watches the web view's
cookie store (which includes HttpOnly cookies) until Blackboard accepts the
session. The password is typed into the school's page and never reaches this
program. The cookies are then saved like the browser path saves them.

Everything here is GUI-free so it can be tested on any machine; the platform
modules only open the window, read its cookies and close it.
"""

from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable

from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.session import cookie_matches_host, host_of
from blackboard_sync.system import is_windows

# `login --browser inapp` forces this method.
INAPP = "inapp"
POLL_SECONDS = 2
WINDOW_TITLE = "Blackboard Sync – Giriş"
WINDOW_SIZE = (520, 720)
CLOSED_MESSAGE = "The sign-in window was closed before sign-in finished."
WEBVIEW2_MISSING = (
    "The sign-in window needs the Microsoft Edge WebView2 Runtime, which is missing on this "
    "computer. Install it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 or install "
    "Google Chrome or Microsoft Edge, then sign in again."
)

Cookie = dict
CheckUser = Callable[[str, list[Cookie]], "dict | None"]


def blackboard_cookies(cookies: Iterable[Cookie], base_url: str) -> list[Cookie]:
    """Only the cookies Blackboard's host would receive (no identity-provider cookies)."""
    host = host_of(base_url)
    return [c for c in cookies if cookie_matches_host(c.get("domain") or host, host)]


def _epoch_from_http_date(value, now: float | None = None) -> float | None:
    """``Wed, 21 Oct 2026 07:28:00 GMT`` to seconds; None for session cookies.

    A cookie store never hands out expired cookies, so an expiry in the past is
    a session cookie's placeholder (1969/1970, possibly shifted by the local
    time zone, or year 1, which the date parser reads as 2001).
    """
    if not value:
        return None
    try:
        seconds = parsedate_to_datetime(str(value)).timestamp()
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    return seconds if seconds > (time.time() if now is None else now) else None


def cookies_from_simple_cookies(jars: Iterable) -> list[Cookie]:
    """Convert pywebview's ``window.get_cookies()`` result (``SimpleCookie`` objects).

    WebView2 reports a session cookie with a placeholder expiry in the past,
    which becomes None here, the same as a session cookie from the browser path.
    """
    out = []
    for jar in jars or []:
        for name, morsel in jar.items():
            out.append({
                "name": name,
                "value": morsel.value,
                "domain": morsel["domain"] or "",
                "path": morsel["path"] or "/",
                "secure": bool(morsel["secure"]),
                "expires": _epoch_from_http_date(morsel["expires"]),
            })
    return out


def cookies_from_nshttpcookies(cookies: Iterable) -> list[Cookie]:
    """Convert ``NSHTTPCookie`` objects from WKWebView's cookie store."""
    out = []
    for c in cookies or []:
        expires = c.expiresDate()
        out.append({
            "name": str(c.name()),
            "value": str(c.value()),
            "domain": str(c.domain() or ""),
            "path": str(c.path() or "/"),
            "secure": bool(c.isSecure()),
            "expires": float(expires.timeIntervalSince1970()) if expires is not None else None,
        })
    return out


def watch_for_session(
    fetch_cookies: Callable[[], Iterable[Cookie] | None],
    base_url: str,
    check_user: CheckUser,
    timeout: float,
    closed: threading.Event,
    poll: float = POLL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[dict, list[Cookie]]:
    """Poll the window's cookies until Blackboard accepts them.

    Runs on a worker thread while the window runs on the main thread. Stops
    with an error when the student closes the window or time runs out.
    """
    deadline = clock() + timeout
    while clock() < deadline:
        if closed.is_set():
            raise BlackboardSyncError(CLOSED_MESSAGE)
        cookies = blackboard_cookies(fetch_cookies() or [], base_url)
        user = check_user(base_url, cookies) if cookies else None
        if user:
            return user, cookies
        closed.wait(poll)
    raise BlackboardSyncError(f"Sign-in was not completed within {int(timeout // 60)} minutes.")


class Outcome:
    """Carries the worker thread's result (or error) back to the GUI thread."""

    def __init__(self) -> None:
        self.value: tuple[dict, list[Cookie]] | None = None
        self.error: BaseException | None = None

    def run(self, work: Callable[[], tuple[dict, list[Cookie]]], finished: Callable[[], None]) -> None:
        try:
            self.value = work()
        except BaseException as exc:  # handed to the GUI thread, re-raised there
            self.error = exc
        finally:
            finished()

    def result(self) -> tuple[dict, list[Cookie]]:
        if self.error is not None:
            raise self.error
        if self.value is None:
            raise BlackboardSyncError(CLOSED_MESSAGE)
        return self.value


def sign_in(
    url: str,
    base_url: str,
    timeout: float,
    check_user: CheckUser,
    profile_dir,
    platform: str | None = None,
) -> tuple[dict, list[Cookie]]:
    """Open the sign-in window and return (Blackboard user, Blackboard cookies)."""
    return _gui(platform).sign_in(url, base_url, timeout, check_user, profile_dir)


def check_runtime(platform: str | None = None) -> str:
    """Load the web component the window needs, without opening it; returns its name.

    Part of ``--check-login-runtime``, which CI runs against the packaged apps.
    """
    return _gui(platform).check_runtime()


def _gui(platform: str | None):
    try:
        if is_windows(platform):
            from blackboard_sync import inapp_windows as gui
        else:
            from blackboard_sync import inapp_macos as gui
    except ImportError as exc:  # a checkout set up before this window existed
        raise BlackboardSyncError(
            f"The sign-in window is unavailable ({exc}); run ./scripts/setup.sh again "
            "or install a Chromium-based browser."
        ) from exc
    return gui
