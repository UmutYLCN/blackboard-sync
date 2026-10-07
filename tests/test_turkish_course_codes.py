"""Course codes with Turkish letters and the folder rename for existing users (audit B4)."""

from __future__ import annotations

import errno

import pytest

from blackboard_sync import sync as sync_mod
from blackboard_sync.paths import (
    course_code_and_title,
    course_folder_name,
    fold_course_key,
    legacy_course_folder_name,
)
from blackboard_sync.state import State

from .test_sync import files_under, sync

TERM = "2026-2027 Güz"
OLD = f"{TERM}/BİL303-1 BİL303 Algoritma Analizi"
NEW = f"{TERM}/BİL303 Algoritma Analizi"
SYLLABUS_NAME = "Syllabus/CSE303_Algorithm_Analysis_for_Computer_Engineering_Syllabus_v1.pdf"


def _turkish_course(fake_bb):
    course = fake_bb.routes["/learn/api/public/v1/users/_900_1/courses"]["results"][0]["course"]
    course["courseId"] = "BİL303-1"
    course["name"] = "BİL303 Algoritma Analizi"


def _sync_like_older_version(config, client, monkeypatch):
    """Mirror once with the ASCII-only naming that versions before this fix used."""
    monkeypatch.setattr(sync_mod, "course_folder_name", legacy_course_folder_name)
    sync(config, client)
    monkeypatch.setattr(sync_mod, "course_folder_name", course_folder_name)
    assert (config.dest / OLD).is_dir() and not (config.dest / NEW).exists()


def _recorded_paths(config):
    return sorted(o["path"] for o in State.load(config.state_file).outputs.values())


# -- recognising codes ---------------------------------------------------------

def test_P4_turkish_course_codes_are_recognised():
    assert course_code_and_title("İNG101-1", "İNG101 İngilizce I") == ("İNG101", "İngilizce I")
    assert course_folder_name("İNG101-1", "İNG101 İngilizce I", windows=False) == "İNG101 İngilizce I"
    assert course_code_and_title("TÜR101-2", "Türk Dili I") == ("TÜR101", "Türk Dili I")
    assert course_code_and_title("_x", "ÇEV201-3 Çevre Bilimi") == ("ÇEV201", "Çevre Bilimi")
    assert fold_course_key("BİL101") == "bil101"


def test_turkish_codes_are_upper_cased_the_turkish_way():
    assert course_code_and_title("işl101-1", "Giriş")[0] == "İŞL101"
    assert course_code_and_title("ısı202", "Isı Transferi")[0] == "ISI202"
    # ASCII codes keep plain upper-casing, so existing folders keep their names.
    assert course_code_and_title("phil101-1", "Philosophy")[0] == "PHIL101"


def test_decomposed_letters_still_form_one_code():
    assert course_code_and_title("BİL101-1", "Algoritmalar") == ("BİL101", "Algoritmalar")


def test_ascii_course_folders_do_not_change():
    for course_id, name in (
        ("CSE303-1", "Algorithm Analysis"),
        ("MTH201-1", "MTH201-1 Linear Algebra"),
        ("COE309-1", "COE309 - Internship I"),
        ("ORIENT", "Student Orientation"),
        ("ENG101-1", "İngilizce I"),
    ):
        for windows in (False, True):
            assert course_folder_name(course_id, name, windows=windows) == legacy_course_folder_name(
                course_id, name, windows=windows
            )


def test_legacy_folder_name_matches_what_older_versions_produced():
    assert legacy_course_folder_name("İNG101-1", "İNG101 İngilizce I", windows=False) == (
        "İNG101-1 İNG101 İngilizce I"
    )


def test_notification_line_uses_the_short_code(config, client, fake_bb):
    _turkish_course(fake_bb)
    report = sync(config, client)
    course = next(c for c in report.courses if c.folder == NEW)
    assert course.code == "BİL303"
    assert course.summary_line().startswith("BİL303: ")


# -- --course filter -----------------------------------------------------------

@pytest.mark.parametrize("wanted", ["bil303", "BIL303", "BİL303", "bİl303", "bıl303", "BİL303-1", "_13004_1"])
def test_course_filter_matches_dotted_and_dotless_i(config, client, fake_bb, wanted):
    _turkish_course(fake_bb)
    report = sync(config, client, course_filters=[wanted])
    assert [c.folder for c in report.courses] == [NEW]


def test_course_filter_folds_other_turkish_letters():
    assert fold_course_key("TÜR101") == fold_course_key("tur101") == fold_course_key("tür101")
    assert fold_course_key("ÇEV201") == "cev201"


# -- renaming folders of existing users ----------------------------------------

def test_existing_folder_is_renamed_without_downloading_again(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    before = {p.split("/", 2)[2]: (config.dest / p).read_bytes() for p in files_under(config.dest) if p.startswith(OLD)}
    downloads = len(fake_bb.downloads())

    report = sync(config, client)

    assert not (config.dest / OLD).exists()
    assert {p.split("/", 2)[2]: (config.dest / p).read_bytes() for p in files_under(config.dest) if p.startswith(NEW)} == before
    assert f"{NEW}/{SYLLABUS_NAME}" in files_under(config.dest)
    assert len(fake_bb.downloads()) == downloads
    assert report.totals() == {k: 0 for k in report.totals()}
    assert report.warnings == []
    assert [c.folder for c in report.courses if c.code == "BİL303"] == [NEW]
    # The recorded paths follow the folder, so later runs stay quiet too.
    assert not any(p.startswith(OLD + "/") for p in _recorded_paths(config))
    assert f"{NEW}/{SYLLABUS_NAME}" in _recorded_paths(config)
    again = sync(config, client)
    assert len(fake_bb.downloads()) == downloads and again.totals()["new_files"] == 0
    assert not (config.dest / OLD).exists()


def test_rename_keeps_files_the_student_added(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    (config.dest / OLD / "my notes.txt").write_text("mine", encoding="utf-8")
    sync(config, client)
    assert (config.dest / NEW / "my notes.txt").read_text(encoding="utf-8") == "mine"


def test_existing_target_keeps_the_old_folder(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    (config.dest / NEW).mkdir()
    (config.dest / NEW / "other.txt").write_text("someone else's", encoding="utf-8")
    old_files = [p for p in files_under(config.dest) if p.startswith(OLD)]
    downloads = len(fake_bb.downloads())

    report = sync(config, client)

    assert [p for p in files_under(config.dest) if p.startswith(OLD)] == old_files
    assert (config.dest / NEW / "other.txt").read_text(encoding="utf-8") == "someone else's"
    assert files_under(config.dest / NEW) == ["other.txt"]
    assert any("Kept folder" in w and "already exists" in w for w in report.warnings)
    # Syncing continues into the old folder.
    assert [c.folder for c in report.courses if c.code == "BİL303"] == [OLD]
    assert len(fake_bb.downloads()) == downloads
    assert f"{OLD}/{SYLLABUS_NAME}" in _recorded_paths(config)

    # Once the student clears the way, the next run finishes the rename.
    (config.dest / NEW / "other.txt").unlink()
    (config.dest / NEW).rmdir()
    report = sync(config, client)
    assert report.warnings == [] and not (config.dest / OLD).exists()
    assert f"{NEW}/{SYLLABUS_NAME}" in files_under(config.dest)
    assert len(fake_bb.downloads()) == downloads


def test_failed_rename_keeps_the_old_folder(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    old_files = files_under(config.dest)
    downloads = len(fake_bb.downloads())

    def locked(src, dst):
        raise PermissionError(errno.EACCES, "The process cannot access the file", str(src))

    monkeypatch.setattr(sync_mod.os, "rename", locked)
    report = sync(config, client)

    assert files_under(config.dest) == old_files
    assert not (config.dest / NEW).exists()
    assert any("Kept folder" in w and "cannot access" in w for w in report.warnings)
    assert [c.folder for c in report.courses if c.code == "BİL303"] == [OLD]
    assert len(fake_bb.downloads()) == downloads
    assert report.totals()["new_files"] == 0
    assert f"{OLD}/{SYLLABUS_NAME}" in _recorded_paths(config)


def test_rename_interrupted_before_state_was_saved(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    downloads = len(fake_bb.downloads())
    # The folder moved, then the run was killed before state.json was written.
    (config.dest / OLD).rename(config.dest / NEW)

    report = sync(config, client)

    assert report.warnings == [] and report.totals()["new_files"] == 0
    assert len(fake_bb.downloads()) == downloads
    assert f"{NEW}/{SYLLABUS_NAME}" in _recorded_paths(config)
    assert not (config.dest / OLD).exists()


def test_dry_run_does_not_rename(config, client, fake_bb, monkeypatch):
    _turkish_course(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    sync(config, client, dry_run=True)
    assert (config.dest / OLD).is_dir() and not (config.dest / NEW).exists()
