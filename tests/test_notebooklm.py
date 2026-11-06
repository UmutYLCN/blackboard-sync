"""Adding the synced files to NotebookLM: what goes up, and the rules around it. No network here."""

import asyncio
import json
import os
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blackboard_sync.cli import main
from blackboard_sync.config import Config
from blackboard_sync.errors import (
    BlackboardSyncError,
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMRateLimited,
    NotebookLMSignInFailed,
    NotebookLMTransient,
)
from blackboard_sync.menubar import jobs, main_window_model
from blackboard_sync.menubar.model import NOTEBOOKLM_DUPLICATES, AppModel
from blackboard_sync.notebooklm import duplicates, planner, runner, signin, store
from blackboard_sync.notebooklm.planner import CourseScan, FileInfo
from blackboard_sync.settings import Settings
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock

from .conftest import assert_owner_only

TERM = "2026-2027 Güz"


@dataclass
class Remote:
    id: str
    title: str
    status: str = "ready"
    created_at: str = ""


class FakeGateway:
    """The ``Gateway`` surface, in memory."""

    def __init__(self, notebooks=(), sources=None, limit=300):
        self.notebooks = list(notebooks)
        self.sources = {key: list(value) for key, value in (sources or {}).items()}
        self.limit = limit
        self.added: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.undeletable: set[str] = set()
        self.failures: dict[str, list[Exception]] = {}  # per title, raised before it goes up
        self.land_despite_failure = False
        self.processing = "ready"
        self.closed = False

    async def source_limit(self):
        return self.limit

    async def find_notebooks(self, title):
        return [n for n in self.notebooks if n.title == title]

    async def create_notebook(self, title):
        notebook = Remote(f"nb{len(self.notebooks)}", title)
        self.notebooks.append(notebook)
        return notebook

    async def list_sources(self, notebook_id):
        return list(self.sources.get(notebook_id, []))

    async def add_file(self, notebook_id, path, title):
        pending = self.failures.get(title)
        if pending:
            if self.land_despite_failure:
                self.sources.setdefault(notebook_id, []).append(Remote("landed", title))
            raise pending.pop(0)
        Path(path).stat()
        self.added.append((notebook_id, title))
        source = Remote(f"s{len(self.added)}", title, "processing")
        self.sources.setdefault(notebook_id, []).append(source)
        return source.id

    async def delete_source(self, notebook_id, source_id):
        if source_id in self.undeletable:
            raise NotebookLMTransient("timed out")
        self.deleted.append(source_id)
        self.sources[notebook_id] = [s for s in self.sources[notebook_id] if s.id != source_id]

    async def wait_ready(self, notebook_id, source_ids, timeout):
        return {source_id: self.processing for source_id in source_ids}

    async def close(self):
        self.closed = True


def put(config, folder, rel, data=None, kind="attachment", name=None):
    """A file the sync downloaded, recorded in its state; files have their own content by default."""
    path = f"{folder}/{rel}"
    target = config.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    data = path.encode() if data is None else data
    target.write_bytes(data)
    return f"{kind}:_1_1:{name or path}", {"path": path, "sha256": "x", "size": len(data)}


@pytest.fixture
def config(tmp_path):
    made = Config(dest=tmp_path / "dest", data_dir=tmp_path / "data",
                  notebooklm_legacy_state=tmp_path / "legacy" / "state.json")
    made.ensure_data_dir()
    store.session_file(made).parent.mkdir()
    store.session_file(made).write_text("{}")
    return made


def write_state(config, courses, outputs):
    state = State(config.state_file)
    state.courses = {f"_{index}_1": {"code": "C", "title": "T", "term": TERM, "folder": folder}
                     for index, folder in enumerate(courses)}
    state.outputs = dict(outputs)
    state.dirty = True
    state.save()


CS = f"{TERM}/CSE301 Database"
MTH = f"{TERM}/MTH101 Mathematics"


def run(config, gateway, **options):
    async def opener(_config):
        return gateway

    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)

    result = runner.run(config, opener=opener, sleep=sleep, **options)
    result.waits = waits
    return result


# -- which files are candidates ------------------------------------------------------------------
def test_scan_takes_the_synced_files_of_current_ticked_courses_only(config):
    outputs = [
        put(config, CS, "Week 1/slides.pdf"),
        put(config, CS, "Week 1/.Slides.md", kind="note-md"),
        put(config, CS, "Duyurular/Exam.pdf", kind="announcement-note"),
        put(config, CS, "Week 1/data.zip"),
        put(config, CS, "Week 1/photo.png"),
        put(config, CS, "Week 1/empty.pdf", data=b""),
        put(config, MTH, "book.pdf"),
        put(config, f"{TERM.replace('Güz', 'Bahar')}/OLD100 Past", "old.pdf"),
    ]
    write_state(config, [CS, MTH], outputs)
    mine = config.root / CS / "my own notes.pdf"
    mine.write_bytes(b"private")

    state = State.load(config.state_file, backup=False)
    scans = planner.scan_courses(state, config.root, {"_1_1"})

    assert [scan.title for scan in scans] == ["CSE301 Database"]
    assert [f.rel for f in scans[0].uploadable] == ["Week 1/slides.pdf"]
    assert {f.rel: f.skip_reason for f in scans[0].skipped} == {
        "Week 1/data.zip": "unsupported format", "Week 1/empty.pdf": "empty file", "Week 1/photo.png": "image"}


def test_a_file_the_student_deleted_is_counted_as_skipped(config):
    key, entry = put(config, CS, "a.pdf")
    (config.root / entry["path"]).unlink()
    write_state(config, [CS], [(key, entry)])
    scan = planner.scan_courses(State.load(config.state_file, backup=False), config.root)[0]
    assert [f.skip_reason for f in scan.files] == ["missing"]


@pytest.mark.parametrize("ext, size, reason", [
    (".pdf", 1, ""), (".docx", 1, ""), (".pptx", 1, ""), (".txt", 1, ""), (".md", 1, ""), (".csv", 1, ""),
    (".epub", 1, ""), (".ppt", 1, "unsupported format"), ("", 1, "unsupported format"), (".jpg", 1, "image"),
    (".pdf", 0, "empty file"), (".pdf", planner.MAX_FILE_BYTES + 1, "over the 200 MB limit"),
])
def test_what_notebooklm_accepts(ext, size, reason):
    assert planner.skip_reason(ext, size) == reason


def test_images_are_off_by_default_but_can_be_taken():
    assert planner.skip_reason(".png", 1, include_images=True) == ""


def test_a_notebook_is_named_after_the_course_folder_and_the_term_only_on_a_clash():
    titles = planner.notebook_titles([CS, f"2026 Yaz/{CS.split('/')[1]}", MTH])
    assert titles[MTH] == "MTH101 Mathematics"
    assert titles[CS] == "CSE301 Database (2026-2027 Güz)"
    assert titles[f"2026 Yaz/{CS.split('/')[1]}"] == "CSE301 Database (2026 Yaz)"


def test_macos_decomposed_names_become_composed_titles():
    assert planner.notebook_titles(["T/Mühendislik"])["T/Mühendislik"] == "Mühendislik"


# -- the plan -------------------------------------------------------------------------------------
def scan_of(tmp_path, *names):
    files = []
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        info = path.stat()
        files.append(FileInfo(name, path, info.st_size, info.st_mtime_ns))
    return CourseScan("T/C", "C", files)


def actions(plan):
    return {action.file.rel: action.action for action in plan.actions}


def test_plan_new_adopted_and_failed_copies(tmp_path):
    scan = scan_of(tmp_path, "new.pdf", "there.pdf", "broken.pdf")
    sources = [Remote("s1", "there.pdf"), Remote("s2", "broken.pdf", "error")]
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")], sources=sources,
                               limit=50)
    assert actions(plan) == {"new.pdf": planner.UPLOAD, "there.pdf": planner.ADOPT, "broken.pdf": planner.UPLOAD}
    assert plan.status == planner.READY and plan.notebook_id == "n"


def test_plan_compares_with_what_was_added(tmp_path):
    scan = scan_of(tmp_path, "same.pdf", "touched.pdf", "changed.pdf", "other.pdf")
    state = store.UploadState(tmp_path / "s")
    for info in scan.files:
        state.record("T/C", info.rel, notebook_id="n", source_id="s", size=info.size, mtime_ns=info.mtime_ns,
                     sha256=store.sha256_file(info.path))
    os.utime(tmp_path / "touched.pdf", ns=(1, 1))
    (tmp_path / "changed.pdf").write_bytes(b"something else")
    state.data["courses"]["T/C"]["files"]["other.pdf"]["notebook_id"] = "another"
    scan = CourseScan("T/C", "C", [FileInfo(f.rel, f.path, f.path.stat().st_size, f.path.stat().st_mtime_ns)
                                   for f in scan.files])
    plan = planner.plan_course(scan, state, matches=[Remote("n", "C")], sources=[], limit=50)
    assert actions(plan) == {"same.pdf": planner.UNCHANGED, "touched.pdf": planner.TOUCHED,
                             "changed.pdf": planner.MODIFIED, "other.pdf": planner.UPLOAD}


def test_stop_do_not_truncate(tmp_path):
    scan = scan_of(tmp_path, "a.pdf", "b.pdf")
    sources = [Remote(str(i), f"r{i}") for i in range(49)]
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")], sources=sources,
                               limit=50)
    assert plan.status == planner.BLOCKED and plan.overflow == 1


def test_a_title_shared_by_notebooks_is_skipped_not_guessed(tmp_path):
    plan = planner.plan_course(scan_of(tmp_path, "a.pdf"), store.UploadState(tmp_path / "s"),
                               matches=[Remote("1", "C"), Remote("2", "C")], sources=None, limit=50)
    assert plan.status == planner.AMBIGUOUS and not plan.actions


def test_a_course_without_files_gets_no_notebook(tmp_path):
    plan = planner.plan_course(CourseScan("T/C", "C"), store.UploadState(tmp_path / "s"), matches=[], sources=[], limit=50)
    assert plan.status == planner.EMPTY


# -- a run ----------------------------------------------------------------------------------------
def test_a_run_makes_the_notebook_adds_the_files_and_a_second_run_adds_nothing(config):
    write_state(config, [CS], [put(config, CS, "Week 1/a.pdf"), put(config, CS, "b.docx"), put(config, CS, "c.zip")])
    gateway = FakeGateway()

    first = run(config, gateway)

    assert [n.title for n in gateway.notebooks] == ["CSE301 Database"]
    assert set(gateway.added) == {("nb0", "Week 1/a.pdf"), ("nb0", "b.docx")}
    assert first.status == "ok" and len(first.added) == 2 and first.skipped == 1
    assert first.waits == [runner.DELAY_SECONDS] * 2
    assert gateway.closed

    second = run(config, gateway)
    assert len(gateway.added) == 2 and not second.added
    assert_owner_only(store.state_file(config))


def test_the_same_titled_notebook_is_reused_and_lost_state_adopts_its_sources(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    notebook = Remote("existing", "CSE301 Database")
    gateway = FakeGateway([notebook], {"existing": [Remote("s9", "a.pdf")]})

    result = run(config, gateway)

    assert not gateway.added and len(gateway.notebooks) == 1
    assert len(result.adopted) == 1
    assert store.UploadState.load(store.state_file(config)).get_file(CS, "a.pdf")["source_id"] == "s9"


def test_a_blocked_course_gets_nothing_and_the_others_go_on(config):
    write_state(config, [CS, MTH], [put(config, CS, "a.pdf"), put(config, MTH, "b.pdf")])
    notebook = Remote("full", "CSE301 Database")
    gateway = FakeGateway([notebook], {"full": [Remote(str(i), f"r{i}") for i in range(50)]}, limit=50)

    result = run(config, gateway)

    assert [title for _, title in gateway.added] == ["b.pdf"]
    assert result.blocked == [("CSE301 Database", 1, 50)]
    saved = store.status(config)
    assert saved.blocked == 1 and saved.message == "CSE301 Database: 1 over the 50 source limit; nothing added."


def test_an_unknown_account_limit_falls_back_to_the_free_plan(config):
    write_state(config, [CS], [put(config, CS, f"{i}.pdf", name=str(i)) for i in range(51)])
    gateway = FakeGateway(limit=None)
    result = run(config, gateway)
    assert not gateway.added and result.blocked == [("CSE301 Database", 1, 50)]


def test_a_passing_failure_is_retried_with_growing_waits(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    gateway.failures["a.pdf"] = [NotebookLMTransient("x"), NotebookLMTransient("y")]

    result = run(config, gateway)

    assert len(result.added) == 1 and result.waits == [5.0, 15.0, runner.DELAY_SECONDS]


def test_giving_up_after_three_attempts_leaves_the_file_for_the_next_run(config):
    write_state(config, [CS], [put(config, CS, "a.pdf"), put(config, CS, "b.pdf")])
    gateway = FakeGateway()
    gateway.failures["a.pdf"] = [NotebookLMTransient(str(i)) for i in range(3)]

    result = run(config, gateway)

    assert [title for _, title in gateway.added] == ["b.pdf"] and len(result.failed) == 1
    assert "1 file could not be added" in store.status(config).message
    assert run(config, gateway).added  # not recorded: it goes up now


def test_a_failure_that_still_landed_is_not_added_twice(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    gateway.land_despite_failure = True
    gateway.failures["a.pdf"] = [NotebookLMTransient("timed out")]

    result = run(config, gateway)

    assert not gateway.added and len(result.added) == 1
    assert store.UploadState.load(store.state_file(config)).get_file(CS, "a.pdf")["source_id"] == "landed"


def test_a_rejected_file_is_not_retried_and_the_rest_go_on(config):
    write_state(config, [CS], [put(config, CS, "a.pdf"), put(config, CS, "b.pdf")])
    gateway = FakeGateway()
    gateway.failures["a.pdf"] = [NotebookLMPermanent("rejected")]

    result = run(config, gateway)

    assert result.failed == [("CSE301 Database/a.pdf", "rejected")]
    assert [title for _, title in gateway.added] == ["b.pdf"]


def test_an_expired_session_ends_the_run_and_keeps_what_went_up(config):
    write_state(config, [CS], [put(config, CS, "a.pdf"), put(config, CS, "b.pdf")])
    gateway = FakeGateway()
    gateway.failures["b.pdf"] = [NotebookLMLoginRequired()]

    result = run(config, gateway)

    assert result.status == "login_required" and gateway.closed
    assert store.status(config).needs_login
    assert store.UploadState.load(store.state_file(config)).get_file(CS, "a.pdf") is not None


def test_a_failed_new_notebook_fails_that_course_only(config):
    write_state(config, [CS, MTH], [put(config, CS, "a.pdf"), put(config, MTH, "b.pdf")])
    gateway = FakeGateway()
    real = gateway.create_notebook

    async def create(title):
        if title == "CSE301 Database":
            raise NotebookLMPermanent("notebook limit")
        return await real(title)

    gateway.create_notebook = create
    result = run(config, gateway)
    assert len(result.failed) == 1 and [title for _, title in gateway.added] == ["b.pdf"]


def test_processing_errors_are_reported(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    gateway.processing = "error"
    result = run(config, gateway)
    assert result.processing_errors == ["CSE301 Database/a.pdf"]
    assert store.status(config).failed == 1


def test_a_modified_file_is_reported_never_replaced(config):
    key, entry = put(config, CS, "a.pdf")
    write_state(config, [CS], [(key, entry)])
    gateway = FakeGateway()
    run(config, gateway)
    (config.root / entry["path"]).write_bytes(b"new content")

    result = run(config, gateway)

    assert len(gateway.added) == 1 and result.modified == ["CSE301 Database/a.pdf"]
    assert len(gateway.sources["nb0"]) == 1


def test_an_automatic_run_with_nothing_new_stays_off_the_network(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    run(config, gateway)
    before = store.last_run_file(config).read_text()

    async def opener(_config):
        raise AssertionError("no network")

    result = runner.run(config, auto=True, opener=opener)

    assert result.status == "ok" and not result.worked
    assert store.last_run_file(config).read_text() == before


def age_session(config, seconds=runner.SESSION_REFRESH_SECONDS + 60):
    path = store.session_file(config)
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime - seconds))


def test_with_nothing_new_the_session_is_still_opened_now_and_then_to_keep_it_alive(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    run(config, gateway)
    gateway.closed = False
    before = store.last_run_file(config).read_text()
    age_session(config)

    result = run(config, gateway, auto=True)

    assert gateway.closed and not result.worked
    assert store.last_run_file(config).read_text() == before

    gateway.closed = False
    run(config, gateway, auto=True)  # just done: it stays off the network again
    assert not gateway.closed


def test_a_session_found_dead_when_keeping_it_alive_shows_on_the_card(config):
    write_state(config, [], [])
    age_session(config)

    async def opener(_config):
        raise NotebookLMLoginRequired()

    runner.run(config, auto=True, opener=opener)
    assert store.status(config).needs_login


def test_no_network_while_keeping_the_session_alive_is_not_worth_a_word(config):
    write_state(config, [], [])
    age_session(config)

    async def opener(_config):
        raise NotebookLMTransient("offline")

    assert runner.run(config, auto=True, opener=opener).status == "ok"
    assert not store.last_run_file(config).exists()


def test_an_automatic_run_looks_at_the_courses_with_something_new_only(config):
    outputs = [put(config, CS, "a.pdf"), put(config, MTH, "b.pdf")]
    write_state(config, [CS, MTH], outputs)
    gateway = FakeGateway()
    run(config, gateway)
    seen = []
    real = gateway.find_notebooks

    async def find(title):
        seen.append(title)
        return await real(title)

    gateway.find_notebooks = find
    write_state(config, [CS, MTH], [*outputs, put(config, CS, "c.pdf")])

    run(config, gateway, auto=True)

    assert seen == ["CSE301 Database"] and gateway.added[-1][1] == "c.pdf"


def test_a_manual_run_proves_the_session_even_with_nothing_new(config):
    write_state(config, [], [])
    opened = []

    async def opener(_config):
        opened.append(True)
        raise NotebookLMLoginRequired()

    assert runner.run(config, opener=opener).status == "login_required" and opened


def test_no_session_means_sign_in(config):
    store.session_file(config).unlink()
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    assert run(config, FakeGateway()).status == "login_required"


def test_google_out_of_reach_is_an_error_not_a_lost_session(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])

    async def opener(_config):
        raise NotebookLMTransient("NetworkError: no route")

    result = runner.run(config, opener=opener)
    saved = store.status(config)
    assert result.status == "error" and saved.error and not saved.needs_login
    assert saved.message == "NetworkError: no route"


def test_only_one_run_at_a_time(config):
    from blackboard_sync.sync import run_lock

    write_state(config, [CS], [put(config, CS, "a.pdf")])
    with run_lock(store.lock_file(config)):
        result = run(config, FakeGateway())
    assert result.status == "locked" and not store.last_run_file(config).exists()


def test_progress_events_count_the_uploads(config):
    write_state(config, [CS], [put(config, CS, "a.pdf"), put(config, CS, "b.pdf")])
    events: list[dict] = []
    run(config, FakeGateway(), events=events.append)
    assert events[0] == {"event": "planning"}
    assert events[-1]["event"] == "processing"
    assert events[-2] == {"event": "progress", "done": 2, "finished": 2, "total": 2, "course": "CSE301 Database",
                          "file": "b.pdf"}


def test_a_stopped_run_lost_nothing(config):
    """Each file is saved as soon as it is up, before the next one starts."""
    write_state(config, [CS], [put(config, CS, "a.pdf"), put(config, CS, "b.pdf")])
    gateway = FakeGateway()
    saved_counts = []
    real = gateway.add_file

    async def add_file(notebook_id, path, title):
        data = store.UploadState.load(store.state_file(config)).data
        saved_counts.append(sum(len(c["files"]) for c in data["courses"].values()))
        return await real(notebook_id, path, title)

    gateway.add_file = add_file
    run(config, gateway)
    assert saved_counts == [0, 1]


# -- the store ------------------------------------------------------------------------------------
def test_status_of_a_connection_that_never_ran(config):
    assert store.status(config) == store.NotebookLMStatus(connected=True)


def test_status_survives_a_damaged_last_run(config):
    store.last_run_file(config).write_text("{ not json")
    assert store.status(config) == store.NotebookLMStatus(connected=True)
    store.last_run_file(config).write_text(json.dumps({"added": "many", "finished_at": 3}))
    assert store.status(config) == store.NotebookLMStatus(connected=True)


def test_a_damaged_state_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[")
    assert store.UploadState.load(path).data["courses"] == {}
    path.write_text(json.dumps({"version": 99, "courses": {"x": {}}}))
    assert store.UploadState.load(path).data["courses"] == {}


def test_disconnect_deletes_the_session_and_browser_data_and_keeps_the_record(config):
    store.session_file(config).with_suffix(".json.lock").write_text("")
    store.last_run_file(config).write_text("{}")
    store.state_file(config).write_text("{}")
    for folder in (store.profile_dir(config), store.library_home(config)):
        folder.mkdir()
        (folder / "Cookies").write_text("secret")

    assert store.disconnect(config) == []

    left = sorted(path.name for path in config.notebooklm_dir.iterdir())
    assert left == ["state.json"]
    assert not store.status(config).connected


def test_signing_in_again_clears_the_old_error_and_keeps_the_counts(config):
    store.save_last_run(config, {"status": "login_required", "added": 3, "message": "sign in"})
    store.mark_connected(config)
    saved = store.status(config)
    assert not saved.needs_login and saved.added == 3 and not saved.message


# -- the Google sign-in ---------------------------------------------------------------------------
class FakePage:
    def __init__(self, url):
        self.url = url


class FakeContext:
    def __init__(self, pages, cookies=()):
        self.pages = pages
        self.names = list(cookies)

    def cookies(self):
        return [{"name": name, "value": "v"} for name in self.names]


class FakeBrowser:
    """Like Playwright's sync API: what the browser did only arrives during a call, here ``cookies()``.

    Each entry of ``timeline`` is the browser at the next look; ``sleep`` alone changes nothing.
    """

    def __init__(self, *timeline):
        self.timeline = list(timeline)
        self.context = FakeContext([FakePage("about:blank")])
        self.closed = False

    def is_connected(self):
        return True

    @property
    def contexts(self):
        browser = self

        class Live:
            @property
            def pages(self):
                return browser.context.pages

            def cookies(self):
                if browser.timeline:
                    browser.context = browser.timeline.pop(0)
                return browser.context.cookies()

        return [Live()]

    def new_browser_cdp_session(self):
        class Session:
            def send(_self, _method):
                self.closed = True

        return Session()

    def close(self):
        pass


SIGNED_IN = FakeContext([FakePage("https://notebook.google.com/")], sorted(signin.REQUIRED_COOKIES))


def test_the_sign_in_waits_for_notebooklm_and_the_session_cookies():
    browser = FakeBrowser(
        FakeContext([FakePage("https://accounts.google.com/signin")], ["SID"]),
        FakeContext([FakePage("https://notebook.google.com/")], ["NID"]),  # the signed-out product page
        SIGNED_IN,
    )
    state = signin.wait_for_sign_in(browser, 5, sleep=lambda _s: None)
    assert {cookie["name"] for cookie in state["cookies"]} == signin.REQUIRED_COOKIES


def test_a_closed_sign_in_window_is_reported():
    browser = FakeBrowser(FakeContext([FakePage("https://accounts.google.com/")]), FakeContext([]))
    with pytest.raises(BlackboardSyncError, match="closed before sign-in"):
        signin.wait_for_sign_in(browser, 5, sleep=lambda _s: None)


@pytest.fixture
def signin_seams(monkeypatch):
    monkeypatch.setattr(signin, "find_browser", lambda *a, **k: Path("/Applications/Google Chrome.app"))
    monkeypatch.setattr(signin, "wait_for_port", lambda port: None)
    monkeypatch.setattr(signin, "free_port", lambda: 12345)
    started = []

    def run(argv, **_options):
        started.append(argv)
        return type("Done", (), {"returncode": 0, "stderr": ""})()

    return started, run


def test_login_saves_the_session_owner_only_and_never_with_port_zero(config, signin_seams):
    started, spawn_run = signin_seams
    store.session_file(config).unlink()
    store.save_last_run(config, {"status": "login_required"})

    signin.login(config, run=spawn_run, connect=lambda url: FakeBrowser(SIGNED_IN), check=lambda c: None,
                 platform="darwin")

    assert_owner_only(store.session_file(config))
    assert not store.status(config).needs_login
    assert "--remote-debugging-port=12345" in started[0]
    assert signin.SIGN_IN_URL in started[0]


def test_a_session_google_rejects_is_not_kept(config, signin_seams):
    _started, spawn_run = signin_seams

    def check(_config):
        raise NotebookLMLoginRequired()

    with pytest.raises(NotebookLMSignInFailed) as caught:
        signin.login(config, run=spawn_run, connect=lambda url: FakeBrowser(SIGNED_IN), check=check, platform="darwin")
    assert caught.value.outcome == signin.VERIFY_FAILED
    assert not store.session_file(config).exists()


def test_a_session_the_library_cannot_use_is_not_kept(config, signin_seams):
    _started, spawn_run = signin_seams

    def check(_config):
        raise NotebookLMPermanent("no such thing")

    with pytest.raises(NotebookLMSignInFailed) as caught:
        signin.login(config, run=spawn_run, connect=lambda url: FakeBrowser(SIGNED_IN), check=check, platform="darwin")
    assert caught.value.outcome == signin.VERIFY_FAILED
    assert not store.session_file(config).exists()


def test_google_out_of_reach_keeps_a_fresh_session(config, signin_seams):
    _started, spawn_run = signin_seams

    def check(_config):
        raise NotebookLMTransient("offline")

    signin.login(config, run=spawn_run, connect=lambda url: FakeBrowser(SIGNED_IN), check=check, platform="darwin")
    assert store.session_file(config).exists()


def test_no_supported_browser_is_said_plainly(config, monkeypatch):
    from blackboard_sync.login import NoSupportedBrowserError

    def missing(*_a, **_k):
        raise NoSupportedBrowserError("no browser")

    monkeypatch.setattr(signin, "find_browser", missing)
    with pytest.raises(NotebookLMSignInFailed, match="needs Chrome, Edge or Brave") as caught:
        signin.login(config, platform="darwin")
    assert caught.value.outcome == signin.NO_BROWSER


def test_a_free_port_is_a_real_port():
    assert signin.free_port() > 0


def test_the_sign_in_sees_what_happened_while_it_slept():
    """The bug of the first live test: the page only moved on for Playwright during a call of its
    own, and looking at the URL alone made none, so a finished sign-in was never noticed."""
    browser = FakeBrowser(FakeContext([FakePage("https://accounts.google.com/signin")]), SIGNED_IN)
    state = signin.wait_for_sign_in(browser, timeout=5, sleep=lambda _s: None)
    assert {cookie["name"] for cookie in state["cookies"]} == signin.REQUIRED_COOKIES
    assert state["origins"] == []


def test_a_closed_window_is_seen_while_nothing_else_happens():
    browser = FakeBrowser(FakeContext([FakePage("https://accounts.google.com/signin")]), FakeContext([]))
    with pytest.raises(NotebookLMSignInFailed) as caught:
        signin.wait_for_sign_in(browser, timeout=5, sleep=lambda _s: None)
    assert caught.value.outcome == signin.WINDOW_CLOSED


def test_chromium_refusing_the_look_once_its_last_window_is_gone_counts_as_closed():
    """What a real Chrome does: ``Storage.getCookies`` fails, the browser itself lives on."""
    browser = FakeBrowser(FakeContext([FakePage("https://accounts.google.com/signin")]))
    live = browser.contexts[0]

    class Refusing:
        pages: list = []

        def cookies(self):
            raise RuntimeError("Browser context management is not supported.")

    browser.__class__ = type("Gone", (FakeBrowser,), {"contexts": property(lambda self: [Refusing()])})
    assert live.pages  # it had a window a moment ago
    with pytest.raises(NotebookLMSignInFailed) as caught:
        signin.wait_for_sign_in(browser, timeout=5, sleep=lambda _s: None)
    assert caught.value.outcome == signin.WINDOW_CLOSED


def test_another_failure_of_the_look_is_not_hidden():
    class Failing:
        pages = [FakePage("https://accounts.google.com/signin")]

        def cookies(self):
            raise RuntimeError("something else")

    browser = FakeBrowser()
    browser.__class__ = type("Broken", (FakeBrowser,), {"contexts": property(lambda self: [Failing()])})
    with pytest.raises(RuntimeError, match="something else"):
        signin.wait_for_sign_in(browser, timeout=5, sleep=lambda _s: None)


def test_running_out_of_time_says_so():
    browser = FakeBrowser(FakeContext([FakePage("https://accounts.google.com/signin")]))
    with pytest.raises(NotebookLMSignInFailed) as caught:
        signin.wait_for_sign_in(browser, timeout=0, sleep=lambda _s: None)
    assert caught.value.outcome == signin.TIMED_OUT


def test_the_cli_reports_how_a_connect_ended(config, monkeypatch, capsys):
    from blackboard_sync import cli

    def fail(_config, **_options):
        raise NotebookLMSignInFailed("Sign-in was not completed.", signin.TIMED_OUT)

    monkeypatch.setattr(signin, "login", fail)
    args = type("Args", (), {"notebooklm_action": "login"})()
    assert cli.cmd_notebooklm(args, config) != 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert (result["outcome"], result["message"]) == (signin.TIMED_OUT, "Sign-in was not completed.")


def test_the_cli_reports_a_connect_that_worked(config, monkeypatch, capsys):
    from blackboard_sync import cli

    def works(_config, on_verify, **_options):
        on_verify()

    monkeypatch.setattr(signin, "login", works)
    args = type("Args", (), {"notebooklm_action": "login"})()
    assert cli.cmd_notebooklm(args, config) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0] == {"event": "sign_in", "step": "verify"}
    assert lines[-1]["outcome"] == signin.CONNECTED


# -- courses side by side -------------------------------------------------------------------------
class ParallelGateway(FakeGateway):
    """Counts the uploads in flight, per notebook and in all; each upload lets the others run."""

    def __init__(self, meet=0, **options):
        super().__init__(**options)
        self.in_flight: dict[str, int] = {}
        self.most = 0
        self.most_in_a_notebook = 0
        self.meet = meet  # uploads wait until this many are in flight; hashing makes the timing unknown
        self.met = asyncio.Event()

    async def add_file(self, notebook_id, path, title):
        self.in_flight[notebook_id] = self.in_flight.get(notebook_id, 0) + 1
        self.most = max(self.most, sum(self.in_flight.values()))
        self.most_in_a_notebook = max(self.most_in_a_notebook, self.in_flight[notebook_id])
        try:
            if self.most >= self.meet:
                self.met.set()
            await asyncio.wait_for(self.met.wait(), 10)
            await asyncio.sleep(0)
            return await super().add_file(notebook_id, path, title)
        finally:
            self.in_flight[notebook_id] -= 1


def many_courses(config, courses=5, files=3):
    folders = [f"{TERM}/C{index} Course" for index in range(courses)]
    write_state(config, folders, [put(config, folder, f"{name}.pdf") for folder in folders
                                  for name in "abcdefg"[:files]])
    return folders


async def yielding_sleep(_seconds):
    await asyncio.sleep(0)


def run_parallel(config, gateway, **options):
    async def opener(_config):
        return gateway

    return runner.run(config, opener=opener, sleep=yielding_sleep, **options)


def test_courses_go_side_by_side_and_a_course_stays_in_order(config):
    many_courses(config)
    gateway = ParallelGateway(meet=runner.COURSE_CONCURRENCY)

    result = run_parallel(config, gateway)

    assert len(result.added) == 15 and not result.failed
    assert runner.COURSE_CONCURRENCY == 3
    assert gateway.most == 3
    assert gateway.most_in_a_notebook == 1


def test_the_count_on_the_card_runs_across_all_courses(config):
    many_courses(config)
    events: list[dict] = []
    run_parallel(config, ParallelGateway(), events=events.append)
    progress = [event for event in events if event["event"] == "progress"]

    assert {event["total"] for event in progress} == {15}
    assert [event["done"] for event in progress] == sorted(event["done"] for event in progress)
    assert [event["finished"] for event in progress] == sorted(event["finished"] for event in progress)
    assert progress[-1]["done"] == progress[-1]["finished"] == 15
    assert len({event["course"] for event in progress}) == 5


def test_a_rate_limit_leaves_one_course_at_work(config):
    many_courses(config, courses=4, files=4)
    gateway = ParallelGateway()
    gateway.failures["a.pdf"] = [NotebookLMRateLimited("429")]
    seen_after: list[int] = []
    original = gateway.add_file

    async def watching(notebook_id, path, title):
        if not gateway.failures["a.pdf"]:
            seen_after.append(sum(gateway.in_flight.values()))
        return await original(notebook_id, path, title)

    gateway.add_file = watching

    result = run_parallel(config, gateway)

    assert len(result.added) == 16 and not result.failed
    # Those already on their way finish that file; then it is one at a time, to the end.
    assert seen_after[-8:] == [0] * 8


def test_a_rate_limited_upload_keeps_its_three_waits(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    gateway = FakeGateway()
    gateway.failures["a.pdf"] = [NotebookLMRateLimited("429"), NotebookLMRateLimited("429")]

    result = run(config, gateway)

    assert result.waits[:2] == [5.0, 15.0] and len(result.added) == 1


def test_the_gate_lets_in_as_many_as_it_says_and_narrows():
    async def scenario():
        gate = runner.CourseGate(2)
        await gate.enter("a")
        await gate.enter("b")
        third = asyncio.create_task(gate.enter("c"))
        await asyncio.sleep(0)
        assert not third.done()

        gate.slow_down()
        stepping = asyncio.create_task(gate.step("a"))
        await asyncio.sleep(0)
        assert gate.active == {"b"} and not stepping.done()  # "b" works on; "a" waits its turn
        await gate.step("b")
        assert gate.active == {"b"}

        gate.leave("b")
        await asyncio.wait({stepping, third}, return_when=asyncio.FIRST_COMPLETED)
        assert len(gate.active) == 1
        gate.leave(next(iter(gate.active)))
        await asyncio.gather(stepping, third)

    asyncio.run(scenario())


def test_every_change_to_the_record_is_saved_alone_and_whole(config, monkeypatch):
    many_courses(config)
    original = store.UploadState.save
    saves: list[dict] = []
    locks: list[bool] = []

    def watched(self):
        original(self)
        saves.append(json.loads(self.path.read_text(encoding="utf-8")))  # a whole file at every moment

    monkeypatch.setattr(store.UploadState, "save", watched)
    real_commit = runner._Execution.commit

    async def commit(self, change):
        def inside():
            locks.append(self.lock.locked())
            change()

        await real_commit(self, inside)

    monkeypatch.setattr(runner._Execution, "commit", commit)

    run_parallel(config, ParallelGateway())

    assert locks and all(locks)
    counts = [sum(len(course["files"]) for course in save["courses"].values()) for save in saves]
    assert counts == sorted(counts) and counts[-1] == 15


def test_a_stopped_parallel_run_lost_nothing_and_stops_the_others(config):
    many_courses(config)
    gateway = ParallelGateway()
    gateway.failures["b.pdf"] = [NotebookLMLoginRequired()]

    result = run_parallel(config, gateway)

    assert result.status == "login_required"
    recorded = store.UploadState.load(store.state_file(config)).data["courses"]
    uploaded = sum(len(course["files"]) for course in recorded.values())
    assert uploaded == len(gateway.added)  # the rest is still to do, and the next run does it
    assert uploaded < 15


def test_a_rate_limit_is_told_from_other_passing_failures():
    gateway = gateway_module()
    from notebooklm import NetworkError, RateLimitError

    assert isinstance(gateway.translate_exception(RateLimitError("slow down")), NotebookLMRateLimited)
    assert isinstance(gateway.translate_exception(NetworkError("HTTP 429 Too Many Requests")), NotebookLMRateLimited)
    plain = gateway.translate_exception(NetworkError("connection reset"))
    assert isinstance(plain, NotebookLMTransient) and not isinstance(plain, NotebookLMRateLimited)


# -- the gateway ----------------------------------------------------------------------------------
def gateway_module():
    pytest.importorskip("notebooklm")  # macOS only: the library is not installed elsewhere
    from blackboard_sync.notebooklm import gateway

    return gateway


def test_failures_are_sorted_into_what_can_be_done():
    gateway = gateway_module()
    import notebooklm as lib

    assert isinstance(gateway.translate_exception(lib.NetworkError("down")), NotebookLMTransient)
    assert isinstance(gateway.translate_exception(asyncio.TimeoutError()), NotebookLMTransient)
    assert isinstance(gateway.translate_exception(lib.AuthError("nope")), NotebookLMLoginRequired)
    assert isinstance(gateway.translate_exception(lib.ValidationError("bad file")), NotebookLMPermanent)
    assert isinstance(gateway.translate_exception(ValueError("odd")), NotebookLMPermanent)


def test_a_dead_session_wrapped_in_another_class_is_still_a_dead_session():
    gateway = gateway_module()
    import notebooklm as lib

    try:
        try:
            raise lib.AuthError("expired")
        except lib.AuthError as inner:
            raise lib.SourceAddError("upload failed") from inner
    except lib.SourceAddError as exc:
        assert isinstance(gateway.translate_exception(exc), NotebookLMLoginRequired)
    assert isinstance(gateway.translate_exception(RuntimeError("Run notebooklm login")), NotebookLMLoginRequired)


def test_our_own_failures_pass_through():
    gateway = gateway_module()
    failure = NotebookLMPermanent("x")
    assert gateway.translate_exception(failure) is failure


def test_the_gateway_lists_and_adds_through_the_library():
    gateway_mod = gateway_module()

    class Sources:
        async def list(self, notebook_id):
            status = type("Status", (), {"name": "READY"})
            return [type("S", (), {"id": "s1", "title": "Müh.pdf", "status": status, "created_at": None})]

        async def add_file(self, notebook_id, path, title, wait):
            assert wait is False
            return type("S", (), {"id": "s2"})

    class Notebooks:
        async def list(self):
            return [type("N", (), {"id": "n1", "title": " Müh "}), type("N", (), {"id": "n2", "title": None})]

    gateway = gateway_mod.Gateway(Path("session.json"))
    gateway._client = type("Client", (), {"sources": Sources(), "notebooks": Notebooks()})

    async def scenario():
        assert [n.id for n in await gateway.find_notebooks("Müh")] == ["n1"]
        assert await gateway.list_sources("n1") == [gateway_mod.RemoteSource("s1", "Müh.pdf", "ready")]
        assert await gateway.add_file("n1", Path("a.pdf"), "a.pdf") == "s2"
        assert await gateway.wait_ready("n1", ["s1"], 0) == {"s1": "ready"}
        assert await gateway.wait_ready("n1", ["gone"], 0) == {"gone": "missing"}

    asyncio.run(scenario())


def test_a_failing_limit_lookup_is_not_fatal():
    gateway_mod = gateway_module()

    class Settings:
        async def get_account_limits(self):
            raise RuntimeError("changed")

    gateway = gateway_mod.Gateway(Path("session.json"))
    gateway._client = type("Client", (), {"settings": Settings()})
    assert asyncio.run(gateway.source_limit()) is None


# Files that are in the notebook already, under whatever title NotebookLM left them.


@pytest.mark.parametrize("title", [
    "Lecture Notes/Week 1/Notlar_1.pptx",  # the library's rename worked
    "Notlar_1.pptx",  # it did not: the bare file name
    unicodedata.normalize("NFD", "Notlar_1.pptx"),
    "NOTLAR_1.PPTX",
    "Notlar_1",  # no extension
])
def test_every_title_notebooklm_leaves_counts_as_there(tmp_path, title):
    scan = scan_of(tmp_path, "Lecture Notes/Week 1/Notlar_1.pptx")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("old", title)], limit=50)
    assert [(a.action, a.source_id) for a in plan.actions] == [(planner.ADOPT, "old")]


def test_a_decomposed_turkish_name_matches_its_composed_path(tmp_path):
    name = "Haftalık Özet.pdf"
    scan = scan_of(tmp_path, f"Ders/{name}")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("old", unicodedata.normalize("NFD", name))], limit=50)
    assert actions(plan) == {f"Ders/{name}": planner.ADOPT}


def test_the_same_name_under_another_extension_is_another_file(tmp_path):
    scan = scan_of(tmp_path, "Syllabus.pdf")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("old", "Syllabus.docx")], limit=50)
    assert actions(plan) == {"Syllabus.pdf": planner.UPLOAD}


def test_a_name_that_could_be_several_sources_is_held_not_added(tmp_path):
    scan = scan_of(tmp_path, "Week 2/notes.pdf")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("a", "notes.pdf"), Remote("b", "Other/notes.pdf")], limit=50)
    assert actions(plan) == {"Week 2/notes.pdf": planner.HOLD}
    assert not plan.uploads


def test_two_files_cannot_both_be_the_one_bare_title(tmp_path):
    scan = scan_of(tmp_path, "Week 1/notes.pdf", "Week 2/notes.pdf")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("a", "notes.pdf")], limit=50)
    assert set(actions(plan).values()) == {planner.HOLD}


def test_an_unknown_source_with_the_same_name_stops_the_upload_even_in_another_folder(tmp_path):
    """The safety net: a file whose name is in the notebook is not added on a guess."""
    scan = scan_of(tmp_path, "Week 2/notes.pdf")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("a", "Week 1/notes.pdf")], limit=50)
    assert actions(plan) == {"Week 2/notes.pdf": planner.HOLD}


def test_a_source_known_to_hold_other_content_is_not_this_file(tmp_path):
    scan = scan_of(tmp_path, "Week 2/notes.pdf")
    state = store.UploadState(tmp_path / "s")
    state.record("T/C", "Week 1/notes.pdf", notebook_id="n", source_id="a", size=1, mtime_ns=1, sha256="other")
    plan = planner.plan_course(scan, state, matches=[Remote("n", "C")], sources=[Remote("a", "notes.pdf")], limit=50)
    assert actions(plan) == {"Week 2/notes.pdf": planner.UPLOAD}


def test_a_moved_file_is_found_by_its_content(tmp_path):
    scan = scan_of(tmp_path, "Renamed folder/new name.pdf")
    state = store.UploadState(tmp_path / "s")
    digest = store.sha256_file(scan.files[0].path)
    state.record("T/C", "Old folder/old name.pdf", notebook_id="n", source_id="a", size=1, mtime_ns=1, sha256=digest)
    plan = planner.plan_course(scan, state, matches=[Remote("n", "C")], sources=[Remote("a", "old name.pdf")], limit=50)
    assert [(a.action, a.source_id) for a in plan.actions] == [(planner.ADOPT, "a")]


def test_the_same_content_in_two_folders_goes_up_once(tmp_path):
    scan = scan_of(tmp_path, "A/x.pdf", "B/y.pdf")
    scan.files[1].path.write_bytes(scan.files[0].path.read_bytes())
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")], sources=[], limit=50)
    assert actions(plan) == {"A/x.pdf": planner.UPLOAD, "B/y.pdf": planner.HOLD}


def test_a_copy_that_failed_processing_does_not_count_as_there(tmp_path):
    scan = scan_of(tmp_path, "A/x.pdf")
    plan = planner.plan_course(scan, store.UploadState(tmp_path / "s"), matches=[Remote("n", "C")],
                               sources=[Remote("a", "x.pdf", "error")], limit=50)
    assert actions(plan) == {"A/x.pdf": planner.UPLOAD}


def test_a_held_file_is_reported_and_nothing_goes_up(config):
    write_state(config, [CS], [put(config, CS, "Week 2/notes.pdf")])
    gateway = FakeGateway([Remote("n1", "CSE301 Database")],
                          {"n1": [Remote("a", "notes.pdf"), Remote("b", "Other/notes.pdf")]})

    result = run(config, gateway)

    assert not gateway.added and len(result.held) == 1
    assert result.notice() == "1 file may already be in NotebookLM, so it was not added."
    assert store.status(config).held == 1
    assert "CSE301 Database/Week 2/notes.pdf" in result.last_run()["held_files"][0]


def test_a_failure_that_landed_is_found_while_it_is_still_preparing(config):
    write_state(config, [CS], [put(config, CS, "Week 1/a.pdf")])

    class Landing(FakeGateway):
        async def add_file(self, notebook_id, path, title):
            self.sources.setdefault(notebook_id, []).append(Remote("landed", "a.pdf", "preparing"))
            raise NotebookLMTransient("timed out")

    gateway = Landing()
    run(config, gateway)

    assert store.UploadState.load(store.state_file(config)).get_file(CS, "Week 1/a.pdf")["source_id"] == "landed"


def test_a_retry_does_not_take_an_older_source_with_the_same_name_for_its_own(config):
    entry = put(config, CS, "Week 2/a.pdf")
    write_state(config, [CS], [entry])
    state = store.UploadState(store.state_file(config))
    state.record(CS, "Week 1/a.pdf", notebook_id="n1", source_id="other", size=1, mtime_ns=1, sha256="different")
    state.save()
    gateway = FakeGateway([Remote("n1", "CSE301 Database")], {"n1": [Remote("other", "a.pdf")]})
    gateway.failures["Week 2/a.pdf"] = [NotebookLMTransient("timed out")]

    run(config, gateway)

    assert gateway.added == [("n1", "Week 2/a.pdf")]
    assert store.UploadState.load(store.state_file(config)).get_file(CS, "Week 2/a.pdf")["source_id"] == "s1"


# What the dersler-notebooklm tool uploaded before this app.


def legacy(config, course="CSE301 Database", notebook="n1", files=None):
    config.notebooklm_legacy_state.parent.mkdir(exist_ok=True)
    config.notebooklm_legacy_state.write_text(json.dumps({"version": 1, "courses": {
        course: {"notebook_id": notebook, "files": files or {}}}}), encoding="utf-8")
    return config.notebooklm_legacy_state.read_bytes()


def legacy_entry(config, folder, rel, source_id, notebook="n1", **changes):
    path = config.root / folder / rel
    info = path.stat()
    return {"notebook_id": notebook, "source_id": source_id, "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "sha256": store.sha256_file(path), "uploaded_at": "2026-10-23T10:18:47+00:00", **changes}


def test_what_the_old_tool_uploaded_is_not_added_again_under_any_title(config):
    write_state(config, [CS], [put(config, CS, "Week 1/a.pdf"), put(config, CS, "b.pdf")])
    before = legacy(config, files={"Week 1/a.pdf": legacy_entry(config, CS, "Week 1/a.pdf", "old-a"),
                                   "b.pdf": legacy_entry(config, CS, "b.pdf", "old-b")})
    gateway = FakeGateway([Remote("n1", "CSE301 Database")],
                          {"n1": [Remote("old-a", "Something the document calls itself"), Remote("old-b", "b.pdf")]})

    result = run(config, gateway)

    assert not gateway.added and not result.held
    saved = store.UploadState.load(store.state_file(config))
    assert saved.get_file(CS, "Week 1/a.pdf")["source_id"] == "old-a"
    assert saved.get_file(CS, "Week 1/a.pdf")["origin"] == store.LEGACY_TOOL
    assert config.notebooklm_legacy_state.read_bytes() == before


def test_a_legacy_import_needs_no_network_for_an_automatic_run(config):
    write_state(config, [CS], [put(config, CS, "a.pdf")])
    legacy(config, files={"a.pdf": legacy_entry(config, CS, "a.pdf", "old")})
    store.session_file(config).touch()

    assert run(config, FakeGateway(), auto=True).worked is False


def test_a_file_that_changed_since_the_old_tool_is_reported_not_added(config):
    entry = put(config, CS, "a.pdf")
    write_state(config, [CS], [entry])
    legacy(config, files={"a.pdf": legacy_entry(config, CS, "a.pdf", "old", sha256="not this content", size=1)})
    gateway = FakeGateway([Remote("n1", "CSE301 Database")], {"n1": [Remote("old", "a.pdf")]})

    result = run(config, gateway)

    assert not gateway.added and len(result.modified) == 1


def test_the_old_tools_record_of_another_notebook_counts_for_nothing(config):
    write_state(config, [CS], [put(config, CS, "Week 1/a.pdf")])
    legacy(config, files={"Week 1/a.pdf": legacy_entry(config, CS, "Week 1/a.pdf", "old", notebook="elsewhere")})
    gateway = FakeGateway([Remote("n1", "CSE301 Database")])

    run(config, gateway)

    assert gateway.added == [("n1", "Week 1/a.pdf")]


def test_a_file_already_recorded_keeps_its_entry_but_the_old_copy_is_remembered(config):
    state = store.UploadState(store.state_file(config))
    state.record(CS, "a.pdf", notebook_id="n1", source_id="new", size=1, mtime_ns=1, sha256="h")
    config.notebooklm_legacy_state.parent.mkdir()
    config.notebooklm_legacy_state.write_text(json.dumps({"courses": {"CSE301 Database": {"files": {
        "a.pdf": {"notebook_id": "n1", "source_id": "old", "size": 1, "mtime_ns": 1, "sha256": "h"}}}}}))

    assert state.import_legacy([CS], config.notebooklm_legacy_state) == 0
    assert state.get_file(CS, "a.pdf")["source_id"] == "new"
    assert state.known_sources(CS)["old"].origin == store.ORIGIN_LEGACY


@pytest.mark.parametrize("text", ["not json", "[]", '{"courses": []}', '{"courses": {"C": {"files": 1}}}'])
def test_an_unusable_old_state_is_ignored(tmp_path, text):
    path = tmp_path / "state.json"
    path.write_text(text)
    assert store.UploadState(tmp_path / "s").import_legacy(["T/C"], path) == 0


def test_a_missing_old_state_is_no_problem(tmp_path):
    assert store.UploadState(tmp_path / "s").import_legacy(["T/C"], tmp_path / "none.json") == 0


def test_the_old_state_path_can_be_set(tmp_path):
    env = {"BBSYNC_DATA_DIR": str(tmp_path), "BBSYNC_NOTEBOOKLM_LEGACY_STATE": "~/elsewhere/state.json"}
    assert Config.from_env(env).notebooklm_legacy_state == Path.home() / "elsewhere" / "state.json"
    assert Config.from_env({"BBSYNC_DATA_DIR": str(tmp_path)}).notebooklm_legacy_state.name == "state.json"


# Duplicates: listing, and removing only what is safe to remove.

OLD, NEW = "2026-10-23T10:18:00+00:00", "2026-11-06T10:53:00+00:00"


def known(rel="a.pdf", sha="h", origin=store.ORIGIN_APP):
    return store.KnownSource(rel, sha, origin)


def verdicts(sources, record):
    return [(d.older.id, [(c.id, c.verdict, c.removable) for c in d.newer])
            for d in duplicates.find_in_notebook(sources, record)]


def test_a_newer_identical_copy_this_app_added_can_go():
    sources = [Remote("new", "a.pdf", created_at=NEW), Remote("old", "Week 1/a.pdf", created_at=OLD)]
    record = {"old": known(origin=store.ORIGIN_LEGACY), "new": known()}
    assert verdicts(sources, record) == [("old", [("new", duplicates.IDENTICAL, True)])]


def test_a_file_changed_on_blackboard_keeps_both_versions():
    sources = [Remote("old", "a.pdf", created_at=OLD), Remote("new", "a.pdf", created_at=NEW)]
    record = {"old": known(sha="before", origin=store.ORIGIN_LEGACY), "new": known(sha="after")}
    assert verdicts(sources, record) == [("old", [("new", duplicates.CHANGED, False)])]


@pytest.mark.parametrize("record", [
    {},  # nothing here knows them
    {"old": known()},  # the newer copy is nobody's on this computer
    {"old": known(), "new": known(origin=store.ORIGIN_ADOPTED)},  # the app found it there
    {"old": known(), "new": known(origin=store.ORIGIN_LEGACY)},
])
def test_a_copy_this_app_did_not_add_is_listed_and_stays(record):
    sources = [Remote("old", "a.pdf", created_at=OLD), Remote("new", "a.pdf", created_at=NEW)]
    assert verdicts(sources, record) == [("old", [("new", duplicates.NOT_ADDED_BY_APP, False)])]


def test_an_older_copy_with_unknown_content_is_no_ground_for_removing_the_newer():
    sources = [Remote("hand", "a.pdf", created_at=OLD), Remote("new", "a.pdf", created_at=NEW)]
    assert verdicts(sources, {"new": known()}) == [("hand", [("new", duplicates.UNVERIFIED, False)])]


@pytest.mark.parametrize("older", [
    Remote("old", "a.pdf", "error", OLD),  # the only good copy would go
    Remote("old", "a.pdf", "ready", ""),  # no telling which is older
])
def test_the_copy_that_stays_must_be_good_and_older(older):
    sources = [older, Remote("new", "a.pdf", created_at=NEW)]
    record = {"old": known(origin=store.ORIGIN_LEGACY), "new": known()}
    assert not any(copy.removable for d in duplicates.find_in_notebook(sources, record) for copy in d.newer)


def test_two_different_files_sharing_a_name_are_no_duplicate():
    sources = [Remote("one", "notes.pdf", created_at=OLD), Remote("two", "notes.pdf", created_at=NEW)]
    assert verdicts(sources, {"one": known("A/notes.pdf", "h1"), "two": known("B/notes.pdf", "h2")}) == []


def test_each_of_two_same_named_files_has_its_own_duplicate():
    sources = [Remote("b", "notes.pdf", created_at=OLD), Remote("a", "notes.pdf", created_at="2026-10-24T00:00:00+00:00"),
               Remote("a2", "notes.pdf", created_at=NEW)]
    record = {"b": known("B/notes.pdf", "h2"), "a": known("A/notes.pdf", "h1", store.ORIGIN_LEGACY),
              "a2": known("A/notes.pdf", "h1")}
    assert verdicts(sources, record) == [("a", [("a2", duplicates.IDENTICAL, True)])]


def record_pair(config, removable=True):
    """The live case: the old tool's copy, and this app's newer one of the same file."""
    state = store.UploadState(store.state_file(config))
    state.set_notebook(CS, "n1")
    state.record(CS, "Week 1/a.pdf", notebook_id="n1", source_id="new", size=1, mtime_ns=1, sha256="h")
    state.save()
    config.notebooklm_legacy_state.parent.mkdir(exist_ok=True)
    config.notebooklm_legacy_state.write_text(json.dumps({"courses": {"CSE301 Database": {"files": {
        "Week 1/a.pdf": {"notebook_id": "n1", "source_id": "old", "size": 1, "mtime_ns": 1,
                         "sha256": "h" if removable else "older content"}}}}}))
    return FakeGateway(sources={"n1": [Remote("old", "a.pdf", created_at=OLD),
                                       Remote("hand", "b.pdf", created_at=OLD),
                                       Remote("hand2", "b.pdf", created_at=NEW),
                                       Remote("new", "Week 1/a.pdf", created_at=NEW)]})


@pytest.fixture
def gateway_of(monkeypatch):
    """Runs the duplicates step against this gateway, without its pause between removals."""
    monkeypatch.setattr(duplicates, "DELETE_DELAY_SECONDS", 0)

    def use(gateway):
        async def opener(_config):
            return gateway

        monkeypatch.setattr(runner, "open_gateway", opener)
        return gateway

    return use


def test_listing_deletes_nothing(config, gateway_of):
    gateway = gateway_of(record_pair(config))

    report = duplicates.find(config)

    assert report.status == "ok" and not gateway.deleted
    assert report.as_dict()["duplicates"] == 2 and report.as_dict()["removable"] == 1
    assert gateway.closed


def test_removing_takes_only_the_newer_copy_and_the_file_stays_known(config, gateway_of):
    gateway = gateway_of(record_pair(config))

    report = duplicates.remove(config, ["new", "old", "hand", "hand2"])

    assert gateway.deleted == ["new"]
    assert report.removed == ["CSE301 Database/Week 1/a.pdf"]
    entry = store.UploadState.load(store.state_file(config)).get_file(CS, "Week 1/a.pdf")
    assert entry["source_id"] == "old" and entry["adopted"]


def test_a_changed_file_is_not_removed_even_when_asked(config, gateway_of):
    gateway = gateway_of(record_pair(config, removable=False))

    duplicates.remove(config, ["new"])

    assert not gateway.deleted


def test_a_failed_removal_is_reported_and_leaves_the_record(config, gateway_of):
    gateway = gateway_of(record_pair(config))
    gateway.undeletable.add("new")

    report = duplicates.remove(config, ["new"])

    assert report.failed and not report.removed
    assert store.UploadState.load(store.state_file(config)).get_file(CS, "Week 1/a.pdf")["source_id"] == "new"


def test_removing_a_copy_does_not_bring_the_file_back(config, gateway_of):
    write_state(config, [CS], [put(config, CS, "Week 1/a.pdf")])
    gateway = gateway_of(record_pair(config))
    gateway.notebooks = [Remote("n1", "CSE301 Database")]
    duplicates.remove(config, ["new"])

    run(config, gateway)

    assert not gateway.added


def test_duplicates_wait_for_a_running_sync(config, gateway_of):
    gateway_of(FakeGateway())
    with run_lock(store.lock_file(config)):
        assert duplicates.find(config).status == "locked"


def test_duplicates_need_a_session(config, gateway_of):
    gateway_of(FakeGateway())
    store.session_file(config).unlink()
    assert duplicates.find(config).status == "login_required"


def cli(config, monkeypatch, *arguments, tty=False, answer=""):
    monkeypatch.setattr("sys.stdin.isatty", lambda: tty, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    monkeypatch.setenv("BBSYNC_NOTEBOOKLM_LEGACY_STATE", str(config.notebooklm_legacy_state))
    return main(["--data-dir", str(config.data_dir), "notebooklm", *arguments])


def test_the_duplicates_command_lists_as_json_and_deletes_nothing(config, monkeypatch, capsys, gateway_of):
    gateway = gateway_of(record_pair(config))

    assert cli(config, monkeypatch, "duplicates", "--json") == 0

    report = json.loads(capsys.readouterr().out)
    assert report["removable"] == 1 and not gateway.deleted
    copy = report["courses"][0]["duplicates"][0]
    assert copy["older"]["id"] == "old" and copy["newer"][0]["id"] == "new"


def test_the_duplicates_command_says_which_copy_is_which(config, monkeypatch, capsys, gateway_of):
    gateway_of(record_pair(config))
    assert cli(config, monkeypatch, "duplicates") == 0
    out = capsys.readouterr().out
    assert "a.pdf" in out and "2026-10-23" in out and "2026-11-06" in out and "can be removed" in out


def test_removing_from_a_script_needs_yes(config, monkeypatch, capsys, gateway_of):
    gateway = gateway_of(record_pair(config))

    assert cli(config, monkeypatch, "remove-duplicates") != 0

    assert not gateway.deleted


@pytest.mark.parametrize("answer, deleted", [("", []), ("n", []), ("y", ["new"])])
def test_removing_asks_first(config, monkeypatch, capsys, gateway_of, answer, deleted):
    gateway = gateway_of(record_pair(config))
    cli(config, monkeypatch, "remove-duplicates", tty=True, answer=answer)
    assert gateway.deleted == deleted


def test_yes_removes_only_the_named_copies(config, monkeypatch, capsys, gateway_of):
    gateway = gateway_of(record_pair(config))
    assert cli(config, monkeypatch, "remove-duplicates", "--yes", "--source", "other") == 0
    assert not gateway.deleted
    assert cli(config, monkeypatch, "remove-duplicates", "--yes", "--source", "new") == 0
    assert gateway.deleted == ["new"]


def test_the_gateway_reads_the_age_of_a_source_and_deletes_through_the_library():
    gateway_mod = gateway_module()
    deleted = []

    class Sources:
        async def list(self, notebook_id):
            status = type("Status", (), {"name": "READY"})
            when = datetime(2026, 10, 23, 10, 18, tzinfo=timezone.utc)
            return [type("S", (), {"id": "s1", "title": "a.pdf", "status": status, "created_at": when})]

        async def delete(self, notebook_id, source_id):
            deleted.append((notebook_id, source_id))

    gateway = gateway_mod.Gateway(Path("session.json"))
    gateway._client = type("Client", (), {"sources": Sources()})

    async def scenario():
        assert (await gateway.list_sources("n1"))[0].created_at == "2026-10-23T10:18:00+00:00"
        await gateway.delete_source("n1", "s1")

    asyncio.run(scenario())
    assert deleted == [("n1", "s1")]


def test_the_card_says_what_was_held_back_and_when_it_looks_for_duplicates(tmp_path):
    model = AppModel(Settings(base_url="https://bb.example.edu", dest=tmp_path), datetime.now(timezone.utc))
    model.notebooklm = store.NotebookLMStatus(connected=True, finished_at="2026-11-06T10:00:00+00:00", held=2)
    assert "2 held back" in main_window_model.notebooklm_card(model, datetime.now(timezone.utc)).counts
    assert model.begin_notebooklm(NOTEBOOKLM_DUPLICATES)
    card = main_window_model.notebooklm_card(model, datetime.now(timezone.utc))
    assert card.running and card.detail == main_window_model.T_NOTEBOOKLM_DUPLICATES_RUNNING


def test_the_duplicates_window_lists_both_copies_and_only_offers_what_can_go():
    copy = {"created_at": NEW, "verdict": "changed", "removable": False, "id": "x"}
    report = {"duplicates": 2, "courses": [
        {"course": "CSE301", "duplicates": [
            {"name": "a.pdf", "older": {"created_at": OLD}, "newer": [copy]},
            {"name": "b.pdf", "older": {"created_at": OLD},
             "newer": [{**copy, "verdict": "identical", "removable": True, "id": "y"}]}]},
        {"course": "Empty", "duplicates": []}]}

    assert main_window_model.removable_ids(report) == ["y"]
    assert main_window_model.duplicates_title(report).startswith("2 ")
    text = main_window_model.duplicates_text(report)
    assert "CSE301" in text and "2026-10-23" in text and "2026-11-06" in text and "Empty" not in text
    assert main_window_model.duplicates_title({"duplicates": 0}) == "No duplicates in your notebooks."


def test_the_app_lists_duplicates_through_the_child_and_survives_its_failure(monkeypatch):
    calls = []

    def fake_run(command, **_options):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='noise\n{"status": "ok"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert jobs.run_notebooklm_duplicates() == {"status": "ok"}
    assert jobs.run_notebooklm_duplicates(["a", "b"]) == {"status": "ok"}
    assert calls[0][-3:] == ["notebooklm", "duplicates", "--json"]
    assert calls[1][-4:] == ["--source", "a", "--source", "b"] and "--yes" in calls[1]

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess([], 1, stdout="", stderr=""))
    assert jobs.run_notebooklm_duplicates()["status"] == "error"
