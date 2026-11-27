"""Online minimum-version check and Store update launchers; no GUI code.

The website serves ``https://blackboardsyncapp.com/min-version.json`` so older
builds can be asked to update (or the direct ``.dmg`` build can be retired in
favor of the Mac App Store) without shipping a new release first:

    {
      "schema": 1,
      "minimum": {"macos": "1.7.2", "windows": "1.7.2"},
      "dmg_retired": false,
      "mas_url": "https://apps.apple.com/app/id<TBD>"
    }

Unreachable servers, non-HTTPS responses, invalid JSON, unknown schema numbers
and missing/invalid keys all resolve to "no enforcement": a network or server
problem never locks a student out. Valid answers are cached briefly in memory
so startup and periodic checks do not re-fetch back to back.

When enforcement triggers:
- ``dmg_retired: true`` on a macOS direct (``.dmg``) build stops syncing and
  directs the student to ``mas_url`` (never affects Windows or ``mas`` builds);
- below ``minimum`` on macOS direct ``.dmg`` launches ``update_macos``;
- below ``minimum`` on Microsoft Store queries and installs updates via
  ``StoreContext`` (initialized with the window handle), falling back to opening
  the Store product page (``ms-windows-store://pdp/?ProductId=9NXJCQ5JL1KB``);
- below ``minimum`` on Mac App Store builds (seam) opens the App Store.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

import requests

from blackboard_sync import __version__, licensing, system, updater
from blackboard_sync.i18n import tr
from blackboard_sync.windows import package

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MIN_VERSION_URL = "https://blackboardsyncapp.com/min-version.json"
CHECK_TIMEOUT = 5
CACHE_TTL_SECONDS = 900.0  # 15 minutes

KEY_MACOS = "macos"
KEY_WINDOWS = "windows"
KEY_MAS = "mas"

STATUS_OK = "ok"
STATUS_REQUIRED = "required"
STATUS_DMG_RETIRED = "dmg_retired"
STATUS_UNKNOWN = "unknown"

MS_STORE_PRODUCT_ID = "9NXJCQ5JL1KB"
MS_STORE_URI = f"ms-windows-store://pdp/?ProductId={MS_STORE_PRODUCT_ID}"
MS_STORE_WEB_URL = "https://apps.microsoft.com/detail/9nxjcq5jl1kb"
MAC_APP_STORE_URL = "macappstore://showUpdatesPage"
MAC_APP_STORE_WEB_URL = "https://apps.apple.com/"

# StorePackageUpdateState values (Windows.Services.Store).
STORE_UPDATE_PENDING = 0
STORE_UPDATE_DOWNLOADING = 1
STORE_UPDATE_DEPLOYING = 2
STORE_UPDATE_COMPLETED = 3
STORE_UPDATE_CANCELED = 4
STORE_UPDATE_OTHER_ERROR = 5

STORE_UPDATE_TIMEOUT = 1800.0  # seconds: Store download + install


@dataclass(frozen=True)
class MinVersionResult:
    """How ``min-version.json`` applies to this build."""

    status: str  # "ok" | "required" | "dmg_retired" | "unknown"
    minimum: str = ""  # normalized "X.Y.Z" when present and valid
    mas_url: str = ""  # Mac App Store URL when ``status == "dmg_retired"``

    @property
    def required(self) -> bool:
        return self.status in (STATUS_REQUIRED, STATUS_DMG_RETIRED)

    @property
    def dmg_retired(self) -> bool:
        return self.status == STATUS_DMG_RETIRED


class StoreUpdateAction(str, Enum):
    INSTALLED = "installed"
    CANCELLED = "cancelled"
    OPENED_STORE = "opened_store"
    FAILED = "failed"


@dataclass(frozen=True)
class StoreUpdateResult:
    action: StoreUpdateAction
    message: str = ""


def valid_mas_url(raw: object) -> str | None:
    """Return ``raw`` stripped when it is a safe ``https://`` or ``macappstore://`` URL, else None."""
    if not isinstance(raw, str):
        return None
    url = raw.strip()
    if not url or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return None
    for scheme in ("https://", "macappstore://"):
        if url.startswith(scheme) and len(url) > len(scheme):
            return url
    return None


def is_macos_direct(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> bool:
    """True only when running on macOS as the direct (``.dmg``) distribution."""
    target_platform = platform or sys.platform
    if target_platform != "darwin":
        return False
    return licensing.current_distribution(platform=target_platform, env=env, packaged=packaged) == licensing.DIST_DIRECT


def platform_key(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> str | None:
    """Which ``minimum`` key governs this process (``macos``, ``windows``, ``mas``, or None)."""
    target_platform = platform or sys.platform
    dist = licensing.current_distribution(platform=target_platform, env=env, packaged=packaged)
    if dist == licensing.DIST_MAC_APP_STORE:
        return KEY_MAS
    if dist == licensing.DIST_MICROSOFT_STORE:
        return KEY_WINDOWS
    if target_platform == "darwin":
        return KEY_MACOS
    if system.is_windows(target_platform):
        return KEY_WINDOWS
    return None


def validate_payload(data: object) -> dict[str, object] | None:
    """Return a copy of ``data`` when it is a valid schema-1 payload, else None."""
    if not isinstance(data, dict):
        return None
    schema = data.get("schema")
    if type(schema) is not int or schema != SCHEMA_VERSION:
        return None
    minimum = data.get("minimum")
    if not isinstance(minimum, dict):
        return None
    copied = dict(data)
    copied["minimum"] = dict(minimum)
    return copied


def evaluate_minimum(
    minimum_map: Mapping[str, object],
    current: str = __version__,
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> MinVersionResult:
    """Compare ``current`` against ``minimum_map`` for this platform/distribution."""
    key = platform_key(platform=platform, env=env, packaged=packaged)
    if key is None or key not in minimum_map or minimum_map[key] is None:
        return MinVersionResult(STATUS_OK)
    raw = minimum_map[key]
    if not isinstance(raw, str):
        return MinVersionResult(STATUS_UNKNOWN)
    parsed_min = updater.parse_version(raw)
    if parsed_min is None:
        return MinVersionResult(STATUS_UNKNOWN)
    minimum_text = ".".join(map(str, parsed_min))
    if updater.parse_version(current) is None:
        return MinVersionResult(STATUS_OK, minimum=minimum_text)
    if updater.is_newer(minimum_text, current):
        return MinVersionResult(STATUS_REQUIRED, minimum=minimum_text)
    return MinVersionResult(STATUS_OK, minimum=minimum_text)


def evaluate_payload(
    payload: Mapping[str, object],
    current: str = __version__,
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> MinVersionResult:
    """Evaluate ``dmg_retired`` (macOS direct only) and ``minimum`` for this build."""
    raw_retired = payload.get("dmg_retired")
    if type(raw_retired) is bool and raw_retired and is_macos_direct(platform=platform, env=env, packaged=packaged):
        mas_url = valid_mas_url(payload.get("mas_url"))
        if mas_url is not None:
            return MinVersionResult(STATUS_DMG_RETIRED, mas_url=mas_url)
    minimum_map = payload.get("minimum")
    if not isinstance(minimum_map, Mapping):
        return MinVersionResult(STATUS_UNKNOWN)
    return evaluate_minimum(minimum_map, current, platform=platform, env=env, packaged=packaged)


def parse_min_version(
    data: object,
    current: str = __version__,
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
) -> MinVersionResult:
    """Interpret a decoded ``min-version.json`` payload; never raises."""
    payload = validate_payload(data)
    if payload is None:
        return MinVersionResult(STATUS_UNKNOWN)
    return evaluate_payload(payload, current, platform=platform, env=env, packaged=packaged)


def _fetch_payload(
    url: str = MIN_VERSION_URL,
    get: updater.Getter = updater._get,
    timeout: float = CHECK_TIMEOUT,
) -> tuple[str, dict[str, object] | None]:
    """Fetch ``url`` over HTTPS; returns ``("ok", payload)``, ``("invalid", None)``, or ``("unreachable", None)``."""
    if not url or not url.startswith("https://"):
        return "invalid", None
    try:
        resp = get(
            url,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        try:
            final_url = getattr(resp, "url", url)
            if final_url is not None and not str(final_url).startswith("https://"):
                log.info("min-version check rejected non-HTTPS redirect: %s", final_url)
                return "invalid", None
            if resp.status_code != 200:
                log.info("min-version check: HTTP %s", resp.status_code)
                return "unreachable", None
            data = resp.json()
        finally:
            resp.close()
    except requests.RequestException as exc:
        log.info("min-version check failed: %s", exc)
        return "unreachable", None
    except ValueError as exc:
        log.info("min-version check invalid JSON: %s", exc)
        return "invalid", None
    payload = validate_payload(data)
    if payload is None:
        log.info("min-version check rejected payload schema")
        return "invalid", None
    return "ok", payload


def check(
    current: str = __version__,
    *,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    packaged: bool | None = None,
    get: updater.Getter = updater._get,
    url: str = MIN_VERSION_URL,
) -> MinVersionResult:
    """Fetch ``min-version.json`` once and compare with ``current``; never raises."""
    kind, payload = _fetch_payload(url=url, get=get)
    if kind != "ok" or payload is None:
        return MinVersionResult(STATUS_UNKNOWN)
    return evaluate_payload(payload, current, platform=platform, env=env, packaged=packaged)


class MinVersionChecker:
    """Stateful checker that caches the last good ``min-version.json`` answer briefly."""

    def __init__(
        self,
        *,
        get: updater.Getter = updater._get,
        url: str = MIN_VERSION_URL,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        current: str | Callable[[], str] = __version__,
        platform: str | None = None,
        env: Mapping[str, str] | None = None,
        packaged: bool | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._get = get
        self._url = url
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._current = current
        self._platform = platform
        self._env = env
        self._packaged = packaged
        self._cached_payload: dict[str, object] | None = None
        self._cached_at: float = 0.0

    def _current_version(self) -> str:
        return self._current() if callable(self._current) else self._current

    def _evaluate(self, payload: Mapping[str, object]) -> MinVersionResult:
        return evaluate_payload(
            payload,
            self._current_version(),
            platform=self._platform,
            env=self._env,
            packaged=self._packaged,
        )

    def _fresh_cached_payload(self, now: float) -> dict[str, object] | None:
        if self._cached_payload is not None and 0.0 <= (now - self._cached_at) < self._ttl_seconds:
            return self._cached_payload
        return None

    def check(self, *, force: bool = False) -> MinVersionResult:
        """Return the current ``MinVersionResult``; never raises."""
        now = self._clock()
        with self._lock:
            if not force:
                cached = self._fresh_cached_payload(now)
                if cached is not None:
                    return self._evaluate(cached)
        kind, payload = _fetch_payload(url=self._url, get=self._get)
        fetched_at = self._clock()
        with self._lock:
            if kind == "ok" and payload is not None:
                self._cached_payload = payload
                self._cached_at = fetched_at
                return self._evaluate(self._cached_payload)
            if kind == "unreachable":
                cached = self._fresh_cached_payload(fetched_at)
                if cached is not None:
                    return self._evaluate(cached)
            self._cached_payload = None
            return MinVersionResult(STATUS_UNKNOWN)


def default_checker() -> MinVersionChecker:
    return MinVersionChecker()


def _default_windows_opener(uri: str) -> None:
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        startfile(uri)
    elif not webbrowser.open(uri):
        raise OSError(f"could not open {uri}")


def open_microsoft_store(
    uri: str = MS_STORE_URI,
    fallback_url: str = MS_STORE_WEB_URL,
    opener: Callable[[str], None] | None = None,
) -> bool:
    """Open the Microsoft Store listing; returns False only when both URIs fail."""
    open_fn = opener or _default_windows_opener
    try:
        open_fn(uri)
        return True
    except OSError:
        log.warning("Could not open %s; falling back to %s", uri, fallback_url, exc_info=True)
    try:
        if opener is not None:
            opener(fallback_url)
            return True
        return bool(webbrowser.open(fallback_url))
    except OSError:
        log.warning("Could not open Microsoft Store web URL %s", fallback_url, exc_info=True)
        return False


def _default_macos_opener(url: str) -> None:
    subprocess.Popen(["open", url], stdin=subprocess.DEVNULL)


def open_mac_app_store(
    url: str = MAC_APP_STORE_URL,
    fallback_url: str = MAC_APP_STORE_WEB_URL,
    opener: Callable[[str], None] | None = None,
) -> bool:
    """Open the Mac App Store page (seam for ``DIST_MAC_APP_STORE`` and retired ``.dmg`` builds)."""
    target = valid_mas_url(url) or MAC_APP_STORE_URL
    open_fn = opener or _default_macos_opener
    try:
        open_fn(target)
        return True
    except OSError:
        log.warning("Could not open %s; falling back to %s", target, fallback_url, exc_info=True)
    if fallback_url and fallback_url != target:
        try:
            open_fn(fallback_url)
            return True
        except OSError:
            log.warning("Could not open Mac App Store fallback %s", fallback_url, exc_info=True)
    return False


class WindowsStoreUpdater:
    """Microsoft Store self-update via ``StoreContext``, falling back to the Store page."""

    def __init__(
        self,
        *,
        context_factory: Callable[[], object] | None = None,
        initialize_window: Callable[[object, int], None] | None = None,
        mta_scope: Callable[[], contextlib.AbstractContextManager[None]] | None = None,
        is_packaged: Callable[[], bool] = package.is_packaged,
        opener: Callable[[str], None] | None = None,
        timeout: float = STORE_UPDATE_TIMEOUT,
    ) -> None:
        self._lock = threading.RLock()
        self._custom_factory = context_factory is not None
        self._context_factory = context_factory or licensing._default_store_context
        self._init_window = initialize_window or licensing._default_init_window
        self._keeper = None if (mta_scope is not None or self._custom_factory) else licensing._MtaKeeper()
        self._mta_scope = mta_scope or (
            self._keeper.thread_scope if self._keeper is not None else contextlib.nullcontext
        )
        self._is_packaged = is_packaged
        self._opener = opener
        self._timeout = timeout
        self._context: object | None = None
        self._completed_refs: list[object] = []

    def _ensure_context(self) -> object:
        with self._lock:
            if self._context is None:
                self._context = self._context_factory()
            return self._context

    def _fallback_to_store_page(self) -> StoreUpdateResult:
        if open_microsoft_store(opener=self._opener):
            return StoreUpdateResult(StoreUpdateAction.OPENED_STORE)
        return StoreUpdateResult(StoreUpdateAction.FAILED, tr("Could not install the update."))

    def install_update(
        self,
        hwnd: int | None = None,
        on_ui_thread: Callable[[Callable[[], None]], None] | None = None,
    ) -> StoreUpdateResult:
        """Query and install Store package updates with ``hwnd``, or open the Store listing."""
        if not self._custom_factory and not self._is_packaged():
            return self._fallback_to_store_page()
        try:
            with self._mta_scope():
                context = self._ensure_context()
                updates = context.get_app_and_optional_store_package_updates_async().get()
                if not updates or len(updates) == 0:
                    log.info("No pending Store package updates reported locally; opening Store listing")
                    return self._fallback_to_store_page()
                result, timed_out = licensing.run_store_windowed_async(
                    context,
                    init_window=self._init_window,
                    hwnd=hwnd,
                    on_ui_thread=on_ui_thread,
                    start_op=lambda ctx: ctx.request_download_and_install_store_package_updates_async(updates),
                    timeout=self._timeout,
                    ref_holder=self._completed_refs,
                )
                if timed_out or result is None:
                    log.warning("Store package update timed out or returned no result; opening Store listing")
                    return self._fallback_to_store_page()
                overall = int(getattr(result, "overall_state", STORE_UPDATE_OTHER_ERROR))
                if overall in (STORE_UPDATE_COMPLETED, STORE_UPDATE_DEPLOYING):
                    return StoreUpdateResult(StoreUpdateAction.INSTALLED)
                if overall == STORE_UPDATE_CANCELED:
                    return StoreUpdateResult(StoreUpdateAction.CANCELLED)
                log.warning("Store package update ended in state %d; opening Store listing", overall)
                return self._fallback_to_store_page()
        except Exception as exc:
            log.warning("Microsoft Store package update failed (%s); opening Store listing", exc)
            return self._fallback_to_store_page()

    def close(self) -> None:
        with self._lock:
            self._context = None
            self._completed_refs.clear()
        if self._keeper is not None:
            self._keeper.close()
