"""Presentation and post-sync decisions remain independent of AppKit and Google."""
from datetime import datetime, timezone

import pytest

from blackboard_sync import gcal
from blackboard_sync.config import Config
from blackboard_sync.errors import CalendarAuthExpired
from blackboard_sync.menubar import jobs, settings_form as form
from blackboard_sync.menubar.main_window_model import attention_items
from blackboard_sync.menubar.model import AppModel, RunOutcome

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize('status,title,button', [
    (gcal.CalendarStatus(), 'Not connected', 'Connect Google Calendar'),
    (gcal.CalendarStatus(True), 'Connected', ''),
    (gcal.CalendarStatus(True, last_error='Revoked', needs_reconnect=True),
     'Google Calendar needs to be reconnected', 'Reconnect'),
    (gcal.CalendarStatus(True, last_error='Offline'), 'Google Calendar error', 'Reconnect'),
])
def test_presentation(status, title, button):
    value = form.calendar_presentation(status)
    assert (value.title, value.button) == (title, button)
    assert value.warning == bool(status.last_error)
    assert form.calendar_presentation(status, 'connect').button == 'Cancel'
    assert form.calendar_presentation(status, 'connect').enabled
    assert not form.calendar_presentation(status, 'sync').enabled


def test_last_sync_and_immediate_controls(tmp_path):
    model = AppModel(tmp_path, NOW)
    model.calendar = gcal.CalendarStatus(True, last_sync=NOW.isoformat())
    status = form.window_status(model)
    rows = form.row_states(status)
    assert NOW.astimezone().strftime('%Y-%m-%d %H:%M') in rows['google_calendar'].detail
    assert 'T00:' not in rows['google_calendar'].detail
    assert rows['google_calendar_sync'].enabled
    assert rows['google_calendar_disconnect'].enabled
    model.paused = True
    assert not form.row_states(form.window_status(model))['google_calendar_sync'].enabled
    assert all(not row.field for row in form.SECTIONS[form.SECTION_CALENDAR].rows)


@pytest.mark.parametrize('connected,paused,outcome,reconnect,expected', [
    (True, False, 'ok', False, True),
    (False, False, 'ok', False, False),
    (True, True, 'ok', False, False),
    (True, False, 'error', False, False),
    (True, False, 'paused', False, False),
    (True, False, 'ok', True, False),
])
def test_post_sync_hook(tmp_path, monkeypatch, connected, paused, outcome, reconnect, expected):
    config = Config(data_dir=tmp_path)
    monkeypatch.setattr(gcal, 'status', lambda _: gcal.CalendarStatus(connected, needs_reconnect=reconnect))
    model = AppModel(tmp_path, NOW)
    model.paused = paused
    result = RunOutcome(status=outcome)
    assert jobs.calendar_after_sync(config, model, result) == expected
    assert result.status == outcome
    assert model.calendar_busy == ('sync' if expected else None)
    if expected:
        assert not jobs.calendar_after_sync(config, model, result)  # one worker at a time


@pytest.mark.parametrize('error', [CalendarAuthExpired(), RuntimeError('internal detail')])
def test_calendar_error_never_fails_blackboard(tmp_path, monkeypatch, error):
    config = Config(data_dir=tmp_path)
    monkeypatch.setattr(gcal, 'status', lambda _: gcal.CalendarStatus(True))
    calls = []
    def perform(config, action, **options):
        calls.append(action)
        raise error
    monkeypatch.setattr(gcal, 'perform', perform)
    blackboard = RunOutcome(status='ok')
    result = jobs.run_calendar_guarded(config)
    assert result.last_error
    assert result.needs_reconnect == isinstance(error, CalendarAuthExpired)
    assert blackboard.status == 'ok'
    assert calls == ['sync']


def test_reconnect_attention_has_settings_action(tmp_path):
    model = AppModel(tmp_path, NOW, last=RunOutcome(status='ok', finished_at=NOW),
                     session={'user': {'displayName': 'Student'}})
    model.calendar = gcal.CalendarStatus(True, last_error='revoked', needs_reconnect=True)
    item = next(item for item in attention_items(model) if item.action == 'calendar_settings')
    assert item.title == 'Google Calendar needs to be reconnected'
    assert item.action_title == 'Reconnect'
    model.calendar = gcal.CalendarStatus()
    assert not any(item.action == 'calendar_settings' for item in attention_items(model))


def test_calendar_card_keeps_one_action_group_for_each_connection_state():
    disconnected = form.calendar_presentation(gcal.CalendarStatus())
    assert disconnected.show_connect
    assert not disconnected.show_sync and not disconnected.show_disconnect
    connected = form.calendar_presentation(gcal.CalendarStatus(True))
    assert not connected.show_connect
    assert connected.show_sync and connected.show_disconnect
    assert connected.sync_enabled and connected.disconnect_enabled
    expired = form.calendar_presentation(gcal.CalendarStatus(True, needs_reconnect=True))
    assert expired.show_connect and expired.show_disconnect and not expired.show_sync
    for busy in ('sync', 'disconnect'):
        waiting = form.calendar_presentation(gcal.CalendarStatus(True), busy)
        assert not waiting.show_connect
        assert not waiting.sync_enabled and not waiting.disconnect_enabled
    authorization = form.calendar_presentation(gcal.CalendarStatus(), 'connect')
    assert authorization.show_connect and authorization.button == 'Cancel'
