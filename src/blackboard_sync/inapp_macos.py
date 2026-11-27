"""The in-app sign-in window on macOS: a WKWebView in a plain Cocoa window.

Runs in the ``login`` process (a child of the menu bar app, or a terminal
command), which becomes a regular app with a Dock icon for as long as the
window is open. Cookies come from the web view's ``WKHTTPCookieStore``, which
includes HttpOnly cookies. The default (persistent) website data store keeps
the identity provider's "stay signed in" between sign-ins, like the browser
path's private profile does.
"""

from __future__ import annotations

import queue
import signal
import threading
import time
from urllib.parse import urlsplit

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivateIgnoringOtherApps,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSEvent,
    NSEventTypeApplicationDefined,
    NSMenu,
    NSMenuItem,
    NSRunningApplication,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSMakePoint, NSMakeRect, NSObject, NSURLRequest
from PyObjCTools import AppHelper
from WebKit import WKWebsiteDataStore, WKWebView, WKWebViewConfiguration

from blackboard_sync.i18n import tr
from blackboard_sync.inapp import (
    WINDOW_SIZE,
    WINDOW_TITLE,
    Outcome,
    blackboard_cookies,
    cookies_from_nshttpcookies,
    watch_for_session,
)
from blackboard_sync.session import cookie_matches_host, host_of

COOKIE_READ_SECONDS = 10
SILENT_POLL_SECONDS = 1.0

# Read-only DOM check used by WKWebView silent refresh: detects visible sign-in inputs or
# account pickers without ever reading, modifying, or submitting any field values.
_SILENT_STATE_JS = """
(() => {
  const vis = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const sels = [
    "input[type=password]",
    "input[type=email]",
    "input[type=text][name*='user' i]",
    "input[type=text][name*='login' i]",
    "input[type=text][name*='email' i]",
    "input[type=text][id*='user' i]",
    "input[type=text][id*='login' i]",
    "input[type=text][id*='email' i]",
    "input[name*='otp' i]",
    "input[name*='code' i]",
    "input[id*='otp' i]",
    "input[id*='code' i]",
    "input[autocomplete*='one-time-code' i]",
    "[data-testid*='account' i]",
    "[id*='account-list' i]",
    "[class*='account-tile' i]",
    "[class*='account-item' i]",
    "div[role='listbox']"
  ];
  const wants = sels.some((q) => Array.from(document.querySelectorAll(q)).some(vis));
  return [String(location.href || ''), String(document.title || ''), Boolean(wants)];
})()
"""


class SignInWindowDelegate(NSObject):
    """Notices the student closing the window; opens pop-ups in the same view."""

    def initWithClosed_(self, closed):
        self = objc.super(SignInWindowDelegate, self).init()
        if self is None:
            return None
        self.closed = closed
        return self

    def windowWillClose_(self, _notification):
        self.closed.set()
        stop_event_loop()

    # WKUIDelegate: a sign-in page that opens a new window (target=_blank,
    # window.open) continues in this one instead of doing nothing.
    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, web_view, _configuration, action, _features
    ):
        web_view.loadRequest_(action.request())
        return None


def stop_event_loop() -> None:
    """End ``NSApp.run()`` and return to Python.

    (``AppHelper.stopEventLoop`` would terminate the process instead, before
    the session is saved.) ``stop:`` takes effect after the next event, so post one.
    """
    app = NSApplication.sharedApplication()
    app.stop_(None)
    wake = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
        NSEventTypeApplicationDefined, NSMakePoint(0, 0), 0, 0, 0, None, 0, 0, 0
    )
    app.postEvent_atStart_(wake, True)


def _edit_menu() -> NSMenu:
    """A main menu, so Cmd+C / Cmd+V / Cmd+A / Cmd+W work in the sign-in page."""
    bar = NSMenu.alloc().init()
    for title, items in (
        ("Blackboard Sync", [(tr("Close Sign-in Window"), "performClose:", "w")]),
        ("Edit", [
            (tr("Undo"), "undo:", "z"),
            (tr("Cut"), "cut:", "x"),
            (tr("Copy"), "copy:", "c"),
            (tr("Paste"), "paste:", "v"),
            (tr("Select All"), "selectAll:", "a"),
        ]),
    ):
        holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        menu = NSMenu.alloc().initWithTitle_(title)
        for label, action, key in items:
            menu.addItemWithTitle_action_keyEquivalent_(label, action, key)
        holder.setSubmenu_(menu)
        bar.addItem_(holder)
    return bar


def check_runtime() -> str:
    """Prove WebKit loads (CI's ``--check-login-runtime``)."""
    WKWebViewConfiguration.alloc().init()
    return "WKWebView"


def sign_in(url, base_url, timeout, check_user, profile_dir) -> tuple[dict, list[dict]]:
    """Show the window until sign-in finishes; runs the Cocoa event loop on this thread.

    ``profile_dir`` is unused: WKWebView keeps its data in the app's own
    website data store.
    """
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.setMainMenu_(_edit_menu())

    closed = threading.Event()
    delegate = SignInWindowDelegate.alloc().initWithClosed_(closed)
    config = WKWebViewConfiguration.alloc().init()
    config.setWebsiteDataStore_(WKWebsiteDataStore.defaultDataStore())
    width, height = WINDOW_SIZE
    frame = NSMakeRect(0, 0, width, height)
    style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
             | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, style, NSBackingStoreBuffered, False
    )
    window.setReleasedWhenClosed_(False)
    window.setTitle_(WINDOW_TITLE)
    web_view = WKWebView.alloc().initWithFrame_configuration_(frame, config)
    web_view.setUIDelegate_(delegate)
    window.setContentView_(web_view)
    window.setDelegate_(delegate)
    window.center()
    web_view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

    def bring_to_front() -> None:
        # Once the app is running: become the active app and put the window on
        # top, even when started from a background process or terminal session.
        NSRunningApplication.currentApplication().activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps
        )
        if app.respondsToSelector_("activate"):  # macOS 14+
            app.activate()
        else:
            app.activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)
        window.orderFrontRegardless()

    window.makeKeyAndOrderFront_(None)
    AppHelper.callAfter(bring_to_front)

    store = config.websiteDataStore().httpCookieStore()

    def fetch_cookies() -> list[dict]:
        # The cookie store answers on the main thread; convert there, hand over plain dicts.
        answer: queue.Queue = queue.Queue()
        AppHelper.callAfter(
            lambda: store.getAllCookies_(lambda cookies: answer.put(cookies_from_nshttpcookies(cookies)))
        )
        try:
            return answer.get(timeout=COOKIE_READ_SECONDS)
        except queue.Empty:
            return []

    def finished() -> None:
        if not closed.is_set():
            AppHelper.callAfter(window.close)

    def interrupted(*_args) -> None:
        # Ctrl+C in the terminal: Python sees it at the next cookie read.
        closed.set()
        window.close()

    outcome = Outcome()
    threading.Thread(
        target=outcome.run,
        args=(lambda: watch_for_session(fetch_cookies, base_url, check_user, timeout, closed), finished),
        daemon=True,
    ).start()
    previous = signal.signal(signal.SIGINT, interrupted)
    try:
        app.run()
    finally:
        signal.signal(signal.SIGINT, previous)
    return outcome.result()


def _is_login_url(url: str, base_url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    bb_host = host_of(base_url).lower()
    if host not in ("", "about", bb_host):
        return True
    lowered = url.lower()
    return any(marker in lowered for marker in ("/webapps/login", "/auth-saml", "/webapps/bb-auth-provider"))


def silent_sign_in(
    base_url: str,
    timeout: float,
    check_user,
    stillness_timeout: float = 6.0,
    clock=time.monotonic,
) -> tuple[str, dict | None, list[dict]]:
    """Refresh the Blackboard session silently using an offscreen WKWebView and its persistent cookie store.

    Used by Mac App Store (``mas``) builds in place of headless external Chromium + Playwright CDP.
    Shows no window and no Dock icon: Blackboard cookies are cleared first so stale cookies are not
    re-saved, while the school's SSO cookies in ``WKWebsiteDataStore.defaultDataStore()`` remain intact.
    """
    app = NSApplication.sharedApplication()
    if not app.isRunning():
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    closed = threading.Event()
    delegate = SignInWindowDelegate.alloc().initWithClosed_(closed)
    config = WKWebViewConfiguration.alloc().init()
    config.setWebsiteDataStore_(WKWebsiteDataStore.defaultDataStore())
    web_view = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, 800, 600), config)
    web_view.setUIDelegate_(delegate)
    store = config.websiteDataStore().httpCookieStore()
    bb_host = host_of(base_url)

    def clear_blackboard_cookies_and_load() -> None:
        def on_cookies(all_cookies) -> None:
            to_delete = [
                c for c in (all_cookies or [])
                if cookie_matches_host(str(c.domain() or bb_host), bb_host)
            ]
            if not to_delete:
                web_view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(base_url + "/")))
                return
            remaining = [len(to_delete)]

            def after_delete() -> None:
                remaining[0] -= 1
                if remaining[0] <= 0:
                    web_view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(base_url + "/")))

            for cookie in to_delete:
                store.deleteCookie_completionHandler_(cookie, after_delete)

        store.getAllCookies_(on_cookies)

    def fetch_cookies() -> list[dict]:
        answer: queue.Queue = queue.Queue()
        AppHelper.callAfter(
            lambda: store.getAllCookies_(lambda cookies: answer.put(cookies_from_nshttpcookies(cookies)))
        )
        try:
            return answer.get(timeout=COOKIE_READ_SECONDS)
        except queue.Empty:
            return []

    def inspect_page() -> tuple[str, str, bool]:
        answer: queue.Queue = queue.Queue()

        def evaluate() -> None:
            def on_js(result, _error) -> None:
                if result is not None and len(result) == 3:
                    answer.put((str(result[0] or ""), str(result[1] or ""), bool(result[2])))
                else:
                    current_url = str(web_view.URL().absoluteString() if web_view.URL() else "")
                    answer.put((current_url, str(web_view.title() or ""), False))

            web_view.evaluateJavaScript_completionHandler_(_SILENT_STATE_JS, on_js)

        AppHelper.callAfter(evaluate)
        try:
            return answer.get(timeout=5.0)
        except queue.Empty:
            return "", "", False

    result_box: list[tuple[str, dict | None, list[dict]]] = []

    def poll_worker() -> None:
        reason, found_user, found_cookies = "timeout", None, []
        try:
            deadline = clock() + timeout
            last_snap = None
            snap_since = clock()
            # Give initial cookie deletion + request start a brief moment.
            closed.wait(0.4)
            while clock() < deadline and not closed.is_set():
                cookies = blackboard_cookies(fetch_cookies(), base_url)
                user = check_user(base_url, cookies) if cookies else None
                if user:
                    reason, found_user, found_cookies = "refreshed", user, cookies
                    return
                url_str, title_str, wants_student = inspect_page()
                now = clock()
                snap = (url_str, title_str)
                if url_str and snap != last_snap:
                    last_snap = snap
                    snap_since = now
                elif last_snap is not None and (now - snap_since) >= stillness_timeout:
                    reason = "sso-needs-interaction"
                    return
                if wants_student:
                    reason = "sso-needs-interaction"
                    return
                if "/webapps/login" in url_str.lower() and (now - snap_since) >= 2.0:
                    reason = "sso-needs-interaction"
                    return
                closed.wait(SILENT_POLL_SECONDS)
            url_str, _, _ = inspect_page()
            if _is_login_url(url_str, base_url):
                reason = "sso-needs-interaction"
        finally:
            result_box.append((reason, found_user, found_cookies))
            AppHelper.callAfter(finish)

    def finish() -> None:
        closed.set()
        web_view.stopLoading()
        stop_event_loop()

    def interrupted(*_args) -> None:
        closed.set()
        AppHelper.callAfter(finish)

    AppHelper.callAfter(clear_blackboard_cookies_and_load)
    threading.Thread(target=poll_worker, daemon=True).start()
    previous = signal.signal(signal.SIGINT, interrupted)
    try:
        app.run()
    finally:
        signal.signal(signal.SIGINT, previous)
    return result_box[0] if result_box else ("error", None, [])
