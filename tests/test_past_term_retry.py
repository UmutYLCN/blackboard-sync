"""Eski dönemler: a lookup that met a running sync tries again, and a download shows its progress."""

from datetime import datetime, timedelta, timezone

from blackboard_sync.menubar.model import PAST_RETRY_DELAYS, AppModel, RunOutcome
from blackboard_sync.menubar.settings_form import T_PAST_DOWNLOAD, T_PAST_DOWNLOADING, window_status

NOW = datetime(2026, 10, 16, 18, 30, tzinfo=timezone.utc)
PAST = "2025-2026 Bahar"
SESSION = {"saved_at": NOW.timestamp(), "user": {"displayName": "Ada"}}


def signed_in(tmp_path):
    return AppModel(tmp_path, NOW, session=SESSION)


def lookup(model, names, outcome, now=NOW):
    assert model.begin("past_terms")
    model.finish_past_terms(names, outcome, now)


def test_a_lookup_that_met_a_running_sync_is_tried_again_by_itself(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {}, RunOutcome("locked"))

    assert not model.past_terms_loaded
    assert not model.past_terms_due(NOW + timedelta(seconds=5))
    wait = PAST_RETRY_DELAYS["locked"]
    assert model.past_terms_due(NOW + wait)

    lookup(model, {PAST: "_t1_1"}, RunOutcome("ok"), NOW + wait)
    assert model.past_terms_loaded and model.past_terms_retry_at is None
    assert not model.past_terms_due(NOW + wait * 10)
    status = window_status(model)
    assert status.past_terms == (PAST,) and status.past_enabled and status.past_message == ""


def test_while_waiting_the_window_says_why_instead_of_loading_forever(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {}, RunOutcome("locked"))
    status = window_status(model)
    assert status.past_message == "Başka bir senkron sürüyor; eski dönemler birazdan yeniden yüklenecek."
    assert not status.past_enabled and not status.past_running


def test_a_failed_lookup_waits_longer_and_a_sign_in_request_does_not_loop(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {}, RunOutcome("error", message="Blackboard yanıt vermedi"))
    assert not model.past_terms_due(NOW + PAST_RETRY_DELAYS["locked"])
    assert model.past_terms_due(NOW + PAST_RETRY_DELAYS["error"])

    again = signed_in(tmp_path)
    lookup(again, {}, RunOutcome("login_required"))
    assert again.past_terms_loaded and not again.past_terms_due(NOW + timedelta(hours=1))


def test_reopening_the_window_looks_up_at_once_even_while_waiting(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {}, RunOutcome("locked"))
    model.reload_past_terms()
    assert model.past_terms_due(NOW)


def test_the_list_cannot_be_used_while_the_lookup_is_waiting(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {}, RunOutcome("locked"))
    assert not model.can_download_past_term and not model.select_past_term(PAST)


def test_a_running_download_locks_the_list_and_the_button_says_so(tmp_path):
    model = signed_in(tmp_path)
    lookup(model, {PAST: "_t1_1"}, RunOutcome("ok"))
    idle = window_status(model)
    assert idle.past_enabled and not idle.past_running and T_PAST_DOWNLOAD != T_PAST_DOWNLOADING

    assert model.select_past_term(PAST) and model.begin("past_term")
    running = window_status(model)
    assert running.past_running and not running.past_enabled
    assert PAST in running.past_message and "indiriliyor" in running.past_message
    assert not model.select_past_term(PAST)  # no second download on top of it

    model.finish_sync(RunOutcome("ok", past_term=PAST), NOW)
    assert not window_status(model).past_running
