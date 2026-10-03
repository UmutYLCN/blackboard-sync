"""Interactive sign-in through the student's own Chrome or Brave.

A visible browser window opens on the Blackboard sign-in page with a private
profile kept in the data directory. The student signs in normally (including
any single sign-on or two-factor step); this tool never sees the password. Once
Blackboard accepts the session, its cookies are saved for ``sync`` to reuse.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from blackboard_sync.api import PUBLIC
from blackboard_sync.config import Config
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.session import save_session

BROWSERS = {
    "chrome": ["Google Chrome.app/Contents/MacOS/Google Chrome"],
    "brave": ["Brave Browser.app/Contents/MacOS/Brave Browser"],
}
APP_DIRS = [Path("/Applications"), Path.home() / "Applications"]


def find_browser(preference: str = "auto") -> Path:
    """Locate an installed Chrome or Brave executable."""
    order = ["chrome", "brave"] if preference == "auto" else [preference]
    for name in order:
        if name not in BROWSERS:
            raise BlackboardSyncError(f"Unknown browser {name!r}; use chrome or brave.")
        for app_dir in APP_DIRS:
            for rel in BROWSERS[name]:
                candidate = app_dir / rel
                if candidate.exists():
                    return candidate
    wanted = "Google Chrome or Brave" if preference == "auto" else preference
    raise BlackboardSyncError(f"Could not find {wanted} in /Applications.")


def login(config: Config, browser: str = "auto", timeout: float = 600, out=print) -> dict:
    """Open a browser, wait for the student to sign in, save the session."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise BlackboardSyncError("Playwright is not installed; run scripts/setup.sh.") from exc

    executable = find_browser(browser)
    config.ensure_data_dir()
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.profile_dir, 0o700)

    me_url = f"{config.base_url}{PUBLIC}/v1/users/me"
    out(f"Opening {executable.parent.parent.parent.name} on {config.base_url} ...")
    out("Sign in to Blackboard in that window. It closes by itself once you are in.")

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            executable_path=str(executable),
            headless=False,
            no_viewport=True,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(config.base_url + "/", wait_until="domcontentloaded")
            deadline = time.monotonic() + timeout
            user = None
            while time.monotonic() < deadline:
                if not context.pages:
                    raise BlackboardSyncError("The browser window was closed before sign-in finished.")
                try:
                    resp = context.request.get(me_url, headers={"Accept": "application/json"})
                    if resp.ok and "json" in resp.headers.get("content-type", ""):
                        data = resp.json()
                        if data.get("id"):
                            user = data
                            break
                except PlaywrightError:
                    if not context.pages:
                        raise BlackboardSyncError(
                            "The browser window was closed before sign-in finished."
                        )
                time.sleep(2)
            if user is None:
                raise BlackboardSyncError(
                    f"Sign-in was not completed within {int(timeout // 60)} minutes."
                )
            cookies = context.cookies(config.base_url)
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass

    kept = save_session(config.session_file, config.base_url, cookies, user)
    out(f"Signed in as {user.get('userName') or user.get('id')}; session saved ({kept} cookies).")
    return user
