"""The latest term is the current one, the way the top group appears on Blackboard.

The term that started most recently (or, undated, holds the newest course) is current,
with every term starting at that moment; courses without a term always come along; the
school's own term names are kept; folders an older version made stay in use.
"""

import copy
import json
from datetime import timedelta

from blackboard_sync.state import State
from blackboard_sync.sync import NO_TERM, Course, Term, choose_current_terms, merge_term_aliases, parse_time

from .test_old_terms import CURRENT, MEMBERS, ROOT, TERMS, add_membership, add_term, archive, top_folders  # noqa: F401
from .test_sync import NOW, sync

FALL = "2026-09-21T00:00:00.000Z"
FALL_END = "2027-01-31T23:59:59.000Z"
CSE = f"{CURRENT}/CSE303 Algorithm Analysis"


def term(tid, name=None, start=None, end=None, created=(), courses=None):
    t = Term(tid, name or tid, parse_time(start), parse_time(end))
    for i, stamp in enumerate(created):
        t.courses.append(Course(f"_{tid}_{i}", f"X{i}", "X", tid, t.name, "", f"X{i}", stamp))
    for course_id in courses or ():
        t.courses.append(Course(course_id, course_id, course_id, tid, t.name, "", course_id))
    return t


def names(terms):
    return [t.name for t in terms]


# -- choosing the group ----------------------------------------------------------

def test_undated_terms_use_their_newest_course():
    old = term("_1", "Ek Dönem", created=["2025-09-01T00:00:00Z", "2025-10-01T00:00:00Z"])
    new = term("_2", "Ortak Dersler", created=["2024-01-01T00:00:00Z", "2026-09-01T00:00:00Z"])
    assert choose_current_terms([old, new], NOW) == [new]


def test_mixed_dated_and_undated_terms_compare_start_with_course_creation():
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, created=["2026-08-20T00:00:00Z"])
    older = term("_old", "Ek Dönem", created=["2025-09-01T00:00:00Z"])
    assert choose_current_terms([older, fall], NOW) == [fall]
    newer = term("_new", "Telafi", created=["2026-09-25T00:00:00Z"])
    assert choose_current_terms([older, fall, newer], NOW) == [newer]


def test_courses_without_a_term_come_with_the_current_group():
    spring = term("_spring", "2025-2026 Bahar", "2026-02-09T00:00:00Z", "2026-06-30T00:00:00Z", created=["x"])
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, created=["x"])
    termless = term(None, NO_TERM, created=["2020-01-01T00:00:00Z"])
    assert choose_current_terms([termless, spring, fall], NOW) == [fall, termless]


def test_year_long_and_semester_terms_starting_together_are_one_group():
    year = term("_year", "2026-2027", FALL, "2027-06-30T00:00:00Z", created=["x"])
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, created=["x"])
    spring = term("_spring", "2025-2026 Bahar", "2026-02-09T00:00:00Z", "2026-06-30T00:00:00Z", created=["x"])
    assert choose_current_terms(merge_term_aliases([spring, year, fall]), NOW) == [year, fall]


def test_next_term_opens_a_month_early_only_once_the_current_one_has_ended():
    fall = term("_fall", "2026-2027 Güz", FALL, FALL_END, created=["x"])
    spring = term("_spring", "2026-2027 Bahar", "2027-02-15T00:00:00Z", "2027-06-30T00:00:00Z", created=["x"])
    assert choose_current_terms([fall, spring], NOW) == [fall]
    # Exam weeks: the fall term still runs, so it stays even though spring opens within a month.
    assert choose_current_terms([fall, spring], parse_time("2027-01-20T00:00:00Z")) == [fall]
    # The day after fall ends, spring (two weeks away) takes over.
    assert choose_current_terms([fall, spring], parse_time("2027-02-01T12:00:00Z")) == [spring]
    # In a long gap the ended term stays until the next one is a month away.
    summer_gap = term("_old", "2025-2026 Bahar", "2026-02-09T00:00:00Z", "2026-06-30T00:00:00Z", created=["x"])
    assert choose_current_terms([summer_gap, fall], parse_time("2026-07-15T00:00:00Z")) == [summer_gap]
    # Nothing has started yet (a first-year student in summer): the first upcoming term.
    assert choose_current_terms([spring, fall], parse_time("2026-06-01T00:00:00Z")) == [fall]


def test_when_no_term_can_be_dated_every_course_is_current():
    a = term("_a", "Dönem A", courses=["_c1"])
    b = term("_b", "Dönem B", courses=["_c2"])
    termless = term(None, NO_TERM, courses=["_c3"])
    assert choose_current_terms([a, b, termless], NOW) == [a, b, termless]
    assert choose_current_terms([], NOW) == []


# -- names and merging --------------------------------------------------------------

def test_turkish_and_english_record_of_one_semester_are_one_term():
    tr_term = term("_tr", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    en_term = term("_en", "2026-2027 Fall", FALL, FALL_END, courses=["_c2", "_c3"])
    [merged] = merge_term_aliases([tr_term, en_term])
    # The school's own name of the record holding most courses; no Turkish-first naming.
    assert (merged.id, merged.name) == ("_en", "2026-2027 Fall")
    assert merged.ids == ["_en", "_tr"] and merged.names == ["2026-2027 Fall", "2026-2027 Güz"]
    assert sorted(c.id for c in merged.courses) == ["_c1", "_c2", "_c3"]
    assert {c.term_name for c in merged.courses} == {"2026-2027 Fall"}


def test_one_semester_under_two_names_takes_the_first_name_on_a_tie():
    tr_term = term("_tr", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    en_term = term("_en", "2026-2027 Fall", FALL, FALL_END, courses=["_c2"])
    assert names(merge_term_aliases([tr_term, en_term])) == ["2026-2027 Güz"]
    assert names(merge_term_aliases([en_term, tr_term])) == ["2026-2027 Fall"]


def test_english_only_term_keeps_its_english_name():
    fall = term("_en", "2026-2027 Fall", FALL, FALL_END, courses=["_c1"])
    spring = term("_sp", "2025-2026 Spring", "2026-02-09T00:00:00Z", "2026-06-30T00:00:00Z", courses=["_c2"])
    assert names(merge_term_aliases([fall, spring])) == ["2026-2027 Fall", "2025-2026 Spring"]


def test_same_season_name_in_different_years_or_dates_is_not_merged():
    fall = term("_a", "2026-2027 Güz", FALL, FALL_END, courses=["_c1"])
    other_dates = term("_b", "2026-2027 Fall", "2027-09-20T00:00:00Z", "2028-01-31T00:00:00Z", courses=["_c2"])
    other_year = term("_c", "2025-2026 Fall", FALL, FALL_END, courses=["_c3"])
    assert len(merge_term_aliases([fall, other_dates, other_year])) == 3


# -- whole syncs --------------------------------------------------------------------

def test_english_only_school_keeps_fall(config, client, archive):
    archive.routes[f"{TERMS}/_50_1"]["name"] = "2026-2027 Fall"
    report = sync(config, client)
    assert report.terms == ["2026-2027 Fall"]
    assert top_folders(config) == ["2026-2027 Fall"]
    assert (config.root / "2026-2027 Fall/CSE303 Algorithm Analysis").is_dir()


def test_existing_guz_folder_stays_in_use_when_the_term_is_named_fall(config, client, archive):
    """An older version named an English-only "2026-2027 Fall" term "2026-2027 Güz"; its folder stays."""
    sync(config, client)
    state_before = json.loads(config.state_file.read_text(encoding="utf-8"))
    files_before = {p.relative_to(config.root): p.stat().st_mtime_ns for p in config.root.rglob("*") if p.is_file()}
    downloads_before = len(archive.downloads())
    archive.routes[f"{TERMS}/_50_1"]["name"] = "2026-2027 Fall"
    add_membership(archive, "_13777_1", "_50_1", name="Operating Systems", code="CSE331-1")

    report = sync(config, client)

    assert report.terms == ["2026-2027 Fall"]
    assert top_folders(config) == [CURRENT]
    assert sorted(c.folder for c in report.courses if c.code in ("CSE303", "CSE331")) == [
        CSE, f"{CURRENT}/CSE331 Operating Systems"]
    # Nothing that was there is downloaded again, moved or rewritten.
    assert len(archive.downloads()) == downloads_before + 2  # only the new course's two files
    for rel, mtime in files_before.items():
        assert (config.root / rel).stat().st_mtime_ns == mtime
    state_after = json.loads(config.state_file.read_text(encoding="utf-8"))
    for key, out in state_before["outputs"].items():
        assert state_after["outputs"][key]["path"] == out["path"]


def test_old_state_file_loads_unchanged_and_keeps_the_guz_folder(config, client, archive):
    sync(config, client)
    archive.routes[f"{TERMS}/_50_1"]["name"] = "2026-2027 Fall"
    raw_before = config.state_file.read_text(encoding="utf-8")
    state = State.load(config.state_file)
    assert {o["path"].split("/")[0] for o in state.outputs.values()} == {CURRENT}
    assert config.state_file.read_text(encoding="utf-8") == raw_before
    archive.calls.clear()
    report = sync(config, client)
    assert archive.downloads() == []
    assert CSE in {c.folder for c in report.courses}


def test_course_without_a_term_is_synced_with_the_current_term(config, client, archive):
    add_membership(archive, "_14000_1", None, name="Library Orientation", code="LIB100-1")
    report = sync(config, client)
    assert sorted(report.terms) == sorted([CURRENT, NO_TERM])
    assert top_folders(config) == [CURRENT, NO_TERM]
    assert (config.root / NO_TERM / "LIB100 Library Orientation" / "first.pdf").is_file()


def test_year_long_and_semester_term_with_the_same_start_are_both_synced(config, client, archive):
    add_term(archive, "_year_1", "2026-2027", like="_50_1", end="2027-06-30T23:59:59.000Z")
    add_membership(archive, "_14100_1", "_year_1", name="Senior Project", code="CSE499-1")
    report = sync(config, client)
    assert sorted(report.terms) == sorted([CURRENT, "2026-2027"])
    assert top_folders(config) == ["2026-2027", CURRENT]
    assert (config.root / "2026-2027/CSE499 Senior Project/first.pdf").is_file()


def test_undated_terms_choose_the_one_holding_the_newest_course(config, client, archive):
    for tid in ("_50_1", "_40_1"):
        archive.routes[f"{TERMS}/{tid}"].pop("availability")
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert not any(call.startswith(ROOT) for call in archive.calls)


def test_no_courses_found_is_said_in_the_sync_result(config, client, archive):
    archive.routes[MEMBERS]["results"] = []
    archive.routes[MEMBERS].pop("paging", None)
    report = sync(config, client)
    assert report.status == "ok" and report.courses == []
    assert report.message.startswith("No courses found on Blackboard")
    assert report.message in report.warnings
    assert report.message in report.render_text()
    assert report.to_dict()["message"] == report.message


def test_unticked_or_filtered_courses_are_not_reported_as_none_found(config, client, archive):
    report = sync(config, client, course_filters=["NOPE999"])
    assert report.message == ""
    assert report.warnings == ["No courses found for the selected term."]


def test_running_term_stays_current_while_the_next_one_opens(config, client, archive):
    start = (NOW + timedelta(days=20)).isoformat().replace("+00:00", "Z")
    add_term(archive, "_next_1", "2026-2027 Ara Dönem", like="_50_1", start=start, end="2027-03-01T00:00:00.000Z")
    member = copy.deepcopy(archive.routes[MEMBERS]["results"][0])
    member["course"].update(id="_15000_1", termId="_next_1", courseId="CSE600-1", name="Seminar")
    archive.routes[MEMBERS]["results"].append(member)
    assert sync(config, client, dry_run=True).terms == [CURRENT]
