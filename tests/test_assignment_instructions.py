"""Public Ultra content responses carry instructor files in handler.instructions.

Shapes match read-only observations from several courses; ids, hosts, tokens and
file bytes below are invented. No assessment/attempt/grade APIs are used.
"""

import html
import json

import pytest

from blackboard_sync.state import State

from .conftest import FakeResponse
from .test_sync import CSE, sync

ROOT = "/learn/api/public/v1/courses/_13004_1/contents"
INSTRUCTIONS = ROOT + "/_instructions_1/attachments"
STAMP = "2026-10-03T09:00:00.000Z"


def file_link(xid="901_1", name="homework.docx", token="FIRST"):
    url = f"https://blackboard.example.edu/bbcswebdav/pid-700-dt-asiobject-rid-{xid}/xid-{xid}?token={token}"
    meta = {"displayName": name, "fileName": name, "resourceUrl": url, "fileSize": 12}
    return f'<a href="{html.escape(url)}" data-bbfile="{html.escape(json.dumps(meta), quote=True)}">{name}</a>'


def add_assessment(fake_bb, instructions=None, root=ROOT, item_id="_instructions_1", handler="resource/x-bb-asmt-test-link"):
    item = {
        "id": item_id, "title": "Assignment 1" if "asmt" in handler else "Test 1",
        "modified": STAMP, "position": 20,
        "contentHandler": {
            "id": handler, "assessmentId": "_700_1", "gradeColumnId": "_800_1",
            "instructions": file_link() if instructions is None else instructions,
            # Other handler fields must never be crawled for files.
            "feedback": file_link("999_1", "feedback.pdf"),
        },
        "submission": {"body": file_link("998_1", "student.docx")},
    }
    fake_bb.routes[root]["results"].append(item)
    collection = root.split("/contents")[0] + f"/contents/{item_id}/attachments"
    real_get = fake_bb.get

    def get(url, **kwargs):
        if url.split("?", 1)[0].endswith(collection):
            return FakeResponse(400, url, {"message": "The Content Item does not support file attachments"})
        return real_get(url, **kwargs)

    fake_bb.get = get
    fake_bb.files["/bbcswebdav/pid-700-dt-asiobject-rid-901_1/xid-901_1"] = b"DOCX instructions"
    return item


def warnings(report):
    return [w for c in report.courses for w in c.warnings]


def test_downloads_instructions_for_assignments_and_tests_across_nested_courses(config, client, fake_bb):
    add_assessment(fake_bb)
    nested = ROOT + "/_c22_1/children"
    add_assessment(fake_bb, {"rawText": file_link("902_1", "test-guide.pdf")}, nested, "_test_1", "resource/x-bb-test")
    other = "/learn/api/public/v1/courses/_13050_1/contents"
    add_assessment(fake_bb, file_link("903_1", "exercise.docx"), other, "_exercise_1")
    for xid in ("902_1", "903_1"):
        fake_bb.files[f"/bbcswebdav/pid-700-dt-asiobject-rid-{xid}/xid-{xid}"] = b"guidelines"

    report = sync(config, client)

    expected = [f"{CSE}/homework.docx", f"{CSE}/Lecture Notes/Week 2/test-guide.pdf",
                "2026-2027 Güz/COE305 Software Project Management/exercise.docx"]
    for name in expected:
        assert (config.root / name).exists()
    assert not warnings(report)
    assert not any("assessment" in c or "gradebook" in c or "attempt" in c for c in fake_bb.calls)
    assert not any("999_1" in c or "998_1" in c for c in fake_bb.calls)
    note = (config.root / CSE / "Assignment 1.md").read_text()
    assert "- homework.docx" in note and "FIRST" not in note


def test_old_state_discovers_instructions_and_signed_url_rotation_does_not_redownload(config, client, fake_bb):
    item = add_assessment(fake_bb, "")
    sync(config, client)  # old releases recorded an empty assignment with this timestamp
    item["contentHandler"]["instructions"] = file_link()
    report = sync(config, client)
    assert f"{CSE}/homework.docx" in next(c for c in report.courses if c.code == "CSE303").new_files
    item["contentHandler"]["instructions"] = file_link(token="SECOND")
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.downloads() == []
    stored = config.state_file.read_text()
    assert "FIRST" not in stored and "SECOND" not in stored and "https://" not in stored


def test_replaced_instruction_with_same_timestamp_updates_file_and_preserves_local_edits(config, client, fake_bb):
    item = add_assessment(fake_bb)
    sync(config, client)
    item["contentHandler"]["instructions"] = file_link("904_1")
    fake_bb.files["/bbcswebdav/pid-700-dt-asiobject-rid-904_1/xid-904_1"] = b"new instructions"
    report = sync(config, client)
    assert next(c for c in report.courses if c.code == "CSE303").updated_files == [f"{CSE}/homework.docx"]
    target = config.root / CSE / "homework.docx"
    assert target.read_bytes() == b"new instructions"
    target.write_bytes(b"my edits")
    item["contentHandler"]["instructions"] = file_link("905_1")
    fake_bb.files["/bbcswebdav/pid-700-dt-asiobject-rid-905_1/xid-905_1"] = b"third version"
    sync(config, client)
    assert target.read_bytes() == b"my edits"
    assert target.with_name("homework (2).docx").read_bytes() == b"third version"


def test_body_and_instructions_are_deduplicated(config, client, fake_bb):
    item = add_assessment(fake_bb)
    item["body"] = file_link()
    sync(config, client)
    assert fake_bb.downloads().count("/bbcswebdav/pid-700-dt-asiobject-rid-901_1/xid-901_1") == 1


@pytest.mark.parametrize("bad_first", [False, True])
def test_partial_failure_downloads_other_files_and_retries_only_failed_instruction(config, client, fake_bb, bad_first):
    bad = file_link("906_1", "later.pdf")
    add_assessment(fake_bb, bad + file_link() if bad_first else file_link() + bad)
    first = sync(config, client)
    assert warnings(first)
    assert (config.root / CSE / "homework.docx").exists()
    state = State.load(config.state_file)
    assert state.items["content:_13004_1:_instructions_1"]["partial"]
    bad_url = "/bbcswebdav/pid-700-dt-asiobject-rid-906_1/xid-906_1"
    fake_bb.calls.clear()
    sync(config, client)
    assert bad_url in fake_bb.calls and fake_bb.downloads() == []
    fake_bb.files[bad_url] = b"recovered"
    fake_bb.calls.clear()
    report = sync(config, client)
    assert not warnings(report)
    assert fake_bb.downloads() == [bad_url]
    assert not State.load(config.state_file).items["content:_13004_1:_instructions_1"].get("partial")


def test_dry_run_and_selective_missing_file_recovery(config, client, fake_bb):
    add_assessment(fake_bb)
    report = sync(config, client, dry_run=True)
    assert f"{CSE}/homework.docx" in next(c for c in report.courses if c.code == "CSE303").new_files
    assert fake_bb.downloads() == [] and not config.state_file.exists() and not config.root.exists()
    sync(config, client)
    path = config.root / CSE / "homework.docx"
    path.unlink()
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.downloads() == [] and not path.exists()
    key = "xid:_13004_1:_instructions_1:901_1"
    sync(config, client, refetch_missing=True, refetch_keys={key})
    assert path.exists()
    path.unlink()
    state = State.load(config.state_file)
    state.dismiss_outputs([key])
    state.save()
    sync(config, client, refetch_missing=True)
    assert not path.exists()


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_real_attachment_collection_failure_warns_and_is_retried(config, client, fake_bb, status):
    add_assessment(fake_bb)
    real_get = fake_bb.get

    def get(url, **kwargs):
        if url.endswith(INSTRUCTIONS):
            return FakeResponse(status, url, {"message": "Request failed"})
        return real_get(url, **kwargs)

    fake_bb.get = get
    report = sync(config, client)
    assert any("Assignment 1" in w and f"HTTP {status}" in w for w in warnings(report))
    assert State.load(config.state_file).items["content:_13004_1:_instructions_1"]["partial"]
    assert (config.root / CSE / "homework.docx").exists()
    fake_bb.calls.clear()
    fake_bb.get = real_get
    assert not warnings(sync(config, client))
    assert fake_bb.downloads() == []
    assert (config.root / CSE / "homework.docx").exists()


def test_empty_instructions_and_explicitly_unsupported_collection_are_silent(config, client, fake_bb):
    add_assessment(fake_bb, "")
    assert not warnings(sync(config, client))


def test_actual_attachment_collection_is_still_downloaded_with_instructions(config, client, fake_bb):
    add_assessment(fake_bb)
    # Replace just the unsupported response with a real attachment collection.
    real_get = fake_bb.get
    att_url = INSTRUCTIONS + "/_att_1/download"

    def get(url, **kwargs):
        if url.endswith(INSTRUCTIONS):
            return FakeResponse(200, url, {"results": [{"id": "_att_1", "fileName": "extra.pdf"}]})
        return real_get(url, **kwargs)

    fake_bb.get = get
    fake_bb.files[att_url] = b"extra instructions"
    assert not warnings(sync(config, client))
    assert (config.root / CSE / "extra.pdf").exists()
    assert (config.root / CSE / "homework.docx").exists()


def test_session_upload_download_and_state_ignore_session_prefix_and_signature(config, client, fake_bb):
    upload_id = "abcdef0123456789abcdef0123456789"

    def instructions(session, token):
        url = f"https://blackboard.example.edu/sessions/AA/{session}/{upload_id}/guide.docx?token={token}"
        meta = {"fileName": "guide.docx", "resourceUrl": url}
        return f'<a data-bbfile="{html.escape(json.dumps(meta), quote=True)}" href="{url}">Guide</a>'

    item = add_assessment(fake_bb, instructions("OLD", "FIRST"))
    path = f"/sessions/AA/OLD/{upload_id}/guide.docx"
    fake_bb.files[path] = b"temporary upload"
    assert not warnings(sync(config, client))
    assert (config.root / CSE / "guide.docx").read_bytes() == b"temporary upload"
    item["contentHandler"]["instructions"] = instructions("NEW", "SECOND")
    fake_bb.calls.clear()
    assert not warnings(sync(config, client))
    assert fake_bb.downloads() == []
    assert "OLD" not in config.state_file.read_text()
    assert "FIRST" not in config.state_file.read_text()
