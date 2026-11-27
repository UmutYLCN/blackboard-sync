"""Store trial and one-time purchase licensing, kept platform-neutral above the providers.

Blackboard Sync needs no account of its own: the store account (Microsoft account
on Windows, Apple ID on the Mac App Store) tracks the free trial and the one-time
purchase. Direct builds (the GitHub ``.dmg`` and source runs) use ``AlwaysFullProvider``;
the MSIX-packaged Microsoft Store build uses ``WindowsStoreProvider``; the Mac App Store
build plugs in at ``DIST_MAC_APP_STORE`` (``MacAppStoreUnavailableProvider`` until its
StoreKit provider lands).

Offline or unreachable Store checks return ``LicenseKind.UNKNOWN``, which never locks out
a student: syncing keeps working and the app re-checks later.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Iterator, Mapping, Protocol

from blackboard_sync import system
from blackboard_sync.i18n import tr
from blackboard_sync.windows import package

log = logging.getLogger(__name__)

DISTRIBUTION_ENV = "BBSYNC_DISTRIBUTION"
SIMULATE_ENV = "BBSYNC_LICENSE_SIMULATE"
SIMULATE_PRICE_ENV = "BBSYNC_LICENSE_PRICE"

DIST_DIRECT = "direct"
DIST_MICROSOFT_STORE = "msstore"
DIST_MAC_APP_STORE = "mas"

# StorePurchaseStatus values (Windows.Services.Store).
PURCHASE_SUCCEEDED = 0
PURCHASE_ALREADY_PURCHASED = 1
PURCHASE_NOT_PURCHASED = 2
PURCHASE_NETWORK_ERROR = 3
PURCHASE_SERVER_ERROR = 4

PURCHASE_TIMEOUT = 600.0  # seconds: checkout may involve 2FA or adding a payment method
MAX_REASONABLE_TRIAL = timedelta(days=3650)

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd]?)\s*$", re.IGNORECASE)


class LicenseKind(str, Enum):
    FULL = "full"
    TRIAL = "trial"
    TRIAL_EXPIRED = "trial_expired"
    UNKNOWN = "unknown"  # offline / Store unreachable: grace


class PurchaseOutcome(str, Enum):
    PURCHASED = "purchased"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LicenseState:
    """How the current Store entitlement stands."""

    kind: LicenseKind
    expires_at: datetime | None = None
    formatted_price: str = ""
    message: str = ""

    def is_expired(self, now: datetime | None = None) -> bool:
        """True only when a trial is known to have ended and no full license is active."""
        if self.kind == LicenseKind.TRIAL_EXPIRED:
            return True
        if self.kind == LicenseKind.TRIAL and self.expires_at is not None and now is not None:
            return now >= self.expires_at
        return False

    def allows_sync(self, now: datetime | None = None) -> bool:
        """Full licenses, active trials and offline/unknown grace all allow syncing."""
        return not self.is_expired(now)

    def time_remaining(self, now: datetime) -> timedelta | None:
        if self.expires_at is None:
            return None
        return max(timedelta(0), self.expires_at - now)


@dataclass(frozen=True)
class PurchaseResult:
    outcome: PurchaseOutcome
    state: LicenseState
    message: str = ""


class LicenseProvider(Protocol):
    """Platform-specific entitlement check and purchase flow."""

    @property
    def managed(self) -> bool:
        """True when a Store manages trial/purchase entitlements for this build."""

    def get_state(self, now: datetime | None = None) -> LicenseState:
        """Return the current ``LicenseState``; never raises."""

    def purchase(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        """Run the Store purchase flow and return the updated state; never raises."""

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        """Register or clear a callback invoked when the Store signals a license change."""

    def close(self) -> None:
        """Release any Store event listeners."""


def _utcnow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def not_available_message() -> str:
    return tr("Purchases are not available in this build.")


def store_unreachable_message() -> str:
    return tr("Could not reach the Microsoft Store. Check your internet connection and try again.")


def purchase_failed_message() -> str:
    return tr("Could not complete the purchase in the Microsoft Store. Try again in a moment.")


def no_purchase_found_message() -> str:
    return tr("No purchase was found for this account yet.")


class AlwaysFullProvider:
    """Direct GitHub ``.dmg`` and unpackaged developer runs: always licensed."""

    managed = False

    def get_state(self, now: datetime | None = None) -> LicenseState:
        return LicenseState(LicenseKind.FULL)

    def purchase(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        return PurchaseResult(PurchaseOutcome.PURCHASED, LicenseState(LicenseKind.FULL))

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        pass

    def close(self) -> None:
        pass


class MacAppStoreUnavailableProvider:
    """Seam for the Mac App Store build before the StoreKit provider is wired in.

    ``get_state`` returns ``UNKNOWN`` (offline/unavailable grace) so a build launched
    against this stub never locks a student out; ``purchase`` reports that StoreKit
    purchases are not available in this build.
    """

    managed = True

    def get_state(self, now: datetime | None = None) -> LicenseState:
        return LicenseState(LicenseKind.UNKNOWN, message=not_available_message())

    def purchase(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        message = not_available_message()
        return PurchaseResult(PurchaseOutcome.UNAVAILABLE, LicenseState(LicenseKind.UNKNOWN, message=message), message)

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        pass

    def close(self) -> None:
        pass


def _hresult_code(error: object) -> int:
    if error is None:
        return 0
    value = getattr(error, "value", error)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _valid_expiry(
    expiration_date: datetime | None,
    trial_time_remaining: timedelta | None,
    now: datetime,
) -> datetime | None:
    """Normalize a ``StoreAppLicense`` expiry into a finite UTC ``datetime``, or None.

    Partner Center time-based trials populate ``ExpirationDate``; WinRT uses sentinel years
    (1601 for zero FILETIME, 9999 for unlimited) when no date applies. ``TrialTimeRemaining``
    is consulted only when ``ExpirationDate`` carries no finite date.
    """
    if isinstance(expiration_date, datetime):
        exp = expiration_date if expiration_date.tzinfo is not None else expiration_date.replace(tzinfo=timezone.utc)
        if 2000 <= exp.year < 9000 and exp - now <= MAX_REASONABLE_TRIAL:
            return exp.astimezone(timezone.utc)
    if isinstance(trial_time_remaining, timedelta) and timedelta(0) < trial_time_remaining <= MAX_REASONABLE_TRIAL:
        return now + trial_time_remaining
    return None


class _MtaKeeper:
    """Holds one COM MTA reference open so ``StoreContext`` and its event listener stay alive."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            ready = threading.Event()
            stop = threading.Event()

            def keep() -> None:
                from winrt.runtime import ApartmentType, init_apartment, uninit_apartment

                initialized = False
                try:
                    init_apartment(ApartmentType.MULTI_THREADED)
                    initialized = True
                except OSError:
                    pass
                ready.set()
                stop.wait()
                if initialized:
                    with contextlib.suppress(OSError):
                        uninit_apartment()

            thread = threading.Thread(target=keep, name="winrt-store-mta", daemon=True)
            thread.start()
            ready.wait(timeout=5.0)
            self._stop = stop
            self._thread = thread

    @contextlib.contextmanager
    def thread_scope(self) -> Iterator[None]:
        self.ensure_started()
        from winrt.runtime import ApartmentType, init_apartment, uninit_apartment

        initialized = False
        try:
            init_apartment(ApartmentType.MULTI_THREADED)
            initialized = True
        except OSError:
            pass  # caller is already in an apartment (e.g. STA)
        try:
            yield
        finally:
            if initialized:
                with contextlib.suppress(OSError):
                    uninit_apartment()

    def close(self) -> None:
        with self._lock:
            stop, thread = self._stop, self._thread
            self._stop = self._thread = None
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)


def _default_store_context():
    from winrt.windows.services.store import StoreContext

    return StoreContext.get_default()


def _default_init_window(context: object, hwnd: int) -> None:
    from winrt.runtime.interop import initialize_with_window

    initialize_with_window(context, hwnd)


def run_store_windowed_async(
    context: object,
    *,
    init_window: Callable[[object, int], None],
    hwnd: int | None,
    on_ui_thread: Callable[[Callable[[], None]], None] | None,
    start_op: Callable[[object], object],
    timeout: float,
    ref_holder: list[object] | None = None,
) -> tuple[object | None, bool]:
    """Initialize ``context`` with ``hwnd`` and await ``start_op(context)``.

    Returns ``(result, timed_out)``; raises when starting or completing the
    WinRT operation raises. When ``on_ui_thread`` is provided, modal initiation
    runs on that UI thread and completion is awaited via ``.completed`` so an
    STA UI pump never blocks.
    """
    if on_ui_thread is None:
        if hwnd:
            init_window(context, int(hwnd))
        return start_op(context).get(), False

    done = threading.Event()
    outcome_box: list[tuple[object | None, BaseException | None]] = []
    holder = ref_holder if ref_holder is not None else []

    def start_on_ui() -> None:
        try:
            if hwnd:
                init_window(context, int(hwnd))
            operation = start_op(context)
            if hasattr(operation, "completed"):
                def on_completed(async_op: object, _status: object) -> None:
                    try:
                        get_res = getattr(async_op, "get_results", None) or getattr(async_op, "get")
                        outcome_box.append((get_res(), None))
                    except BaseException as err:
                        outcome_box.append((None, err))
                    finally:
                        done.set()

                holder.append(on_completed)
                operation.completed = on_completed
            else:
                outcome_box.append((operation.get(), None))
                done.set()
        except BaseException as err:
            outcome_box.append((None, err))
            done.set()

    on_ui_thread(start_on_ui)
    try:
        if not done.wait(timeout=timeout):
            return None, True
    finally:
        holder.clear()
    result, error = outcome_box[0] if outcome_box else (None, RuntimeError("no result"))
    if error is not None:
        raise error
    return result, False


class WindowsStoreProvider:
    """Microsoft Store licensing via ``Windows.Services.Store.StoreContext`` (MSIX build)."""

    managed = True

    def __init__(
        self,
        *,
        context_factory: Callable[[], object] | None = None,
        initialize_window: Callable[[object, int], None] | None = None,
        mta_scope: Callable[[], contextlib.AbstractContextManager[None]] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._custom_factory = context_factory is not None
        self._context_factory = context_factory or _default_store_context
        self._init_window = initialize_window or _default_init_window
        self._keeper = None if (mta_scope is not None or self._custom_factory) else _MtaKeeper()
        self._mta_scope = mta_scope or (self._keeper.thread_scope if self._keeper is not None else contextlib.nullcontext)
        self._context: object | None = None
        self._token: object | None = None
        self._on_change: Callable[[], None] | None = None
        self._store_id: str = ""
        self._cached_price: str = ""
        self._purchased = False
        # Strong references to WinRT callbacks so Python GC never collects them mid-flight.
        self._offline_handler_ref = self._on_offline_licenses_changed
        self._purchase_completed_refs: list[object] = []

    def _on_offline_licenses_changed(self, _sender: object = None, _args: object = None) -> None:
        with self._lock:
            callback = self._on_change
        if callback is not None:
            try:
                callback()
            except Exception:
                log.exception("OfflineLicensesChanged callback failed")

    def _ensure_context(self) -> object:
        with self._lock:
            if self._context is None:
                self._context = self._context_factory()
            if self._token is None and self._on_change is not None:
                add = getattr(self._context, "add_offline_licenses_changed", None)
                if add is not None:
                    try:
                        self._token = add(self._offline_handler_ref)
                    except Exception:
                        log.warning("Could not subscribe to OfflineLicensesChanged", exc_info=True)
            return self._context

    def _load_product(self, context: object) -> object | None:
        """Query ``GetStoreProductForCurrentAppAsync`` for the formatted price and Store ID."""
        try:
            result = context.get_store_product_for_current_app_async().get()
        except Exception as exc:
            log.info("Could not query Microsoft Store product: %s", exc)
            return None
        if result is None:
            return None
        code = _hresult_code(getattr(result, "extended_error", 0))
        if code != 0:
            log.info("Microsoft Store product query returned HRESULT 0x%08X", code & 0xFFFFFFFF)
            return None
        product = getattr(result, "product", None)
        if product is None:
            return None
        store_id = str(getattr(product, "store_id", "") or "").strip()
        price_obj = getattr(product, "price", None)
        formatted = str(getattr(price_obj, "formatted_price", "") or "").strip() if price_obj is not None else ""
        with self._lock:
            if store_id:
                self._store_id = store_id
            if formatted:
                self._cached_price = formatted
        return product

    def _cached_values(self) -> tuple[str, str]:
        with self._lock:
            return self._store_id, self._cached_price

    def get_state(self, now: datetime | None = None) -> LicenseState:
        current_now = _utcnow(now)
        with self._lock:
            if self._purchased:
                return LicenseState(LicenseKind.FULL)
        try:
            with self._mta_scope():
                context = self._ensure_context()
                app_license = context.get_app_license_async().get()
                if app_license is None:
                    _, price = self._cached_values()
                    return LicenseState(LicenseKind.UNKNOWN, formatted_price=price)
                is_active = bool(getattr(app_license, "is_active", False))
                is_trial = bool(getattr(app_license, "is_trial", False))
                if is_active and not is_trial:
                    return LicenseState(LicenseKind.FULL)

                product = self._load_product(context)
                _, price = self._cached_values()
                expires_at = _valid_expiry(
                    getattr(app_license, "expiration_date", None),
                    getattr(app_license, "trial_time_remaining", None),
                    current_now,
                )
                if is_active and is_trial:
                    if expires_at is not None and expires_at <= current_now:
                        return LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=expires_at, formatted_price=price)
                    return LicenseState(LicenseKind.TRIAL, expires_at=expires_at, formatted_price=price)
                if not is_active and is_trial:
                    return LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=expires_at, formatted_price=price)
                # Neither active nor marked as trial: check whether the Store is reachable.
                if product is not None and bool(getattr(product, "is_in_user_collection", False)):
                    return LicenseState(LicenseKind.FULL)
                if product is None:
                    # Offline, Store unreachable, or a sideloaded test package without Store association.
                    return LicenseState(LicenseKind.UNKNOWN, formatted_price=price)
                return LicenseState(LicenseKind.TRIAL_EXPIRED, formatted_price=price)
        except Exception as exc:
            log.warning("Could not read Microsoft Store license: %s", exc)
            _, price = self._cached_values()
            return LicenseState(LicenseKind.UNKNOWN, formatted_price=price)

    def purchase(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        current_now = _utcnow(now)
        try:
            with self._mta_scope():
                context = self._ensure_context()
                store_id, _ = self._cached_values()
                if not store_id:
                    self._load_product(context)
                    store_id, _ = self._cached_values()
                if not store_id:
                    msg = store_unreachable_message()
                    return PurchaseResult(PurchaseOutcome.UNAVAILABLE, self.get_state(current_now), msg)

                purchase_result, timed_out = run_store_windowed_async(
                    context,
                    init_window=self._init_window,
                    hwnd=hwnd,
                    on_ui_thread=on_ui_thread,
                    start_op=lambda ctx: ctx.request_purchase_async(store_id),
                    timeout=PURCHASE_TIMEOUT,
                    ref_holder=self._purchase_completed_refs,
                )
                if timed_out:
                    msg = purchase_failed_message()
                    return PurchaseResult(PurchaseOutcome.UNAVAILABLE, self.get_state(current_now), msg)

                status = int(getattr(purchase_result, "status", PURCHASE_SERVER_ERROR))
                if status in (PURCHASE_SUCCEEDED, PURCHASE_ALREADY_PURCHASED):
                    with self._lock:
                        self._purchased = True
                    return PurchaseResult(PurchaseOutcome.PURCHASED, LicenseState(LicenseKind.FULL))
                if status == PURCHASE_NOT_PURCHASED:
                    return PurchaseResult(PurchaseOutcome.CANCELLED, self.get_state(current_now))
                code = _hresult_code(getattr(purchase_result, "extended_error", 0))
                log.warning("Microsoft Store purchase ended with status %d (HRESULT 0x%08X)",
                            status, code & 0xFFFFFFFF)
                msg = purchase_failed_message()
                return PurchaseResult(PurchaseOutcome.UNAVAILABLE, self.get_state(current_now), msg)
        except Exception as exc:
            log.warning("Microsoft Store purchase failed: %s", exc)
            msg = purchase_failed_message()
            return PurchaseResult(PurchaseOutcome.UNAVAILABLE, self.get_state(current_now), msg)

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        with self._lock:
            self._on_change = callback
            if self._context is not None and self._token is None and callback is not None:
                add = getattr(self._context, "add_offline_licenses_changed", None)
                if add is not None:
                    try:
                        self._token = add(self._offline_handler_ref)
                    except Exception:
                        log.warning("Could not subscribe to OfflineLicensesChanged", exc_info=True)

    def close(self) -> None:
        with self._lock:
            context, token = self._context, self._token
            self._context = self._token = None
            self._on_change = None
            self._purchase_completed_refs.clear()
        if context is not None and token is not None:
            remove = getattr(context, "remove_offline_licenses_changed", None)
            if remove is not None:
                with contextlib.suppress(Exception):
                    with self._mta_scope():
                        remove(token)
        if self._keeper is not None:
            self._keeper.close()


def _parse_simulated_duration(spec: str) -> timedelta:
    match = _DURATION_RE.match(spec)
    if not match:
        return timedelta(hours=24)
    amount = max(1, int(match.group(1)))
    unit = (match.group(2) or "h").lower()
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(hours=amount)


class SimulatedLicenseProvider:
    """Local license simulation via ``BBSYNC_LICENSE_SIMULATE`` for manual verification."""

    managed = True

    def __init__(self, initial: LicenseState) -> None:
        self._lock = threading.Lock()
        self._state = initial
        self._on_change: Callable[[], None] | None = None

    def get_state(self, now: datetime | None = None) -> LicenseState:
        current_now = _utcnow(now)
        with self._lock:
            state = self._state
            if state.kind == LicenseKind.TRIAL and state.expires_at is not None and current_now >= state.expires_at:
                state = LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=state.expires_at,
                                     formatted_price=state.formatted_price)
                self._state = state
            return state

    def purchase(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
        now: datetime | None = None,
    ) -> PurchaseResult:
        with self._lock:
            self._state = LicenseState(LicenseKind.FULL)
            callback = self._on_change
        if callback is not None:
            callback()
        return PurchaseResult(PurchaseOutcome.PURCHASED, LicenseState(LicenseKind.FULL))

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        with self._lock:
            self._on_change = callback

    def close(self) -> None:
        with self._lock:
            self._on_change = None


def current_distribution(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> str:
    """Which distribution this process runs as: ``msstore``, ``mas``, or ``direct``.

    An MSIX-packaged Windows process always resolves to ``msstore`` so environment
    variables on a student's PC cannot downgrade a Store package to ``direct``.
    """
    env = os.environ if env is None else env
    is_win = system.is_windows(platform)
    is_msix = package.is_packaged() if (packaged is None and is_win) else bool(packaged)
    if is_win and is_msix:
        return DIST_MICROSOFT_STORE
    raw = (env.get(DISTRIBUTION_ENV) or "").strip().lower()
    if raw in (DIST_MICROSOFT_STORE, "windows-store", "msix"):
        return DIST_MICROSOFT_STORE
    if raw in (DIST_MAC_APP_STORE, "appstore", "mac-app-store"):
        return DIST_MAC_APP_STORE
    if raw == DIST_DIRECT:
        return DIST_DIRECT
    return DIST_DIRECT


def _simulated_provider(
    env: Mapping[str, str],
    now: datetime,
    *,
    allow_full: bool,
) -> SimulatedLicenseProvider | None:
    raw = (env.get(SIMULATE_ENV) or "").strip()
    if not raw:
        return None
    price = (env.get(SIMULATE_PRICE_ENV) or "").strip()
    head, _, tail = raw.partition(":")
    mode = head.strip().lower()
    if mode == "full" and allow_full:
        return SimulatedLicenseProvider(LicenseState(LicenseKind.FULL))
    if mode == "trial":
        duration = _parse_simulated_duration(tail) if tail.strip() else timedelta(hours=24)
        return SimulatedLicenseProvider(
            LicenseState(LicenseKind.TRIAL, expires_at=now + duration, formatted_price=price)
        )
    if mode in ("expired", "trial_expired"):
        return SimulatedLicenseProvider(
            LicenseState(LicenseKind.TRIAL_EXPIRED, expires_at=now - timedelta(seconds=1), formatted_price=price)
        )
    if mode in ("offline", "unknown"):
        return SimulatedLicenseProvider(LicenseState(LicenseKind.UNKNOWN, formatted_price=price))
    return None


def default_provider(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
    now: datetime | None = None,
) -> LicenseProvider:
    """Pick the license provider for this build."""
    env = os.environ if env is None else env
    is_win = system.is_windows(platform)
    is_msix = package.is_packaged() if (packaged is None and is_win) else bool(packaged)
    simulated = _simulated_provider(env, _utcnow(now), allow_full=not is_msix)
    if simulated is not None:
        return simulated
    dist = current_distribution(platform=platform, env=env, packaged=is_msix)
    if dist == DIST_MICROSOFT_STORE:
        return WindowsStoreProvider()
    if dist == DIST_MAC_APP_STORE:
        return MacAppStoreUnavailableProvider()
    return AlwaysFullProvider()
