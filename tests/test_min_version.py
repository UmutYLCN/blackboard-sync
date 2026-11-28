"""Online minimum-version check, direct .dmg retirement, sync gating, Store/macOS installers and UI states."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from blackboard_sync import i18n, licensing, min_version, updater
from blackboard_sync.config import Config
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar.model import (
    FIRST_SYNC_DELAY,
    REQUIRED_UPDATE_ACTION,
    UPDATE_INTERVAL,
    UPDATE_RETRY_DELAY,
    AppModel,
    Icon,
    RecentItem,
    RunOutcome,
)
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.min_version import (
    MAC_APP_STORE_URL,
    MIN_VERSION_URL,
    MS_STORE_URI,
    STATUS_DMG_RETIRED,
    STORE_UPDATE_CANCELED,
    STORE_UPDATE_COMPLETED,
    STORE_UPDATE_OTHER_ERROR,
    MinVersionChecker,
    MinVersionResult,
    StoreUpdateAction,
    StoreUpdateResult,
    WindowsStoreUpdater,
)
from blackboard_sync.settings import Settings
from blackboard_sync.windows import webui_page, webui_state

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
DEST = Path("/Users/student/Documents")
ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MAS_URL = "https://apps.apple.com/app/blackboard-sync/id6740000000"


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: str = "", url: str = MIN_VERSION_URL):
        self.status_code = status_code
        self._body = body
        self.url = url
        self.closed = False

    def json(self):
        return json.loads(self._body)

    def close(self) -> None:
        self.closed = True


class _FakeOp:
    """WinRT ``IAsyncOperation`` / ``IAsyncOperationWithProgress`` stand-in."""

    def __init__(self, value=None, error: Exception | None = None):
        self._value = value
        self._error = error
        self._completed = None

    def get(self):
        if self._error is not None:
            raise self._error
        return self._value

    def get_results(self):
        return self.get()

    @property
    def completed(self):
        return self._completed

    @completed.setter
    def completed(self, handler):
        self._completed = handler
        if handler is not None:
            handler(self, 1)


class _FakeStoreUpdateContext:
    def __init__(self, updates=(), install_result=None, updates_error=None, install_error=None):
        self.updates = updates
        self.install_result = install_result
        self.updates_error = updates_error
        self.install_error = install_error
        self.install_calls: list[object] = []

    def get_app_and_optional_store_package_updates_async(self):
        return _FakeOp(self.updates, self.updates_error)

    def request_download_and_install_store_package_updates_async(self, package_updates):
        self.install_calls.append(package_updates)
        return _FakeOp(self.install_result, self.install_error)


def signed_in_model(min_state: MinVersionResult | None = None) -> AppModel:
    session = {"saved_at": NOW.timestamp(), "user": {"displayName": "Umut Yalcin"}}
    return AppModel(
        DEST,
        NOW,
        configured=True,
        session=session,
        last=RunOutcome("ok", finished_at=NOW - timedelta(minutes=20)),
        recent=[RecentItem("2026-2027 Fall/CSE303/week1.pdf", "CSE303", NOW.isoformat())],
        min_version_state=min_state,
    )


# -- site/min-version.json & min_version fetcher/parser/cache --------------------------


def test_site_min_version_file_parses_cleanly_for_every_distribution():
    payload = json.loads((ROOT / "site" / "min-version.json").read_text(encoding="utf-8"))
    assert payload["dmg_retired"] is False
    assert payload["mas_url"] == "https://apps.apple.com/app/id<TBD>"
    assert min_version.parse_min_version(payload, "1.7.1", platform="darwin", env={}).required
    assert not min_version.parse_min_version(payload, "1.7.2", platform="darwin", env={}).required
    assert min_version.parse_min_version(payload, "1.7.1", platform="win32", packaged=True).required
    assert not min_version.parse_min_version(payload, "1.7.2", platform="win32", packaged=True).required
    # Missing "mas" key in site/min-version.json means no enforcement for Mac App Store builds yet.
    mas = min_version.parse_min_version(payload, "1.0.0", platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"})
    assert mas == MinVersionResult("ok") and not mas.required


@pytest.mark.parametrize("current, expected_status", [
    ("1.7.1", "required"),
    ("1.6.9", "required"),
    ("1.7.2", "ok"),
    ("1.7.3", "ok"),
    ("2.0.0", "ok"),
])
def test_check_compares_versions_per_platform_and_distribution(current, expected_status):
    payload = json.dumps({"schema": 1, "minimum": {"macos": "1.7.2", "windows": "1.8.0", "mas": "1.9.0"}})
    seen_calls: list[tuple[str, object]] = []

    def fake_get(url, **kwargs):
        seen_calls.append((url, kwargs.get("timeout")))
        return _FakeResponse(200, payload)

    mac = min_version.check(current, platform="darwin", env={}, get=fake_get)
    assert mac == MinVersionResult(expected_status, minimum="1.7.2")
    assert seen_calls == [(MIN_VERSION_URL, min_version.CHECK_TIMEOUT)]

    win_below = min_version.check("1.7.9", platform="win32", packaged=True, get=fake_get)
    assert win_below == MinVersionResult("required", minimum="1.8.0")
    win_equal = min_version.check("1.8.0", platform="win32", packaged=True, get=fake_get)
    assert win_equal == MinVersionResult("ok", minimum="1.8.0")

    mas_below = min_version.check("1.8.5", platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"}, get=fake_get)
    assert mas_below == MinVersionResult("required", minimum="1.9.0")


@pytest.mark.parametrize("bad_case", [
    "timeout",
    "http_503",
    "http_404",
    "http_redirect",
    "invalid_json",
    "schema_2",
    "schema_bool",
    "missing_minimum",
    "missing_key",
    "bad_version",
    "linux_platform",
])
def test_offline_invalid_unknown_schema_or_missing_key_never_enforces(bad_case):
    def fake_get(url, **kwargs):
        if bad_case == "timeout":
            raise requests.Timeout("timed out")
        if bad_case == "http_503":
            return _FakeResponse(503, "")
        if bad_case == "http_404":
            return _FakeResponse(404, "{}")
        if bad_case == "http_redirect":
            return _FakeResponse(200, '{"schema": 1, "minimum": {"macos": "9.9.9"}}', url="http://evil.example/min.json")
        if bad_case == "invalid_json":
            return _FakeResponse(200, "{not valid json")
        if bad_case == "schema_2":
            return _FakeResponse(200, json.dumps({"schema": 2, "minimum": {"macos": "9.9.9"}}))
        if bad_case == "schema_bool":
            return _FakeResponse(200, json.dumps({"schema": True, "minimum": {"macos": "9.9.9"}}))
        if bad_case == "missing_minimum":
            return _FakeResponse(200, json.dumps({"schema": 1}))
        if bad_case == "missing_key":
            return _FakeResponse(200, json.dumps({"schema": 1, "minimum": {"windows": "9.9.9"}}))
        if bad_case == "bad_version":
            return _FakeResponse(200, json.dumps({"schema": 1, "minimum": {"macos": "latest"}}))
        return _FakeResponse(200, json.dumps({"schema": 1, "minimum": {"macos": "9.9.9", "windows": "9.9.9"}}))

    platform = "linux" if bad_case == "linux_platform" else "darwin"
    result = min_version.check("1.0.0", platform=platform, env={}, get=fake_get)
    assert not result.required


def test_dmg_retired_applies_only_to_macos_direct_and_never_to_windows_mas_or_invalid(tmp_path, monkeypatch):
    retired_payload = json.dumps({
        "schema": 1,
        "minimum": {"macos": "1.7.2", "windows": "1.7.2", "mas": "1.7.2"},
        "dmg_retired": True,
        "mas_url": SAMPLE_MAS_URL,
    })
    fake_get = lambda url, **kw: _FakeResponse(200, retired_payload)

    # macOS direct (.dmg) is retired even when __version__ is at or above minimum.
    mac_direct = min_version.check("2.0.0", platform="darwin", env={}, get=fake_get)
    assert mac_direct == MinVersionResult(STATUS_DMG_RETIRED, mas_url=SAMPLE_MAS_URL)
    assert mac_direct.required and mac_direct.dmg_retired

    mac_explicit_direct = min_version.check(
        "1.7.1", platform="darwin", env={"BBSYNC_DISTRIBUTION": "direct"}, get=fake_get
    )
    assert mac_explicit_direct == MinVersionResult(STATUS_DMG_RETIRED, mas_url=SAMPLE_MAS_URL)

    # Mac App Store builds ignore dmg_retired completely (only governed by minimum["mas"]),
    # whether selected via BBSYNC_DISTRIBUTION=mas, APP_SANDBOX_CONTAINER_ID, or bundled mas-distribution marker.
    mas_ok = min_version.check("1.7.2", platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"}, get=fake_get)
    assert mas_ok == MinVersionResult("ok", minimum="1.7.2") and not mas_ok.required and not mas_ok.dmg_retired
    mas_old = min_version.check("1.7.1", platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"}, get=fake_get)
    assert mas_old == MinVersionResult("required", minimum="1.7.2") and not mas_old.dmg_retired
    mas_sandbox = min_version.check(
        "2.0.0",
        platform="darwin",
        env={"APP_SANDBOX_CONTAINER_ID": licensing.MAS_BUNDLE_ID, "BBSYNC_DISTRIBUTION": "direct"},
        get=fake_get,
    )
    assert mas_sandbox == MinVersionResult("ok", minimum="1.7.2") and not mas_sandbox.required and not mas_sandbox.dmg_retired

    marker = tmp_path / licensing.MAS_MARKER_REL
    marker.parent.mkdir(parents=True)
    marker.write_text("mas\n", encoding="utf-8")
    monkeypatch.setattr(licensing.sys, "frozen", True, raising=False)
    monkeypatch.setattr(licensing.sys, "_MEIPASS", str(tmp_path), raising=False)
    mas_frozen = min_version.check("2.0.0", platform="darwin", env={"BBSYNC_DISTRIBUTION": "direct"}, get=fake_get)
    assert mas_frozen == MinVersionResult("ok", minimum="1.7.2") and not mas_frozen.required and not mas_frozen.dmg_retired
    monkeypatch.setattr(licensing.sys, "frozen", False, raising=False)
    monkeypatch.delattr(licensing.sys, "_MEIPASS", raising=False)

    # Windows (MSIX Store and unpackaged runs) ignores dmg_retired completely.
    win_store = min_version.check(
        "1.7.2", platform="win32", env={"BBSYNC_DISTRIBUTION": "direct"}, packaged=True, get=fake_get
    )
    assert win_store == MinVersionResult("ok", minimum="1.7.2") and not win_store.required and not win_store.dmg_retired
    win_direct = min_version.check(
        "1.7.2", platform="win32", env={"BBSYNC_DISTRIBUTION": "direct"}, packaged=False, get=fake_get
    )
    assert win_direct == MinVersionResult("ok", minimum="1.7.2") and not win_direct.required and not win_direct.dmg_retired
    win_msstore_env = min_version.check(
        "1.7.1", platform="win32", env={"BBSYNC_DISTRIBUTION": "msstore"}, packaged=False, get=fake_get
    )
    assert win_msstore_env == MinVersionResult("required", minimum="1.7.2") and not win_msstore_env.dmg_retired

    # Missing, false, or invalid dmg_retired / mas_url values never retire the .dmg build.
    for non_blocking in (
        {"schema": 1, "minimum": {"macos": "1.7.2"}},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": False, "mas_url": SAMPLE_MAS_URL},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": "true", "mas_url": SAMPLE_MAS_URL},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": 1, "mas_url": SAMPLE_MAS_URL},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": True},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": True, "mas_url": ""},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": True, "mas_url": 123},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": True, "mas_url": "http://insecure.example/app"},
        {"schema": 1, "minimum": {"macos": "1.7.2"}, "dmg_retired": True, "mas_url": "https://apps.apple.com/bad url"},
    ):
        res = min_version.parse_min_version(non_blocking, "1.7.2", platform="darwin", env={})
        assert not res.required and not res.dmg_retired


def test_dmg_retired_ui_state_blocks_sync_and_renders_across_all_six_locales():
    model = signed_in_model()
    became_blocked, unlocked = model.apply_min_version(
        MinVersionResult(STATUS_DMG_RETIRED, mas_url=SAMPLE_MAS_URL), NOW
    )
    assert became_blocked and not unlocked
    model.pending = "sync"
    assert not model.due(NOW + timedelta(days=1))
    assert model.pending_job(NOW) is None
    assert not model.session_check_due(NOW + timedelta(days=1))
    assert model.icon() == Icon.PAUSED

    menu = model.menu(NOW)
    assert not menu.sync_enabled
    assert "Blackboard Sync moved to the Mac App Store" in menu.status_lines
    assert any(
        entry.action == REQUIRED_UPDATE_ACTION and entry.title == "Open Mac App Store" and entry.enabled
        for entry in menu.entries
    )

    status = main.main_status(model, NOW)
    assert not status.sync_enabled and not status.pause_enabled
    assert status.update_banner is None and status.license is None
    assert len(status.recent) == 1 and status.recent[0].name == "week1.pdf"
    req = status.update_required
    assert req is not None
    assert req.title == "Blackboard Sync moved to the Mac App Store"
    assert "Mac App Store" in req.detail
    assert req.button_title == "Open Mac App Store"
    assert req.action == REQUIRED_UPDATE_ACTION and req.enabled

    expected_titles = {
        "en": "Blackboard Sync moved to the Mac App Store",
        "tr": "Blackboard Sync Mac App Store'a taşındı",
        "es": "Blackboard Sync se trasladó al Mac App Store",
        "fr": "Blackboard Sync est passé sur le Mac App Store",
        "de": "Blackboard Sync ist in den Mac App Store umgezogen",
        "ar": "انتقل Blackboard Sync إلى Mac App Store",
    }
    try:
        for code, expected_title in expected_titles.items():
            i18n.set_language(code)
            loc_req = main.update_required_state(model)
            assert loc_req is not None
            assert loc_req.title == expected_title
            assert loc_req.detail
            assert loc_req.button_title
    finally:
        i18n.set_language("en")


def test_checker_caches_last_good_answer_briefly_and_clears_after_ttl():
    clock = [100.0]
    calls = 0
    should_fail = False
    payload = json.dumps({"schema": 1, "minimum": {"macos": "1.7.2"}})

    def fake_get(url, **kwargs):
        nonlocal calls
        calls += 1
        if should_fail:
            raise requests.ConnectionError("offline")
        return _FakeResponse(200, payload)

    checker = MinVersionChecker(
        get=fake_get,
        ttl_seconds=300.0,
        clock=lambda: clock[0],
        current="1.7.1",
        platform="darwin",
        env={},
    )
    first = checker.check()
    assert first == MinVersionResult("required", minimum="1.7.2") and calls == 1

    # Within TTL, check() reuses the cached good answer without hitting the network.
    clock[0] += 120.0
    second = checker.check()
    assert second == first and calls == 1

    # Forced check during a momentary network blip within TTL keeps the brief cache.
    should_fail = True
    forced = checker.check(force=True)
    assert forced == first and calls == 2

    # Once TTL expires and the server is unreachable, enforcement drops (never lock out).
    clock[0] += 400.0
    expired = checker.check()
    assert expired == MinVersionResult("unknown") and not expired.required and calls == 3


# -- Sync gating, downloaded files untouched & UI model --------------------------------


def test_below_minimum_blocks_sync_preserves_files_and_shows_update_required_screen():
    model = signed_in_model()
    became_blocked, unlocked = model.apply_min_version(MinVersionResult("required", minimum="1.7.2"), NOW)
    assert became_blocked and not unlocked
    model.pending = "sync"

    # All sync entry points on AppModel are gated, matching license expiry.
    assert not model.due(NOW + timedelta(days=1))
    assert model.pending_job(NOW) is None
    assert not model.session_check_due(NOW + timedelta(days=1))
    assert model.icon() == Icon.PAUSED
    assert not model.min_version_due(NOW + timedelta(hours=1))
    assert model.min_version_due(NOW + UPDATE_INTERVAL)

    menu = model.menu(NOW)
    assert not menu.sync_enabled
    assert "Update required" in menu.status_lines
    assert any(entry.action == REQUIRED_UPDATE_ACTION and entry.enabled for entry in menu.entries)
    # Downloaded files and Open folder remain untouched and accessible.
    assert len(menu.recent) == 1 and "week1.pdf" in menu.recent[0][0]
    assert any(entry.action == "folder" and entry.enabled for entry in menu.entries)

    status = main.main_status(model, NOW)
    assert not status.sync_enabled and not status.pause_enabled
    assert status.update_banner is None and status.license is None
    assert status.home_heading == "Home" and status.home_subtitle == ""
    assert len(status.recent) == 1 and status.recent[0].name == "week1.pdf"
    req = status.update_required
    assert req is not None
    assert req.title == "Update required"
    assert "1.7.2" in req.detail
    assert req.button_title == "Update" and req.action == REQUIRED_UPDATE_ACTION and req.enabled

    # Equal / above minimum unlocks syncing again.
    became_blocked, unlocked = model.apply_min_version(MinVersionResult("ok", minimum="1.7.2"), NOW)
    assert not became_blocked and unlocked
    assert model.due(NOW)
    normal_status = main.main_status(model, NOW)
    assert normal_status.update_required is None and normal_status.sync_enabled


def test_offline_unknown_min_version_never_blocks_and_retries_after_hour():
    model = signed_in_model()
    model.apply_min_version(MinVersionResult("unknown"), NOW)
    assert not model.update_required
    assert model.due(NOW + FIRST_SYNC_DELAY)
    assert model.menu(NOW).sync_enabled
    assert main.main_status(model, NOW).update_required is None
    assert not model.min_version_due(NOW + timedelta(minutes=10))
    assert model.min_version_due(NOW + UPDATE_RETRY_DELAY)


# -- Windows Store WinRT updater & TrayApp gating --------------------------------------


def test_windows_store_updater_installs_with_hwnd_and_falls_back_to_store_uri():
    initialized: list[tuple[object, int]] = []
    opened: list[str] = []
    ui_calls: list[str] = []

    def on_ui(fn):
        ui_calls.append("ui")
        fn()

    # 1. Store reports a package update and completes installation with HWND on UI thread.
    pkg = SimpleNamespace(package=SimpleNamespace(id="BlackboardSync_1.7.2"))
    ctx = _FakeStoreUpdateContext(
        updates=[pkg],
        install_result=SimpleNamespace(overall_state=STORE_UPDATE_COMPLETED),
    )
    store_up = WindowsStoreUpdater(
        context_factory=lambda: ctx,
        initialize_window=lambda obj, hwnd: initialized.append((obj, hwnd)),
        opener=opened.append,
    )
    res = store_up.install_update(hwnd=0xCAFE, on_ui_thread=on_ui)
    assert res == StoreUpdateResult(StoreUpdateAction.INSTALLED)
    assert ui_calls == ["ui"]
    assert initialized == [(ctx, 0xCAFE)]
    assert len(ctx.install_calls) == 1
    assert opened == []

    # 2. User cancels the Store modal -> CANCELLED without opening the Store page.
    cancel_ctx = _FakeStoreUpdateContext(
        updates=[pkg],
        install_result=SimpleNamespace(overall_state=STORE_UPDATE_CANCELED),
    )
    cancel_up = WindowsStoreUpdater(
        context_factory=lambda: cancel_ctx,
        initialize_window=lambda obj, hwnd: None,
        opener=opened.append,
    )
    assert cancel_up.install_update(hwnd=0xCAFE, on_ui_thread=on_ui) == StoreUpdateResult(StoreUpdateAction.CANCELLED)
    assert opened == []

    # 3. Empty Store update list -> falls back to ms-windows-store://pdp/?ProductId=9NXJCQ5JL1KB.
    empty_up = WindowsStoreUpdater(
        context_factory=lambda: _FakeStoreUpdateContext(updates=[]),
        opener=opened.append,
    )
    assert empty_up.install_update(hwnd=0xCAFE, on_ui_thread=on_ui) == StoreUpdateResult(StoreUpdateAction.OPENED_STORE)
    assert opened == [MS_STORE_URI]

    # 4. Store install error or WinRT exception -> falls back to ms-windows-store://pdp/?ProductId=9NXJCQ5JL1KB.
    opened.clear()
    err_up = WindowsStoreUpdater(
        context_factory=lambda: _FakeStoreUpdateContext(
            updates=[pkg], install_result=SimpleNamespace(overall_state=STORE_UPDATE_OTHER_ERROR)
        ),
        initialize_window=lambda obj, hwnd: None,
        opener=opened.append,
    )
    assert err_up.install_update(hwnd=0xCAFE, on_ui_thread=on_ui) == StoreUpdateResult(StoreUpdateAction.OPENED_STORE)
    assert opened == [MS_STORE_URI]

    opened.clear()
    exc_up = WindowsStoreUpdater(
        context_factory=lambda: _FakeStoreUpdateContext(updates_error=OSError("Store unavailable")),
        opener=opened.append,
    )
    assert exc_up.install_update(hwnd=0xCAFE, on_ui_thread=on_ui) == StoreUpdateResult(StoreUpdateAction.OPENED_STORE)
    assert opened == [MS_STORE_URI]

    # 5. Unpackaged Windows run -> falls back directly to the Store page.
    opened.clear()
    unpackaged_up = WindowsStoreUpdater(is_packaged=lambda: False, opener=opened.append)
    assert unpackaged_up.install_update() == StoreUpdateResult(StoreUpdateAction.OPENED_STORE)
    assert opened == [MS_STORE_URI]


def test_tray_app_enforces_min_version_stops_running_sync_and_runs_store_update(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import TrayApp

    downloaded = tmp_path / "Docs" / "University" / "2026-2027 Fall" / "CSE303" / "week1.pdf"
    downloaded.parent.mkdir(parents=True)
    downloaded.write_bytes(b"existing pdf")

    results = [MinVersionResult("required", minimum="1.7.2")]
    opened: list[str] = []
    app = TrayApp.__new__(TrayApp)
    app.config = Config(data_dir=tmp_path, dest=tmp_path / "Docs")
    app.settings = Settings("https://bb.example.edu", tmp_path / "Docs")
    app.login_after_job = False
    app.uninstalling = False
    app.closed = False
    app.model = signed_in_model()
    app.license_provider = licensing.AlwaysFullProvider()
    app.min_version_checker = SimpleNamespace(check=lambda force=False: results[0])
    app.store_updater = WindowsStoreUpdater(
        context_factory=lambda: _FakeStoreUpdateContext(updates=[]),
        opener=opened.append,
    )
    app.save = lambda: None
    app.refresh = lambda: None
    app.window = None
    app.root = None
    app.web = SimpleNamespace(window_handle=lambda: 0x1234, invoke_ui=lambda fn: fn())

    threads: list[object] = []
    monkeypatch.setattr(
        "blackboard_sync.windows.app.threading.Thread",
        lambda target, daemon=True, **kw: SimpleNamespace(start=lambda: threads.append(target)),
    )
    app.post = lambda callback, *args: callback(*args)
    monkeypatch.setattr("blackboard_sync.windows.app.jobs.utcnow", lambda: NOW)
    monkeypatch.setattr("blackboard_sync.windows.app.jobs.refresh_session", lambda *a: None)

    stopped: list[bool] = []
    monkeypatch.setattr("blackboard_sync.windows.app.jobs.stop_sync", lambda: stopped.append(True) or True)
    app.model.busy = "sync"

    # Startup min-version check discovers version is below minimum and stops in-flight sync.
    app.start_min_version_check()
    threads.pop(0)()
    assert app.model.update_required
    assert stopped == [True]
    app.model.busy = None

    started_jobs: list[str] = []
    orig_start_job = app.start_job

    def guarded_start_job(job):
        before = app.model.busy
        orig_start_job(job)
        if before is None and app.model.busy == job:
            started_jobs.append(job)
            threads.pop()

    app.start_job = guarded_start_job

    # Scheduled loop, window Sync now and tray Sync now are all blocked.
    app.start_next()
    app.dispatch("sync")
    app.dispatch("sync", from_menu=True)
    assert started_jobs == [] and threads == []
    assert downloaded.read_bytes() == b"existing pdf"

    # Clicking the Update button runs the Store updater (falling back to Store URI here).
    app.dispatch(REQUIRED_UPDATE_ACTION)
    assert app.model.min_version_updating
    threads.pop(0)()
    assert not app.model.min_version_updating
    assert opened == [MS_STORE_URI]


# -- WebUI, Tk fallback & macOS AppKit / MenuBarApp ------------------------------------


def test_webui_and_tk_render_full_screen_update_required_in_ltr_and_arabic_rtl(tmp_path, monkeypatch):
    from blackboard_sync.windows import main_window as tk_module
    from tests.test_web_window import make_window as make_web_window
    from tests.test_windows import fake_tk

    req_model = signed_in_model(MinVersionResult("required", minimum="1.7.2"))
    req_status = main.main_status(req_model, NOW)

    # 1. WebMainWindow switches even a first-run window onto overview's Update required screen
    #    and only accepts REQUIRED_UPDATE_ACTION while enabled.
    web_win, _host, events = make_web_window()
    web_win.run_action(REQUIRED_UPDATE_ACTION)
    assert events == []

    first_run_blocked = AppModel(
        DEST, NOW, configured=False, min_version_state=MinVersionResult("required", minimum="1.7.2")
    )
    web_win.update_status(main.main_status(first_run_blocked, NOW))
    assert web_win.visible_page() == main.OVERVIEW
    web_win.run_action(REQUIRED_UPDATE_ACTION)
    assert events == [("action", REQUIRED_UPDATE_ACTION)]

    web_data = webui_state.window_state(req_status, main.OVERVIEW, main.OVERVIEW, today=date(2026, 11, 27))
    assert web_data["update_required"] == {
        "title": "Update required",
        "detail": req_status.update_required.detail,
        "notice": "",
        "button": {"id": REQUIRED_UPDATE_ACTION, "title": "Update", "enabled": True},
    }
    assert web_data["banner"] is None and web_data["license"] is None
    assert webui_state.ids(web_data)["update_required"] == {REQUIRED_UPDATE_ACTION}

    # Arabic translation & RTL document check.
    i18n.set_language("ar")
    try:
        ar_status = main.main_status(req_model, NOW)
        assert ar_status.update_required.title == "التحديث مطلوب"
        assert "1.7.2" in ar_status.update_required.detail
        ar_html = webui_page.document(nonce="n", lang="ar")
        assert '<html lang="ar" dir="rtl"' in ar_html
    finally:
        i18n.set_language("en")

    # 2. Tk fallback shows update_required_frame and hides overview_holder cleanly.
    fake_tk(monkeypatch, tmp_path)
    tk_actions: list[str] = []
    tk_win = tk_module.MainWindow(
        None,
        FormValues("https://bb.example.edu", str(tmp_path), True),
        main.main_status(signed_in_model(), NOW),
        lambda *a: None,
        tk_actions.append,
        lambda: None,
    )
    assert tk_win.update_required_frame.removed
    assert not tk_win.overview_holder.removed

    tk_win.update_status(req_status)
    assert not tk_win.update_required_frame.removed
    assert tk_win.overview_holder.removed
    assert tk_win.update_required_title.options["text"] == "Update required"
    assert "1.7.2" in tk_win.update_required_detail.options["text"]
    assert tk_win.update_required_button.options["text"] == "Update"
    tk_win.update_required_button.options["command"]()
    assert tk_actions == [REQUIRED_UPDATE_ACTION]

    tk_win.update_status(main.main_status(signed_in_model(), NOW))
    assert tk_win.update_required_frame.removed
    assert not tk_win.overview_holder.removed


def test_macos_window_and_menubar_app_enforce_min_version_dmg_retired_and_mas(tmp_path, monkeypatch):
    rumps = pytest.importorskip("rumps")
    pytest.importorskip("AppKit")
    from PyObjCTools import AppHelper

    from blackboard_sync.menubar import app as mac_app
    from blackboard_sync.menubar import rtl_layout
    from tests.test_menubar_app import make_window, visible_page

    # 1. AppKit MainWindow shows full-screen update_required_card on Home (also on first_run),
    #    handles both 'Update required' and 'Blackboard Sync moved to the Mac App Store',
    #    and keeps it centered under Arabic RTL mirroring.
    actions: list[str] = []
    first_run_model = AppModel(tmp_path, NOW, configured=False)
    window, model, _ = make_window(tmp_path, first_run_model, on_action=actions.append)
    try:
        assert visible_page(window) == "start"
        assert window.update_required_card.isHidden()

        model.apply_min_version(MinVersionResult("required", minimum="1.7.2"), NOW)
        window.update_status(main.main_status(model, NOW))
        assert visible_page(window) == main.OVERVIEW
        assert not window.update_required_card.isHidden()
        assert window.status_card.isHidden() and window.notebooklm_card.isHidden()
        assert window.ai_card.isHidden() and window.notify_card.isHidden() and window.calendar_card.isHidden()
        assert str(window.update_required_title.stringValue()) == "Update required"
        assert str(window.update_required_button.title()) == "Update"

        ltr_x = window.update_required_button.frame().origin.x
        rtl_layout.mirror(window.window.contentView())
        assert abs(window.update_required_button.frame().origin.x - ltr_x) < 1.0

        # Switch to retired .dmg state: multi-word title & 'Open Mac App Store' CTA.
        model.apply_min_version(MinVersionResult(STATUS_DMG_RETIRED, mas_url=SAMPLE_MAS_URL), NOW)
        window.update_status(main.main_status(model, NOW))
        assert str(window.update_required_title.stringValue()) == "Blackboard Sync moved to the Mac App Store"
        assert str(window.update_required_button.title()) == "Open Mac App Store"

        window.target.requiredUpdate_(None)
        assert actions == [REQUIRED_UPDATE_ACTION]
    finally:
        window.window.close()

    # 2. MenuBarApp blocks syncs when below minimum, starts update_macos on .dmg, opens App Store on MAS,
    #    and opens mas_url when dmg_retired is active on macOS direct.
    monkeypatch.setattr(rumps.Timer, "start", lambda self: None)
    monkeypatch.setattr(rumps.events.on_notification, "register", lambda callback: None)
    monkeypatch.setattr(rumps.events.on_wake, "register", lambda callback: None)
    monkeypatch.setattr(AppHelper, "callAfter", lambda fn, *a, **kw: fn(*a, **kw))
    monkeypatch.setattr(
        mac_app.threading,
        "Thread",
        lambda target, args=(), daemon=True, **kw: SimpleNamespace(start=lambda: target(*args)),
    )

    config = Config(base_url="https://bb.example.edu", dest=tmp_path / "Docs", data_dir=tmp_path / "data")
    current_result = [MinVersionResult("required", minimum="1.7.2")]
    checker = SimpleNamespace(check=lambda force=False: current_result[0])
    menu_app = mac_app.build_app(config, min_version_checker=checker)
    menu_app.notify = lambda note: None
    menu_app.quit = lambda _s=None: None
    menu_app.model.configured = True
    menu_app.model.session = {"saved_at": NOW.timestamp(), "user": {"displayName": "Ada Student"}}

    menu_app.start_min_version_check()
    assert menu_app.model.update_required
    menu_app.start_sync()
    assert menu_app.model.busy is None

    # Direct .dmg build below minimum: clicking Update fetches the release and runs update_macos.install.
    release = updater.Release(
        version="1.7.2",
        page_url="https://github.com/UmutYLCN/blackboard-sync/releases/tag/v1.7.2",
        asset_name="Blackboard-Sync-1.7.2.dmg",
        asset_url="https://github.com/UmutYLCN/blackboard-sync/releases/download/v1.7.2/Blackboard-Sync-1.7.2.dmg",
    )
    installed: list[str] = []
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "direct")
    monkeypatch.setattr(mac_app.updater, "check", lambda: updater.CheckResult("available", release))
    monkeypatch.setattr(mac_app.runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(
        mac_app.update_macos,
        "find_target",
        lambda _bundle: mac_app.update_macos.Target(tmp_path / "Blackboard Sync.app", "TEAM"),
    )
    monkeypatch.setattr(
        mac_app.update_macos,
        "install",
        lambda rel, *a, **kw: installed.append(rel.version),
    )
    menu_app.window_action(REQUIRED_UPDATE_ACTION)
    assert installed == ["1.7.2"]

    # Direct .dmg build when dmg_retired=true: stops syncing and button opens mas_url directly.
    opened_urls: list[str] = []
    monkeypatch.setattr(mac_app, "open_url", opened_urls.append)
    current_result[0] = MinVersionResult(STATUS_DMG_RETIRED, mas_url=SAMPLE_MAS_URL)
    menu_app.start_min_version_check()
    assert menu_app.model.min_version.dmg_retired
    assert menu_app.model.update_required
    menu_app.start_sync()
    assert menu_app.model.busy is None
    menu_app.window_action(REQUIRED_UPDATE_ACTION)
    assert opened_urls == [SAMPLE_MAS_URL]
    assert installed == ["1.7.2"]  # update_macos was NOT called for a retired .dmg

    # Mac App Store flavor below minimum: menu exposes REQUIRED_UPDATE_ACTION, Demo Mode is gated,
    # and clicking Update routes through updater.store_update_url() (generic Updates page, or exact app page
    # once MAS_APP_ID / BBSYNC_MAS_APP_ID is set, with HTTPS fallback on opener error).
    opened_urls.clear()
    monkeypatch.setenv("BBSYNC_DISTRIBUTION", "mas")
    monkeypatch.delenv("BBSYNC_MAS_APP_ID", raising=False)
    current_result[0] = MinVersionResult("required", minimum="1.9.0")
    menu_app.start_min_version_check()
    mas_menu = menu_app.model.menu(NOW)
    assert any(e.action == REQUIRED_UPDATE_ACTION and e.title == "Update required — Update" for e in mas_menu.entries)
    first_run_mas = AppModel(tmp_path, NOW, configured=False, min_version_state=MinVersionResult("required", minimum="1.9.0"))
    first_run_mas_status = main.main_status(first_run_mas, NOW)
    assert first_run_mas_status.shows_demo is False
    assert first_run_mas_status.update_required is not None

    menu_app.window_action(REQUIRED_UPDATE_ACTION)
    assert opened_urls == [updater.store_update_url()] == [MAC_APP_STORE_URL]

    opened_urls.clear()
    monkeypatch.setenv("BBSYNC_MAS_APP_ID", "6740001234")
    menu_app.window_action(REQUIRED_UPDATE_ACTION)
    assert opened_urls == [updater.store_update_url()] == ["macappstore://apps.apple.com/app/id6740001234"]

    fallback_seen: list[str] = []

    def fail_macappstore_scheme(target: str) -> None:
        if target.startswith("macappstore://"):
            raise OSError("scheme unavailable")
        fallback_seen.append(target)

    assert min_version.open_mac_app_store(opener=fail_macappstore_scheme) is True
    assert fallback_seen == ["https://apps.apple.com/app/id6740001234"]
