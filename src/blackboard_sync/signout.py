"""Full sign-out: remove the saved session and every bit of login data the app owns.

The identity provider's "stay signed in" cookies live in the sign-in browser's
profile (``browser-profile``), the Windows sign-in window's WebView2 storage
(``inapp-profile``) and, on macOS, the sign-in window's WebKit website data
store. Deleting only ``session.json`` would let the next sign-in reopen the same
account silently, so all of them go. Downloaded files, settings and sync state
are never touched, and only paths directly inside the app's data directory are
ever deleted.
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

from blackboard_sync.config import Config

log = logging.getLogger("blackboard_sync.signout")

LOCKED_WARNING = (
    "Giriş verilerinin bir kısmı silinemedi; açık kalan giriş tarayıcısını kapatıp "
    "tekrar çıkış yapın."
)
RETRIES = 3
RETRY_DELAY = 0.3


def login_data_dirs(config: Config) -> list[Path]:
    """The browser data directories sign-out removes (all inside the data directory)."""
    return [config.profile_dir, config.inapp_profile_dir]


def _inside(path: Path, root: Path) -> bool:
    return path.parent == root and path.name not in ("", ".", "..")


def _remove_tree(path: Path, sleep=time.sleep) -> bool:
    """Delete ``path`` (a link is unlinked, never followed); False if it would not go."""
    for attempt in range(RETRIES):
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            log.warning("could not remove %s: %s", path, exc)
            if attempt < RETRIES - 1:
                sleep(RETRY_DELAY)  # a browser that is still closing releases its files
    return not (path.is_symlink() or path.exists())


def clear_webkit_data() -> None:
    """Ask WebKit to forget everything its default store holds for this app (macOS).

    The store lives under ``~/Library/WebKit/<bundle id>``, owned by WebKit, so
    it is cleared through its API instead of by deleting files.
    """
    if sys.platform != "darwin":
        return
    from Foundation import NSDate
    from WebKit import WKWebsiteDataStore

    store = WKWebsiteDataStore.defaultDataStore()
    store.removeDataOfTypes_modifiedSince_completionHandler_(
        WKWebsiteDataStore.allWebsiteDataTypes(), NSDate.distantPast(), lambda: None
    )


def sign_out(config: Config, clear_web=None, sleep=time.sleep) -> list[str]:
    """Remove the session file and all login browser data; returns warnings.

    A failure to remove the session file raises ``OSError`` (the account would
    still be signed in); leftovers that are locked by a still-running sign-in
    browser come back as a warning after everything else was removed.
    """
    config.session_file.unlink(missing_ok=True)
    warnings: list[str] = []
    for path in login_data_dirs(config):
        if _inside(path, config.data_dir) and not _remove_tree(path, sleep):
            warnings.append(LOCKED_WARNING)
    try:
        (clear_web or clear_webkit_data)()
    except Exception as exc:  # WebKit unavailable: the rest is already gone
        log.warning("could not clear WebKit data: %s", exc)
        warnings.append(LOCKED_WARNING)
    return list(dict.fromkeys(warnings))
