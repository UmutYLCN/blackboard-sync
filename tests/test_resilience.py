"""One bad file or network blip must not abort the rest of the sync."""

import http.server
import json
import os
import threading
from pathlib import Path

import pytest
import requests

from blackboard_sync import cli
from blackboard_sync.session import http_session
from blackboard_sync.state import State

from .conftest import FakeResponse, note_text
from .test_sync import CSE, SLIDES, SYLLABUS, SYLLABUS_DL, files_under, sync


def _cli_sync(config, client, monkeypatch):
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_u1"}, "cookies": []}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    return cli.main(
        ["--data-dir", str(config.data_dir), "--base-url", config.base_url,
         "sync", "--json", "--dest", str(config.dest)]
    )


# The PDF files Blackboard serves; the notes' own PDFs are still saved.
DOWNLOADED_PDFS = {Path(SYLLABUS).name, Path(SLIDES).name, "hw1.pdf"}


def _block_pdfs(monkeypatch):
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst).name in DOWNLOADED_PDFS:
            raise PermissionError(13, "Access is denied (file open in another program)", str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)


def test_oserror_while_placing_a_file_becomes_a_warning(config, client, monkeypatch):
    _block_pdfs(monkeypatch)
    report = sync(config, client)

    assert report.status == "ok"
    assert any("Access is denied" in w for c in report.courses for w in c.warnings)
    # Other items and the other courses still synced.
    assert f"{CSE}/Course Website - Visualizations.pdf" in files_under(config.dest)
    assert sorted(c.code for c in report.courses) == ["COE305", "CSE303", "MTH201"]
    assert not list(config.dest.rglob("*.partial"))


def test_cli_writes_report_when_a_file_cannot_be_placed(config, client, capsys, monkeypatch):
    _block_pdfs(monkeypatch)
    assert _cli_sync(config, client, monkeypatch) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert any("Access is denied" in w for c in out["courses"] for w in c["warnings"])
    assert config.last_run_file.exists()


def test_failed_item_is_retried_on_the_next_run(config, client, monkeypatch):
    with monkeypatch.context() as m:
        _block_pdfs(m)
        sync(config, client)
    report = sync(config, client)
    assert f"{CSE}/hw1.pdf" in files_under(config.dest)
    assert report.status == "ok"


def test_one_network_error_skips_only_that_item(config, client, fake_bb):
    real_get = fake_bb.get

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            raise requests.ConnectionError("connection reset")
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)

    assert any("connection reset" in w for c in report.courses for w in c.warnings)
    assert "MTH201" in [c.code for c in report.courses]
    assert f"{CSE}/hw1.pdf" in files_under(config.dest)


def test_cli_always_writes_a_report_on_unexpected_errors(config, client, capsys, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "run_sync", boom)
    assert _cli_sync(config, client, monkeypatch) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "error" and "kaboom" in out["message"]
    assert json.loads(config.last_run_file.read_text(encoding="utf-8"))["status"] == "error"


def test_http_session_retries_get_only_on_transient_statuses():
    retry = http_session({"cookies": []}).get_adapter("https://x.example").max_retries
    assert retry.total == 3
    assert retry.backoff_factor > 0
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.allowed_methods == frozenset({"GET"})


class _Flaky(http.server.BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        self.send_response(503 if type(self).hits <= 2 else 200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def test_transient_503_is_retried_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr("urllib3.util.retry.time.sleep", sleeps.append)
    _Flaky.hits = 0
    server = http.server.HTTPServer(("127.0.0.1", 0), _Flaky)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        resp = http_session({"cookies": []}).get(f"http://127.0.0.1:{server.server_port}/", timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    assert resp.status_code == 200 and _Flaky.hits == 3
    assert sleeps  # backed off between attempts


@pytest.mark.parametrize("status", [404, 410, 403])
def test_unavailable_attachment_is_recorded_and_not_retried_until_modified(config, client, fake_bb, status):
    real_get = fake_bb.get
    failing = [True]
    hits = []

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            hits.append(url)
            if failing[0]:
                return FakeResponse(status, url=url, content=b"Not Found")
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)

    assert report.status == "ok"
    assert len(hits) == 1
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert len(cse.failed_files) == 1
    failed = cse.failed_files[0]
    assert failed["name"] == Path(SYLLABUS).name
    assert failed["status"] == status
    assert "courseId=_13004_1" in failed["link"] and "contentId=_c11_1" in failed["link"]
    assert any(f"HTTP {status}" in w for w in cse.warnings)
    assert SYLLABUS not in files_under(config.dest)

    # State marks the item complete (not partial) with the attachment in ``unavailable`` and writes a note PDF.
    state = State.load(config.state_file)
    item_state = state.items["content:_13004_1:_c11_1"]
    assert "partial" not in item_state
    assert item_state["unavailable"] == ["attachment:_13004_1:_a11_1"]
    note_rel = state.outputs["note:_13004_1:_c11_1"]["path"]
    note_path = config.dest / note_rel
    assert note_path.exists()
    note = note_text(note_path)
    assert "Open in Blackboard:" in note
    assert failed["link"] in note

    # Next run with the same modified: no retry, no failed_files, no warnings.
    hits.clear()
    second = sync(config, client)
    cse2 = next(c for c in second.courses if c.code == "CSE303")
    assert hits == []
    assert cse2.failed_files == [] and cse2.warnings == []

    # Deleting the note PDF locally rebuilds it without retrying the unavailable file or warning again.
    note_path.unlink()
    hits.clear()
    restored = sync(config, client)
    cse_restored = next(c for c in restored.courses if c.code == "CSE303")
    assert hits == []
    assert cse_restored.failed_files == [] and cse_restored.warnings == []
    assert note_path.exists()

    # Once modified changes (instructor re-uploads), the attachment is retried and succeeds.
    failing[0] = False
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children"]["results"][0]["modified"] = (
        "2026-10-05T12:00:00.000Z"
    )
    hits.clear()
    third = sync(config, client)
    cse3 = next(c for c in third.courses if c.code == "CSE303")
    assert len(hits) == 1
    assert SYLLABUS in files_under(config.dest)
    assert cse3.failed_files == [] and cse3.warnings == []
    refreshed_state = State.load(config.state_file).items["content:_13004_1:_c11_1"]
    assert "unavailable" not in refreshed_state and "partial" not in refreshed_state


def test_transient_500_attachment_stays_partial_and_is_retried(config, client, fake_bb):
    real_get = fake_bb.get
    failing = [True]

    def get(url, **kw):
        if failing[0] and url.endswith(SYLLABUS_DL):
            return FakeResponse(500, url=url, content=b"Internal Server Error")
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)

    cse = next(c for c in report.courses if c.code == "CSE303")
    assert len(cse.failed_files) == 1
    assert cse.failed_files[0]["name"] == Path(SYLLABUS).name
    assert cse.failed_files[0]["status"] == 500
    assert any("HTTP 500" in w for w in cse.warnings)
    item_state = State.load(config.state_file).items["content:_13004_1:_c11_1"]
    assert item_state.get("partial") is True
    assert "unavailable" not in item_state

    # Next run retries even without a modified change.
    failing[0] = False
    fake_bb.calls.clear()
    second = sync(config, client)
    cse2 = next(c for c in second.courses if c.code == "CSE303")
    assert SYLLABUS_DL in fake_bb.downloads()
    assert SYLLABUS in files_under(config.dest)
    assert cse2.failed_files == [] and cse2.warnings == []
    assert "partial" not in State.load(config.state_file).items["content:_13004_1:_c11_1"]


def test_unavailable_announcement_embedded_file_is_not_retried_until_modified(config, client, fake_bb):
    ann_route = "/learn/api/public/v1/courses/_13004_1/announcements"
    ann = fake_bb.routes[ann_route]["results"][0]
    ann_id = ann["id"]
    ann["body"] = '<p>See <a href="/bbcswebdav/xid-999_1">missing.pdf</a></p>'
    real_get = fake_bb.get
    hits = []

    def get(url, **kw):
        if url.endswith("/bbcswebdav/xid-999_1"):
            hits.append(url)
            return FakeResponse(404, url=url, content=b"Not Found")
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)

    assert len(hits) == 1
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert len(cse.failed_files) == 1
    assert cse.failed_files[0]["name"] == "missing.pdf"
    assert cse.failed_files[0]["status"] == 404
    assert cse.failed_files[0]["link"].endswith("/ultra/courses/_13004_1/announcements")
    ann_state = State.load(config.state_file).items[f"announcement:_13004_1:{ann_id}"]
    assert "partial" not in ann_state
    assert ann_state["unavailable"] == [f"xid:_13004_1:announcement:{ann_id}:999_1"]
    ann_note = note_text(config.dest / CSE / "Duyurular" / "2026-09-20 Welcome to CSE303.pdf")
    assert "missing.pdf" in ann_note

    hits.clear()
    second = sync(config, client)
    cse2 = next(c for c in second.courses if c.code == "CSE303")
    assert hits == []
    assert cse2.failed_files == [] and cse2.warnings == []
