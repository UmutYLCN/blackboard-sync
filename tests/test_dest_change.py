"""Changing the destination folder: the dialog's three choices (audit B6)."""

import errno
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from blackboard_sync import relocate
from blackboard_sync.config import Config
from blackboard_sync.menubar import settings_form
from blackboard_sync.menubar.model import (
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


def file_contents(root):
    """All files, including the hidden Markdown twins of PDF notes."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def cross_drive(monkeypatch, windows_error=False):
    rename = relocate._rename_no_replace

    def other_drive(src, dst):
        if src.parent == dst.parent:  # publishing the temp copy is on the destination drive
            return rename(src, dst)
        error = OSError(errno.EACCES if windows_error else errno.EXDEV, "different drives")
        if windows_error:
            error.winerror = 17
        raise error

    monkeypatch.setattr(relocate, "_rename_no_replace", other_drive)


# -- Taşı ---------------------------------------------------------------------

@pytest.fixture
def nested_move_fixture(config, client, fake_bb, tmp_path, monkeypatch, request):
    """Downloaded PDFs, a presentation and notes, beside the student's own file."""
    from blackboard_sync import sync as sync_mod
    from .test_windows_long_paths import COURSE, _deep_tree

    windows = request.param
    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: windows)
    monkeypatch.setattr(relocate, "is_windows", lambda platform=None: windows)
    monkeypatch.chdir(tmp_path)
    # A short source path makes Windows re-fit these names at the longer target,
    # independently of the platform's pytest temporary-directory length.
    config.dest = SHORT_DEST
    _deep_tree(fake_bb)
    fake_bb.routes[f"{COURSE}/_f1_1/attachments"]["results"].append(
        {"id": "_ap1_1", "fileName": "lecture.pptx"})
    fake_bb.files[f"{COURSE}/_f1_1/attachments/_ap1_1/download"] = b"PK presentation contents"
    synced(config, client)
    before = file_contents(config.root)
    slides = next(rel for rel in before if rel.endswith("/slides.pdf"))
    own = config.root / Path(slides).parent / "my notes.txt"
    own.write_bytes(b"student notes")
    return config, before, slides, own


@pytest.mark.parametrize("nested_move_fixture", [False, True], indirect=True, ids=["macos", "windows-paths"])
@pytest.mark.parametrize("failure", [None, "conflict", "locked"])
def test_settings_move_nested_files_and_retry(nested_move_fixture, tmp_path, monkeypatch, caplog, failure):
    from blackboard_sync.menubar import jobs
    from blackboard_sync.settings import Settings

    config, before, slides, own = nested_move_fixture
    own_rel = own.relative_to(config.root).as_posix()
    shown = sum(not Path(rel).name.startswith(".") for rel in before) + 1  # the student's file goes too
    old = config.dest
    new = tmp_path / "A longer destination location"
    # Exercise the real Settings submission and the worker used by both apps.
    app = tray(tmp_path, monkeypatch)
    app.config = config
    app.settings = Settings(config.base_url, old)
    app.model.dest = old
    monkeypatch.setattr(jobs, "synced_file_count",
                        lambda cfg, dest: relocate.count_synced_files(cfg.state_file, dest))
    placement = relocate.Placement(state(config), sync_root(new), relocate.is_windows())
    targets = {rel: placement.file(rel) for rel in [*before, own_rel]}
    if relocate.is_windows():
        assert targets[slides] != slides
    blocked = sync_root(new) / targets[slides]
    rename = relocate._rename_no_replace
    if failure == "conflict":
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_bytes(b"destination-owned")
    elif failure == "locked":
        def locked(src, dst):
            if src == config.root / slides:
                raise PermissionError(errno.EACCES, "file is open", str(src))
            return rename(src, dst)
        monkeypatch.setattr(relocate, "_rename_no_replace", locked)

    values = settings_form.FormValues(app.settings.base_url, str(new), False)
    assert app.settings_submitted(values, False) is None
    assert app.asked == [(old, new, shown)] and app.started == [MOVE_JOB]
    result = jobs.run_move_guarded(config, app.model.move_from, app.model.dest)
    assert result.status == "ok"
    assert result.kept == ([(slides, CONFLICT if failure == "conflict" else FAILED)] if failure else [])
    assert result.moved == shown - bool(failure)
    assert (sync_root(new) / targets[own_rel]).read_bytes() == b"student notes" and not own.exists()
    assert result.old_removed == (not failure)
    for rel, data in before.items():
        if failure and rel == slides:
            assert (config.root / rel).read_bytes() == data
            if failure == "locked":
                assert not blocked.exists()
            else:
                assert blocked.read_bytes() == b"destination-owned"
        else:
            assert (sync_root(new) / targets[rel]).read_bytes() == data
            assert not (config.root / rel).exists()
    if failure:
        assert str(config.root / slides) in caplog.text
        if failure == "conflict":
            blocked.unlink()
        monkeypatch.setattr(relocate, "_rename_no_replace", rename)

    # Retry from disk, after the conflict/lock clears. The failed file must still be tracked.
    again = jobs.run_move_guarded(config, old, new)
    assert again.kept == [] and again.moved == bool(failure) and again.old_removed
    assert file_contents(sync_root(new)) == {
        **{targets[rel]: data for rel, data in before.items()}, targets[own_rel]: b"student notes"}
    assert not config.root.exists()
    final = jobs.run_move_guarded(config, old, new)
    assert final.moved == 0 and final.kept == [] and final.old_removed


@pytest.mark.parametrize("nested_move_fixture", [False], indirect=True)
def test_cross_drive_copy_is_verified_before_removing_original(nested_move_fixture, tmp_path, monkeypatch):
    config, before, slides, _own = nested_move_fixture
    cross_drive(monkeypatch)
    copy = relocate.shutil.copyfileobj

    def corrupt(data, out, length):
        if Path(data.name) == config.root / slides:
            out.write(b"x" * len(before[slides]))  # same size, different contents
        else:
            copy(data, out, length)

    monkeypatch.setattr(relocate.shutil, "copyfileobj", corrupt)
    new = tmp_path / "USB"
    result = move(config, new)
    assert result.kept == [(slides, FAILED)]
    assert (config.root / slides).read_bytes() == before[slides]
    assert not (sync_root(new) / slides).exists()
    assert not result.old_removed
    assert not [p for p in new.rglob("*") if p.name.startswith(".bbsync-")]


@pytest.mark.parametrize("nested_move_fixture", [False], indirect=True)
def test_destination_hard_link_is_verified_and_original_is_removed(nested_move_fixture, tmp_path):
    config, before, slides, own = nested_move_fixture
    shown = sum(not Path(rel).name.startswith(".") for rel in before)
    new = tmp_path / "Okul"
    target = sync_root(new) / slides
    target.parent.mkdir(parents=True)
    os.link(config.root / slides, target)
    result = move(config, new)
    assert result.moved == shown + 1 and result.kept == [] and result.old_removed  # with the student's file
    assert (sync_root(new) / own.relative_to(config.root)).read_bytes() == b"student notes"
    assert target.read_bytes() == before[slides]


@pytest.mark.skipif(sys.platform == "win32", reason="Creating symlinks needs Windows developer mode")
@pytest.mark.parametrize("nested_move_fixture", [False], indirect=True)
def test_destination_link_back_to_original_is_reported_and_kept(nested_move_fixture, tmp_path, caplog):
    config, before, slides, _own = nested_move_fixture
    new = tmp_path / "Okul"
    target = sync_root(new) / slides
    target.parent.mkdir(parents=True)
    target.symlink_to((config.root / slides).resolve())
    result = move(config, new)
    assert result.kept == [(slides, FAILED)] and not result.old_removed
    assert (config.root / slides).read_bytes() == before[slides]
    assert target.read_bytes() == before[slides] and slides in caplog.text


@pytest.mark.parametrize("between_drives", [False, True])
@pytest.mark.parametrize("nested_move_fixture", [False], indirect=True)
def test_destination_appearing_during_move_is_not_overwritten(
        nested_move_fixture, tmp_path, monkeypatch, between_drives):
    config, before, slides, _own = nested_move_fixture
    new = tmp_path / "Okul"
    target = sync_root(new) / slides
    move_file = relocate._move_file
    set_hidden = relocate.set_hidden

    def appeared():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"destination-owned")

    def race(src, dst):
        if src == config.root / slides:
            if between_drives:
                return relocate._copy_then_remove(src, dst)
            appeared()
        return move_file(src, dst)

    def publish(path, hidden):
        set_hidden(path, hidden)
        if not hidden and path.parent == target.parent:
            appeared()

    monkeypatch.setattr(relocate, "_move_file", race)
    monkeypatch.setattr(relocate, "set_hidden", publish)
    result = move(config, new)
    assert result.kept == [(slides, CONFLICT)]
    assert target.read_bytes() == b"destination-owned"
    assert (config.root / slides).read_bytes() == before[slides]
    assert not result.old_removed


def test_move_takes_every_synced_file_and_nothing_is_downloaded_again(config, client, fake_bb, tmp_path):
    files = synced(config, client)
    (config.dest / CSE / "Lecture Notes" / "Week 2").mkdir()  # an empty folder an older version made
    downloads = len(fake_bb.downloads())
    before = state(config)
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.status == "ok" and result.moved == len(files) and result.kept == []
    assert files_under(sync_root(new)) == files
    assert result.old_removed and not config.dest.exists()  # it held nothing else
    assert (sync_root(new) / CSE / "Lecture Notes" / "Week 2").is_dir()  # empty folders come along
    after = state(config)
    assert after.outputs == before.outputs and after.items == before.items  # paths are relative

    config.dest = new
    report = sync(config, client)
    assert len(fake_bb.downloads()) == downloads
    assert report.totals() == {k: 0 for k in report.totals()}
    assert files_under(sync_root(new)) == files


def test_move_relocates_student_files_inside_course_folders(config, client, tmp_path):
    files = synced(config, client)
    own = {f"{CSE}/my notes.txt": b"mine",
           f"{CSE}/Lecture Notes/Week 1/exported slides.pptx": b"PK student export",
           f"{CSE}/Study/summary.pdf": b"%PDF summary"}
    for rel, data in own.items():
        (config.dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (config.dest / rel).write_bytes(data)
    (config.dest / CSE / ".DS_Store").write_bytes(b"finder")
    new = tmp_path / "Okul"

    # The Settings prompt counts what the move takes.
    assert relocate.count_synced_files(config.state_file, config.dest) == len(files) + len(own)
    result = move(config, new)

    assert result.moved == len(files) + len(own) and result.kept == []
    assert result.old_removed and not config.dest.exists()
    assert files_under(sync_root(new)) == sorted([*files, *own])
    assert all((sync_root(new) / rel).read_bytes() == data for rel, data in own.items())


def test_files_outside_the_term_folders_stay_and_are_reported(config, client, tmp_path):
    files = synced(config, client)
    (config.dest / "my plan.txt").write_bytes(b"not a course file")
    (config.dest / "Other").mkdir()
    (config.dest / "Other" / "photo.jpg").write_bytes(b"jpeg")
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.moved == len(files) and not result.old_removed
    assert sorted(result.kept) == [("Other/photo.jpg", relocate.LEFT), ("my plan.txt", relocate.LEFT)]
    assert (config.dest / "my plan.txt").read_bytes() == b"not a course file"
    assert (config.dest / "Other" / "photo.jpg").read_bytes() == b"jpeg"
    assert not (config.dest / "2026-2027 Güz").exists()  # every course file went
    assert files_under(sync_root(new)) == files


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
    rename = relocate._rename_no_replace

    def locked(src, dst):
        if str(src).endswith("hw1.pdf"):
            raise PermissionError(13, "The process cannot access the file", str(src))
        rename(src, dst)

    monkeypatch.setattr(relocate, "_rename_no_replace", locked)
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


@pytest.mark.parametrize("windows_error", [False, True])
def test_move_between_drives_copies_then_removes_the_original(config, client, tmp_path, monkeypatch, windows_error):
    files = synced(config, client)
    new = tmp_path / "USB"

    cross_drive(monkeypatch, windows_error)
    result = move(config, new)

    assert result.kept == [] and result.moved == len(files)
    assert files_under(sync_root(new)) == files
    assert (sync_root(new) / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert not config.dest.exists()


def test_copy_is_dropped_when_the_original_cannot_be_removed(config, client, tmp_path, monkeypatch):
    files = synced(config, client)
    new = tmp_path / "USB"
    cross_drive(monkeypatch)
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
    root = sync_root(new)
    every_file = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert sorted(o["path"] for o in state(config).outputs.values()) == every_file  # the state follows
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


# -- Yeniden indir ---------------------------------------------------------------

def test_redownload_fills_the_new_folder_and_leaves_the_old_one(config, client, tmp_path):
    files = synced(config, client)
    old = config.dest
    config.dest = tmp_path / "Okul"
    sync(config, client)  # the sync the choice queues: the folder mirrors Blackboard
    assert files_under(config.root) == files
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
    assert m.icon() == Icon.SYNCING and "Moving files" in m.activity()
    notes = m.finish_move("ok", 12, 0)
    assert m.busy is None and m.move_from is None and m.note == ""
    assert notes[0].message == "12 files moved to the new folder."
    assert notes[0].data == {"open": str(Path("/Volumes/USB/Okul/University"))}


def test_files_left_behind_are_reported():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    notes = m.finish_move("ok", 10, 2)
    assert "2 files could not be moved" in m.note and "2 files could not be moved" in notes[0].message


def test_locked_move_is_retried_later():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    assert m.finish_move("locked", 0, 0) == []
    assert m.pending_job() == MOVE_JOB and m.move_from == Path("/Users/ada/University")
    assert "shortly" in m.note


def test_failed_move_is_shown():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_MOVE)
    m.begin(MOVE_JOB)
    m.finish_move("error", 0, 0, "No space left on device")
    assert m.pending is None and "Could not move" in m.note


def test_redownload_choice_queues_a_sync_once_signed_in():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False, dest_choice=DEST_REFETCH)
    assert m.recent == []
    m.session = None
    assert m.pending_job() is None  # waits for the sign-in
    m.session = SESSION
    assert m.pending_job() == "sync"
    assert m.begin("sync") and m.pending is None


def test_a_new_folder_without_downloaded_files_queues_nothing():
    m = model()
    m.apply_settings(Path("/Volumes/USB/Okul"), school_changed=False)
    assert m.pending_job() is None and m.recent == []


def test_dialog_offers_move_first_and_names_both_folders():
    assert [c for c, _ in settings_form.DEST_CHOICES] == [DEST_MOVE, DEST_REFETCH]
    assert [t for _, t in settings_form.DEST_CHOICES] == ["Move", "Download again"]
    old, new = Path("/tmp/University"), Path("/tmp/Okul")
    text = settings_form.dest_change_message(old, new, 7)
    assert str(old) in text and str(new) in text and "7 files" in text
    assert "not moved" not in settings_form.T_DEST_HINT


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
    assert app.model.busy is None and app.notices[0].message == "4 files moved to the new folder."


def test_windows_dialog_defaults_to_move_and_escape_cancels(monkeypatch):
    from blackboard_sync.windows.main_window import ask_dest_choice

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
    assert ["Move", "Download again", "Cancel"] == [t for t in titles if t in (
        "Move", "Download again", "Sadece new fileslar", "Cancel")]

    widgets = []
    pressed[:] = [lambda dialog: dialog.bindings["<Escape>"](None)]
    assert ask_dest_choice(None, Path("/a"), Path("/b"), 3) is None

    widgets = []
    pressed[:] = [lambda dialog: next(w for w in widgets if w.options.get("text") == "Download again")
                  .options["command"]()]
    assert ask_dest_choice(None, Path("/a"), Path("/b"), 3) == DEST_REFETCH


# -- the macOS alert ---------------------------------------------------------------

def test_macos_alert_buttons_map_to_choices(monkeypatch):
    pytest.importorskip("AppKit")
    from blackboard_sync.menubar import main_window

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
            return main_window.NSAlertFirstButtonReturn + Alert.response

    monkeypatch.setattr(main_window, "NSAlert", Alert)
    monkeypatch.setattr(main_window, "NSApp", SimpleNamespace(activateIgnoringOtherApps_=lambda flag: None))
    expected = [DEST_MOVE, DEST_REFETCH, None]
    for response, choice in enumerate(expected):
        Alert.response = response
        assert main_window.ask_dest_choice(Path("/a"), Path("/b"), 2) == choice
    assert Alert.buttons == ["Move", "Download again", "Cancel"]


# -- Files a move used to leave behind (docs/TODO.md) ----------------------------

def _unrecorded(root, files):
    """Files on disk that state.json does not know, as a stopped sync could leave them."""
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)


def test_move_includes_files_from_interrupted_sync_before_checkpoint(config, client, tmp_path):
    files = synced(config, client)
    # Placed by a sync that was paused before it saved them (as on Windows, where
    # the process is ended without running anything).
    placed = {f"{CSE}/Lecture Notes/Week 1/Lecture 01 Slides.pptx": b"PK slides",
              f"{CSE}/Lecture Notes/Week 2/Deep Learning Notes.pdf": b"%PDF notes"}
    _unrecorded(config.root, placed)
    recorded = {o["path"] for o in state(config).outputs.values()}
    assert not set(placed) & recorded
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.status == "ok" and result.kept == [] and result.old_removed
    assert result.moved == len(files) + len(placed)
    assert files_under(sync_root(new)) == sorted([*files, *placed])
    assert all((sync_root(new) / rel).read_bytes() == data for rel, data in placed.items())
    assert not config.root.exists()


def test_move_includes_locally_annotated_file_beside_numbered_update(config, client, fake_bb, tmp_path):
    from .test_sync import SYLLABUS_DL

    synced(config, client)
    (config.root / SYLLABUS).write_bytes(b"%PDF syllabus + my highlights")
    children = fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children"]
    children["results"][0]["modified"] = "2026-10-01T00:00:00.000Z"
    fake_bb.files[SYLLABUS_DL] = b"%PDF syllabus v2"
    sync(config, client)
    update = SYLLABUS.replace("_v1.pdf", "_v1 (2).pdf")
    files = files_under(config.root)
    assert SYLLABUS in files and update in files
    new = tmp_path / "Okul"

    result = move(config, new)

    assert result.kept == [] and result.old_removed and result.moved == len(files)
    assert (sync_root(new) / SYLLABUS).read_bytes() == b"%PDF syllabus + my highlights"
    assert (sync_root(new) / update).read_bytes() == b"%PDF syllabus v2"
    assert state(config).edited_originals == [SYLLABUS]  # still tracked, relative to the new folder


def test_failed_move_does_not_leave_empty_parent_folder_at_destination(config, tmp_path, monkeypatch):
    locked_rel = f"{CSE}/Locked Module/Week 3/Slides.pptx"
    _unrecorded(config.root, {locked_rel: b"PK locked", f"{CSE}/hw.pdf": b"%PDF hw"})
    st = State.load(config.state_file)
    for key, rel in (("attachment:c:1", locked_rel), ("attachment:c:2", f"{CSE}/hw.pdf")):
        data = (config.root / rel).read_bytes()
        st.record_output(key, rel, relocate.sha256_file(config.root / rel), len(data))
    st.save()
    rename = relocate._rename_no_replace

    def locked(src, dst):
        if src == config.root / locked_rel:
            raise PermissionError(errno.EACCES, "file is open in another program", str(src))
        return rename(src, dst)

    monkeypatch.setattr(relocate, "_rename_no_replace", locked)
    new = tmp_path / "Okul"
    result = move(config, new)

    assert result.kept == [(locked_rel, FAILED)] and not result.old_removed
    assert (config.root / locked_rel).read_bytes() == b"PK locked"
    assert (sync_root(new) / CSE / "hw.pdf").read_bytes() == b"%PDF hw"
    assert not (sync_root(new) / CSE / "Locked Module").exists()


def test_read_only_file_moves_between_drives(config, client, tmp_path, monkeypatch):
    """Windows refuses to remove a read-only file; the move clears the attribute first."""
    import stat

    files = synced(config, client)
    (config.root / SYLLABUS).chmod(stat.S_IREAD)
    cross_drive(monkeypatch)
    unlink = Path.unlink

    def windows_unlink(path, missing_ok=False):
        if path.exists() and not path.lstat().st_mode & stat.S_IWRITE:
            raise PermissionError(errno.EACCES, "Access is denied", str(path))
        return unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", windows_unlink)
    new = tmp_path / "USB"
    result = move(config, new)
    assert result.kept == [] and result.moved == len(files) and result.old_removed
    assert (sync_root(new) / SYLLABUS).read_bytes() == b"%PDF syllabus v1"


def test_windows_move_disambiguates_colliding_shortened_filenames(config, tmp_path, monkeypatch):
    monkeypatch.setattr(relocate, "is_windows", lambda platform=None: True)
    monkeypatch.chdir(tmp_path)
    config.dest = SHORT_DEST
    folder = f"{CSE}/Module_05_Relational_Database_Design_" + "A" * 28
    parts = {f"{folder}/Lecture_05_Normalization_Slides_Part_{n}.pptx": f"part {n}".encode() for n in (1, 2)}
    _unrecorded(config.root, parts)
    st = State.load(config.state_file)
    for n, (rel, data) in enumerate(parts.items()):
        st.record_output(f"attachment:c:{n}", rel, relocate.sha256_file(config.root / rel), len(data))
    st.save()
    new = Path("D" * 150)  # deep enough that both names shorten to the same one

    result = move(config, new)

    assert result.kept == [] and result.moved == 2 and result.old_removed
    moved = {o["path"]: (sync_root(new) / o["path"]).read_bytes() for o in state(config).outputs.values()}
    assert sorted(moved.values()) == sorted(parts.values())
    first = min((Path(rel).name for rel in moved), key=len)
    assert {Path(rel).name for rel in moved} == {first, first.replace(".pptx", " (2).pptx")}


def test_windows_move_records_newly_shortened_folders_in_state(config, tmp_path, monkeypatch):
    from blackboard_sync.paths import ELLIPSIS

    monkeypatch.setattr(relocate, "is_windows", lambda platform=None: True)
    monkeypatch.chdir(tmp_path)
    config.dest = SHORT_DEST
    week = "Week 05 Materials " + "m" * 40  # full length at the short path, shortened at the long one
    rel = f"{CSE}/{week}/slides.pdf"
    _unrecorded(config.root, {rel: b"%PDF slides"})
    st = State.load(config.state_file)
    st.record_output("attachment:c:1", rel, relocate.sha256_file(config.root / rel), 11)
    st.save()
    assert st.folders == {}

    result = move(config, LONG_DEST)
    assert result.kept == [] and result.old_removed
    there = state(config)
    (fitted, name), = there.folders.items()
    assert name == week and ELLIPSIS in fitted
    assert there.outputs["attachment:c:1"]["path"] == f"{fitted}/slides.pdf"

    config.dest = LONG_DEST
    back = move(config, SHORT_DEST)
    assert back.kept == [] and back.old_removed
    assert state(config).outputs["attachment:c:1"]["path"] == rel  # the full name again
    assert state(config).folders == {}
    assert (sync_root(SHORT_DEST) / rel).read_bytes() == b"%PDF slides"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows ends a process without a signal")
def test_paused_sync_runs_its_finally_blocks(monkeypatch):
    import signal

    from blackboard_sync import cli

    saved = []
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit) as stopped:
        with cli._exit_on_sigterm():
            try:
                os.kill(os.getpid(), signal.SIGTERM)  # what Pause sends
                time.sleep(5)  # not reached: the handler ends the run first
            finally:
                saved.append(True)  # run_sync saves state.json here
    assert stopped.value.code == 143 and saved == [True]
    assert signal.getsignal(signal.SIGTERM) == before
