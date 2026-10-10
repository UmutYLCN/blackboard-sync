"""The main window's decisions: sections, the overview, the unsaved-changes bar, when it opens."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync.deleted import MissingOutput
from blackboard_sync.menubar.main_window_model import (
    DELETED,
    GENERAL,
    OVERVIEW,
    T_CONNECTED,
    T_EXPIRED,
    T_NAV_OVERVIEW,
    T_NAV_START,
    T_NEVER_SYNCED,
    T_SIGNED_OUT,
    T_SYNC_RUNNING,
    T_WAITING,
    WindowState,
    day_time,
    deleted_detail,
    has_changes,
    is_first_run,
    last_sync_text,
    main_status,
    recent_count,
    reopen_hint,
    shows_window_at_launch,
)
from blackboard_sync.menubar.model import AppModel, RecentItem, RunOutcome
from blackboard_sync.menubar.settings_form import FormValues

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
DEST = Path("/Users/student/Documents")
FINISHED = NOW - timedelta(minutes=20)


def signed_in(model, name="UMUT YALÇIN"):
    model.session = {"saved_at": NOW.timestamp(), "user": {"displayName": name}}
    return model


def synced(**kwargs):
    return signed_in(AppModel(DEST, NOW, last=RunOutcome("ok", finished_at=FINISHED), **kwargs))


def test_day_time_names_today_and_yesterday_in_local_time():
    local = NOW.astimezone()
    assert day_time(NOW, NOW) == f"bugün {local:%H:%M}"
    assert day_time(NOW - timedelta(days=1), NOW) == f"dün {(NOW - timedelta(days=1)).astimezone():%H:%M}"
    older = NOW - timedelta(days=9)
    assert day_time(older, NOW) == f"{older.astimezone():%d.%m.%Y %H:%M}"


def test_first_run_until_set_up_and_signed_in_or_synced_once():
    assert is_first_run(AppModel(DEST, NOW, configured=False))
    # Saved settings but nobody ever signed in: still the first-run steps.
    assert is_first_run(AppModel(DEST, NOW))
    # Signed in from the terminal before saving the window: the form must still be saved.
    assert is_first_run(signed_in(AppModel(DEST, NOW, configured=False)))
    assert not is_first_run(signed_in(AppModel(DEST, NOW)))
    # Signed out (or expired) after syncing: the overview with "Giriş yap", not the steps again.
    assert not is_first_run(AppModel(DEST, NOW, last=RunOutcome("ok", finished_at=FINISHED)))
    assert not is_first_run(AppModel(DEST, NOW, session_expired=True))


def test_the_first_section_is_called_baslangic_until_the_first_sign_in():
    status = main_status(AppModel(DEST, NOW, configured=False), NOW)
    assert status.first_run and status.overview_title == T_NAV_START
    assert (status.start_title, status.start_login, status.start_enabled) == ("Giriş yap", True, True)
    status = main_status(synced(), NOW)
    assert not status.first_run and status.overview_title == T_NAV_OVERVIEW


def test_baslangic_only_saves_when_already_signed_in():
    status = main_status(signed_in(AppModel(DEST, NOW, configured=False)), NOW)
    assert (status.start_title, status.start_login) == ("Kaydet", False)


def test_baslangic_says_where_to_sign_in_while_waiting():
    model = AppModel(DEST, NOW, configured=False)
    model.begin("login")
    model.login_method = "Google Chrome"
    status = main_status(model, NOW)
    assert status.start_title == "Giriş bekleniyor…" and not status.start_enabled
    assert status.start_message == "Google Chrome penceresinde giriş yapmanız bekleniyor…"
    assert status.account.title == T_WAITING


def test_signed_in_card_shows_the_last_sync_once():
    status = main_status(synced(), NOW)
    card = status.account
    assert (card.initials, card.title, card.badge) == ("UY", "UMUT YALÇIN", T_CONNECTED)
    assert card.detail == last_sync_text(synced(), NOW) == f"Son senkron: {day_time(FINISHED, NOW)}"
    assert not card.warning and not card.action_title
    assert status.sync_title == "Şimdi senkronize et" and status.sync_enabled


@pytest.mark.parametrize("job", ["sync", "refetch", "past_term", "move"])
def test_while_syncing_the_card_keeps_the_last_sync_time(job):
    model = synced()
    model.begin(job)
    card = main_status(model, NOW).account
    assert card.badge == T_SYNC_RUNNING
    assert card.detail == f"Son senkron: {day_time(FINISHED, NOW)}"
    assert "pencereyi kapatabilirsiniz" not in card.detail
    status = main_status(model, NOW)
    assert not status.sync_enabled
    assert status.sync_title == ("Senkronize ediliyor…" if job == "sync" else "Şimdi senkronize et")


def test_never_synced_and_failed_runs_are_named_honestly():
    model = signed_in(AppModel(DEST, NOW))
    assert last_sync_text(model, NOW) == T_NEVER_SYNCED
    model.last = RunOutcome("error", message="Blackboard'a ulaşılamadı", finished_at=FINISHED)
    card = main_status(model, NOW).account
    assert card.detail == f"Son deneme: {day_time(FINISHED, NOW)}"
    assert card.warning and card.message == "Senkron tamamlanamadı: Blackboard'a ulaşılamadı"
    assert card.badge == ""


def test_expired_or_signed_out_card_offers_sign_in_and_keeps_sync_off():
    model = AppModel(DEST, NOW, last=RunOutcome("login_required", finished_at=FINISHED), session_expired=True)
    status = main_status(model, NOW)
    assert (status.account.title, status.account.action_title) == (T_EXPIRED, "Giriş yap")
    assert status.account.warning and status.account.action_enabled and not status.sync_enabled
    model = AppModel(DEST, NOW, last=RunOutcome("ok", finished_at=FINISHED))
    card = main_status(model, NOW).account
    assert (card.title, card.initials, card.detail) == (T_SIGNED_OUT, "!", f"Son senkron: {day_time(FINISHED, NOW)}")
    model.begin("sync")
    assert not main_status(model, NOW).account.action_enabled


def test_a_note_shows_in_the_card():
    model = synced()
    model.note = "Dosya bulunamadı."
    assert main_status(model, NOW).account.message == "Dosya bulunamadı."


def test_recent_rows_name_the_file_course_and_day():
    at = (NOW - timedelta(days=1)).isoformat()
    model = synced(recent=[RecentItem("2026-2027 Güz/SWE305 Web/Homework1.docx", "SWE305", at),
                           RecentItem("2026-2027 Güz/CSE301/Duyurular/Quiz", "CSE301", "bad")])
    rows = main_status(model, NOW).recent
    assert [(r.name, r.detail, r.kind) for r in rows] == [
        ("Homework1.docx", f"SWE305 · {day_time(NOW - timedelta(days=1), NOW)}", "DOCX"),
        ("Quiz", "CSE301", ""),
    ]
    assert rows[0].path == "2026-2027 Güz/SWE305 Web/Homework1.docx"
    assert recent_count(rows) == "2 dosya" and recent_count(()) == ""


def test_deleted_row_shows_its_folder_once():
    row = MissingOutput("k", "T/C/W/a.pdf", "T", "C", "a.pdf", "2026-2027 Güz/CSE301 Algorithms/Week 3")
    assert deleted_detail(row) == "2026-2027 Güz · CSE301 Algorithms · Week 3"


def test_the_save_bar_appears_only_after_a_change():
    saved = FormValues("https://bb.example.edu", "~/Documents", True)
    assert not has_changes(saved, FormValues("https://bb.example.edu", "~/Documents", True))
    assert has_changes(saved, FormValues("https://bb.example.edu", "~/Belgeler", True))
    assert has_changes(saved, FormValues("https://bb.example.edu", "~/Documents", True, sync_interval_minutes=30))
    assert has_changes(saved, FormValues("https://bb.example.edu", "~/Documents", False))


def test_only_a_quiet_start_skips_the_window():
    assert shows_window_at_launch(background=False, configured=True)
    assert not shows_window_at_launch(background=True, configured=True)
    assert shows_window_at_launch(background=True, configured=False)  # nothing syncs before setting up


def test_window_state_reopens_on_the_overview_and_keeps_the_open_section():
    state = WindowState()
    assert not state.open
    assert state.show() == OVERVIEW and state.open
    state.select(DELETED)
    assert state.show() == DELETED  # started again while open: stays where it is
    assert state.show(GENERAL) == GENERAL  # "Ayarlar…"
    state.closed()
    assert not state.open
    assert state.show() == OVERVIEW  # opened again after closing
    with pytest.raises(ValueError):
        state.select("tabs")


def test_reopen_hint_names_the_platforms_launcher():
    assert "Applications veya Launchpad'den" in reopen_hint("Applications veya Launchpad'den")
    assert reopen_hint("Başlat menüsünden").startswith("Bu pencereyi kapatabilirsiniz.")
