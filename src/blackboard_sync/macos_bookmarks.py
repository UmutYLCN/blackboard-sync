"""Security-scoped folder bookmarks for the Mac App Store (App Sandbox) build.

Under macOS App Sandbox, an app cannot read or write arbitrary folders such as
``~/Documents/University`` unless the student picked the folder in ``NSOpenPanel``
(``com.apple.security.files.user-selected.read-write``). To keep that permission
across restarts and across child CLI ``sync`` runs, the ``NSURL`` returned by
``NSOpenPanel`` is saved as an app-scoped security-scoped bookmark
(``com.apple.security.files.bookmarks.app-scope``) in ``dest-bookmark.json`` and
resolved + activated with ``startAccessingSecurityScopedResource`` on every launch.

Outside the kernel sandbox (developer runs with ``BBSYNC_DISTRIBUTION=mas`` or unit
tests on any OS), ``NSURLBookmarkCreationWithSecurityScope`` is unavailable without
the sandbox entitlement, so the module falls back cleanly to a plain ``NSURL``
bookmark (or path record off macOS) while exercising the exact same persistence,
resolution, stale-refresh, and sync-gate contract.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Iterator, Mapping

from blackboard_sync import licensing
from blackboard_sync.errors import BlackboardSyncError
from blackboard_sync.i18n import tr
from blackboard_sync.session import write_private_json
from blackboard_sync.system import make_private_dir

log = logging.getLogger(__name__)

BOOKMARK_FILE = "dest-bookmark.json"

# Strong references to active security-scoped NSURLs so Python/PyObjC GC never
# deallocates an NSURL while its kernel sandbox token is in use.
_lock = threading.RLock()
_active_urls: dict[str, tuple[object, bool]] = {}


def bookmark_path(data_dir: Path) -> Path:
    return data_dir / BOOKMARK_FILE


def _is_sandboxed(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return sys.platform == "darwin" and bool((env.get(licensing.SANDBOX_CONTAINER_ENV) or "").strip())


def has_bookmark(data_dir: Path) -> bool:
    """True when the student has explicitly chosen and saved a download folder bookmark."""
    try:
        raw = json.loads(bookmark_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(raw, dict):
        return False
    if _is_sandboxed():
        return bool(isinstance(raw.get("bookmark"), str) and raw["bookmark"].strip())
    return bool(
        (isinstance(raw.get("bookmark"), str) and raw["bookmark"].strip())
        or (isinstance(raw.get("path"), str) and raw["path"].strip())
    )


def _create_bookmark_bytes(path: Path, nsurl: object | None = None, *, sandboxed: bool | None = None) -> bytes | None:
    if sys.platform != "darwin":
        return None
    import Foundation

    is_sbx = _is_sandboxed() if sandboxed is None else sandboxed
    url = nsurl if nsurl is not None else Foundation.NSURL.fileURLWithPath_(str(path))
    data, error = url.bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(
        Foundation.NSURLBookmarkCreationWithSecurityScope, None, None, None
    )
    if data is not None:
        return bytes(data)
    if is_sbx:
        raise OSError(f"Could not create security-scoped bookmark for {path}: {error}")
    # Unsandboxed developer run / test: plain bookmark exercises NSURL resolution without kernel entitlement.
    data, _err = url.bookmarkDataWithOptions_includingResourceValuesForKeys_relativeToURL_error_(
        0, None, None, None
    )
    return bytes(data) if data is not None else None


def _resolve_bookmark_bytes(raw_bytes: bytes, *, sandboxed: bool | None = None) -> tuple[Path, object, bool, bool]:
    """Return ``(resolved_path, nsurl, is_stale, security_scoped)``."""
    import Foundation

    is_sbx = _is_sandboxed() if sandboxed is None else sandboxed
    ns_data = Foundation.NSData.dataWithBytes_length_(raw_bytes, len(raw_bytes))
    url, stale, error = Foundation.NSURL.URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(
        ns_data, Foundation.NSURLBookmarkResolutionWithSecurityScope, None, None, None
    )
    if url is not None and url.path():
        return Path(str(url.path())), url, bool(stale), True
    if is_sbx:
        raise OSError(f"Could not resolve security-scoped bookmark: {error}")
    url, stale, error = Foundation.NSURL.URLByResolvingBookmarkData_options_relativeToURL_bookmarkDataIsStale_error_(
        ns_data, 0, None, None, None
    )
    if url is None or not url.path():
        raise OSError(f"Could not resolve bookmark: {error}")
    return Path(str(url.path())), url, bool(stale), False


def _start_access(path: Path, nsurl: object | None, security_scoped: bool) -> bool:
    key = os.path.normpath(str(path))
    with _lock:
        if key in _active_urls:
            return True
        started = False
        if nsurl is not None and hasattr(nsurl, "startAccessingSecurityScopedResource"):
            started = bool(nsurl.startAccessingSecurityScopedResource())
            if security_scoped and _is_sandboxed() and not started:
                return False
        _active_urls[key] = (nsurl, started)
        return True


def save_bookmark(
    data_dir: Path,
    path: Path,
    nsurl: object | None = None,
    *,
    sandboxed: bool | None = None,
) -> Path:
    """Persist a security-scoped bookmark for ``path`` and start accessing it."""
    resolved_path = Path(os.path.normpath(path.expanduser()))
    raw_bytes = _create_bookmark_bytes(resolved_path, nsurl=nsurl, sandboxed=sandboxed)
    payload: dict[str, str] = {"path": str(resolved_path)}
    if raw_bytes is not None:
        payload["bookmark"] = base64.b64encode(raw_bytes).decode("ascii")
    make_private_dir(data_dir)
    write_private_json(bookmark_path(data_dir), payload)

    # Resolve and start accessing the freshly saved bookmark so this process holds the scope.
    if raw_bytes is not None and sys.platform == "darwin":
        try:
            target_path, resolved_url, _stale, scoped = _resolve_bookmark_bytes(raw_bytes, sandboxed=sandboxed)
            _start_access(target_path, resolved_url, scoped)
            return target_path
        except OSError:
            if _is_sandboxed() if sandboxed is None else sandboxed:
                raise
    _start_access(resolved_path, nsurl, False)
    return resolved_path


def activate_saved_bookmark(
    data_dir: Path,
    *,
    sandboxed: bool | None = None,
) -> Path | None:
    """Resolve the saved bookmark on launch (refreshing it if stale) and start accessing it.

    Returns the resolved folder ``Path`` when access is active, or ``None`` when no
    bookmark exists or macOS refused access.
    """
    is_sbx = _is_sandboxed() if sandboxed is None else sandboxed
    try:
        data = json.loads(bookmark_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    encoded = data.get("bookmark")
    if isinstance(encoded, str) and encoded.strip() and sys.platform == "darwin":
        try:
            raw_bytes = base64.b64decode(encoded)
            resolved_path, nsurl, is_stale, scoped = _resolve_bookmark_bytes(raw_bytes, sandboxed=is_sbx)
        except (OSError, ValueError) as exc:
            log.warning("Could not resolve saved folder bookmark: %s", exc)
            return None
        if not _start_access(resolved_path, nsurl, scoped):
            log.warning("macOS denied security-scoped access to %s", resolved_path)
            return None
        if is_stale:
            try:
                save_bookmark(data_dir, resolved_path, nsurl=nsurl, sandboxed=is_sbx)
            except OSError as exc:
                log.warning("Could not refresh stale folder bookmark: %s", exc)
        return resolved_path
    if is_sbx:
        return None
    saved_path = data.get("path")
    if isinstance(saved_path, str) and saved_path.strip():
        resolved_path = Path(os.path.normpath(saved_path))
        _start_access(resolved_path, None, False)
        return resolved_path
    return None


def release_except(keep: Path | None = None) -> None:
    """Stop accessing any active security-scoped folders other than ``keep``."""
    keep_key = os.path.normpath(str(keep)) if keep is not None else None
    with _lock:
        keys = [k for k in _active_urls if k != keep_key]
        released = [_active_urls.pop(k) for k in keys]
    for nsurl, started in released:
        if started and nsurl is not None and hasattr(nsurl, "stopAccessingSecurityScopedResource"):
            with contextlib.suppress(Exception):
                nsurl.stopAccessingSecurityScopedResource()


def release_all() -> None:
    """Stop accessing all security-scoped folders held by this process."""
    release_except(None)


def is_active(path: Path) -> bool:
    """True when ``path`` currently has active security-scoped access in this process."""
    key = os.path.normpath(str(path))
    with _lock:
        return key in _active_urls


@contextlib.contextmanager
def scoped_folder_access(
    data_dir: Path,
    *,
    require: bool = True,
    env: Mapping[str, str] | None = None,
) -> Iterator[Path | None]:
    """Activate the saved folder bookmark for the duration of a CLI command in ``mas`` builds."""
    if not licensing.is_mas(env=env):
        yield None
        return
    resolved = activate_saved_bookmark(data_dir)
    if resolved is None and require:
        raise BlackboardSyncError(tr("Choose the folder to save the files in."))
    try:
        yield resolved
    finally:
        release_all()
