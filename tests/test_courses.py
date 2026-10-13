"""Dersler: which courses sync, keyed by the Blackboard course primary key."""

import json
from datetime import datetime, timezone

from blackboard_sync import courses
from blackboard_sync.deadlines import calendar_page
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.state import State
from tests.test_sync import CSE, SYLLABUS, files_under, sync

CSE_ID = "_13004_1"  # CSE303 Algorithm Analysis
ROOT = f"/learn/api/public/v2/courses/{CSE_ID}/gradebook/columns"


def untick(config, *course_ids):
    courses.save_disabled(config, course_ids)


def test_every_current_course_is_listed_and_on_by_default(config, client):
    sync(config, client)
    rows = courses.load_rows(config)
    assert [(r.id, r.code, r.title, r.enabled) for r in rows] == [
        ("_13050_1", "COE305", "Software Project Management", True),
        ("_13004_1", "CSE303", "Algorithm Analysis", True),
        ("_13010_1", "MTH201", "Linear Algebra", True),
    ]
    assert {r.term for r in rows} == {"2026-2027 Güz"}
    assert not config.courses_file.exists()  # nothing unticked, nothing saved


def test_an_unticked_course_gets_no_requests_and_keeps_its_files(config, client, fake_bb):
    fake_bb.routes[ROOT] = {"results": [{"id": "_g_1", "name": "Ödev", "grading": {"due": "2026-10-13T22:30:00Z"}}]}
    sync(config, client)
    before = files_under(config.dest / CSE)
    assert State.load(config.state_file).deadline_courses.get(CSE_ID)
    untick(config, CSE_ID)
    (config.dest / SYLLABUS).unlink()  # not even a missing file brings it back
    fake_bb.calls.clear()
    report = sync(config, client)
    assert not any(f"/courses/{CSE_ID}/" in call for call in fake_bb.calls)  # contents, announcements, due dates
    assert [c.code for c in report.courses] == ["COE305", "MTH201"]
    assert files_under(config.dest / CSE) == [p for p in before if f"{CSE}/{p}" != SYLLABUS]
    state = State.load(config.state_file)
    assert CSE_ID not in state.deadline_courses
    assert state.courses[CSE_ID]["code"] == "CSE303"  # still listed, so it can be ticked again
    assert [r.enabled for r in courses.load_rows(config) if r.id == CSE_ID] == [False]


def test_ticking_a_course_again_fills_in_what_is_missing(config, client, fake_bb):
    sync(config, client)
    untick(config, CSE_ID)
    (config.dest / SYLLABUS).unlink()
    sync(config, client)
    courses.set_enabled(config, CSE_ID, True)
    assert courses.load_disabled(config) == set()
    sync(config, client)
    assert (config.dest / SYLLABUS).is_file()


def test_a_course_that_appears_later_syncs_by_default(config, client, fake_bb):
    untick(config, "_13010_1")  # the student unticked MTH201 before COE305 showed up
    memberships = fake_bb.routes["/learn/api/public/v1/users/_900_1/courses?offset=4"]
    saved = memberships["results"]
    memberships["results"] = []
    report = sync(config, client)
    assert sorted(c.code for c in report.courses) == ["CSE303"]
    memberships["results"] = saved
    report = sync(config, client)
    assert sorted(c.code for c in report.courses) == ["COE305", "CSE303"]


def test_unticking_while_a_sync_runs_skips_the_courses_still_to_come(config, client, fake_bb, monkeypatch):
    from blackboard_sync import sync as sync_mod

    real = sync_mod.Syncer.sync_course

    def sync_course(self, course):
        if course.code == "COE305":  # the first course, by code
            untick(config, "_13010_1")
        return real(self, course)

    monkeypatch.setattr(sync_mod.Syncer, "sync_course", sync_course)
    report = sync(config, client)
    assert [c.code for c in report.courses] == ["COE305", "CSE303"]


def test_an_unreadable_choice_file_syncs_every_course(config, client):
    config.ensure_data_dir()
    config.courses_file.write_text("{not json", encoding="utf-8")
    assert courses.load_disabled(config) == set()
    config.courses_file.write_text(json.dumps({"disabled": ["_1_1", 5]}), encoding="utf-8")
    assert courses.load_disabled(config) == {"_1_1"}
    report = sync(config, client)
    assert len(report.courses) == 3


def test_the_choice_file_is_private_and_sorted(config):
    courses.set_enabled(config, "_2_1", False)
    courses.set_enabled(config, "_1_1", False)
    courses.set_enabled(config, "_2_1", True)
    assert json.loads(config.courses_file.read_text(encoding="utf-8")) == {"version": 1, "disabled": ["_1_1"]}


def test_filtered_and_past_term_runs_leave_the_course_list_alone(config, client):
    sync(config, client)
    listed = State.load(config.state_file).courses
    sync(config, client, course_filters=["CSE303"])
    sync(config, client, dry_run=True)
    assert State.load(config.state_file).courses == listed


def test_the_calendar_hides_an_unticked_course_at_once(config, client, fake_bb):
    fake_bb.routes[ROOT] = {"results": [{"id": "_g_1", "name": "Ödev", "grading": {"due": "2026-10-13T22:30:00Z"}}]}
    sync(config, client)
    state = State.load(config.state_file)
    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    assert calendar_page(state, config.root, now, timezone.utc).days
    assert not calendar_page(state, config.root, now, timezone.utc, hidden={CSE_ID}).days


def test_the_app_hides_recent_files_of_unticked_courses(config, client, tmp_path):
    sync(config, client)
    untick(config, CSE_ID)
    model = AppModel(config.dest, datetime.now(timezone.utc))
    jobs.refresh_hidden_folders(config, model)
    assert model.hidden_folders == (CSE,)


def test_duyurular_hides_an_unticked_course_at_once(config, client):
    from blackboard_sync import announcements

    sync(config, client)
    assert [r.course for r in announcements.load_rows(config)] == ["CSE303 Algorithm Analysis"]
    untick(config, CSE_ID)
    assert announcements.load_rows(config) == ()  # before any sync
    sync(config, client)
    assert announcements.load_rows(config) == ()
    courses.set_enabled(config, CSE_ID, True)
    assert [r.course for r in announcements.load_rows(config)] == ["CSE303 Algorithm Analysis"]
