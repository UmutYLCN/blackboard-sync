"""Files an instructor attaches to an announcement are saved next to its note."""

import html
import json

from blackboard_sync.state import State

from .conftest import note_text
from .test_sync import CSE, sync

ANNOUNCEMENTS = "/learn/api/public/v1/courses/_13004_1/announcements"
FOLDER = f"{CSE}/Duyurular"
NOTE = f"{FOLDER}/2026-10-01 Exam rooms.pdf"
FILE_URL = "/bbcswebdav/pid-700-dt-asiobject-rid-911_1/xid-911_1"
STATE_KEY = "announcement:_13004_1:_n3_1"
FILE_KEY = "xid:_13004_1:announcement:_n3_1:911_1"


def file_link(xid="911_1", name="exam-rooms.pdf"):
    url = f"https://blackboard.example.edu/bbcswebdav/pid-700-dt-asiobject-rid-{xid}/xid-{xid}?token=T"
    meta = {"displayName": name, "fileName": name, "resourceUrl": url, "fileSize": 12}
    return f'<a href="{html.escape(url)}" data-bbfile="{html.escape(json.dumps(meta), quote=True)}">{name}</a>'


def add_announcement(fake_bb, body, modified="2026-10-01T08:00:00.000Z"):
    ann = {
        "id": "_n3_1", "title": "Exam rooms", "draft": False, "body": body,
        "created": "2026-10-01T08:00:00.000Z", "modified": modified,
    }
    fake_bb.routes[ANNOUNCEMENTS]["results"].append(ann)
    fake_bb.files[FILE_URL] = b"%PDF rooms"
    return ann


def warnings(report):
    return [w for c in report.courses for w in c.warnings]


def test_announcement_file_is_downloaded_and_listed_in_the_note(config, client, fake_bb):
    add_announcement(fake_bb, f"<p>Rooms are attached.</p><p>{file_link()}</p>")
    report = sync(config, client)

    assert not warnings(report)
    assert (config.root / FOLDER / "exam-rooms.pdf").read_bytes() == b"%PDF rooms"
    note = note_text(config.root / NOTE)
    assert "Rooms are attached." in note
    assert "Files saved next to this note:\n- exam-rooms.pdf\n" in note
    assert "bbcswebdav" not in note and "token" not in note
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert f"{FOLDER}/exam-rooms.pdf" in cse.new_files
    assert NOTE in cse.new_announcements


def test_announcement_without_files_keeps_the_same_note(config, client, fake_bb):
    sync(config, client)
    note = note_text(config.root / FOLDER / "2026-09-20 Welcome to CSE303.pdf")
    assert "Files saved" not in note
    assert note.startswith("# Welcome to CSE303\n\n_Announcement · CSE303 Algorithm Analysis · 2026-09-20_\n\n")
    assert fake_bb.downloads().count(FILE_URL) == 0


def test_failed_announcement_download_keeps_the_note_and_retries_only_that_file(config, client, fake_bb):
    add_announcement(fake_bb, f"<p>Rooms are attached.</p>{file_link()}")
    del fake_bb.files[FILE_URL]
    report = sync(config, client)

    assert any("Exam rooms" in w for w in warnings(report))
    assert not (config.root / FOLDER / "exam-rooms.pdf").exists()
    note = note_text(config.root / NOTE)
    assert "Rooms are attached." in note and "Files saved" not in note
    assert State.load(config.state_file).items[STATE_KEY]["partial"]

    fake_bb.files[FILE_URL] = b"%PDF rooms"
    fake_bb.calls.clear()
    report = sync(config, client)
    assert not warnings(report)
    assert fake_bb.downloads() == [FILE_URL]
    assert "- exam-rooms.pdf" in note_text(config.root / NOTE)
    assert not State.load(config.state_file).items[STATE_KEY].get("partial")


def test_unchanged_announcement_does_not_download_again(config, client, fake_bb):
    add_announcement(fake_bb, file_link())
    sync(config, client)
    assert FILE_KEY in State.load(config.state_file).items[STATE_KEY]["outputs"]

    fake_bb.calls.clear()
    report = sync(config, client)
    assert fake_bb.downloads() == []
    assert not warnings(report)
    assert (config.root / FOLDER / "exam-rooms.pdf").exists()


def test_announcement_synced_before_files_were_supported_gets_its_file(config, client, fake_bb):
    ann = add_announcement(fake_bb, "<p>Rooms are attached.</p>")
    sync(config, client)  # an older release saw no file in this announcement
    ann["body"] = f"<p>Rooms are attached.</p>{file_link()}"
    report = sync(config, client)
    assert not warnings(report)
    assert (config.root / FOLDER / "exam-rooms.pdf").exists()
    assert "- exam-rooms.pdf" in note_text(config.root / NOTE)
