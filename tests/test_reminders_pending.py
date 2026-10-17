"""Teslim tarihi hatırlatmaları ve yeniden başlatmada kalıcı taşıma işi."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from blackboard_sync import deadlines
from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import MOVE_JOB, AppModel
from blackboard_sync.settings import Settings, save_settings
from blackboard_sync.state import State

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
ISTANBUL = ZoneInfo("Europe/Istanbul")


def item(id, due, title="Ödev"):
    return {"id": id, "title": title, "due": due.isoformat(), "content_id": None, "url": "https://school.edu/x"}


def state_with(tmp_path, *items, course="_c1_1"):
    state = State(tmp_path / "state.json")
    state.deadline_courses[course] = {"name": "CSE303 Algorithms", "items": list(items)}
    return state


def remind(state, tmp_path, now, sent=None, hidden=frozenset()):
    return deadlines.due_reminders(state, tmp_path, now, sent or {}, hidden)


# -- reminders --------------------------------------------------------------------

def test_nothing_is_announced_more_than_a_day_ahead(tmp_path):
    state = state_with(tmp_path, item("a", NOW + timedelta(hours=25)))
    reminders, sent = remind(state, tmp_path, NOW)
    assert reminders == [] and sent == {}


def test_a_due_date_is_announced_once_a_day_ahead_and_once_an_hour_ahead(tmp_path):
    due = NOW + timedelta(hours=23)
    state = state_with(tmp_path, item("a", due))

    first, sent = remind(state, tmp_path, NOW)
    assert [(r.stage, r.title) for r in first] == [("24h", "Ödev")]
    again, sent = remind(state, tmp_path, NOW + timedelta(minutes=30), sent)
    assert again == []
    last, sent = remind(state, tmp_path, due - timedelta(minutes=50), sent)
    assert [r.stage for r in last] == ["1h"]
    never, _ = remind(state, tmp_path, due - timedelta(minutes=10), sent)
    assert never == []


def test_reaching_a_date_late_gives_only_the_most_urgent_reminder(tmp_path):
    state = state_with(tmp_path, item("a", NOW + timedelta(minutes=40)))
    reminders, sent = remind(state, tmp_path, NOW)
    assert [r.stage for r in reminders] == ["1h"]
    assert sent["_c1_1:a"]["stages"] == ["1h", "24h"]
    assert remind(state, tmp_path, NOW + timedelta(minutes=1), sent)[0] == []


def test_elapsed_dates_are_never_announced_and_their_records_are_dropped(tmp_path):
    state = state_with(tmp_path, item("a", NOW - timedelta(minutes=5)), item("b", NOW - timedelta(days=3)))
    sent = {"_c1_1:b": {"due": (NOW - timedelta(days=3)).isoformat(), "stages": ["24h"]},
            "gone:x": {"due": NOW.isoformat(), "stages": ["24h"]}}
    reminders, kept = remind(state, tmp_path, NOW, sent)
    assert reminders == [] and "_c1_1:b" not in kept and "gone:x" not in kept


def test_a_moved_due_date_is_announced_again(tmp_path):
    state = state_with(tmp_path, item("a", NOW + timedelta(hours=5)))
    _, sent = remind(state, tmp_path, NOW)
    state = state_with(tmp_path, item("a", NOW + timedelta(hours=20)))
    reminders, _ = remind(state, tmp_path, NOW, sent)
    assert [r.stage for r in reminders] == ["24h"]


def test_unticked_courses_get_no_reminders(tmp_path):
    state = state_with(tmp_path, item("a", NOW + timedelta(hours=5)))
    assert remind(state, tmp_path, NOW, hidden={"_c1_1"}) == ([], {})


def test_reminder_text_names_the_course_the_work_and_the_local_time(tmp_path):
    state = state_with(tmp_path, item("a", datetime(2026, 10, 14, 7, 30, tzinfo=timezone.utc), "Proje"))
    (reminder,), _ = remind(state, tmp_path, NOW)
    title, message = deadlines.reminder_text(reminder, NOW, ISTANBUL)
    assert title == "Teslim tarihi yaklaşıyor"
    assert message == "CSE303 Algorithms: Proje\nSon teslim: 14 Ekim 10:30"
    same_day = deadlines.Reminder("k", "1h", NOW + timedelta(minutes=50), "Proje", "CSE303", "x")
    assert deadlines.reminder_text(same_day, NOW, ISTANBUL)[0] == "Teslime 1 saat kaldı"
    assert deadlines.reminder_text(same_day, NOW, ISTANBUL)[1].endswith("Son teslim: 15:50")


# -- the app's check ----------------------------------------------------------------

def app_model(tmp_path, *items):
    config = Config(base_url="https://school.edu", dest=tmp_path / "University", data_dir=tmp_path / "data")
    save_settings(config.data_dir, Settings("https://school.edu", config.dest))
    state = state_with(tmp_path, *items)
    state.path = config.state_file
    state.dirty = True
    state.save()
    return config, AppModel(config.dest, NOW, configured=True)


def test_check_notifies_once_and_remembers_it_across_a_restart(tmp_path):
    config, model = app_model(tmp_path, item("a", NOW + timedelta(hours=5), "Proje"))

    notes = jobs.check_reminders(config, model, NOW)
    assert [n.title for n in notes] == ["Teslim tarihi yaklaşıyor"]
    assert notes[0].data == {"deadline": "https://school.edu/x"}

    jobs.save_model(config, model)
    restarted = jobs.load_model(config, NOW + timedelta(minutes=10), False)
    assert jobs.check_reminders(config, restarted, NOW + timedelta(minutes=10)) == []


def test_check_looks_only_every_few_minutes_and_only_once_configured(tmp_path):
    config, model = app_model(tmp_path, item("a", NOW + timedelta(hours=5)))
    assert len(jobs.check_reminders(config, model, NOW)) == 1
    model.reminders_sent.clear()
    assert jobs.check_reminders(config, model, NOW + timedelta(minutes=1)) == []
    assert len(jobs.check_reminders(config, model, NOW + jobs.REMINDER_CHECK_EVERY)) == 1
    model.configured = False
    model.reminders_checked_at = None
    assert jobs.check_reminders(config, model, NOW) == []


def test_many_reminders_at_once_become_one_notification(tmp_path):
    items = [item(f"i{n}", NOW + timedelta(hours=2 + n), f"Ödev {n}") for n in range(jobs.REMINDER_GROUP_FROM)]
    config, model = app_model(tmp_path, *items)
    notes = jobs.check_reminders(config, model, NOW)
    assert len(notes) == 1 and notes[0].title == "Yaklaşan teslim tarihleri"
    assert notes[0].message.count("\n") == len(items) - 1


# -- the move that was asked for survives a restart ---------------------------------

def test_a_queued_move_is_still_queued_after_a_restart(tmp_path):
    config = Config(base_url="https://school.edu", dest=tmp_path / "New", data_dir=tmp_path / "data")
    save_settings(config.data_dir, Settings("https://school.edu", config.dest))
    model = AppModel(tmp_path / "Old", NOW, configured=True)
    model.apply_settings(config.dest, False, dest_choice="move")
    jobs.save_model(config, model)

    restarted = jobs.load_model(config, NOW, False)

    assert restarted.pending == MOVE_JOB and restarted.move_from == tmp_path / "Old"
    assert restarted.pending_job() == MOVE_JOB


def test_a_move_cut_short_by_quitting_runs_again(tmp_path):
    model = AppModel(tmp_path / "Old", NOW, configured=True)
    model.apply_settings(tmp_path / "New", False, dest_choice="move")
    assert model.begin(MOVE_JOB) and model.pending is None
    assert model.saved_state()["pending"] == {"job": MOVE_JOB, "move_from": str(tmp_path / "Old")}
    model.finish_move("ok", 3, 0)
    assert model.saved_state()["pending"] is None


def test_a_download_into_the_new_folder_is_queued_too_and_bad_data_is_ignored(tmp_path):
    model = AppModel(tmp_path / "Old", NOW, configured=True)
    model.apply_settings(tmp_path / "New", False, dest_choice="refetch")
    saved = model.saved_state()["pending"]
    fresh = AppModel(tmp_path / "New", NOW, configured=True)
    fresh.restore_pending(saved)
    assert fresh.pending == "sync"
    for junk in (None, "move", {"job": "move"}, {"job": "move", "move_from": 5}, {"job": "bogus"}, []):
        other = AppModel(tmp_path / "New", NOW, configured=True)
        other.restore_pending(junk)
        assert other.pending is None and other.move_from is None

