"""The tray app's own event loop for the WebView2 window: what ``TrayApp`` uses of a Tk root.

With the Tk window, Tk's root owns the app's thread: timers (``after``), the wake-up
event workers send (``event_generate``) and ``mainloop``. pywebview wants the main
thread for its window instead, so the app's state then lives on a thread of its own
running this loop. Like Tk, it runs every callback on that one thread, so
``TrayApp`` keeps a single owner for the model; unlike Tk, ``after`` and
``event_generate`` may be called from any thread.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import sys
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)


class EventLoop:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._condition = threading.Condition()
        self._timers: list[tuple[float, int, Callable, tuple]] = []
        self._cancelled: set[int] = set()
        self._bindings: dict[str, Callable] = {}
        self._events: list[str] = []
        self._ids = itertools.count(1)
        self._destroyed = False
        self.on_destroy: list[Callable[[], None]] = []
        self.report_callback_exception = lambda *exc: log.error("Callback failed", exc_info=exc)

    # -- what TrayApp calls, as on a Tk root ------------------------------------
    def after(self, ms: int, callback: Callable, *args) -> int:
        """Run ``callback(*args)`` on the loop's thread in ``ms`` milliseconds; returns an id."""
        ident = next(self._ids)
        with self._condition:
            heapq.heappush(self._timers, (self.clock() + ms / 1000, ident, callback, args))
            self._condition.notify()
        return ident

    def after_cancel(self, ident: int) -> None:
        with self._condition:
            self._cancelled.add(ident)

    def bind(self, event: str, callback: Callable) -> None:
        self._bindings[event] = callback

    def event_generate(self, event: str, when: str | None = None) -> None:
        """Run the callback bound to ``event`` on the loop's thread, soon; raises once destroyed (as Tk)."""
        with self._condition:
            if self._destroyed:
                raise RuntimeError("the event loop is gone")
            self._events.append(event)
            self._condition.notify()

    def withdraw(self) -> None:
        """Tk's hidden root window; there is none here."""

    def mainloop(self) -> None:
        """Run callbacks until ``destroy``."""
        while True:
            job = self._next()
            if job is None:
                return
            callback, args = job
            try:
                callback(*args)
            except Exception:
                self.report_callback_exception(*sys.exc_info())

    def destroy(self) -> None:
        """End ``mainloop`` (after the callback that called this) and run ``on_destroy`` once."""
        with self._condition:
            if self._destroyed:
                return
            self._destroyed = True
            self._condition.notify_all()
        for callback in self.on_destroy:
            try:
                callback()
            except Exception:
                log.exception("Shutdown callback failed")

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    # -- inside ----------------------------------------------------------------
    def _next(self) -> tuple[Callable, tuple] | None:
        """The next callback to run, waiting for one; None once destroyed."""
        with self._condition:
            while not self._destroyed:
                if self._events:
                    event = self._events.pop(0)
                    callback = self._bindings.get(event)
                    if callback is not None:
                        return callback, (None,)
                    continue
                while self._timers and self._timers[0][1] in self._cancelled:
                    self._cancelled.discard(heapq.heappop(self._timers)[1])
                if self._timers:
                    wait = self._timers[0][0] - self.clock()
                    if wait <= 0:
                        _due, _ident, callback, args = heapq.heappop(self._timers)
                        return callback, args
                    self._condition.wait(wait)
                else:
                    self._condition.wait()
            return None
