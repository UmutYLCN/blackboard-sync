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

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivateIgnoringOtherApps,
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

from blackboard_sync.inapp import (
    WINDOW_SIZE,
    WINDOW_TITLE,
    Outcome,
    cookies_from_nshttpcookies,
    watch_for_session,
)

COOKIE_READ_SECONDS = 10


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
        ("Blackboard Sync", [("Giriş penceresini kapat", "performClose:", "w")]),
        ("Düzen", [
            ("Geri al", "undo:", "z"),
            ("Kes", "cut:", "x"),
            ("Kopyala", "copy:", "c"),
            ("Yapıştır", "paste:", "v"),
            ("Tümünü seç", "selectAll:", "a"),
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
