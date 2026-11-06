"""Adding the synced files to NotebookLM: what goes up, and the rules around it. No network here."""

import asyncio
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from blackboard_sync.config import Config
from blackboard_sync.errors import (
    BlackboardSyncError,
    NotebookLMLoginRequired,
    NotebookLMPermanent,
    NotebookLMTransient,
)
from blackboard_sync.notebooklm import planner, runner, signin, store
from blackboard_sync.notebooklm.planner import CourseScan, FileInfo
from blackboard_sync.state import State

TERM = "2026-2027 Güz"


@dataclass
class Remote:
    id: str
    title: str
    status: str = "ready"


class FakeGateway:
    """The ``Gateway`` surface, in memory."""

    def __init__(self, notebooks=(), sources=None, limit=300):
        self.notebooks = list(notebooks)
        self.sources = {key: list(value) for key, value in (sources or {}).items()}
        self.limit = limit
        self.added: list[tuple[str, str]] = []
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

    async def wait_ready(self, notebook_id, source_ids, timeout):
        return {source_id: self.processing for source_id in source_ids}

    async def close(self):
        self.closed = True


def put(config, folder, rel, data=b"content", kind="attachment", name=None):
    """A file the sync downloaded, recorded in its state."""
    path = f"{folder}/{rel}"
    target = config.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return f"{kind}:_1_1:{name or path}", {"path": path, "sha256": "x", "size": len(data)}


@pytest.fixture
def config(tmp_path):
    made = Config(dest=tmp_path / "dest", data_dir=tmp_path / "data")
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
        path.write_bytes(b"data")
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
    assert stat.S_IMODE(store.state_file(config).stat().st_mode) == 0o600


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
    assert events[-1] == {"event": "progress", "done": 2, "total": 2, "course": "CSE301 Database"}


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
        self.cookies = list(cookies)

    def storage_state(self):
        return {"cookies": [{"name": name, "value": "v"} for name in self.cookies], "origins": []}


class FakeBrowser:
    def __init__(self, *timeline):
        self.timeline = list(timeline)
        self.closed = False

    def is_connected(self):
        return True

    @property
    def contexts(self):
        return [self.timeline.pop(0) if len(self.timeline) > 1 else self.timeline[0]]

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

    assert stat.S_IMODE(store.session_file(config).stat().st_mode) == 0o600
    assert not store.status(config).needs_login
    assert "--remote-debugging-port=12345" in started[0]
    assert signin.SIGN_IN_URL in started[0]


def test_a_session_google_rejects_is_not_kept(config, signin_seams):
    _started, spawn_run = signin_seams

    def check(_config):
        raise NotebookLMLoginRequired()

    with pytest.raises(NotebookLMLoginRequired):
        signin.login(config, run=spawn_run, connect=lambda url: FakeBrowser(SIGNED_IN), check=check, platform="darwin")
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
    with pytest.raises(BlackboardSyncError, match="needs Chrome, Edge or Brave"):
        signin.login(config, platform="darwin")


def test_a_free_port_is_a_real_port():
    assert signin.free_port() > 0


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
            return [type("S", (), {"id": "s1", "title": "Müh.pdf", "status": status})]

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
