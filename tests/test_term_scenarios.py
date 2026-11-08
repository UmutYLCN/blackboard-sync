"""Which terms are current at schools set up in 28 different ways.

``fixtures/term_scenarios.json`` holds 28 synthetic Blackboard setups (no real account's data):
each one's API answers, the date of the sync and the terms and courses a student there means
by "this term" (``expected_ideal_output``). ``current_rule_output`` is what version 1.7.0's
rule picked; at the first school (İSTÜN) that was right and must stay exactly so.
"""

import json
from pathlib import Path

import pytest

from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer, parse_time, run_sync

from .conftest import BASE_URL, FakeBlackboard

SCENARIOS = {s["id"][:3]: s for s in json.loads(
    (Path(__file__).parent / "fixtures" / "term_scenarios.json").read_text(encoding="utf-8"))["scenarios"]}
USER = "_900_1"
OTHER_SCHOOL = "https://lms.other-school.example"
# The first school's checks (research report, part 3): their result must not change at all.
FIRST_SCHOOL = ["S01", "S02", "S03", "S12", "S15"]
# Where the test expects something other than the report's ideal pick, and why.
EXPECTED = {
    # The spring term's start is set to the day registration opens, inside the fall term. The
    # report accepts "Fall 2026 (or both)"; both are kept, since fall is still running.
    "S11": {"ideal_term_names": ["Fall 2026", "Spring 2027"], "ideal_course_ids": ["_13004_1", "_16001_1"],
            "ideal_course_codes": ["CSE303", "CSE304"]},
}


def discover(tmp_path, scenario, base_url=BASE_URL, state=None):
    config = Config(base_url=base_url, dest=tmp_path / "University", data_dir=tmp_path / "data")
    config.ensure_data_dir()
    state = state if state is not None else scenario.get("initial_state")
    if state:
        config.state_file.write_text(json.dumps(state), encoding="utf-8")
    syncer = Syncer(BlackboardClient(base_url, FakeBlackboard(scenario["api_routes"])), config,
                    State.load(config.state_file, backup=False), dry_run=True, windows=False)
    return syncer.discover(USER, now=parse_time(scenario["now"]))


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_the_current_terms_and_courses_of_each_setup(tmp_path, sid):
    scenario = SCENARIOS[sid]
    expected = EXPECTED.get(sid, scenario["expected_ideal_output"])
    state = scenario.get("initial_state")
    if sid == "S20":
        # The recorded files are the first school's; the student has moved to another one.
        state = {**state, "school": "blackboard.example.edu"}
    terms, courses = discover(tmp_path, scenario, OTHER_SCHOOL if sid == "S20" else BASE_URL, state)
    assert sorted(t.name for t in terms) == sorted(expected["ideal_term_names"])
    assert sorted(c.id for c in courses) == sorted(expected["ideal_course_ids"])
    assert sorted(c.code for c in courses) == sorted(expected["ideal_course_codes"])
    for course in courses:  # each course in its own term's folder
        assert course.rel_dir.split("/")[0] in {t.folder for t in terms}
    if sid == "S20":  # not in the first school's folder of its course with the same id
        assert [c.rel_dir for c in courses] == ["1448 الفصل الدراسي الأول/ARAB101 اللغة العربية"]


@pytest.mark.parametrize("sid", FIRST_SCHOOL)
def test_the_first_school_gets_exactly_what_it_got_before(tmp_path, sid):
    scenario = SCENARIOS[sid]
    before = scenario["current_rule_output"]
    terms, courses = discover(tmp_path, scenario)
    assert [t.name for t in terms] == before["selected_term_names"]
    assert [c.id for c in courses] == before["selected_course_ids"]
    assert [c.rel_dir for c in courses] == before["selected_course_rel_dirs"]


def test_first_school_sync_opens_only_the_current_courses(tmp_path):
    """S01 as a whole sync: the private course and last term's course are never opened."""
    scenario = SCENARIOS["S01"]
    config = Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=tmp_path / "data")
    bb = FakeBlackboard(scenario["api_routes"])
    report = run_sync(config, BlackboardClient(BASE_URL, bb), now=parse_time(scenario["now"]))
    assert report.terms == ["2026-2027 Güz"]
    assert sorted(c.code for c in report.courses) == ["COE305", "CSE303", "MTH201"]
    assert not any(course in call for call in bb.calls for course in ("_13099_1", "_12001_1"))


def test_archived_term_with_a_new_course_does_not_leave_the_student_with_nothing(tmp_path):
    """S14 as a whole sync: the archived term is left out first, so the running term is synced."""
    scenario = SCENARIOS["S14"]
    config = Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=tmp_path / "data")
    config.ensure_data_dir()
    config.state_file.write_text(json.dumps(scenario["initial_state"]), encoding="utf-8")
    bb = FakeBlackboard(scenario["api_routes"])
    report = run_sync(config, BlackboardClient(BASE_URL, bb), now=parse_time(scenario["now"]))
    assert report.terms == ["2026-2027 Güz"]
    assert [c.code for c in report.courses] == ["CSE303"]
    assert report.message == ""
    assert not any("_12999_1" in call or "_12001_1" in call for call in bb.calls)


def test_moving_to_another_school_does_not_reuse_the_first_schools_folders(tmp_path):
    """S20, and back: each school's course with id _13004_1 keeps a folder of its own."""
    scenario = SCENARIOS["S20"]
    istun_files = scenario["initial_state"]  # written by the first school, before schools were recorded
    data = tmp_path / "data"
    first = Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=data)
    first.ensure_data_dir()
    first.state_file.write_text(json.dumps(istun_files), encoding="utf-8")
    # The first sync after the update adopts the state file for the school in use; nothing changes.
    state = State.load(first.state_file)
    state.use_school(BASE_URL)
    state.save()
    assert json.loads(first.state_file.read_text(encoding="utf-8"))["outputs"] == istun_files["outputs"]

    terms, courses = discover(tmp_path, scenario, OTHER_SCHOOL, json.loads(first.state_file.read_text(encoding="utf-8")))
    assert [c.rel_dir for c in courses] == ["1448 الفصل الدراسي الأول/ARAB101 اللغة العربية"]

    # Back at the first school, its course is in its folder again.
    state = State.load(first.state_file)
    state.use_school(OTHER_SCHOOL)
    state.use_school(BASE_URL)
    assert state.outputs == istun_files["outputs"]
    assert Syncer(None, first, state, dry_run=True).recorded_course_dirs() == {
        "_13004_1": "2026-2027 Güz/CSE303 Algorithm Analysis"}


def test_switching_school_keeps_each_schools_files_apart(tmp_path):
    state = State(tmp_path / "state.json")
    state.use_school(BASE_URL)
    state.record_output("attachment:_1_1:_a", "Güz/A Course/a.pdf", "x", 1)
    state.use_school(OTHER_SCHOOL)
    state.record_output("attachment:_2_1:_b", "Fall/B Course/b.pdf", "y", 1)
    assert [State.from_this_school(o) for o in state.outputs.values()] == [False, True]
    state.use_school(BASE_URL + "/")
    assert [State.from_this_school(o) for o in state.outputs.values()] == [True, False]
    assert state.school == "blackboard.example.edu"

