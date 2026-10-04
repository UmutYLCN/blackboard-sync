"""Interactive sign-in through the student's own Chrome, Edge or Brave.

On macOS the browser is started the way the Dock or Finder would start it:
through LaunchServices (``open -n -a <app>``), with a private profile kept in
the data directory. That makes it an ordinary, frontmost app window that takes
the keyboard, even when this command runs from a terminal multiplexer or
another background session. (Starting the browser binary directly as a child
process can leave the window unable to take keyboard focus there; see the
README's troubleshooting section.) On Windows the installed ``chrome.exe`` /
``msedge.exe`` / ``brave.exe`` is started as its own detached process with the
same private profile and flags.

The student signs in normally (including single sign-on and two-factor steps);
this tool never sees the password. It only watches over the browser's local
DevTools port (127.0.0.1) until Blackboard accepts the session, then saves the
Blackboard cookies for ``sync`` and closes the browser.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping

import requests

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.session import save_session
from blackboard_sync.system import is_windows, make_private_dir

BROWSERS = {
    "chrome": "Google Chrome.app",
    "brave": "Brave Browser.app",
    "edge": "Microsoft Edge.app",
}
APP_DIRS = [Path("/Applications"), Path.home() / "Applications"]
# Windows: executable name and its folder below Program Files / %LOCALAPPDATA%.
WINDOWS_BROWSERS = {
    "chrome": ("chrome.exe", ("Google", "Chrome", "Application")),
    "edge": ("msedge.exe", ("Microsoft", "Edge", "Application")),
    "brave": ("brave.exe", ("BraveSoftware", "Brave-Browser", "Application")),
}
BROWSER_LABELS = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "brave": "Brave"}
# Edge ships with every Windows, so it is the dependable fallback there.
AUTO_ORDER = {"darwin": ["chrome", "brave", "edge"], "win32": ["chrome", "edge", "brave"]}
# Chromium writes the port it picked for --remote-debugging-port=0 here.
DEVTOOLS_PORT_FILE = "DevToolsActivePort"
POLL_SECONDS = 2
# Windows: run the browser on its own, without a console and outside our
# Ctrl+C group, like an app started from the Start menu.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _browser_order(preference: str, platform: str | None) -> list[str]:
    if preference != "auto":
        if preference not in BROWSERS:
            raise BlackboardSyncError(f"Unknown browser {preference!r}; use chrome, edge or brave.")
        return [preference]
    return AUTO_ORDER["win32" if is_windows(platform) else "darwin"]


def find_browser(
    preference: str = "auto",
    app_dirs: list[Path] | None = None,
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    registry: Callable[[str], list[str]] | None = None,
) -> Path:
    """Locate an installed browser: an app bundle on macOS, an ``.exe`` on Windows."""
    order = _browser_order(preference, platform)
    if is_windows(platform):
        for name in order:
            for candidate in windows_browser_candidates(name, env, registry):
                if candidate.is_file():
                    return candidate
        wanted = "Google Chrome, Microsoft Edge or Brave" if preference == "auto" else BROWSER_LABELS[preference]
        raise BlackboardSyncError(f"Could not find {wanted} on this computer.")
    for name in order:
        for app_dir in app_dirs or APP_DIRS:
            candidate = app_dir / BROWSERS[name]
            if candidate.is_dir():
                return candidate
    wanted = "Google Chrome or Brave" if preference == "auto" else preference
    raise BlackboardSyncError(f"Could not find {wanted} in /Applications.")


def windows_browser_candidates(
    name: str,
    env: Mapping[str, str] | None = None,
    registry: Callable[[str], list[str]] | None = None,
) -> list[Path]:
    """Where a Windows browser may be installed, most authoritative first.

    The "App Paths" registry entries the installers write come first, then the
    standard per-machine and per-user install folders.
    """
    env = os.environ if env is None else env
    exe, parts = WINDOWS_BROWSERS[name]
    found = [Path(p) for p in (registry or windows_app_paths)(exe) if p]
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = env.get(var)
        if base:
            found.append(Path(base).joinpath(*parts, exe))
    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def windows_app_paths(exe: str) -> list[str]:
    """The registered location of ``exe`` (HKCU, then HKLM "App Paths")."""
    try:
        import winreg
    except ImportError:  # not Windows
        return []
    key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    paths = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as handle:
                value, _ = winreg.QueryValueEx(handle, None)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            paths.append(os.path.expandvars(value.strip().strip('"')))
    return paths


def browser_label(app: Path) -> str:
    """A readable browser name: "Google Chrome", "Microsoft Edge", "Brave Browser"."""
    for name, (exe, _) in WINDOWS_BROWSERS.items():
        if app.name.lower() == exe:
            return BROWSER_LABELS[name]
    return app.stem


def browser_flags(profile_dir: Path, url: str) -> list[str]:
    """A separate, normal browser instance with a private profile.

    ``--user-data-dir`` keeps it apart from the student's own profile (and
    makes it a new instance even if their everyday browser is running). Port 0
    lets the browser pick a free local port for DevTools, which Chromium binds
    to 127.0.0.1 only.
    """
    return [
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]


def launch_command(app: Path, profile_dir: Path, url: str, platform: str | None = None) -> list[str]:
    """The command that starts the sign-in browser.

    macOS: ``open -n -a`` (``-n`` starts a new instance even if the student's
    everyday browser is already running). Windows: the browser executable.
    """
    if is_windows(platform):
        return [str(app), *browser_flags(profile_dir, url)]
    return ["/usr/bin/open", "-n", "-a", str(app), "--args", *browser_flags(profile_dir, url)]


def start_browser(
    argv: list[str],
    label: str,
    platform: str | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    spawn: Callable[..., object] = subprocess.Popen,
) -> None:
    if not is_windows(platform):
        result = run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            raise BlackboardSyncError(f"Could not open {label}: {result.stderr.strip()}")
        return
    try:
        spawn(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as exc:
        raise BlackboardSyncError(f"Could not open {label}: {exc}") from exc


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
    spawn: Callable[..., object] = subprocess.Popen,
    platform: str | None = None,
) -> dict:
    """Open a browser, wait for the student to sign in, save the session."""
    app = find_browser(browser, platform=platform)
    label = browser_label(app)
    config.ensure_data_dir()
    make_private_dir(config.profile_dir, platform=platform)
    stale = config.profile_dir / DEVTOOLS_PORT_FILE
    if stale.exists():
        stale.unlink()

    out(f"Opening {label} on {config.base_url} ...")
    out("Sign in to Blackboard in that window. It closes by itself once you are in.")
    start_browser(
        launch_command(app, config.profile_dir, config.base_url + "/", platform),
        label,
        platform,
        run=run,
        spawn=spawn,
    )
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
            raise BlackboardSyncError("Playwright is not installed; see the README's setup steps.") from exc
        self._pw = sync_playwright().start()
        return self._pw.chromium.connect_over_cdp

    def __exit__(self, *exc):
        if self._pw is not None:
            self._pw.stop()
