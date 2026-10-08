"""The University folder inside the chosen folder, and moving an older version's files into it."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from blackboard_sync import cli, deleted, relocate, uninstall
from blackboard_sync.config import Config
from blackboard_sync.menubar import jobs, settings_form
from blackboard_sync.menubar.model import MOVE_JOB, AppModel, RunOutcome
from blackboard_sync.relocate import CONFLICT, FAILED, move_destination
from blackboard_sync.settings import Settings, save_settings
from blackboard_sync.state import State
from blackboard_sync.system import sync_root

from .test_past_terms import COURSE as PAST_COURSE, PAST, archive  # noqa: F401 (fixture)
from .test_sync import CSE, SYLLABUS, files_under, sync

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def icloud(config, tmp_path):
    """The student chose a folder that is not called University, like iCloud Drive."""
    config.dest = tmp_path / "iCloud Drive"
    return config


def legacy_layout(config, client):
    """What an older version left: the term folders directly in the chosen folder.

    Synced into ``dest/University`` first, then lifted one level up, with the
    state as an older version wrote it (no ``university_folder`` flag).
    """
    sync(config, client)
    files = files_under(config.root)
    for child in list(config.root.iterdir()):
        shutil.move(str(child), str(config.dest / child.name))
    config.root.rmdir()
    data = json.loads(config.state_file.read_text(encoding="utf-8"))
    data.pop("university_folder")
    config.state_file.write_text(json.dumps(data), encoding="utf-8")
    assert files_under(config.dest) == files
    return files


def cli_sync(config, client, monkeypatch, capsys, *args):
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_u1"}, "cookies": []}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    code = cli.main(["--data-dir", str(config.data_dir), "--base-url", config.base_url,
                     "sync", "--json", "--dest", str(config.dest), *args])
    return code, json.loads(capsys.readouterr().out)


# -- the rule --------------------------------------------------------------------

@pytest.mark.parametrize("dest, root", [
    (PurePosixPath("/Users/ada/Library/Mobile Documents/com~apple~CloudDocs"),
     PurePosixPath("/Users/ada/Library/Mobile Documents/com~apple~CloudDocs/University")),
    (PurePosixPath("/Users/ada/Documents/University"), PurePosixPath("/Users/ada/Documents/University")),
    (PurePosixPath("/Volumes/USB/university"), PurePosixPath("/Volumes/USB/university")),
    (PurePosixPath("/Volumes/USB/UNIVERSITY"), PurePosixPath("/Volumes/USB/UNIVERSITY")),
    (PurePosixPath("/Volumes/USB/University old"), PurePosixPath("/Volumes/USB/University old/University")),
    (PureWindowsPath(r"C:\Users\ada\iCloudDrive"), PureWindowsPath(r"C:\Users\ada\iCloudDrive\University")),
    (PureWindowsPath(r"C:\Users\ada\OneDrive\Belgeler\University"),
     PureWindowsPath(r"C:\Users\ada\OneDrive\Belgeler\University")),
    (PureWindowsPath(r"D:\Okul\uNiVeRsItY"), PureWindowsPath(r"D:\Okul\uNiVeRsItY")),
    (PureWindowsPath("D:\\"), PureWindowsPath(r"D:\University")),
])
def test_files_go_into_a_university_folder_unless_the_folder_is_one(dest, root):
    assert sync_root(dest) == root
    assert type(sync_root(dest)) is type(dest)


def test_config_keeps_the_chosen_folder_and_derives_the_root(tmp_path):
    config = Config(dest=tmp_path / "iCloud Drive", data_dir=tmp_path / "data")
    assert config.dest == tmp_path / "iCloud Drive"
    assert config.root == tmp_path / "iCloud Drive" / "University"
    assert Config(dest=tmp_path / "University", data_dir=tmp_path / "data").root == tmp_path / "University"


# -- every writer uses it --------------------------------------------------------

def test_sync_writes_into_the_university_folder(icloud, client):
    report = sync(icloud, client)
    files = files_under(icloud.dest)
    assert files and all(f.startswith("University/2026-2027 Güz/") for f in files)
    assert report.dest == str(icloud.root)
    # Recorded paths stay relative to the University folder.
    assert {o["path"] for o in State.load(icloud.state_file).outputs.values()} == set(files_under(icloud.root))


def test_folder_already_named_university_gets_no_second_one(config, client):
    config.dest = config.dest.parent / "UNIVERSITY"
    sync(config, client)
    assert (config.dest / CSE).is_dir() and not (config.dest / "University").exists()


def test_past_term_download_goes_into_the_university_folder(icloud, client, archive):  # noqa: F811
    sync(icloud, client, term_name=PAST)
    assert (icloud.root / PAST_COURSE / "first.pdf").read_bytes() == b"first archive file"
    assert not (icloud.dest / PAST_COURSE).exists()


def test_stale_partials_are_cleaned_in_the_university_folder(icloud, client):
    partial = icloud.root / CSE / ".bbsync-old.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"half")
    import os
    os.utime(partial, (0, 0))
    sync(icloud, client)
    assert not partial.exists()


def test_deleted_tab_lists_and_dismisses_in_the_university_folder(icloud, client):
    sync(icloud, client)
    (icloud.root / SYLLABUS).unlink()
    rows = deleted.load_missing(icloud, icloud.dest)
    assert [row.path for row in rows] == [SYLLABUS]
    deleted.dismiss_missing(icloud, icloud.dest, [rows[0].key])
    assert deleted.load_missing(icloud, icloud.dest) == []


def test_refetch_selection_restores_into_the_university_folder(icloud, client):
    sync(icloud, client)
    (icloud.root / SYLLABUS).unlink()
    key = deleted.load_missing(icloud, icloud.dest)[0].key
    report = sync(icloud, client, refetch_missing=True, refetch_keys={key})
    assert (icloud.root / SYLLABUS).is_file() and report.message.startswith("1 dosya")


def _trash(trashed):
    return lambda p: trashed.append(p) or (p.unlink() if p.is_file() else p.rmdir())


def test_uninstall_trashes_the_files_in_the_university_folder(icloud, client):
    sync(icloud, client)
    own = icloud.dest / "Pages" / "kendi.txt"
    own.parent.mkdir(parents=True)
    own.write_text("mine")
    assert uninstall.trash_course_files(icloud, send_to_trash=_trash([])) == []
    assert files_under(icloud.dest) == ["Pages/kendi.txt"] and own.read_text() == "mine"


def test_uninstall_trashes_the_university_folder_once_it_is_empty(icloud):
    rel = f"{CSE}/slides.pdf"
    (icloud.root / rel).parent.mkdir(parents=True)
    (icloud.root / rel).write_bytes(b"pdf")
    state = State(icloud.state_file)
    state.record_output("a", rel, "hash", 3)
    state.save()
    trashed = []
    assert uninstall.trash_course_files(icloud, send_to_trash=_trash(trashed)) == []
    assert trashed[-1] == icloud.root and not icloud.root.exists() and icloud.dest.is_dir()


def test_uninstall_also_finds_files_an_older_version_left_in_the_chosen_folder(icloud, client):
    files = legacy_layout(icloud, client)
    trashed = []
    uninstall.trash_course_files(icloud, send_to_trash=_trash(trashed))
    assert {icloud.dest / f for f in files} <= set(trashed)
    assert files_under(icloud.dest) == [] and icloud.dest.is_dir()


def test_uninstall_dialog_and_menu_name_the_university_folder(tmp_path):
    model = AppModel(dest=tmp_path / "iCloud Drive", now=NOW)
    assert model.root == tmp_path / "iCloud Drive" / "University"
    assert next(e for e in model.menu(NOW).entries if e.action == "folder").title == "University klasörünü aç"


# -- the one-time move ----------------------------------------------------------

def test_first_sync_after_the_update_moves_the_files_and_downloads_nothing(icloud, client, fake_bb,
                                                                          monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    (icloud.dest / "Pages").mkdir()
    own = icloud.dest / "Pages" / "kendi.txt"
    own.write_text("mine")
    downloads = len(fake_bb.downloads())

    code, report = cli_sync(icloud, client, monkeypatch, capsys)

    assert code == 0 and report["status"] == "ok"
    assert report["moved_into_root"] == len(files) and report["left_outside_root"] == []
    assert report["totals"] == {k: 0 for k in report["totals"]}  # nothing new, nothing again
    assert len(fake_bb.downloads()) == downloads
    assert files_under(icloud.root) == files
    # Only the student's own file is left; the emptied term folder is gone.
    assert files_under(icloud.dest) == ["Pages/kendi.txt", *[f"University/{f}" for f in files]]
    assert not (icloud.dest / "2026-2027 Güz").exists()
    assert own.read_text() == "mine"
    assert State.load(icloud.state_file).in_university_folder


def test_the_move_runs_only_once(icloud, client, monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    cli_sync(icloud, client, monkeypatch, capsys)
    # Later a copy shows up directly in the chosen folder again: it is not ours to move.
    copy = icloud.dest / SYLLABUS
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b"%PDF syllabus v1")

    code, report = cli_sync(icloud, client, monkeypatch, capsys)

    assert code == 0 and report["moved_into_root"] == 0
    assert copy.exists() and files_under(icloud.root) == files


def test_conflicting_and_locked_files_stay_and_are_reported(icloud, client, monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    conflict = icloud.root / SYLLABUS
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b"another file")
    rename = relocate.os.rename

    def locked(src, dst):
        if str(src).endswith("hw1.pdf"):
            raise PermissionError(13, "in use", str(src))
        rename(src, dst)

    monkeypatch.setattr(relocate.os, "rename", locked)
    code, report = cli_sync(icloud, client, monkeypatch, capsys)

    assert code == 0
    assert sorted(report["left_outside_root"]) == sorted([SYLLABUS, f"{CSE}/hw1.pdf"])
    assert report["moved_into_root"] == len(files) - 2
    assert conflict.read_bytes() == b"another file"  # never overwritten
    assert (icloud.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert (icloud.dest / CSE / "hw1.pdf").is_file()
    outcome = RunOutcome.from_report(report)
    assert outcome.moved_into_root == len(files) - 2 and outcome.left_outside_root == 2


def test_migration_reports_conflicts_with_reasons(icloud, client):
    legacy_layout(icloud, client)
    (icloud.root / SYLLABUS).parent.mkdir(parents=True)
    (icloud.root / SYLLABUS).write_bytes(b"another file")
    state = State.load(icloud.state_file)
    result = relocate.migrate_to_root(state, icloud.dest)
    assert result.kept == [(SYLLABUS, CONFLICT)]
    assert relocate.migrate_to_root(state, icloud.dest) is None  # recorded: never again


def test_nothing_to_move_for_a_folder_named_university(config, client):
    sync(config, client)
    state = State.load(config.state_file)
    state.in_university_folder = False
    assert not relocate.migration_pending(state, config.dest)
    result = relocate.migrate_to_root(state, config.dest)
    assert result.moved == 0 and result.kept == [] and state.in_university_folder


def test_a_new_install_needs_no_move_and_writes_no_state(icloud):
    state = State.load(icloud.state_file)
    assert relocate.migrate_to_root(state, icloud.dest) is None
    assert not icloud.state_file.exists()


def test_dry_run_moves_nothing(icloud, client, monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    code, report = cli_sync(icloud, client, monkeypatch, capsys, "--dry-run")
    assert code == 0 and report["moved_into_root"] == 0
    assert files_under(icloud.dest) == files


def test_move_happens_even_when_the_session_expired(icloud, client, fake_bb, monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    fake_bb.expired = True
    code, report = cli_sync(icloud, client, monkeypatch, capsys)
    assert report["status"] == "login_required"
    assert report["moved_into_root"] == len(files) and files_under(icloud.root) == files


def test_cli_text_output_mentions_the_move(icloud, client, monkeypatch, capsys):
    files = legacy_layout(icloud, client)
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_u1"}, "cookies": []}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    assert cli.main(["--data-dir", str(icloud.data_dir), "--base-url", icloud.base_url,
                     "sync", "--dest", str(icloud.dest)]) == 0
    assert f"Moved {len(files)} file(s) into {icloud.root}" in capsys.readouterr().out


# -- the apps ----------------------------------------------------------------------

def test_app_start_queues_the_move_before_any_sync(icloud, client):
    files = legacy_layout(icloud, client)
    save_settings(icloud.data_dir, Settings(base_url=icloud.base_url, dest=icloud.dest))
    model = jobs.load_model(icloud, NOW, autostart=False)
    assert model.pending_job() == MOVE_JOB and model.move_from == icloud.dest and model.migrating
    assert model.begin(MOVE_JOB)
    assert "University klasörüne taşınıyor" in model.activity()

    result = jobs.run_move_guarded(icloud, model.move_from, model.dest)

    assert result.status == "ok" and result.moved == len(files) and result.kept == []
    assert files_under(icloud.root) == files
    notes = model.finish_move(result.status, result.moved, len(result.kept))
    assert [(n.title, n.message) for n in notes] == [
        ("Dosyalar University klasörüne taşındı", f"{len(files)} dosya University klasörüne taşındı.")]
    assert notes[0].data == {"open": str(icloud.root)}
    assert model.move_from is None and model.note == ""
    # Afterwards nothing is pending at the next start.
    assert jobs.load_model(icloud, NOW, autostart=False).pending is None


def test_app_start_queues_nothing_for_a_current_layout(icloud, client):
    sync(icloud, client)
    save_settings(icloud.data_dir, Settings(base_url=icloud.base_url, dest=icloud.dest))
    assert jobs.load_model(icloud, NOW, autostart=False).pending is None


def test_sync_outcome_with_a_move_notifies_in_turkish(tmp_path):
    model = AppModel(dest=tmp_path / "iCloud Drive", now=NOW)
    model.begin("sync")
    outcome = RunOutcome("ok", finished_at=NOW, moved_into_root=12, left_outside_root=2)
    notes = model.finish_sync(outcome, NOW)
    assert notes[0].title == "Bazı dosyalar taşınamadı"
    assert notes[0].message == "12 dosya University klasörüne taşındı. 2 dosya taşınamadı ve eski yerinde kaldı."
    assert notes[0].data == {"open": str(tmp_path / "iCloud Drive" / "University")}
    assert "2 dosya taşınamadı" in model.note


def test_sync_outcome_without_a_move_has_no_move_notification(tmp_path):
    model = AppModel(dest=tmp_path / "iCloud Drive", now=NOW)
    model.begin("sync")
    assert model.finish_sync(RunOutcome("ok", finished_at=NOW), NOW) == []


# -- changing the folder ---------------------------------------------------------

def test_destination_change_moves_between_university_folders(icloud, client, tmp_path):
    sync(icloud, client)
    files = files_under(icloud.root)
    new = tmp_path / "USB"
    result = move_destination(icloud.state_file, icloud.lock_file, icloud.dest, new)
    assert result.moved == len(files) and files_under(new / "University") == files
    assert not icloud.root.exists() and icloud.dest.is_dir()  # the chosen folder is left alone


def test_destination_change_brings_along_files_not_yet_moved_in(icloud, client, tmp_path):
    files = legacy_layout(icloud, client)
    new = tmp_path / "Okul" / "University"
    assert relocate.count_synced_files(icloud.state_file, icloud.dest) == len(files)
    result = move_destination(icloud.state_file, icloud.lock_file, icloud.dest, new)
    assert result.status == "ok" and result.moved == len(files) and result.kept == []
    assert files_under(new) == files and files_under(icloud.dest) == []
    assert State.load(icloud.state_file).in_university_folder


def test_choosing_the_university_folder_itself_is_no_change(tmp_path):
    current = Settings("https://blackboard.example.edu", tmp_path / "iCloud Drive")
    values = settings_form.FormValues("https://blackboard.example.edu", str(tmp_path / "iCloud Drive" / "University"),
                                      False)
    assert not settings_form.submit(values, current).dest_changed
    values.dest = str(tmp_path / "USB")
    assert settings_form.submit(values, current).dest_changed
    model = AppModel(dest=current.dest, now=NOW, recent=[])
    model.courses = ["kept"]
    model.apply_settings(tmp_path / "iCloud Drive" / "University", school_changed=False)
    assert model.courses == ["kept"] and model.root == tmp_path / "iCloud Drive" / "University"


def test_folder_change_question_names_the_university_folders(tmp_path):
    text = settings_form.dest_change_message(Path("/tmp/iCloud"), Path("/tmp/Okul"), 3)
    assert str(Path("/tmp/iCloud/University")) in text and str(Path("/tmp/Okul/University")) in text


def test_note_under_the_folder_field():
    assert settings_form.T_DEST_HINT.startswith(
        "Dosyalar seçtiğiniz klasörün içindeki University klasörüne kaydedilir.")


def test_failed_moves_keep_their_reason(icloud, client, monkeypatch):
    legacy_layout(icloud, client)
    monkeypatch.setattr(relocate.os, "rename", lambda src, dst: (_ for _ in ()).throw(PermissionError(13, "x")))
    result = relocate.migrate_to_root(State.load(icloud.state_file), icloud.dest)
    assert result.moved == 0 and result.kept and all(reason == FAILED for _rel, reason in result.kept)
