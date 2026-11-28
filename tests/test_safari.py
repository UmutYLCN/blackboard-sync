"""Gemini Notebook in the Mac App Store build: the loopback bridge, SafariGateway and the Safari setup.

A thread stands in for the extension's page: it asks the real bridge for work over HTTP, as
``packaging/safari-extension/Resources/content.js`` does, and answers from a table of handlers.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blackboard_sync.config import Config
from blackboard_sync.errors import (
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMRateLimited,
    NotebookLMSignInFailed,
    NotebookLMTransient,
)
from blackboard_sync.menubar import main_window_model as main, settings_form
from blackboard_sync.menubar.model import AppModel, RunOutcome
from blackboard_sync.notebooklm import runner, safari, signin, store

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class Page(threading.Thread):
    """The extension's page: serves the bridge until it says bye, with ``handlers[op](args)``."""

    def __init__(self, bridge: safari.Bridge, handlers: dict, token: str | None = None):
        super().__init__(daemon=True)
        self.bridge, self.handlers = bridge, handlers
        self.token = token or bridge.token
        self.seen: list[str] = []
        self.goodbye: dict | None = None

    def request(self, path: str, body: dict | None = None) -> bytes:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.bridge.port}{path}", data=data,
                                     headers={safari.HEADER: self.token}, method="GET" if data is None else "POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read()

    def read_file(self, file_id: str, size: int, chunk: int = 3) -> bytes:
        return b"".join(self.request(f"/file/{file_id}?offset={offset}&length={min(chunk, size - offset)}")
                        for offset in range(0, size, chunk))

    def run(self) -> None:
        while True:
            try:
                work = json.loads(self.request("/next"))
            except (urllib.error.URLError, ConnectionError, OSError):
                return
            if work["op"] == "idle":
                continue
            if work["op"] == "bye":
                self.goodbye = work
                return
            self.seen.append(work["op"])
            try:
                reply = {"id": work["id"], "ok": True, "value": self.handlers[work["op"]](self, work["args"])}
            except safari.BridgeError as exc:
                reply = {"id": work["id"], "ok": False, "error": {"kind": exc.kind, "message": str(exc)}}
            self.request("/result", reply)


def started(handlers: dict, **kw) -> tuple[safari.Bridge, Page]:
    bridge = safari.Bridge(long_poll=0.3)
    bridge.start()
    page = Page(bridge, handlers, **kw)
    page.start()
    return bridge, page


def config(tmp_path: Path) -> Config:
    cfg = Config(base_url="https://bb.example.edu", dest=tmp_path / "Docs", data_dir=tmp_path / "data")
    cfg.ensure_data_dir()
    cfg.notebooklm_dir.mkdir(parents=True, exist_ok=True)
    return cfg


# -- the bridge ---------------------------------------------------------------------------


def test_bridge_carries_calls_and_serves_files_in_chunks_to_the_token_holder(tmp_path):
    upload = tmp_path / "week 1.pdf"
    upload.write_bytes(b"%PDF-1.4 lecture notes")
    handlers = {"hello": lambda page, args: {"origin": "https://notebook.google.com"},
                "read": lambda page, args: base64.b64encode(page.read_file(args["file_id"], args["size"])).decode()}
    bridge, page = started(handlers)

    async def go():
        assert await bridge.call("hello", timeout=5) == {"origin": "https://notebook.google.com"}
        file_id = bridge.offer(upload)
        data = await bridge.call("read", {"file_id": file_id, "size": upload.stat().st_size}, timeout=5)
        bridge.withdraw(file_id)
        return base64.b64decode(data), file_id

    data, file_id = asyncio.run(go())
    assert data == upload.read_bytes()
    with pytest.raises(urllib.error.HTTPError) as gone:  # withdrawn: the page can no longer read it
        page.request(f"/file/{file_id}?offset=0&length=4")
    assert gone.value.code == 404
    stranger = Page(bridge, {}, token="not-the-token-" + "x" * 16)
    with pytest.raises(urllib.error.HTTPError) as refused:
        stranger.request("/next")
    assert refused.value.code == 403
    assert bridge.address().startswith(store.APP_URL + f"#bbsync={bridge.port}.")
    bridge.stop(close_tab=True)
    page.join(5)
    assert page.goodbye == {"op": "bye", "args": {"close": True}}


def test_bridge_reports_the_pages_failure_and_a_page_that_went_quiet():
    def refuse(page, args):
        raise safari.BridgeError("rate", "slow down")

    bridge, page = started({"refuse": refuse})
    with pytest.raises(safari.BridgeError) as failed:
        asyncio.run(bridge.call("refuse", timeout=5))
    assert failed.value.kind == "rate"
    bridge.stop()
    page.join(5)

    quiet = safari.Bridge(long_poll=0.3)
    quiet.start()
    with pytest.raises(asyncio.TimeoutError):  # no page at all: the call times out
        asyncio.run(quiet.call("hello", timeout=0.5))
    quiet.reached.set()
    quiet.last_seen -= safari.LOST_SECONDS + 1  # the page asked for work once, then went silent
    with pytest.raises(safari.BridgeLost):
        asyncio.run(quiet.call("hello", timeout=5))
    quiet.stop(linger=0)


@pytest.mark.parametrize("kind, error", [("login", NotebookLMLoginRequired), ("rate", NotebookLMRateLimited),
                                         ("permanent", NotebookLMPermanent), ("transient", NotebookLMTransient),
                                         ("odd", NotebookLMTransient)])
def test_page_failures_become_the_errors_runner_acts_on(kind, error):
    translated = safari.translate(safari.BridgeError(kind, "why"))
    assert type(translated) is error
    if kind == "login":
        assert str(translated) == safari.T_SIGN_IN_SAFARI


# -- SafariGateway -----------------------------------------------------------------------


def notebook_page(sources: list[dict]):
    """Handlers that act like Gemini Notebook: one notebook, files listed as they are added."""
    def add_file(page, args):
        assert page.read_file(args["file_id"], args["size"]) == b"slides"
        sources.append({"id": "s-new", "title": args["filename"], "status": "processing"})
        return "s-new"

    def rename(page, args):
        next(s for s in sources if s["id"] == args["source_id"])["title"] = args["title"]
        return True

    return {"hello": lambda page, args: {"origin": "https://notebook.google.com"},
            "list_notebooks": lambda page, args: [{"id": "n1", "title": "BIO 101 (Fall 2026)"}],
            "create_notebook": lambda page, args: {"id": "n2", "title": args["title"]},
            "list_sources": lambda page, args: [dict(s) for s in sources],
            "account_limits": lambda page, args: {"source_limit": 300},
            "add_file": add_file, "rename_source": rename}


def test_safari_gateway_opens_safari_in_front_and_speaks_the_gateway_surface(tmp_path):
    sources: list[dict] = []
    handlers = notebook_page(sources)
    opened = []
    pages: list[Page] = []

    def opener(url, background):
        opened.append((url, background))
        bridge = gateway.bridge
        pages.append(Page(bridge, handlers))
        pages[0].start()
        return True

    async def no_wait(_seconds):
        return None

    gateway = safari.SafariGateway(bridge=safari.Bridge(long_poll=0.3), opener=opener, state=lambda: safari.ENABLED,
                                   sleep=no_wait)
    upload = tmp_path / "slides.pdf"
    upload.write_bytes(b"slides")

    async def go():
        await gateway.open()
        try:
            assert await gateway.source_limit() == 300
            assert await gateway.find_notebooks("BIO 101 (Fall 2026)") == [safari.RemoteNotebook("n1", "BIO 101 (Fall 2026)")]
            created = await gateway.create_notebook("CHEM 110 (Fall 2026)")
            assert created in await gateway.list_notebooks()
            source_id = await gateway.add_file("n1", upload, title="Week 1/slides.pdf")
            sources[0]["status"] = "ready"
            return source_id, await gateway.wait_ready("n1", [source_id, "gone"], timeout=0)
        finally:
            await gateway.close()

    source_id, ready = asyncio.run(go())
    assert opened and opened[0][1] is False  # only the student starts a run: Safari comes to the front
    assert source_id == "s-new" and sources[0]["title"] == "Week 1/slides.pdf"  # renamed, like the library does
    assert ready == {"s-new": "ready", "gone": "missing"}
    pages[0].join(5)
    assert pages[0].goodbye == {"op": "bye", "args": {"close": True}}


def test_safari_gateway_says_what_is_missing_before_a_run(tmp_path):
    with pytest.raises(NotebookLMLoginRequired) as off:
        asyncio.run(safari.SafariGateway(state=lambda: safari.DISABLED, opener=lambda *a, **k: True).open())
    assert str(off.value) == safari.T_EXTENSION_OFF

    silent = safari.SafariGateway(bridge=safari.Bridge(long_poll=0.3), opener=lambda *a, **k: True,
                                  state=lambda: safari.ENABLED, hello_seconds=0.5)
    with pytest.raises(NotebookLMLoginRequired) as no_answer:  # Safari has not let the extension run there
        asyncio.run(silent.open())
    assert str(no_answer.value) == safari.T_NO_ANSWER

    def signed_out(page, args):
        raise safari.BridgeError("login", "not signed in to Google in this browser")

    gateway = safari.SafariGateway(bridge=safari.Bridge(long_poll=0.3), state=lambda: safari.UNKNOWN,
                                   opener=lambda url, background: Page(gateway.bridge, {"hello": signed_out}).start() or True)
    with pytest.raises(NotebookLMLoginRequired) as login:
        asyncio.run(gateway.open())
    assert str(login.value) == safari.T_SIGN_IN_SAFARI


# -- the Safari setup ---------------------------------------------------------------------


def test_connect_walks_through_the_extension_the_site_and_google_then_marks_the_app_connected(tmp_path):
    cfg = config(tmp_path)
    states = iter([safari.DISABLED, safari.DISABLED, safari.ENABLED])
    shown, events = [], []
    attempts = {"hello": 0}

    def hello(page, args):
        attempts["hello"] += 1
        if attempts["hello"] == 1:
            raise safari.BridgeError("login", "not signed in")
        return {"origin": "https://notebook.google.com"}

    bridge = safari.Bridge(long_poll=0.3)

    def opener(url, background):
        assert url == bridge.address() and background is False
        Page(bridge, {"hello": hello, "list_notebooks": lambda page, args: []}).start()
        return True

    safari.connect(cfg, timeout=60, on_event=events.append, state=lambda: next(states),
                   show_settings=lambda: shown.append(True) or True, opener=opener, bridge=bridge,
                   pause=lambda _s: None, attempt=0.2)
    assert shown == [True]
    assert [e["step"] for e in events] == [safari.STEP_EXTENSION, safari.STEP_GOOGLE, safari.STEP_VERIFY]
    marker = json.loads(store.safari_file(cfg).read_text(encoding="utf-8"))
    assert set(marker) == {"connected_at"}  # no cookie, token or account
    assert store.status(cfg).connected
    assert not store.session_file(cfg).exists()
    store.disconnect(cfg)
    assert not store.safari_file(cfg).exists() and not store.status(cfg).connected


def test_connect_hints_to_allow_the_site_and_gives_up_in_time(tmp_path):
    cfg = config(tmp_path)
    clock = {"now": 0.0}

    def tick():
        clock["now"] += 3.0
        return clock["now"]

    events = []
    with pytest.raises(NotebookLMSignInFailed) as late:
        safari.connect(cfg, timeout=60, on_event=events.append, state=lambda: safari.ENABLED,
                       opener=lambda *a, **k: True, bridge=safari.Bridge(long_poll=0.3), clock=tick, attempt=0.05)
    assert late.value.outcome == signin.TIMED_OUT
    assert [e["step"] for e in events] == [safari.STEP_ALLOW]  # the page never spoke: Safari has not let it
    assert not store.safari_file(cfg).exists()

    with pytest.raises(NotebookLMSignInFailed) as stuck:
        safari.connect(cfg, timeout=2, state=lambda: safari.DISABLED, show_settings=lambda: True,
                       opener=lambda *a, **k: pytest.fail("no page before the extension is on"),
                       clock=tick, pause=lambda _s: None)
    assert str(stuck.value) == safari.T_EXTENSION_OFF

    with pytest.raises(NotebookLMSignInFailed) as no_safari:
        safari.connect(cfg, timeout=60, state=lambda: safari.ENABLED, opener=lambda *a, **k: False,
                       bridge=safari.Bridge(long_poll=0.3))
    assert no_safari.value.outcome == signin.NO_BROWSER


def test_open_page_always_names_safari():
    calls = []

    class Done:
        returncode = 0

    assert safari.open_page("https://notebook.google.com/", background=True, run=lambda cmd, **kw: calls.append(cmd) or Done())
    assert calls == [["open", "-g", "-b", safari.SAFARI, "https://notebook.google.com/"]]
    assert safari.extension_id() == safari.DEFAULT_BUNDLE_ID + safari.EXTENSION_SUFFIX


# -- the Mac App Store build around it -----------------------------------------------------


def test_mas_runs_through_safari_and_only_when_the_student_asks(tmp_path, monkeypatch):
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    cfg = config(tmp_path)

    class Opened(Exception):
        pass

    async def fake_open(self):
        raise Opened

    monkeypatch.setattr(safari.SafariGateway, "open", fake_open)
    with pytest.raises(Opened):  # the library is never loaded in this build
        asyncio.run(runner.open_gateway(cfg))

    safari.mark_connected(cfg)
    model = AppModel(dest=tmp_path / "Docs", now=NOW, configured=True)
    model.notebooklm = store.status(cfg)
    assert model.notebooklm.connected
    assert not model.wants_notebooklm(RunOutcome("ok", 0, ""), True)  # never after a (scheduled) sync

    rows = [r.key for s in settings_form.settings_sections(notebooklm=True, mas=True) for r in s.rows]
    assert "notebooklm_safari" in rows and "notebooklm_auto" not in rows

    card = main.notebooklm_card(AppModel(dest=tmp_path / "Docs", now=NOW, configured=True), NOW)
    assert (card.detail, card.secondary) == (main.T_NOTEBOOKLM_SAFARI_INTRO, main.T_NOTEBOOKLM_SAFARI_SIGN_IN)
    step = main.notebooklm_progress({"event": "sign_in", "step": safari.STEP_ALLOW})
    assert (step.text, step.hint) == main.T_NOTEBOOKLM_SAFARI_STEPS[safari.STEP_ALLOW]
    assert set(main.T_NOTEBOOKLM_SAFARI_STEPS) == {safari.STEP_EXTENSION, safari.STEP_ALLOW, safari.STEP_GOOGLE}


def test_extension_package_matches_the_app_side():
    resources = ROOT / "packaging" / "safari-extension" / "Resources"
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    hosts = {"https://notebook.google.com/*", "https://notebooklm.google.com/*"}
    assert set(manifest["content_scripts"][0]["matches"]) == hosts
    assert set(manifest["host_permissions"]) == hosts | {"http://127.0.0.1/*"}
    assert manifest["permissions"] == ["storage"]  # no cookies, no tabs, no history
    content = (resources / "content.js").read_text(encoding="utf-8")
    for op in ("hello", "account_limits", "list_notebooks", "create_notebook", "list_sources", "add_file",
               "rename_source"):
        assert f'case "{op}"' in content
    assert safari.HEADER in (resources / "background.js").read_text(encoding="utf-8")
    keys = set(json.loads((resources / "_locales" / "en" / "messages.json").read_text(encoding="utf-8")))
    for lang in ("tr", "es", "fr", "de", "ar"):
        assert set(json.loads((resources / "_locales" / lang / "messages.json").read_text(encoding="utf-8"))) == keys
    build = (ROOT / "scripts" / "build-safari-extension.sh").read_text(encoding="utf-8")
    assert f"$APP_ID{safari.EXTENSION_SUFFIX}" in build
    assert "build-safari-extension.sh" in (ROOT / "scripts" / "build-mas.sh").read_text(encoding="utf-8")
    assert "mas-safari-extension.plist" in (ROOT / "scripts" / "sign-mas.sh").read_text(encoding="utf-8")
