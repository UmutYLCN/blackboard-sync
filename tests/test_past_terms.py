import copy
import json
from datetime import timedelta

import pytest

from blackboard_sync import cli
from blackboard_sync.menubar import jobs
from blackboard_sync.menubar.model import AppModel, Icon, RunOutcome, sync_arguments
from blackboard_sync.settings import Settings
from blackboard_sync.state import State
from blackboard_sync.sync import Course, Syncer, Term, choose_past_terms, parse_time, run_lock

from .test_menubar_jobs import fake_runner
from .test_session import _run_cli, _save
from .test_sync import NOW, sync

PAST = "2025-2026 Bahar"
COURSE = "2025-2026 Bahar/CSE201 Data Structures"
ROOT = "/learn/api/public/v1/courses/_12001_1"
FILE1 = f"{ROOT}/contents/_archive_1/attachments/_old1/download"
FILE2 = f"{ROOT}/contents/_archive_1/attachments/_old2/download"


@pytest.fixture
def archive(fake_bb):
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


def test_listing_excludes_current_and_sorts_newest_first(config, client, fake_bb):
    terms, _ = Syncer(client, config, State(config.state_file)).discover("_900_1", all_terms=True)
    older = copy.deepcopy(terms[-1])
    older.id, older.name, older.start = "older", "2025-2026 - Fall", parse_time("2025-09-01T00:00:00Z")
    assert [t.name for t in choose_past_terms([older, *terms], NOW)] == [PAST, older.name]


def test_listing_excludes_all_overlapping_current_terms():
    course = Course("c", "CSE", "Course", "t", "Term", "", "CSE")
    terms = [Term(str(i), str(i), NOW - timedelta(days=i), NOW + timedelta(days=5), [course])
             for i in (1, 2)]
    terms.append(Term("old", "Old", NOW - timedelta(days=100), NOW - timedelta(days=50), [course]))
    terms.append(Term(None, "No term", courses=[course]))
    assert [t.name for t in choose_past_terms(terms, NOW)] == ["Old"]


def test_undated_terms_sort_by_newest_course():
    def term(key, created):
        return Term(key, key, courses=[Course(key, key, key, key, key, "", key, created)])
    terms = [term("old", "2024-01-01Z"), term("new", "2025-01-01Z"), term("current", "2026-01-01Z")]
    assert [t.name for t in choose_past_terms(terms, NOW)] == ["new", "old"]


def test_archive_writes_term_folder_and_backward_compatible_state(config, client, archive):
    report = sync(config, client, term_name=PAST)
    assert report.past_term == PAST and report.terms == [PAST]
    assert (config.dest / COURSE / "first.pdf").read_bytes() == b"first archive file"
    assert report.totals()["new_files"] == 2
    state = State.load(config.state_file)
    assert state.past_terms["_40_1"]["courses"] == ["_12001_1"]
    assert json.loads(config.state_file.read_text())["version"] == 1
    assert "eski dönem" in report.render_text().lower()


def test_regular_sync_never_requests_or_updates_past_content(config, client, archive):
    sync(config, client, term_name=PAST)
    archive.files[FILE1] = b"changed remotely"
    archive.routes[f"{ROOT}/contents"]["results"][0]["modified"] = "2026-10-01T00:00:00Z"
    archive.calls.clear()
    before = copy.deepcopy(State.load(config.state_file).past_terms)
    report = sync(config, client, refetch_missing=True)
    assert report.terms == ["2026-2027 Güz"] and not report.past_term
    assert not any(call.startswith(ROOT) for call in archive.calls)
    assert (config.dest / COURSE / "first.pdf").read_bytes() == b"first archive file"
    assert State.load(config.state_file).past_terms == before


def test_repeated_archive_only_fetches_missing_outputs_even_when_remote_changed(config, client, archive):
    sync(config, client, term_name=PAST)
    archive.calls.clear()
    assert not sync(config, client, term_name=PAST).totals()["new_files"]
    assert archive.downloads() == []
    (config.dest / COURSE / "second.pdf").unlink()
    (config.dest / COURSE / "Lecture.md").unlink()
    archive.files[FILE1] = b"remote update must be ignored"
    archive.routes[f"{ROOT}/contents"]["results"][0].update(
        modified="2026-10-01T00:00:00Z", body="<p>Changed remote note</p>")
    announcement = next((config.dest / COURSE / "Duyurular").glob("*.md"))
    before = announcement.read_bytes()
    archive.routes[f"{ROOT}/announcements"]["results"][0].update(
        modified="2026-10-01T00:00:00Z", body="<p>Changed announcement</p>")
    report = sync(config, client, term_name=PAST)
    assert archive.downloads() == [FILE2]
    assert (config.dest / COURSE / "first.pdf").read_bytes() == b"first archive file"
    assert (config.dest / COURSE / "Lecture.md").exists()
    assert announcement.read_bytes() == before
    assert report.totals()["updated_files"] == report.totals()["updated_notes"] == 0


def test_archive_dry_run_does_not_record_state(config, client, archive):
    report = sync(config, client, term_name=PAST, dry_run=True)
    assert report.past_term == PAST and not config.state_file.exists()
    assert not config.dest.exists() and archive.downloads() == []


def test_archive_stays_frozen_if_current_memberships_disappear(config, client, archive):
    sync(config, client, term_name=PAST)
    memberships = archive.routes["/learn/api/public/v1/users/_900_1/courses"]
    memberships["results"] = [m for m in memberships["results"] if m["course"]["termId"] == "_40_1"]
    memberships.pop("paging")
    archive.calls.clear()
    assert sync(config, client).courses == []
    assert not any(call.startswith(ROOT) for call in archive.calls)


def test_archive_honors_deleted_files_dismissal(config, client, archive):
    sync(config, client, term_name=PAST)
    state = State.load(config.state_file)
    state.dismiss_outputs(["attachment:_12001_1:_old1"])
    state.save()
    (config.dest / COURSE / "first.pdf").unlink()
    (config.dest / COURSE / "second.pdf").unlink()
    archive.calls.clear()
    sync(config, client, term_name=PAST)
    assert archive.downloads() == [FILE2]
    assert not (config.dest / COURSE / "first.pdf").exists()


@pytest.mark.parametrize("name, message", [("2026-2027 Güz", "güncel"), ("unknown", "bulunamadı"), ("", "belirtin")])
def test_cli_rejects_current_and_unknown_terms_without_changing_last_run(config, archive, monkeypatch, capsys, name, message):
    _save(config)
    config.last_run_file.write_text('{"current":true}')
    assert _run_cli(config, archive, monkeypatch, "--json", "--term", name) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error" and message in report["message"]
    assert config.last_run_file.read_text() == '{"current":true}'
    assert not config.state_file.exists()


def test_cli_archive_preserves_last_current_run_and_next_sync_defaults(config, archive, monkeypatch, capsys):
    _save(config)
    assert _run_cli(config, archive, monkeypatch, "--json") == 0
    capsys.readouterr()
    before = config.last_run_file.read_bytes()
    assert _run_cli(config, archive, monkeypatch, "--json", "--term", PAST) == 0
    assert json.loads(capsys.readouterr().out)["past_term"] == PAST
    assert config.last_run_file.read_bytes() == before
    assert _run_cli(config, archive, monkeypatch, "--json") == 0
    assert json.loads(capsys.readouterr().out)["terms"] == ["2026-2027 Güz"]


def test_cli_listing_and_archive_respect_run_lock(config, archive, monkeypatch, capsys):
    _save(config)
    monkeypatch.setattr(cli, "http_session", lambda _data: archive)
    args = ["--base-url", config.base_url, "--data-dir", str(config.data_dir), "past-terms", "--json"]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["terms"] == [PAST]
    with run_lock(config.lock_file):
        assert _run_cli(config, archive, monkeypatch, "--json", "--term", PAST) == 4
        assert json.loads(capsys.readouterr().out)["status"] == "locked"
        assert cli.main(args) == 4
    assert not config.state_file.exists()


@pytest.mark.parametrize("status", ["ok", "locked", "error", "login_required"])
def test_archive_job_preserves_current_courses_result_and_schedule(tmp_path, status):
    last = RunOutcome("ok", finished_at=NOW)
    model = AppModel(tmp_path, NOW, last=last)
    scheduled, courses = model.next_run_at, model.courses
    assert model.begin("past_terms")
    assert model.icon() == Icon.SYNCING
    model.finish_past_terms([PAST], RunOutcome("ok"))
    assert not model.select_past_term("unknown")
    assert model.select_past_term(PAST) and model.begin("past_term")
    assert "eski dönem" in model.activity()
    notes = model.finish_sync(RunOutcome(status, message="failure", past_term=PAST), NOW)
    assert model.next_run_at == scheduled and model.last is last and model.courses is courses
    assert model.busy is None and model.past_term == ""
    assert "past_term" not in model.saved_state()
    if status == "ok":
        assert "0 dosya indirildi (eski dönem)" in notes[0].message
    assert "--term" not in sync_arguments("sync", Settings("https://bb.example.edu", tmp_path))


def test_jobs_pass_term_and_handle_listing_failures(tmp_path):
    settings = Settings("https://bb.example.edu", tmp_path)
    runner = fake_runner(stdout=json.dumps({"status": "ok", "past_term": PAST}))
    assert jobs.run_sync("past_term", settings, runner=runner, term_name=PAST).past_term == PAST
    assert runner.calls[0][0][-2:] == ["--term", PAST]
    assert jobs.run_past_terms(settings, fake_runner(stdout=json.dumps({"terms": [PAST]})))[0] == [PAST]
    for runner in (fake_runner(stdout="bad json"), fake_runner(returncode=3), fake_runner(raises=OSError("offline"))):
        names, result = jobs.run_past_terms(settings, runner)
        assert names == [] and result.status != "ok"


def test_cli_rejects_combined_term_selection():
    with pytest.raises(SystemExit) as error:
        cli.build_parser().parse_args(["sync", "--term", PAST, "--all-terms"])
    assert error.value.code == 2


def test_archive_dry_run_reports_missing_outputs(config, client, archive):
    sync(config, client, term_name=PAST)
    (config.dest / COURSE / "first.pdf").unlink()
    (config.dest / COURSE / "Lecture.md").unlink()
    archive.calls.clear()
    state = config.state_file.read_bytes()
    report = sync(config, client, term_name=PAST, dry_run=True)
    assert report.totals()["new_files"] == report.totals()["new_notes"] == 1
    assert archive.downloads() == [] and config.state_file.read_bytes() == state


def test_dialog_download_disables_during_other_jobs_and_school_change(tmp_path):
    model = AppModel(tmp_path, NOW)
    model.past_terms = [PAST]
    assert model.can_download_past_term
    model.begin("sync")
    assert not model.can_download_past_term and not model.select_past_term(PAST)
    model.finish_sync(RunOutcome("ok"), NOW)
    model.updates.busy = "download"
    assert not model.can_download_past_term
    model.updates.busy = None
    model.apply_settings(tmp_path, school_changed=True)
    assert not model.can_download_past_term


def test_archive_notification_includes_partial_failure(tmp_path):
    model = AppModel(tmp_path, NOW)
    model.past_term = PAST
    model.begin("past_term")
    result = RunOutcome.from_report({"status": "ok", "courses": [{"warnings": ["file failed"]}]})
    note = model.finish_sync(result, NOW)[0]
    assert "1 uyarı" in note.message and "tekrar deneyin" in note.message
