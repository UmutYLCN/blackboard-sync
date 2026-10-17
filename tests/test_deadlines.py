from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from blackboard_sync import deadlines
from blackboard_sync.errors import ApiError, LoginRequired
from blackboard_sync.menubar.main_window_model import CALENDAR, WindowState, main_status
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.menubar.settings_form import FormValues
from blackboard_sync.state import State
from tests.test_sync import sync

COURSE = "_13004_1"
ROOT = f"/learn/api/public/v2/courses/{COURSE}/gradebook/columns"
NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def column(id="_grade_1", due="2026-10-13T22:30:00Z", **fields):
    return {"id": id, "name": "Ödev 1", "grading": {"due": due}, "contentId": "_c4_1", **fields}


@pytest.mark.parametrize("value", [None, "", "not a date", "2026-10-13", "2026-10-13T19:00:00", 123])
def test_invalid_or_ambiguous_timestamps_are_not_guessed(value):
    assert deadlines.parse_due(value) is None
    assert deadlines.column_deadline(column(due=value), COURSE, "https://school.edu") is None


def test_only_explicit_visible_grade_column_due_dates_are_used():
    result = deadlines.column_deadline(column(due="2026-10-14T01:30:00+03:00", displayName="Proje"),
                                       COURSE, "https://school.edu")
    assert result["due"] == "2026-10-13T22:30:00+00:00"
    assert result["title"] == "Proje"
    assert parse_qs(urlsplit(result["url"]).query)["contentId"] == ["_c4_1"]
    assert deadlines.column_deadline(column(availability={"available": "No"}), COURSE, "https://school.edu") is None
    assert deadlines.column_deadline({"id": "x", "dueDate": "2026-10-13T22:30:00Z",
                                      "availability": {"end": "2026-10-13T22:30:00Z"}}, COURSE, "https://school.edu") is None
    linked = deadlines.column_deadline(column(contentId=None), COURSE, "https://school.edu", {"_grade_1": "nested"})
    assert linked["content_id"] == "nested"
    standalone = deadlines.column_deadline(column(contentId=None), COURSE, "https://school.edu")
    assert standalone["url"] == f"https://school.edu/ultra/courses/{COURSE}/grades"


def cache(state, *columns):
    state.deadline_courses[COURSE] = {"name": "CSE303 Algorithms", "items": [
        deadlines.column_deadline(c, COURSE, "https://school.edu") for c in columns]}


def test_groups_by_local_day_and_separates_elapsed_times_on_the_same_day(tmp_path):
    state = State(tmp_path / "cache.json")
    cache(state, column("tomorrow", "2026-10-13T22:30:00Z"), column("past", "2026-10-13T11:59:00Z"),
          column("later", "2026-10-13T18:00:00Z"), column("now", NOW.isoformat()),
          column("older", "2026-10-12T10:00:00Z"))
    page = deadlines.calendar_page(state, tmp_path, NOW, ZoneInfo("Europe/Istanbul"))
    assert [(d.day.isoformat(), d.past) for d in page.days] == [
        ("2026-10-13", False), ("2026-10-14", False), ("2026-10-13", True), ("2026-10-12", True)]
    assert [r.time for r in page.days[0].rows] == ["15:00", "21:00"]
    assert page.days[1].title == "Yarın · 14 Ekim 2026"
    assert page.days[1].rows[0].time == "01:30"
    assert page.days[0].rows[0].course == "CSE303 Algorithms"
    us = deadlines.calendar_page(state, tmp_path, NOW, ZoneInfo("America/Los_Angeles"))
    assert len(us.days) == 3  # Istanbul's tomorrow is still today in California.


def test_dst_fold_sorts_by_instant_and_not_wall_clock(tmp_path):
    state = State(tmp_path / "cache.json")
    cache(state, column("second", "2026-11-01T06:15:00Z"), column("first", "2026-11-01T05:45:00Z"))
    page = deadlines.calendar_page(state, tmp_path, NOW, ZoneInfo("America/New_York"))
    assert [r.time for r in page.days[0].rows] == ["01:45", "01:15"]
    assert [r.due.fold for r in page.days[0].rows] == [0, 1]


@pytest.mark.parametrize("extension", ["md", "pdf"])
def test_note_opening_tracks_relocation_and_falls_back_when_missing_or_unsafe(tmp_path, extension):
    state = State(tmp_path / "cache.json")
    cache(state, column())
    note_key = f"note:{COURSE}:_c4_1"
    name = f"Ödev.{extension}"
    note = tmp_path / "new" / name
    note.parent.mkdir()
    note.write_text("instructions")
    state.record_output(note_key, f"old/{name}", "sha", 12)
    state.move_tree("old", "new")
    page = deadlines.calendar_page(state, tmp_path, NOW)
    assert page.days[0].rows[0].target == f"new/{name}"
    note.unlink()
    assert deadlines.calendar_page(state, tmp_path, NOW).days[0].rows[0].target.startswith("https://")
    state.record_output(note_key, "../outside.md", "sha", 12)
    assert deadlines.calendar_page(state, tmp_path, NOW).days[0].rows[0].target.startswith("https://")


def test_sync_paginates_and_updates_dates_even_when_content_modified_is_unchanged(config, client, fake_bb):
    next_page = ROOT + "?offset=200"
    fake_bb.routes[ROOT] = {"results": [column()], "paging": {"nextPage": next_page}}
    fake_bb.routes[next_page] = {"results": [column("_test_1", "2026-10-14T09:00:00Z", name="Sınav")]}
    sync(config, client)
    state = State.load(config.state_file)
    assert len(state.deadline_courses[COURSE]["items"]) == 2
    assert state.deadline_courses[COURSE]["updated_at"]
    assert next_page in fake_bb.calls
    fake_bb.routes[ROOT]["results"][0]["grading"]["due"] = "2026-10-15T20:00:00Z"
    fake_bb.routes[next_page]["results"] = []
    fake_bb.calls.clear()
    sync(config, client)
    state = State.load(config.state_file)
    assert [c["due"] for c in state.deadline_courses[COURSE]["items"]] == ["2026-10-15T20:00:00+00:00"]
    assert not fake_bb.downloads()
    calls = list(fake_bb.calls)
    page = deadlines.load_calendar(config, config.dest)
    assert page.days and not page.message
    assert fake_bb.calls == calls  # local page needs no HTTP
    fake_bb.routes[ROOT] = {"results": []}
    sync(config, client)
    assert State.load(config.state_file).deadline_courses[COURSE]["items"] == []


def test_partial_paging_failure_preserves_cache_and_marks_it_unavailable(config, client, fake_bb):
    fake_bb.routes[ROOT] = {"results": [column()]}
    sync(config, client)
    old = State.load(config.state_file).deadline_courses[COURSE]["items"]
    fake_bb.routes[ROOT] = {"results": [], "paging": {"nextPage": ROOT + "?offset=200"}}
    report = sync(config, client)
    state = State.load(config.state_file)
    assert state.deadline_courses[COURSE]["items"] == old
    assert state.deadline_courses[COURSE]["unavailable"]
    assert any("due dates" in w for c in report.courses for w in c.warnings)
    assert deadlines.load_calendar(config, config.dest).message == deadlines.T_INCOMPLETE
    fake_bb.routes[ROOT] = {"results": []}
    sync(config, client)
    assert not deadlines.load_calendar(config, config.dest).message


def test_denied_access_is_distinct_from_no_due_dates(config, client, monkeypatch):
    def denied(course):
        raise ApiError(403, ROOT, "Forbidden")
    monkeypatch.setattr(client, "grade_columns", denied)
    sync(config, client)
    page = deadlines.load_calendar(config, config.dest)
    assert not page.days and page.message == deadlines.T_INCOMPLETE


def test_login_expiry_is_not_swallowed(config, client, monkeypatch):
    def expired(course):
        raise LoginRequired("expired")
    monkeypatch.setattr(client, "grade_columns", expired)
    with pytest.raises(LoginRequired):
        sync(config, client)


def test_old_state_loads_without_a_migration_and_dry_run_does_not_collect(config, client, fake_bb):
    state = State(config.state_file, {"version": 1, "items": {}, "outputs": {}})
    assert not state.deadline_courses
    assert deadlines.calendar_page(state, config.root, NOW).message == deadlines.T_NOT_SYNCED
    sync(config, client, dry_run=True)
    assert ROOT not in fake_bb.calls
    assert not config.state_file.exists()


def test_normal_sync_removes_courses_no_longer_in_the_active_term(config, client):
    state = State(config.state_file)
    state.deadline_courses["old-course"] = {"name": "Old", "items": []}
    state.dirty = True
    state.save()
    sync(config, client)
    assert "old-course" not in State.load(config.state_file).deadline_courses


def test_windows_calendar_navigation_scrolling_and_clicks_use_cached_rows(monkeypatch, tmp_path):
    from tests.test_windows import fake_tk
    from blackboard_sync.windows.main_window import MainWindow
    widgets = fake_tk(monkeypatch, tmp_path)
    state = State(tmp_path / "cache.json")
    cache(state, column(), column("past", "2026-10-12T10:00:00Z"))
    page = [deadlines.calendar_page(state, tmp_path, NOW)]
    opened = []
    values = FormValues("https://school.edu", str(tmp_path), True)
    window = MainWindow(None, values, main_status(AppModel(tmp_path, NOW), NOW),
                        lambda *_: None, lambda *_: None, lambda: None,
                        on_deadlines=lambda: page[0], on_deadline=opened.append)
    window.select(CALENDAR)
    assert window.visible_page() == CALENDAR
    assert window.nav[CALENDAR].options["text"] == "Takvim"
    buttons = [w for w in widgets if w.options.get("text") == "Ödev 1" and "command" in w.options]
    buttons[0].options["command"]()
    assert opened == [page[0].days[0].rows[0].target]
    window.calendar_canvas.view = (0, 0.5)
    window.wheel(type("Event", (), {"delta": -120})())
    assert window.calendar_canvas.scrolled == [(1, "units")]
    page[0] = deadlines.DeadlinePage()
    window.select(CALENDAR)
    assert any(w.options.get("text") == deadlines.T_EMPTY and not w.destroyed for w in widgets)


def test_window_state_accepts_calendar():
    window = WindowState()
    assert window.show(CALENDAR) == CALENDAR


def test_handler_column_id_matches_nested_content_when_column_lacks_content_id(config, client, fake_bb):
    children = f"/learn/api/public/v1/courses/{COURSE}/contents/_c22_1/children"
    fake_bb.routes[children]["results"].append({
        "id": "_nested_1", "title": "Sınav yönergesi", "body": "<p>Instructions</p>",
        "contentHandler": {"id": "resource/x-bb-asmt-test-link", "gradeColumnId": "_grade_1"}})
    fake_bb.routes[f"/learn/api/public/v1/courses/{COURSE}/contents/_nested_1/attachments"] = {"results": []}
    fake_bb.routes[ROOT] = {"results": [column(contentId=None)]}
    sync(config, client)
    state = State.load(config.state_file)
    item = state.deadline_courses[COURSE]["items"][0]
    assert item["content_id"] == "_nested_1"
    page = deadlines.load_calendar(config, config.dest)
    note = state.output(f"note:{COURSE}:_nested_1")
    assert note is not None
    assert page.days[0].rows[0].target == note["path"]
    assert (config.root / note["path"]).is_file()


def test_archive_and_file_restore_leave_deadlines_alone(config, client, fake_bb):
    fake_bb.routes[ROOT] = {"results": [column()]}
    sync(config, client)
    before = State.load(config.state_file).deadline_courses
    fake_bb.calls.clear()
    sync(config, client, term_name="2025-2026 Bahar")
    assert not any("gradebook" in call for call in fake_bb.calls)
    state = State.load(config.state_file)
    assert state.deadline_courses == before
    note_key = f"note:{COURSE}:_c4_1"
    (config.root / state.output(note_key)["path"]).unlink()
    fake_bb.calls.clear()
    sync(config, client)
    assert (config.root / state.output(note_key)["path"]).is_file()
    assert State.load(config.state_file).deadline_courses == before
