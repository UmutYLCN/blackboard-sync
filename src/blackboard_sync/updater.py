"""Finding, downloading and starting a newer release of the app; no GUI code.

The app asks GitHub for the latest release of this repository, compares its
tag with ``__version__`` and picks the installer for this platform by name.
The release workflow (``.github/workflows/release.yml``) publishes exactly
these asset names; changing one side means changing the other:

- macOS:   ``Blackboard-Sync-<version>.dmg``
- Windows: ``Blackboard-Sync-<version>-Setup.exe`` (an Inno Setup installer)
- both:    ``SHA256SUMS.txt``, one ``<sha256>  <asset name>`` line per installer

Only HTTPS downloads from this repository's releases are accepted, and when a
release carries ``SHA256SUMS.txt`` the installer must match its line. Every
network or server problem (offline, private repository, rate limit) only
means "no update information": checking never raises.

macOS: ``update_macos`` verifies the app on the .dmg and swaps it in place of
the running one, then restarts it; where it cannot (an unsigned app, a folder
it cannot write, ...) the .dmg is opened and the student drags the new app
over the old one. Windows: the installer runs silently and restarts the app,
after the tray app has quit.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from blackboard_sync import __version__

log = logging.getLogger(__name__)

REPO = "UmutYLCN/blackboard-sync"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
# browser_download_url of every asset of this repository's releases.
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
CHECKSUMS_ASSET = "SHA256SUMS.txt"
USER_AGENT = f"blackboard-sync/{__version__} (update check)"
CHECK_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 60
CHUNK = 1 << 16
# Inno Setup: no wizard, no message boxes, no reboot; the installer restarts the app.
WINDOWS_INSTALLER_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")

# Stands in for ``requests.get`` (tests pass a fake).
Getter = Callable[..., requests.Response]


class UpdateError(Exception):
    """A download that must not be installed; the message is Turkish, for the student."""


@dataclass(frozen=True)
class Release:
    """A newer release that has an installer for this platform."""

    version: str
    page_url: str
    asset_name: str
    asset_url: str
    asset_size: int | None = None
    checksums_url: str | None = None

    def to_dict(self) -> dict:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: dict) -> "Release":
        return cls(**data)


@dataclass(frozen=True)
class CheckResult:
    status: str  # "available" | "current" | "unknown" (offline, private, rate limited, ...)
    release: Release | None = None


def parse_version(text: str) -> tuple[int, int, int] | None:
    """``"v1.2.3"`` or ``"1.2.3"`` -> ``(1, 2, 3)``; anything else (pre-releases too) -> None."""
    match = _VERSION.fullmatch((text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    return new is not None and old is not None and new > old


def asset_name(version: str, platform: str | None = None) -> str | None:
    """The installer this platform downloads; None where there is none (e.g. Linux)."""
    platform = platform or sys.platform
    if platform == "darwin":
        return f"Blackboard-Sync-{version}.dmg"
    if platform == "win32":
        return f"Blackboard-Sync-{version}-Setup.exe"
    return None


def is_trusted_url(url: str | None) -> bool:
    return bool(url) and url.startswith(DOWNLOAD_PREFIX) and ".." not in url


def parse_release(data: dict, current: str = __version__, platform: str | None = None) -> CheckResult:
    """Interpret the ``releases/latest`` API answer."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return CheckResult("current")
    tag = str(data.get("tag_name") or "")
    version = parse_version(tag)
    if version is None or not is_newer(tag, current):
        return CheckResult("current")
    version_text = ".".join(map(str, version))
    wanted = asset_name(version_text, platform)
    assets = {
        a.get("name"): a for a in data.get("assets") or [] if isinstance(a, dict)
    }
    asset = assets.get(wanted)
    if asset is None or not is_trusted_url(asset.get("browser_download_url")):
        # A newer release without an installer for this platform (yet).
        return CheckResult("current")
    checksums = assets.get(CHECKSUMS_ASSET)
    checksums_url = checksums.get("browser_download_url") if checksums else None
    size = asset.get("size")
    page_url = str(data.get("html_url") or "")
    return CheckResult(
        "available",
        Release(
            version=version_text,
            page_url=page_url if page_url.startswith(f"https://github.com/{REPO}/") else RELEASES_URL,
            asset_name=wanted,
            asset_url=asset["browser_download_url"],
            asset_size=size if isinstance(size, int) and size > 0 else None,
            checksums_url=checksums_url,
        ),
    )


def _get(url: str, **kwargs) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    return requests.get(url, headers=headers, **kwargs)


def check(current: str = __version__, platform: str | None = None, get: Getter = _get) -> CheckResult:
    """Ask GitHub whether a newer release exists; never raises."""
    try:
        resp = get(
            LATEST_RELEASE_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=CHECK_TIMEOUT,
        )
        try:
            if resp.status_code != 200:
                # 404: no release yet or a private repository; 403/429: rate limited.
                log.info("update check: HTTP %s", resp.status_code)
                return CheckResult("unknown")
            data = resp.json()
        finally:
            resp.close()
    except (requests.RequestException, ValueError) as exc:
        log.info("update check failed: %s", exc)
        return CheckResult("unknown")
    return parse_release(data, current, platform)


def parse_checksums(text: str) -> dict[str, str]:
    """``sha256sum``/``shasum -a 256`` output -> {file name: lowercase hex digest}."""
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and _SHA256.fullmatch(parts[0]):
            sums[parts[1].strip().lstrip("*")] = parts[0].lower()
    return sums


def expected_checksum(release: Release, get: Getter = _get) -> str | None:
    """The installer's SHA-256 from the release's SHA256SUMS.txt; None when it has none."""
    if release.checksums_url is None:
        return None
    if not is_trusted_url(release.checksums_url):
        raise UpdateError("Güncelleme doğrulanamadı.")
    try:
        resp = get(release.checksums_url, timeout=CHECK_TIMEOUT)
        try:
            if resp.status_code != 200:
                raise UpdateError("Güncelleme doğrulanamadı.")
            text = resp.text
        finally:
            resp.close()
    except requests.RequestException as exc:
        raise UpdateError("Güncelleme indirilemedi; internet bağlantınızı kontrol edin.") from exc
    digest = parse_checksums(text).get(release.asset_name)
    if digest is None:
        # The checksum file is the release's integrity contract: an installer it
        # does not list is not installed.
        raise UpdateError("Güncelleme doğrulanamadı.")
    return digest


def download_dir(platform: str | None = None, home: Path | None = None) -> Path:
    """macOS: the Downloads folder, where the student sees the .dmg. Windows: a temp folder."""
    platform = platform or sys.platform
    if platform == "darwin":
        return (home or Path.home()) / "Downloads"
    return Path(tempfile.gettempdir()) / "blackboard-sync-update"


def download(release: Release, folder: Path, get: Getter = _get) -> Path:
    """Download and verify the installer into ``folder``; raises ``UpdateError``.

    The file only appears under its final name once it is complete and its
    checksum (when the release publishes one) matches.
    """
    if not is_trusted_url(release.asset_url) or Path(release.asset_name).name != release.asset_name:
        raise UpdateError("Güncelleme bu uygulamanın sayfasından gelmiyor; indirilmedi.")
    expected = expected_checksum(release, get)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / release.asset_name
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        resp = get(release.asset_url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        try:
            # Assets redirect to GitHub's storage; never accept a non-HTTPS hop.
            if resp.status_code != 200 or not str(resp.url).startswith("https://"):
                raise UpdateError("Güncelleme indirilemedi.")
            with open(partial, "wb") as fh:
                for chunk in resp.iter_content(CHUNK):
                    fh.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        finally:
            resp.close()
    except requests.RequestException as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("Güncelleme indirilemedi; internet bağlantınızı kontrol edin.") from exc
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if (release.asset_size is not None and size != release.asset_size) or (
        expected is not None and digest.hexdigest() != expected
    ):
        partial.unlink(missing_ok=True)
        raise UpdateError("İndirilen güncelleme doğrulanamadı; yüklenmedi.")
    os.replace(partial, target)
    log.info("downloaded %s (%d bytes, sha256 %s)", target, size, digest.hexdigest())
    return target


def open_disk_image(path: Path, popen: Callable[..., object] = subprocess.Popen) -> None:
    """macOS: mount the .dmg; Finder shows the app next to the Applications link."""
    popen(["open", str(path)], stdin=subprocess.DEVNULL)


def installer_command(path: Path) -> list[str]:
    return [str(path), *WINDOWS_INSTALLER_ARGS]


def launch_installer(path: Path, popen: Callable[..., object] = subprocess.Popen) -> None:
    """Windows: start the silent installer detached; the caller quits right after.

    The installer waits for nothing from this process, replaces the app once it
    has exited and starts it again.
    """
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen(installer_command(path), stdin=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def install_windows_update(release: Release, get: Getter = _get, popen: Callable[..., object] = subprocess.Popen) -> None:
    """Windows tray app's "Güncelle": download, verify, start the silent installer.

    Raises ``UpdateError`` when nothing was started; on success the caller
    quits at once so the installer can replace the running app.
    """
    launch_installer(download(release, download_dir("win32"), get), popen)
