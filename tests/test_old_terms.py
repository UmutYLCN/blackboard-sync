"""Past terms beside the current one: one folder per term, whatever language Blackboard answers in."""

import copy
import json

import pytest

from blackboard_sync import cli
from blackboard_sync.errors import ApiError, BlackboardSyncError
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import AppModel, RunOutcome, sync_arguments
from blackboard_sync.settings import Settings
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer, academic_term, choose_past_terms

from .test_menubar_jobs import fake_runner
from .test_past_terms import COURSE, FILE1, FILE2, PAST, ROOT, archive  # noqa: F401 (fixture)
from .test_session import _run_cli, _save
from .test_sync import NOW, sync

MEMBERS = "/learn/api/public/v1/users/_900_1/courses"
TERMS = "/learn/api/public/v1/terms"
CURRENT = "2026-2027 Güz"


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


def test_earlier_terms_open_beside_the_current_term(config, client, archive):
    add_term(archive, "_30_1", "2025-2026 Güz", start="2025-09-22T00:00:00.000Z", end="2026-01-31T23:59:59.000Z")
    add_membership(archive, "_11001_1", "_30_1", name="Programlama", code="CSE101-1")
    sync(config, client)
    assert [t.name for t in choose_past_terms(discover_all(config, client), NOW)] == [PAST, "2025-2026 Güz"]
    for name in (PAST, "2025-2026 Güz"):
        assert sync(config, client, term_name=name).totals()["new_files"] == 2
    assert sorted(p.name for p in config.root.iterdir()) == ["2025-2026 Bahar", "2025-2026 Güz", CURRENT]
    assert has_files(config.root / COURSE)
    assert (config.root / "2025-2026 Güz/CSE101 Programlama/first.pdf").read_bytes() == b"first archive file"


@pytest.mark.parametrize("past", [False, True])
def test_course_listed_twice_in_two_languages_is_synced_once(config, client, archive, past):
    members = archive.routes[MEMBERS]["results"]
    original = members[2 if past else 0]
    duplicate = copy.deepcopy(original)
    duplicate["id"] = "_duplicate_m"
    duplicate["course"]["name"] = "Veri Yapıları" if past else "Algoritma Analizi"
    members.append(duplicate)
    report = sync(config, client, **({"term_name": PAST} if past else {}))
    code = original["course"]["courseId"].split("-")[0]
    assert [c.folder for c in report.courses if c.code == code] == [
        COURSE if past else f"{CURRENT}/CSE303 Algorithm Analysis"]
    term_dir = config.root / (PAST if past else CURRENT)
    assert len([p for p in term_dir.iterdir() if p.name.startswith(code)]) == 1


def test_english_record_of_a_past_term_is_the_same_term(config, client, archive):
    add_term(archive, "_40_en", "2025-2026 Spring")
    add_membership(archive, "_12001_1", "_40_en")  # the same course again, under the English term
    add_membership(archive, "_12555_1", "_40_en", name="Discrete Mathematics", code="MTH210-1")
    terms = discover_all(config, client)
    assert [t.name for t in choose_past_terms(terms, NOW)] == [PAST]
    report = sync(config, client, term_name=PAST)
    assert report.terms == [PAST]
    assert sorted(c.folder for c in report.courses) == [COURSE, f"{PAST}/MTH210 Discrete Mathematics"]
    assert len(archive.downloads()) == 4  # two files of each course, each once
    report = sync(config, client, all_terms=True)
    assert report.terms == [CURRENT, PAST]
    assert sorted(p.name for p in config.root.iterdir()) == [PAST, CURRENT]


def test_english_only_term_is_named_in_turkish():
    assert academic_term("2025-2026 Spring") == academic_term("2025/2026 Bahar Dönemi") == ("2025", "2026", "Bahar")
    assert academic_term("2026-2027 - Fall") == ("2026", "2027", "Güz")
    assert academic_term("Yaz Okulu") is None and academic_term("2025-2026 Ek Dönem") is None


def test_past_term_named_in_english_downloads_into_turkish_folder(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "2025-2026 Spring"
    report = sync(config, client, term_name="2025-2026 Spring")
    assert report.past_term == PAST and report.courses[0].folder == COURSE
    assert has_files(config.root / COURSE)


def test_language_change_between_listing_and_download_still_downloads(config, client, archive):
    listed = choose_past_terms(discover_all(config, client), NOW)[0]
    archive.routes[f"{TERMS}/_40_1"]["name"] = "2025-2026 Spring"
    assert sync(config, client, term_name=listed.name).totals()["new_files"] == 2
    (config.root / COURSE / "first.pdf").unlink()
    assert sync(config, client, term_id=listed.id).totals()["new_files"] == 1
    assert archive.downloads() == [FILE1, FILE2, FILE1]


def test_renamed_term_and_course_keep_the_folder_holding_their_files(config, client, archive):
    sync(config, client, term_name=PAST)
    archive.calls.clear()
    archive.routes[f"{TERMS}/_40_1"]["name"] = "2025-2026 Spring"
    archive.routes[MEMBERS]["results"][2]["course"]["name"] = "Veri Yapıları"
    report = sync(config, client, term_name="2025-2026 Spring")
    assert report.courses[0].folder == COURSE
    assert sorted(p.name for p in config.root.iterdir()) == [PAST]
    assert sorted(p.name for p in (config.root / PAST).iterdir()) == ["CSE201 Data Structures"]
    assert archive.downloads() == []


def test_new_course_of_a_term_joins_the_folder_its_files_are_in(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Spring Term"  # not a name the app can read
    sync(config, client, term_name="Spring Term")
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Bahar Dönemi"
    add_membership(archive, "_12555_1", "_40_1", name="Discrete Mathematics", code="MTH210-1")
    report = sync(config, client, term_name="Bahar Dönemi")
    assert sorted(c.folder for c in report.courses) == [
        "Spring Term/CSE201 Data Structures", "Spring Term/MTH210 Discrete Mathematics"]


def test_terms_with_the_same_name_are_listed_apart_and_downloaded_by_id(config, client, archive, monkeypatch, capsys):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Ek Dönem"
    add_term(archive, "_41_1", "Ek Dönem", start="2025-07-01T00:00:00.000Z", end="2025-08-31T23:59:59.000Z")
    add_membership(archive, "_12555_1", "_41_1", name="Discrete Mathematics", code="MTH210-1")
    _save(config)
    monkeypatch.setattr(cli, "http_session", lambda data: archive)
    assert cli.main(["--base-url", "https://blackboard.example.edu", "--data-dir", str(config.data_dir),
                     "past-terms", "--json"]) == 0
    options = json.loads(capsys.readouterr().out)["options"]
    assert [(o["id"], o["label"]) for o in options] == [("_40_1", "Ek Dönem"), ("_41_1", "Ek Dönem (_41_1)")]
    with pytest.raises(BlackboardSyncError, match="--term-id.*_40_1, _41_1"):
        sync(config, client, term_name="Ek Dönem")
    assert archive.downloads() == []
    assert _run_cli(config, archive, monkeypatch, "--json", "--term-id", "_41_1") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["past_term"] == "Ek Dönem" and report["totals"]["new_files"] == 2
    assert [c["folder"] for c in report["courses"]] == ["Ek Dönem (_41_1)/MTH210 Discrete Mathematics"]
    assert sync(config, client, term_id="_40_1").totals()["new_files"] == 2
    assert sorted(p.name for p in config.root.iterdir()) == ["Ek Dönem", "Ek Dönem (_41_1)"]


def test_terms_whose_folder_names_collide_get_folders_of_their_own(config, client, archive):
    archive.routes[f"{TERMS}/_40_1"]["name"] = "Ek: Dönem"
    add_term(archive, "_41_1", "Ek/ Dönem", start="2025-07-01T00:00:00.000Z", end="2025-08-31T23:59:59.000Z")
    add_membership(archive, "_12555_1", "_41_1", name="Discrete Mathematics", code="MTH210-1")
    first = sync(config, client, term_id="_40_1").courses[0].folder
    second = sync(config, client, term_id="_41_1").courses[0].folder
    assert first.split("/")[0] != second.split("/")[0]
    assert sorted(p.name for p in (config.root / first.split("/")[0]).iterdir()) == ["CSE201 Data Structures"]


def test_unreadable_past_course_is_reported_and_left_for_a_retry(config, client, archive, monkeypatch, tmp_path):
    read = client.contents

    def denied(course_id):
        if course_id == "_12001_1":
            raise ApiError(403, ROOT + "/contents", "Forbidden")
        return read(course_id)

    monkeypatch.setattr(client, "contents", denied)
    report = sync(config, client, term_name=PAST)
    assert report.courses[0].content_error and any("Could not read the content" in w for w in report.warnings)
    entry = State.load(config.state_file).past_terms["_40_1"]
    assert entry["incomplete"] and "downloaded_at" not in entry
    outcome = RunOutcome.from_report(report.to_dict())
    model = AppModel(tmp_path, NOW)
    model.past_term = PAST
    assert model.begin("past_term")
    model.finish_sync(outcome, NOW)
    assert "Could not read the content of 1 course" in model.note and "not complete" in model.note

    monkeypatch.setattr(client, "contents", read)
    assert sync(config, client, term_name=PAST).totals()["new_files"] == 2
    entry = State.load(config.state_file).past_terms["_40_1"]
    assert "incomplete" not in entry and entry["downloaded_at"]


@pytest.mark.parametrize("dated", [True, False])
def test_english_record_of_the_current_term_is_the_current_term(config, client, archive, dated):
    add_term(archive, "_fall_en", "2026-2027 Fall", like="_50_1")
    if not dated:
        archive.routes[f"{TERMS}/_fall_en"].pop("availability")
    add_membership(archive, "_13004_1", "_fall_en", name="Algoritma Analizi", code="CSE303-1")
    add_membership(archive, "_13777_1", "_fall_en", name="Operating Systems", code="CSE331-1")
    assert [t.name for t in choose_past_terms(discover_all(config, client), NOW)] == [PAST]
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert sorted(p.name for p in config.root.iterdir()) == [CURRENT]
    assert "CSE331 Operating Systems" in {p.name for p in (config.root / CURRENT).iterdir()}
    with pytest.raises(BlackboardSyncError, match="is the current term"):
        sync(config, client, term_name="2026-2027 Fall")


def test_current_term_archived_by_its_english_name_is_not_frozen(config, client, archive):
    state = State(config.state_file)
    state.record_past_term("_fall_en", "2026-2027 Fall", ["_13004_1"])
    state.save()
    add_term(archive, "_fall_en", "2026-2027 Fall", like="_50_1")
    add_membership(archive, "_13777_1", "_fall_en", name="Operating Systems", code="CSE331-1")
    report = sync(config, client)
    assert report.terms == [CURRENT]
    assert "CSE331" in {c.code for c in report.courses}  # its course is not left out as archived


def test_term_yet_to_start_is_not_a_past_term(config, client, archive):
    add_term(archive, "_60_1", "2026-2027 Bahar", start="2027-02-08T00:00:00.000Z", end="2027-06-30T23:59:59.000Z")
    add_membership(archive, "_14001_1", "_60_1", name="Compilers", code="CSE402-1")
    assert [t.name for t in choose_past_terms(discover_all(config, client), NOW)] == [PAST]


def test_same_code_sections_keep_separate_folders(config, client, archive):
    add_membership(archive, "_12002_1", "_40_1", name="Data Structures", code="CSE201-2")
    report = sync(config, client, term_name=PAST)
    assert sorted(c.folder for c in report.courses) == [COURSE, f"{COURSE} (CSE201-2)"]
    assert archive.downloads().count(FILE1) == 1 and len(archive.downloads()) == 4


def test_gui_starts_the_download_with_the_listed_term_id(tmp_path):
    settings = Settings("https://bb.example.edu", tmp_path)
    listing = {"terms": ["Ek Dönem", "Ek Dönem (_41_1)"], "options": [
        {"id": "_40_1", "name": "Ek Dönem", "folder": "Ek Dönem", "label": "Ek Dönem"},
        {"id": "_41_1", "name": "Ek Dönem", "folder": "Ek Dönem (_41_1)", "label": "Ek Dönem (_41_1)"},
    ]}
    terms, outcome = jobs.run_past_terms(settings, fake_runner(stdout=json.dumps(listing)))
    assert terms == {"Ek Dönem": "_40_1", "Ek Dönem (_41_1)": "_41_1"}
    model = AppModel(tmp_path, NOW)
    assert model.begin("past_terms")
    model.finish_past_terms(terms, outcome)
    assert model.past_terms == ["Ek Dönem", "Ek Dönem (_41_1)"]
    assert model.select_past_term("Ek Dönem (_41_1)") and model.past_term_id == "_41_1"
    assert sync_arguments("past_term", settings, model.past_term, model.past_term_id)[-2:] == ["--term-id", "_41_1"]
    runner = fake_runner(stdout=json.dumps({"status": "ok", "past_term": "Ek Dönem"}))
    jobs.run_sync("past_term", settings, runner=runner, term_name=model.past_term, term_id=model.past_term_id)
    assert runner.calls[0][0][-2:] == ["--term-id", "_41_1"]


@pytest.fixture(autouse=True)
def retained_archive_engine(monkeypatch):
    """Exercise the retained archive engine; release-default guards have their own tests."""
    monkeypatch.setattr("blackboard_sync.menubar.model.PAST_TERMS_AVAILABLE", True)
