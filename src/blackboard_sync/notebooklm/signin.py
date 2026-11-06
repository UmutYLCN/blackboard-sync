"""The one-time Google sign-in, in the student's own Chromium-based browser.

The browser is started the same way as for Blackboard (``login.py``), with a private profile,
and the student signs in by hand, two-factor steps included; this code never sees the password.
It watches over the browser's local DevTools port until NotebookLM has opened and the Google
session cookies exist, saves them owner-only and closes the browser.

Google refuses embedded web views, so there is no in-app window to fall back on here. It can
also refuse a browser that reports automation (``navigator.webdriver``), which Chromium does for
``--remote-debugging-port=0``, so a free port is chosen here; Chromium then writes no port file.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError, NotebookLMLoginRequired, NotebookLMTransient
from blackboard_sync.i18n import tr
from blackboard_sync.login import (
    POLL_SECONDS,
    BrowserStartError,
    NoSupportedBrowserError,
    _close_browser,
    _connector,
    browser_label,
    find_browser,
    launch_command,
    start_browser,
)
from blackboard_sync.notebooklm import store
from blackboard_sync.session import write_private_json
from blackboard_sync.system import make_private_dir

# Straight to Google's sign-in; the bare address shows a product page to someone signed out.
SIGN_IN_URL = "https://notebook.google.com/login?continue=https%3A%2F%2Fnotebook.google.com%2F"
# The app moved to the first host with the rename to Gemini Notebook.
APP_HOSTS = frozenset({"notebook.google.com", "notebooklm.google.com"})
# What the library cannot work without (``MINIMUM_REQUIRED_COOKIES``).
REQUIRED_COOKIES = frozenset({"SID", "__Secure-1PSIDTS"})
SIGN_IN_TIMEOUT = 600.0
BROWSER_START_TIMEOUT = 30.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_port(port: int, timeout: float = BROWSER_START_TIMEOUT, sleep: Callable[[float], None] = time.sleep) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            sleep(0.25)
    raise BrowserStartError(tr("The browser did not start. If a sign-in window from an earlier attempt is "
                               "still open, close it and try again."))


def signed_in_state(context) -> dict | None:
    """The browser's storage state once NotebookLM has opened on a signed-in account."""
    if not any(urlsplit(page.url).hostname in APP_HOSTS for page in context.pages):
        return None
    state = context.storage_state()
    return state if REQUIRED_COOKIES <= {cookie.get("name") for cookie in state.get("cookies", [])} else None


def wait_for_sign_in(cdp_browser, timeout: float, sleep: Callable[[float], None] = time.sleep) -> dict:
    deadline = time.monotonic() + timeout
    seen_window = False
    while time.monotonic() < deadline:
        if not cdp_browser.is_connected():
            raise BlackboardSyncError(tr("The browser was closed before sign-in finished."))
        contexts = cdp_browser.contexts
        has_window = bool(contexts and contexts[0].pages)
        if seen_window and not has_window:
            raise BlackboardSyncError(tr("The browser window was closed before sign-in finished."))
        seen_window = seen_window or has_window
        state = signed_in_state(contexts[0]) if has_window else None
        if state is not None:
            return state
        sleep(POLL_SECONDS)
    raise BlackboardSyncError(tr("Sign-in was not completed within {n} minutes.").format(n=int(timeout // 60)))


def verify(config: Config) -> None:
    """Prove the session works: open the library on it (raises what ``runner.open_gateway`` raises)."""
    from blackboard_sync.notebooklm.runner import open_gateway

    async def check() -> None:
        await (await open_gateway(config)).close()

    asyncio.run(check())


def _capture_session(config: Config, app: Path, timeout: float, run, spawn, connect, platform) -> dict:
    profile = store.profile_dir(config)
    make_private_dir(profile, platform=platform)
    label = browser_label(app)
    port = free_port()
    start_browser(launch_command(app, profile, SIGN_IN_URL, platform, port=port), label, platform, run=run, spawn=spawn)
    wait_for_port(port)
    with _connector(connect) as connect_fn:
        try:
            browser = connect_fn(f"http://127.0.0.1:{port}")
        except Exception as exc:
            raise BrowserStartError(tr("Could not connect to {browser}: {error}").format(browser=label, error=exc)) from exc
        try:
            return wait_for_sign_in(browser, timeout)
        finally:
            _close_browser(browser)


def login(config: Config, timeout: float = SIGN_IN_TIMEOUT, run=subprocess.run, spawn=subprocess.Popen,
          connect=None, check: Callable[[Config], None] = verify, platform: str | None = None) -> None:
    """Sign in to Google and save the session; raises ``BlackboardSyncError`` with what went wrong."""
    config.ensure_data_dir()
    make_private_dir(config.notebooklm_dir, platform=platform)
    try:
        app = find_browser("auto", platform=platform)
    except NoSupportedBrowserError as exc:
        raise BlackboardSyncError(
            tr("NotebookLM needs Chrome, Edge or Brave to sign in to Google; install one and try again.")) from exc
    state = _capture_session(config, app, timeout, run, spawn, connect, platform)
    path = store.session_file(config)
    write_private_json(path, state)
    try:
        check(config)
    except NotebookLMLoginRequired:
        path.unlink(missing_ok=True)
        raise
    except NotebookLMTransient:
        pass  # Google could not be reached just now; the first run will tell
    store.mark_connected(config)

