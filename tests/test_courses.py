"""Dersler: which courses sync, keyed by the Blackboard course primary key."""

import json
from datetime import datetime, timezone

import pytest

from blackboard_sync import courses
from blackboard_sync.deadlines import calendar_page
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import AppModel
from blackboard_sync.state import State
from tests.test_old_terms import CURRENT, MEMBERS, add_membership, add_term, archive, freeze  # noqa: F401
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


def test_unticking_while_a_sync_runs_skips_the_courses_still_to_come(config, client, archive, monkeypatch):
    from blackboard_sync import sync as sync_mod

    add_term(archive, "_year_1", "2026-2027", like="_50_1")
    add_membership(archive, "_14100_1", "_year_1", name="Senior Project", code="CSE499-1")
    real = sync_mod.Syncer.sync_course

    def sync_course(self, course):
        if course.code == "COE305":  # the first course, by code
            untick(config, "_13010_1", "_14100_1")
        return real(self, course)

    monkeypatch.setattr(sync_mod.Syncer, "sync_course", sync_course)
    report = sync(config, client)
    assert [c.code for c in report.courses] == ["COE305", "CSE303"]
    assert report.terms == [CURRENT]


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
    assert json.loads(config.courses_file.read_text(encoding="utf-8")) == {"version": 2, "disabled": ["_1_1"],
                                                                                         "enabled": []}


def test_filtered_and_dry_runs_leave_the_course_list_alone(config, client):
    sync(config, client)
    listed = State.load(config.state_file).courses
    sync(config, client, course_filters=["CSE303"])
    sync(config, client, dry_run=True)
    assert State.load(config.state_file).courses == listed


@pytest.mark.parametrize("dry_run", [False, True])
def test_first_filtered_sync_uses_the_full_current_roster(config, client, archive, dry_run):
    add_membership(archive, "_14000_1", None, name="Orientation", code="PDR01")
    report = sync(config, client, course_filters=["PDR01"], dry_run=dry_run)
    assert report.courses == [] and report.terms == []
    assert report.warnings == []
    assert not any("/courses/_14000_1/" in call for call in archive.calls)


@pytest.mark.parametrize("options", [{"course_filters": ["PDR01"]}, {"all_terms": True}])
def test_cached_and_frozen_terms_do_not_keep_a_termless_course_off(config, client, archive, options):
    add_membership(archive, "_14000_1", None, name="Orientation", code="PDR01")
    sync(config, client)
    freeze(config)
    for path, page in archive.routes.items():
        if path.startswith(MEMBERS):
            for member in page["results"]:
                if member["course"].get("termId") == "_50_1":
                    member["availability"] = {"available": "No"}
    report = sync(config, client, **options)
    assert "PDR01" in [course.code for course in report.courses]
    assert (config.root / "No term/PDR01 Orientation/first.pdf").is_file()


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


# -- courses without a term: off unless the student ticks them ---------------------------------

def info(term, termless, code="X"):
    return {"code": code, "title": "T", "term": term, "folder": f"{term}/{code}", "termless": termless}


MIXED = {"_1_1": info("2026-2027 Güz", False, "CSE303"), "_2_1": info("No term", True, "PDR01")}


def test_a_termless_course_is_off_by_default_when_a_termed_course_exists(config):
    assert courses.default_off(MIXED) == {"_2_1"}
    assert courses.effective_disabled(config, MIXED) == {"_2_1"}


def test_termless_courses_stay_on_when_there_is_nothing_else(config):
    only = {"_2_1": info("No term", True, "PDR01"), "_3_1": info("No term", True, "LIB100")}
    assert courses.default_off(only) == set()
    assert courses.effective_disabled(config, only) == set()
    assert courses.effective_disabled(config, {}) == set()


def test_ticking_a_termless_course_is_saved_as_an_opt_in_and_unticking_takes_it_back(config):
    state = State(config.state_file)
    state.courses = dict(MIXED)
    state.dirty = True
    state.save()
    courses.set_enabled(config, "_2_1", True)
    assert json.loads(config.courses_file.read_text(encoding="utf-8")) == {
        "version": 2, "disabled": [], "enabled": ["_2_1"]}
    assert courses.effective_disabled(config, MIXED) == set()
    assert {r.id: r.enabled for r in courses.load_rows(config)}["_2_1"] is True
    courses.set_enabled(config, "_2_1", False)
    assert courses.effective_disabled(config, MIXED) == {"_2_1"}
    assert json.loads(config.courses_file.read_text(encoding="utf-8"))["enabled"] == []
    courses.set_enabled(config, "_1_1", False)  # an ordinary course never lands in "enabled"
    courses.set_enabled(config, "_1_1", True)
    assert json.loads(config.courses_file.read_text(encoding="utf-8"))["enabled"] == []


def test_ticking_a_termless_course_when_nothing_else_is_current_keeps_it_on_later(config):
    only = {"_2_1": info("No term", True, "PDR01")}
    state = State(config.state_file)
    state.courses = dict(only)
    state.dirty = True
    state.save()
    courses.set_enabled(config, "_2_1", False)
    courses.set_enabled(config, "_2_1", True)
    assert courses.effective_disabled(config, MIXED) == set()


def test_saving_the_unticked_courses_keeps_the_opt_in(config):
    config.ensure_data_dir()
    config.courses_file.write_text(json.dumps({"version": 2, "disabled": [], "enabled": ["_2_1"]}), encoding="utf-8")
    courses.save_disabled(config, ["_9_1"])
    assert courses._read(config) == ({"_9_1"}, {"_2_1"})


def test_a_version_1_file_reads_as_no_opt_in(config):
    config.ensure_data_dir()
    config.courses_file.write_text(json.dumps({"version": 1, "disabled": ["_1_1"]}), encoding="utf-8")
    assert courses.effective_disabled(config, MIXED) == {"_1_1", "_2_1"}
    config.courses_file.write_text(json.dumps({"disabled": [], "enabled": "no"}), encoding="utf-8")
    assert courses.effective_disabled(config, MIXED) == {"_2_1"}


def test_a_state_from_1_7_1_marks_its_no_term_course_off_without_the_flag(config):
    """1.7.1 did not store "termless"; its "No term" folder name is all there is until the next sync."""
    old = {"_1_1": {"code": "CSE303", "title": "T", "term": "2026-2027 Güz", "folder": "g/CSE303"},
           "_12439_1": {"code": "PDR01", "title": "T", "term": "No term", "folder": "No term/PDR01"}}
    assert courses.effective_disabled(config, old) == {"_12439_1"}
    state = State(config.state_file)
    state.courses = old
    state.dirty = True
    state.save()
    rows = {r.id: r for r in courses.load_rows(config)}
    assert rows["_12439_1"].enabled is False and rows["_12439_1"].termless
    assert courses.load_hidden_folders(config) == ("No term/PDR01",)  # its files are hidden from Recent, not touched


def test_the_upgrade_stops_a_course_the_student_never_ticked_and_keeps_the_files(config, client, archive):
    """A 1.7.1 install: the termless course was synced; now it is off and nothing on disk changes."""
    from blackboard_sync.sync import NO_TERM
    add_membership(archive, "_14000_1", None, name="Library Orientation", code="LIB100-1")
    sync(config, client)  # the first sync here already leaves it off ...
    courses.set_enabled(config, "_14000_1", True)
    sync(config, client)  # ... so tick it to get the files a 1.7.1 install had
    folder = config.root / NO_TERM / "LIB100 Library Orientation"
    assert folder.is_dir()
    before = files_under(config.root)
    # What 1.7.1 left: no "termless" key, no "enabled" list, nothing unticked.
    state = State.load(config.state_file)
    state.courses = {key: {k: v for k, v in value.items() if k != "termless"} for key, value in state.courses.items()}
    state.dirty = True
    state.save()
    config.courses_file.write_text(json.dumps({"version": 1, "disabled": []}), encoding="utf-8")
    archive.calls.clear()
    sync(config, client)
    assert not any("_14000_1" in call for call in archive.calls)
    assert files_under(config.root) == before  # nothing deleted or moved
    assert {r.id: r.enabled for r in courses.load_rows(config)}["_14000_1"] is False


def test_the_courses_without_a_term_come_last_with_a_hint_only_beside_termed_courses(config):
    state = State(config.state_file)
    state.courses = {**MIXED, "_3_1": info("2020 Bahar", False, "AAA100")}
    state.dirty = True
    state.save()
    rows = courses.load_rows(config)
    assert [r.id for r in rows] == ["_3_1", "_1_1", "_2_1"] and rows[-1].termless
    assert courses.termless_hint(rows) == courses.T_TERMLESS_HINT
    assert courses.termless_hint(rows[:2]) == ""
    assert courses.termless_hint([rows[-1]]) == ""


def test_calendar_and_announcements_leave_out_a_default_off_course(config):
    from blackboard_sync import announcements, deadlines

    state = State(config.state_file)
    state.courses = dict(MIXED)
    state.record_current_courses(list(MIXED))
    for course_id, course in MIXED.items():
        code = course["code"]
        state.deadline_courses[course_id] = {"name": code, "items": [
            {"id": "exam", "title": f"{code} exam", "due": "2026-10-13T12:00:00Z", "url": config.base_url}]}
        key = f"announcement:{course_id}:news"
        state.record_announcement(key, announcements.metadata(
            {"title": f"{code} news"}, course_id, code, f"/courses/{course_id}/announcements", key))
    state.save()
    calendar = deadlines.load_calendar(config, config.dest)
    assert [row.title for day in calendar.days for row in day.rows] == ["CSE303 exam"]
    assert [row.title for row in announcements.load_rows(config)] == ["CSE303 news"]
