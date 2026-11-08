"""Several terms side by side: one folder per term, whatever language Blackboard answers in.

Only ``--all-terms`` syncs more than the current term; the old "download a past term" feature is gone.
A term an older version downloaded as an archive is still recorded in ``state.json`` (``past_terms``);
the normal sync keeps it frozen.
"""

import copy
import json

import pytest

from blackboard_sync import cli
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer, academic_term, choose_current_terms

from .test_session import _run_cli, _save
from .test_sync import NOW, sync

PAST = "2025-2026 Bahar"
COURSE = "2025-2026 Bahar/CSE201 Data Structures"
ROOT = "/learn/api/public/v1/courses/_12001_1"
FILE1 = f"{ROOT}/contents/_archive_1/attachments/_old1/download"
FILE2 = f"{ROOT}/contents/_archive_1/attachments/_old2/download"
MEMBERS = "/learn/api/public/v1/users/_900_1/courses"
TERMS = "/learn/api/public/v1/terms"
CURRENT = "2026-2027 Güz"


@pytest.fixture
def archive(fake_bb):
    """The 2025-2026 Bahar course with a document holding two files, and an announcement."""
    fake_bb.routes[f"{ROOT}/contents"] = {"results": [{
        "id": "_archive_1", "title": "Lecture", "modified": "2026-03-01T00:00:00Z",
        "contentHandler": {"id": "resource/x-bb-document"}, "body": "<p>Old lecture</p>",
    }]}
    fake_bb.routes[f"{ROOT}/contents/_archive_1/attachments"] = {"results": [
        {"id": "_old1", "fileName": "first.pdf"}, {"id": "_old2", "fileName": "second.pdf"},
    ]}
    fake_bb.routes[f"{ROOT}/announcements"] = {"results": [{
        "id": "_ann_old", "title": "Old announcement", "modified": "2026-03-01T00:00:00Z",
        "body": "<p>Old announcement</p>",
    }]}
    fake_bb.files[FILE1] = b"first archive file"
    fake_bb.files[FILE2] = b"second archive file"
    return fake_bb


def freeze(config, term_id="_40_1", name=PAST, courses=("_12001_1",)):
    """The record an older version left for a term it had downloaded as an archive."""
    state = State.load(config.state_file)
    state.past_terms[term_id] = {"name": name, "courses": list(courses), "downloaded_at": "2026-04-01T10:00:00+00:00"}
    state.dirty = True
    state.save()


def add_term(bb, term_id, name, like="_40_1", **dates):
    term = copy.deepcopy(bb.routes[f"{TERMS}/{like}"])
    term.update(id=term_id, name=name)
    if dates:
        term["availability"]["duration"].update(dates)
    bb.routes[f"{TERMS}/{term_id}"] = term


def add_membership(bb, course_id, term_id, name="Veri Yapıları", code="CSE201-1"):
    """A membership of course ``course_id`` holding a copy of the archive course's content."""
    member = copy.deepcopy(bb.routes[MEMBERS]["results"][2])
    member.update(id=f"_m_{course_id}_{term_id}", courseId=course_id)
    member["course"].update(id=course_id, termId=term_id, name=name, courseId=code)
    bb.routes[MEMBERS]["results"].append(member)
    root = ROOT.replace("_12001_1", course_id)
    if root != ROOT:
        for path, value in list(bb.routes.items()):
            if path.startswith(ROOT):
                bb.routes[path.replace(ROOT, root)] = copy.deepcopy(value)
        for path, value in list(bb.files.items()):
            if path.startswith(ROOT):
                bb.files[path.replace(ROOT, root)] = value


def discover_all(config, client):
    terms, _ = Syncer(client, config, State.load(config.state_file)).discover("_900_1", all_terms=True, now=NOW)
    return terms


def has_files(folder):
    return {"first.pdf", "second.pdf"} <= {p.name for p in folder.iterdir()}




def top_folders(config):
    return sorted(p.name for p in config.root.iterdir())


def old_downloads(bb):
    return [call for call in bb.downloads() if "_old" in call]


def test_normal_sync_opens_only_the_current_term(config, client, archive):
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert top_folders(config) == [CURRENT]
    assert not any(call.startswith(ROOT) for call in archive.calls)


def test_all_terms_opens_every_term_beside_the_current_one(config, client, archive):
    add_term(archive, "_30_1", "2025-2026 Güz", start="2025-09-22T00:00:00.000Z", end="2026-01-31T23:59:59.000Z")
    add_membership(archive, "_11001_1", "_30_1", name="Programlama", code="CSE101-1")
    sync(config, client, all_terms=True)
    assert top_folders(config) == ["2025-2026 Bahar", "2025-2026 Güz", CURRENT]
    assert has_files(config.root / COURSE)
    assert (config.root / "2025-2026 Güz/CSE101 Programlama/first.pdf").read_bytes() == b"first archive file"


@pytest.mark.parametrize("all_terms", [False, True])
def test_course_listed_twice_in_two_languages_is_synced_once(config, client, archive, all_terms):
    members = archive.routes[MEMBERS]["results"]
    original = members[2 if all_terms else 0]
    duplicate = copy.deepcopy(original)
    duplicate["id"] = "_duplicate_m"
    duplicate["course"]["name"] = "Veri Yapıları" if all_terms else "Algoritma Analizi"
    members.append(duplicate)
    report = sync(config, client, all_terms=all_terms)
    code = original["course"]["courseId"].split("-")[0]
    assert [c.folder for c in report.courses if c.code == code] == [
        COURSE if all_terms else f"{CURRENT}/CSE303 Algorithm Analysis"]
    term_dir = config.root / (PAST if all_terms else CURRENT)
    assert len([p for p in term_dir.iterdir() if p.name.startswith(code)]) == 1


def test_english_record_of_an_earlier_term_is_the_same_term(config, client, archive):
    add_term(archive, "_40_en", "2025-2026 Spring")
    add_membership(archive, "_12001_1", "_40_en")  # the same course again, under the English term
    add_membership(archive, "_12555_1", "_40_en", name="Discrete Mathematics", code="MTH210-1")
    report = sync(config, client, all_terms=True)
    assert sorted(report.terms) == sorted([CURRENT, PAST])
    assert top_folders(config) == [PAST, CURRENT]
    earlier = [c.folder for c in report.courses if c.folder.startswith(PAST)]
    assert sorted(earlier) == [COURSE, f"{PAST}/MTH210 Discrete Mathematics"]
    assert len(old_downloads(archive)) == 4  # two files of each course, each once


def test_turkish_and_english_season_names_are_one_semester():
    assert academic_term("2025-2026 Spring") == academic_term("2025/2026 Bahar Dönemi") == ("2025", "2026", "spring")
    assert academic_term("2026-2027 - Fall") == academic_term("2026-2027 Güz") == ("2026", "2027", "fall")
    assert academic_term("Yaz Okulu") is None and academic_term("2025-2026 Ek Dönem") is None


def test_earlier_term_named_in_english_keeps_its_english_folder(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "2025-2026 Spring"
    report = sync(config, client, all_terms=True)
    assert "2025-2026 Spring/CSE201 Data Structures" in {c.folder for c in report.courses}
    assert has_files(config.root / "2025-2026 Spring/CSE201 Data Structures")
    assert top_folders(config) == ["2025-2026 Spring", CURRENT]


def test_renamed_term_and_course_keep_the_folder_holding_their_files(config, client, archive):
    sync(config, client, all_terms=True)
    archive.calls.clear()
    archive.routes[f"{TERMS}/_40_1"]["name"] = "2025-2026 Spring"
    archive.routes[MEMBERS]["results"][2]["course"]["name"] = "Veri Yapıları"
    report = sync(config, client, all_terms=True)
    assert COURSE in {c.folder for c in report.courses}
    assert top_folders(config) == [PAST, CURRENT]
    assert sorted(p.name for p in (config.root / PAST).iterdir()) == ["CSE201 Data Structures"]
    assert old_downloads(archive) == []


def test_new_course_of_a_term_joins_the_folder_its_files_are_in(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Spring Term"  # not a name the app can read
    sync(config, client, all_terms=True)
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Bahar Dönemi"
    add_membership(archive, "_12555_1", "_40_1", name="Discrete Mathematics", code="MTH210-1")
    report = sync(config, client, all_terms=True)
    assert sorted(c.folder for c in report.courses if "Spring Term" in c.folder) == [
        "Spring Term/CSE201 Data Structures", "Spring Term/MTH210 Discrete Mathematics"]


def test_terms_with_the_same_name_get_folders_of_their_own(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Ek Dönem"
    add_term(archive, "_41_1", "Ek Dönem", start="2025-07-01T00:00:00.000Z", end="2025-08-31T23:59:59.000Z")
    add_membership(archive, "_12555_1", "_41_1", name="Discrete Mathematics", code="MTH210-1")
    report = sync(config, client, all_terms=True)
    assert sorted(c.folder for c in report.courses if "Ek Dönem" in c.folder) == [
        "Ek Dönem (_41_1)/MTH210 Discrete Mathematics", "Ek Dönem/CSE201 Data Structures"]
    assert top_folders(config) == [CURRENT, "Ek Dönem", "Ek Dönem (_41_1)"]


def test_terms_whose_folder_names_collide_get_folders_of_their_own(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Ek: Dönem"
    add_term(archive, "_41_1", "Ek/ Dönem", start="2025-07-01T00:00:00.000Z", end="2025-08-31T23:59:59.000Z")
    add_membership(archive, "_12555_1", "_41_1", name="Discrete Mathematics", code="MTH210-1")
    report = sync(config, client, all_terms=True)
    first = next(c.folder for c in report.courses if c.code == "CSE201")
    second = next(c.folder for c in report.courses if c.code == "MTH210")
    assert first.split("/")[0] != second.split("/")[0]
    assert sorted(p.name for p in (config.root / first.split("/")[0]).iterdir()) == ["CSE201 Data Structures"]


@pytest.mark.parametrize("dated", [True, False])
def test_english_record_of_the_current_term_is_the_current_term(config, client, archive, dated):
    add_term(archive, "_fall_en", "2026-2027 Fall", like="_50_1")
    if not dated:
        archive.routes[f"{TERMS}/_fall_en"].pop("availability")
    add_membership(archive, "_13004_1", "_fall_en", name="Algoritma Analizi", code="CSE303-1")
    add_membership(archive, "_13777_1", "_fall_en", name="Operating Systems", code="CSE331-1")
    assert [t.name for t in choose_current_terms(discover_all(config, client), NOW)] == [CURRENT]
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert top_folders(config) == [CURRENT]
    assert "CSE331 Operating Systems" in {p.name for p in (config.root / CURRENT).iterdir()}


def test_same_code_sections_keep_separate_folders(config, client, archive):
    add_membership(archive, "_12002_1", "_40_1", name="Data Structures", code="CSE201-2")
    report = sync(config, client, all_terms=True)
    assert sorted(c.folder for c in report.courses if c.folder.startswith(PAST)) == [COURSE, f"{COURSE} (CSE201-2)"]
    assert len(old_downloads(archive)) == 4


# -- terms an older version downloaded as archives stay as they are ---------------------------------

def test_normal_sync_leaves_a_term_an_older_version_archived_alone(config, client, archive):
    sync(config, client, all_terms=True)
    freeze(config)
    archive.files[FILE1] = b"changed remotely"
    archive.routes[f"{ROOT}/contents"]["results"][0]["modified"] = "2026-10-01T00:00:00Z"
    archive.calls.clear()
    before = copy.deepcopy(State.load(config.state_file).past_terms)
    (config.dest / COURSE / "second.pdf").unlink()
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert not any(call.startswith(ROOT) for call in archive.calls)
    assert (config.dest / COURSE / "first.pdf").read_bytes() == b"first archive file"
    assert not (config.dest / COURSE / "second.pdf").exists()
    assert State.load(config.state_file).past_terms == before


def test_archived_term_stays_frozen_if_current_memberships_disappear(config, client, archive):
    sync(config, client, all_terms=True)
    freeze(config)
    memberships = archive.routes[MEMBERS]
    memberships["results"] = [m for m in memberships["results"] if m["course"]["termId"] == "_40_1"]
    memberships.pop("paging")
    archive.calls.clear()
    assert sync(config, client).courses == []
    assert not any(call.startswith(ROOT) for call in archive.calls)


def test_current_term_archived_by_its_english_name_is_not_frozen(config, client, archive):
    freeze(config, "_fall_en", "2026-2027 Fall", ["_13004_1"])
    add_term(archive, "_fall_en", "2026-2027 Fall", like="_50_1")
    add_membership(archive, "_13777_1", "_fall_en", name="Operating Systems", code="CSE331-1")
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert "CSE331" in {c.code for c in report.courses}  # its course is not left out as archived


def test_state_file_with_leftover_archive_fields_still_loads(config, client, archive):
    config.ensure_data_dir()
    config.state_file.write_text(json.dumps({
        "version": 1, "items": {}, "outputs": {},
        "past_terms": {"_40_1": {"name": PAST, "courses": ["_12001_1"], "incomplete": True}},
        "something_a_later_version_added": {"x": 1},
    }), encoding="utf-8")
    report = sync(config, client)
    assert report.status == "ok" and report.terms == [CURRENT]
    assert "_40_1" in State.load(config.state_file).past_terms
    assert not any(call.startswith(ROOT) for call in archive.calls)


@pytest.mark.parametrize("argv", [["past-terms"], ["sync", "--term", PAST], ["sync", "--term-id", "_40_1"],
                                  ["check", "--term", PAST]])
def test_the_past_term_commands_and_options_are_gone(config, argv, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--base-url", "https://blackboard.example.edu", "--data-dir", str(config.data_dir), *argv])
    assert stop.value.code == 2


def test_all_terms_still_syncs_every_term_from_the_command_line(config, archive, monkeypatch, capsys):
    _save(config)
    assert _run_cli(config, archive, monkeypatch, "--json", "--all-terms") == 0
    report = json.loads(capsys.readouterr().out)
    assert sorted(report["terms"]) == sorted([CURRENT, PAST]) and "past_term" not in report
    assert has_files(config.root / COURSE)
