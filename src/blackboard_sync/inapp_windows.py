"""The in-app sign-in window on Windows: Microsoft Edge WebView2 through pywebview.

WebView2 ships with Windows 10 and 11 (it is part of Microsoft Edge). Without
it pywebview would silently fall back to the old Internet Explorer engine,
which cannot read cookies and which Microsoft's sign-in no longer supports, so
that case is reported instead. The web view's data (the identity provider's
"stay signed in") is kept in a private folder in the data directory, like the
browser path's profile. ``window.get_cookies()`` reads WebView2's cookie
manager, which includes HttpOnly cookies, for the page that is open; once the
student is back on Blackboard those are the Blackboard cookies.
"""

from __future__ import annotations

import threading

from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.inapp import (
    WEBVIEW2_MISSING,
    WINDOW_SIZE,
    WINDOW_TITLE,
    Outcome,
    cookies_from_simple_cookies,
    watch_for_session,
)
from blackboard_sync.system import make_private_dir

GUI = "edgechromium"


def _load_webview2():
    """Import pywebview's WinForms backend and insist on WebView2."""
    try:
        import webview
        from webview.guilib import initialize
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise BlackboardSyncError(f"The sign-in window is unavailable: {exc}") from exc
    try:
        backend = initialize(GUI)
    except Exception as exc:  # pythonnet / .NET could not load
        raise BlackboardSyncError(f"The sign-in window is unavailable: {exc}") from exc
    if getattr(backend, "renderer", None) != GUI:
        raise BlackboardSyncError(WEBVIEW2_MISSING)
    return webview


def check_runtime() -> str:
    """Prove pythonnet, the WebView2 interop DLLs and the runtime load (CI)."""
    _load_webview2()
    return "WebView2"


def sign_in(url, base_url, timeout, check_user, profile_dir) -> tuple[dict, list[dict]]:
    """Show the window until sign-in finishes; runs the GUI loop on this thread."""
    webview = _load_webview2()
    # Pop-ups from the sign-in page open in this window, not in a browser.
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    make_private_dir(profile_dir)
    width, height = WINDOW_SIZE
    window = webview.create_window(WINDOW_TITLE, url, width=width, height=height)
    closed = threading.Event()
    window.events.closed += closed.set

    def fetch_cookies() -> list[dict]:
        try:
            return cookies_from_simple_cookies(window.get_cookies())
        except Exception:  # the window is going away
            return []

    def finished() -> None:
        if not closed.is_set():
            window.destroy()

    outcome = Outcome()

    def work():
        outcome.run(
            lambda: watch_for_session(fetch_cookies, base_url, check_user, timeout, closed),
            finished,
        )

    def begin():
        # pywebview's own worker thread is not a daemon; a cookie read cut off by
        # the window closing must not keep the process alive afterwards.
        threading.Thread(target=work, daemon=True).start()

    webview.start(begin, gui=GUI, private_mode=False, storage_path=str(profile_dir))
    return outcome.result()
