"""One bad file or network blip must not abort the rest of the sync."""

import http.server
import json
import os
import threading

import pytest
import requests

from blackboard_sync import cli
from blackboard_sync.session import http_session

from .test_sync import CSE, SYLLABUS_DL, files_under, sync


def _cli_sync(config, client, monkeypatch):
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_u1"}, "cookies": []}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    return cli.main(
        ["--data-dir", str(config.data_dir), "--base-url", config.base_url,
         "sync", "--json", "--dest", str(config.dest)]
    )


def _block_pdfs(monkeypatch):
    real_replace = os.replace

    def replace(src, dst):
        if str(dst).endswith(".pdf"):
            raise PermissionError(13, "Access is denied (file open in another program)", str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)


def test_oserror_while_placing_a_file_becomes_a_warning(config, client, monkeypatch):
    _block_pdfs(monkeypatch)
    report = sync(config, client)

    assert report.status == "ok"
    assert any("Access is denied" in w for c in report.courses for w in c.warnings)
    # Other items and the other courses still synced.
    assert f"{CSE}/Course Website - Visualizations.md" in files_under(config.dest)
    assert (config.dest / "2026-2027 Güz" / "MTH201 Linear Algebra").is_dir()
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
    assert "MTH201 Linear Algebra" in [p.name for p in (config.dest / "2026-2027 Güz").iterdir()]
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
