"""The folder mirrors Blackboard: missing or broken files come back, edits are kept."""

import json
import os

from blackboard_sync.state import State, intact
from tests.test_sync import CSE, SLIDES, SYLLABUS, SYLLABUS_DL, _touch_syllabus, files_under, sync

SYLLABUS_KEY = "attachment:_13004_1:_a11_1"


def recorded(config, key=SYLLABUS_KEY):
    return State.load(config.state_file).outputs[key]


def test_a_downloaded_file_records_its_modification_time(config, client):
    sync(config, client)
    entry = recorded(config)
    assert entry["mtime_ns"] == (config.dest / SYLLABUS).stat().st_mtime_ns
    assert intact(config.dest / SYLLABUS, entry)


def test_an_empty_file_is_downloaded_again(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).write_bytes(b"")  # e.g. a cloud drive or a crash left it empty
    fake_bb.calls.clear()
    report = sync(config, client)
    assert fake_bb.downloads() == [SYLLABUS_DL]
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert SYLLABUS in next(c for c in report.courses if c.code == "CSE303").new_files
    assert not any("(2)" in p for p in files_under(config.dest))


def test_a_cut_short_file_the_student_never_touched_is_downloaded_again(config, client, fake_bb):
    sync(config, client)
    path = config.dest / SYLLABUS
    stamp = path.stat().st_mtime_ns
    path.write_bytes(b"%PDF syl")  # shorter, but with the modification time we wrote it with
    os.utime(path, ns=(stamp, stamp))
    assert not intact(path, recorded(config))
    sync(config, client)
    assert path.read_bytes() == b"%PDF syllabus v1"


def test_a_file_the_student_edited_is_never_replaced(config, client, fake_bb):
    sync(config, client)
    path = config.dest / SYLLABUS
    path.write_bytes(b"%PDF syllabus v1 + my highlights")
    os.utime(path, ns=(recorded(config)["mtime_ns"] + 10**9,) * 2)  # saved later by the student
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.downloads() == []  # an edit is not damage
    _touch_syllabus(fake_bb, b"%PDF syllabus v2")
    sync(config, client)
    assert path.read_bytes() == b"%PDF syllabus v1 + my highlights"
    assert (config.dest / SYLLABUS.replace("_v1.pdf", "_v1 (2).pdf")).read_bytes() == b"%PDF syllabus v2"


def test_changed_bytes_under_our_own_modification_time_are_damage(config, client, fake_bb):
    sync(config, client)
    path = config.dest / SYLLABUS
    stamp = path.stat().st_mtime_ns
    path.write_bytes(b"%PDF sYllabus v1")  # same size, other bytes: only a hash can tell
    os.utime(path, ns=(stamp, stamp))
    _touch_syllabus(fake_bb, b"%PDF syllabus v2")  # the hash is compared once Blackboard changes it
    sync(config, client)
    assert path.read_bytes() == b"%PDF syllabus v2"
    assert not any("(2)" in p for p in files_under(config.dest))


def test_an_older_record_without_a_modification_time_keeps_old_protection(config, client, fake_bb):
    sync(config, client)
    data = json.loads(config.state_file.read_text(encoding="utf-8"))
    for entry in data["outputs"].values():
        entry.pop("mtime_ns")
    config.state_file.write_text(json.dumps(data), encoding="utf-8")
    (config.dest / SLIDES).write_bytes(b"")
    (config.dest / SYLLABUS).write_bytes(b"%PDF other")
    sync(config, client)
    assert (config.dest / SLIDES).read_bytes() == b"%PDF week 1 slides"  # empty is always damage
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF other"  # may be the student's


def test_files_taken_off_the_old_silinenler_list_come_back_once(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    data = json.loads(config.state_file.read_text(encoding="utf-8"))
    data["outputs"][SYLLABUS_KEY]["dismissed"] = True  # "Listeden kaldır" in an older version
    config.state_file.write_text(json.dumps(data), encoding="utf-8")
    sync(config, client)
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"
    assert "dismissed" not in json.loads(config.state_file.read_text(encoding="utf-8"))["outputs"][SYLLABUS_KEY]
    # A newer version on Blackboard reaches it too: "dismissed" used to hide updates for good.
    _touch_syllabus(fake_bb, b"%PDF syllabus v2")
    sync(config, client)
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v2"


def test_reading_a_state_with_dismissed_flags_does_not_rewrite_it(config, client):
    sync(config, client)
    data = json.loads(config.state_file.read_text(encoding="utf-8"))
    data["outputs"][SYLLABUS_KEY]["dismissed"] = True
    config.state_file.write_text(json.dumps(data), encoding="utf-8")
    before = config.state_file.read_bytes()
    state = State.load(config.state_file, backup=False)  # what the window does
    assert "dismissed" not in state.outputs[SYLLABUS_KEY] and state.dirty
    assert config.state_file.read_bytes() == before


def test_a_deleted_video_an_older_version_saved_is_not_fetched_again(config, client, fake_bb):
    sync(config, client)
    state = State.load(config.state_file)
    video = f"{CSE}/Syllabus/intro.mp4"
    state.record_output("attachment:_13004_1:_old_video", video, "sha", 9)
    state.items["content:_13004_1:_c11_1"]["outputs"].append("attachment:_13004_1:_old_video")
    state.dirty = True
    state.save()
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.calls and not any("/contents/_c11_1/attachments" in call for call in fake_bb.calls)
    assert not (config.dest / video).exists()


def test_a_dry_run_lists_what_would_come_back(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    fake_bb.calls.clear()
    report = sync(config, client, dry_run=True)
    assert SYLLABUS in next(c for c in report.courses if c.code == "CSE303").new_files
    assert fake_bb.downloads() == [] and not (config.dest / SYLLABUS).exists()


def test_a_second_run_after_a_restore_downloads_nothing(config, client, fake_bb):
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    sync(config, client)
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.downloads() == []
