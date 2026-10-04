import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from blackboard_sync import updater
from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import (
    UPDATE_FIRST_DELAY,
    UPDATE_INTERVAL,
    UPDATE_RETRY_DELAY,
    AppModel,
    UpdateState,
)
from blackboard_sync.menubar.settings_form import FormValues, initial_values, submit
from blackboard_sync.settings import Settings, load_settings, save_settings
from blackboard_sync.updater import CheckResult, Release, UpdateError

from .conftest import FakeResponse

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
DOWNLOAD = "https://github.com/UmutYLCN/blackboard-sync/releases/download/v1.1.0/"
DMG = b"fake disk image" * 100
EXE = b"MZ fake installer" * 100


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def asset(name, size=10):
    return {"name": name, "size": size, "browser_download_url": DOWNLOAD + name}


def latest(tag="v1.1.0", assets=None, **extra):
    data = {
        "tag_name": tag,
        "html_url": "https://github.com/UmutYLCN/blackboard-sync/releases/tag/" + tag,
        "draft": False,
        "prerelease": False,
        "assets": assets if assets is not None else [
            asset("Blackboard-Sync-1.1.0.dmg", len(DMG)),
            asset("Blackboard-Sync-1.1.0-Setup.exe", len(EXE)),
            asset("SHA256SUMS.txt"),
        ],
    }
    data.update(extra)
    return data


class FakeGitHub:
    """Stands in for ``requests.get``: URL -> response, or an exception to raise."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        route = self.routes.get(url, FakeResponse(404, url, {"message": "Not Found"}))
        if isinstance(route, Exception):
            raise route
        return route


def text_response(url, text):
    resp = FakeResponse(200, url, content=text.encode())
    resp.text = text
    return resp


def github(release=None, sums=None, dmg=DMG):
    routes = {updater.LATEST_RELEASE_API: FakeResponse(200, updater.LATEST_RELEASE_API, release or latest())}
    if sums is not None:
        routes[DOWNLOAD + "SHA256SUMS.txt"] = text_response(DOWNLOAD + "SHA256SUMS.txt", sums)
    # Assets redirect to GitHub's storage host; the final URL is what counts.
    routes[DOWNLOAD + "Blackboard-Sync-1.1.0.dmg"] = FakeResponse(
        200, "https://objects.githubusercontent.com/x/dmg", content=dmg
    )
    routes[DOWNLOAD + "Blackboard-Sync-1.1.0-Setup.exe"] = FakeResponse(
        200, "https://objects.githubusercontent.com/x/exe", content=EXE
    )
    return FakeGitHub(routes)


SUMS = f"{sha(DMG)}  Blackboard-Sync-1.1.0.dmg\n{sha(EXE)} *Blackboard-Sync-1.1.0-Setup.exe\n"


# -- versions and assets ------------------------------------------------------

@pytest.mark.parametrize(
    "candidate, current, newer",
    [
        ("v1.1.0", "1.0.9", True),
        ("1.10.0", "1.9.0", True),  # numeric, not text order
        ("v0.2.0", "0.1.0", True),
        ("v0.1.0", "0.1.0", False),
        ("v0.0.9", "0.1.0", False),
        ("v2.0.0-beta.1", "0.1.0", False),  # pre-release tags are never offered
        ("latest", "0.1.0", False),
        ("v1.0.0", "1.0.0.dev0", False),  # unknown running version: stay quiet
    ],
)
def test_version_comparison(candidate, current, newer):
    assert updater.is_newer(candidate, current) is newer


def test_asset_name_contract():
    assert updater.asset_name("1.1.0", "darwin") == "Blackboard-Sync-1.1.0.dmg"
    assert updater.asset_name("1.1.0", "win32") == "Blackboard-Sync-1.1.0-Setup.exe"
    assert updater.asset_name("1.1.0", "linux") is None


def test_newer_release_picks_this_platforms_installer():
    mac = updater.check("0.1.0", "darwin", github()).release
    assert mac == Release(
        version="1.1.0",
        page_url="https://github.com/UmutYLCN/blackboard-sync/releases/tag/v1.1.0",
        asset_name="Blackboard-Sync-1.1.0.dmg",
        asset_url=DOWNLOAD + "Blackboard-Sync-1.1.0.dmg",
        asset_size=len(DMG),
        checksums_url=DOWNLOAD + "SHA256SUMS.txt",
    )
    win = updater.check("0.1.0", "win32", github()).release
    assert win.asset_name == "Blackboard-Sync-1.1.0-Setup.exe"


def test_check_is_unauthenticated_with_a_user_agent_and_a_short_timeout(monkeypatch):
    fake = github()
    monkeypatch.setattr(updater.requests, "get", fake)
    updater.check("0.1.0", "darwin")
    url, kwargs = fake.calls[0]
    assert url == "https://api.github.com/repos/UmutYLCN/blackboard-sync/releases/latest"
    assert kwargs["timeout"] <= 10
    assert kwargs["headers"]["User-Agent"].startswith("blackboard-sync/")
    assert "Authorization" not in kwargs["headers"]


@pytest.mark.parametrize(
    "release",
    [
        latest(tag="v0.1.0"),  # same version
        latest(draft=True),
        latest(prerelease=True),
        latest(assets=[asset("Blackboard-Sync-1.1.0-Setup.exe")]),  # no .dmg yet
        latest(assets=[{"name": "Blackboard-Sync-1.1.0.dmg", "browser_download_url": "https://evil.example/x.dmg"}]),
        latest(assets=[{"name": "Blackboard-Sync-1.1.0.dmg", "browser_download_url": "http://github.com/UmutYLCN/"
                        "blackboard-sync/releases/download/v1.1.0/Blackboard-Sync-1.1.0.dmg"}]),
    ],
)
def test_nothing_to_offer(release):
    assert updater.check("0.1.0", "darwin", github(release)) == CheckResult("current")


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(404, updater.LATEST_RELEASE_API, {"message": "Not Found"}),  # private repo, no release
        FakeResponse(403, updater.LATEST_RELEASE_API, {"message": "API rate limit exceeded"}),
        FakeResponse(429, updater.LATEST_RELEASE_API, {}),
        FakeResponse(200, updater.LATEST_RELEASE_API, content=b"<html>"),  # not JSON
        requests.ConnectionError("offline"),
        requests.Timeout("slow"),
    ],
)
def test_offline_private_or_rate_limited_is_no_information(response):
    fake = FakeGitHub({updater.LATEST_RELEASE_API: response})
    assert updater.check("0.1.0", "darwin", fake) == CheckResult("unknown")


# -- download and checksum ----------------------------------------------------

def mac_release(fake):
    return updater.check("0.1.0", "darwin", fake).release


def test_download_verifies_the_checksum(tmp_path):
    fake = github(sums=SUMS)
    path = updater.download(mac_release(fake), tmp_path, fake)
    assert path == tmp_path / "Blackboard-Sync-1.1.0.dmg"
    assert path.read_bytes() == DMG
    assert fake.calls[-1][1]["stream"] is True
    assert list(tmp_path.iterdir()) == [path]


def test_checksum_mismatch_is_refused_and_leaves_nothing(tmp_path):
    fake = github(sums=SUMS, dmg=b"x" * len(DMG))  # same size, other bytes
    with pytest.raises(UpdateError):
        updater.download(mac_release(fake), tmp_path, fake)
    assert list(tmp_path.iterdir()) == []


def test_installer_missing_from_the_checksum_file_is_refused(tmp_path):
    fake = github(sums=f"{sha(EXE)}  Blackboard-Sync-1.1.0-Setup.exe\n")
    with pytest.raises(UpdateError):
        updater.download(mac_release(fake), tmp_path, fake)
    assert not (tmp_path / "Blackboard-Sync-1.1.0.dmg").exists()


def test_unreachable_checksum_file_is_refused(tmp_path):
    fake = github(sums=SUMS)
    fake.routes[DOWNLOAD + "SHA256SUMS.txt"] = requests.ConnectionError("offline")
    with pytest.raises(UpdateError):
        updater.download(mac_release(fake), tmp_path, fake)


def test_release_without_checksum_file_still_checks_the_size(tmp_path):
    release = latest(assets=[asset("Blackboard-Sync-1.1.0.dmg", len(DMG))])
    fake = github(release)
    assert updater.download(mac_release(fake), tmp_path, fake).read_bytes() == DMG
    fake = github(release, dmg=DMG[:-1])
    with pytest.raises(UpdateError):
        updater.download(mac_release(fake), tmp_path / "short", fake)


def test_only_https_downloads_from_this_repository(tmp_path):
    fake = github(sums=SUMS)
    good = mac_release(fake)
    for bad in (
        Release("1.1.0", "", good.asset_name, "https://evil.example/Blackboard-Sync-1.1.0.dmg"),
        Release("1.1.0", "", good.asset_name, "http://github.com/UmutYLCN/blackboard-sync/releases/download/x"),
        Release("1.1.0", "", good.asset_name, DOWNLOAD + "../../../other/x.dmg"),
        Release("1.1.0", "", "../evil.dmg", good.asset_url),
    ):
        with pytest.raises(UpdateError):
            updater.download(bad, tmp_path, fake)
    fake.routes[good.asset_url] = FakeResponse(200, "http://objects.example/x", content=DMG)  # downgraded redirect
    with pytest.raises(UpdateError):
        updater.download(good, tmp_path, fake)
    assert list(tmp_path.iterdir()) == []


def test_interrupted_download_leaves_no_partial_file(tmp_path):
    fake = github(sums=SUMS)
    release = mac_release(fake)

    class Broken(FakeResponse):
        def iter_content(self, chunk_size=1):
            yield DMG[:10]
            raise requests.ConnectionError("reset")

    fake.routes[release.asset_url] = Broken(200, "https://objects.githubusercontent.com/x", content=DMG)
    with pytest.raises(UpdateError):
        updater.download(release, tmp_path, fake)
    assert list(tmp_path.iterdir()) == []


def test_parse_checksums():
    assert updater.parse_checksums(SUMS + "garbage line\n\n") == {
        "Blackboard-Sync-1.1.0.dmg": sha(DMG),
        "Blackboard-Sync-1.1.0-Setup.exe": sha(EXE),
    }


# -- installing ---------------------------------------------------------------

def test_mac_opens_the_disk_image():
    calls = []
    dmg = Path("/Users/me/Downloads/Blackboard-Sync-1.1.0.dmg")
    updater.open_disk_image(dmg, lambda *a, **k: calls.append(a[0]))
    assert calls == [["open", str(dmg)]]


def test_windows_downloads_verifies_and_starts_the_silent_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    fake = github(sums=SUMS)
    release = updater.check("0.1.0", "win32", fake).release
    calls = []
    updater.install_windows_update(release, fake, lambda *a, **k: calls.append(a[0]))
    exe = tmp_path / "blackboard-sync-update" / "Blackboard-Sync-1.1.0-Setup.exe"
    assert exe.read_bytes() == EXE
    assert calls == [[str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]]


def test_windows_mismatch_starts_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    fake = github(sums=SUMS.replace(sha(EXE), "0" * 64))
    release = updater.check("0.1.0", "win32", fake).release
    calls = []
    with pytest.raises(UpdateError):
        updater.install_windows_update(release, fake, lambda *a, **k: calls.append(a))
    assert calls == []


def test_download_folders():
    assert updater.download_dir("darwin", home=Path("/Users/me")) == Path("/Users/me/Downloads")
    assert updater.download_dir("win32").name == "blackboard-sync-update"


# -- schedule, notifications and the menu -------------------------------------

RELEASE = Release("1.1.0", "https://github.com/UmutYLCN/blackboard-sync/releases/tag/v1.1.0",
                  "Blackboard-Sync-1.1.0.dmg", DOWNLOAD + "Blackboard-Sync-1.1.0.dmg")
AVAILABLE = CheckResult("available", RELEASE)


def model(**kwargs):
    return AppModel(dest=Path("/Users/student/Documents/Okul"), now=NOW, **kwargs)


def version_row(m):
    return m.menu(NOW).entries[-2]


def test_checks_once_a_day_after_start_up():
    m = model()
    assert not m.update_due(NOW)  # not right at start-up
    later = NOW + UPDATE_FIRST_DELAY
    assert m.update_due(later)
    assert m.updates.begin("check") and not m.update_due(later)  # one at a time
    m.updates.finish_check(CheckResult("current"), later, manual=False)
    assert not m.update_due(later + UPDATE_INTERVAL - timedelta(minutes=1))
    assert m.update_due(later + UPDATE_INTERVAL)


def test_setting_off_means_no_scheduled_checks():
    m = model(check_updates=False)
    assert not m.update_due(NOW + timedelta(days=30))
    m.apply_settings(m.dest, school_changed=False, check_updates=True)
    assert m.update_due(NOW + timedelta(days=30))
    m.apply_settings(m.dest, school_changed=False, check_updates=False)
    assert not m.update_due(NOW + timedelta(days=30))
    m.apply_settings(m.dest, school_changed=False)  # a caller without the setting keeps it
    assert not m.update_due(NOW + timedelta(days=30))
    # "Güncellemeleri denetle" still works when it is off.
    assert version_row(m).action == "check_updates" and m.updates.begin("check")


def test_one_notification_per_new_version():
    m = model()
    notes = m.updates.finish_check(AVAILABLE, NOW, manual=False)
    assert [n.title for n in notes] == ["Blackboard Sync 1.1.0 hazır — Güncelle"]
    assert notes[0].data == {"action": "update"}
    assert m.updates.finish_check(AVAILABLE, NOW + UPDATE_INTERVAL, manual=False) == []
    newer = CheckResult("available", Release("1.2.0", "", "Blackboard-Sync-1.2.0.dmg", ""))
    assert len(m.updates.finish_check(newer, NOW + 2 * UPDATE_INTERVAL, manual=False)) == 1


def test_failed_check_is_silent_and_retried_sooner():
    m = model()
    assert m.updates.finish_check(CheckResult("unknown"), NOW, manual=False) == []
    assert m.updates.checked_at is None
    assert not m.update_due(NOW + UPDATE_RETRY_DELAY - timedelta(seconds=1))
    assert m.update_due(NOW + UPDATE_RETRY_DELAY)


def test_manual_check_always_answers():
    m = model()
    assert [n.title for n in m.updates.finish_check(CheckResult("current"), NOW, manual=True)] == [
        "Blackboard Sync güncel"
    ]
    assert [n.title for n in m.updates.finish_check(CheckResult("unknown"), NOW, manual=True)] == [
        "Güncellemeler denetlenemedi"
    ]
    m.updates.finish_check(AVAILABLE, NOW, manual=False)
    assert len(m.updates.finish_check(AVAILABLE, NOW, manual=True)) == 1


def test_version_row_follows_the_update_state():
    m = model()
    assert version_row(m).title.endswith("Güncellemeleri denetle")
    m.updates.begin("check")
    assert version_row(m).title == "Güncellemeler denetleniyor…" and not version_row(m).enabled
    m.updates.finish_check(AVAILABLE, NOW, manual=False)
    row = version_row(m)
    assert (row.title, row.action) == ("Güncelleme var: 1.1.0 — Güncelle", "update")
    assert m.updates.begin("download") and not version_row(m).enabled
    assert [n.title for n in m.updates.finish_download("İndirilen güncelleme doğrulanamadı; yüklenmedi.")] == [
        "Güncelleme yüklenemedi"
    ]
    assert version_row(m).action == "update"  # can be tried again
    m.updates.finish_check(CheckResult("current"), NOW, manual=False)
    assert version_row(m).action == "check_updates"


def test_download_needs_a_known_release():
    assert not UpdateState().begin("download")


def test_update_state_survives_a_restart(tmp_path):
    # Ahead of any real version, so the remembered release stays an update.
    ahead = Release("99.0.0", "https://github.com/UmutYLCN/blackboard-sync/releases/tag/v99.0.0",
                    "Blackboard-Sync-99.0.0.dmg", DOWNLOAD + "Blackboard-Sync-99.0.0.dmg")
    config = Config(data_dir=tmp_path / "data", dest=tmp_path / "Okul")
    m = jobs.load_model(config, NOW, autostart=False)
    m.updates.finish_check(CheckResult("available", ahead), NOW, manual=False)
    jobs.save_model(config, m)
    saved = json.loads(jobs.menubar_state_file(config).read_text())["updates"]
    assert saved["notified"] == "99.0.0" and saved["available"]["version"] == "99.0.0"

    restored = jobs.load_model(config, NOW + timedelta(hours=3), autostart=False)
    assert restored.updates.available == ahead
    assert not restored.update_due(NOW + timedelta(hours=5))  # checked today already
    assert restored.updates.finish_check(CheckResult("available", ahead), NOW + UPDATE_INTERVAL, manual=False) == []

    # After installing 99.0.0 the remembered release is no longer an update.
    assert UpdateState.load(saved, NOW, current="99.0.0").available is None
    assert UpdateState.load({"available": {"bad": 1}, "checked_at": "nonsense"}, NOW).available is None


def test_setting_reaches_the_model_on_start(tmp_path):
    config = Config(data_dir=tmp_path / "data", dest=tmp_path / "Okul")
    save_settings(config.data_dir, Settings("https://bb.example.edu", tmp_path / "Okul", check_updates=False))
    assert jobs.load_model(config, NOW, autostart=False).check_updates is False


# -- the setting --------------------------------------------------------------

def test_check_updates_setting_defaults_on_and_round_trips(tmp_path):
    assert Settings("https://bb.example.edu", tmp_path).check_updates is True
    save_settings(tmp_path, Settings("https://bb.example.edu", tmp_path / "Okul", check_updates=False))
    assert load_settings(tmp_path).check_updates is False
    # settings.json from before this option counts as on.
    (tmp_path / "settings.json").write_text(json.dumps({"base_url": "https://bb.example.edu", "dest": str(tmp_path)}))
    assert load_settings(tmp_path).check_updates is True


def test_settings_window_carries_the_checkbox(tmp_path):
    current = Settings("https://bb.example.edu", tmp_path, check_updates=False)
    values = initial_values(current, current, autostart=True)
    assert values.check_updates is False
    values.check_updates = True
    assert submit(values, current).settings.check_updates is True
    # A window that does not know the option yet (three fields) leaves it on.
    assert submit(FormValues("https://bb.example.edu", str(tmp_path), False), current).settings.check_updates is True
