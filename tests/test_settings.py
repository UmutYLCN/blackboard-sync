import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync import cli
from blackboard_sync.config import DEFAULT_BASE_URL, DEFAULT_DEST, Config
from blackboard_sync.menubar.model import AppModel, RecentItem, RunOutcome
from blackboard_sync.menubar.settings_form import FormValues, initial_values, submit
from blackboard_sync.settings import (
    Settings,
    SettingsError,
    display_path,
    load_settings,
    normalize_base_url,
    normalize_dest,
    save_settings,
)

from .conftest import assert_owner_only

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
HOME = Path.home()
ISTUN = Settings("https://blackboard.istun.edu.tr", HOME / "Documents" / "Okul")


# -- validation ---------------------------------------------------------------

@pytest.mark.parametrize(
    "typed, expected",
    [
        ("https://blackboard.istun.edu.tr", "https://blackboard.istun.edu.tr"),
        ("  https://Blackboard.Istun.edu.tr/  ", "https://blackboard.istun.edu.tr"),
        ("blackboard.okul.edu.tr", "https://blackboard.okul.edu.tr"),
        ("https://lms.okul.edu.tr/ultra/course?x=1", "https://lms.okul.edu.tr"),
        ("https://lms.okul.edu.tr:8443/", "https://lms.okul.edu.tr:8443"),
    ],
)
def test_school_address_is_reduced_to_the_https_host(typed, expected):
    assert normalize_base_url(typed) == expected


@pytest.mark.parametrize(
    "typed",
    ["", "   ", "http://blackboard.istun.edu.tr", "ftp://x.edu", "https://localhost", "https://bb .edu",
     "https://user@bb.edu", "https://bb.edu:99999"],
)
def test_bad_school_address_is_refused_in_turkish(typed):
    with pytest.raises(SettingsError) as info:
        normalize_base_url(typed)
    assert info.value.field == "base_url"
    assert str(info.value)  # a message the window can show


def test_http_gets_a_specific_message():
    with pytest.raises(SettingsError, match="https://"):
        normalize_base_url("http://blackboard.istun.edu.tr")


def test_destination_folder(tmp_path):
    assert normalize_dest("~/Documents/Okul/") == HOME / "Documents" / "Okul"
    assert normalize_dest(str(tmp_path / "new" / ".." / "Okul")) == tmp_path / "Okul"  # may not exist yet
    (tmp_path / "file.pdf").write_bytes(b"x")
    for bad in ("", "Okul", str(tmp_path / "file.pdf")):
        with pytest.raises(SettingsError) as info:
            normalize_dest(bad)
        assert info.value.field == "dest"


@pytest.mark.skipif(sys.platform == "win32", reason="macOS settings window shows POSIX paths")
def test_display_path_uses_tilde():
    assert display_path(Path("/Users/me/Documents/Okul"), home=Path("/Users/me")) == "~/Documents/Okul"
    assert display_path(Path("/Volumes/USB/Okul"), home=Path("/Users/me")) == "/Volumes/USB/Okul"


# -- the settings file --------------------------------------------------------

def test_settings_round_trip_privately(tmp_path):
    data_dir = tmp_path / "data"
    assert load_settings(data_dir) is None
    path = save_settings(data_dir, Settings("https://bb.example.edu", tmp_path / "Okul"))
    assert path == data_dir / "settings.json"
    assert_owner_only(path)
    assert load_settings(data_dir) == Settings("https://bb.example.edu", tmp_path / "Okul")


def test_broken_settings_file_counts_as_not_saved(tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    assert load_settings(tmp_path) is None
    (tmp_path / "settings.json").write_text('{"base_url": "http://insecure.edu", "dest": "/x"}')
    assert load_settings(tmp_path) is None


def test_config_reads_saved_settings_and_env_still_wins(tmp_path):
    assert Config.from_env({"BBSYNC_DATA_DIR": str(tmp_path)}).base_url == DEFAULT_BASE_URL
    assert Config.from_env({"BBSYNC_DATA_DIR": str(tmp_path)}).dest == DEFAULT_DEST
    save_settings(tmp_path, Settings("https://bb.example.edu", tmp_path / "Okul"))
    config = Config.from_env({"BBSYNC_DATA_DIR": str(tmp_path)})
    assert (config.base_url, config.dest) == ("https://bb.example.edu", tmp_path / "Okul")
    env = {"BBSYNC_DATA_DIR": str(tmp_path), "BBSYNC_BASE_URL": "https://other.edu", "BBSYNC_DEST": "/tmp/x"}
    config = Config.from_env(env)
    assert (config.base_url, config.dest) == ("https://other.edu", Path("/tmp/x"))


def test_cli_reads_the_settings_of_its_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("BBSYNC_BASE_URL", raising=False)
    monkeypatch.delenv("BBSYNC_DEST", raising=False)
    save_settings(tmp_path, Settings("https://bb.example.edu", tmp_path / "Okul"))
    args = cli.build_parser().parse_args(["--data-dir", str(tmp_path), "sync"])
    config = cli.make_config(args)
    assert (config.base_url, config.dest, config.data_dir) == ("https://bb.example.edu", tmp_path / "Okul", tmp_path)
    args = cli.build_parser().parse_args(
        ["--data-dir", str(tmp_path), "--base-url", "https://x.edu/", "sync", "--dest", str(tmp_path / "B")]
    )
    config = cli.make_config(args)
    assert (config.base_url, config.dest) == ("https://x.edu", tmp_path / "B")


# -- the settings window's form -----------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="macOS settings window shows POSIX paths")
def test_first_launch_is_prefilled_with_the_defaults_and_autostart():
    values = initial_values(None, ISTUN, autostart=False)
    assert values == FormValues("https://blackboard.istun.edu.tr", "~/Documents/Okul", autostart=True)


@pytest.mark.skipif(sys.platform == "win32", reason="macOS settings window shows POSIX paths")
def test_later_the_window_shows_what_was_saved():
    saved = Settings("https://bb.example.edu", Path("/Volumes/USB/Okul"))
    assert initial_values(saved, saved, autostart=False) == FormValues(
        "https://bb.example.edu", "/Volumes/USB/Okul", autostart=False
    )


def test_unchanged_settings_need_no_new_sign_in():
    result = submit(FormValues("blackboard.istun.edu.tr/", "~/Documents/Okul", True), ISTUN)
    assert result.settings == ISTUN
    assert not result.school_changed and not result.dest_changed
    assert result.needs_login(login_pressed=False) is False
    assert result.needs_login(login_pressed=True) is True


def test_another_school_requires_signing_in_again():
    result = submit(FormValues("https://lms.other.edu.tr", "~/Documents/Okul", False), ISTUN)
    assert result.school_changed and result.needs_login(login_pressed=False)
    assert result.autostart is False


def test_new_folder_is_reported_but_not_a_new_sign_in(tmp_path):
    result = submit(FormValues(ISTUN.base_url, str(tmp_path / "Dersler"), True), ISTUN)
    assert result.dest_changed and not result.needs_login(login_pressed=False)


def test_invalid_input_names_the_field():
    with pytest.raises(SettingsError) as info:
        submit(FormValues("http://x.edu", "~/Okul", True), ISTUN)
    assert info.value.field == "base_url"
    with pytest.raises(SettingsError) as info:
        submit(FormValues(ISTUN.base_url, "Okul", True), ISTUN)
    assert info.value.field == "dest"


# -- what saving does to the app ----------------------------------------------

def test_nothing_syncs_on_schedule_before_the_first_save():
    m = AppModel(dest=ISTUN.dest, now=NOW, configured=False)
    later = NOW + timedelta(hours=2)
    assert not m.due(later)
    assert "Ayarlar" in m.status_lines(later)[0]
    assert not any(line.startswith("Sonraki senkron") for line in m.status_lines(later))
    m.apply_settings(ISTUN.dest, school_changed=False)
    assert m.due(later)


def test_new_folder_restarts_recent_list_and_keeps_old_files_alone():
    m = AppModel(dest=ISTUN.dest, now=NOW, recent=[RecentItem("a.pdf", "CSE303", NOW.isoformat())])
    m.apply_settings(ISTUN.dest, school_changed=False)
    assert len(m.recent) == 1
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False)
    assert m.dest == Path("/Volumes/USB/Okul") and m.recent == []


def test_new_school_forgets_the_old_result():
    m = AppModel(dest=ISTUN.dest, now=NOW, last=RunOutcome(status="ok", finished_at=NOW), login_prompted=True)
    m.apply_settings(ISTUN.dest, school_changed=True)
    assert m.last is None and m.login_prompted is False
    assert "giriş" in m.note
