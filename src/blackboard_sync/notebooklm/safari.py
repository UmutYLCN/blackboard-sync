"""Gemini Notebook in the Mac App Store build: through Safari and the app's own Safari extension.

The App Sandbox lets the app neither drive a browser nor take Google's cookies, so the app hands
the Google side to its Safari Web Extension (``packaging/safari-extension``). The extension runs on
the Gemini Notebook page, where the student is signed in to Google in Safari, and makes the same few
calls ``gateway`` makes with the library. This app never sees a Google cookie or password.

The app and the page talk over a loopback ``Bridge``: the app opens Safari at the notebook page with
the bridge's port and a one-time token in the address fragment, which never leaves the browser.
The page asks the bridge for work (``/next``), answers it (``/result``) and reads the files to add
(``/file``). ``SafariGateway`` puts the ``Gateway`` surface on top, so ``runner`` stays as it is.

Safari asks the student twice, once: to turn the extension on, and to let it run on
notebook.google.com. ``connect`` walks them through both and proves the page answers.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hmac
import itertools
import json
import logging
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from blackboard_sync.errors import (
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMRateLimited,
    NotebookLMSignInFailed,
    NotebookLMTransient,
)
from blackboard_sync.i18n import tr
from blackboard_sync.notebooklm import remote, store
from blackboard_sync.notebooklm.remote import RemoteNotebook, RemoteSource
from blackboard_sync.session import write_private_json

log = logging.getLogger(__name__)

SAFARI = "com.apple.Safari"
DEFAULT_BUNDLE_ID = "io.github.umutylcn.blackboard-sync.mas"
EXTENSION_SUFFIX = ".SafariExtension"  # the extension's bundle id, after the app's
HEADER = "X-BBSync-Token"

LONG_POLL_SECONDS = 20.0  # how long the page's ask for work is held open
HELLO_SECONDS = 60.0  # a run's wait for the page to answer before it gives up
CALL_SECONDS = 120.0
UPLOAD_SECONDS = 15 * 60.0
REGISTER_SECONDS = 30.0  # a new source must be listed before it can be renamed
LOST_SECONDS = 90.0  # the page pings every 10 s; this long without it, the tab is gone
ALLOW_HINT_SECONDS = 8.0  # connect: no word from the page this long, so Safari has not let it run
SIGN_IN_TIMEOUT = 600.0

ENABLED, DISABLED, UNKNOWN = "enabled", "disabled", "unknown"
# What ``connect`` reports while it waits, as ``{"event": "sign_in", "step": ...}``.
STEP_EXTENSION, STEP_ALLOW, STEP_GOOGLE, STEP_VERIFY = "extension", "allow", "google", "verify"

T_EXTENSION_OFF = tr("Turn on the Blackboard Sync extension in Safari, then try again.")
T_NO_ANSWER = tr("Safari did not answer. Allow Blackboard Sync on notebook.google.com in Safari, then try again.")
T_SIGN_IN_SAFARI = tr("Sign in to Google in Safari, then try again.")
T_TAB_CLOSED = tr("The Safari tab closed before all files were added. Sync again to go on.")


class BridgeError(Exception):
    """The page answered with a failure; ``kind`` is login, rate, transient or permanent."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class BridgeLost(Exception):
    """The page stopped asking for work: the Safari tab was closed or Safari quit."""


def bundle_id() -> str:
    """The app's bundle id; the extension's is this plus ``EXTENSION_SUFFIX``."""
    if getattr(sys, "frozen", False):
        try:
            from Foundation import NSBundle

            found = NSBundle.mainBundle().bundleIdentifier()
            if found:
                return str(found)
        except Exception:  # pragma: no cover - only in a broken bundle
            log.exception("could not read the bundle id")
    return (os.environ.get("BBSYNC_MAS_BUNDLE_ID") or DEFAULT_BUNDLE_ID).strip()


def extension_id() -> str:
    return bundle_id() + EXTENSION_SUFFIX


_services: dict | None = None


def _safari_services() -> dict:
    """SafariServices through PyObjC's bridge, with the two completion blocks it needs described."""
    global _services
    if _services is None:
        import objc

        found: dict = {}
        objc.loadBundle("SafariServices", found, bundle_path="/System/Library/Frameworks/SafariServices.framework")
        state_block = {"callable": {"retval": {"type": b"v"},
                                    "arguments": {0: {"type": b"^v"}, 1: {"type": b"@"}, 2: {"type": b"@"}}}}
        done_block = {"callable": {"retval": {"type": b"v"}, "arguments": {0: {"type": b"^v"}, 1: {"type": b"@"}}}}
        objc.registerMetaDataForSelector(b"SFSafariExtensionManager",
                                         b"getStateOfSafariExtensionWithIdentifier:completionHandler:",
                                         {"arguments": {3: state_block}})
        objc.registerMetaDataForSelector(b"SFSafariApplication",
                                         b"showPreferencesForExtensionWithIdentifier:completionHandler:",
                                         {"arguments": {3: done_block}})
        _services = found
    return _services


def extension_state(timeout: float = 5.0) -> str:
    """Whether Safari has the extension turned on; ``UNKNOWN`` when Safari cannot say."""
    try:
        manager = _safari_services()["SFSafariExtensionManager"]
    except Exception:
        log.exception("SafariServices is not available")
        return UNKNOWN
    answered = threading.Event()
    result = {"state": UNKNOWN}

    def handler(state, error):
        if state is not None and error is None:
            result["state"] = ENABLED if state.isEnabled() else DISABLED
        else:
            log.warning("Safari did not report the extension's state: %s", error)
        answered.set()

    manager.getStateOfSafariExtensionWithIdentifier_completionHandler_(extension_id(), handler)
    answered.wait(timeout)
    return result["state"]


def open_extension_settings() -> bool:
    """Safari's Settings, on this app's extension; False when Safari could not show them."""
    try:
        application = _safari_services()["SFSafariApplication"]
    except Exception:
        log.exception("SafariServices is not available")
        return False
    shown = threading.Event()
    outcome = {"ok": False}

    def handler(error):
        outcome["ok"] = error is None
        if error is not None:
            log.warning("Safari did not show the extension settings: %s", error)
        shown.set()

    application.showPreferencesForExtensionWithIdentifier_completionHandler_(extension_id(), handler)
    shown.wait(10.0)
    return outcome["ok"]


def open_page(url: str, background: bool = False, run=subprocess.run) -> bool:
    """Open ``url`` in Safari, whatever the default browser; ``background`` leaves Safari behind."""
    command = ["open", *(["-g"] if background else []), "-b", SAFARI, url]
    try:
        return run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("could not open Safari: %s", exc)
        return False


class Bridge:
    """The loopback server the page works for. One token, one run; any number of calls at once."""

    def __init__(self, host: str = "127.0.0.1", long_poll: float = LONG_POLL_SECONDS):
        self.host = host
        self.long_poll = long_poll
        self.token = secrets.token_urlsafe(24)
        self.reached = threading.Event()  # the page asked for work at least once
        self.last_seen = 0.0
        self._cond = threading.Condition()
        self._queue: deque[dict] = deque()
        self._pending: dict[str, concurrent.futures.Future] = {}
        self._files: dict[str, Path] = {}
        self._ids = itertools.count(1)
        self._goodbye: dict | None = None  # once set, every ask for work gets it
        self._heard_goodbye = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    # The app's side.
    def start(self) -> int:
        bridge = self
        handler = type("BridgeHandler", (_Handler,), {"bridge": bridge})
        self._server = ThreadingHTTPServer((self.host, 0), handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="safari-bridge", daemon=True).start()
        return self.port

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else 0

    def address(self, base: str = store.APP_URL) -> str:
        return f"{base}#bbsync={self.port}.{self.token}"

    def offer(self, path: Path) -> str:
        file_id = secrets.token_urlsafe(9)
        with self._cond:
            self._files[file_id] = Path(path)
        return file_id

    def withdraw(self, file_id: str) -> None:
        with self._cond:
            self._files.pop(file_id, None)

    def lost(self, now: float | None = None) -> bool:
        return self.reached.is_set() and (now or time.monotonic()) - self.last_seen > LOST_SECONDS

    async def call(self, op: str, args: dict | None = None, timeout: float = CALL_SECONDS) -> Any:
        """Have the page do ``op``; raises ``BridgeError``, ``BridgeLost`` or ``asyncio.TimeoutError``."""
        request_id = f"r{next(self._ids)}"
        future: concurrent.futures.Future = concurrent.futures.Future()
        with self._cond:
            self._pending[request_id] = future
            self._queue.append({"id": request_id, "op": op, "args": args or {}})
            self._cond.notify_all()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        waiting = asyncio.wrap_future(future)
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise asyncio.TimeoutError(op)
                done, _ = await asyncio.wait({waiting}, timeout=min(remaining, 1.0))
                if done:
                    reply = waiting.result()
                    break
                if self.lost():
                    raise BridgeLost(op)
        finally:
            with self._cond:
                self._pending.pop(request_id, None)
                self._queue = deque(item for item in self._queue if item["id"] != request_id)
            if not waiting.done():
                waiting.cancel()
        if reply.get("ok"):
            return reply.get("value")
        error = reply.get("error") or {}
        raise BridgeError(str(error.get("kind") or "transient"), str(error.get("message") or op))

    def stop(self, close_tab: bool = False, linger: float = 2.0) -> None:
        """Tell the page the work is done, give it a moment to hear that, and close the server."""
        if self._server is None:
            return
        with self._cond:
            self._goodbye = {"op": "bye", "args": {"close": close_tab}}
            self._cond.notify_all()
        if self.reached.is_set():
            self._heard_goodbye.wait(linger)
        server, self._server = self._server, None
        server.shutdown()
        server.server_close()

    # The page's side, on the server's threads.
    def _seen(self) -> None:
        self.last_seen = time.monotonic()
        self.reached.set()

    def _next(self) -> dict:
        self._seen()
        end = time.monotonic() + self.long_poll
        with self._cond:
            while True:
                if self._queue:
                    return self._queue.popleft()
                if self._goodbye is not None:
                    self._heard_goodbye.set()
                    return self._goodbye
                left = end - time.monotonic()
                if left <= 0:
                    return {"op": "idle"}
                self._cond.wait(min(left, 1.0))

    def _result(self, body: dict) -> None:
        self._seen()
        with self._cond:
            future = self._pending.get(str(body.get("id")))
        if future is not None and not future.done():
            future.set_result(body)

    def _file(self, file_id: str, offset: int, length: int) -> bytes | None:
        self._seen()
        with self._cond:
            path = self._files.get(file_id)
        if path is None:
            return None
        with open(path, "rb") as fh:
            fh.seek(max(offset, 0))
            return fh.read(max(length, 0))


class _Handler(BaseHTTPRequestHandler):
    bridge: Bridge

    def log_message(self, *_args) -> None:  # the token is in every request: never log them
        pass

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", f"{HEADER}, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _allowed(self) -> bool:
        if hmac.compare_digest(self.headers.get(HEADER, ""), self.bridge.token):
            return True
        self._json({"error": "forbidden"}, 403)
        return False

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server's naming
        self._send(204)

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed():
            return
        url = urlsplit(self.path)
        if url.path == "/next":
            self._json(self.bridge._next())
        elif url.path.startswith("/file/"):
            query = parse_qs(url.query)
            try:
                offset = int(query.get("offset", ["0"])[0])
                length = int(query.get("length", ["0"])[0])
            except ValueError:
                self._json({"error": "bad range"}, 400)
                return
            try:
                data = self.bridge._file(url.path.removeprefix("/file/"), offset, length)
            except OSError as exc:
                self._json({"error": str(exc)}, 500)
                return
            if data is None:
                self._json({"error": "not found"}, 404)
            else:
                self._send(200, data, "application/octet-stream")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed():
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        path = urlsplit(self.path).path
        if path == "/result" and isinstance(body, dict):
            self.bridge._result(body)
        elif path == "/alive":
            self.bridge._seen()
        elif path == "/log" and isinstance(body, dict):
            self.bridge._seen()
            log.info("Safari page: %s %s", body.get("event"), str(body.get("detail", ""))[:200])
        else:
            self._json({"error": "not found"}, 404)
            return
        self._json({"ok": True})


def translate(error: BridgeError) -> Exception:
    """The page's failure as the error ``runner`` acts on."""
    if error.kind == "login":
        return NotebookLMLoginRequired(T_SIGN_IN_SAFARI)
    if error.kind == "rate":
        return NotebookLMRateLimited(str(error))
    if error.kind == "permanent":
        return NotebookLMPermanent(str(error))
    return NotebookLMTransient(str(error))


class SafariGateway:
    """``Gateway``'s surface, carried out by the Safari page.

    Only the student starts a run (the card's button; never after a scheduled sync), so Safari
    comes to the front on the notebook page, where a banner shows each file going in.
    """

    def __init__(self, *, bridge: Bridge | None = None, opener: Callable[..., bool] = open_page,
                 state: Callable[[], str] = extension_state, hello_seconds: float = HELLO_SECONDS,
                 register_seconds: float = REGISTER_SECONDS, sleep=asyncio.sleep):
        self.bridge = bridge or Bridge()
        self._opener = opener
        self._state = state
        self._hello_seconds = hello_seconds
        self._register_seconds = register_seconds
        self._sleep = sleep
        self._open = False
        self._notebooks: list[RemoteNotebook] | None = None

    async def _call(self, op: str, args: dict | None = None, timeout: float = CALL_SECONDS) -> Any:
        try:
            return await self.bridge.call(op, args, timeout)
        except BridgeError as exc:
            raise translate(exc) from exc
        except BridgeLost as exc:
            raise NotebookLMLoginRequired(T_TAB_CLOSED) from exc
        except asyncio.TimeoutError as exc:
            raise NotebookLMTransient(f"Safari did not answer {op} in {int(timeout)} s") from exc

    async def open(self) -> "SafariGateway":
        """Open a Safari tab on the notebook page and wait for it to answer; listing proves the session."""
        if self._state() == DISABLED:
            raise NotebookLMLoginRequired(T_EXTENSION_OFF)
        self.bridge.start()
        self._open = True
        try:
            if not self._opener(self.bridge.address(), background=False):
                raise NotebookLMTransient(tr("Could not open Safari."))
            try:
                await self.bridge.call("hello", timeout=self._hello_seconds)
            except asyncio.TimeoutError as exc:
                raise NotebookLMLoginRequired(T_NO_ANSWER) from exc
            except BridgeError as exc:
                raise translate(exc) from exc
            await self.list_notebooks()
        except BaseException:
            await self.close()
            raise
        return self

    async def close(self) -> None:
        if self._open:
            self._open = False
            await asyncio.to_thread(self.bridge.stop, True)

    async def source_limit(self) -> int | None:
        try:
            value = await self._call("account_limits")
        except (NotebookLMTransient, NotebookLMPermanent):
            return None
        limit = value.get("source_limit") if isinstance(value, dict) else None
        return limit if isinstance(limit, int) and limit > 0 else None

    async def list_notebooks(self) -> list[RemoteNotebook]:
        if self._notebooks is None:
            raw = await self._call("list_notebooks")
            self._notebooks = [RemoteNotebook(str(item["id"]), store.nfc(str(item.get("title") or "")).strip())
                               for item in raw or [] if item.get("id")]
        return self._notebooks

    async def find_notebooks(self, title: str) -> list[RemoteNotebook]:
        wanted = store.nfc(title).strip()
        return [notebook for notebook in await self.list_notebooks() if notebook.title == wanted]

    async def create_notebook(self, title: str) -> RemoteNotebook:
        raw = await self._call("create_notebook", {"title": title})
        created = RemoteNotebook(str(raw["id"]), store.nfc(str(raw.get("title") or title)).strip())
        (await self.list_notebooks()).append(created)
        return created

    async def list_sources(self, notebook_id: str) -> list[RemoteSource]:
        raw = await self._call("list_sources", {"notebook_id": notebook_id})
        return [RemoteSource(str(item["id"]), store.nfc(str(item.get("title") or "")),
                             str(item.get("status") or "unknown"))
                for item in raw or [] if item.get("id")]

    async def add_file(self, notebook_id: str, path: Path, title: str) -> str:
        """Up under the file's own name, then renamed to ``title`` once NotebookLM lists it, as the library does."""
        path = Path(path)
        size = path.stat().st_size
        file_id = self.bridge.offer(path)
        try:
            source_id = await self._call("add_file", {
                "notebook_id": notebook_id, "file_id": file_id, "filename": path.name, "size": size,
                "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            }, timeout=UPLOAD_SECONDS)
        finally:
            self.bridge.withdraw(file_id)
        source_id = str(source_id)
        if title != path.name:
            await self._rename(notebook_id, source_id, title)
        return source_id

    async def _rename(self, notebook_id: str, source_id: str, title: str) -> None:
        """Best effort, like the library: the file is in, under its own name, whatever happens here."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._register_seconds
        try:
            while not any(source.id == source_id and source.status != "error"
                          for source in await self.list_sources(notebook_id)):
                if loop.time() >= deadline:
                    log.warning("source %s was not listed in time to be renamed", source_id)
                    return
                await self._sleep(1.0)
            await self._call("rename_source", {"notebook_id": notebook_id, "source_id": source_id, "title": title})
        except (NotebookLMTransient, NotebookLMPermanent) as exc:
            log.warning("source %s uploaded but not renamed: %s", source_id, exc)

    async def wait_ready(self, notebook_id: str, source_ids: list[str], timeout: float) -> dict[str, str]:
        return await remote.wait_ready(self.list_sources, notebook_id, source_ids, timeout, self._sleep)


def check_runtime() -> str:
    """For the packaged app's self-test: the Safari route and SafariServices load, without the library."""
    services = _safari_services()
    assert "SFSafariExtensionManager" in services and "SFSafariApplication" in services
    return f"notebooklm ok (Safari, {extension_id()})"


def mark_connected(config) -> None:
    """What says this app was set up with Safari: no cookie, no token, no account, only when."""
    write_private_json(store.safari_file(config), {"connected_at": store.utcnow_text()})


def connect(config, timeout: float = SIGN_IN_TIMEOUT, on_event: Callable[[dict], None] = lambda event: None,
            state: Callable[[], str] = extension_state, show_settings: Callable[[], bool] = open_extension_settings,
            opener: Callable[..., bool] = open_page, bridge: Bridge | None = None,
            clock: Callable[[], float] = time.monotonic, pause: Callable[[float], None] = time.sleep,
            attempt: float = 5.0) -> None:
    """Walk the student through Safari's two questions and prove the page works; raises ``NotebookLMSignInFailed``.

    1. The extension must be on: Safari's Settings open on it, and this waits until it is.
    2. Safari opens the notebook page in front. If the page stays silent, Safari has not let the
       extension run there yet: the student allows it from the extension's toolbar button.
    3. If Google has nobody signed in, the student signs in on that page; the page picks the
       bridge up again when it comes back.
    """
    from blackboard_sync.notebooklm.signin import NO_BROWSER, TIMED_OUT, VERIFY_FAILED

    deadline = clock() + timeout
    late = tr("Sign-in was not completed within {n} minutes.").format(n=int(timeout // 60))

    def step(name: str) -> None:
        on_event({"event": "sign_in", "step": name})

    if state() == DISABLED:
        step(STEP_EXTENSION)
        show_settings()
        while state() != ENABLED:
            if clock() >= deadline:
                raise NotebookLMSignInFailed(T_EXTENSION_OFF, TIMED_OUT)
            pause(1.0)
    bridge = bridge or Bridge()
    bridge.start()
    try:
        if not opener(bridge.address(), background=False):
            raise NotebookLMSignInFailed(tr("Could not open Safari."), NO_BROWSER)
        asyncio.run(_greet(bridge, deadline, clock, step, late, attempt))
        step(STEP_VERIFY)
        try:
            asyncio.run(bridge.call("list_notebooks", timeout=CALL_SECONDS))
        except (BridgeError, BridgeLost, asyncio.TimeoutError) as exc:
            raise NotebookLMSignInFailed(tr("Google took the sign-in, but Gemini Notebook did not open. Try again."),
                                         VERIFY_FAILED) from exc
    finally:
        bridge.stop(close_tab=True)  # the run that follows opens its own tab
    mark_connected(config)


async def _greet(bridge: Bridge, deadline: float, clock, step, late: str, attempt: float) -> None:
    """Ask the page to say hello until it does, ``attempt`` seconds at a time, hinting the student along."""
    from blackboard_sync.notebooklm.signin import TIMED_OUT, WINDOW_CLOSED

    started, hinted, signing_in = clock(), False, False
    while True:
        if clock() >= deadline:
            raise NotebookLMSignInFailed(late, TIMED_OUT)
        try:
            await bridge.call("hello", timeout=attempt)
            return
        except asyncio.TimeoutError:
            if not bridge.reached.is_set() and not hinted and clock() - started >= ALLOW_HINT_SECONDS:
                step(STEP_ALLOW)
                hinted = True
        except BridgeLost as exc:
            raise NotebookLMSignInFailed(tr("The browser window was closed before sign-in finished."),
                                         WINDOW_CLOSED) from exc
        except BridgeError as exc:
            if exc.kind != "login":
                log.warning("the page could not say hello: %s", exc)
            elif not signing_in:
                step(STEP_GOOGLE)
                signing_in = True
            await asyncio.sleep(min(3.0, attempt))
