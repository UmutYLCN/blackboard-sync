"""Download hardening tests: mtime, Range resume, unstable network, 255B cap, extensions, sockets, MOTW."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from blackboard_sync import api as api_mod
from blackboard_sync import cli, gcal, i18n, login, session_refresh
from blackboard_sync import sync as sync_mod
from blackboard_sync.api import BlackboardClient, PartialTransfer
from blackboard_sync.menubar import main_window_model
from blackboard_sync.menubar.model import AppModel, RunOutcome
from blackboard_sync.paths import (
    MAX_NAME_BYTES,
    append_suffix,
    ensure_extension,
    fit_windows_folder,
    has_real_extension,
    markdown_twin,
    note_name,
    numbered_variant,
    sanitize_name,
)
from blackboard_sync.state import State, intact, untouched
from blackboard_sync.sync import UNSTABLE_NETWORK_DROPS, parse_time, run_sync
from blackboard_sync.windows import webui_state

from .conftest import BASE_URL, FakeResponse, note_markdown
from .test_sync import CSE, SLIDES, SYLLABUS, SYLLABUS_DL, _route_item, files_under, sync


# ---------------------------------------------------------------------------
# 1. Downloaded files and folders take Blackboard's ``modified`` timestamp
# ---------------------------------------------------------------------------


def test_downloaded_files_notes_and_folders_take_blackboard_modified_date(config, client, fake_bb):
    # Give course a modified date as well so we can verify the course folder mtime.
    fake_bb.routes["/learn/api/public/v1/users/_900_1/courses"]["results"][0]["course"]["modified"] = (
        "2026-09-15T12:30:00.000Z"
    )
    sync(config, client)

    # Attachment takes item's modified timestamp.
    syllabus_mtime = parse_time("2026-09-01T10:05:00.000Z").timestamp()
    assert abs((config.dest / SYLLABUS).stat().st_mtime - syllabus_mtime) < 1

    # Embedded file and its note + hidden Markdown twin take their item's modified timestamp.
    slides_mtime = parse_time("2026-09-22T10:10:00.000Z").timestamp()
    assert abs((config.dest / SLIDES).stat().st_mtime - slides_mtime) < 1
    note_pdf = config.dest / CSE / "Lecture Notes" / "Week 1" / "Intro - Asymptotic Notation.pdf"
    assert abs(note_pdf.stat().st_mtime - slides_mtime) < 1
    assert abs(note_markdown(note_pdf).stat().st_mtime - slides_mtime) < 1

    # Announcement note and announcements folder take the announcement's modified timestamp.
    ann_mtime = parse_time("2026-09-20T08:00:00.000Z").timestamp()
    ann_pdf = config.dest / CSE / "Duyurular" / "2026-09-20 Welcome to CSE303.pdf"
    assert abs(ann_pdf.stat().st_mtime - ann_mtime) < 1
    assert abs((config.dest / CSE / "Duyurular").stat().st_mtime - ann_mtime) < 1

    # Nested Blackboard folders take their own modified timestamps (post-order, not clobbered by children).
    assert abs((config.dest / CSE / "Syllabus").stat().st_mtime - parse_time("2026-09-01T10:00:00.000Z").timestamp()) < 1
    assert abs((config.dest / CSE / "Lecture Notes" / "Week 1").stat().st_mtime - parse_time("2026-09-22T10:00:00.000Z").timestamp()) < 1
    assert abs((config.dest / CSE / "Lecture Notes").stat().st_mtime - parse_time("2026-09-01T10:00:00.000Z").timestamp()) < 1
    assert abs((config.dest / CSE).stat().st_mtime - parse_time("2026-09-15T12:30:00.000Z").timestamp()) < 1

    # Recorded mtime_ns matches the stamped timestamp so intact()/untouched() work cleanly.
    state = State.load(config.state_file)
    entry = state.outputs["attachment:_13004_1:_a11_1"]
    assert entry["mtime_ns"] == (config.dest / SYLLABUS).stat().st_mtime_ns
    assert intact(config.dest / SYLLABUS, entry)
    assert untouched(config.dest / SYLLABUS, entry)


def test_file_falls_back_to_http_last_modified_when_item_has_no_modified(config, client, fake_bb):
    _route_item(fake_bb, "_c11_1").pop("modified")
    real_get = fake_bb.get

    def get(url, **kw):
        resp = real_get(url, **kw)
        if url.endswith(SYLLABUS_DL):
            resp.headers["Last-Modified"] = "Wed, 16 Sep 2026 14:20:00 GMT"
        return resp

    fake_bb.get = get
    sync(config, client)
    expected = datetime(2026, 9, 16, 14, 20, 0, tzinfo=timezone.utc).timestamp()
    assert abs((config.dest / SYLLABUS).stat().st_mtime - expected) < 1


# ---------------------------------------------------------------------------
# 2. HTTP Range resume & unstable-network notice
# ---------------------------------------------------------------------------


class _FlakyChunkResponse(FakeResponse):
    """Yields ``prefix`` bytes then raises ``error`` mid-stream."""

    def __init__(self, status_code, url, prefix: bytes, headers: dict, error: Exception | None = None):
        super().__init__(status_code, url, content=prefix, headers=headers)
        self._error = error
        self.closed = False

    def iter_content(self, chunk_size=1):
        if self.content:
            yield self.content
        if self._error is not None:
            raise self._error

    def close(self):
        self.closed = True


def test_in_run_range_resume_recovers_mid_stream_drop(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body = b"0123456789ABCDEF" * 40  # 640 bytes
    fake_bb.files[SYLLABUS_DL] = body
    real_get = fake_bb.get
    seen_ranges: list[tuple[str | None, str | None]] = []
    responses: list[_FlakyChunkResponse] = []

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            hdrs = kw.get("headers") or {}
            rng, if_range = hdrs.get("Range"), hdrs.get("If-Range")
            seen_ranges.append((rng, if_range))
            if len(seen_ranges) == 1:
                resp = _FlakyChunkResponse(
                    200, url, body[:200],
                    {"Content-Type": "application/pdf", "Content-Length": str(len(body)), "ETag": '"v1"'},
                    error=requests.exceptions.ChunkedEncodingError("connection dropped"),
                )
            else:
                assert rng == "bytes=200-" and if_range == '"v1"'
                resp = _FlakyChunkResponse(
                    206, url, body[200:],
                    {
                        "Content-Type": "application/pdf",
                        "Content-Range": f"bytes 200-{len(body) - 1}/{len(body)}",
                        "Content-Length": str(len(body) - 200),
                        "ETag": '"v1"',
                    },
                )
            responses.append(resp)
            return resp
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)

    assert report.status == "ok"
    assert report.network_drops == 1
    assert report.unstable_network is False  # single recovered blip stays quiet
    assert (config.dest / SYLLABUS).read_bytes() == body
    assert not list(config.dest.rglob("*.partial"))
    assert all(r.closed for r in responses)
    assert State.load(config.state_file).partials == {}


def test_silent_truncation_triggers_range_resume_and_never_places_truncated_file(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body = b"ABCDEFGHIJ" * 30
    fake_bb.files[SYLLABUS_DL] = body
    real_get = fake_bb.get
    attempt = 0

    def get(url, **kw):
        nonlocal attempt
        if url.endswith(SYLLABUS_DL):
            attempt += 1
            if attempt == 1:
                # Ends cleanly with only 100 of 300 bytes (silent premature EOF).
                return _FlakyChunkResponse(
                    200, url, body[:100],
                    {"Content-Type": "application/pdf", "Content-Length": str(len(body)), "ETag": '"e1"'},
                )
            assert (kw.get("headers") or {}).get("Range") == "bytes=100-"
            return _FlakyChunkResponse(
                206, url, body[100:],
                {
                    "Content-Type": "application/pdf",
                    "Content-Range": f"bytes 100-{len(body) - 1}/{len(body)}",
                    "ETag": '"e1"',
                },
            )
        return real_get(url, **kw)

    fake_bb.get = get
    report = sync(config, client)
    assert report.status == "ok" and attempt == 2
    assert (config.dest / SYLLABUS).read_bytes() == body


@pytest.mark.parametrize("reason", ["server_returns_200", "wrong_range_start", "changed_total_size", "changed_etag", "status_416"])
def test_range_resume_restarts_cleanly_when_206_is_invalid_or_rejected(tmp_path, monkeypatch, reason):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body_v1 = b"AAAA" * 50  # 200 bytes
    body_v2 = b"BBBB" * 60  # 240 bytes
    calls: list[dict] = []

    class SessionStub:
        headers: dict = {}

        def get(self, url, **kw):
            hdrs = dict(kw.get("headers") or {})
            calls.append(hdrs)
            if len(calls) == 1:
                return _FlakyChunkResponse(
                    200, url, body_v1[:80],
                    {"Content-Type": "application/pdf", "Content-Length": str(len(body_v1)), "ETag": '"v1"'},
                    error=requests.ConnectionError("reset"),
                )
            if len(calls) == 2:
                assert hdrs.get("Range") == "bytes=80-"
                if reason == "server_returns_200":
                    return _FlakyChunkResponse(
                        200, url, body_v2,
                        {"Content-Type": "application/pdf", "Content-Length": str(len(body_v2)), "ETag": '"v2"'},
                    )
                if reason == "wrong_range_start":
                    return _FlakyChunkResponse(
                        206, url, body_v1[40:],
                        {"Content-Range": f"bytes 40-{len(body_v1) - 1}/{len(body_v1)}", "ETag": '"v1"'},
                    )
                if reason == "changed_total_size":
                    return _FlakyChunkResponse(
                        206, url, body_v2[80:],
                        {"Content-Range": f"bytes 80-{len(body_v2) - 1}/{len(body_v2)}", "ETag": '"v1"'},
                    )
                if reason == "changed_etag":
                    return _FlakyChunkResponse(
                        206, url, body_v1[80:],
                        {"Content-Range": f"bytes 80-{len(body_v1) - 1}/{len(body_v1)}", "ETag": '"v2"'},
                    )
                if reason == "status_416":
                    return _FlakyChunkResponse(416, url, b"", {})
            # Clean restart without Range header
            assert "Range" not in hdrs
            return _FlakyChunkResponse(
                200, url, body_v2,
                {"Content-Type": "application/pdf", "Content-Length": str(len(body_v2)), "ETag": '"v2"'},
            )

    dl = BlackboardClient(BASE_URL, SessionStub()).download("/file.pdf", tmp_path, expected_name="file.pdf")
    try:
        assert dl.path.read_bytes() == body_v2
        assert dl.size == len(body_v2)
        expected_calls = 2 if reason == "server_returns_200" else 3
        assert len(calls) == expected_calls
    finally:
        dl.path.unlink(missing_ok=True)


def test_cross_run_range_resume_and_unstable_network_reporting(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body = b"0123456789" * 50  # 500 bytes
    fake_bb.files[SYLLABUS_DL] = body
    real_get = fake_bb.get
    mode = ["fail"]
    seen_ranges: list[str | None] = []

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            rng = (kw.get("headers") or {}).get("Range")
            seen_ranges.append(rng)
            if mode[0] == "fail":
                if rng is None:
                    return _FlakyChunkResponse(
                        200, url, body[:120],
                        {"Content-Type": "application/pdf", "Content-Length": str(len(body)), "ETag": '"v1"'},
                        error=requests.ConnectionError("drop 1"),
                    )
                raise requests.ConnectionError("still offline")
            assert rng == "bytes=120-"
            return _FlakyChunkResponse(
                206, url, body[120:],
                {
                    "Content-Type": "application/pdf",
                    "Content-Range": f"bytes 120-{len(body) - 1}/{len(body)}",
                    "ETag": '"v1"',
                },
            )
        return real_get(url, **kw)

    fake_bb.get = get

    # Run 1: drops repeatedly past MAX_RESUME_ATTEMPTS -> transient failure + unstable network + kept partial.
    report1 = sync(config, client, lock_held=True)
    assert report1.status == "ok"
    assert report1.network_drops >= UNSTABLE_NETWORK_DROPS
    assert report1.unstable_network is True
    assert "Your internet connection seems unstable" in report1.render_text()
    assert not (config.dest / SYLLABUS).exists()  # never truncated under final name
    cse1 = next(c for c in report1.courses if c.code == "CSE303")
    assert len(cse1.failed_files) == 1 and cse1.failed_files[0]["status"] is None  # transient
    state1 = State.load(config.state_file)
    assert state1.items["content:_13004_1:_c11_1"].get("partial") is True
    partial_entry = state1.partials["attachment:_13004_1:_a11_1"]
    partial_file = config.dest / partial_entry["path"]
    assert partial_file.is_file() and partial_file.read_bytes() == body[:120]

    # Run 2 (even with lock_held=True): tracked partial is kept and resumed from byte 120!
    mode[0] = "resume"
    seen_ranges.clear()
    report2 = sync(config, client, lock_held=True)
    assert seen_ranges == ["bytes=120-"]
    assert (config.dest / SYLLABUS).read_bytes() == body
    assert not partial_file.exists()
    assert report2.unstable_network is False
    cse2 = next(c for c in report2.courses if c.code == "CSE303")
    assert cse2.failed_files == []
    state2 = State.load(config.state_file)
    assert state2.partials == {}
    assert "partial" not in state2.items["content:_13004_1:_c11_1"]


def test_cross_run_partial_restarts_cleanly_when_item_modified_changes(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body_v1 = b"OLD" * 100
    body_v2 = b"NEW" * 100
    fake_bb.files[SYLLABUS_DL] = body_v1
    real_get = fake_bb.get
    failing = [True]
    ranges: list[str | None] = []

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            rng = (kw.get("headers") or {}).get("Range")
            ranges.append(rng)
            if failing[0]:
                if rng is None:
                    return _FlakyChunkResponse(
                        200, url, body_v1[:50],
                        {"Content-Type": "application/pdf", "Content-Length": str(len(body_v1))},
                        error=requests.ConnectionError("drop"),
                    )
                raise requests.ConnectionError("drop")
        return real_get(url, **kw)

    fake_bb.get = get
    sync(config, client, lock_held=True)
    old_partial = config.dest / State.load(config.state_file).partials["attachment:_13004_1:_a11_1"]["path"]
    assert old_partial.is_file()

    # Instructor uploads a newer version before the next sync -> must NOT resume old partial!
    failing[0] = False
    _route_item(fake_bb, "_c11_1")["modified"] = "2026-10-05T12:00:00.000Z"
    fake_bb.files[SYLLABUS_DL] = body_v2
    ranges.clear()
    sync(config, client, lock_held=True)

    assert ranges == [None]  # clean full download, no Range header
    assert (config.dest / SYLLABUS).read_bytes() == body_v2
    assert not old_partial.exists()
    assert State.load(config.state_file).partials == {}


def test_cross_run_partial_cleared_when_server_returns_404(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(api_mod, "_sleep", lambda _: None)
    body = b"DATA" * 80
    fake_bb.files[SYLLABUS_DL] = body
    real_get = fake_bb.get
    phase = ["drop"]

    def get(url, **kw):
        if url.endswith(SYLLABUS_DL):
            if phase[0] == "drop":
                if (kw.get("headers") or {}).get("Range") is None:
                    return _FlakyChunkResponse(
                        200, url, body[:40], {"Content-Length": str(len(body))},
                        error=requests.ConnectionError("drop"),
                    )
                raise requests.ConnectionError("drop")
            return FakeResponse(404, url, content=b"Gone")
        return real_get(url, **kw)

    fake_bb.get = get
    sync(config, client, lock_held=True)
    partial_path = config.dest / State.load(config.state_file).partials["attachment:_13004_1:_a11_1"]["path"]
    assert partial_path.is_file()

    phase[0] = "404"
    report = sync(config, client, lock_held=True)
    cse = next(c for c in report.courses if c.code == "CSE303")
    assert cse.failed_files[0]["status"] == 404
    assert not partial_path.exists()
    state = State.load(config.state_file)
    assert state.partials == {}
    assert state.items["content:_13004_1:_c11_1"]["unavailable"] == ["attachment:_13004_1:_a11_1"]


@pytest.mark.parametrize("language, title, detail", [
    (
        "en",
        "Your internet connection seems unstable",
        "Downloads were interrupted several times. Interrupted files resume automatically when the connection steadies.",
    ),
    (
        "tr",
        "İnternet bağlantınız dengesiz görünüyor",
        "İndirmeler birkaç kez kesintiye uğradı. Bağlantı düzeldiğinde yarım kalan dosyalar kaldığı yerden kendiliğinden devam eder.",
    ),
])
def test_unstable_network_attention_item_en_and_tr(monkeypatch, tmp_path, language, title, detail):
    monkeypatch.setattr(i18n, "_language", language)
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    outcome = RunOutcome.from_report({
        "status": "ok",
        "finished_at": now.isoformat(),
        "unstable_network": True,
        "warnings": [],
        "courses": [],
    })
    assert outcome.unstable_network is True
    model = AppModel(
        dest=tmp_path,
        now=now,
        last=outcome,
        session={"user": {"displayName": "Ada"}, "saved_at": int(now.timestamp())},
    )
    (item,) = main_window_model.attention_items(model)
    assert item.title == title
    assert item.detail == detail
    assert item.warning is True
    # WebView2 state passes it straight through with no new UI surface needed.
    web = webui_state.attention_items((item,))
    assert web == [{"id": "", "title": title, "detail": detail, "action_title": "", "warning": True}]


# ---------------------------------------------------------------------------
# 3. 255-byte cap for multi-byte Turkish/Arabic names & no mass renames
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("stem, ext", [
    ("Öğretim Üyesi Ders Materyalleri ve Çözümlü Alıştırmalar " * 10, ".pdf"),
    ("مقدمة في علوم الحاسوب والخوارزميات المتقدمة وتراكيب البيانات " * 10, ".ipynb"),
    ("تحليل الخوارزميات " * 20, ".m"),
    ("ŞĞÜİÖÇşğüıöç" * 40, ".docx"),
])
def test_multibyte_names_never_exceed_255_bytes_and_keep_extension(windows, stem, ext):
    out = sanitize_name(stem + ext, windows=windows)
    assert out.endswith(ext)
    assert len(out.encode("utf-8")) <= MAX_NAME_BYTES

    numbered = numbered_variant("folder/" + out, 12, windows=windows).split("/")[-1]
    assert numbered.endswith(f" (12){ext}")
    assert len(numbered.encode("utf-8")) <= MAX_NAME_BYTES

    note = note_name(stem, windows=windows)
    assert note.endswith(".pdf")
    assert len(note.encode("utf-8")) <= MAX_NAME_BYTES
    twin = markdown_twin("folder/" + note).split("/")[-1]
    assert twin.startswith(".") and twin.endswith(".md")
    assert len(twin.encode("utf-8")) <= MAX_NAME_BYTES

    disambig = append_suffix(stem, "CSE303-1", windows=windows)
    assert disambig.endswith(" (CSE303-1)")
    assert len(disambig.encode("utf-8")) <= MAX_NAME_BYTES


def test_fit_windows_folder_never_exceeds_255_utf8_bytes():
    arabic = "الرياضيات المتقدمة " * 30
    fitted = fit_windows_folder(Path("C:/U"), "", arabic)
    assert len(fitted.encode("utf-8")) <= MAX_NAME_BYTES


def test_existing_legacy_macos_files_and_folders_are_not_renamed(config, client, fake_bb, monkeypatch):
    monkeypatch.setattr(sync_mod, "is_windows", lambda platform=None: False)
    # Give a Blackboard folder a "?" in its title that older macOS versions kept verbatim.
    _route_item(fake_bb, "_c1_1")["title"] = "What is a syllabus?"
    legacy_folder = f"{CSE}/What is a syllabus?"
    legacy_file = f"{legacy_folder}/Q1 \"Intro\"?.pdf"
    (config.dest / legacy_folder).mkdir(parents=True)
    (config.dest / legacy_file).write_bytes(b"%PDF syllabus v1")
    # Pre-populate state as if an older macOS version had already synced it.
    state = State(config.state_file)
    state.use_school(config.base_url)
    st = (config.dest / legacy_file).stat()
    state.record_output(
        "attachment:_13004_1:_a11_1",
        legacy_file,
        sync_mod.sha256_file(config.dest / legacy_file),
        st.st_size,
        st.st_mtime_ns,
    )
    state.record_item("content:_13004_1:_c11_1", "2026-09-01T10:05:00.000Z", ["attachment:_13004_1:_a11_1"], "Syllabus.pdf")
    state.save()

    # Add a brand-new item inside that same Blackboard folder.
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c1_1/children"]["results"].append({
        "id": "_c12_1", "title": "extra.pdf", "position": 1,
        "modified": "2026-09-02T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-file"},
    })
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c12_1/attachments"] = {
        "results": [{"id": "_a12_1", "fileName": "extra.pdf", "mimeType": "application/pdf"}]
    }
    fake_bb.files["/learn/api/public/v1/courses/_13004_1/contents/_c12_1/attachments/_a12_1/download"] = b"%PDF extra"

    sync(config, client)

    # Existing legacy file and folder stay intact; no duplicate sanitized folder created!
    assert (config.dest / legacy_file).is_file()
    assert (config.dest / legacy_folder / "extra.pdf").read_bytes() == b"%PDF extra"
    assert not (config.dest / CSE / "What is a syllabus").exists()


# ---------------------------------------------------------------------------
# 4. Real extensions preserved (.ipynb, .m); MIME fallback only when missing
# ---------------------------------------------------------------------------


def test_ensure_extension_preserves_real_extensions_and_guesses_when_missing():
    # Real extensions are ALWAYS kept regardless of MIME type.
    assert has_real_extension("lab1.ipynb")
    assert has_real_extension("solver.m")
    assert has_real_extension("plot.R")
    assert has_real_extension("archive.7z")
    assert ensure_extension("lab1.ipynb", "application/json", "text/plain") == "lab1.ipynb"
    assert ensure_extension("solver.m", "text/plain", "application/octet-stream") == "solver.m"
    assert ensure_extension("report.docx", "application/zip") == "report.docx"

    # Extensionless names (including numeric suffixes like "Homework 1.2") guess from MIME.
    assert not has_real_extension("Lecture 1")
    assert not has_real_extension("Homework 1.2")
    assert ensure_extension("Lecture 1", "application/pdf") == "Lecture 1.pdf"
    assert ensure_extension("Homework 1.2", "application/pdf; charset=utf-8") == "Homework 1.2.pdf"
    assert ensure_extension("Data", "text/csv") == "Data.csv"
    assert ensure_extension("Slides", "application/vnd.openxmlformats-officedocument.presentationml.presentation") == "Slides.pptx"

    # Content-Disposition fallback extension beats MIME guessing.
    assert ensure_extension("Week 1 Notebook", "application/json", fallback_name="week1.ipynb") == "Week 1 Notebook.ipynb"

    # Generic MIME types never add a bogus extension.
    assert ensure_extension("README", "application/octet-stream") == "README"
    assert ensure_extension("README", "") == "README"

    # Adding an extension to a 255-byte Turkish/Arabic name stays within 255 UTF-8 bytes.
    long_base = sanitize_name("أ" * 200, windows=False)
    with_ext = ensure_extension(long_base, "application/pdf", windows=False)
    assert with_ext.endswith(".pdf") and len(with_ext.encode("utf-8")) <= MAX_NAME_BYTES


def test_sync_keeps_ipynb_and_m_extensions_and_guesses_only_for_extensionless(config, client, fake_bb):
    atts_url = "/learn/api/public/v1/courses/_13004_1/contents/_c4_1/attachments"
    fake_bb.routes[atts_url]["results"] = [
        {"id": "_a_nb", "fileName": "lab1.ipynb", "mimeType": "application/json"},
        {"id": "_a_m", "fileName": "ode_solver.m", "mimeType": "text/plain"},
        {"id": "_a_noext", "fileName": "Problem Set 1", "mimeType": "application/pdf"},
        {"id": "_a_cd", "fileName": "Starter Code", "mimeType": "application/octet-stream"},
    ]
    base = "/learn/api/public/v1/courses/_13004_1/contents/_c4_1/attachments"
    fake_bb.files[f"{base}/_a_nb/download"] = b'{"cells":[]}'
    fake_bb.files[f"{base}/_a_m/download"] = b"function y = ode_solver(x)\nend\n"
    fake_bb.files[f"{base}/_a_noext/download"] = b"%PDF problem set"
    fake_bb.files[f"{base}/_a_cd/download"] = b"x = 1\n"
    fake_bb.content_types[f"{base}/_a_nb/download"] = "text/plain"
    fake_bb.content_types[f"{base}/_a_m/download"] = "text/plain"
    fake_bb.content_types[f"{base}/_a_noext/download"] = "application/pdf"

    real_get = fake_bb.get

    def get(url, **kw):
        resp = real_get(url, **kw)
        if url.endswith("/_a_cd/download"):
            resp.headers["Content-Disposition"] = 'attachment; filename="starter.m"'
        return resp

    fake_bb.get = get
    sync(config, client)

    saved = files_under(config.dest)
    assert f"{CSE}/lab1.ipynb" in saved
    assert f"{CSE}/ode_solver.m" in saved
    assert f"{CSE}/Problem Set 1.pdf" in saved
    assert f"{CSE}/Starter Code.m" in saved


# ---------------------------------------------------------------------------
# 5. Socket / session / response closing audit
# ---------------------------------------------------------------------------


def test_blackboard_client_closes_responses_and_session():
    closed_responses = []
    session_closed = []

    class TrackingResponse(FakeResponse):
        def close(self):
            closed_responses.append(self.status_code)

    class TrackingSession:
        headers: dict = {}

        def get(self, url, **kw):
            if "fail" in url:
                return TrackingResponse(500, url, {"message": "boom"})
            return TrackingResponse(200, url, {"ok": True})

        def close(self):
            session_closed.append(True)

    with BlackboardClient(BASE_URL, TrackingSession()) as client:
        assert client.get_json("/ok") == {"ok": True}
        with pytest.raises(api_mod.ApiError):
            client.get_json("/fail")

    assert closed_responses == [200, 500]
    assert session_closed == [True]


def test_cli_keep_alive_login_and_gcal_close_sessions(config, client, monkeypatch, capsys):
    # cli.cmd_sync and cli.cmd_check close the BlackboardClient session.
    closed = []
    client.http.close = lambda: closed.append("cli")
    monkeypatch.setattr(cli, "open_client", lambda cfg: (client, {"user": {"id": "_900_1"}, "cookies": []}))
    monkeypatch.setattr(cli, "refresh_saved_cookies", lambda *a: None)
    assert cli.main(["--data-dir", str(config.data_dir), "--base-url", config.base_url, "check"]) == 0
    assert cli.main(["--data-dir", str(config.data_dir), "--base-url", config.base_url, "sync", "--json", "--dest", str(config.dest)]) == 0
    assert closed == ["cli", "cli"]

    # session_refresh.keep_alive closes the Session it opens.
    ka_closed = []

    class FakeKeepAliveHttp:
        headers: dict = {}

        def get(self, url, **kw):
            return FakeResponse(200, url, {"id": "_900_1"})

        def close(self):
            ka_closed.append(True)

    monkeypatch.setattr(session_refresh, "load_session", lambda *a: {"base_url": BASE_URL, "cookies": []})
    monkeypatch.setattr(session_refresh, "http_session", lambda data: FakeKeepAliveHttp())
    monkeypatch.setattr(session_refresh, "refresh_saved_cookies", lambda *a: None)
    assert session_refresh.keep_alive(config).status == session_refresh.ALIVE
    assert ka_closed == [True]

    # login.session_user closes internally-created Session, leaves caller-supplied Session open.
    created_closed = []

    class OwnedSession(requests.Session):
        def get(self, url, **kw):
            return FakeResponse(200, url, {"id": "_900_1"})

        def close(self):
            created_closed.append(True)
            super().close()

    monkeypatch.setattr(login.requests, "Session", OwnedSession)
    assert login.session_user(BASE_URL, []) == {"id": "_900_1"}
    assert created_closed == [True]

    external_closed = []

    class ExternalSession:
        headers: dict = {}
        cookies = requests.cookies.RequestsCookieJar()

        def get(self, url, **kw):
            return FakeResponse(200, url, {"id": "_900_1"})

        def close(self):
            external_closed.append(True)

    assert login.session_user(BASE_URL, [], http=ExternalSession()) == {"id": "_900_1"}
    assert external_closed == []

    # gcal.CalendarClient._request closes every response, and perform() closes its Session.
    gcal_resp_closed = []
    gcal_sess_closed = []

    class GcalResp:
        status_code = 200
        headers: dict = {}

        def json(self):
            return {"ok": True}

        def close(self):
            gcal_resp_closed.append(True)

    class GcalSession:
        def request(self, *a, **kw):
            return GcalResp()

        def close(self):
            gcal_sess_closed.append(True)

    gc = gcal.CalendarClient(config, http=GcalSession())
    assert gc._request("GET", "https://example.invalid") == {"ok": True}
    assert gcal_resp_closed == [True]
    gc.close()
    assert gcal_sess_closed == []  # external http not closed

    monkeypatch.setattr(gcal.requests, "Session", GcalSession)
    gc_owned = gcal.CalendarClient(config)
    gc_owned.close()
    assert gcal_sess_closed == [True]


# ---------------------------------------------------------------------------
# 6. Mark of the Web integration in Syncer (Windows only, best effort, before mtime)
# ---------------------------------------------------------------------------


def test_sync_tags_downloaded_files_with_motw_before_mtime_and_never_fails_on_error(config, client, monkeypatch):
    events: list[tuple[str, str]] = []
    real_apply = sync_mod._apply_mtime

    def fake_motw(path: Path, url: str = "") -> bool:
        events.append(("motw", path.name))
        assert url.startswith(BASE_URL)
        # Simulate non-NTFS / permission failure on one file — must not fail sync.
        return False

    def fake_mtime(path: Path, when, *, only_if_dir: bool = False) -> None:
        if not only_if_dir:
            events.append(("mtime", path.name))
        real_apply(path, when, only_if_dir=only_if_dir)

    monkeypatch.setattr(sync_mod, "mark_of_the_web", fake_motw)
    monkeypatch.setattr(sync_mod, "_apply_mtime", fake_mtime)

    report = sync(config, client)
    assert report.status == "ok"

    # Downloaded files get MOTW strictly before their mtime is stamped; notes do not get MOTW.
    syllabus_name = Path(SYLLABUS).name
    motw_idx = events.index(("motw", syllabus_name))
    mtime_idx = events.index(("mtime", syllabus_name))
    assert motw_idx < mtime_idx
    assert ("motw", "Homework 1.pdf") not in events  # locally generated note
    assert ("motw", "hw1.pdf") in events  # downloaded attachment
    assert ("motw", "week1-slides.pdf") in events  # downloaded embedded file
