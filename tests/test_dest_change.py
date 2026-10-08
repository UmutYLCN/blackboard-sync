"""Changing the destination folder: the dialog's three choices (audit B6)."""

import errno
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from blackboard_sync import relocate
from blackboard_sync.config import Config
from blackboard_sync.menubar import settings_form
from blackboard_sync.menubar.model import (
    DEST_KEEP,
    DEST_MOVE,
    DEST_REFETCH,
    MOVE_JOB,
    AppModel,
    Icon,
    RecentItem,
)
from blackboard_sync.relocate import CONFLICT, FAILED, move_destination, move_files
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock, run_sync
from blackboard_sync.system import sync_root

from .test_sync import CSE, SYLLABUS, files_under

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
SESSION = {"saved_at": 0, "user": {"displayName": "Ada Student"}}


def sync(config, client, **kwargs):
    return run_sync(config, client, now=NOW, **kwargs)


def synced(config, client):
    """A first sync into ``config.dest``'s University folder; returns its files."""
    sync(config, client)
    return files_under(config.root)


def state(config):
    return State.load(config.state_file)


def move(config, new):
    return move_destination(config.state_file, config.lock_file, config.dest, new)


# -- Taşı ---------------------------------------------------------------------

def test_move_takes_every_synced_file_and_nothing_is_downloaded_again(config, client, fake_bb, tmp_path):
    files = synced(config, client)
    downloads = len(fake_bb.downloads())
    before = state(config)
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.status == "ok" and result.moved == len(files) and result.kept == []
    assert files_under(sync_root(new)) == files
    assert result.old_removed and not config.dest.exists()  # it held nothing else
    assert (sync_root(new) / CSE / "Lecture Notes" / "Week 2").is_dir()  # empty Blackboard folders come along
    after = state(config)
    assert after.outputs == before.outputs and after.items == before.items  # paths are relative

    config.dest = new
    report = sync(config, client)
    assert len(fake_bb.downloads()) == downloads
    assert report.totals() == {k: 0 for k in report.totals()}
    assert files_under(sync_root(new)) == files


def test_move_leaves_the_students_own_files_and_their_folder(config, client, tmp_path):
    files = synced(config, client)
    own = config.dest / CSE / "my notes.txt"
    own.write_text("mine", encoding="utf-8")
    (config.dest / CSE / ".DS_Store").write_bytes(b"finder")
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.moved == len(files) and not result.old_removed
    assert own.read_text(encoding="utf-8") == "mine"
    assert files_under(config.dest) == [f"{CSE}/.DS_Store", f"{CSE}/my notes.txt"]
    assert files_under(sync_root(new)) == files
    # Only the folder with the student's file is left.
    assert [p.name for p in (config.dest / "2026-2027 Güz").iterdir()] == ["CSE303 Algorithm Analysis"]
    assert [p.name for p in config.dest.iterdir()] == ["2026-2027 Güz"]


def test_old_folder_with_only_system_leftovers_is_removed(config, client, tmp_path):
    synced(config, client)
    (config.dest / ".DS_Store").write_bytes(b"finder")
    (config.dest / CSE / "Thumbs.db").write_bytes(b"explorer")
    result = move(config, tmp_path / "Okul")
    assert result.kept == [] and result.old_removed and not config.dest.exists()


def test_conflicting_file_in_the_new_folder_is_never_overwritten(config, client, tmp_path):
    files = synced(config, client)
    new = tmp_path / "Okul"
    (sync_root(new) / SYLLABUS).parent.mkdir(parents=True)
    (sync_root(new) / SYLLABUS).write_bytes(b"another file")

    result = move(config, new)

    assert result.kept == [(SYLLABUS, CONFLICT)]
    assert result.moved == len(files) - 1
    assert (sync_root(new) / SYLLABUS).read_bytes() == b"another file"
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert not result.old_removed and config.dest.is_dir()


def test_identical_file_already_in_the_new_folder_counts_as_moved(config, client, tmp_path):
    files = synced(config, client)
    new = tmp_path / "Okul"
    (sync_root(new) / SYLLABUS).parent.mkdir(parents=True)
    (sync_root(new) / SYLLABUS).write_bytes(b"%PDF syllabus v1")

    result = move(config, new)

    assert result.kept == [] and result.moved == len(files)
    assert files_under(sync_root(new)) == files and not config.dest.exists()


def test_locked_file_stays_and_keeps_the_old_folder(config, client, tmp_path, monkeypatch):
    files = synced(config, client)
    new = tmp_path / "Okul"
    rename = os.rename

    def locked(src, dst):
        if str(src).endswith("hw1.pdf"):
            raise PermissionError(13, "The process cannot access the file", str(src))
        rename(src, dst)

    monkeypatch.setattr(relocate.os, "rename", locked)
    result = move(config, new)

    assert result.kept == [(f"{CSE}/hw1.pdf", FAILED)]
    assert result.moved == len(files) - 1 and not result.old_removed
    assert files_under(config.dest) == [f"{CSE}/hw1.pdf"]
    assert not (sync_root(new) / CSE / "hw1.pdf").exists()


def test_files_deleted_by_the_student_stay_deleted(config, client, tmp_path):
    files = synced(config, client)
    (config.dest / SYLLABUS).unlink()
    new = tmp_path / "Okul"
    result = move(config, new)
    assert result.kept == [] and result.moved == len(files) - 1
    assert SYLLABUS not in files_under(sync_root(new))


def test_move_between_drives_copies_then_removes_the_original(config, client, tmp_path, monkeypatch):
    files = synced(config, client)
    new = tmp_path / "USB"

    def other_drive(src, dst):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(relocate.os, "rename", other_drive)
    result = move(config, new)

    assert result.kept == [] and result.moved == len(files)
    assert files_under(sync_root(new)) == files
    assert (sync_root(new) / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert not config.dest.exists()


def test_copy_is_dropped_when_the_original_cannot_be_removed(config, client, tmp_path, monkeypatch):
    files = synced(config, client)
    new = tmp_path / "USB"
    monkeypatch.setattr(relocate.os, "rename", lambda src, dst: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    unlink = Path.unlink

    def open_in_reader(self, *args, **kwargs):
        if self.name == "hw1.pdf" and config.dest in self.parents:
            raise PermissionError(13, "in use", str(self))
        unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", open_in_reader)
    result = move(config, new)

    assert result.kept == [(f"{CSE}/hw1.pdf", FAILED)] and result.moved == len(files) - 1
    assert (config.dest / CSE / "hw1.pdf").is_file()
    assert not (sync_root(new) / CSE / "hw1.pdf").exists()
    assert not [p for p in new.rglob("*") if p.name.startswith(".bbsync-")]


def test_move_into_a_subfolder_of_the_old_one(config, client):
    files = synced(config, client)
    new = config.dest / "Blackboard"
    result = move(config, new)
    assert result.kept == [] and result.moved == len(files)
    assert files_under(sync_root(new)) == files
    assert files_under(config.dest) == [f"Blackboard/University/{f}" for f in files]


def test_same_folder_moves_nothing(config, client):
    files = synced(config, client)
    result = move(config, config.dest / ".")
    assert result.moved == 0 and files_under(config.dest) == files


def test_move_waits_for_a_running_sync(config, client, tmp_path):
    files = synced(config, client)
    with run_lock(config.lock_file):
        result = move(config, tmp_path / "Okul")
    assert result.status == "locked" and files_under(config.dest) == files


def test_count_of_synced_files_decides_whether_to_ask(config, client, tmp_path):
    assert relocate.count_synced_files(config.state_file, config.dest) == 0
    files = synced(config, client)
    assert relocate.count_synced_files(config.state_file, config.dest) == len(files)
    assert relocate.count_synced_files(config.state_file, tmp_path / "elsewhere") == 0


def test_move_files_keeps_state_untouched(config, client, tmp_path):
    synced(config, client)
    loaded = state(config)
    move_files(loaded, config.dest, tmp_path / "Okul")
    assert not loaded.dirty


# -- Windows: folder names follow the new destination's path budget -------------

# Relative to the test's folder, so the lengths do not depend on where pytest keeps it.
SHORT_DEST = Path("U")
# As long as a OneDrive "Belgeler" folder, so deep folders get shortened more.
LONG_DEST = Path(("OneDrive - ISTUN " * 4).strip()) / "Belgeler" / "University"


@pytest.mark.parametrize("direction", ["to a longer path", "to a shorter path"])
def test_windows_move_renames_folders_for_the_new_path_budget(config, client, fake_bb, tmp_path, monkeypatch, direction):
    from blackboard_sync import sync as sync_mod
    from blackboard_sync.paths import ELLIPSIS, WINDOWS_MAX_PATH

    from .test_windows_long_paths import SLIDES, _deep_tree

    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: True)
    monkeypatch.setattr(relocate, "is_windows", lambda platform=None: True)
    _deep_tree(fake_bb)
    monkeypatch.chdir(tmp_path)
    old, new = (SHORT_DEST, LONG_DEST) if direction == "to a longer path" else (LONG_DEST, SHORT_DEST)
    config.dest = old
    files = synced(config, client)
    assert any(ELLIPSIS in f for f in files)
    downloads = len(fake_bb.downloads())

    result = move(config, new)

    assert result.status == "ok" and result.kept == [] and result.moved == len(files)
    assert not sync_root(old).exists()  # the chosen folder itself is not ours to remove
    moved = files_under(sync_root(new))
    assert len(moved) == len(files) and moved != files  # the shortened folders were named again
    assert all(len(str(sync_root(new))) + 1 + len(f) <= WINDOWS_MAX_PATH for f in moved)
    assert sorted(o["path"] for o in state(config).outputs.values()) == moved  # the state follows
    slides = next(f for f in moved if f.endswith("/slides.pdf"))
    assert (sync_root(new) / slides).read_bytes() == SLIDES

    # A sync in the new folder picks exactly these folders: nothing new, nothing doubled.
    config.dest = new
    report = sync(config, client)
    assert report.warnings == [] and all(c.warnings == [] for c in report.courses)
    assert report.totals() == {k: 0 for k in report.totals()}
    assert len(fake_bb.downloads()) == downloads
    assert files_under(sync_root(new)) == moved
    # No second copy of a shortened folder appeared next to the moved one.
    course = sync_root(new) / CSE
    assert len([p for p in course.iterdir() if p.is_dir() and p.name.startswith("Haftalık")]) == 1


def test_windows_sync_records_full_names_of_shortened_folders(config, client, fake_bb, monkeypatch):
    from blackboard_sync import sync as sync_mod
    from blackboard_sync.paths import ELLIPSIS

    from .test_windows_long_paths import DOC, MODULE, _deep_tree

    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: True)
    _deep_tree(fake_bb)
    monkeypatch.chdir(config.dest.parent)
    config.dest = LONG_DEST
    sync(config, client)
    folders = state(config).folders
    assert sorted(folders.values()) == sorted([MODULE, DOC])
    assert all(ELLIPSIS in Path(rel).name for rel in folders)


# -- Yeniden indir / Sadece yeni dosyalar ---------------------------------------

def test_redownload_fills_the_new_folder_and_leaves_the_old_one(config, client, tmp_path):
    files = synced(config, client)
    old = config.dest
    config.dest = tmp_path / "Okul"
    sync(config, client, refetch_missing=True)
    assert files_under(config.root) == files
    assert files_under(old) == files


def test_new_files_only_leaves_the_new_folder_empty_of_old_content(config, client, tmp_path):
    files = synced(config, client)
    old = config.dest
    config.dest = tmp_path / "Okul"
    report = sync(config, client)
    assert report.totals()["new_files"] == 0
    assert files_under(old) == files


# -- what the app does with the choice -----------------------------------------

def model(**kwargs):
    m = AppModel(dest=Path("/Users/ada/University"), now=NOW,
                 recent=[RecentItem("a.pdf", "CSE303", NOW.isoformat())], **kwargs)
    m.session = SESSION
    return m


def test_move_choice_queues_the_move_before_any_sync():
    m = model()
    m.next_run_at = NOW - timedelta(minutes=1)  # a sync is overdue too
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    assert m.pending_job() == MOVE_JOB and m.move_from == Path("/Users/ada/University")
    assert len(m.recent) == 1  # still valid: the files keep their place under the new folder
    assert m.begin(MOVE_JOB) and m.pending is None
    assert m.icon() == Icon.SYNCING and "taşınıyor" in m.activity()
    notes = m.finish_move("ok", 12, 0)
    assert m.busy is None and m.move_from is None and m.note == ""
    assert notes[0].message == "12 dosya yeni klasöre taşındı."
    assert notes[0].data == {"open": str(Path("/Volumes/USB/Okul/University"))}


def test_files_left_behind_are_reported():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    notes = m.finish_move("ok", 10, 2)
    assert "2 dosya taşınamadı" in m.note and "2 dosya taşınamadı" in notes[0].message


def test_locked_move_is_retried_later():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    assert m.finish_move("locked", 0, 0) == []
    assert m.pending_job() == MOVE_JOB and m.move_from == Path("/Users/ada/University")
    assert "birazdan" in m.note


def test_failed_move_is_shown():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    m.finish_move("error", 0, 0, "No space left on device")
    assert m.pending is None and "taşınamadı" in m.note


def test_redownload_choice_queues_a_refetch_once_signed_in():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_REFETCH)
    assert m.recent == []
    m.session = None
    assert m.pending_job() is None  # waits for the sign-in
    m.session = SESSION
    assert m.pending_job() == "refetch"
    assert m.begin("refetch") and m.pending is None


def test_new_files_only_choice_queues_nothing():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_KEEP)
    assert m.pending_job() is None and m.recent == []


def test_dialog_offers_move_first_and_names_both_folders():
    assert [c for c, _ in settings_form.DEST_CHOICES] == [DEST_MOVE, DEST_REFETCH, DEST_KEEP]
    assert [t for _, t in settings_form.DEST_CHOICES] == ["Taşı", "Yeniden indir", "Sadece yeni dosyalar"]
    old, new = Path("/tmp/University"), Path("/tmp/Okul")
    text = settings_form.dest_change_message(old, new, 7)
    assert str(old) in text and str(new) in text and "7 dosya" in text
    assert "taşınmaz" not in settings_form.T_DEST_HINT


# -- the Windows tray app --------------------------------------------------------

def tray(tmp_path, monkeypatch, files=0, choice=DEST_MOVE):
    from blackboard_sync.menubar import jobs
    from blackboard_sync.settings import Settings
    from blackboard_sync.windows import app as module

    app = module.TrayApp.__new__(module.TrayApp)
    app.config = Config(data_dir=tmp_path / "data", dest=tmp_path / "old")
    app.settings = Settings("https://old.school.edu", tmp_path / "old")
    app.model = AppModel(app.settings.dest, NOW)
    app.login_after_job = False
    app.window = None
    app.save = lambda: None
    app.refresh = lambda: None
    app.started, app.asked, app.notices = [], [], []
    app.post_notifications = app.notices.extend
    app.start_job = app.started.append
    app.ask_dest_choice = lambda old, new, n: app.asked.append((old, new, n)) or choice
    monkeypatch.setattr(module.autostart, "set_enabled", lambda enabled: None)
    monkeypatch.setattr(jobs, "synced_file_count", lambda config, dest: files)
    return app


def test_windows_asks_only_when_the_old_folder_has_files(tmp_path, monkeypatch):
    from blackboard_sync.menubar.settings_form import FormValues

    app = tray(tmp_path, monkeypatch, files=0)
    assert app.settings_submitted(FormValues("https://old.school.edu", str(tmp_path / "new"), False), False) is None
    assert app.asked == [] and app.model.pending is None


def test_windows_move_choice_saves_and_starts_the_move(tmp_path, monkeypatch):
    from blackboard_sync.menubar.settings_form import FormValues

    app = tray(tmp_path, monkeypatch, files=5)
    assert app.settings_submitted(FormValues("https://old.school.edu", str(tmp_path / "new"), False), False) is None
    assert app.asked == [(tmp_path / "old", tmp_path / "new", 5)]
    assert app.started == [MOVE_JOB] and app.model.move_from == tmp_path / "old"
    assert (tmp_path / "data" / "settings.json").exists()


def test_windows_cancel_keeps_the_old_folder(tmp_path, monkeypatch):
    from blackboard_sync.menubar.settings_form import FormValues

    app = tray(tmp_path, monkeypatch, files=5, choice=None)
    error = app.settings_submitted(FormValues("https://old.school.edu", str(tmp_path / "new"), False), False)
    assert error == (settings_form.T_DEST_NOT_CHANGED, "dest")
    assert app.model.dest == tmp_path / "old" and not (tmp_path / "data" / "settings.json").exists()


def test_windows_new_school_signs_in_after_the_move(tmp_path, monkeypatch):
    from blackboard_sync.menubar.settings_form import FormValues

    app = tray(tmp_path, monkeypatch, files=5)
    app.start_job = lambda job: app.started.append(job) or app.model.begin(job)
    assert app.settings_submitted(FormValues("new.school.edu", str(tmp_path / "new"), False), False) is None
    assert app.started == [MOVE_JOB] and app.login_after_job
    app.job_done(MOVE_JOB, relocate.MoveResult(moved=3))
    assert app.started == [MOVE_JOB, "login"] and not app.login_after_job


def test_windows_runs_the_move_job_on_a_worker(tmp_path, monkeypatch):
    import queue

    from blackboard_sync.menubar import jobs
    from blackboard_sync.windows import app as module

    app = tray(tmp_path, monkeypatch)
    del app.start_job
    app.events, app.closed = queue.Queue(), False
    app.root = SimpleNamespace(event_generate=lambda *a, **kw: None)
    app.notices = []
    app.post_notifications = app.notices.extend
    calls = []
    monkeypatch.setattr(jobs, "run_move_guarded", lambda config, old, new: calls.append((old, new))
                        or relocate.MoveResult(moved=4))

    class Thread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(module.threading, "Thread", Thread)
    app.model.apply_settings(tmp_path / "new", school_changed=False, dest_choice=DEST_MOVE)
    app.start_next()
    callback, args = app.events.get_nowait()
    callback(*args)
    assert calls == [(tmp_path / "old", tmp_path / "new")]
    assert app.model.busy is None and app.notices[0].message == "4 dosya yeni klasöre taşındı."


def test_windows_dialog_defaults_to_move_and_escape_cancels(monkeypatch):
    from blackboard_sync.windows.settings_window import ask_dest_choice

    pressed = []

    class Widget:
        def __init__(self, *args, **kwargs):
            self.options, self.bindings = kwargs, {}
            widgets.append(self)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

        def bind(self, key, callback):
            self.bindings[key] = callback

        def wait_window(self):
            pressed[0](self)

    ttk = SimpleNamespace(Frame=Widget, Label=Widget, Button=Widget)
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(Toplevel=Widget, ttk=ttk))

    widgets = []
    pressed[:] = [lambda dialog: dialog.bindings["<Return>"](None)]
    assert ask_dest_choice(None, Path("/a"), Path("/b"), 3) == DEST_MOVE
    titles = [w.options.get("text") for w in widgets]
    assert ["Taşı", "Yeniden indir", "Sadece yeni dosyalar", "Vazgeç"] == [t for t in titles if t in (
        "Taşı", "Yeniden indir", "Sadece yeni dosyalar", "Vazgeç")]

    widgets = []
    pressed[:] = [lambda dialog: dialog.bindings["<Escape>"](None)]
    assert ask_dest_choice(None, Path("/a"), Path("/b"), 3) is None

    widgets = []
    pressed[:] = [lambda dialog: next(w for w in widgets if w.options.get("text") == "Yeniden indir")
                  .options["command"]()]
    assert ask_dest_choice(None, Path("/a"), Path("/b"), 3) == DEST_REFETCH


# -- the macOS alert ---------------------------------------------------------------

def test_macos_alert_buttons_map_to_choices(monkeypatch):
    pytest.importorskip("AppKit")
    from blackboard_sync.menubar import settings_window

    class Button:
        def setKeyEquivalent_(self, key):
            self.key = key

    class Alert:
        response = 0
        buttons: list = []

        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            Alert.buttons = []
            return self

        def setMessageText_(self, text):
            self.title = text

        def setInformativeText_(self, text):
            self.text = text

        def addButtonWithTitle_(self, title):
            Alert.buttons.append(title)
            return Button()

        def runModal(self):
            return settings_window.NSAlertFirstButtonReturn + Alert.response

    monkeypatch.setattr(settings_window, "NSAlert", Alert)
    monkeypatch.setattr(settings_window, "NSApp", SimpleNamespace(activateIgnoringOtherApps_=lambda flag: None))
    expected = [DEST_MOVE, DEST_REFETCH, DEST_KEEP, None]
    for response, choice in enumerate(expected):
        Alert.response = response
        assert settings_window.ask_dest_choice(Path("/a"), Path("/b"), 2) == choice
    assert Alert.buttons == ["Taşı", "Yeniden indir", "Sadece yeni dosyalar", "Vazgeç"]
