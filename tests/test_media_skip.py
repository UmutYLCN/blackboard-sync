"""Videos and audio are never downloaded: they become links in the item's note."""

import html
import json

import pytest

from blackboard_sync.api import BlackboardClient
from blackboard_sync.errors import SkippedMedia
from blackboard_sync.state import State
from blackboard_sync.sync import Syncer

from .conftest import SAMPLE_FILES
from .test_announcement_files import add_announcement
from .test_past_terms import COURSE as PAST_COURSE, PAST, ROOT as PAST_ROOT, archive  # noqa: F401
from .test_sync import COURSE, CSE, NOW, files_under, sync

HEADING = "Videos and audio (open in Blackboard):"
BASE = "https://blackboard.example.edu"
BIG = b"\0" * (3 << 20)


def attach(fake_bb, item_id, att_id, file_name, mime=None, body=BIG, title="Lecture", handler="resource/x-bb-file"):
    """A content item with one attachment; returns the attachment's download path."""
    item = {
        "id": item_id, "title": title, "position": 9, "modified": "2026-09-30T10:00:00.000Z",
        "contentHandler": {"id": handler},
    }
    fake_bb.routes[COURSE]["results"].append(item)
    att = {"id": att_id, "fileName": file_name}
    if mime:
        att["mimeType"] = mime
    fake_bb.routes[f"{COURSE}/{item_id}/attachments"] = {"results": [att]}
    path = f"{COURSE}/{item_id}/attachments/{att_id}/download"
    fake_bb.files[path] = body
    return path


def bb_file(xid, name, mime=None):
    meta = {"displayName": name, "fileName": name}
    if mime:
        meta["mimeType"] = mime
    url = f"{BASE}/bbcswebdav/pid-7-dt-content-rid-{xid}/xid-{xid}?t=TOKEN"
    return f'<a href="{html.escape(url)}" data-bbfile="{html.escape(json.dumps(meta), quote=True)}">{name}</a>'


def add_document(fake_bb, item_id, body="", description=None):
    item = {
        "id": item_id, "title": "Week recording", "position": 9, "modified": "2026-09-30T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-document"}, "body": body,
    }
    if description:
        item["description"] = description
    fake_bb.routes[COURSE]["results"].append(item)
    fake_bb.routes[f"{COURSE}/{item_id}/attachments"] = {"results": []}


def bodies(fake_bb):
    """Download paths whose body was read, apart from the fixture course's own files."""
    return [p for p in fake_bb.bodies_read if p not in SAMPLE_FILES]


def tree(config):
    return files_under(config.dest)


def no_partials(config):
    return not [p for p in config.dest.rglob(".bbsync-*")]


def test_video_attachment_and_embedded_video_are_links_not_downloads(config, client, fake_bb):
    """The scout's E1: nothing is downloaded, the note links both, a second run asks for nothing."""
    video = attach(fake_bb, "_v1_1", "_va_1", "lecture1.mp4", "video/mp4")
    add_document(fake_bb, "_v2_1", f"<p>Recording:</p>{bb_file('900_1', 'week1-recording.mp4', 'video/mp4')}")
    embedded = "/bbcswebdav/xid-900_1"
    fake_bb.files[embedded] = BIG

    report = sync(config, client)

    assert bodies(fake_bb) == [] and bodies(fake_bb) == []
    assert not [w for c in report.courses for w in c.warnings]
    assert not any(f.endswith((".mp4", ".partial")) for f in tree(config)) and no_partials(config)
    attachment_note = (config.dest / CSE / "Lecture.md").read_text(encoding="utf-8")
    assert f"{HEADING}\n- lecture1.mp4: <{BASE}{video}>\n" in attachment_note
    note = (config.dest / CSE / "Week recording.md").read_text(encoding="utf-8")
    assert f"{HEADING}\n- week1-recording.mp4: <{BASE}/bbcswebdav/xid-900_1>\n" in note
    assert "Recording:" in note and "Files saved" not in note and "TOKEN" not in note

    fake_bb.calls.clear()
    second = sync(config, client)
    assert not any("_v1_1" in c or "_v2_1" in c or c == embedded for c in fake_bb.calls)
    assert second.totals() == {k: 0 for k in second.totals()}
    assert bodies(fake_bb) == []


def test_skipped_files_are_recorded_so_the_item_is_not_reprocessed(config, client, fake_bb):
    add_document(fake_bb, "_v2_1", bb_file("900_1", "week1-recording.mp4", "video/mp4"))
    sync(config, client)

    item = State.load(config.state_file).items["content:_13004_1:_v2_1"]
    assert item["media"] == ["xid:_13004_1:_v2_1:900_1"] and not item.get("partial")
    # even when the files are checked for being missing (past-term and refetch runs)
    assert State.load(config.state_file).item_unchanged(
        "content:_13004_1:_v2_1", "2026-09-30T10:00:00.000Z", config.dest, True
    )


@pytest.mark.parametrize("mime", ["audio/mpeg", "audio/x-m4a", "VIDEO/WebM"])
def test_audio_and_other_video_types_are_links(config, client, fake_bb, mime):
    attach(fake_bb, "_v1_1", "_va_1", "talk", mime)
    sync(config, client)
    assert bodies(fake_bb) == []
    assert "- talk: <" in (config.dest / CSE / "Lecture.md").read_text(encoding="utf-8")


def test_media_extension_without_a_mime_type_is_skipped_before_any_request(config, client, fake_bb):
    path = attach(fake_bb, "_v1_1", "_va_1", "Podcast ep 1.MP3")
    attach(fake_bb, "_v3_1", "_va_3", "clip.mov", "application/octet-stream", title="Clip")
    sync(config, client)
    assert path not in fake_bb.calls and bodies(fake_bb) == []
    assert (config.dest / CSE / "Lecture.md").read_text(encoding="utf-8").count("- Podcast ep 1.MP3: <") == 1
    assert "- clip.mov: <" in (config.dest / CSE / "Clip.md").read_text(encoding="utf-8")


def test_video_content_type_header_stops_the_download_before_the_body(config, client, fake_bb):
    """Nothing in the listing says video: the response headers do."""
    path = attach(fake_bb, "_v1_1", "_va_1", "session-5", "application/octet-stream")
    fake_bb.content_types[path] = "video/mp4"

    report = sync(config, client)

    assert path in fake_bb.calls and bodies(fake_bb) == []
    assert not [w for c in report.courses for w in c.warnings]
    assert no_partials(config) and not any("session-5" in f for f in tree(config) if f != f"{CSE}/Lecture.md")
    assert "- session-5: <" in (config.dest / CSE / "Lecture.md").read_text(encoding="utf-8")


def test_header_gate_leaves_no_temporary_file(tmp_path, client, fake_bb):
    path = "/bbcswebdav/xid-5_1"
    fake_bb.files[path], fake_bb.content_types[path] = BIG, "audio/mpeg"
    into = tmp_path / "out"
    into.mkdir()

    with pytest.raises(SkippedMedia) as skipped:
        client.download(path, into, expected_name="x.bin")

    assert list(into.iterdir()) == [] and bodies(fake_bb) == []
    assert skipped.value.content_type == "audio/mpeg"


def test_download_gate_checks_the_name_from_the_server(tmp_path, client, fake_bb):
    path = "/bbcswebdav/xid-5_1"
    fake_bb.files[path] = BIG
    real = fake_bb.get

    def named(url, **kwargs):
        resp = real(url, **kwargs)
        resp.headers["Content-Disposition"] = 'attachment; filename="lesson.mkv"'
        return resp

    fake_bb.get = named
    with pytest.raises(SkippedMedia):
        BlackboardClient("https://blackboard.example.edu", fake_bb).download(path, tmp_path, expected_name="file")
    assert list(tmp_path.iterdir()) == [] and bodies(fake_bb) == []


def test_unknown_large_file_is_still_downloaded(config, client, fake_bb):
    path = attach(fake_bb, "_v1_1", "_va_1", "dataset.bin", "application/octet-stream", title="Data")
    attach(fake_bb, "_v2_1", "_va_2", "notes.pdf", "application/pdf", body=b"%PDF", title="Notes")
    sync(config, client)
    assert (config.dest / CSE / "dataset.bin").read_bytes() == BIG
    assert (config.dest / CSE / "notes.pdf").read_bytes() == b"%PDF"
    assert path in bodies(fake_bb)
    assert not (config.dest / CSE / "Data.md").exists()  # a plain file still needs no note


def test_an_item_with_a_video_and_a_pdf_keeps_the_pdf_and_links_the_video(config, client, fake_bb):
    fake_bb.routes[COURSE]["results"].append({
        "id": "_m1_1", "title": "Week 3", "position": 9, "modified": "2026-09-30T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-document"}, "body": "",
    })
    base = f"{COURSE}/_m1_1/attachments"
    fake_bb.routes[base] = {"results": [
        {"id": "_p_1", "fileName": "slides.pdf", "mimeType": "application/pdf"},
        {"id": "_q_1", "fileName": "week3.mp4", "mimeType": "video/mp4"},
    ]}
    fake_bb.files[f"{base}/_p_1/download"] = b"%PDF"
    fake_bb.files[f"{base}/_q_1/download"] = BIG

    sync(config, client)

    assert (config.dest / CSE / "slides.pdf").read_bytes() == b"%PDF"
    note = (config.dest / CSE / "Week 3.md").read_text(encoding="utf-8")
    assert "Files saved next to this note:\n- slides.pdf\n" in note
    assert "- week3.mp4: <" in note and bodies(fake_bb) == [f"{base}/_p_1/download"]


def test_description_file_that_is_a_video_becomes_a_link(config, client, fake_bb):
    add_document(fake_bb, "_d1_1", "<p>See below.</p>", description=bb_file("901_1", "overview.mov", "video/quicktime"))
    fake_bb.files["/bbcswebdav/xid-901_1"] = BIG
    sync(config, client)
    assert bodies(fake_bb) == []
    note = (config.dest / CSE / "Week recording.md").read_text(encoding="utf-8")
    assert f"{HEADING}\n- overview.mov: <{BASE}/bbcswebdav/xid-901_1>" in note


def test_announcement_video_is_a_link_and_not_reprocessed(config, client, fake_bb):
    add_announcement(fake_bb, f"<p>Watch this.</p>{bb_file('902_1', 'rec.mp4', 'video/mp4')}")
    report = sync(config, client)
    assert bodies(fake_bb) == [] and bodies(fake_bb) == []
    assert not [w for c in report.courses for w in c.warnings]
    note = (config.dest / CSE / "Duyurular" / "2026-10-01 Exam rooms.md").read_text(encoding="utf-8")
    assert "Watch this." in note and f"{HEADING}\n- rec.mp4: <{BASE}/bbcswebdav/xid-902_1>" in note
    assert State.load(config.state_file).items["announcement:_13004_1:_n3_1"]["media"]

    fake_bb.calls.clear()
    sync(config, client)
    assert not [c for c in fake_bb.calls if "xid-902_1" in c]


def test_announcement_video_found_only_by_its_response_headers(config, client, fake_bb):
    add_announcement(fake_bb, f"<p>Watch this.</p>{bb_file('903_1', 'rec')}")
    path = "/bbcswebdav/pid-700-dt-asiobject-rid-911_1/xid-911_1"
    path = "/bbcswebdav/pid-7-dt-content-rid-903_1/xid-903_1"  # the signed Ultra URL, as embedded
    fake_bb.files[path], fake_bb.content_types[path] = BIG, "video/mp4"
    sync(config, client)
    assert path in fake_bb.calls and bodies(fake_bb) == [] and no_partials(config)
    assert "- rec: <" in (config.dest / CSE / "Duyurular" / "2026-10-01 Exam rooms.md").read_text(encoding="utf-8")


def test_past_term_download_skips_videos_too(config, client, archive):  # noqa: F811
    archive.routes[f"{PAST_ROOT}/contents/_archive_1/attachments"]["results"][0] = {
        "id": "_old1", "fileName": "lecture.mp4", "mimeType": "video/mp4",
    }
    sync(config, client, term_name=PAST)
    assert (config.dest / PAST_COURSE / "second.pdf").exists()
    assert not (config.dest / PAST_COURSE / "lecture.mp4").exists()
    assert "- lecture.mp4: <" in (config.dest / PAST_COURSE / "Lecture.md").read_text(encoding="utf-8")


def test_every_fetch_file_path_goes_through_the_gate(config, client, fake_bb):
    """The refetch path calls fetch_file with a recorded key and no pre-filter."""
    path = "/bbcswebdav/xid-8_1"
    fake_bb.files[path], fake_bb.content_types[path] = BIG, "video/mp4"
    syncer = Syncer(client, config, State(config.state_file), refetch_missing=True)
    (config.dest / "Dir").mkdir(parents=True)
    with pytest.raises(SkippedMedia):
        syncer.fetch_file("xid:c:i:8_1", "Dir/anything.bin", path, None)  # type: ignore[arg-type]
    assert bodies(fake_bb) == [] and no_partials(config) and tree(config) == []


def test_a_video_saved_by_an_older_version_stays_and_is_not_downloaded_again(config, client, fake_bb):
    path = attach(fake_bb, "_v1_1", "_va_1", "lecture1.mp4", "video/mp4", title="Lecture")
    old = config.dest / CSE / "lecture1.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old video")
    state = State(config.state_file)
    state.record_output("attachment:_13004_1:_va_1", f"{CSE}/lecture1.mp4", "sha", 9)
    state.save()
    fake_bb.content_types[path] = "video/mp4"

    sync(config, client)

    assert old.read_bytes() == b"old video" and bodies(fake_bb) == []
    note_path = config.dest / CSE / "Lecture.md"
    assert not note_path.exists()  # nothing is left to link: the file is still saved locally
    state = State.load(config.state_file)
    assert state.output("attachment:_13004_1:_va_1")["path"] == f"{CSE}/lecture1.mp4"
    assert "attachment:_13004_1:_va_1" in state.items["content:_13004_1:_v1_1"]["outputs"]
