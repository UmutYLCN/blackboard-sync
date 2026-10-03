"""Interactive sign-in through the student's own Chrome or Brave.

The browser is started the way the Dock or Finder would start it: through
macOS LaunchServices (``open -n -a <app>``), with a private profile kept in the
data directory. That makes it an ordinary, frontmost app window that takes the
keyboard, even when this command runs from a terminal multiplexer or another
background session. (Starting the browser binary directly as a child process
can leave the window unable to take keyboard focus there; see the README's
troubleshooting section.)

The student signs in normally (including single sign-on and two-factor steps);
this tool never sees the password. It only watches over the browser's local
DevTools port until Blackboard accepts the session, then saves the Blackboard
cookies for ``sync`` and closes the browser.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.session import save_session

BROWSERS = {
    "chrome": "Google Chrome.app",
    "brave": "Brave Browser.app",
}
APP_DIRS = [Path("/Applications"), Path.home() / "Applications"]
# Chromium writes the port it picked for --remote-debugging-port=0 here.
DEVTOOLS_PORT_FILE = "DevToolsActivePort"
POLL_SECONDS = 2


def find_browser(preference: str = "auto", app_dirs: list[Path] | None = None) -> Path:
    """Locate an installed Chrome or Brave app bundle."""
    order = ["chrome", "brave"] if preference == "auto" else [preference]
    for name in order:
        if name not in BROWSERS:
            raise BlackboardSyncError(f"Unknown browser {name!r}; use chrome or brave.")
        for app_dir in app_dirs or APP_DIRS:
            candidate = app_dir / BROWSERS[name]
            if candidate.is_dir():
                return candidate
    wanted = "Google Chrome or Brave" if preference == "auto" else preference
    raise BlackboardSyncError(f"Could not find {wanted} in /Applications.")


def launch_command(app: Path, profile_dir: Path, url: str) -> list[str]:
    """The ``open`` command that starts a separate, normal browser instance.

    ``-n`` starts a new instance even if the student's everyday browser is
    already running; ``--user-data-dir`` keeps it apart from their own profile.
    Port 0 lets the browser pick a free local port for DevTools.
    """
    return [
        "/usr/bin/open",
        "-n",
        "-a",
        str(app),
        "--args",
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]


def wait_for_devtools_port(profile_dir: Path, timeout: float = 30) -> int:
    """Read the DevTools port the freshly started browser wrote to its profile."""
    port_file = profile_dir / DEVTOOLS_PORT_FILE
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            first_line = port_file.read_text().splitlines()[0].strip()
            port = int(first_line)
            if port > 0:
                return port
        except (OSError, IndexError, ValueError):
            pass
        time.sleep(0.25)
    raise BlackboardSyncError(
        "The browser did not start. If a sign-in window from an earlier attempt is "
        "still open, close it and run `blackboard-sync login` again."
    )


def session_user(base_url: str, cookies: list[dict], http: requests.Session | None = None) -> dict | None:
    """Return the signed-in Blackboard user for these cookies, or None."""
    http = http or requests.Session()
    for c in cookies:
        http.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path") or "/")
    try:
        data = BlackboardClient(base_url, http, timeout=15).me()
    except (BlackboardSyncError, requests.RequestException):
        return None
    return data if data.get("id") else None


def _close_browser(browser) -> None:
    """Quit the sign-in browser instance (not the student's everyday browser)."""
    try:
        browser.new_browser_cdp_session().send("Browser.close")
    except Exception:  # already gone
        pass
    try:
        browser.close()
    except Exception:
        pass


def login(
    config: Config,
    browser: str = "auto",
    timeout: float = 600,
    out=print,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    connect: Callable[[str], object] | None = None,
    check_user: Callable[[str, list[dict]], dict | None] = session_user,
) -> dict:
    """Open a browser, wait for the student to sign in, save the session."""
    app = find_browser(browser)
    config.ensure_data_dir()
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.profile_dir, 0o700)
    stale = config.profile_dir / DEVTOOLS_PORT_FILE
    if stale.exists():
        stale.unlink()

    out(f"Opening {app.stem} on {config.base_url} ...")
    out("Sign in to Blackboard in that window. It closes by itself once you are in.")
    result = run(
        launch_command(app, config.profile_dir, config.base_url + "/"),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BlackboardSyncError(f"Could not open {app.stem}: {result.stderr.strip()}")
    port = wait_for_devtools_port(config.profile_dir)

    with _connector(connect) as connect_fn:
        cdp_browser = connect_fn(f"http://127.0.0.1:{port}")
        try:
            user, cookies = _wait_for_sign_in(cdp_browser, config.base_url, timeout, check_user)
        finally:
            _close_browser(cdp_browser)

    kept = save_session(config.session_file, config.base_url, cookies, user)
    out(f"Signed in as {user.get('userName') or user.get('id')}; session saved ({kept} cookies).")
    return user


def _wait_for_sign_in(cdp_browser, base_url: str, timeout: float, check_user) -> tuple[dict, list[dict]]:
    deadline = time.monotonic() + timeout
    seen_window = False
    while time.monotonic() < deadline:
        if not cdp_browser.is_connected():
            raise BlackboardSyncError("The browser was closed before sign-in finished.")
        contexts = cdp_browser.contexts
        has_window = bool(contexts and contexts[0].pages)
        if seen_window and not has_window:
            # On macOS the app keeps running after its last window is closed.
            raise BlackboardSyncError("The browser window was closed before sign-in finished.")
        seen_window = seen_window or has_window
        if not contexts:
            time.sleep(POLL_SECONDS)
            continue
        cookies = contexts[0].cookies(base_url)
        user = check_user(base_url, cookies) if cookies else None
        if user:
            return user, cookies
        time.sleep(POLL_SECONDS)
    raise BlackboardSyncError(f"Sign-in was not completed within {int(timeout // 60)} minutes.")


class _connector:
    """Provide a ``connect(url)`` function, starting Playwright only when needed."""

    def __init__(self, connect):
        self.connect = connect
        self._pw = None

    def __enter__(self):
        if self.connect is not None:
            return self.connect
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise BlackboardSyncError("Playwright is not installed; run scripts/setup.sh.") from exc
        self._pw = sync_playwright().start()
        return self._pw.chromium.connect_over_cdp

    def __exit__(self, *exc):
        if self._pw is not None:
            self._pw.stop()
