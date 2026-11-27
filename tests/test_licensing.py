"""Store trial and one-time purchase licensing: providers, sync gating and UI states."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from blackboard_sync import licensing
from blackboard_sync.config import Config
from blackboard_sync.licensing import (
    AlwaysFullProvider,
    LicenseKind,
    LicenseState,
    MacAppStoreUnavailableProvider,
    PurchaseOutcome,
    PurchaseResult,
    WindowsStoreProvider,
    current_distribution,
    default_provider,
)
from blackboard_sync.menubar import main_window_model as main
from blackboard_sync.menubar.model import (
    FIRST_SYNC_DELAY,
    LICENSE_CHECK_INTERVAL,
    LICENSE_RETRY_INTERVAL,
    AppModel,
    Icon,
    RecentItem,
    RunOutcome,
)
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.settings import Settings
from blackboard_sync.windows import webui_state

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
DEST = Path("/Users/student/Documents")


class FakeLicenseProvider:
    """Controllable ``LicenseProvider`` for testing trial, expiry, offline grace and purchase."""

    managed = True

    def __init__(self, state: LicenseState, purchase_result: PurchaseResult | None = None):
        self.state = state
        self.purchase_result = purchase_result
        self.checks = 0
        self.purchases: list[tuple[int | None, bool]] = []
        self.on_change = None
        self.closed = False

    def get_state(self, now: datetime | None = None) -> LicenseState:
        self.checks += 1
        return self.state

    def purchase(self, hwnd=None, on_ui_thread=None, now=None) -> PurchaseResult:
        ran_on_ui = False
        if on_ui_thread is not None:
            def mark():
                nonlocal ran_on_ui
                ran_on_ui = True
            on_ui_thread(mark)
        self.purchases.append((hwnd, ran_on_ui))
        if self.purchase_result is not None:
            self.state = self.purchase_result.state
            return self.purchase_result
        self.state = LicenseState(LicenseKind.FULL)
        return PurchaseResult(PurchaseOutcome.PURCHASED, self.state)

    def set_on_change(self, callback) -> None:
        self.on_change = callback

    def close(self) -> None:
        self.closed = True


class _FakeOp:
    """WinRT ``IAsyncOperation`` stand-in supporting both ``.get()`` and ``.completed``."""

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


class _FakeStoreContext:
    def __init__(self, app_license=None, product_result=None, purchase_result=None, license_error=None):
        self.app_license = app_license
        self.product_result = product_result
        self.purchase_result = purchase_result
        self.license_error = license_error
        self.handlers: dict[int, object] = {}
        self.removed_tokens: list[int] = []
        self.purchase_store_ids: list[str] = []
        self._next_token = 10

    def add_offline_licenses_changed(self, handler):
        token = self._next_token
        self._next_token += 1
        self.handlers[token] = handler
        return token

    def remove_offline_licenses_changed(self, token):
        self.removed_tokens.append(token)
        self.handlers.pop(token, None)

    def fire_offline_changed(self):
        for handler in list(self.handlers.values()):
            handler(self, None)

    def get_app_license_async(self):
        return _FakeOp(self.app_license, self.license_error)

    def get_store_product_for_current_app_async(self):
        return _FakeOp(self.product_result)

    def request_purchase_async(self, store_id: str):
        self.purchase_store_ids.append(store_id)
        return _FakeOp(self.purchase_result)


def signed_in_model(license_state: LicenseState | None = None) -> AppModel:
    session = {"saved_at": NOW.timestamp(), "user": {"displayName": "Umut Yalcin"}}
    return AppModel(
        DEST,
        NOW,
        configured=True,
        session=session,
        last=RunOutcome("ok", finished_at=NOW - timedelta(minutes=20)),
        recent=[RecentItem("2026-2027 Fall/CSE303/week1.pdf", "CSE303", NOW.isoformat())],
        license_state=license_state,
    )


# -- Distribution selection & MAS seam ------------------------------------------------


def test_distribution_selects_full_for_direct_and_store_for_packaged_msix():
    assert current_distribution(platform="darwin", env={}, packaged=False) == licensing.DIST_DIRECT
    assert current_distribution(platform="win32", env={}, packaged=False) == licensing.DIST_DIRECT
    assert current_distribution(platform="win32", env={}, packaged=True) == licensing.DIST_MICROSOFT_STORE
    # An MSIX-packaged build cannot be downgraded to direct/full via environment variables.
    assert current_distribution(
        platform="win32", env={"BBSYNC_DISTRIBUTION": "direct"}, packaged=True
    ) == licensing.DIST_MICROSOFT_STORE

    direct = default_provider(platform="darwin", env={}, packaged=False, now=NOW)
    assert isinstance(direct, AlwaysFullProvider) and not direct.managed
    assert direct.get_state(NOW) == LicenseState(LicenseKind.FULL)

    # Packaged MSIX ignores BBSYNC_LICENSE_SIMULATE=full.
    msix_provider = default_provider(
        platform="win32", env={"BBSYNC_LICENSE_SIMULATE": "full"}, packaged=True, now=NOW
    )
    assert isinstance(msix_provider, WindowsStoreProvider) and msix_provider.managed


def test_mac_app_store_seam_uses_grace_until_storekit_lands():
    provider = default_provider(platform="darwin", env={"BBSYNC_DISTRIBUTION": "mas"}, packaged=False, now=NOW)
    assert isinstance(provider, MacAppStoreUnavailableProvider) and provider.managed
    state = provider.get_state(NOW)
    assert state.kind == LicenseKind.UNKNOWN and state.allows_sync(NOW)
    result = provider.purchase(now=NOW)
    assert result.outcome == PurchaseOutcome.UNAVAILABLE
    assert "not available" in result.message


def test_license_simulation_supports_trial_expired_and_offline():
    trial = default_provider(
        platform="darwin",
        env={"BBSYNC_LICENSE_SIMULATE": "trial:6h", "BBSYNC_LICENSE_PRICE": "$4.99"},
        packaged=False,
        now=NOW,
    )
    state = trial.get_state(NOW)
    assert state.kind == LicenseKind.TRIAL
    assert state.expires_at == NOW + timedelta(hours=6)
    assert state.formatted_price == "$4.99"
    # Passing expiry flips the simulated trial to expired; purchasing flips it to full.
    expired = trial.get_state(NOW + timedelta(hours=7))
    assert expired.kind == LicenseKind.TRIAL_EXPIRED and not expired.allows_sync(NOW + timedelta(hours=7))
    purchased = trial.purchase(now=NOW + timedelta(hours=7))
    assert purchased.outcome == PurchaseOutcome.PURCHASED and purchased.state.kind == LicenseKind.FULL


# -- WindowsStoreProvider (WinRT StoreContext contract) -------------------------------


def test_windows_store_provider_maps_full_trial_expired_and_offline_states():
    # 1. Full license: active and not a trial.
    ctx = _FakeStoreContext(app_license=SimpleNamespace(is_active=True, is_trial=False))
    provider = WindowsStoreProvider(context_factory=lambda: ctx)
    assert provider.get_state(NOW) == LicenseState(LicenseKind.FULL)

    # 2. Active trial: reads expiry and StoreProduct.Price.FormattedPrice.
    expiry = NOW + timedelta(hours=18)
    product = SimpleNamespace(
        store_id="9NBLGGH4TEST",
        is_in_user_collection=True,
        price=SimpleNamespace(formatted_price="₺179,00"),
    )
    ctx.app_license = SimpleNamespace(
        is_active=True, is_trial=True, expiration_date=expiry, trial_time_remaining=timedelta(0)
    )
    ctx.product_result = SimpleNamespace(extended_error=0, product=product)
    state = provider.get_state(NOW)
    assert state == LicenseState(LicenseKind.TRIAL, expires_at=expiry, formatted_price="₺179,00")

    # 3. Expired trial: IsActive=False, IsTrial=True.
    ctx.app_license = SimpleNamespace(
        is_active=False, is_trial=True, expiration_date=NOW - timedelta(hours=1), trial_time_remaining=timedelta(0)
    )
    expired = provider.get_state(NOW)
    assert expired.kind == LicenseKind.TRIAL_EXPIRED
    assert expired.formatted_price == "₺179,00"
    assert not expired.allows_sync(NOW)

    # 4. Offline / Store unreachable: GetAppLicenseAsync raises -> UNKNOWN grace.
    offline_ctx = _FakeStoreContext(license_error=OSError("Store service unreachable"))
    offline_provider = WindowsStoreProvider(context_factory=lambda: offline_ctx)
    grace = offline_provider.get_state(NOW)
    assert grace.kind == LicenseKind.UNKNOWN and grace.allows_sync(NOW)

    # 5. Unassociated sideloaded package or offline first run (IsActive=False, IsTrial=False, no Store product).
    sideload_ctx = _FakeStoreContext(
        app_license=SimpleNamespace(is_active=False, is_trial=False, expiration_date=datetime(1601, 1, 1, tzinfo=timezone.utc)),
        product_result=SimpleNamespace(extended_error=-2147012889, product=None),
    )
    sideload_provider = WindowsStoreProvider(context_factory=lambda: sideload_ctx)
    assert sideload_provider.get_state(NOW).kind == LicenseKind.UNKNOWN


def test_windows_store_provider_initializes_window_purchases_and_listens_for_changes():
    product = SimpleNamespace(
        store_id="9NBLGGH4TEST",
        is_in_user_collection=False,
        price=SimpleNamespace(formatted_price="$4.99"),
    )
    ctx = _FakeStoreContext(
        app_license=SimpleNamespace(
            is_active=False, is_trial=True, expiration_date=NOW - timedelta(minutes=5), trial_time_remaining=timedelta(0)
        ),
        product_result=SimpleNamespace(extended_error=0, product=product),
        purchase_result=SimpleNamespace(status=licensing.PURCHASE_SUCCEEDED, extended_error=0),
    )
    initialized: list[tuple[object, int]] = []
    ui_calls: list[str] = []
    changed_events: list[int] = []

    provider = WindowsStoreProvider(
        context_factory=lambda: ctx,
        initialize_window=lambda obj, hwnd: initialized.append((obj, hwnd)),
    )
    provider.set_on_change(lambda: changed_events.append(1))
    assert provider.get_state(NOW).kind == LicenseKind.TRIAL_EXPIRED

    # OfflineLicensesChanged notifies the app.
    ctx.fire_offline_changed()
    assert changed_events == [1]

    # Purchase initializes StoreContext with the window handle on the UI thread and flips to FULL.
    def on_ui(fn):
        ui_calls.append("ui")
        fn()

    ctx.app_license = SimpleNamespace(is_active=True, is_trial=False)
    result = provider.purchase(hwnd=0x123456, on_ui_thread=on_ui, now=NOW)
    assert result.outcome == PurchaseOutcome.PURCHASED
    assert result.state == LicenseState(LicenseKind.FULL)
    assert ui_calls == ["ui"]
    assert initialized == [(ctx, 0x123456)]
    assert ctx.purchase_store_ids == ["9NBLGGH4TEST"]

    # User cancellation keeps the current state without an error message.
    cancel_ctx = _FakeStoreContext(
        app_license=SimpleNamespace(
            is_active=False, is_trial=True, expiration_date=NOW - timedelta(minutes=5), trial_time_remaining=timedelta(0)
        ),
        product_result=SimpleNamespace(extended_error=0, product=product),
        purchase_result=SimpleNamespace(status=licensing.PURCHASE_NOT_PURCHASED, extended_error=0),
    )
    cancel_provider = WindowsStoreProvider(
        context_factory=lambda: cancel_ctx,
        initialize_window=lambda obj, hwnd: None,
    )
    cancelled = cancel_provider.purchase(hwnd=0x123456, on_ui_thread=on_ui, now=NOW)
    assert cancelled.outcome == PurchaseOutcome.CANCELLED and cancelled.message == ""
    assert cancelled.state.kind == LicenseKind.TRIAL_EXPIRED

    provider.close()
    assert len(ctx.removed_tokens) == 1


# -- AppModel, MainStatus, WebUI, Tk fallback & TrayApp -------------------------------


@pytest.mark.parametrize("delta, expected_line", [
    (timedelta(minutes=25), "Free trial · 25 minutes left"),
    (timedelta(hours=1), "Free trial · 1 hour left"),
    (timedelta(hours=18), "Free trial · 18 hours left"),
    (timedelta(hours=24), "Free trial · 24 hours left"),
    (timedelta(days=5), "Free trial · 5 days left"),
])
def test_trial_running_allows_sync_and_formats_any_partner_center_trial_length(delta, expected_line):
    model = signed_in_model(LicenseState(LicenseKind.TRIAL, expires_at=NOW + delta, formatted_price="$4.99"))
    assert model.due(NOW + FIRST_SYNC_DELAY)
    assert model.menu(NOW).sync_enabled
    status = main.main_status(model, NOW)
    assert status.sync_enabled
    assert status.license is not None
    assert status.license.kind == main.LICENSE_TRIAL
    assert status.license.detail == expected_line
    assert status.license.buy_title == "Buy"
    assert status.license.restore_action == ""

    web = webui_state.window_state(status, main.OVERVIEW, main.OVERVIEW, today=date(2026, 11, 27))
    assert web["license"]["kind"] == "trial"
    assert web["license"]["detail"] == expected_line
    assert webui_state.ids(web)["license"] == {main.LICENSE_BUY_ACTION}


def test_trial_expired_blocks_sync_shows_store_price_and_keeps_downloaded_files():
    model = signed_in_model(
        LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=NOW - timedelta(hours=2), formatted_price="€4,99")
    )
    model.pending = "sync"
    assert not model.due(NOW + timedelta(days=1))
    assert model.pending_job(NOW) is None
    assert not model.session_check_due(NOW + timedelta(days=1))
    assert model.icon() == Icon.PAUSED

    menu = model.menu(NOW)
    assert not menu.sync_enabled
    assert "Free trial ended" in menu.status_lines
    # Downloaded files in Recent downloads and Open folder remain accessible.
    assert len(menu.recent) == 1 and "week1.pdf" in menu.recent[0][0]
    assert any(entry.action == "folder" and entry.enabled for entry in menu.entries)

    status = main.main_status(model, NOW)
    assert not status.sync_enabled and not status.pause_enabled
    assert status.home.title == "Free trial ended"
    assert len(status.recent) == 1 and status.recent[0].name == "week1.pdf"
    card = status.license
    assert card is not None and card.kind == main.LICENSE_EXPIRED
    assert card.title == "Your free trial has ended"
    assert "€4,99" in card.detail
    assert card.buy_title == "Buy for €4,99"
    assert card.restore_title == "I already bought it"

    # Without a Store price yet, no hardcoded price appears.
    no_price = signed_in_model(LicenseState(LicenseKind.TRIAL_EXPIRED))
    no_price_card = main.main_status(no_price, NOW).license
    assert no_price_card.buy_title == "Buy"
    assert "$" not in no_price_card.detail and "€" not in no_price_card.detail

    web = webui_state.window_state(status, main.OVERVIEW, main.OVERVIEW, today=date(2026, 11, 27))
    assert web["license"]["kind"] == "expired"
    assert web["home"]["button"] == {"id": "sync", "title": "Sync now", "enabled": False}
    assert webui_state.ids(web)["license"] == {main.LICENSE_BUY_ACTION, main.LICENSE_RESTORE_ACTION}


def test_offline_unknown_license_keeps_working_and_rechecks_later():
    model = signed_in_model(LicenseState(LicenseKind.UNKNOWN))
    model.apply_license(LicenseState(LicenseKind.UNKNOWN), NOW)
    assert model.due(NOW + FIRST_SYNC_DELAY)
    assert model.menu(NOW).sync_enabled
    status = main.main_status(model, NOW)
    assert status.sync_enabled and status.license is None
    assert not model.license_check_due(NOW + timedelta(minutes=5), managed=True)
    assert model.license_check_due(NOW + LICENSE_RETRY_INTERVAL, managed=True)


def test_full_license_shows_no_trial_ui_and_skips_periodic_polling():
    model = signed_in_model(LicenseState(LicenseKind.FULL))
    model.apply_license(LicenseState(LicenseKind.FULL), NOW)
    assert model.due(NOW + FIRST_SYNC_DELAY)
    status = main.main_status(model, NOW)
    assert status.sync_enabled and status.license is None
    assert not model.license_check_due(NOW + LICENSE_CHECK_INTERVAL * 10, managed=True)


def test_tray_app_blocks_expired_sync_and_purchase_or_restore_unlocks_sync(tmp_path, monkeypatch):
    from blackboard_sync.windows.app import TrayApp

    provider = FakeLicenseProvider(
        LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=NOW - timedelta(hours=1), formatted_price="$4.99")
    )
    app = TrayApp.__new__(TrayApp)
    app.config = Config(data_dir=tmp_path, dest=tmp_path / "Docs")
    app.settings = Settings("https://bb.example.edu", tmp_path / "Docs")
    app.login_after_job = False
    app.uninstalling = False
    app.closed = False
    app.model = signed_in_model(provider.state)
    app.license_provider = provider
    provider.set_on_change(lambda: app.post(app.on_license_changed))
    app.save = lambda: None
    app.refresh = lambda: None
    app.window = None
    app.root = None
    app.web = SimpleNamespace(
        window_handle=lambda: 0xBEEF,
        invoke_ui=lambda fn: fn(),
    )

    threads: list[object] = []
    monkeypatch.setattr(
        "blackboard_sync.windows.app.threading.Thread",
        lambda target, daemon=True, **kw: SimpleNamespace(start=lambda: threads.append(target)),
    )
    app.post = lambda callback, *args: callback(*args)
    monkeypatch.setattr("blackboard_sync.windows.app.jobs.utcnow", lambda: NOW)
    monkeypatch.setattr("blackboard_sync.windows.app.jobs.refresh_session", lambda *a: None)

    started_jobs: list[str] = []
    # Exercise the real TrayApp.start_job guard, without spawning a real CLI sync subprocess.
    orig_start_job = app.start_job

    def guarded_start_job(job):
        before = app.model.busy
        orig_start_job(job)
        if before is None and app.model.busy == job:
            started_jobs.append(job)
            threads.pop()  # drop the sync worker thread queued by start_job

    app.start_job = guarded_start_job

    # Sync loop, manual Sync now and tray Sync now are all blocked while expired.
    app.start_next()
    app.dispatch("sync")
    app.dispatch("sync", from_menu=True)
    assert started_jobs == [] and threads == []

    # "I already bought it" re-checks; while still expired it leaves a clear notice.
    app.dispatch(main.LICENSE_RESTORE_ACTION)
    assert app.model.license_busy == "restore"
    threads.pop(0)()
    assert app.model.license_busy is None
    assert app.model.license.kind == LicenseKind.TRIAL_EXPIRED
    assert "No purchase was found" in app.model.license_notice
    assert started_jobs == []

    # Clicking Buy passes the WebView2 HWND + UI dispatcher to the provider, flips to FULL, and starts a sync.
    app.dispatch(main.LICENSE_BUY_ACTION)
    assert app.model.license_busy == "buy"
    threads.pop(0)()  # purchase worker -> purchase_done -> start_next -> start_job("sync")
    assert provider.purchases == [(0xBEEF, True)]
    assert app.model.license == LicenseState(LicenseKind.FULL)
    assert app.model.license_notice == ""
    assert started_jobs == ["sync"]

    # OfflineLicensesChanged also refreshes the license when bought externally in the Store app.
    app.model.busy = None
    started_jobs.clear()
    provider.state = LicenseState(LicenseKind.TRIAL_EXPIRED, formatted_price="$4.99")
    app.model.apply_license(provider.state, NOW)
    provider.state = LicenseState(LicenseKind.FULL)
    provider.on_change()
    threads.pop(0)()
    assert app.model.license == LicenseState(LicenseKind.FULL)
    assert started_jobs == ["sync"]


def test_web_window_and_tk_fallback_render_and_route_license_actions(tmp_path, monkeypatch):
    from blackboard_sync.windows import main_window as tk_module
    from tests.test_web_window import make_window as make_web_window
    from tests.test_windows import fake_tk

    expired_model = signed_in_model(
        LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=NOW - timedelta(hours=1), formatted_price="$4.99")
    )
    expired_status = main.main_status(expired_model, NOW)

    # 1. WebMainWindow only forwards license actions when the license card is drawn and enabled.
    web_win, _host, events = make_web_window()
    web_win.run_action(main.LICENSE_BUY_ACTION)
    web_win.run_action(main.LICENSE_RESTORE_ACTION)
    assert events == []

    web_win.update_status(expired_status)
    web_win.run_action(main.LICENSE_BUY_ACTION)
    web_win.run_action(main.LICENSE_RESTORE_ACTION)
    assert events == [("action", main.LICENSE_BUY_ACTION), ("action", main.LICENSE_RESTORE_ACTION)]

    # 2. Tk fallback window shows and hides the license banner cleanly without disturbing update_banner's row.
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
    assert tk_win.overview_license_banner[0].removed
    assert tk_win.overview_update_banner[0].grid_options["row"] == 1

    tk_win.update_status(expired_status)
    box, title, detail, _notice, buy, restore = tk_win.overview_license_banner
    assert not box.removed
    assert title.options["text"] == "Your free trial has ended"
    assert "$4.99" in detail.options["text"]
    assert buy.options["text"] == "Buy for $4.99"
    assert restore.options["text"] == "I already bought it"
    buy.options["command"]()
    restore.options["command"]()
    assert tk_actions == [main.LICENSE_BUY_ACTION, main.LICENSE_RESTORE_ACTION]


def test_windows_packaging_declares_store_winrt_dependencies():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    lock = (root / "requirements.lock").read_text(encoding="utf-8")
    spec = (root / "packaging" / "blackboard_sync_windows.spec").read_text(encoding="utf-8")
    assert "winrt-Windows.Services.Store==4!10.0.28000.2957; sys_platform == 'win32'" in pyproject
    for pkg in ("winrt-runtime==", "winrt-Windows.Foundation==", "winrt-Windows.Foundation.Collections==",
                "winrt-Windows.Services.Store=="):
        assert pkg in lock
    for hidden in ('"blackboard_sync.licensing"', '"winrt.runtime.interop"', '"winrt.windows.services.store"'):
        assert hidden in spec
