"""Teslim tarihi hatırlatmaları, hafta/ay takvimi ve yeniden başlatmada kalıcı taşıma işi."""

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


# -- week and month ---------------------------------------------------------------

def page_with(tmp_path, *items):
    return deadlines.calendar_page(state_with(tmp_path, *items), tmp_path, NOW, ISTANBUL)


def test_week_starts_on_monday_and_holds_that_days_due_dates(tmp_path):
    page = page_with(tmp_path, item("a", datetime(2026, 10, 14, 7, 30, tzinfo=timezone.utc)),
                     item("b", datetime(2026, 10, 14, 5, 0, tzinfo=timezone.utc), "Sınav"))
    grid = deadlines.grid_page(page, deadlines.VIEW_WEEK, date(2026, 10, 16), date(2026, 10, 13))
    assert grid.title == "12 – 18 Ekim 2026" and len(grid.weeks) == 1
    days = grid.weeks[0]
    assert [d.number for d in days] == ["12", "13", "14", "15", "16", "17", "18"]
    assert [d.today for d in days] == [False, True, False, False, False, False, False]
    assert [r.title for r in days[2].rows] == ["Sınav", "Ödev"]  # earliest first
    assert all(not d.rows for i, d in enumerate(days) if i != 2)


def test_elapsed_and_upcoming_dates_of_one_day_share_a_cell(tmp_path):
    page = page_with(tmp_path, item("a", NOW - timedelta(hours=1)), item("b", NOW + timedelta(hours=1)))
    cell = next(d for d in deadlines.grid_page(page, deadlines.VIEW_WEEK, NOW.date(), NOW.date()).weeks[0]
                if d.day == NOW.date())
    assert len(cell.rows) == 2


def test_month_fills_whole_weeks_and_marks_the_neighbouring_months(tmp_path):
    grid = deadlines.grid_page(page_with(tmp_path), deadlines.VIEW_MONTH, date(2026, 10, 20), date(2026, 10, 13))
    assert grid.title == "Ekim 2026" and grid.weekdays[0] == "Pzt"
    assert len(grid.weeks) == 5 and all(len(week) == 7 for week in grid.weeks)
    assert grid.weeks[0][0].day == date(2026, 9, 28) and grid.weeks[0][0].outside
    assert not grid.weeks[0][3].outside and grid.weeks[0][3].number == "1"
    assert grid.weeks[-1][-1].day == date(2026, 11, 1) and grid.weeks[-1][-1].outside


def test_month_lengths_and_year_boundaries(tmp_path):
    page = page_with(tmp_path)
    february = deadlines.grid_page(page, deadlines.VIEW_MONTH, date(2026, 2, 10), date(2026, 2, 10))
    assert len(february.weeks) == 5 and february.weeks[-1][-1].day == date(2026, 3, 1)
    december = deadlines.grid_page(page, deadlines.VIEW_MONTH, date(2026, 12, 5), date(2026, 12, 5))
    assert december.title == "Aralık 2026" and december.weeks[-1][-1].day == date(2027, 1, 3)
    across = deadlines.grid_page(page, deadlines.VIEW_WEEK, date(2026, 12, 30), date(2026, 12, 30))
    assert across.title == "28 Ara 2026 – 3 Oca 2027"


def test_stepping_moves_by_week_or_month(tmp_path):
    assert deadlines.shift_anchor(date(2026, 10, 16), deadlines.VIEW_WEEK, 1) == date(2026, 10, 23)
    assert deadlines.shift_anchor(date(2026, 10, 16), deadlines.VIEW_WEEK, -3) == date(2026, 9, 25)
    assert deadlines.shift_anchor(date(2026, 12, 31), deadlines.VIEW_MONTH, 1) == date(2027, 1, 1)
    assert deadlines.shift_anchor(date(2026, 1, 31), deadlines.VIEW_MONTH, -1) == date(2025, 12, 1)


def test_an_empty_calendar_still_draws_and_keeps_the_hint(tmp_path):
    grid = deadlines.grid_page(deadlines.DeadlinePage(), deadlines.VIEW_MONTH, date(2026, 10, 1), date(2026, 10, 1))
    assert grid.message == deadlines.T_NOT_SYNCED
    assert sum(len(day.rows) for week in grid.weeks for day in week) == 0


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


# -- the Windows window draws the views ---------------------------------------------

def test_windows_calendar_switches_between_list_week_and_month(monkeypatch, tmp_path):
    from tests.test_windows import fake_tk
    from blackboard_sync.menubar.main_window_model import CALENDAR, main_status
    from blackboard_sync.menubar.settings_form import FormValues
    from blackboard_sync.windows.main_window import MainWindow

    widgets = fake_tk(monkeypatch, tmp_path)
    today = datetime.now().astimezone().date()
    due = datetime.now(timezone.utc) + timedelta(days=1)
    page = deadlines.calendar_page(state_with(tmp_path, item("a", due, "Proje")), tmp_path, datetime.now(timezone.utc))
    opened = []
    window = MainWindow(None, FormValues("https://school.edu", str(tmp_path), True),
                        main_status(AppModel(tmp_path, NOW), NOW), lambda *_: None, lambda *_: None, lambda: None,
                        on_deadlines=lambda: page, on_deadline=opened.append)
    window.select(CALENDAR)
    assert window.calendar_mode.get() == deadlines.VIEW_LIST

    window.calendar_mode.set(deadlines.VIEW_WEEK)
    window.refresh_calendar()
    def alive(w):  # the fake does not destroy a destroyed widget's children
        while w is not None and hasattr(w, "destroyed"):
            if w.destroyed:
                return False
            w = w.parent
        return True

    live = [w for w in widgets if alive(w)]
    assert sum(1 for w in live if w.options.get("text") == "Proje" and "command" in w.options) == 1
    assert window.calendar_title.options["text"] == deadlines.grid_page(page, "week", today, today).title

    window.calendar_mode.set(deadlines.VIEW_MONTH)
    window.refresh_calendar()
    assert window.calendar_title.options["text"] == deadlines.grid_page(page, "month", today, today).title
    window._calendar_step(1)
    assert window.calendar_anchor == deadlines.shift_anchor(today, "month", 1)
    window._calendar_open_week(today)
    assert window.calendar_mode.get() == deadlines.VIEW_WEEK and window.calendar_anchor == today
    window._calendar_today()
    assert window.calendar_anchor is None
