"""Deep course trees stay within Windows' path limit (audit B9)."""

from __future__ import annotations

import errno
import os
import sys
from pathlib import PureWindowsPath

import pytest

from blackboard_sync import sync as sync_mod
from blackboard_sync.paths import (
    ELLIPSIS,
    MIN_FOLDER_CHARS,
    WINDOWS_FILE_ROOM,
    WINDOWS_MAX_PATH,
    fit_windows_folder,
    fit_windows_path,
    join_rel,
    sanitize_name,
)
from blackboard_sync.state import State

from .test_sync import CSE, files_under, sync

COURSE = "/learn/api/public/v1/courses/_13004_1/contents"
STUDENT_BASE = PureWindowsPath(r"C:\Users\ogrenci.soyadi\OneDrive - ISTUN\Belgeler\University")
MODULE_TITLE = "Haftalık Ders Materyalleri ve Okuma Listesi - " + "Uzun başlık " * 10
DOC_TITLE = "Week 05 - Normalization, Functional Dependencies and Decomposition Examples " * 2
MODULE = sanitize_name(MODULE_TITLE, windows=True)
DOC = sanitize_name(DOC_TITLE, windows=True)
SLIDES = b"%PDF deep slides"


def _folder(item_id, title, position=9):
    return {
        "id": item_id, "title": title, "position": position, "hasChildren": True,
        "modified": "2026-09-01T10:00:00.000Z", "contentHandler": {"id": "resource/x-bb-folder"},
    }


def _deep_tree(fake_bb):
    """Course > 120-character module > 120-character document > slides.pdf and a note."""
    fake_bb.routes[COURSE]["results"].append(_folder("_m1_1", MODULE_TITLE))
    fake_bb.routes[f"{COURSE}/_m1_1/children"] = {"results": [_folder("_d1_1", DOC_TITLE, 0)]}
    fake_bb.routes[f"{COURSE}/_d1_1/children"] = {
        "results": [
            {
                "id": "_f1_1", "title": "slides.pdf", "position": 0,
                "modified": "2026-09-30T10:00:00.000Z",
                "contentHandler": {"id": "resource/x-bb-file", "file": {"fileName": "slides.pdf"}},
            },
            {
                "id": "_n1_1", "title": "Reading for this week", "position": 1,
                "modified": "2026-09-30T10:00:00.000Z",
                "contentHandler": {"id": "resource/x-bb-document"},
                "body": "<p>Chapter 14, sections 1 to 3.</p>",
            },
        ]
    }
    fake_bb.routes[f"{COURSE}/_f1_1/attachments"] = {
        "results": [{"id": "_af1_1", "fileName": "slides.pdf", "mimeType": "application/pdf"}]
    }
    fake_bb.routes[f"{COURSE}/_n1_1/attachments"] = {"results": []}
    fake_bb.files[f"{COURSE}/_f1_1/attachments/_af1_1/download"] = SLIDES


def _deep_files(config):
    return [f for f in files_under(config.dest) if f.startswith(f"{CSE}/Haftalık")]


def _windows(monkeypatch):
    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: True)


def _sync_like_older_version(config, client, monkeypatch):
    """Mirror once with full folder names, as versions before this fix did."""
    monkeypatch.setattr(sync_mod, "fit_windows_folder", lambda base, parent, name: name)
    sync(config, client)
    monkeypatch.setattr(sync_mod, "fit_windows_folder", fit_windows_folder)
    assert (config.dest / CSE / MODULE / DOC / "slides.pdf").read_bytes() == SLIDES


def _recorded_paths(config):
    return sorted(o["path"] for o in State.load(config.state_file).outputs.values())


# -- naming --------------------------------------------------------------------

def test_P9_deep_folders_are_shortened_to_fit_max_path():
    rel = join_rel("2026-2027 Güz", "CSE303 Algorithm Analysis for Computer Engineering")
    # Before: only the file name was shortened, giving a 378-character path.
    assert len(str(STUDENT_BASE)) + 1 + len(join_rel(rel, MODULE, DOC, "slides.pdf")) == 378
    for name in (MODULE, DOC):
        rel = join_rel(rel, fit_windows_folder(STUDENT_BASE, rel, name))
    assert len(str(STUDENT_BASE)) + 1 + len(rel) <= WINDOWS_MAX_PATH - WINDOWS_FILE_ROOM
    full = fit_windows_path(STUDENT_BASE, join_rel(rel, "slides.pdf"))
    assert full.endswith("/slides.pdf")
    assert len(str(STUDENT_BASE)) + 1 + len(full) <= WINDOWS_MAX_PATH
    module, doc = rel.split("/")[2:]
    assert module.startswith("Haftalık Ders Materyalleri") and ELLIPSIS in module
    assert doc.startswith("Week 05 - Norma") and ELLIPSIS in doc


def test_short_folder_names_are_kept():
    assert fit_windows_folder(STUDENT_BASE, "2026-2027 Güz/CSE303 Algorithm Analysis", "Week 1") == "Week 1"
    assert fit_windows_folder(STUDENT_BASE, "", "2026-2027 Güz") == "2026-2027 Güz"


def test_shortened_names_keep_their_end_so_siblings_stay_apart():
    parent = "2026-2027 Güz/CSE303 Algorithm Analysis/" + "Unit " * 12
    part1 = fit_windows_folder(STUDENT_BASE, parent, DOC + " Part 1")
    part2 = fit_windows_folder(STUDENT_BASE, parent, DOC + " Part 2")
    assert part1 != part2
    assert part1.endswith("Part 1") and part2.endswith("Part 2")
    room = WINDOWS_MAX_PATH - WINDOWS_FILE_ROOM - (len(str(STUDENT_BASE)) + 1 + len(parent) + 1)
    assert len(part1) == room // 2


def test_folder_names_never_get_shorter_than_the_minimum():
    deep = "x" * 230
    name = fit_windows_folder(STUDENT_BASE, deep, DOC)
    assert MIN_FOLDER_CHARS - 2 <= len(name) <= MIN_FOLDER_CHARS
    assert name.startswith("Week 05") and ELLIPSIS in name and not name.endswith((" ", "."))


# -- syncing -------------------------------------------------------------------

def test_deep_course_tree_syncs_within_the_limit(config, client, fake_bb, monkeypatch):
    _windows(monkeypatch)
    _deep_tree(fake_bb)
    report = sync(config, client)

    assert report.warnings == [] and all(c.warnings == [] for c in report.courses)
    deep = _deep_files(config)
    assert len(deep) == 2
    slides = next(f for f in deep if f.endswith("/slides.pdf"))
    assert (config.dest / slides).read_bytes() == SLIDES
    assert any(f.endswith("/Reading for this week.md") for f in deep)
    assert all(len(str(config.dest)) + 1 + len(f) <= WINDOWS_MAX_PATH for f in files_under(config.dest))
    # The same folders are chosen again: nothing new, nothing downloaded twice.
    downloads = len(fake_bb.downloads())
    again = sync(config, client)
    assert again.totals() == {k: 0 for k in again.totals()}
    assert len(fake_bb.downloads()) == downloads
    assert _deep_files(config) == deep


def test_macos_keeps_full_folder_names(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: False)
    _deep_tree(fake_bb)
    sync(config, client)
    module, doc = sanitize_name(MODULE_TITLE, windows=False), sanitize_name(DOC_TITLE, windows=False)
    assert (config.dest / CSE / module / doc / "slides.pdf").read_bytes() == SLIDES


def test_existing_long_folders_are_renamed_without_downloading_again(config, client, fake_bb, monkeypatch):
    _windows(monkeypatch)
    _deep_tree(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    (config.dest / CSE / MODULE / DOC / "my notes.txt").write_text("mine", encoding="utf-8")
    before = len(files_under(config.dest))
    downloads = len(fake_bb.downloads())

    report = sync(config, client)

    assert report.warnings == [] and all(c.warnings == [] for c in report.courses)
    assert report.totals() == {k: 0 for k in report.totals()}
    assert len(fake_bb.downloads()) == downloads
    assert not (config.dest / CSE / MODULE).exists()
    # Every file moved along, none was duplicated, and the student's own file is kept.
    assert len(files_under(config.dest)) == before
    deep = _deep_files(config)
    assert (config.dest / next(f for f in deep if f.endswith("/slides.pdf"))).read_bytes() == SLIDES
    assert (config.dest / next(f for f in deep if f.endswith("/my notes.txt"))).read_text(encoding="utf-8") == "mine"
    assert not any(MODULE in p for p in _recorded_paths(config))
    assert all(len(str(config.dest)) + 1 + len(f) <= WINDOWS_MAX_PATH for f in files_under(config.dest))


def test_failed_rename_keeps_using_the_long_folder(config, client, fake_bb, monkeypatch):
    _windows(monkeypatch)
    _deep_tree(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    old_files = files_under(config.dest)
    downloads = len(fake_bb.downloads())

    def locked(src, dst):
        raise PermissionError(errno.EACCES, "The process cannot access the file", str(src))

    monkeypatch.setattr(sync_mod.os, "rename", locked)
    report = sync(config, client)

    assert files_under(config.dest) == old_files
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert any("Kept folder" in w and "cannot access" in w for w in cse.warnings)
    assert len(fake_bb.downloads()) == downloads and report.totals()["new_files"] == 0
    assert f"{CSE}/{MODULE}/{DOC}/slides.pdf" in _recorded_paths(config)


def test_dry_run_does_not_rename(config, client, fake_bb, monkeypatch):
    _windows(monkeypatch)
    _deep_tree(fake_bb)
    _sync_like_older_version(config, client, monkeypatch)
    old_files = files_under(config.dest)
    sync(config, client, dry_run=True)
    assert files_under(config.dest) == old_files


# -- a real Windows file system ------------------------------------------------
# CI runs these two again with LongPathsEnabled switched off (Windows'
# default) and BBSYNC_TEST_MAX_PATH=1, so MAX_PATH is really enforced.

@pytest.mark.skipif(os.environ.get("BBSYNC_TEST_MAX_PATH") != "1", reason="needs Windows with long paths off")
def test_runner_enforces_max_path(tmp_path):
    with pytest.raises(OSError):
        (tmp_path / ("d" * 120) / ("e" * 120) / ("f" * 120)).mkdir(parents=True)


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows file system")
def test_deep_course_tree_on_real_windows(config, client, fake_bb):
    _deep_tree(fake_bb)
    assert len(str(config.dest)) >= len(str(STUDENT_BASE))
    report = sync(config, client)

    assert report.warnings == [] and all(c.warnings == [] for c in report.courses)
    deep = _deep_files(config)
    assert (config.dest / next(f for f in deep if f.endswith("/slides.pdf"))).read_bytes() == SLIDES
    assert any(f.endswith("/Reading for this week.md") for f in deep)
