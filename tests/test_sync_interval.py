"""The automatic sync interval chosen in the settings window (30 min / 1 h / 3 h / by hand)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import (
    FIRST_SYNC_DELAY,
    RETRY_DELAY,
    SYNC_INTERVAL,
    AppModel,
    RunOutcome,
    format_time,
)
from blackboard_sync.menubar.settings_form import (
    INTERVAL_OPTIONS,
    FormValues,
    initial_values,
    submit,
)
from blackboard_sync.settings import (
    SYNC_INTERVAL_CHOICES,
    Settings,
    load_settings,
    save_settings,
    settings_path,
)

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
DEST = Path.home() / "Documents" / "University"  # absolute on every OS
SCHOOL = "https://blackboard.istun.edu.tr"


def model(minutes, **kwargs):
    return AppModel(dest=DEST, now=NOW, sync_interval_minutes=minutes, **kwargs)


def result(status="ok", at=NOW, message=""):
    return RunOutcome(status=status, finished_at=at, message=message)


def finish(m, status="ok", at=NOW):
    assert m.begin("sync")
    return m.finish_sync(result(status, at), at)


# -- Settings ---------------------------------------------------------------------

def test_default_is_one_hour_and_round_trips(tmp_path):
    assert Settings(SCHOOL, DEST).sync_interval_minutes == 60
    for minutes in SYNC_INTERVAL_CHOICES:
        save_settings(tmp_path, Settings(SCHOOL, DEST, sync_interval_minutes=minutes))
        assert load_settings(tmp_path).sync_interval_minutes == minutes


def test_old_settings_file_without_the_field_keeps_one_hour(tmp_path):
    settings_path(tmp_path).write_text(json.dumps({"base_url": SCHOOL, "dest": str(DEST)}), encoding="utf-8")
    loaded = load_settings(tmp_path)
    assert loaded is not None and loaded.sync_interval_minutes == 60


@pytest.mark.parametrize("bad", [None, "30", 15, -1, 61, 3.5, True, [], "manual"])
def test_invalid_interval_falls_back_to_one_hour(tmp_path, bad):
    data = {"base_url": SCHOOL, "dest": str(DEST), "sync_interval_minutes": bad}
    settings_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    assert load_settings(tmp_path).sync_interval_minutes == 60


def test_manual_mode_is_zero_and_survives_a_reload(tmp_path):
    save_settings(tmp_path, Settings(SCHOOL, DEST, sync_interval_minutes=0))
    assert load_settings(tmp_path).sync_interval_minutes == 0


def test_the_menu_offers_30_60_180_and_by_hand_only():
    assert [m for m, _ in INTERVAL_OPTIONS] == [30, 60, 180, 0]
    assert [t for _, t in INTERVAL_OPTIONS][-1] == "Yalnızca elle"


# -- form -------------------------------------------------------------------------

def test_form_prefills_and_submits_the_interval(tmp_path):
    current = Settings(SCHOOL, tmp_path, sync_interval_minutes=180)
    values = initial_values(current, current, autostart=False)
    assert values.sync_interval_minutes == 180
    values.sync_interval_minutes = 30
    result_ = submit(values, current)
    assert result_.settings.sync_interval_minutes == 30 and result_.interval_changed
    assert not submit(initial_values(current, current, False), current).interval_changed


def test_form_without_the_field_keeps_the_default_and_bad_values_are_normalised(tmp_path):
    current = Settings(SCHOOL, tmp_path)
    assert submit(FormValues(SCHOOL, str(tmp_path), False), current).settings.sync_interval_minutes == 60
    values = FormValues(SCHOOL, str(tmp_path), False, sync_interval_minutes=7)
    assert submit(values, current).settings.sync_interval_minutes == 60


def test_load_model_uses_the_saved_interval(tmp_path):
    from blackboard_sync.config import Config

    config = Config(data_dir=tmp_path / "data", base_url=SCHOOL, dest=tmp_path / "University")
    save_settings(config.data_dir, Settings(SCHOOL, tmp_path / "University", sync_interval_minutes=180))
    assert jobs.load_model(config, NOW, autostart=False).sync_interval == timedelta(hours=3)
    save_settings(config.data_dir, Settings(SCHOOL, tmp_path / "University", sync_interval_minutes=0))
    assert jobs.load_model(config, NOW, autostart=False).sync_interval is None


# -- scheduling -------------------------------------------------------------------

def test_default_model_keeps_the_hourly_schedule():
    m = AppModel(dest=DEST, now=NOW)
    assert m.sync_interval == SYNC_INTERVAL == timedelta(hours=1)
    assert m.next_run_at == NOW + FIRST_SYNC_DELAY


@pytest.mark.parametrize("minutes", [30, 60, 180])
def test_each_interval_schedules_the_next_run_after_a_sync(minutes):
    m = model(minutes)
    assert m.due(NOW + FIRST_SYNC_DELAY)
    finish(m, at=NOW + FIRST_SYNC_DELAY)
    interval = timedelta(minutes=minutes)
    start = NOW + FIRST_SYNC_DELAY
    assert m.next_run_at == start + interval
    assert not m.due(start + interval - timedelta(seconds=1))
    assert m.due(start + interval)


def test_login_required_waits_one_interval_like_before():
    m = model(180)
    finish(m, "login_required")
    assert m.next_run_at == NOW + timedelta(hours=3)


@pytest.mark.parametrize("minutes, expected", [(30, RETRY_DELAY), (60, RETRY_DELAY), (180, RETRY_DELAY)])
def test_retry_is_ten_minutes_for_the_listed_intervals(minutes, expected):
    m = model(minutes)
    finish(m, "error")
    assert m.next_run_at == NOW + expected
    finish(m, "locked")
    assert m.next_run_at == NOW + expected


def test_retry_is_capped_at_the_interval():
    m = model(60)
    m.sync_interval = timedelta(minutes=5)  # only reachable in tests: every real choice is >= 30 min
    assert m.retry_delay == timedelta(minutes=5)
    finish(m, "error")
    assert m.next_run_at == NOW + timedelta(minutes=5)


def test_manual_mode_never_syncs_by_itself():
    m = model(0)
    assert m.sync_interval is None and m.next_run_at is None
    assert not m.due(NOW + timedelta(days=30))
    finish(m, "ok", NOW)
    assert m.next_run_at is None and not m.due(NOW + timedelta(days=30))


@pytest.mark.parametrize("status", ["error", "locked", "login_required"])
def test_manual_mode_has_no_automatic_retry(status):
    m = model(0)
    finish(m, status)
    assert m.next_run_at is None and m.retry_delay is None
    assert not m.due(NOW + timedelta(days=1))


def test_manual_sync_still_works_in_manual_mode():
    m = model(0)
    assert m.begin("sync")
    assert not m.begin("sync")
    m.finish_sync(result(), NOW)
    assert m.begin("sync")


def test_signing_in_does_not_start_an_automatic_sync_in_manual_mode():
    m = model(0)
    m.busy = "login"
    m.finish_login(True, "", NOW)
    assert not m.due(NOW + timedelta(days=1))


# -- changing the interval --------------------------------------------------------

def test_changing_the_interval_recomputes_from_the_last_sync():
    m = model(60)
    finish(m, at=NOW)
    later = NOW + timedelta(minutes=10)
    m.apply_settings(DEST, False, sync_interval_minutes=180, now=later)
    assert m.sync_interval == timedelta(hours=3)
    assert m.next_run_at == NOW + timedelta(hours=3)
    m.apply_settings(DEST, False, sync_interval_minutes=30, now=later)
    assert m.next_run_at == NOW + timedelta(minutes=30)


def test_an_overdue_result_runs_thirty_seconds_later_not_immediately():
    m = model(180)
    finish(m, at=NOW)
    later = NOW + timedelta(hours=2)  # 3 h -> 30 min: last + 30 min is long past
    m.apply_settings(DEST, False, sync_interval_minutes=30, now=later)
    assert m.next_run_at == later + FIRST_SYNC_DELAY
    assert not m.due(later)
    assert m.due(later + FIRST_SYNC_DELAY)


def test_changing_the_interval_before_any_sync_keeps_the_start_delay():
    m = model(60)
    m.apply_settings(DEST, False, sync_interval_minutes=30, now=NOW + timedelta(minutes=5))
    assert m.next_run_at == NOW + timedelta(minutes=5) + FIRST_SYNC_DELAY


def test_after_an_error_the_retry_delay_is_kept_for_the_new_interval():
    m = model(180)
    finish(m, "error", NOW)
    m.apply_settings(DEST, False, sync_interval_minutes=60, now=NOW + timedelta(minutes=1))
    assert m.next_run_at == NOW + RETRY_DELAY


def test_switching_to_manual_and_back():
    m = model(60)
    finish(m, at=NOW)
    m.apply_settings(DEST, False, sync_interval_minutes=0, now=NOW)
    assert m.next_run_at is None and not m.due(NOW + timedelta(days=2))
    m.apply_settings(DEST, False, sync_interval_minutes=60, now=NOW + timedelta(hours=5))
    assert m.next_run_at == NOW + timedelta(hours=5) + FIRST_SYNC_DELAY


def test_saving_with_the_same_interval_leaves_the_schedule_alone():
    m = model(60)
    finish(m, at=NOW)
    before = m.next_run_at
    m.apply_settings(DEST, False, sync_interval_minutes=60, now=NOW + timedelta(minutes=20))
    m.apply_settings(DEST, False)
    assert m.next_run_at == before


def test_a_finished_run_uses_the_interval_in_force_at_that_moment():
    m = model(60)
    assert m.begin("sync")
    m.apply_settings(DEST, False, sync_interval_minutes=180, now=NOW)  # changed while syncing
    m.finish_sync(result(at=NOW + timedelta(minutes=1)), NOW + timedelta(minutes=1))
    assert m.next_run_at == NOW + timedelta(minutes=1, hours=3)


# -- text -------------------------------------------------------------------------

def test_next_run_text_is_the_absolute_clock_time_for_every_interval():
    for minutes in (30, 60, 180):
        m = model(minutes)
        finish(m, at=NOW)
        expected = f"sonraki: {format_time(NOW + timedelta(minutes=minutes), NOW)}"
        assert m.detail(NOW)[-1] == expected


def test_overdue_run_still_says_birazdan():
    m = model(60)
    finish(m, at=NOW)
    assert m.detail(NOW + timedelta(hours=2))[-1] == "sonraki: birazdan"


def test_manual_mode_says_automatic_sync_is_off_and_puts_the_sync_button_first():
    m = model(0, session={"saved_at": 9e9, "user": {"displayName": "Ada"}})
    finish(m, at=NOW)
    lines = m.status_lines(NOW)
    assert lines[0] == f"✓ Ada · {format_time(NOW, NOW)} senkronize edildi"
    assert lines[1].endswith("otomatik senkron kapalı")
    assert not any("sonraki" in line for line in lines)
    entries = m.menu(NOW).entries
    assert entries[0].action == "sync" and entries[0].title == "Şimdi senkronize et" and entries[0].enabled


def test_automatic_modes_keep_the_menu_layout():
    entries = model(60).menu(NOW).entries
    assert [e.action for e in entries if e.action == "sync"] == ["sync"]
    assert entries[0].action != "sync"


def test_manual_mode_text_is_constant_over_time_so_the_menu_is_not_rebuilt():
    m = model(0)
    finish(m, at=NOW)
    assert m.detail(NOW)[-1] == m.detail(NOW + timedelta(hours=9))[-1] == "otomatik senkron kapalı"
