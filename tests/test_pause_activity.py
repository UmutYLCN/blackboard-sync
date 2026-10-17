"""Duraklat, Sync activity and the Notifications page: the model and the sync child process behind them."""

import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.main_window_model import (
    STATE_ATTENTION, STATE_ERROR, STATE_PAUSED, STATE_SYNCED, STATE_SYNCING, attention_items, format_size, main_status,
)
from blackboard_sync.menubar.model import (
    ACTIVITY_LIMIT, NOTICE_LIMIT, AppModel, Icon, Notification, RunOutcome, T_PAUSE, T_RESUME,
)
from blackboard_sync.settings import Settings, save_settings

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SESSION = {"saved_at": NOW.timestamp(), "user": {"displayName": "Ada Student"}}


def signed_in(tmp_path, **kwargs):
    return AppModel(tmp_path, NOW, configured=True, session=SESSION,
                    last=RunOutcome("ok", finished_at=NOW), **kwargs)


# -- Duraklat -----------------------------------------------------------------------

def test_pausing_stops_the_schedule_and_resuming_syncs_at_once(tmp_path):
    model = signed_in(tmp_path)
    model.next_run_at = NOW - timedelta(minutes=1)
    assert model.due(NOW)
    model.pause()
    assert not model.due(NOW) and model.icon() == Icon.PAUSED and model.activity() == "Duraklatıldı"
    model.resume(NOW)
    assert not model.paused and model.due(NOW)


def test_a_queued_download_waits_while_paused_but_a_move_does_not(tmp_path):
    model = signed_in(tmp_path)
    model.pending = "sync"
    model.pause()
    assert model.pending_job() is None
    model.pending = "move"
    assert model.pending_job() == "move"
    model.pending = "sync"
    model.resume(NOW)
    assert model.pending_job() == "sync"


def test_the_menu_offers_pause_and_resume_and_sync_now_waits(tmp_path):
    model = signed_in(tmp_path)
    entries = {e.action: e for e in model.menu(NOW).entries if e.action}
    assert entries["pause"].title == T_PAUSE and entries["sync"].enabled
    model.pause()
    entries = {e.action: e for e in model.menu(NOW).entries if e.action}
    assert entries["pause"].title == T_RESUME and not entries["sync"].enabled


def test_a_stopped_sync_changes_nothing_but_frees_the_slot(tmp_path):
    model = signed_in(tmp_path)
    scheduled, last = model.next_run_at, model.last
    assert model.begin("sync")
    model.pause()
    assert model.finish_sync(RunOutcome("paused", finished_at=NOW), NOW) == []
    assert model.busy is None and model.last is last and model.next_run_at == scheduled and model.note == ""


def test_a_stopped_past_term_download_says_so(tmp_path):
    model = signed_in(tmp_path)
    model.past_terms, model.past_term_ids = ["2025-2026 Bahar"], {"2025-2026 Bahar": "_t_1"}
    model.past_terms_loaded = True
    assert model.select_past_term("2025-2026 Bahar") and model.begin("past_term")
    model.finish_sync(RunOutcome("paused", finished_at=NOW), NOW)
    assert model.busy is None and model.past_term == "" and "duraklatıldı" in model.past_message


def test_the_pause_survives_a_restart(tmp_path):
    config = Config(base_url="https://school.edu", dest=tmp_path / "University", data_dir=tmp_path / "data")
    save_settings(config.data_dir, Settings("https://school.edu", config.dest))
    model = signed_in(tmp_path)
    model.pause()
    jobs.save_model(config, model)
    assert jobs.load_model(config, NOW, False).paused
    model.resume(NOW)
    jobs.save_model(config, model)
    assert not jobs.load_model(config, NOW, False).paused


# -- stopping the child process ------------------------------------------------------

def test_stop_sync_ends_a_running_child_and_reports_paused(monkeypatch):
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    monkeypatch.setattr(jobs, "cli_command", lambda *args, **kw: sleeper)
    result = []
    worker = threading.Thread(target=lambda: result.append(jobs.run_sync("sync", Settings("https://s.edu", Path("/x")))))
    worker.start()
    for _ in range(100):  # wait until the child is up
        if jobs._running is not None:
            break
        time.sleep(0.05)
    assert jobs.stop_sync() is True
    worker.join(10)
    assert not worker.is_alive()
    assert result[0].status == "paused"
    assert jobs.stop_sync() is False  # nothing runs any more


def test_a_child_that_finishes_on_its_own_is_not_reported_as_paused(monkeypatch):
    script = "import json; print(json.dumps({'status': 'ok', 'courses': []}))"
    monkeypatch.setattr(jobs, "cli_command", lambda *args, **kw: [sys.executable, "-c", script])
    outcome = jobs.run_sync("sync", Settings("https://s.edu", Path("/x")))
    assert outcome.status == "ok"
    assert jobs.stop_sync() is False


# -- Sync activity -------------------------------------------------------------------

def outcome_with(*entries):
    return RunOutcome("ok", finished_at=NOW, entries=list(entries))


def test_a_sync_adds_what_it_brought_to_the_activity_with_sizes(tmp_path):
    root = tmp_path / "University"
    (root / "CSE301").mkdir(parents=True)
    (root / "CSE301" / "week1.pdf").write_bytes(b"x" * 2048)
    model = signed_in(tmp_path)
    model.begin("sync")
    model.finish_sync(outcome_with(("CSE301", "CSE301/week1.pdf", "new_file"), ("CSE301", "CSE301/n.md", "new_note")), NOW)
    rows = main_status(model, NOW).activity
    assert [(r.name, r.status, r.size) for r in rows] == [
        ("week1.pdf", "Başarıyla indirildi", "2.0 KB"), ("n.md", "Not kaydedildi", "—")]
    assert rows[0].course == "CSE301" and rows[0].kind == "PDF"


def test_activity_is_newest_first_capped_and_hides_unticked_courses(tmp_path):
    model = signed_in(tmp_path)
    for n in range(3):
        model.begin("sync")
        model.finish_sync(outcome_with(("C", f"C/f{n}.pdf", "new_file")), NOW + timedelta(minutes=n))
    assert [i.path for i in model.activity_log] == ["C/f2.pdf", "C/f1.pdf", "C/f0.pdf"]
    model.hidden_folders = ("C",)
    assert model.visible_activity() == []
    model.hidden_folders = ()
    model.activity_log = model.activity_log * (ACTIVITY_LIMIT // 2)
    model.begin("sync")
    model.finish_sync(outcome_with(("C", "C/new.pdf", "updated_file")), NOW)
    assert len(model.activity_log) == ACTIVITY_LIMIT and model.activity_log[0].label == "Güncellendi"


def test_activity_and_notices_survive_a_restart_and_bad_entries_are_dropped(tmp_path):
    config = Config(base_url="https://school.edu", dest=tmp_path / "University", data_dir=tmp_path / "data")
    save_settings(config.data_dir, Settings("https://school.edu", config.dest))
    model = signed_in(tmp_path)
    model.begin("sync")
    model.finish_sync(outcome_with(("C", "C/a.pdf", "new_file")), NOW)
    model.log_notice(Notification("Başlık", "İleti", {}), NOW)
    saved = model.saved_state()
    saved["activity"].append({"path": "broken"})
    saved["notices"].append("junk")
    jobs.write_private_json(jobs.menubar_state_file(config), saved)
    restored = jobs.load_model(config, NOW, False)
    assert [i.path for i in restored.activity_log] == ["C/a.pdf"]
    assert [(n.title, n.message) for n in restored.notices] == [("Başlık", "İleti")]


def test_the_notification_history_keeps_the_newest(tmp_path):
    model = signed_in(tmp_path)
    for n in range(NOTICE_LIMIT + 5):
        model.log_notice(Notification(f"t{n}", "m", {}), NOW)
    assert len(model.notices) == NOTICE_LIMIT and model.notices[0].title == f"t{NOTICE_LIMIT + 4}"
    model.log_notice(Notification("", "", {}), NOW)  # nothing to show: nothing to keep
    assert len(model.notices) == NOTICE_LIMIT


@pytest.mark.parametrize("size, text", [(None, "—"), (0, "0 B"), (900, "900 B"), (1024, "1.0 KB"), (14 * 1024, "14 KB"),
                                        (5 * 1024 * 1024, "5.0 MB"), (3 * 1024**3, "3.0 GB")])
def test_sizes_read_like_drives(size, text):
    assert format_size(size) == text


# -- Home and Notifications -----------------------------------------------------------

def test_home_states(tmp_path):
    model = signed_in(tmp_path)
    home = main_status(model, NOW).home
    assert (home.kind, home.title) == (STATE_SYNCED, "Güncel") and home.detail.startswith("Son senkron: ")
    model.begin("sync")
    assert main_status(model, NOW).home.kind == STATE_SYNCING
    model.busy = None
    model.pause()
    home = main_status(model, NOW).home
    assert (home.kind, home.action, home.action_title) == (STATE_PAUSED, "pause", "Sürdür")
    model.resume(NOW)
    model.session = None
    home = main_status(model, NOW).home
    assert (home.kind, home.action) == (STATE_ATTENTION, "login")
    model.session = SESSION
    model.last = RunOutcome("error", message="Ağ yok", finished_at=NOW)
    home = main_status(model, NOW).home
    assert (home.kind, home.detail) == (STATE_ERROR, "Ağ yok")


def test_attention_lists_only_what_needs_the_student(tmp_path):
    model = signed_in(tmp_path)
    assert attention_items(model) == ()
    model.pause()
    assert attention_items(model) == ()  # a pause is on Home's card, not an alarm
    model.last = RunOutcome("ok", finished_at=NOW, warning_count=3)
    assert [i.title for i in attention_items(model)] == ["3 uyarı"]
    model.last = RunOutcome("ok", finished_at=NOW, unreadable_courses=2, warning_count=3)
    assert [i.title for i in attention_items(model)] == ["2 dersin içeriği okunamadı"]
    model.last = RunOutcome("error", message="Ağ yok", finished_at=NOW)
    assert [(i.title, i.detail) for i in attention_items(model)] == [("Senkron tamamlanamadı", "Ağ yok")]
    model.session, model.session_expired = None, True
    items = attention_items(model)
    assert items[0].title == "Oturum sona erdi" and (items[0].action, items[0].action_title) == ("login", "Giriş yap")


def test_nothing_needs_attention_before_the_first_sign_in(tmp_path):
    assert attention_items(AppModel(tmp_path, NOW, configured=False)) == ()
    assert main_status(AppModel(tmp_path, NOW, configured=False), NOW).pause_enabled is False
